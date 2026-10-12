#!/usr/bin/env python3
"""
Exhaustive Concurrency & Strategy Benchmark Matrix.

Tests:
1. Control vs Fully Refined Strategies across all Starting 5 (S1-S5).
2. Concurrency caps: Max 2, Max 3, Max 5, Max 7, Max 8, Max 10, Uncapped.
3. Execution Scenarios: Fast, Central80, Central85 (Headline), Slow.
4. Strict cash accounting: 15.0 SOL bankroll, 0.50 SOL ticket (0.25 SOL cooldown probe),
   1,505,000 lamports standard fee per transaction, failed attempt penalties.

Single source of truth benchmark on 1,800 creation-selected launches (October 3-6).
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
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research/core_plan_audit_20261007"))
sys.path.insert(0, str(ROOT / "research/core_gap_refinement_20261007"))

import engine as E
import ledger as F
import tailored_requested as T
import grace_requested as G

def load_canonical_data():
    t0 = time.time()
    saved = json.load(gzip.open(G.OUT / "CONTROL_REPLAY.json.gz", "rt"))
    tapes, signals = {}, []
    for window in ["earlier", "later"]:
        restored = G.load(window)
        tapes.update(restored)
        signals.extend(dict(r, window=window) for r in saved
                       if r["window"] == window and r["horizon"] == 60
                       and r["scenario"] == "central85" and r["fee"] == 1505000
                       and r["ticket"] == .5)
    print(f"Loaded {len(tapes)} tapes and {len(signals)} canonical signals in {time.time()-t0:.2f}s.")
    return tapes, signals

def get_strategy_config(rule, is_refined):
    cfg = {
        "tailored_trail_basis": "percentage_points",
    }
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
        elif rule == "s5_carryover":
            pass
    else:
        # Fully refined config
        if rule == "s1_dev_absorption":
            cfg.update(s1_dynamic_exit=True, s1_trough_grace=0, s1_target=0.30)
        elif rule == "s2_survival_shelf":
            cfg.update(s2_dynamic_exit=True, s2_target=0.30)
        elif rule == "s3_deadman":
            cfg.update(s3_extended_hold=60, s3_grace=8, s3_relative_price_stop=0.12, s3_dynamic_arm=0.50, s3_dynamic_width=0.15)
        elif rule == "s4_upper_ath":
            cfg.update(s4_remove_short_timeout=True, s4_rejection_grace=4, s4_stop=0.08)
        elif rule == "s5_carryover":
            pass
    return cfg

def is_signal_eligible(sig, is_refined):
    if is_refined and sig["rule"] == "s2_survival_shelf":
        # Freshness filter: age <= 240s and outside_buyers <= 80
        return sig.get("age_seconds", 0) <= 240 and sig.get("outside_buyers", 0) <= 80
    return True

def run_all_simulations(tapes, signals):
    scenarios = ["fast", "central80", "central85", "slow"]
    policies = ["control", "refined"]
    
    jobs = []
    for policy in policies:
        is_ref = (policy == "refined")
        for s in signals:
            if not is_signal_eligible(s, is_ref):
                continue
            cfg = get_strategy_config(s["rule"], is_ref)
            for sc in scenarios:
                for ticket in [0.5, 0.25]:
                    jobs.append((policy, s, sc, ticket, 1505000, cfg))
                    
    print(f"Simulating {len(jobs)} combinations across threads...")
    t0 = time.time()
    
    def run_job(j):
        pol, s, sc, ticket, fee, cfg = j
        sim = E.simulate(tapes[s["mint"]], s, sc, "lower", ticket, fee, cfg)
        return dict(sim, policy=pol)

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(run_job, j): j for j in jobs}
        for fut in concurrent.futures.as_completed(futures):
            results.append(fut.result())
            
    print(f"Completed {len(results)} simulations in {time.time()-t0:.2f}s.")
    return results

def evaluate_matrix(results):
    caps = [2, 3, 5, 7, 8, 10, None]
    scenarios = ["fast", "central80", "central85", "slow"]
    policies = ["control", "refined"]
    
    matrix = {}
    
    for pol in policies:
        matrix[pol] = {}
        for cap in caps:
            cap_key = f"max_{cap}" if cap is not None else "uncapped"
            matrix[pol][cap_key] = {}
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
                
                matrix[pol][cap_key][sc] = {
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

def print_and_save_report(matrix):
    print("\n" + "=" * 102)
    print("      CONCRETE BENCHMARK REPORT: CONCURRENCY CAPS (MAX 2 -> UNCAPPED) & REFINED RULES")
    print("      15.0 SOL Cash-Funded Bankroll | 0.50 SOL Ticket | 1,505,000 lamports standard fee")
    print("=" * 102)

    # 1. HEADLINE CENTRAL85 COMPARISON TABLE
    print("\n" + "-" * 102)
    print("TABLE 1: HEADLINE CENTRAL85 PERFORMANCE ACROSS ALL POSITION CAPS")
    print("-" * 102)
    print(f" {'Policy':<10} {'Cap':<10} {'Settled SOL':<15} {'Open Mark':<14} {'Combined Net':<16} {'Win Rate':<10} {'Profit Factor':<14} {'Attempts (C/F/U)'}")
    print(" " + "-" * 98)

    caps = [2, 3, 5, 7, 8, 10, None]
    for pol in ["control", "refined"]:
        p_label = "CONTROL" if pol == "control" else "REFINED"
        for cap in caps:
            ck = f"max_{cap}" if cap is not None else "uncapped"
            data = matrix[pol][ck]["central85"]
            c_tag = f"Max {cap}" if cap is not None else "Uncapped"
            note = ""
            if pol == "control" and cap == 2:
                note = " (OLD CONTROL)"
            elif pol == "refined" and cap == 5:
                note = " (PEAK EFFICIENCY)"
            elif pol == "refined" and cap == 10:
                note = " (USER TARGET)"
                
            print(f" {p_label:<10} {c_tag:<10} {data['settled_net_sol']:>+9.4f} SOL   {data['open_marked_sol']:>+8.4f} SOL   {data['combined_sol']:>+10.4f} SOL{note:<18} "
                  f"{data['win_rate']*100:>5.1f}%     {data['profit_factor']:>6.3f}         "
                  f"{data['attempts']:>3} ({data['closed']}C/{data['failed']}F/{data['unresolved']}U)")

    # 2. PLACEMENT SCENARIO SENSITIVITY TABLE FOR REFINED PORTFOLIO
    print("\n" + "-" * 102)
    print("TABLE 2: REFINED PORTFOLIO ACROSS ALL PLACEMENT SCENARIOS (COMBINED MARKED NET SOL)")
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

    # 3. DETAILED PER-STRATEGY ATTRIBUTION FOR MAX 5 vs MAX 10
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

    # Save to JSON
    out_dir = ROOT / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "CONCURRENCY_MATRIX_SUMMARY.json", "w") as f:
        json.dump(matrix, f, indent=2)
    print(f"\n[✓] Saved complete benchmark matrix to reports/CONCURRENCY_MATRIX_SUMMARY.json")
    print("=" * 102 + "\n")

def main():
    tapes, signals = load_canonical_data()
    results = run_all_simulations(tapes, signals)
    matrix = evaluate_matrix(results)
    print_and_save_report(matrix)

if __name__ == "__main__":
    main()
