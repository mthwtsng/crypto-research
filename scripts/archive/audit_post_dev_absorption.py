#!/usr/bin/env python3
"""Comprehensive Stress, Latency, & Walk-Forward Audit for Post-Dev Absorption.

Per Section 14 of EDGE_RESEARCH_GUIDE.md.
Reproduces all results in research/DISCOVERY_POST_DEV_ABSORPTION_EDGE.md.
"""
import gzip
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "research" / "data" / "deployer_bursts" / "dataset" / "markets.jsonl.gz"

SPAM_WALLETS = {
    "49fAsUF3Nk8qbfpSrQND2sULKXanemwibYLGk5Jpn9bY",
    "D9gQ6RhKEpnobPBUdWY5bPQt2p3zGk3iVz6ChpUi2ArA",
    "8NJ7Ujpji8uMF2675mqaTSEm2DCbfJA7fiRKtiaqkaLN",
    "K6Eh9fwKkrhVNq6SpRtJn7F4Myi3HUst5QP8x5BKHnR",
    "s9uu4shkYUQUmnWN2jkwgA2Nbg2Rmv7vUprtjy71xgP",
    "6Xi3uUvwuQgKqx9Uq61HERUT3sWhVhr36HcNnpoatqH5",
    "CXnf4Tt7qFz3KZNwn3Yve5MKaRyxGoAy2eDX3QT8e99m",
}

LAMPORTS = 1_000_000_000
FEE_BPS = 100
PRIORITY_FEE_SOL = 0.002

def ceil_fee(amount: int, bps: int) -> int:
    return (amount * bps + 9999) // 10000

def simulate_buy(vsol: int, vtokens: int, ticket_sol: float) -> tuple[int, int, int]:
    spend_lamports = round(ticket_sol * LAMPORTS)
    fee = ceil_fee(spend_lamports, FEE_BPS)
    net_sol = spend_lamports - fee
    if net_sol <= 0 or vsol <= 0 or vtokens <= 0:
        return 0, vsol, vtokens
    k = vsol * vtokens
    new_vsol = vsol + net_sol
    new_vtokens = (k + new_vsol - 1) // new_vsol
    tokens_bought = vtokens - new_vtokens
    return tokens_bought, new_vsol, new_vtokens

def simulate_sell(vsol: int, vtokens: int, tokens_to_sell: int) -> tuple[float, int, int]:
    if tokens_to_sell <= 0 or vsol <= 0 or vtokens <= 0:
        return 0.0, vsol, vtokens
    k = vsol * vtokens
    new_vtokens = vtokens + tokens_to_sell
    new_vsol = (k + new_vtokens - 1) // new_vtokens
    sol_gross = vsol - new_vsol
    fee = ceil_fee(sol_gross, FEE_BPS)
    sol_net = max(0, sol_gross - fee)
    return sol_net / LAMPORTS, new_vsol, new_vtokens

def evaluate_cohort(
    cohort_name: str,
    target_creators: set[str] | None,
    exclude_creators: set[str] | None,
    date_filter: tuple[str, str] | None,
    latency_events_delay: int = 1,
    ticket_sol: float = 0.5,
    hold_seconds: float = 4.0,
    min_outside_sol: float = 3.0,
    min_buyers: int = 2,
):
    trades = []
    
    with gzip.open(DATA_FILE, "rt") as f:
        for line in f:
            m = json.loads(line)
            dep = m.get("data", {}).get("deployment", {})
            creator = dep.get("creator") or dep.get("user")
            if not creator:
                continue
            
            if target_creators is not None and creator not in target_creators:
                continue
            if exclude_creators is not None and creator in exclude_creators:
                continue
                
            date_str = dep.get("date", "")
            if date_filter is not None:
                if not (date_filter[0] <= date_str <= date_filter[1]):
                    continue
            
            events = m.get("data", {}).get("events", [])
            if len(events) < 6:
                continue
            
            t0 = events[0]["time"]
            has_dev_sold = False
            outside_buyers = set()
            outside_buy_sol = 0.0
            
            signal_idx = None
            tokens_held = 0
            entry_time = None
            
            for idx, ev in enumerate(events):
                t_rel = ev["time"] - t0
                is_dev = (ev["user"] == creator)
                
                if not ev.get("buy") and is_dev:
                    has_dev_sold = True
                
                if ev.get("buy") and not is_dev:
                    outside_buyers.add(ev["user"])
                    outside_buy_sol += ev.get("sol", ev.get("sol_raw", 0)/LAMPORTS)
                
                if has_dev_sold and outside_buy_sol >= min_outside_sol and len(outside_buyers) >= min_buyers and t_rel <= 10.0:
                    signal_idx = idx
                    break
            
            if signal_idx is None:
                continue
                
            actual_entry_idx = min(signal_idx + latency_events_delay, len(events) - 1)
            ev_entry = events[actual_entry_idx]
            entry_time = ev_entry["time"] - t0
            
            tokens, _, _ = simulate_buy(ev_entry["vsol_raw"], ev_entry["vtokens_raw"], ticket_sol)
            if tokens <= 0:
                continue
            tokens_held = tokens
            
            exit_idx = len(events) - 1
            for idx in range(actual_entry_idx + 1, len(events)):
                ev = events[idx]
                t_rel = ev["time"] - t0
                if (t_rel - entry_time) >= hold_seconds:
                    exit_idx = idx
                    break
            
            ev_exit = events[exit_idx]
            exit_time = ev_exit["time"] - t0
            proceeds_sol, _, _ = simulate_sell(ev_exit["vsol_raw"], ev_exit["vtokens_raw"], tokens_held)
            
            net_pnl = proceeds_sol - ticket_sol - (PRIORITY_FEE_SOL * 2)
            trades.append({
                "creator": creator,
                "mint": dep.get("mint"),
                "date": date_str,
                "entry_time": entry_time,
                "exit_time": exit_time,
                "net_pnl": net_pnl,
                "ticket_sol": ticket_sol,
            })
            
    if not trades:
        print(f"[{cohort_name}] Trades: 0")
        return
        
    net_pnl_total = sum(t["net_pnl"] for t in trades)
    wins = [t for t in trades if t["net_pnl"] > 0]
    losses = [t for t in trades if t["net_pnl"] <= 0]
    win_rate = (len(wins) / len(trades)) * 100
    
    gross_win = sum(t["net_pnl"] for t in wins)
    gross_loss = abs(sum(t["net_pnl"] for t in losses))
    pf = (gross_win / gross_loss) if gross_loss > 0 else 999.0
    
    cum, peak, max_dd = 0.0, 0.0, 0.0
    for t in trades:
        cum += t["net_pnl"]
        peak = max(peak, cum)
        max_dd = max(max_dd, peak - cum)
        
    sorted_trades = sorted(trades, key=lambda x: x["net_pnl"], reverse=True)
    top3 = sum(t["net_pnl"] for t in sorted_trades[:3])
    pnl_no_top3 = net_pnl_total - top3
    
    print(f"[{cohort_name:42s}] N={len(trades):3d} | WR={win_rate:5.1f}% | Net={net_pnl_total:+7.3f} SOL | PF={pf:5.2f} | MaxDD={max_dd:5.3f} | ExTop3={pnl_no_top3:+7.3f}")

if __name__ == "__main__":
    print("\n" + "="*105)
    print("AUDIT 1: EXECUTION LATENCY STRESS (Simulating 1, 2, 3 events of frontrunning delay)")
    print("="*105)
    for delay in [0, 1, 2, 3]:
        evaluate_cohort(
            cohort_name=f"Latency Delay = +{delay} events (~{delay*150}ms delay)",
            target_creators=None,
            exclude_creators=SPAM_WALLETS,
            date_filter=None,
            latency_events_delay=delay,
            ticket_sol=0.5,
            hold_seconds=4.0
        )

    print("\n" + "="*105)
    print("AUDIT 2: TICKET SIZE SCALING (0.10, 0.25, 0.50, 1.00 SOL)")
    print("="*105)
    for ticket in [0.10, 0.25, 0.50, 1.00]:
        evaluate_cohort(
            cohort_name=f"Ticket Size = {ticket:.2f} SOL",
            target_creators=None,
            exclude_creators=SPAM_WALLETS,
            date_filter=None,
            latency_events_delay=1,
            ticket_sol=ticket,
            hold_seconds=4.0
        )

    print("\n" + "="*105)
    print("AUDIT 3: PER-DEPLOYER BREAKDOWN (Evaluating Specificity Across Wallets)")
    print("="*105)
    wallets = {
        "8de (Core Champion)": {"8deJ9xeUvXSJwicYptA9mHsU2rN2pDx37KWzkDkEXhU6"},
        "3uz (Core Burst Lead)": {"3uz65G8e463MA5FxcSu1rTUyWRtrRLRZYskKtEHHj7qn"},
        "5Zu (Secondary)": {"5ZuV8eqkvzYFVEKbLvGBdexL2tFv7E5BCd2HZpjqbdg"},
        "36A (Secondary)": {"36A6mEN5rYJdVTb6fMqVvG6ez8g2mTYdr1omWcQ1kDKG"},
    }
    for label, wset in wallets.items():
        evaluate_cohort(
            cohort_name=label,
            target_creators=wset,
            exclude_creators=None,
            date_filter=None,
            latency_events_delay=1,
            ticket_sol=0.5,
            hold_seconds=4.0
        )

    print("\n" + "="*105)
    print("AUDIT 4: WALK-FORWARD CHRONOLOGICAL VALIDATION (Fold 0 vs Fold 1)")
    print("="*105)
    evaluate_cohort(
        cohort_name="Fold 0 (Training Period: <= 2026-09-28)",
        target_creators=None,
        exclude_creators=SPAM_WALLETS,
        date_filter=("2026-09-20", "2026-09-28"),
        latency_events_delay=1,
        ticket_sol=0.5,
        hold_seconds=4.0
    )
    evaluate_cohort(
        cohort_name="Fold 1 (Out-of-Sample Test: >= 2026-09-29)",
        target_creators=None,
        exclude_creators=SPAM_WALLETS,
        date_filter=("2026-09-29", "2026-10-02"),
        latency_events_delay=1,
        ticket_sol=0.5,
        hold_seconds=4.0
    )

    print("\n" + "="*105)
    print("AUDIT 5: ADVERSARIAL NEGATIVE CONTROL (Quarantined Spam Wallets)")
    print("="*105)
    evaluate_cohort(
        cohort_name="Negative Control (Tested on Quarantined Spam)",
        target_creators=SPAM_WALLETS,
        exclude_creators=None,
        date_filter=None,
        latency_events_delay=1,
        ticket_sol=0.5,
        hold_seconds=4.0
    )
    print("="*105 + "\n")
