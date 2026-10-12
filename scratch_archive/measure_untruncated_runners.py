import gzip, pickle, json

print("Loading tapes...")
with gzip.open("research/multi_timeframe_audit_20261005/own_trade_replacement_v3/TAPES.pkl.gz", "rb") as f:
    tapes = pickle.load(f)

with open("scratch/graduated_tokens.json") as f:
    grad_data = json.load(f)
grad_mints = {t["mint"]: t for t in grad_data["graduated"]}

print(f"Loaded {len(grad_mints)} graduated mints.")

# Load 8tpkr trades on graduated mints
grad_trades = []
with gzip.open("research/multi_timeframe_audit_20261005/own_trade_replacement_v3/EXIT_PATH_LABELS.jsonl.gz", "rt") as f:
    for line in f:
        row = json.loads(line)
        if row.get("rule") == "8tpkr_fixed_05" and row.get("scenario") == "central85":
            if row.get("mint") in grad_mints:
                grad_trades.append(row)

print(f"Loaded {len(grad_trades)} 8tpkr trades on graduated mints.")

# For each trade, find its tape and calculate price at entry vs price at 84 SOL graduation
tape_by_mint = {t["mint"]: t for t in tapes if t["mint"] in grad_mints}

legacy_pnl_sum = 0.0
graduation_pnl_sum = 0.0
results = []

for trade in grad_trades:
    mint = trade["mint"]
    legacy_pnl = trade.get("pnl", 0.0)
    legacy_pnl_sum += legacy_pnl
    
    tape = tape_by_mint.get(mint)
    if not tape: continue
    
    # Entry index
    entry_idx = trade.get("index", 0)
    groups = tape.get("groups", [])
    if entry_idx >= len(groups): entry_idx = 0
    
    entry_st = groups[entry_idx].get("state", {})
    entry_rsol = entry_st.get("rsol_raw", 0) / 1e9
    
    # Graduation is at 84 SOL
    # Price ratio from entry_rsol to 84 SOL:
    # vsol = 30 + rsol
    entry_vsol = 30.0 + max(entry_rsol, 1.0)
    grad_vsol = 30.0 + 84.0 # 114.0
    
    price_multiple = (grad_vsol / entry_vsol)**2
    
    ticket = 0.50
    # SOL proceeds at 84 SOL:
    # Since tokens bought = ticket / entry_price_effective
    # At graduation, value in SOL = ticket * price_multiple
    gross_sol_at_grad = ticket * price_multiple
    net_sol_at_grad = gross_sol_at_grad - ticket - 0.005 # deduct entry/exit fees
    
    graduation_pnl_sum += net_sol_at_grad
    results.append({
        "mint": mint[:12],
        "entry_rsol": entry_rsol,
        "legacy_pnl": legacy_pnl,
        "price_mult": price_multiple,
        "grad_net_sol": net_sol_at_grad,
    })

print("\n" + "="*80)
print("THE MIGRATION EXTENSION: 40s TRUNCATED VS 84 SOL GRADUATION CARRYOVER")
print("="*80)
print(f"Number of Graduating Trades:          {len(results)}")
print(f"Legacy Truncated (40s Exit) Total:    {legacy_pnl_sum:+.4f} SOL (Avg: {legacy_pnl_sum/len(results):+.4f} SOL)")
print(f"Graduation Carryover (84 SOL) Total:  {graduation_pnl_sum:+.4f} SOL (Avg: {graduation_pnl_sum/len(results):+.4f} SOL)")
print(f"NET PROFIT EXTENSION:                 {graduation_pnl_sum - legacy_pnl_sum:+.4f} SOL")
print("="*80)

print("\n--- SAMPLE COMPARISONS ---")
for r in results[:10]:
    print(f"Mint: {r['mint']}... | Entry Res: {r['entry_rsol']:5.2f}S | 40s PnL: {r['legacy_pnl']:+.4f} SOL | At 84S: {r['grad_net_sol']:+.4f} SOL ({r['price_mult']:.2f}x)")
