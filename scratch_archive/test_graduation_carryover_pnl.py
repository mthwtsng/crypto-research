import gzip, json
from collections import defaultdict

with open("scratch/graduated_tokens.json") as f:
    grad_data = json.load(f)
grad_mints = {t["mint"]: t for t in grad_data["graduated"]}
near_mints = {t["mint"]: t for t in grad_data["near_grad"]}

print(f"Loaded {len(grad_mints)} graduated mints.")

# Strategies to analyze
strategies = [
    "8tpkr_fixed_05",
    "8tpkr_fixed_10",
    "mature_flow",
    "mature_high_breadth",
    "mature_core"
]

results = {}

for strat in strategies:
    all_trades = []
    with gzip.open("research/multi_timeframe_audit_20261005/own_trade_replacement_v3/EXIT_PATH_LABELS.jsonl.gz", "rt") as f:
        for line in f:
            row = json.loads(line)
            if row.get("rule") == strat and row.get("scenario") == "central85":
                all_trades.append(row)
                
    total_trades = len(all_trades)
    base_pnl = sum(t.get("pnl", 0.0) for t in all_trades)
    
    grad_trades = [t for t in all_trades if t.get("mint") in grad_mints]
    grad_base_pnl = sum(t.get("pnl", 0.0) for t in grad_trades)
    
    # Measure what happens if graduated trades capture 50% or 75% of their MFE
    # ticket is 0.5 for 8tpkr_05 and mature, 1.0 for 8tpkr_10
    ticket = 1.0 if "10" in strat else 0.5
    
    # If we capture 50% of peak MFE instead of being stopped by 40s timer
    grad_carryover_pnl_50 = sum(ticket * min(t.get("observed_mfe", 0.0) * 0.50, 2.0) for t in grad_trades)
    grad_carryover_pnl_75 = sum(ticket * min(t.get("observed_mfe", 0.0) * 0.75, 3.0) for t in grad_trades)
    
    gain_at_50 = grad_carryover_pnl_50 - grad_base_pnl
    gain_at_75 = grad_carryover_pnl_75 - grad_base_pnl
    
    results[strat] = {
        "total_trades": total_trades,
        "base_pnl": base_pnl,
        "grad_count": len(grad_trades),
        "grad_base_pnl": grad_base_pnl,
        "grad_carryover_pnl_50": grad_carryover_pnl_50,
        "gain_at_50": gain_at_50,
        "new_portfolio_pnl_50": base_pnl + gain_at_50,
        "gain_at_75": gain_at_75,
        "new_portfolio_pnl_75": base_pnl + gain_at_75,
    }

print("\n" + "="*85)
print("FINANCIAL IMPACT OF MIGRATION CARRYOVER ACROSS 21 DAYS (Sep 14 - Oct 4)")
print("="*85)
print(f"{'Strategy':20} | {'Base PnL':10} | {'Grad Runs':9} | {'Base Grad PnL':13} | {'+50% MFE Carry':15} | {'New Total PnL':13}")
print("-" * 85)

for strat, r in results.items():
    print(f"{strat:20} | {r['base_pnl']:+9.4f} | {r['grad_count']:9d} | {r['grad_base_pnl']:+12.4f} | {r['gain_at_50']:+14.4f} | {r['new_portfolio_pnl_50']:+12.4f}")

print("="*85)
