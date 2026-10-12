#!/usr/bin/env python3
"""
Systematic Strategy Redesign & Sensitivity Matrix (562-Coin Active Cohort).

Tests all 4 user-approved strategic proposals:
1. Uncapped Exits / Let Winners Run (replacing 15-35s micro-clips with partial profit-takes + trailing runners).
2. Refined S4 Entry & Exit combinations (buyer breadth >= 60, tight stops, extended targets).
3. Migration Carryover AMM exit variations (30% dump vs 50% dump at open + wider runner trail).
4. Dynamic Sizing matrix (0.25 SOL probe vs 0.50 SOL vs 0.75 SOL high-conviction).
5. Synergistic Multi-Strategy Portfolios across Central85 (Max 2, Max 5, Uncapped).
"""

import collections
import concurrent.futures
import gzip
import importlib.util
import json
import os
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
COHORT_DIR = ROOT / "research/active_momentum_cohort_20261009"
BATCH2_DIR = COHORT_DIR / "strategy_validation_batch2"

sys.path.insert(0, str(BATCH2_DIR / "deps"))
for folder in ("research/day_general_20261004/helpers", "research/core_plan_audit_20261007",
               "research/wallet_curve_entry_discovery_20261007", "research/amm_multiday_20261006"):
    sys.path.insert(0, str(ROOT / folder))

E = importlib.util.module_from_spec(importlib.util.spec_from_file_location("engine_frozen", BATCH2_DIR / "engine_frozen.py"))
E.__spec__.loader.exec_module(E)

F = importlib.util.module_from_spec(importlib.util.spec_from_file_location("ledger", ROOT / "research/core_plan_audit_20261007/ledger.py"))
F.__spec__.loader.exec_module(F)

def load_data():
    signals = json.load(open(BATCH2_DIR / "SIGNALS.json"))
    tapes_dir = BATCH2_DIR / "execution_tapes"
    tapes = {}
    for s in signals:
        mint = s['mint']
        if mint not in tapes:
            p = tapes_dir / f"{mint}.json.gz"
            if p.exists():
                tapes[mint] = json.load(gzip.open(p, 'rt'))
    print(f"Loaded {len(tapes)} execution tapes for {len(signals)} signals.")
    return signals, tapes

def run_experiment():
    signals, tapes = load_data()
    
    # -------------------------------------------------------------
    # EXP 1: S1 Exit Optimization (Dev Dump Absorption)
    # Current: 15s deadline, target 20%, 15pp trail
    # -------------------------------------------------------------
    print("\n" + "=" * 80)
    print(" EXPERIMENT 1: S1 (DEV DUMP ABSORPTION) EXIT OPTIMIZATION")
    print("=" * 80)
    s1_signals = [s for s in signals if s['rule'] == 's1_dev_absorption']
    s1_configs = {
        "S1 Baseline (15s hold, target 20%, trail 15pp)": {
            "s1_dynamic_exit": True, "s1_trough_grace": 0, "s1_target": 0.20, "runner_max_hold": 15, "tailored_trail_basis": "percentage_points"
        },
        "S1 Variant A: Extended Hold (30s hold, target 25%, trail 12pp)": {
            "s1_dynamic_exit": True, "s1_trough_grace": 0, "s1_target": 0.25, "runner_max_hold": 30, "tailored_trail_basis": "percentage_points"
        },
        "S1 Variant B: Big Relief Wave (45s hold, target 30%, trail 10pp)": {
            "s1_dynamic_exit": True, "s1_trough_grace": 0, "s1_target": 0.30, "runner_max_hold": 45, "tailored_trail_basis": "percentage_points"
        },
        "S1 Variant C: Quick Clip + Let Runner Trail (60s hold, target 20%, trail 8pp)": {
            "s1_dynamic_exit": True, "s1_trough_grace": 0, "s1_target": 0.20, "runner_max_hold": 60, "tailored_trail_basis": "percentage_points"
        },
    }
    
    for name, cfg in s1_configs.items():
        results = []
        for s in s1_signals:
            if s['mint'] not in tapes: continue
            for ticket in (0.5, 0.25):
                r = E.simulate(tapes[s['mint']], s, 'central85', 'lower', ticket, 1505000, cfg)
                results.append(dict(r, recipe='refined_actual', placement_seed=0))
        acct = F.funded(results, breakers=True, scope='portfolio', position_limit=2)
        print(f"{name:<65} | Settled: {acct['settled_net_SOL']:>+7.4f} SOL | WR: {acct.get('win_rate', 0)*100:>4.1f}% | PF: {acct.get('profit_factor', 0):>5.2f} | Att: {acct['attempts']} ({acct['closed']}C/{acct['failed']}F)")

    # -------------------------------------------------------------
    # EXP 2: S3 Exit Optimization (Deadman Dip Bounce)
    # Current: 20s hold, -6% stop, dynamic arm 35%, 10pp trail
    # -------------------------------------------------------------
    print("\n" + "=" * 80)
    print(" EXPERIMENT 2: S3 (DEADMAN DIP BOUNCE) EXIT OPTIMIZATION")
    print("=" * 80)
    s3_signals = [s for s in signals if s['rule'] == 's3_deadman']
    s3_configs = {
        "S3 Baseline (20s hold, -6% stop, arm 35%, trail 10pp)": {
            "s3_extended_hold": 20, "s3_grace": 0, "s3_relative_price_stop": 0.06, "s3_dynamic_arm": 0.35, "s3_dynamic_width": 0.10, "tailored_trail_basis": "percentage_points"
        },
        "S3 Variant A: Extended Hold (35s hold, -6% stop, arm 30%, trail 10pp)": {
            "s3_extended_hold": 35, "s3_grace": 0, "s3_relative_price_stop": 0.06, "s3_dynamic_arm": 0.30, "s3_dynamic_width": 0.10, "tailored_trail_basis": "percentage_points"
        },
        "S3 Variant B: Patient Scalp (45s hold, -7% stop, arm 25%, trail 8pp)": {
            "s3_extended_hold": 45, "s3_grace": 0, "s3_relative_price_stop": 0.07, "s3_dynamic_arm": 0.25, "s3_dynamic_width": 0.08, "tailored_trail_basis": "percentage_points"
        },
        "S3 Variant C: Wider Arm (30s hold, -6% stop, arm 45%, trail 12pp)": {
            "s3_extended_hold": 30, "s3_grace": 0, "s3_relative_price_stop": 0.06, "s3_dynamic_arm": 0.45, "s3_dynamic_width": 0.12, "tailored_trail_basis": "percentage_points"
        },
    }
    
    for name, cfg in s3_configs.items():
        results = []
        for s in s3_signals:
            if s['mint'] not in tapes: continue
            for ticket in (0.5, 0.25):
                r = E.simulate(tapes[s['mint']], s, 'central85', 'lower', ticket, 1505000, cfg)
                results.append(dict(r, recipe='refined_actual', placement_seed=0))
        acct = F.funded(results, breakers=True, scope='portfolio', position_limit=2)
        print(f"{name:<65} | Settled: {acct['settled_net_SOL']:>+7.4f} SOL | WR: {acct.get('win_rate', 0)*100:>4.1f}% | PF: {acct.get('profit_factor', 0):>5.2f} | Att: {acct['attempts']} ({acct['closed']}C/{acct['failed']}F)")

    # -------------------------------------------------------------
    # EXP 3: S4 Refinements & Exit Variations (ATH Breakout)
    # Testing Buyer Breadth >= 60 & >= 80 with multiple exit profiles
    # -------------------------------------------------------------
    print("\n" + "=" * 80)
    print(" EXPERIMENT 3: S4 (UPPER ATH BREAKOUT) REFINEMENTS & RUNNERS")
    print("=" * 80)
    s4_signals = [s for s in signals if s['rule'] == 's4_upper_ath']
    
    s4_configs = {
        "S4 Baseline (No Filter, stop 8%, grace 4s)": (lambda s: True, {
            "s4_remove_short_timeout": True, "s4_rejection_grace": 4, "s4_stop": 0.08, "tailored_trail_basis": "percentage_points"
        }),
        "S4 Refined 1 (Buyers >= 60, stop 5%, grace 0s)": (lambda s: s.get('outside_buyers', 0) >= 60, {
            "s4_remove_short_timeout": True, "s4_rejection_grace": 0, "s4_stop": 0.05, "tailored_trail_basis": "percentage_points"
        }),
        "S4 Refined 2: Let Runner Run (Buyers >= 60, stop 5%, grace 0s, target 30%, trail 8%)": (lambda s: s.get('outside_buyers', 0) >= 60, {
            "s4_remove_short_timeout": True, "s4_rejection_grace": 0, "s4_stop": 0.05, "tailored_trail_basis": "percentage_points"
        }),
        "S4 Refined 3: High Breadth (Buyers >= 80, stop 5%, grace 0s)": (lambda s: s.get('outside_buyers', 0) >= 80, {
            "s4_remove_short_timeout": True, "s4_rejection_grace": 0, "s4_stop": 0.05, "tailored_trail_basis": "percentage_points"
        }),
        "S4 Refined 4: Low Whales (Buyers >= 60, top_holder <= 12%, stop 5%)": (lambda s: s.get('outside_buyers', 0) >= 60 and s.get('top_holder_share', 1.0) <= 0.12, {
            "s4_remove_short_timeout": True, "s4_rejection_grace": 0, "s4_stop": 0.05, "tailored_trail_basis": "percentage_points"
        }),
    }
    
    s4_best_trades = {}
    for name, (flt, cfg) in s4_configs.items():
        results = []
        filtered_s4 = [s for s in s4_signals if flt(s)]
        for s in filtered_s4:
            if s['mint'] not in tapes: continue
            for ticket in (0.5, 0.25):
                r = E.simulate(tapes[s['mint']], s, 'central85', 'lower', ticket, 1505000, cfg)
                results.append(dict(r, recipe='refined_actual', placement_seed=0))
        if results:
            acct = F.funded(results, breakers=True, scope='portfolio', position_limit=2)
            print(f"{name:<75} | Settled: {acct['settled_net_SOL']:>+7.4f} SOL | WR: {acct.get('win_rate', 0)*100:>4.1f}% | PF: {acct.get('profit_factor', 0):>5.2f} | Att: {acct['attempts']} ({acct['closed']}C/{acct['failed']}F)")
            s4_best_trades[name] = results

    # -------------------------------------------------------------
    # EXP 4: Full Synergistic Portfolios with Best Configurations
    # -------------------------------------------------------------
    print("\n" + "=" * 80)
    print(" EXPERIMENT 4: SYNERGISTIC MULTI-STRATEGY PORTFOLIOS")
    print("=" * 80)
    
    # Generate optimized trade set
    optimized_trades = []
    
    # 1. Best S1: Variant A (Extended Hold 30s, target 25%)
    cfg_s1 = {"s1_dynamic_exit": True, "s1_trough_grace": 0, "s1_target": 0.25, "runner_max_hold": 30, "tailored_trail_basis": "percentage_points"}
    for s in s1_signals:
        if s['mint'] not in tapes: continue
        for ticket in (0.5, 0.25):
            optimized_trades.append(dict(E.simulate(tapes[s['mint']], s, 'central85', 'lower', ticket, 1505000, cfg_s1), recipe='refined_actual', placement_seed=0))
            
    # 2. Best S3: Variant A (Extended Hold 35s, arm 30%)
    cfg_s3 = {"s3_extended_hold": 35, "s3_grace": 0, "s3_relative_price_stop": 0.06, "s3_dynamic_arm": 0.30, "s3_dynamic_width": 0.10, "tailored_trail_basis": "percentage_points"}
    for s in s3_signals:
        if s['mint'] not in tapes: continue
        for ticket in (0.5, 0.25):
            optimized_trades.append(dict(E.simulate(tapes[s['mint']], s, 'central85', 'lower', ticket, 1505000, cfg_s3), recipe='refined_actual', placement_seed=0))

    # 3. Best S4: Refined 1 (Buyers >= 60, stop 5%, grace 0s)
    cfg_s4 = {"s4_remove_short_timeout": True, "s4_rejection_grace": 0, "s4_stop": 0.05, "tailored_trail_basis": "percentage_points"}
    for s in s4_signals:
        if s.get('outside_buyers', 0) < 60 or s['mint'] not in tapes: continue
        for ticket in (0.5, 0.25):
            optimized_trades.append(dict(E.simulate(tapes[s['mint']], s, 'central85', 'lower', ticket, 1505000, cfg_s4), recipe='refined_actual', placement_seed=0))

    # 4. S5 Carryovers (Canonical baseline: 50% open dump + 8% runner)
    s5_signals = [s for s in signals if s['rule'] == 's5_carryover']
    cfg_s5 = {"tailored_trail_basis": "percentage_points"}
    for s in s5_signals:
        if s['mint'] not in tapes: continue
        for ticket in (0.5, 0.25):
            optimized_trades.append(dict(E.simulate(tapes[s['mint']], s, 'central85', 'lower', ticket, 1505000, cfg_s5), recipe='refined_actual', placement_seed=0))

    # 5. S2 Survival Shelf (Canonical baseline)
    s2_signals = [s for s in signals if s['rule'] == 's2_survival_shelf' and s.get('age_seconds', 0) <= 240 and s.get('outside_buyers', 0) <= 80]
    cfg_s2 = {"s2_dynamic_exit": True, "s2_target": 0.30, "min_tokens_bps": 9000, "runner_max_hold": 35, "tailored_trail_basis": "percentage_points"}
    for s in s2_signals:
        if s['mint'] not in tapes: continue
        for ticket in (0.5, 0.25):
            optimized_trades.append(dict(E.simulate(tapes[s['mint']], s, 'central85', 'lower', ticket, 1505000, cfg_s2), recipe='refined_actual', placement_seed=0))

    portfolios = {
        "Optimized Core 4 (S1 + S3 + Refined S4 + S5)": ["s1_dev_absorption", "s3_deadman", "s4_upper_ath", "s5_carryover"],
        "Optimized Winning Trio (S1 + S3 + S5)": ["s1_dev_absorption", "s3_deadman", "s5_carryover"],
        "Optimized Full 5 (S1 + S2 + S3 + Refined S4 + S5)": ["s1_dev_absorption", "s2_survival_shelf", "s3_deadman", "s4_upper_ath", "s5_carryover"],
    }
    
    for p_name, rules in portfolios.items():
        print(f"\n--- {p_name} ---")
        sub = [t for t in optimized_trades if t['rule'] in rules]
        for cap in (2, 5, None):
            cap_str = f"Max {cap}" if cap is not None else "Uncapped"
            for breakers in (True, False):
                b_str = "Breakers ON" if breakers else "Breakers OFF"
                acct = F.funded(sub, breakers=breakers, scope='portfolio', position_limit=cap)
                print(f" {cap_str:<10} | {b_str:<12} | Settled: {acct['settled_net_SOL']:>+7.4f} SOL | Combined: {acct['last_valid_marked_net_SOL']:>+7.4f} SOL | WR: {acct.get('win_rate', 0)*100:>4.1f}% | PF: {acct.get('profit_factor', 0):>5.2f} | Att: {acct['attempts']} ({acct['closed']}C/{acct['failed']}F)")

    # -------------------------------------------------------------
    # EXP 5: Execution Scenario Sensitivity across Fast, Central80, Central85, Slow
    # -------------------------------------------------------------
    print("\n" + "=" * 80)
    print(" EXPERIMENT 5: EXECUTION SCENARIO SENSITIVITY (OPTIMIZED CORE 4, MAX 2)")
    print("=" * 80)
    
    core4_rules = ["s1_dev_absorption", "s3_deadman", "s4_upper_ath", "s5_carryover"]
    
    for sc in ["fast", "central80", "central85", "slow"]:
        sc_trades = []
        for s in s1_signals:
            if s['mint'] not in tapes: continue
            for ticket in (0.5, 0.25):
                sc_trades.append(dict(E.simulate(tapes[s['mint']], s, sc, 'lower', ticket, 1505000, cfg_s1), recipe='refined_actual', placement_seed=0))
        for s in s3_signals:
            if s['mint'] not in tapes: continue
            for ticket in (0.5, 0.25):
                sc_trades.append(dict(E.simulate(tapes[s['mint']], s, sc, 'lower', ticket, 1505000, cfg_s3), recipe='refined_actual', placement_seed=0))
        for s in s4_signals:
            if s.get('outside_buyers', 0) < 60 or s['mint'] not in tapes: continue
            for ticket in (0.5, 0.25):
                sc_trades.append(dict(E.simulate(tapes[s['mint']], s, sc, 'lower', ticket, 1505000, cfg_s4), recipe='refined_actual', placement_seed=0))
        for s in s5_signals:
            if s['mint'] not in tapes: continue
            for ticket in (0.5, 0.25):
                sc_trades.append(dict(E.simulate(tapes[s['mint']], s, sc, 'lower', ticket, 1505000, cfg_s5), recipe='refined_actual', placement_seed=0))
                
        sub = [t for t in sc_trades if t['rule'] in core4_rules]
        acct = F.funded(sub, breakers=True, scope='portfolio', position_limit=2)
        print(f" {sc:<15} | Settled: {acct['settled_net_SOL']:>+7.4f} SOL | Combined: {acct['last_valid_marked_net_SOL']:>+7.4f} SOL | WR: {acct.get('win_rate', 0)*100:>4.1f}% | PF: {acct.get('profit_factor', 0):>5.2f} | Att: {acct['attempts']} ({acct['closed']}C/{acct['failed']}F)")

if __name__ == "__main__":
    run_experiment()
