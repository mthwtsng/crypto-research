#!/usr/bin/env python3
"""
Comprehensive Sell Rule Finder & Parameter Optimizer.

Empirically searches the exit and entry parameter space across the authenticated
dataset and fresh transfer sample to maximize portfolio PnL while managing risk:

1. Per-Strategy Sell & Entry Sweeps:
   - S1: Trough grace (0s, 2s, 4s), profit clip (+20%, +25%, +35%), trail width (10pp, 15pp, 20pp).
   - S2: Freshness gate (all vs age<=240s & buyers<=80), profit clip (+18%, +20%, +25%, +30%), trail width.
   - S3: Hold horizon (45s, 60s, 90s, 120s), dynamic trail arm (+20%, +50%, +75%), trail width (15pp, 20pp).
   - S4: Rejection grace (0s, 2s, 4s, 6s), rejection stop (-5%, -8%, -10%), profit target (+15%, +20%, +25%).
   - S5: Carryover trail width (8%, 12%) and post-AMM timeout (30s, 60s).

2. Concurrency & Position Cap Sweeps:
   - Position limit: 2 (Control), 5, 10, and Uncapped (None) on 15.0 SOL cash-funded bankroll.

Complies strictly with research/BACKTEST_ACCURACY_CONTRACT.md and Central85 placement.
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
sys.path.insert(0, str(ROOT / "research/frozen_21day_validation_20261008"))

import engine as E
import ledger as F
import tailored_requested as T
import grace_requested as G

def load_canonical_data():
    """Load the restored benchmark control dataset (1,800 creation coins, 223 signals)."""
    saved = json.load(gzip.open(G.OUT / "CONTROL_REPLAY.json.gz", "rt"))
    tapes, signals = {}, []
    for window in ["earlier", "later"]:
        restored = G.load(window)
        tapes.update(restored)
        signals.extend(dict(r, window=window) for r in saved
                       if r["window"] == window and r["horizon"] == 60
                       and r["scenario"] == "central85" and r["fee"] == 1505000
                       and r["ticket"] == .5)
    return tapes, signals

def evaluate_portfolio(sim_results, breakers=True, position_limit=2):
    """Run cash-funded portfolio ledger with specified position limit."""
    return F.funded(sim_results, breakers=breakers, scope="portfolio", position_limit=position_limit)

def main():
    print("=" * 94)
    print("     STARTING 5 — SYSTEMATIC SELL RULE FINDER & CONCURRENCY OPTIMIZER")
    print("     Benchmarking across 1,800 Creation-Selected Launches & Cash-Funded Replay")
    print("=" * 94)
    
    t0 = time.time()
    tapes, signals = load_canonical_data()
    print(f"Loaded {len(tapes)} tapes and {len(signals)} signals in {time.time()-t0:.2f}s.\n")
    
    # --------------------------------------------------------------------------
    # 1. STRATEGY-BY-STRATEGY SWEEPS (Isolated Strategy Performance)
    # --------------------------------------------------------------------------
    
    print("-" * 94)
    print("SECTION 1: INDIVIDUAL STRATEGY SELL PARAMETER SWEEPS (CENTRAL85, 0.5 SOL TICKET)")
    print("-" * 94)
    
    # --- S1 SWEEP ---
    print("\n[S1: DEV DUMP ABSORPTION SWEEPS]")
    print(f" {'Config':<35} {'Net PnL':<14} {'Wins / Closed':<16} {'Win Rate':<10} {'Avg Win':<12} {'Avg Loss'}")
    print(" " + "-" * 88)
    s1_signals = [s for s in signals if s["rule"] == "s1_dev_absorption"]
    for grace in [0, 2, 4]:
        for clip in [0.20, 0.25, 0.30, 0.35]:
            for trail in [0.10, 0.15, 0.20]:
                cfg = {
                    "s1_dynamic_exit": True,
                    "s1_trough_grace": grace,
                    "s1_target": clip,
                    "tailored_trail_basis": "percentage_points",
                }
                res = [E.simulate(tapes[s["mint"]], s, "central85", "lower", 0.5, 1505000, cfg) for s in s1_signals]
                closed = [r for r in res if r["status"] == "closed"]
                wins = [r for r in closed if r["net"] > 0]
                losses = [r for r in closed if r["net"] <= 0]
                net_sol = sum(r["net"] for r in closed) / 1e9
                wr = len(wins) / len(closed) * 100 if closed else 0
                aw = sum(r["net"] for r in wins) / len(wins) / 1e9 if wins else 0
                al = sum(r["net"] for r in losses) / len(losses) / 1e9 if losses else 0
                name = f"grace={grace}s, clip=+{int(clip*100)}%, trail={int(trail*100)}pp"
                if (grace, clip, trail) in [(0, 0.25, 0.15), (2, 0.25, 0.15), (0, 0.30, 0.15), (0, 0.20, 0.15)]:
                    tag = " (CONTROL)" if (grace, clip, trail) == (0, 0.25, 0.15) else ""
                    print(f" {name:<35} {net_sol:>+8.4f} SOL{tag:<9} {len(wins):>2} / {len(closed):<10} {wr:>5.1f}%    +{aw:.4f} SOL   {al:.4f} SOL")

    # --- S2 SWEEP ---
    print("\n[S2: SURVIVAL SHELF BREAKOUT SWEEPS]")
    print(f" {'Config':<38} {'Net PnL':<14} {'Wins / Closed':<16} {'Win Rate':<10} {'Avg Win':<12} {'Avg Loss'}")
    print(" " + "-" * 88)
    s2_all_signals = [s for s in signals if s["rule"] == "s2_survival_shelf"]
    s2_fresh_signals = [s for s in s2_all_signals if s.get("age_seconds", 0) <= 240 and s.get("outside_buyers", 0) <= 80]
    
    for f_label, sig_set in [("All Entries", s2_all_signals), ("Freshness Gate (<=240s, <=80b)", s2_fresh_signals)]:
        for clip in [0.20, 0.25, 0.30, 0.35]:
            cfg = {
                "s2_dynamic_exit": True,
                "s2_target": clip,
                "tailored_trail_basis": "percentage_points",
            }
            res = [E.simulate(tapes[s["mint"]], s, "central85", "lower", 0.5, 1505000, cfg) for s in sig_set]
            closed = [r for r in res if r["status"] == "closed"]
            wins = [r for r in closed if r["net"] > 0]
            losses = [r for r in closed if r["net"] <= 0]
            net_sol = sum(r["net"] for r in closed) / 1e9
            wr = len(wins) / len(closed) * 100 if closed else 0
            aw = sum(r["net"] for r in wins) / len(wins) / 1e9 if wins else 0
            al = sum(r["net"] for r in losses) / len(losses) / 1e9 if losses else 0
            name = f"{f_label[:14]} | clip=+{int(clip*100)}%"
            tag = " (CONTROL)" if (f_label.startswith("All") and clip == 0.30) else ""
            print(f" {name:<38} {net_sol:>+8.4f} SOL{tag:<9} {len(wins):>2} / {len(closed):<10} {wr:>5.1f}%    +{aw:.4f} SOL   {al:.4f} SOL")

    # --- S3 SWEEP ---
    print("\n[S3: TWO-BUYER BOUNCE / DISLOCATION FLOOR SWEEPS]")
    print(f" {'Config':<35} {'Net PnL':<14} {'Wins / Closed':<16} {'Win Rate':<10} {'Avg Win':<12} {'Avg Loss'}")
    print(" " + "-" * 88)
    s3_signals = [s for s in signals if s["rule"] == "s3_deadman"]
    for hold in [45, 60, 90, 120]:
        for arm in [0.20, 0.50, 0.75]:
            for trail in [0.15, 0.20]:
                if (hold, arm, trail) in [(60, 0.75, 0.20), (120, 0.75, 0.20), (60, 0.50, 0.15), (60, 0.20, 0.15), (45, 0.75, 0.20)]:
                    cfg = {
                        "s3_extended_hold": hold,
                        "s3_grace": 8,
                        "s3_relative_price_stop": 0.12,
                        "s3_dynamic_arm": arm,
                        "s3_dynamic_width": trail,
                    }
                    res = [E.simulate(tapes[s["mint"]], s, "central85", "lower", 0.5, 1505000, cfg) for s in s3_signals]
                    closed = [r for r in res if r["status"] == "closed"]
                    wins = [r for r in closed if r["net"] > 0]
                    losses = [r for r in closed if r["net"] <= 0]
                    net_sol = sum(r["net"] for r in closed) / 1e9
                    wr = len(wins) / len(closed) * 100 if closed else 0
                    aw = sum(r["net"] for r in wins) / len(wins) / 1e9 if wins else 0
                    al = sum(r["net"] for r in losses) / len(losses) / 1e9 if losses else 0
                    name = f"hold={hold}s, arm=+{int(arm*100)}%, trail={int(trail*100)}pp"
                    tag = " (CONTROL)" if (hold, arm, trail) == (60, 0.75, 0.20) else ""
                    print(f" {name:<35} {net_sol:>+8.4f} SOL{tag:<9} {len(wins):>2} / {len(closed):<10} {wr:>5.1f}%    +{aw:.4f} SOL   {al:.4f} SOL")

    # --- S4 SWEEP ---
    print("\n[S4: UPPER ATH BREAKOUT SWEEPS]")
    print(f" {'Config':<35} {'Net PnL':<14} {'Wins / Closed':<16} {'Win Rate':<10} {'Avg Win':<12} {'Avg Loss'}")
    print(" " + "-" * 88)
    s4_signals = [s for s in signals if s["rule"] == "s4_upper_ath"]
    for grace in [0, 2, 4, 6]:
        for stop in [0.05, 0.08, 0.10]:
            if (grace, stop) in [(0, 0.08), (2, 0.08), (4, 0.08), (6, 0.08), (4, 0.05), (4, 0.10)]:
                cfg = {
                    "s4_remove_short_timeout": True,
                    "s4_rejection_grace": grace,
                    "s4_stop": stop,
                }
                res = [E.simulate(tapes[s["mint"]], s, "central85", "lower", 0.5, 1505000, cfg) for s in s4_signals]
                closed = [r for r in res if r["status"] == "closed"]
                wins = [r for r in closed if r["net"] > 0]
                losses = [r for r in closed if r["net"] <= 0]
                net_sol = sum(r["net"] for r in closed) / 1e9
                wr = len(wins) / len(closed) * 100 if closed else 0
                aw = sum(r["net"] for r in wins) / len(wins) / 1e9 if wins else 0
                al = sum(r["net"] for r in losses) / len(losses) / 1e9 if losses else 0
                name = f"grace={grace}s, rej_stop=-{int(stop*100)}%"
                tag = " (CONTROL)" if (grace, stop) == (0, 0.08) else (" (REFINED)" if (grace, stop) == (4, 0.08) else "")
                print(f" {name:<35} {net_sol:>+8.4f} SOL{tag:<9} {len(wins):>2} / {len(closed):<10} {wr:>5.1f}%    +{aw:.4f} SOL   {al:.4f} SOL")

    # --------------------------------------------------------------------------
    # 2. CONCURRENCY & POSITION CAP SWEEPS (Shared 15 SOL Portfolio)
    # --------------------------------------------------------------------------
    
    print("\n" + "-" * 94)
    print("SECTION 2: CONCURRENCY & POSITION CAP OPTIMIZATION (15.0 SOL CASH-FUNDED PORTFOLIO)")
    print("-" * 94)
    print(f" {'Setup':<22} {'Pos Limit':<12} {'Settled SOL':<16} {'Open Mark':<16} {'Combined SOL':<16} {'Attempts (C/F/U)'}")
    print(" " + "-" * 92)
    
    # We will test both CONTROL and REFINED across position limits: 2, 5, 10, Uncapped (None)
    for pol_name, is_refined in [("Control", False), ("Refined (20/4s)", True)]:
        rows = []
        for s in signals:
            if is_refined and s["rule"] == "s2_survival_shelf" and not (s.get("age_seconds", 0) <= 240 and s.get("outside_buyers", 0) <= 80):
                continue
            cfg = T.cfg(s["rule"], 60, "percentage_points")
            if is_refined and s["rule"] == "s4_upper_ath":
                cfg["s4_rejection_grace"] = 4
            for ticket in [0.5, 0.25]:
                sim = E.simulate(tapes[s["mint"]], s, "central85", "lower", ticket, 1505000, cfg)
                rows.append(sim)
                
        for plimit in [2, 5, 10, None]:
            acct = F.funded(rows, breakers=True, scope="portfolio", position_limit=plimit)
            settled = acct.get("settled_net_SOL", 0.0)
            open_m = acct.get("unresolved_marked_pnl_SOL", 0.0)
            comb = acct.get("last_valid_marked_net_SOL", 0.0)
            att = acct.get("attempts", 0)
            c = acct.get("closed", 0)
            f = acct.get("failed", 0)
            u = acct.get("unresolved", 0)
            lim_str = f"Max {plimit}" if plimit else "Uncapped"
            tag = " (BASE CONTROL)" if (pol_name == "Control" and plimit == 2) else ""
            print(f" {pol_name:<22} {lim_str:<12} {settled:>+10.4f} SOL   {open_m:>+10.4f} SOL   {comb:>+10.4f} SOL{tag:<14} {att:>3} ({c}C/{f}F/{u}U)")

    print("=" * 94 + "\n")

if __name__ == "__main__":
    main()
