#!/usr/bin/env python3
"""
Partial Frozen 21-Day Validation Test Runner.

Executes offline signal preparation and replay simulation on the already collected
raw curves in research/frozen_21day_validation_20261008/ (August 18 – September 7).

Benchmarks both:
1. Control Portfolio: Restored benchmark configuration.
2. Refined Portfolio: S4 4s grace + S2 freshness filter (age <= 240s, buyers <= 80).

Evaluates 15.0 SOL cash-funded bankroll, Central85 headline placement scenario,
and full fee accounting per research/BACKTEST_ACCURACY_CONTRACT.md.
"""

import concurrent.futures
import datetime
import gzip
import json
import os
import pathlib
import sys
import time
from collections import Counter, defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research/frozen_21day_validation_20261008"))
sys.path.insert(0, str(ROOT / "research/core_plan_audit_20261007"))
sys.path.insert(0, str(ROOT / "research/core_gap_refinement_20261007"))

import prepare_validation as B
import rpc_pool as R
import engine as E
import ledger as F
import tailored_requested as T

# Protect RPC quota by skipping RPC queries during intermediate offline check
B.H.one = lambda source: dict(status="skipped_offline_to_protect_rpc")

OUT_DIR = R.OUT

def prepare_all_available_curves(max_workers=16):
    raw_files = sorted(list((OUT_DIR / "raw_curves").glob("*.json.gz")))
    total_files = len(raw_files)
    print(f"[*] Found {total_files} raw curve files collected in validation directory.")
    
    prepared_audits = []
    errors = []
    
    t0 = time.time()
    print(f"[*] Preparing curve tapes and detecting signals (offline mode) across {max_workers} threads...")
    
    def process_file(f):
        try:
            return (True, B.build(f))
        except Exception as e:
            return (False, {"mint": f.name.split(".")[0], "error": str(e)})

    done_cnt = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers) as ex:
        futures = {ex.submit(process_file, f): f for f in raw_files}
        for fut in concurrent.futures.as_completed(futures):
            ok, res = fut.result()
            done_cnt += 1
            if ok:
                prepared_audits.append(res)
            else:
                errors.append(res)
            if done_cnt % 500 == 0 or done_cnt == total_files:
                print(f"    Progress: {done_cnt}/{total_files} processed ({len(prepared_audits)} prepared, {len(errors)} skipped) [{time.time()-t0:.1f}s]", flush=True)
                
    elapsed = time.time() - t0
    print(f"[+] Preparation completed in {elapsed:.1f}s:")
    print(f"    Successfully prepared: {len(prepared_audits)} / {total_files} ({len(prepared_audits)/total_files*100:.1f}%)")
    print(f"    Skipped (gaps/reverts): {len(errors)}")
    
    # Collect all signals
    all_signals = []
    for audit in prepared_audits:
        sigs = audit.get("signals", [])
        all_signals.extend(sigs)
        
    print(f"[+] Total candidate signals detected: {len(all_signals)}")
    dist = Counter(s["rule"] for s in all_signals)
    for rule in ["s1_dev_absorption", "s2_survival_shelf", "s3_deadman", "s4_upper_ath", "s5_carryover"]:
        print(f"    • {rule:<25}: {dist.get(rule, 0):>4} signals")
        
    return prepared_audits, all_signals, errors


def load_prepared_tapes_for_signals(signals):
    signal_mints = {s["mint"] for s in signals}
    tapes = {}
    print(f"[*] Loading bound tapes for {len(signal_mints)} unique signal mints...")
    for mint in signal_mints:
        tape_path = OUT_DIR / "bound_curve_tapes" / f"{mint}.json.gz"
        if tape_path.is_file():
            t = json.load(gzip.open(tape_path, "rt"))
            gs = [dict(g, venue="curve", trades=g["events"], time=g["block_time"]) for g in t["groups"] if g.get("source_status", "succeeded") == "succeeded"]
            gs.sort(key=lambda g: (g["slot"], g["index"]))
            t.update(groups=gs, inventory_key="token_account")
            tapes[mint] = t
            for g in gs:
                E.O.CLOCK[g["slot"]] = g["time"]
    print(f"[+] Loaded {len(tapes)} tapes into memory.")
    return tapes


def is_primary_eligible(s):
    """Refined filter for S2: age <= 240s and outside buyers <= 80."""
    if s["rule"] == "s2_survival_shelf":
        return s.get("age_seconds", 0) <= 240 and s.get("outside_buyers", 0) <= 80
    return True


def run_portfolio_replay(tapes, signals, max_workers=16):
    policies = ["control", "refined"]
    scenarios = ["fast", "central80", "central85", "slow"]
    
    jobs = []
    for policy in policies:
        for s in signals:
            if s["mint"] not in tapes:
                continue
            if policy == "refined" and not is_primary_eligible(s):
                continue
            
            # Strategy config
            cfg = T.cfg(s["rule"], 60, "percentage_points")
            if policy == "refined":
                if s["rule"] == "s4_upper_ath":
                    cfg["s4_rejection_grace"] = 4
                elif s["rule"] == "s2_survival_shelf":
                    cfg["s2_dynamic_exit"] = True
                    cfg["s2_target"] = 0.30
            
            for sc in scenarios:
                for fee in [1505000]: # Standard fee
                    for ticket in [0.5, 0.25]:
                        jobs.append((policy, s, sc, fee, ticket, cfg))
            # Also Central85 with high fee (2,916,000 lamports)
            for ticket in [0.5, 0.25]:
                jobs.append((policy, s, "central85", 2916000, ticket, cfg))

    print(f"[*] Running {len(jobs)} simulation jobs across {max_workers} worker threads...")
    t0 = time.time()
    
    def simulate_job(j):
        policy, s, sc, fee, ticket, cfg = j
        sim = E.simulate(tapes[s["mint"]], s, sc, "lower", ticket, fee, cfg)
        return dict(sim, policy=policy)

    results = []
    sim_errors = []
    with concurrent.futures.ThreadPoolExecutor(max_workers) as ex:
        futures = {ex.submit(simulate_job, j): j for j in jobs}
        for fut in concurrent.futures.as_completed(futures):
            try:
                results.append(fut.result())
            except Exception as e:
                sim_errors.append(str(e))
                
    print(f"[+] Replay simulation completed in {time.time()-t0:.2f}s ({len(results)} finished, {len(sim_errors)} errors).")
    
    # Portfolio Accounting
    accounts = {}
    for policy in policies:
        accounts[policy] = {}
        for sc in scenarios:
            rr = [r for r in results if r["policy"] == policy and r["scenario"] == sc and r["fee"] == 1505000]
            if rr:
                # 15.0 SOL cash-funded portfolio with breakers=True
                acct = F.funded(rr, True, "portfolio", position_limit=None)
                accounts[policy][sc] = acct
                
        # High fee Central85
        rr_hf = [r for r in results if r["policy"] == policy and r["scenario"] == "central85" and r["fee"] == 2916000]
        if rr_hf:
            acct_hf = F.funded(rr_hf, True, "portfolio", position_limit=None)
            accounts[policy]["central85_high_fee"] = acct_hf
            
    return results, accounts


def print_contract_report(accounts, results, total_sampled, prepared_count, signals_count):
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    print("\n" + "=" * 94)
    print("      PARTIAL FROZEN VALIDATION REPORT (AUGUST 18 – SEPTEMBER 7 HISTORICAL SAMPLE)")
    print(f"      Evaluated: {prepared_count} / {total_sampled} Available Curves | Signals: {signals_count}")
    print(f"      Bankroll: 15.0 SOL Cash-Funded | Ticket: 0.50 SOL | Standard Fee: 1,505,000 lamports")
    print(f"      Timestamp: {now_iso}")
    print("=" * 94)
    
    print("\n" + "-" * 94)
    print(f"{'POLICY':<18} {'SCENARIO':<14} {'SETTLED SOL':<16} {'OPEN MARK SOL':<16} {'COMBINED SOL':<18} {'ATTEMPTS'}")
    print("-" * 94)
    
    for pol in ["control", "refined"]:
        p_name = "CONTROL" if pol == "control" else "REFINED"
        for sc in ["fast", "central80", "central85", "slow", "central85_high_fee"]:
            acct = accounts[pol].get(sc)
            if not acct:
                continue
            settled = acct.get("settled_net_SOL", 0.0)
            open_m = acct.get("unresolved_marked_pnl_SOL", 0.0)
            comb = acct.get("last_valid_marked_net_SOL", 0.0)
            attempts = acct.get("attempts", 0)
            closed = acct.get("closed", 0)
            failed = acct.get("failed", 0)
            unres = acct.get("unresolved", 0)
            
            tag = " <-- HEADLINE" if (pol == "refined" and sc == "central85") else ""
            print(f"{p_name:<18} {sc:<14} {settled:>+10.4f} SOL   {open_m:>+10.4f} SOL   {comb:>+12.4f} SOL{tag}   {attempts:>3} ({closed}C/{failed}F/{unres}U)")

    # Detailed Headline Central85 Breakdown
    print("\n" + "=" * 94)
    print("HEADLINE CENTRAL85 COMPARISON (CONTROL vs REFINED):")
    print("=" * 94)
    
    for pol in ["control", "refined"]:
        p_name = "CONTROL" if pol == "control" else "REFINED"
        acct = accounts[pol].get("central85")
        if not acct:
            continue
            
        wr = (acct.get("win_rate", 0.0) or 0.0) * 100.0
        pf = acct.get("profit_factor") or 1.0
        print(f"\n[{p_name} CENTRAL85 PORTFOLIO]:")
        print(f" • Settled PnL:        {acct.get('settled_net_SOL', 0.0):>+10.4f} SOL")
        print(f" • Open Marked PnL:    {acct.get('unresolved_marked_pnl_SOL', 0.0):>+10.4f} SOL")
        print(f" • Combined Marked:    {acct.get('last_valid_marked_net_SOL', 0.0):>+10.4f} SOL")
        print(f" • Trade Lifecycle:    {acct.get('attempts', 0)} attempts | {acct.get('closed', 0)} closed | {acct.get('failed', 0)} failed | {acct.get('unresolved', 0)} unresolved")
        print(f" • Win Rate:           {wr:>5.1f}%  | Profit Factor: {pf:.3f}")
        print(f" • Max Drawdown:       {acct.get('max_settled_drawdown_SOL', 0.0):>10.4f} SOL")
        
        # Strategy Attribution
        print("\n  STRATEGY ATTRIBUTION (CENTRAL85):")
        print(f"  {'Rule':<24} {'Attempts':<10} {'Closed':<8} {'Settled SOL':<16} {'Open Mark':<14} {'Combined Net':<16}")
        print("  " + "-" * 88)
        
        pol_results = [r for r in results if r["policy"] == pol and r["scenario"] == "central85" and r["fee"] == 1505000 and r["ticket"] == 0.5]
        by_rule = defaultdict(list)
        for r in pol_results:
            by_rule[r["rule"]].append(r)
            
        for rule in ["s1_dev_absorption", "s2_survival_shelf", "s3_deadman", "s4_upper_ath", "s5_carryover"]:
            rows = by_rule.get(rule, [])
            if not rows:
                continue
            r_att = len(rows)
            r_closed = sum(1 for x in rows if x.get("status") == "closed")
            r_settled = sum(x.get("net", 0.0) / 1e9 for x in rows if x.get("status") == "closed")
            r_open = sum(x.get("mark", 0.0) / 1e9 for x in rows if x.get("status") != "closed")
            r_comb = r_settled + r_open
            print(f"  {rule:<24} {r_att:>6}     {r_closed:>6}   {r_settled:>+10.4f} SOL   {r_open:>+10.4f} SOL   {r_comb:>+12.4f} SOL")

    print("\n" + "=" * 94)
    print("STANDARD RESULT CARD (ACCURACY CONTRACT COMPLIANT):")
    ref_c85 = accounts["refined"].get("central85", {})
    fast_c = accounts["refined"].get("fast", {}).get("last_valid_marked_net_SOL", 0.0)
    c80_c = accounts["refined"].get("central80", {}).get("last_valid_marked_net_SOL", 0.0)
    c85_c = ref_c85.get("last_valid_marked_net_SOL", 0.0)
    slow_c = accounts["refined"].get("slow", {}).get("last_valid_marked_net_SOL", 0.0)
    
    print(f"Data: Aug 18–Sep 7; {total_sampled} collected launches ({prepared_count} prepared); historical transfer")
    print(f"Looks: 2 configurations x 4 horizons/scenarios")
    print(f"Refined fast / central80 / central85 / slow:")
    print(f"{fast_c:>+8.3f} / {c80_c:>+8.3f} / {c85_c:>+8.3f} / {slow_c:>+8.3f} SOL")
    print(f"Attempts / closed / failed / unresolved: {ref_c85.get('attempts', 0)} / {ref_c85.get('closed', 0)} / {ref_c85.get('failed', 0)} / {ref_c85.get('unresolved', 0)}")
    print(f"Verdict: undetermined, retrospective partial sample ({prepared_count}/{total_sampled} coins)")
    print("=" * 94 + "\n")

    # Export report summary to reports/partial_frozen_run/
    report_dir = ROOT / "reports" / "partial_frozen_run"
    report_dir.mkdir(parents=True, exist_ok=True)
    with open(report_dir / "SUMMARY.json", "w") as f:
        json.dump({
            "timestamp": now_iso,
            "total_sampled": total_sampled,
            "prepared_count": prepared_count,
            "signals_count": signals_count,
            "control": accounts.get("control"),
            "refined": accounts.get("refined"),
        }, f, indent=2, default=str)
    print(f"[✓] Saved summary snapshot to {report_dir / 'SUMMARY.json'}")


def main():
    audits, signals, errors = prepare_all_available_curves(max_workers=16)
    if not signals:
        print("[!] No signals found in prepared curves. Exiting.")
        return
        
    tapes = load_prepared_tapes_for_signals(signals)
    results, accounts = run_portfolio_replay(tapes, signals, max_workers=16)
    
    raw_files = list((OUT_DIR / "raw_curves").glob("*.json.gz"))
    print_contract_report(accounts, results, len(raw_files), len(audits), len(signals))

if __name__ == "__main__":
    main()
