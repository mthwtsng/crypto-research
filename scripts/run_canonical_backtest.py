#!/usr/bin/env python3
"""Canonical Master Backtest Runner & Source of Truth Engine.

Complies strictly with:
- research/BACKTEST_ACCURACY_CONTRACT.md
- research/MASTER_STRATEGY_REGISTRY.md
- research/CODEX_CALIBRATION.md / research/GEMINI_CALIBRATION.md

Runs the restored benchmark control (experimental refinements: refined_registry_requested.py).
Runs the approved replay engine (research/core_plan_audit_20261007/engine.py)
across the authenticated 1,800 creation-selected coins (October 3-6) using
the compressed tapes datasets.
"""

import argparse
import collections
import concurrent.futures
import datetime
import gzip
import json
import os
import pathlib
import pickle
import sys
import time

# Ensure repository root is on sys.path
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research/core_plan_audit_20261007"))
sys.path.insert(0, str(ROOT / "research/core_gap_refinement_20261007"))

import engine as E

FAILED_FEE = 505000 # lamports
RENT = 2039280 # lamports
L = 10**9

def get_strategy_config(rule, args):
    """Map canonical rules to simulation engine configs."""
    cfg = {
        "tailored_trail_basis": args.trail_basis,
    }
    if rule == "s1_dev_absorption":
        cfg.update(
            s1_dynamic_exit=True,
            s1_trough_grace=args.s1_grace,
            **({"runner_max_hold": args.runner_max_hold} if args.runner_max_hold else {}),
        )
    elif rule == "s2_survival_shelf":
        cfg.update(
            s2_dynamic_exit=True,
            **({"runner_max_hold": args.runner_max_hold} if args.runner_max_hold else {}),
        )
    elif rule == "s3_deadman":
        cfg.update(
            s3_extended_hold=args.s3_hold,
            s3_grace=8,
            s3_relative_price_stop=args.s3_stop,
            s3_dynamic_arm=args.s3_arm,
            s3_dynamic_width=args.s3_trail,
        )
    elif rule == "s4_upper_ath":
        cfg.update(
            s4_remove_short_timeout=True,
            s4_rejection_grace=args.s4_grace,
            **({"runner_max_hold": args.runner_max_hold} if args.runner_max_hold else {}),
        )
    elif rule == "s5_carryover":
        pass
    return cfg

def load_signals_and_tapes(rules_filter=None):
    """Use the restored, instruction-bound control inputs; fail on missing data."""
    import grace_requested as G
    saved = json.load(gzip.open(G.OUT / "CONTROL_REPLAY.json.gz", "rt"))
    tapes, signals = {}, []
    for window in ["earlier", "later"]:
        restored = G.load(window)
        tapes.update(restored)
        signals.extend(dict(r, window=window) for r in saved
                       if r["window"] == window and r["horizon"] == 60
                       and r["scenario"] == "central85" and r["fee"] == 1505000
                       and r["ticket"] == .5
                       and (not rules_filter or r["rule"] in rules_filter))
    return tapes, signals

def run_simulation(args):
    rules_filter = args.rules.split(",") if args.rules != "all" else None
    scenarios = args.scenarios.split(",")
    
    print(f"Loading tapes and signals across 1,800 creation-selected launches...")
    t0 = time.time()
    tapes, signals = load_signals_and_tapes(rules_filter)
    print(f"Loaded {len(tapes)} unique tapes and {len(signals)} matching signals in {time.time()-t0:.2f}s.")
    
    jobs = []
    for sig in signals:
        cfg = get_strategy_config(sig["rule"], args)
        for sc in scenarios:
            for ticket in [.5, .25]:
                jobs.append((tapes[sig["mint"]], sig, sc, "lower", ticket, args.fee, cfg))
            
    print(f"Running {len(jobs)} simulation jobs across {args.workers} worker threads...")
    t1 = time.time()
    results = []
    errors = []
    
    def worker(job):
        t, sig, sc, endpoint, ticket, fee, cfg = job
        res = E.simulate(t, sig, sc, endpoint, ticket, fee, cfg)
        return res
        
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_map = {executor.submit(worker, j): j for j in jobs}
        for fut in concurrent.futures.as_completed(future_map):
            try:
                results.append(fut.result())
            except Exception as e:
                errors.append({"job": str(future_map[fut][1]["mint"]), "error": repr(e)})
                
    sim_time = time.time() - t1
    print(f"Completed {len(results)} simulations in {sim_time:.2f}s ({len(errors)} errors).")
    
    return results, errors

def analyze_portfolio(results, args):
    """Chronological shared 15 SOL ledger, with documented breakers/probes."""
    import ledger as F
    summary = {}
    for sc in args.scenarios.split(","):
        traces = [r for r in results if r["scenario"] == sc]
        funded = F.funded(traces, True, "portfolio", position_limit=None)
        rules = {}
        for rule in F.RULES:
            admitted = [r for r in funded["admitted"] if r["rule"] == rule]
            settled = sum(r["net_SOL"] for r in admitted if r["status"] != "unresolved")
            marked = sum(r["net_SOL"] + r["mark_SOL"] for r in admitted if r["status"] == "unresolved")
            closed = [r for r in admitted if r["status"] == "closed"]
            reasons = collections.Counter(l["reason"] for r in admitted for l in r["legs"])
            rules[rule] = dict(attempts=len(admitted), closed=len(closed),
                failed=sum(r["status"] == "failed" for r in admitted),
                unresolved=sum(r["status"] == "unresolved" for r in admitted),
                settled_sol=settled, open_marked_sol=marked, combined_sol=settled+marked,
                win_rate=sum(r["net_SOL"]>0 for r in closed)/len(closed) if closed else 0,
                reasons=dict(reasons))
        summary[sc] = dict(funded, settled_sol=funded["settled_net_SOL"],
            open_marked_sol=funded["unresolved_marked_pnl_SOL"],
            combined_sol=funded["last_valid_marked_net_SOL"],
            win_rate=funded["win_rate"] or 0, profit_factor=funded["profit_factor"] or 0,
            max_drawdown_sol=funded["max_settled_drawdown_SOL"], rules=rules)
    return summary

def generate_report(summary, args, out_dir):
    """Format and save the canonical report card."""
    out_dir.mkdir(parents=True, exist_ok=True)
    
    fast = summary.get("fast", {})
    c80 = summary.get("central80", {})
    c85 = summary.get("central85", {})
    slow = summary.get("slow", {})
    
    card = f"""================================================================================
RESTORED CONTROL CASH-FUNDED SUMMARY (see refined_registry_cycle for full checks/card)
Timestamp: {datetime.datetime.now(datetime.timezone.utc).isoformat()}
Bankroll: {args.bankroll} SOL | Ticket: {args.ticket} SOL | Fee: {args.fee} lamports
Strategy Scope: {args.rules}
S1 Trough Grace: {args.s1_grace}s | S4 Rejection Grace: {args.s4_grace}s | S3 Hold: {args.s3_hold}s
--------------------------------------------------------------------------------
SCENARIOS COMBINED MARKED PnL (SOL):
  Fast:      {fast.get('combined_sol', float('nan')):+8.4f} SOL
  Central80: {c80.get('combined_sol', float('nan')):+8.4f} SOL
  Central85: {c85.get('combined_sol', 0.0):+8.4f} SOL  <-- HEADLINE ESTIMATE
  Slow:      {slow.get('combined_sol', float('nan')):+8.4f} SOL
--------------------------------------------------------------------------------
HEADLINE CENTRAL85 BREAKDOWN:
  Settled PnL:     {c85.get('settled_sol', 0.0):+8.4f} SOL
  Open Marked PnL: {c85.get('open_marked_sol', 0.0):+8.4f} SOL
  Combined PnL:    {c85.get('combined_sol', 0.0):+8.4f} SOL
  Attempts/Closed/Failed/Unresolved: {c85.get('attempts', 0)} / {c85.get('closed', 0)} / {c85.get('failed', 0)} / {c85.get('unresolved', 0)}
  Profit Factor:   {c85.get('profit_factor', 0.0):.3f}
  Win Rate:        {c85.get('win_rate', 0.0)*100:.1f}%
  Max Drawdown:    {c85.get('max_drawdown_sol', 0.0):.4f} SOL
--------------------------------------------------------------------------------
PER-STRATEGY CONTRIBUTIONS (CENTRAL85):
"""
    for r_name, r_data in c85.get("rules", {}).items():
        card += f"  [{r_name}]:\n"
        card += f"    Attempts: {r_data['attempts']} (Closed: {r_data['closed']}, Failed: {r_data['failed']}, Open: {r_data['unresolved']})\n"
        card += f"    Settled: {r_data['settled_sol']:+7.4f} SOL | Open Mark: {r_data['open_marked_sol']:+7.4f} SOL | Combined: {r_data['combined_sol']:+7.4f} SOL\n"
        card += f"    Win Rate: {r_data['win_rate']*100:.1f}%\n"
        card += f"    Exit Reasons: {json.dumps(r_data['reasons'])}\n"

    card += "================================================================================\n"
    print(card)
    
    # Save files
    (out_dir / "RESULT_CARD.txt").write_text(card)
    (out_dir / "SUMMARY.json").write_text(json.dumps(summary, indent=2))
    print(f"Results saved to {out_dir}/RESULT_CARD.txt and {out_dir}/SUMMARY.json")

def main():
    parser = argparse.ArgumentParser(description="Canonical Master Strategy Backtest Runner")
    parser.add_argument("--rules", default="all", help="Comma-separated strategy rules (s1_dev_absorption,s2_survival_shelf,s3_deadman,s4_upper_ath,s5_carryover) or 'all'")
    parser.add_argument("--scenarios", default="fast,central80,central85,slow", help="Comma-separated placement scenarios")
    parser.add_argument("--ticket", type=float, default=0.50, help="Ticket size in SOL (default 0.50)")
    parser.add_argument("--bankroll", type=float, default=15.0, help="Total cash bankroll in SOL (default 15.0)")
    parser.add_argument("--fee", type=int, default=1505000, help="Priority + network fee per transaction in lamports (default 1505000)")
    parser.add_argument("--trail-basis", default="percentage_points", choices=["percentage_points", "relative"], help="Trail basis (default: percentage_points)")
    
    # Grace and exit parameter toggles
    parser.add_argument("--s1-grace", type=int, default=0, help="S1 trough breathing grace in seconds (default 0)")
    parser.add_argument("--s4-grace", type=int, default=0, help="S4 breakout rejection breathing grace in seconds (default 0)")
    parser.add_argument("--s3-hold", type=int, default=60, help="S3 max hold in seconds (default 60)")
    parser.add_argument("--s3-arm", type=float, default=0.75, help="S3 trail arm threshold (default 0.75)")
    parser.add_argument("--s3-trail", type=float, default=0.20, help="S3 giveback trail width (default 0.20)")
    parser.add_argument("--s3-stop", type=float, default=0.12, help="S3 fill-relative stop (default 0.12)")
    parser.add_argument("--runner-max-hold", type=int, default=None, help="Optional declared runner deadline; omitted keeps the benchmark control")
    
    parser.add_argument("--workers", type=int, default=4, help="Thread pool worker count (default 4)")
    parser.add_argument("--output-dir", default="reports/latest_backtest", help="Directory to save report card")
    
    args = parser.parse_args()
    if args.bankroll != 15 or args.ticket != .5:
        parser.error("This approved ledger is calibrated to 15 SOL / 0.50 SOL plus 0.25 probes")
    if "central85" not in args.scenarios.split(","):
        parser.error("Include central85; unrun scenarios must not appear as measured results")
    results, errors = run_simulation(args)
    if errors:
        raise RuntimeError(errors)
    summary = analyze_portfolio(results, args)
    generate_report(summary, args, ROOT / args.output_dir)

if __name__ == "__main__":
    main()
