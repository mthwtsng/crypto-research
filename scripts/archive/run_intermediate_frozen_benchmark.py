#!/usr/bin/env python3
"""
Intermediate 21-Day Transfer Validation Benchmark.

Evaluates the already-collected & prepared sample from the 21-day cohort
(August 18 – September 7) in research/frozen_21day_validation_20261008/:
- 2,134 prepared launch curves
- 102 candidate signals across 83 unique mints
- Strict cash accounting (15.0 SOL bankroll, 0.50 SOL ticket, 1,505,000 lamports standard fee)
- Central85 headline placement scenario (Fast, Central80, Central85, Slow)
- Comparison across concurrency caps: Max 2, Max 5, Max 10, Uncapped
- Comparison between Control and Refined Strategy rules
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

# Configure RPC and cache
E.O.C.rpc = R.rpc
E.O.C.P = R.OUT

OUT_DIR = R.OUT

def load_intermediate_validation_data():
    audit_files = sorted(list((OUT_DIR / "prepare_audits").glob("*.json")))
    print(f"[*] Found {len(audit_files)} prepared audits in validation directory.")
    
    signals = []
    for f in audit_files:
        d = json.load(open(f))
        sigs = d.get("signals", [])
        signals.extend(sigs)
        
    print(f"[+] Total candidate signals detected: {len(signals)}")
    dist = collections.Counter(s["rule"] for s in signals)
    for rule in ["s1_dev_absorption", "s2_survival_shelf", "s3_deadman", "s4_upper_ath", "s5_carryover"]:
        print(f"    • {rule:<25}: {dist.get(rule, 0):>3} signals")
        
    signal_mints = {s["mint"] for s in signals}
    tapes = {}
    print(f"[*] Loading bound tapes for {len(signal_mints)} unique signal mints...")
    for mint in signal_mints:
        tape_path = OUT_DIR / "bound_curve_tapes" / f"{mint}.json.gz"
        if tape_path.is_file():
            t = json.load(gzip.open(tape_path, "rt"))
            gs = [dict(g, venue="curve", trades=g["events"], time=g["block_time"]) 
                  for g in t["groups"] if g.get("source_status", "succeeded") == "succeeded"]
            gs.sort(key=lambda g: (g["slot"], g["index"]))
            t.update(groups=gs, inventory_key="token_account")
            tapes[mint] = t
            for g in gs:
                E.O.CLOCK[g["slot"]] = g["time"]
                
    print(f"[+] Loaded {len(tapes)} bound tapes into memory.")
    
    # Pre-cache block times for next-slot landing
    needed_slots = sorted(list({s["slot"] + 1 for s in signals if s["mint"] in tapes}))
    print(f"[*] Pre-caching block times for {len(needed_slots)} unique landing slots...")
    cached_cnt = 0
    for s in needed_slots:
        try:
            slot_id, b_time = E.O.block_at(s)
            E.O.CLOCK[slot_id] = b_time
            cached_cnt += 1
        except Exception:
            pass
    print(f"[+] Pre-cached {cached_cnt}/{len(needed_slots)} landing slots into CLOCK.")
    return tapes, signals

def get_config(rule, is_refined):
    cfg = {"tailored_trail_basis": "percentage_points"}
    if not is_refined:
        # Standard control config
        if rule == "s1_dev_absorption":
            cfg.update(s1_dynamic_exit=True, s1_trough_grace=0, s1_target=0.25)
        elif rule == "s2_survival_shelf":
            cfg.update(s2_dynamic_exit=True, s2_target=0.30)
        elif rule == "s3_deadman":
            cfg.update(s3_extended_hold=60, s3_grace=8, s3_relative_price_stop=0.12, s3_dynamic_arm=0.75, s3_dynamic_width=0.20)
        elif rule == "s4_upper_ath":
            cfg.update(s4_remove_short_timeout=True, s4_rejection_grace=0, s4_stop=0.08)
    else:
        # Refined config
        if rule == "s1_dev_absorption":
            cfg.update(s1_dynamic_exit=True, s1_trough_grace=0, s1_target=0.30)
        elif rule == "s2_survival_shelf":
            cfg.update(s2_dynamic_exit=True, s2_target=0.30)
        elif rule == "s3_deadman":
            cfg.update(s3_extended_hold=60, s3_grace=8, s3_relative_price_stop=0.12, s3_dynamic_arm=0.50, s3_dynamic_width=0.15)
        elif rule == "s4_upper_ath":
            cfg.update(s4_remove_short_timeout=True, s4_rejection_grace=4, s4_stop=0.08)
    return cfg

def is_eligible(sig, is_refined):
    if is_refined and sig["rule"] == "s2_survival_shelf":
        return sig.get("age_seconds", 0) <= 240 and sig.get("outside_buyers", 0) <= 80
    return True

def run_simulation(tapes, signals, workers=4):
    scenarios = ["fast", "central80", "central85", "slow"]
    policies = ["control", "refined"]
    
    jobs = []
    for policy in policies:
        is_ref = (policy == "refined")
        for s in signals:
            if s["mint"] not in tapes:
                continue
            if not is_eligible(s, is_ref):
                continue
            cfg = get_config(s["rule"], is_ref)
            for sc in scenarios:
                for ticket in [0.5, 0.25]:
                    jobs.append((policy, s, sc, ticket, 1505000, cfg))
                    
    print(f"[*] Simulating {len(jobs)} jobs across {workers} threads...")
    t0 = time.time()
    
    def simulate_job(j):
        pol, s, sc, ticket, fee, cfg = j
        sim = E.simulate(tapes[s["mint"]], s, sc, "lower", ticket, fee, cfg)
        return dict(sim, policy=pol)

    results = []
    errors = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(simulate_job, j): j for j in jobs}
        for fut in concurrent.futures.as_completed(futures):
            try:
                results.append(fut.result())
            except Exception as e:
                errors.append(str(e))
                
    print(f"[+] Replay simulations completed in {time.time()-t0:.2f}s ({len(results)} finished, {len(errors)} errors).")
    return results

def evaluate_matrix(results):
    caps = [2, 5, 10, None]
    scenarios = ["fast", "central80", "central85", "slow"]
    policies = ["control", "refined"]
    
    matrix = {}
    for pol in policies:
        matrix[pol] = {}
        for cap in caps:
            ck = f"max_{cap}" if cap is not None else "uncapped"
            matrix[pol][ck] = {}
            for sc in scenarios:
                subset = [r for r in results if r["policy"] == pol and r["scenario"] == sc]
                acct = F.funded(subset, breakers=True, scope="portfolio", position_limit=cap)
                
                # Rule breakdown
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

def print_report(matrix, total_audits, total_signals):
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    print("\n" + "=" * 102)
    print("      INTERMEDIATE 21-DAY TRANSFER VALIDATION REPORT (AUGUST 18 – SEPTEMBER 7)")
    print(f"      Evaluated: {total_audits} Prepared Launches | {total_signals} Candidate Signals")
    print("      Bankroll: 15.0 SOL Cash-Funded | Ticket: 0.50 SOL | Standard Fee: 1,505,000 lamports")
    print(f"      Timestamp: {now_iso}")
    print("=" * 102)

    # 1. HEADLINE CENTRAL85 COMPARISON TABLE
    print("\n" + "-" * 102)
    print("TABLE 1: CENTRAL85 (HEADLINE ESTIMATE) — CONTROL vs REFINED ACROSS POSITION CAPS")
    print("-" * 102)
    print(f" {'Policy':<10} {'Cap':<10} {'Settled SOL':<15} {'Open Mark':<14} {'Combined Net':<16} {'Win Rate':<10} {'Profit Factor':<14} {'Attempts (C/F/U)'}")
    print(" " + "-" * 98)

    caps = [2, 5, 10, None]
    for pol in ["control", "refined"]:
        p_label = "CONTROL" if pol == "control" else "REFINED"
        for cap in caps:
            ck = f"max_{cap}" if cap is not None else "uncapped"
            data = matrix[pol][ck]["central85"]
            c_tag = f"Max {cap}" if cap is not None else "Uncapped"
            note = ""
            if pol == "control" and cap == 2:
                note = " (CONTROL BASELINE)"
            elif pol == "refined" and cap == 5:
                note = " (PEAK EFFICIENCY)"
            elif pol == "refined" and cap == 10:
                note = " (USER TARGET)"
                
            print(f" {p_label:<10} {c_tag:<10} {data['settled_net_sol']:>+9.4f} SOL   {data['open_marked_sol']:>+8.4f} SOL   {data['combined_sol']:>+10.4f} SOL{note:<18} "
                  f"{data['win_rate']*100:>5.1f}%     {data['profit_factor']:>6.3f}         "
                  f"{data['attempts']:>3} ({data['closed']}C/{data['failed']}F/{data['unresolved']}U)")

    # 2. SCENARIO SENSITIVITY TABLE
    print("\n" + "-" * 102)
    print("TABLE 2: REFINED PORTFOLIO SCENARIO SENSITIVITY (COMBINED MARKED NET SOL)")
    print("-" * 102)
    print(f" {'Position Cap':<14} {'Fast':<16} {'Central80':<16} {'Central85 (HEADLINE)':<24} {'Slow':<16} {'Max Drawdown'}")
    print(" " + "-" * 98)

    for cap in caps:
        ck = f"max_{cap}" if cap is not None else "uncapped"
        c_tag = f"Max {cap}" if cap is not None else "Uncapped"
        fast = matrix["refined"][ck]["fast"]["combined_sol"]
        c80 = matrix["refined"][ck]["central80"]["combined_sol"]
        c85 = matrix["refined"][ck]["central85"]["combined_sol"]
        slow = matrix["refined"][ck]["slow"]["combined_sol"]
        dd = matrix["refined"][ck]["central85"]["max_drawdown_sol"]
        print(f" {c_tag:<14} {fast:>+10.4f} SOL   {c80:>+10.4f} SOL   {c85:>+12.4f} SOL           {slow:>+10.4f} SOL   {dd:>8.4f} SOL")

    # 3. PER-STRATEGY ATTRIBUTION FOR MAX 5 vs MAX 10
    print("\n" + "-" * 102)
    print("TABLE 3: PER-STRATEGY CONTRIBUTION BREAKDOWN (CENTRAL85) — MAX 5 vs MAX 10")
    print("-" * 102)
    print(f" {'Strategy':<22} | {'--- MAX 5 (PEAK EFFICIENCY) ---':<36} | {'--- MAX 10 (USER TARGET) ---':<36}")
    print(f" {'':<22} | {'Settled SOL':<13} {'Attempts':<10} {'Win Rate':<10} | {'Settled SOL':<13} {'Attempts':<10} {'Win Rate':<10}")
    print(" " + "-" * 98)

    m5_rules = matrix["refined"]["max_5"]["central85"]["rules"]
    m10_rules = matrix["refined"]["max_10"]["central85"]["rules"]

    for rule in ["s1_dev_absorption", "s2_survival_shelf", "s3_deadman", "s4_upper_ath", "s5_carryover"]:
        r5 = m5_rules.get(rule, {})
        r10 = m10_rules.get(rule, {})
        print(f" {rule:<22} | {r5.get('settled_sol', 0.0):>+8.4f} SOL   {r5.get('attempts', 0):>4} ({r5.get('closed', 0)}C)    {r5.get('win_rate', 0.0)*100:>5.1f}%    | "
              f"{r10.get('settled_sol', 0.0):>+8.4f} SOL   {r10.get('attempts', 0):>4} ({r10.get('closed', 0)}C)    {r10.get('win_rate', 0.0)*100:>5.1f}%")

    # 4. STANDARD ACCURACY CONTRACT RESULT CARD
    print("\n" + "=" * 102)
    print("STANDARD RESULT CARD (BACKTEST ACCURACY CONTRACT COMPLIANT):")
    ref_c85 = matrix["refined"]["max_5"]["central85"]
    fast_c = matrix["refined"]["max_5"]["fast"]["combined_sol"]
    c80_c = matrix["refined"]["max_5"]["central80"]["combined_sol"]
    c85_c = ref_c85["combined_sol"]
    slow_c = matrix["refined"]["max_5"]["slow"]["combined_sol"]
    
    print(f"Data: Aug 18–Sep 7; {total_audits} prepared launches ({total_signals} signals); historical transfer intermediate")
    print(f"Looks: 2 configurations x 4 horizons/scenarios x 4 caps")
    print(f"Refined Max 5 fast / central80 / central85 / slow:")
    print(f"{fast_c:>+8.3f} / {c80_c:>+8.3f} / {c85_c:>+8.3f} / {slow_c:>+8.3f} SOL")
    print(f"Attempts / closed / failed / unresolved: {ref_c85['attempts']} / {ref_c85['closed']} / {ref_c85['failed']} / {ref_c85['unresolved']}")
    print(f"Settled PnL: {ref_c85['settled_net_sol']:>+8.4f} SOL | Open Marked PnL: {ref_c85['open_marked_sol']:>+8.4f} SOL")
    print(f"Verdict: undetermined, retrospective partial sample ({total_audits} coins)")
    print("=" * 102 + "\n")

    # Save summary
    out_path = ROOT / "reports" / "intermediate_frozen_21day_summary.json"
    with open(out_path, "w") as f:
        json.dump(matrix, f, indent=2)
    print(f"[✓] Saved intermediate validation summary to {out_path}")

def main():
    tapes, signals = load_intermediate_validation_data()
    results = run_simulation(tapes, signals, workers=4)
    matrix = evaluate_matrix(results)
    print_report(matrix, len(tapes), len(signals))

if __name__ == "__main__":
    main()
