#!/usr/bin/env python3
"""
Solana Starting 5 — Multi-VM Ghost Forward Telemetry Aggregator & Dashboard.

Aggregates real-time paper forward trades from local and synced remote VMs:
- Local: data/ghost_trades.jsonl, data/ghost_summary.json
- VM 1:  reports/vm1/ghost_trades.jsonl, reports/vm1/ghost_summary.json
- VM 2:  reports/vm2/ghost_trades.jsonl, reports/vm2/ghost_summary.json

Calculates consolidated PnL, win rates, strategy attribution (S1–S5),
profit factors, and displays an executive Contract-compliant dashboard.
"""

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


# ANSI Colors
BOLD = "\033[1m"
GREEN = "\033[32m"
RED = "\033[31m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
RESET = "\033[0m"
DIM = "\033[2m"

STRATEGY_NAMES = {
    "S1": "S1 Dev Dump Absorption",
    "S2": "S2 Survival Shelf Breakout",
    "S3": "S3 Whale Dislocation Floor",
    "S4": "S4 Upper ATH Breakout",
    "S5": "S5 Pre-Graduation Carryover",
}


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    records = []
    if not path.is_file():
        return records
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def format_sol(val: float) -> str:
    if val > 0:
        return f"{GREEN}+{val:.4f} SOL{RESET}"
    elif val < 0:
        return f"{RED}{val:.4f} SOL{RESET}"
    else:
        return f"{DIM} 0.0000 SOL{RESET}"


def format_pct(val: float) -> str:
    if val > 0:
        return f"{GREEN}+{val:.1f}%{RESET}"
    elif val < 0:
        return f"{RED}{val:.1f}%{RESET}"
    else:
        return f"{DIM} 0.0%{RESET}"


def aggregate_sources(sources: List[Dict[str, Any]]) -> Dict[str, Any]:
    all_trades: List[Dict[str, Any]] = []
    vm_summaries: Dict[str, Dict[str, Any]] = {}

    for src in sources:
        vm_name = src["name"]
        trades = load_jsonl(src["trades_path"])
        all_trades.extend(trades)
        summary = load_json(src["summary_path"])
        if summary:
            vm_summaries[vm_name] = summary

    # Filter closed trades
    closed_trades = [t for t in all_trades if t.get("event") == "CLOSE"]

    # Deduplicate trades if same signature/mint+timestamp occurs across logs
    seen = set()
    deduped_closed = []
    for t in closed_trades:
        key = (t.get("vm_id", ""), t.get("mint", ""), t.get("timestamp", 0))
        if key not in seen:
            seen.add(key)
            deduped_closed.append(t)

    # Global Stats
    total_closed = len(deduped_closed)
    wins = [t for t in deduped_closed if t.get("net_pnl_sol", 0.0) > 0.0]
    losses = [t for t in deduped_closed if t.get("net_pnl_sol", 0.0) <= 0.0]
    win_cnt = len(wins)
    loss_cnt = len(losses)
    win_rate = (win_cnt / total_closed * 100.0) if total_closed > 0 else 0.0

    net_pnl = sum(t.get("net_pnl_sol", 0.0) for t in deduped_closed)
    gross_win = sum(t.get("net_pnl_sol", 0.0) for t in wins)
    gross_loss = abs(sum(t.get("net_pnl_sol", 0.0) for t in losses))
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else (99.9 if gross_win > 0 else 1.0)
    avg_win = (gross_win / win_cnt) if win_cnt > 0 else 0.0
    avg_loss = (gross_loss / loss_cnt) if loss_cnt > 0 else 0.0
    payoff_ratio = (avg_win / avg_loss) if avg_loss > 0 else (99.9 if avg_win > 0 else 1.0)

    # Strategy Breakdown
    by_strat: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for t in deduped_closed:
        code = t.get("strategy_code", "S?")
        by_strat[code].append(t)

    strat_stats = {}
    for code, full_name in STRATEGY_NAMES.items():
        s_trades = by_strat.get(code, [])
        s_count = len(s_trades)
        s_wins = [t for t in s_trades if t.get("net_pnl_sol", 0.0) > 0.0]
        s_losses = [t for t in s_trades if t.get("net_pnl_sol", 0.0) <= 0.0]
        s_win_cnt = len(s_wins)
        s_loss_cnt = len(s_losses)
        s_wr = (s_win_cnt / s_count * 100.0) if s_count > 0 else 0.0
        s_pnl = sum(t.get("net_pnl_sol", 0.0) for t in s_trades)
        s_gw = sum(t.get("net_pnl_sol", 0.0) for t in s_wins)
        s_gl = abs(sum(t.get("net_pnl_sol", 0.0) for t in s_losses))
        s_pf = (s_gw / s_gl) if s_gl > 0 else (99.9 if s_gw > 0 else 1.0)

        strat_stats[code] = {
            "name": full_name,
            "trades": s_count,
            "wins": s_win_cnt,
            "losses": s_loss_cnt,
            "win_rate": s_wr,
            "net_pnl": s_pnl,
            "profit_factor": s_pf,
        }

    # VM Breakdown
    by_vm: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for t in deduped_closed:
        vm = t.get("vm_id", "local")
        by_vm[vm].append(t)

    vm_stats = {}
    for vm, v_trades in by_vm.items():
        v_count = len(v_trades)
        v_wins = sum(1 for t in v_trades if t.get("net_pnl_sol", 0.0) > 0.0)
        v_pnl = sum(t.get("net_pnl_sol", 0.0) for t in v_trades)
        vm_stats[vm] = {
            "trades": v_count,
            "wins": v_wins,
            "win_rate": (v_wins / v_count * 100.0) if v_count > 0 else 0.0,
            "net_pnl": v_pnl,
        }

    return {
        "total_closed": total_closed,
        "wins": win_cnt,
        "losses": loss_cnt,
        "win_rate": win_rate,
        "net_pnl": net_pnl,
        "gross_win": gross_win,
        "gross_loss": gross_loss,
        "profit_factor": profit_factor,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "payoff_ratio": payoff_ratio,
        "strat_stats": strat_stats,
        "vm_stats": vm_stats,
        "vm_summaries": vm_summaries,
        "deduped_closed": deduped_closed,
    }


def print_dashboard(agg: Dict[str, Any]) -> None:
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    print("\n" + "=" * 94)
    print(f" {BOLD}SOLANA STARTING 5 — CONSOLIDATED GHOST FORWARD TELEMETRY DASHBOARD{RESET}")
    print(f" Timestamp: {now_str} | Zero-Capital Paper Forward Mode")
    print("=" * 94)

    # Consolidated Metrics Box
    print(f"\n{BOLD}CONSOLIDATED PORTFOLIO PERFORMANCE:{RESET}")
    pnl_str = format_sol(agg["net_pnl"])
    wr_str = f"{agg['win_rate']:.1f}%"
    pf_str = f"{agg['profit_factor']:.2f}"
    payoff_str = f"{agg['payoff_ratio']:.2f}"

    print(f" • Total Closed Trades:  {agg['total_closed']:>6}  ({agg['wins']} W / {agg['losses']} L)")
    print(f" • Win Rate:             {wr_str:>10}  | Profit Factor: {pf_str}")
    print(f" • Net Realized PnL:     {pnl_str}")
    print(f" • Gross Win / Loss:     +{agg['gross_win']:.4f} SOL / -{agg['gross_loss']:.4f} SOL")
    print(f" • Avg Win / Avg Loss:   +{agg['avg_win']:.4f} SOL / -{agg['avg_loss']:.4f} SOL (Payoff: {payoff_str})")

    # VM Activity
    print("\n" + "-" * 94)
    print(f"{BOLD}RUNNING NODES / VM BREAKDOWN:{RESET}")
    if not agg["vm_stats"]:
        print(f" {DIM}No active trades recorded across VM instances yet. (Waiting for curve events){RESET}")
    else:
        print(f" {'VM ID':<16} {'Trades':<10} {'Wins':<10} {'Win Rate':<14} {'Net PnL':<20}")
        print(" " + "-" * 70)
        for vm, st in agg["vm_stats"].items():
            print(f" {vm:<16} {st['trades']:<10} {st['wins']:<10} {st['win_rate']:>5.1f}%        {format_sol(st['net_pnl'])}")

    # Strategy Attribution
    print("\n" + "-" * 94)
    print(f"{BOLD}STRATEGY ATTRIBUTION (CANONICAL S1–S5):{RESET}")
    print(f" {'Code':<6} {'Strategy Name':<30} {'Trades':<8} {'W / L':<10} {'Win %':<10} {'Profit Factor':<15} {'Net PnL':<15}")
    print(" " + "-" * 92)
    for code in ["S1", "S2", "S3", "S4", "S5"]:
        st = agg["strat_stats"].get(code, {})
        w_l = f"{st.get('wins', 0)}/{st.get('losses', 0)}"
        pf = f"{st.get('profit_factor', 1.0):.2f}"
        print(
            f" {code:<6} {st.get('name', code):<30} {st.get('trades', 0):<8} {w_l:<10} "
            f"{st.get('win_rate', 0.0):>5.1f}%    {pf:<15} {format_sol(st.get('net_pnl', 0.0))}"
        )

    # Active Positions
    active_positions = []
    for vm_name, summary in agg["vm_summaries"].items():
        for pos in summary.get("active_positions", []):
            active_positions.append((vm_name, pos))

    print("\n" + "-" * 94)
    print(f"{BOLD}ACTIVE GHOST POSITIONS ({len(active_positions)} open):{RESET}")
    if not active_positions:
        print(f" {DIM}No open positions currently held.{RESET}")
    else:
        print(f" {'Node':<10} {'Strat':<6} {'Mint':<16} {'Reserve':<12} {'ROI':<12} {'Peak ROI':<12} {'Age':<8}")
        print(" " + "-" * 76)
        for vm_name, pos in active_positions:
            mint_short = pos.get("mint", "")[:12] + "..."
            roi_str = format_pct(pos.get("roi_pct", 0.0))
            peak_str = format_pct(pos.get("peak_roi_pct", 0.0))
            print(
                f" {vm_name:<10} {pos.get('strategy_code', 'S?'):<6} {mint_short:<16} "
                f"{pos.get('current_reserve_sol', 0.0):>5.2f} SOL    {roi_str:<12} {peak_str:<12} {pos.get('elapsed_secs', 0)}s"
            )

    # Recent Closed Trades (Last 8)
    recent = sorted(agg["deduped_closed"], key=lambda x: x.get("timestamp", 0), reverse=True)[:8]
    print("\n" + "-" * 94)
    print(f"{BOLD}RECENT CLOSED GHOST TRADES:{RESET}")
    if not recent:
        print(f" {DIM}No closed trades recorded yet.{RESET}")
    else:
        print(f" {'Time (UTC)':<18} {'Strat':<6} {'Mint':<14} {'PnL (SOL)':<20} {'ROI %':<12} {'Duration':<10} {'Exit Reason'}")
        print(" " + "-" * 92)
        for t in recent:
            t_str = t.get("datetime_utc", "")[:19].replace("T", " ")
            mint_short = t.get("mint", "")[:10] + "..."
            pnl = format_sol(t.get("net_pnl_sol", 0.0))
            roi = format_pct(t.get("pnl_pct", 0.0))
            dur = f"{t.get('duration_secs', 0)}s"
            reason = t.get("exit_reason", "")[:28]
            print(f" {t_str:<18} {t.get('strategy_code', 'S?'):<6} {mint_short:<14} {pnl:<20} {roi:<12} {dur:<10} {reason}")

    print("=" * 94 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Multi-VM Ghost Forward Telemetry Aggregator")
    parser.add_argument("--root", type=str, default=".", help="Root directory of repository")
    parser.add_argument("--watch", type=int, default=0, help="Watch interval in seconds (0 to run once)")
    parser.add_argument("--export", type=str, default="", help="Path to export JSON aggregation report")
    args = parser.parse_args()

    root = Path(args.root).resolve()

    sources = [
        {
            "name": "Local Node",
            "trades_path": root / "data" / "ghost_trades.jsonl",
            "summary_path": root / "data" / "ghost_summary.json",
        },
        {
            "name": "GCP VM1",
            "trades_path": root / "reports" / "vm1" / "ghost_trades.jsonl",
            "summary_path": root / "reports" / "vm1" / "ghost_summary.json",
        },
        {
            "name": "GCP VM2",
            "trades_path": root / "reports" / "vm2" / "ghost_trades.jsonl",
            "summary_path": root / "reports" / "vm2" / "ghost_summary.json",
        },
    ]

    while True:
        agg = aggregate_sources(sources)
        print_dashboard(agg)

        if args.export:
            export_path = Path(args.export)
            export_path.parent.mkdir(parents=True, exist_ok=True)
            with open(export_path, "w", encoding="utf-8") as f:
                json.dump(agg, f, indent=2, default=str)
            print(f"[✓] Exported telemetry snapshot to {export_path}")

        if args.watch <= 0:
            break
        time.sleep(args.watch)


if __name__ == "__main__":
    main()
