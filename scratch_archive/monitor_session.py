import json
import os
import sys

def main():
    path = "data/ghost_summary.json"
    if not os.path.exists(path):
        print("data/ghost_summary.json does not exist yet.")
        return

    with open(path) as f:
        s = json.load(f)

    print("==========================================================================================")
    print("                    SOLANA CANONICAL STARTING 5 — SHADOW MONITORING DASHBOARD")
    print("==========================================================================================")
    print(f" • VM Identifier:     {s.get('vm_id')}")
    print(f" • Uptime:            {s.get('uptime_secs', 0)}s ({s.get('uptime_secs', 0)/60:.1f} mins)")
    print(f" • Active Positions:  {s.get('active_positions_count', 0)}")
    print(f" • Total Closed:      {s.get('total_closed_trades', 0)} (Wins: {s.get('wins', 0)}, Losses: {s.get('losses', 0)}, Win Rate: {s.get('win_rate_pct', 0.0):.1f}%)")
    print(f" • Total Net PnL:     {s.get('total_net_pnl_sol', 0.0):>+8.4f} SOL")
    print(f" • Virtual Cash:      {s.get('virtual_cash_sol', 0.0):.4f} SOL")
    print(f" • Total Equity:      {s.get('total_equity_sol', 0.0):.4f} SOL")
    print(f" • Total Shielded:    {s.get('total_shielded_coins', 0)} coins blocked")

    print("\n--- ACTIVE POSITIONS ---")
    active = s.get("active_positions", [])
    if not active:
        print(" (None currently open)")
    for p in active:
        wl_tag = f"⭐ {p.get('whitelisted_by')}" if p.get('is_whitelisted') else ""
        r_sol = p.get('current_reserve_sol') or 0.0
        roi_str = f"{p.get('roi_pct'):>+6.1f}%" if p.get('roi_pct') is not None else " Await"
        peak_str = f"{p.get('peak_roi_pct'):>+6.1f}%" if p.get('peak_roi_pct') is not None else "   N/A"
        tokens = p.get('tokens_held') or 0
        print(f" • [{p.get('strategy_code')}] Mint: {p.get('mint')[:12]}.. | Reserve: {r_sol:.2f} SOL | Tokens: {tokens:,} | Live ROI: {roi_str} | Peak: {peak_str} | Status: {p.get('status')} {wl_tag}")

    print("\n--- RECENT CLOSED TRADES ---")
    closed = s.get("recent_closed_trades", [])
    if not closed:
        print(" (No closed trades yet)")
    for t in closed:
        wl_tag = f"⭐ {t.get('whitelisted_by')}" if t.get('is_whitelisted') else ""
        note = f" | {t.get('post_exit_note')}" if t.get('post_exit_note') else ""
        print(f" • [{t.get('strategy_code')}] Mint: {t.get('mint')[:12]}.. | Net: {t.get('net_pnl_sol', 0.0):>+8.4f} SOL ({t.get('pnl_pct', 0.0):>+6.1f}%) | Peak: {t.get('peak_roi_pct', 0.0):>+6.1f}% | Reason: {t.get('exit_reason')}{note} {wl_tag}")

    print("\n--- STRATEGY BREAKDOWN ---")
    sb = s.get("strategy_breakdown", {})
    for code, stats in sorted(sb.items()):
        print(f" • {code:<4}: Trades: {stats.get('trades', 0):<2} | Wins: {stats.get('wins', 0):<2} | Losses: {stats.get('losses', 0):<2} | WR: {stats.get('win_rate_pct', 0.0):>5.1f}% | Net PnL: {stats.get('net_pnl_sol', 0.0):>+8.4f} SOL")

    print("\n--- RECENT SHIELDED COINS AUDIT ---")
    shielded = s.get("recent_shielded_coins", [])
    if not shielded:
        print(" (No shielded coins recorded yet)")
    for c in shielded[:10]:
        print(f" • [{c.get('layer')}] Mint: {c.get('mint')[:12]}.. | MCAP: ${c.get('market_cap_usd', 0.0)/1000:>5.1f}k ({c.get('reserve_sol', 0.0):>5.1f} SOL) | Reason: {c.get('reason')}")
    print("==========================================================================================")

if __name__ == "__main__":
    main()
