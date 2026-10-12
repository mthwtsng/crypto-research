"""Systematic improvement test for S1, S2, and S3 strategies.

Evaluates specific microstructural hypotheses against verified active curves:
1. S2 (10.8 SOL Shelf):
   - Hypothesis A: Freshness Gate (age <= 240s) removes stale zombie coins.
   - Hypothesis B: 35s momentum time-stop scratches stalled coins before bleed-out.
   - Hypothesis C: Take-profit at +20% / +25% vs +30%.

2. S1 (Dev Dump Absorption):
   - Hypothesis A: Fast relief wick scalp (12s - 15s hold) vs wide runner.
   - Hypothesis B: Take-profit at +20% (clipping 100% or 60%) vs +30%.
   - Hypothesis C: Scratch after 10s if price hasn't bounced.

3. S3 (Deadman Dip Bounce):
   - Hypothesis A: Remove 8s grace period (instant cut at -6% to -8%).
   - Hypothesis B: Strict 20s bounce deadline.
   - Hypothesis C: Confirmation requirement.
"""
import json
import gzip
import pathlib
import sys
import collections

ROOT = pathlib.Path.cwd()
sys.path.insert(0, str(ROOT / "research/frozen_21day_validation_20261008"))
sys.path.insert(0, str(ROOT / "research/core_plan_audit_20261007"))
sys.path.insert(0, str(ROOT / "research/core_gap_refinement_20261007"))
sys.path.insert(0, str(ROOT / "research/wallet_curve_entry_discovery_20261007"))
sys.path.insert(0, str(ROOT / "research/amm_multiday_20261006"))

import rpc_pool as R
import engine as E
import tailored_requested as T
import curve_adapter as A
import opportunity as O

OUT = R.OUT

def load_tapes_and_signals():
    sigs_dir = OUT / "signals_by_mint"
    tapes_dir = OUT / "bound_curve_tapes"
    
    tapes = {}
    signals = []
    for f in sigs_dir.glob("*.json"):
        sigs = json.load(open(f))
        if not sigs:
            continue
        tape_file = tapes_dir / (f.stem + ".json.gz")
        if not tape_file.exists():
            continue
        t = json.load(gzip.open(tape_file, "rt"))
        gs = [dict(g, venue="curve", trades=g["events"], time=g["block_time"]) 
              for g in t["groups"] if g.get("source_status", "succeeded") == "succeeded"]
        gs.sort(key=lambda g: (g["slot"], g["index"]))
        t.update(groups=gs, inventory_key="token_account")
        tapes[f.stem] = t
        signals.extend(sigs)
        for g in gs:
            E.O.CLOCK[g["slot"]] = g["time"]
            
    # Cache block times
    needed_slots = sorted(list({s["slot"] + 1 for s in signals if s["mint"] in tapes}))
    for s in needed_slots:
        try:
            slot_id, b_time = E.O.block_at(s)
            E.O.CLOCK[slot_id] = b_time
        except Exception:
            pass
            
    return tapes, signals

def simulate_signal(tape, sig, cfg, sc="central85", ticket=0.5, fee=1505000):
    return E.simulate(tape, sig, sc, "lower", ticket, fee, cfg)

def evaluate_strategy(name, cases, tapes, sigs_subset):
    print(f"\n=======================================================")
    print(f"   EVALUATING IMPROVEMENTS FOR: {name.upper()}")
    print(f"=======================================================")
    print(f"{'Configuration':<35} | {'Trades':<6} | {'Settled SOL':<12} | {'Open Mark':<10} | {'Combined':<11} | {'Win Rate':<8} | {'PF':<6}")
    print("-" * 105)
    
    for label, filter_fn, cfg in cases:
        valid_sigs = [s for s in sigs_subset if filter_fn(s)]
        if not valid_sigs:
            print(f"{label:<35} | 0 trades")
            continue
            
        settled_total = 0.0
        marked_total = 0.0
        wins = 0
        losses = 0
        closed_wins_sol = 0.0
        closed_losses_sol = 0.0
        
        for s in valid_sigs:
            mint = s["mint"]
            t = tapes[mint]
            res = simulate_signal(t, s, cfg)
            
            net_sol = res["net"] / 1e9
            mark_sol = res["mark"] / 1e9 if res["status"] == "unresolved" else 0.0
            
            if res["status"] != "unresolved":
                settled_total += net_sol
                if net_sol > 0:
                    wins += 1
                    closed_wins_sol += net_sol
                else:
                    losses += 1
                    closed_losses_sol += abs(net_sol)
            else:
                marked_total += (net_sol + mark_sol)
                
        trades = wins + losses
        wr = (wins / trades * 100) if trades else 0.0
        pf = (closed_wins_sol / closed_losses_sol) if closed_losses_sol > 0 else (99.0 if closed_wins_sol > 0 else 0.0)
        comb = settled_total + marked_total
        
        print(f"{label:<35} | {trades:>6} | {settled_total:>+10.4f} SOL | {marked_total:>+8.4f} SOL | {comb:>+9.4f} SOL | {wr:>6.1f}% | {pf:>6.2f}")

def main():
    print("Loading prepared bound curves and signals...", flush=True)
    tapes, signals = load_tapes_and_signals()
    print(f"Loaded {len(tapes)} tapes and {len(signals)} signals.")
    
    s1_sigs = [s for s in signals if s["rule"] == "s1_dev_absorption"]
    s2_sigs = [s for s in signals if s["rule"] == "s2_survival_shelf"]
    s3_sigs = [s for s in signals if s["rule"] == "s3_deadman"]
    
    # ---------------------------------------------------------
    # 1. S2 IMPROVEMENT SWEEP
    # ---------------------------------------------------------
    s2_cases = [
        ("Control (No age filter, no time-stop)", 
         lambda s: True, 
         {"tailored_trail_basis": "percentage_points", "s2_dynamic_exit": True, "s2_target": 0.30}),
        
        ("Refined (Age <= 240s only)", 
         lambda s: s["age_seconds"] <= 240, 
         {"tailored_trail_basis": "percentage_points", "s2_dynamic_exit": True, "s2_target": 0.30}),
        
        ("Fresh + 35s Momentum Deadline", 
         lambda s: s["age_seconds"] <= 240, 
         {"tailored_trail_basis": "percentage_points", "s2_dynamic_exit": True, "s2_target": 0.30, "runner_max_hold": 35}),

        ("Fresh + 25s Momentum Deadline", 
         lambda s: s["age_seconds"] <= 240, 
         {"tailored_trail_basis": "percentage_points", "s2_dynamic_exit": True, "s2_target": 0.25, "runner_max_hold": 25}),

        ("Fresh (<=180s) + Buyers >= 35 + 30s Deadline", 
         lambda s: s["age_seconds"] <= 180 and s["outside_buyers"] >= 35, 
         {"tailored_trail_basis": "percentage_points", "s2_dynamic_exit": True, "s2_target": 0.25, "runner_max_hold": 30}),
        
        ("Stale Only (Age > 240s) [Failure Test]", 
         lambda s: s["age_seconds"] > 240, 
         {"tailored_trail_basis": "percentage_points", "s2_dynamic_exit": True, "s2_target": 0.30}),
    ]
    evaluate_strategy("s2_survival_shelf", s2_cases, tapes, s2_sigs)

    # ---------------------------------------------------------
    # 2. S1 IMPROVEMENT SWEEP
    # ---------------------------------------------------------
    s1_cases = [
        ("Control (Dynamic exit, target 25%)", 
         lambda s: True, 
         {"tailored_trail_basis": "percentage_points", "s1_dynamic_exit": True, "s1_target": 0.25}),
        
        ("Target 20% + 15s Relief Wick", 
         lambda s: True, 
         {"tailored_trail_basis": "percentage_points", "s1_dynamic_exit": True, "s1_target": 0.20, "runner_max_hold": 15}),

        ("Target 15% + 12s Fast Scalp", 
         lambda s: True, 
         {"tailored_trail_basis": "percentage_points", "s1_dynamic_exit": True, "s1_target": 0.15, "runner_max_hold": 12}),

        ("Reserves 1.5 - 4.0 SOL + 15s Hold", 
         lambda s: 1.5 <= s["reserve"] <= 4.0, 
         {"tailored_trail_basis": "percentage_points", "s1_dynamic_exit": True, "s1_target": 0.20, "runner_max_hold": 15}),

        ("Deep Dip (Reserves < 1.5 SOL) + 10s Hold", 
         lambda s: s["reserve"] < 1.5, 
         {"tailored_trail_basis": "percentage_points", "s1_dynamic_exit": True, "s1_target": 0.20, "runner_max_hold": 10}),
    ]
    evaluate_strategy("s1_dev_absorption", s1_cases, tapes, s1_sigs)

    # ---------------------------------------------------------
    # 3. S3 IMPROVEMENT SWEEP
    # ---------------------------------------------------------
    s3_cases = [
        ("Control (8s grace, 12% stop, 60s hold)", 
         lambda s: True, 
         {"tailored_trail_basis": "percentage_points", "s3_extended_hold": 60, "s3_grace": 8, "s3_relative_price_stop": 0.12, "s3_dynamic_arm": 0.75, "s3_dynamic_width": 0.20}),

        ("Tight Stop (0s grace, 6% stop, 20s hold)", 
         lambda s: True, 
         {"tailored_trail_basis": "percentage_points", "s3_extended_hold": 20, "s3_grace": 0, "s3_relative_price_stop": 0.06, "s3_dynamic_arm": 0.35, "s3_dynamic_width": 0.10}),

        ("Tight Stop (2s grace, 8% stop, 25s hold)", 
         lambda s: True, 
         {"tailored_trail_basis": "percentage_points", "s3_extended_hold": 25, "s3_grace": 2, "s3_relative_price_stop": 0.08, "s3_dynamic_arm": 0.40, "s3_dynamic_width": 0.12}),

        ("Upper Curve Dips (12-18 SOL) + Tight 20s", 
         lambda s: s["reserve"] >= 12.0, 
         {"tailored_trail_basis": "percentage_points", "s3_extended_hold": 20, "s3_grace": 0, "s3_relative_price_stop": 0.06, "s3_dynamic_arm": 0.30, "s3_dynamic_width": 0.10}),
    ]
    evaluate_strategy("s3_deadman", s3_cases, tapes, s3_sigs)

if __name__ == "__main__":
    main()
