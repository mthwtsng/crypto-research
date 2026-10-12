#!/usr/bin/env python3
"""
Multi-Strategy Combined Portfolio Replay (S4 + S5 + S3 + S2 + optional S1).

Simulates the unified cash-funded portfolio on the 2,290 verified active curves
from the 10,080 dataset (August 18 - September 7, 2026):
1. S4: Upper ATH Breakout (4s rejection grace, 40s momentum time-stop: runner_max_hold=40).
2. S5: Pre-Migration Carryover (Dual-venue Raydium AMM pool exits: 50% open dump + 8% runner trail).
3. S3: Deadman Dip Bounce Tight Scalp (0s grace, hard -6% stop, 20s bounce deadline).
4. S2: 10.8 SOL Shelf (Freshness age<=240s, 10% slippage tolerance: min_tokens_bps=9000).
5. S1: Dev Dump Absorption (15s relief wick scalp, +20% target).

Execution:
- Shared 15.0 SOL cash bankroll, 0.50 SOL ticket (0.25 SOL cooldown probe).
- Headline Central85 placement scenario (plus Fast, Central80, Slow sensitivities).
- Concurrency matrix: Max 2, Max 5, Max 10, Uncapped.
- Breakers ON and Breakers OFF.
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
sys.path.insert(0, str(ROOT / "research/wallet_curve_entry_discovery_20261007"))
sys.path.insert(0, str(ROOT / "research/amm_multiday_20261006"))

import engine as E
import ledger as F
import rpc_pool as R
import curve_adapter as A
import amm_counterparty as M
import opportunity as O

OUT_DIR = R.OUT
E.O.C.rpc = R.rpc
E.O.C.P = R.OUT

def load_all_active_data():
    t0 = time.time()
    manifest = json.load(open(OUT_DIR / "ACTIVE_COINS_MANIFEST.json"))
    active_mints = {c["mint"] for c in manifest["coins"]}
    audits_dir = OUT_DIR / "prepare_audits"
    bound_dir = OUT_DIR / "bound_curve_tapes"
    exec_dir = OUT_DIR / "execution_tapes"
    
    signals = []
    tapes = {}
    
    for mint in sorted(active_mints):
        audit_file = audits_dir / (mint + ".json")
        if not audit_file.exists():
            continue
            
        d = json.load(open(audit_file))
        sigs = d.get("signals", [])
        if not sigs:
            continue
            
        tape_file = exec_dir / (mint + ".json.gz")
        if not tape_file.exists():
            tape_file = bound_dir / (mint + ".json.gz")
        if not tape_file.exists():
            continue
            
        t = json.load(gzip.open(tape_file, "rt"))
        gs = t["groups"]
        # Ensure venues are flagged
        if "venue" not in gs[0]:
            gs = [dict(g, venue="curve", trades=g["events"], time=g["block_time"])
                  for g in gs if g.get("source_status", "succeeded") == "succeeded"]
        gs.sort(key=lambda g: (g["slot"], g["index"]))
        t.update(groups=gs, inventory_key="token_account")
        tapes[mint] = t
        signals.extend(sigs)
        for g in gs:
            E.O.CLOCK[g["slot"]] = g["time"]
            
    print(f"Loaded {len(tapes)} active tapes and {len(signals)} signals in {time.time()-t0:.2f}s.")
    
    # Pre-cache block times
    needed_slots = sorted(list({s["slot"] + 1 for s in signals if s["mint"] in tapes}))
    for s in needed_slots:
        try:
            slot_id, b_time = E.O.block_at(s)
            E.O.CLOCK[slot_id] = b_time
        except Exception:
            pass
            
    return tapes, signals

def simulate_s5(tape, sig, sc, ticket=0.5, fee=1505000):
    gs = tape["groups"]
    sig_sig = sig["signal_signature"]
    i = next(idx for idx, g in enumerate(gs) if g["signature"] == sig_sig)
    j, slot = O.landing(gs, i, sig["slot"], O.branch(dict(sig, pool=sig.get("pool") or sig.get("curve")), sc))
    _, tm = O.block_at(slot)
    
    base = dict(sig, scenario=sc, endpoint="lower", ticket=ticket, fee=fee, legs=[],
                signal_position=(sig["slot"], gs[i]["index"], 0),
                entry_position=E.pos(gs, j, slot), entry_time=tm)
                
    ref = A.buy(gs[i]["state"], ticket)
    r = A.buy(gs[j]["state"], ticket)
    if not r:
        return dict(base, status="failed", net=-505000, mark=0, entry_bill=0,
                    close_position=base["entry_position"], close_time=tm, remaining=0)
                    
    st = A.moved(gs[j]["state"], *r)
    h = A.build.inventory(gs[:j+1])
    cf = dict(h)
    n = r[1]
    original = n
    bill = r[0] + A.fee(r[0], st["fee_bps"]) + A.fee(r[0], st["creator_fee_bps"])
    fees = fee
    realized = 0
    venue = "curve"
    clip = False
    peak = -1.0
    lastpos = base["entry_position"]
    lasttime = tm
    legs = []
    
    def quote(amount, cur_st, cur_venue):
        if cur_venue == "curve" and cur_st.get("rtokens_raw", 0) > 0:
            return A.sell(cur_st, amount)
        elif cur_venue == "amm":
            return M.A.sell(cur_st, amount)
        return None

    def proceeds(q, cur_venue):
        return q[0] if cur_venue == "curve" else q["total"]

    for k in range(j+1, len(gs)):
        if n <= 0:
            break
        g = gs[k]
        if g["venue"] == "curve":
            if venue != "curve":
                continue
            st, h, cf, ag, err = A.apply(st, g, h, cf)
            if err:
                continue
            if st["rsol_raw"] <= 60_000_000_000:
                q = quote(n, st, "curve")
                if q:
                    got = proceeds(q, "curve")
                    realized += got
                    fees += fee
                    lastpos = E.pos(gs, k, g["slot"])
                    lasttime = g["time"]
                    legs.append(dict(venue="curve", reason="carryover_invalidation", proceeds=got, fee=fee,
                                     tokens=n, position=lastpos, time=lasttime, trigger_slot=g["slot"], landing_slot=g["slot"]))
                    n = 0
                    break
        elif g["venue"] == "amm":
            if venue == "curve":
                z, hh, cc, err = E.opening_state(st, g, tape, h, cf)
                st = dict(g["state"]) if err else z
                venue = "amm"
            else:
                st, h, cf, err = M.advance(st, g, h, cf)
                if err:
                    continue
            q = quote(n, st, "amm")
            if not q:
                continue
            cur_val = (realized + proceeds(q, "amm") - bill - fees) / bill
            peak = max(peak, cur_val)
            if not clip:
                clip = True
                sell_n = original // 2
                q_sell = quote(sell_n, st, "amm")
                if q_sell:
                    got = proceeds(q_sell, "amm")
                    st = M.moved(st, q_sell, False, False)
                    realized += got
                    fees += fee
                    n -= sell_n
                    lastpos = E.pos(gs, k, g["slot"])
                    lasttime = g["time"]
                    legs.append(dict(venue="amm", reason="AMM_open_half", proceeds=got, fee=fee,
                                     tokens=sell_n, position=lastpos, time=lasttime, trigger_slot=g["slot"], landing_slot=g["slot"]))
            elif clip and 1 + cur_val <= (1 + peak) * 0.92:
                q_sell = quote(n, st, "amm")
                if q_sell:
                    got = proceeds(q_sell, "amm")
                    st = M.moved(st, q_sell, False, False)
                    realized += got
                    fees += fee
                    lastpos = E.pos(gs, k, g["slot"])
                    lasttime = g["time"]
                    legs.append(dict(venue="amm", reason="AMM_runner_trail", proceeds=got, fee=fee,
                                     tokens=n, position=lastpos, time=lasttime, trigger_slot=g["slot"], landing_slot=g["slot"]))
                    n = 0
                    break
                    
    status = "closed" if n == 0 else "unresolved"
    net = realized - bill - fees
    base.update(entry_bill=bill, entry_tokens=original, legs=legs, status=status, net=net, mark=0,
                remaining=n, close_position=lastpos, close_time=lasttime)
    return base

def simulate_trade(tape, sig, sc, ticket, fee):
    rule = sig["rule"]
    if rule == "s5_carryover":
        return simulate_s5(tape, sig, sc, ticket, fee)
        
    cfg = {"tailored_trail_basis": "percentage_points"}
    if rule == "s4_upper_ath":
        # S4: Upper ATH Breakout, 4s rejection grace, -8% stop, half profit target at +20%, 6% runner trail
        cfg.update(s4_remove_short_timeout=True, s4_rejection_grace=4, s4_stop=0.08)
    elif rule == "s3_deadman":
        # S3: Tight Scalp: 0s cascade grace, hard -6% stop, 20s bounce deadline, dynamic arm 0.35, 10pp trail
        cfg.update(s3_extended_hold=20, s3_grace=0, s3_relative_price_stop=0.06, s3_dynamic_arm=0.35, s3_dynamic_width=0.10)
    elif rule == "s2_survival_shelf":
        # S2: 10% slippage guard, dynamic exit target 0.30, 35s momentum hold
        cfg.update(s2_dynamic_exit=True, s2_target=0.30, min_tokens_bps=9000, runner_max_hold=35)
    elif rule == "s1_dev_absorption":
        # S1: 15s relief wick scalp, target 0.20
        cfg.update(s1_dynamic_exit=True, s1_trough_grace=0, s1_target=0.20, runner_max_hold=15)
        
    return E.simulate(tape, sig, sc, "lower", ticket, fee, cfg)

def run_all_simulations(tapes, signals, workers=4):
    scenarios = ["fast", "central80", "central85", "slow"]
    jobs = []
    
    for s in signals:
        mint = s["mint"]
        if mint not in tapes:
            continue
        # S2 freshness filter
        if s["rule"] == "s2_survival_shelf":
            if not (s.get("age_seconds", 0) <= 240 and s.get("outside_buyers", 0) <= 80):
                continue
        for sc in scenarios:
            for ticket in [0.5, 0.25]:
                jobs.append((s, sc, ticket, 1505000))
                
    print(f"[*] Simulating {len(jobs)} executions across {workers} worker threads...")
    t0 = time.time()
    
    def worker(j):
        sig, sc, ticket, fee = j
        return simulate_trade(tapes[sig["mint"]], sig, sc, ticket, fee)
        
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(worker, j): j for j in jobs}
        for fut in concurrent.futures.as_completed(futures):
            results.append(fut.result())
            
    print(f"[+] Replay complete in {time.time()-t0:.2f}s ({len(results)} trade results).")
    return results

def evaluate_portfolios(results):
    caps = [2, 5, 10, None]
    scenarios = ["fast", "central80", "central85", "slow"]
    
    portfolios = {
        "core_4strats": ["s2_survival_shelf", "s3_deadman", "s4_upper_ath", "s5_carryover"],
        "all_5strats": ["s1_dev_absorption", "s2_survival_shelf", "s3_deadman", "s4_upper_ath", "s5_carryover"],
    }
    
    matrix = {}
    for p_name, strat_list in portfolios.items():
        matrix[p_name] = {}
        for breaker_mode in [True, False]:
            b_key = "breakers_on" if breaker_mode else "breakers_off"
            matrix[p_name][b_key] = {}
            for cap in caps:
                c_key = f"max_{cap}" if cap is not None else "uncapped"
                matrix[p_name][b_key][c_key] = {}
                for sc in scenarios:
                    subset = [r for r in results if r["rule"] in strat_list and r["scenario"] == sc]
                    acct = F.funded(subset, breakers=breaker_mode, scope="portfolio", position_limit=cap)
                    
                    rule_breakdown = {}
                    for r_name in strat_list:
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
                        
                    matrix[p_name][b_key][c_key][sc] = {
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

def print_master_report(matrix, tape_count, signal_count):
    print("\n" + "=" * 105)
    print("      UNIFIED MULTI-STRATEGY COMBINED PORTFOLIO REPLAY REPORT")
    print(f"      Verified Active Curves: {tape_count} | Admitted Signals: {signal_count}")
    print("      Initial Capital: 15.0 SOL Cash | Ticket: 0.50 SOL (0.25 SOL probe) | Fees: 1,505,000 lamports")
    print("=" * 105)

    for p_name, p_title in [("core_4strats", "CORE 4-STRATEGY PORTFOLIO (S4 ATH + S5 AMM + S3 TIGHT STOP + S2 10% SLIP)"),
                            ("all_5strats", "FULL 5-STRATEGY PORTFOLIO (S1 WICK + S2 SHELF + S3 DEADMAN + S4 ATH + S5 AMM)")]:
        print("\n" + "#" * 105)
        print(f"  {p_title}")
        print("#" * 105)
        
        for b_mode in ["breakers_on", "breakers_off"]:
            b_label = "CIRCUIT BREAKERS ON" if b_mode == "breakers_on" else "CIRCUIT BREAKERS OFF"
            print(f"\n--- {b_label} (CENTRAL85 MANDATORY HEADLINE) ---")
            print(f" {'Cap':<12} {'Settled SOL':<15} {'Open Mark':<14} {'Combined Net':<16} {'Win Rate':<10} {'Profit Factor':<14} {'Attempts (C/F/U)'}")
            print(" " + "-" * 100)
            
            for cap in [2, 5, 10, None]:
                c_key = f"max_{cap}" if cap is not None else "uncapped"
                d = matrix[p_name][b_mode][c_key]["central85"]
                c_tag = f"Max {cap}" if cap is not None else "Uncapped"
                print(f" {c_tag:<12} {d['settled_net_sol']:>+9.4f} SOL   {d['open_marked_sol']:>+8.4f} SOL   {d['combined_sol']:>+10.4f} SOL "
                      f"{d['win_rate']*100:>5.1f}%     {d['profit_factor']:>6.3f}         "
                      f"{d['attempts']:>3} ({d['closed']}C/{d['failed']}F/{d['unresolved']}U)")

        # Strategy Attribution for Central85 Max 2 and Max 5
        for target_cap in ["max_2", "max_5", "uncapped"]:
            cap_label = target_cap.replace("_", " ").upper()
            print(f"\n--- STRATEGY ATTRIBUTION: {cap_label} (CENTRAL85, BREAKERS ON) ---")
            print(f" {'Strategy':<24} {'Settled SOL':<14} {'Open Mark':<14} {'Combined SOL':<14} {'Attempts':<10} {'Closed':<8} {'Win Rate'}")
            print(" " + "-" * 100)
            rules = matrix[p_name]["breakers_on"][target_cap]["central85"]["rules"]
            for r_name, rd in rules.items():
                print(f" {r_name:<24} {rd.get('settled_sol', 0.0):>+8.4f} SOL   {rd.get('open_mark_sol', 0.0):>+8.4f} SOL   {rd.get('combined_sol', 0.0):>+8.4f} SOL   "
                      f"{rd.get('attempts', 0):>6}     {rd.get('closed', 0):>6}   {rd.get('win_rate', 0.0)*100:>5.1f}%")

    # Execution Scenario Sensitivity for Core 4-Strats at Max 2
    print("\n" + "=" * 105)
    print("      EXECUTION SCENARIO SENSITIVITY: CORE 4-STRATS (MAX 2 POSITIONS, BREAKERS ON)")
    print("=" * 105)
    print(f" {'Scenario':<16} {'Settled SOL':<15} {'Open Mark':<14} {'Combined Net':<16} {'Win Rate':<10} {'Profit Factor':<14} {'Attempts (C/F/U)'}")
    print("-" * 105)
    for sc in ["fast", "central80", "central85", "slow"]:
        d = matrix["core_4strats"]["breakers_on"]["max_2"][sc]
        print(f" {sc:<16} {d['settled_net_sol']:>+9.4f} SOL   {d['open_marked_sol']:>+8.4f} SOL   {d['combined_sol']:>+10.4f} SOL "
              f"{d['win_rate']*100:>5.1f}%     {d['profit_factor']:>6.3f}         "
              f"{d['attempts']:>3} ({d['closed']}C/{d['failed']}F/{d['unresolved']}U)")
    print("=" * 105 + "\n")

def main():
    tapes, signals = load_all_active_data()
    results = run_all_simulations(tapes, signals, workers=4)
    matrix = evaluate_portfolios(results)
    print_master_report(matrix, len(tapes), len(signals))
    
    out_json = ROOT / "reports/COMBINED_PORTFOLIO_REPLAY_REPORT.json"
    with open(out_json, "w") as f:
        json.dump(matrix, f, indent=2)
    print(f"[✓] Report data successfully saved to {out_json}")

if __name__ == "__main__":
    main()
