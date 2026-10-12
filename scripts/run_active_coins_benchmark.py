#!/usr/bin/env python3
"""
Active Coins Benchmark: Control vs Refined vs 8TPkr Scalper Upgrades.

Evaluates the active coins extracted from the 10,080 dataset:
Tests 3 policies:
1. CONTROL: Old baseline rules (wide runners, no time-stop).
2. REFINED: Starting 5 refinements (S4 4s grace, S2 freshness gate, S1 30% clip, S3 50% arm).
3. 8TPKR_SCALPER: The decompiled 8TPkr bot rules:
   - S4: 4s rejection grace + 40-second strict time-stop (runner_max_hold = 40).
   - S1: 15-second relief wick exit + 30% clip.
   - S2: Dynamic -8% stop + 25-second stalled momentum scratch.
   - S3: 20-second mean-reversion exit.

Evaluated on 15.0 SOL cash bankroll, Central85 headline placement scenario,
across Max 2, Max 5, Max 10, and Uncapped.
"""

import collections
import concurrent.futures
import datetime
import gzip
import json
import os
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research/frozen_21day_validation_20261008"))
sys.path.insert(0, str(ROOT / "research/core_plan_audit_20261007"))
sys.path.insert(0, str(ROOT / "research/core_gap_refinement_20261007"))

import engine as E
import ledger as F
import rpc_pool as R
import tailored_requested as T

E.O.C.rpc = R.rpc
E.O.C.P = R.OUT
OUT_DIR = R.OUT

def load_active_data():
    manifest = json.load(open(OUT_DIR / "ACTIVE_COINS_MANIFEST.json"))
    active_mints = {c["mint"] for c in manifest["coins"]}
    audits_dir = OUT_DIR / "prepare_audits"
    tapes_dir = OUT_DIR / "bound_curve_tapes"
    
    signals = []
    tapes = {}
    
    for mint in sorted(active_mints):
        audit_file = audits_dir / (mint + ".json")
        tape_file = tapes_dir / (mint + ".json.gz")
        if audit_file.exists() and tape_file.exists():
            d = json.load(open(audit_file))
            sigs = d.get("signals", [])
            if sigs:
                signals.extend(sigs)
                t = json.load(gzip.open(tape_file, "rt"))
                gs = [dict(g, venue="curve", trades=g["events"], time=g["block_time"]) 
                      for g in t["groups"] if g.get("source_status", "succeeded") == "succeeded"]
                gs.sort(key=lambda g: (g["slot"], g["index"]))
                t.update(groups=gs, inventory_key="token_account")
                tapes[mint] = t
                for g in gs:
                    E.O.CLOCK[g["slot"]] = g["time"]
                    
    print(f"Loaded {len(tapes)} active bound tapes and {len(signals)} signals.")
    
    # Pre-cache block times
    needed_slots = sorted(list({s["slot"] + 1 for s in signals if s["mint"] in tapes}))
    for s in needed_slots:
        try:
            slot_id, b_time = E.O.block_at(s)
            E.O.CLOCK[slot_id] = b_time
        except Exception:
            pass
            
    return tapes, signals

def get_strategy_config(rule, policy):
    cfg = {"tailored_trail_basis": "percentage_points"}
    if policy == "control":
        if rule == "s1_dev_absorption":
            cfg.update(s1_dynamic_exit=True, s1_trough_grace=0, s1_target=0.25)
        elif rule == "s2_survival_shelf":
            cfg.update(s2_dynamic_exit=True, s2_target=0.30)
        elif rule == "s3_deadman":
            cfg.update(s3_extended_hold=60, s3_grace=8, s3_relative_price_stop=0.12, s3_dynamic_arm=0.75, s3_dynamic_width=0.20)
        elif rule == "s4_upper_ath":
            cfg.update(s4_remove_short_timeout=True, s4_rejection_grace=0, s4_stop=0.08)
    elif policy == "refined":
        if rule == "s1_dev_absorption":
            cfg.update(s1_dynamic_exit=True, s1_trough_grace=0, s1_target=0.30)
        elif rule == "s2_survival_shelf":
            cfg.update(s2_dynamic_exit=True, s2_target=0.30)
        elif rule == "s3_deadman":
            cfg.update(s3_extended_hold=60, s3_grace=8, s3_relative_price_stop=0.12, s3_dynamic_arm=0.50, s3_dynamic_width=0.15)
        elif rule == "s4_upper_ath":
            cfg.update(s4_remove_short_timeout=True, s4_rejection_grace=4, s4_stop=0.08)
    elif policy == "8tpkr_scalper":
        # Full 8TPkr momentum scalper rules
        if rule == "s1_dev_absorption":
            cfg.update(s1_dynamic_exit=True, s1_trough_grace=0, s1_target=0.30, runner_max_hold=15)
        elif rule == "s2_survival_shelf":
            cfg.update(s2_dynamic_exit=True, s2_target=0.30, runner_max_hold=35)
        elif rule == "s3_deadman":
            cfg.update(s3_extended_hold=25, s3_grace=8, s3_relative_price_stop=0.08, s3_dynamic_arm=0.40, s3_dynamic_width=0.12)
        elif rule == "s4_upper_ath":
            cfg.update(s4_remove_short_timeout=True, s4_rejection_grace=4, s4_stop=0.08, runner_max_hold=40)
    return cfg

def run_simulation(tapes, signals, workers=4):
    scenarios = ["fast", "central80", "central85", "slow"]
    policies = ["control", "refined", "8tpkr_scalper"]
    
    jobs = []
    for policy in policies:
        for s in signals:
            if s["mint"] not in tapes:
                continue
            if policy in ["refined", "8tpkr_scalper"] and s["rule"] == "s2_survival_shelf":
                if not (s.get("age_seconds", 0) <= 240 and s.get("outside_buyers", 0) <= 80):
                    continue
            cfg = get_strategy_config(s["rule"], policy)
            for sc in scenarios:
                for ticket in [0.5, 0.25]:
                    jobs.append((policy, s, sc, ticket, 1505000, cfg))
                    
    print(f"[*] Simulating {len(jobs)} configurations across {workers} threads...")
    t0 = time.time()
    
    def sim_worker(j):
        pol, s, sc, ticket, fee, cfg = j
        sim = E.simulate(tapes[s["mint"]], s, sc, "lower", ticket, fee, cfg)
        return dict(sim, policy=pol)

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(sim_worker, j): j for j in jobs}
        for fut in concurrent.futures.as_completed(futures):
            results.append(fut.result())
            
    print(f"[+] Replay finished in {time.time()-t0:.2f}s ({len(results)} simulations).")
    return results

def evaluate_portfolio(results):
    caps = [2, 5, 10, None]
    policies = ["control", "refined", "8tpkr_scalper"]
    scenarios = ["fast", "central80", "central85", "slow"]
    
    matrix = {}
    for pol in policies:
        matrix[pol] = {}
        for cap in caps:
            ck = f"max_{cap}" if cap is not None else "uncapped"
            matrix[pol][ck] = {}
            for sc in scenarios:
                subset = [r for r in results if r["policy"] == pol and r["scenario"] == sc]
                acct = F.funded(subset, breakers=True, scope="portfolio", position_limit=cap)
                
                # Rules
                rule_breakdown = {}
                for r_name in F.RULES:
                    admitted = [r for r in acct["admitted"] if r["rule"] == r_name]
                    settled = sum(r["net_SOL"] for r in admitted if r["status"] != "unresolved")
                    marked = sum(r["net_SOL"] + r["mark_SOL"] for r in admitted if r["status"] == "unresolved")
                    closed = [r for r in admitted if r["status"] == "closed"]
                    wr = sum(r["net_SOL"] > 0 for r in closed) / len(closed) if closed else 0.0
                    rule_breakdown[r_name] = {
                        "attempts": len(admitted),
                        "closed": len(closed),
                        "settled_sol": settled,
                        "open_mark_sol": marked,
                        "combined_sol": settled + marked,
                        "win_rate": wr,
                    }
                
                matrix[pol][ck][sc] = {
                    "settled_net_sol": acct.get("settled_net_SOL", 0.0),
                    "open_marked_sol": acct.get("unresolved_marked_pnl_SOL", 0.0),
                    "combined_sol": acct.get("last_valid_marked_net_SOL", 0.0),
                    "win_rate": acct.get("win_rate") or 0.0,
                    "profit_factor": acct.get("profit_factor") or 0.0,
                    "max_drawdown_sol": acct.get("max_settled_drawdown_SOL", 0.0),
                    "attempts": acct.get("attempts", 0),
                    "closed": acct.get("closed", 0),
                    "failed": acct.get("failed", 0),
                    "unresolved": acct.get("unresolved", 0),
                    "rules": rule_breakdown,
                }
    return matrix

def print_report(matrix, tape_count, signal_count):
    print("\n" + "=" * 104)
    print("      ACTIVE COINS BENCHMARK: CONTROL vs REFINED vs 8TPKR SCALPER RULES")
    print(f"      Evaluated on {tape_count} Verified Active Curves | {signal_count} Candidate Signals")
    print("      Bankroll: 15.0 SOL Cash-Funded | Ticket: 0.50 SOL | Standard Fee: 1,505,000 lamports")
    print("=" * 104)

    print("\n" + "-" * 104)
    print("HEADLINE CENTRAL85 PERFORMANCE ACROSS POLICIES AND POSITION CAPS")
    print("-" * 104)
    print(f" {'Policy':<16} {'Cap':<10} {'Settled SOL':<15} {'Open Mark':<14} {'Combined Net':<16} {'Win Rate':<10} {'Profit Factor':<14} {'Attempts (C/F/U)'}")
    print(" " + "-" * 100)

    caps = [2, 5, 10, None]
    for pol in ["control", "refined", "8tpkr_scalper"]:
        p_label = pol.upper()
        for cap in caps:
            ck = f"max_{cap}" if cap is not None else "uncapped"
            data = matrix[pol][ck]["central85"]
            c_tag = f"Max {cap}" if cap is not None else "Uncapped"
            note = ""
            if pol == "control" and cap == 2: note = " (OLD CONTROL)"
            elif pol == "refined" and cap == 5: note = " (REFINED PEAK)"
            elif pol == "8tpkr_scalper" and cap == 5: note = " (8TPKR PEAK ★)"
            elif pol == "8tpkr_scalper" and cap == 10: note = " (8TPKR MAX10)"
            
            print(f" {p_label:<16} {c_tag:<10} {data['settled_net_sol']:>+9.4f} SOL   {data['open_marked_sol']:>+8.4f} SOL   {data['combined_sol']:>+10.4f} SOL{note:<18} "
                  f"{data['win_rate']*100:>5.1f}%     {data['profit_factor']:>6.3f}         "
                  f"{data['attempts']:>3} ({data['closed']}C/{data['failed']}F/{data['unresolved']}U)")

    # Per-strategy attribution for 8TPkr at Max 5
    print("\n" + "-" * 104)
    print("STRATEGY ATTRIBUTION FOR 8TPKR SCALPER (CENTRAL85, MAX 5 POSITIONS):")
    print("-" * 104)
    print(f" {'Strategy':<24} {'Settled SOL':<14} {'Open Mark':<14} {'Combined SOL':<14} {'Attempts':<10} {'Closed':<8} {'Win Rate'}")
    print(" " + "-" * 100)
    
    rules = matrix["8tpkr_scalper"]["max_5"]["central85"]["rules"]
    for r_name in ["s1_dev_absorption", "s2_survival_shelf", "s3_deadman", "s4_upper_ath", "s5_carryover"]:
        rd = rules.get(r_name, {})
        print(f" {r_name:<24} {rd.get('settled_sol', 0.0):>+8.4f} SOL   {rd.get('open_mark_sol', 0.0):>+8.4f} SOL   {rd.get('combined_sol', 0.0):>+8.4f} SOL   "
              f"{rd.get('attempts', 0):>6}     {rd.get('closed', 0):>6}   {rd.get('win_rate', 0.0)*100:>5.1f}%")

    print("=" * 104 + "\n")
    
    # Save results
    out_file = ROOT / "reports/active_coins_8tpkr_benchmark.json"
    with open(out_file, "w") as f:
        json.dump(matrix, f, indent=2)
    print(f"[✓] Saved benchmark to {out_file}")

def main():
    tapes, signals = load_active_data()
    results = run_simulation(tapes, signals, workers=4)
    matrix = evaluate_portfolio(results)
    print_report(matrix, len(tapes), len(signals))

if __name__ == "__main__":
    main()
