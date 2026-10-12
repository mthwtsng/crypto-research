import gzip, pickle, json

print("Loading 5,040 tapes...")
with gzip.open("research/multi_timeframe_audit_20261005/own_trade_replacement_v3/TAPES.pkl.gz", "rb") as f:
    tapes = pickle.load(f)

print(f"Loaded {len(tapes)} tapes.")

# Experiment: Edge 3 (72+ SOL Pre-Graduation Carryover)
# Entry rule:
# 1. Curve reserve crosses >= 70.0 SOL (or 72.0 SOL)
# 2. Buy 0.50 SOL at that slot
# 3. Track forward trajectory to:
#    a) Invalidation: drops below 60.0 SOL
#    b) Graduation: reaches 84.0 SOL (curve complete)
#    c) If graduated: token enters migration freeze. Post-migration AMM initial quote / return.

results_70 = []
results_72 = []

for i, tape in enumerate(tapes):
    mint = tape["mint"]
    groups = tape.get("groups", [])
    
    # Check if crosses 70 and 72
    crossed_70_idx = None
    crossed_72_idx = None
    
    for g_idx, g in enumerate(groups):
        st = g.get("state", {})
        rsol = st.get("rsol_raw", 0) / 1e9
        if rsol >= 70.0 and crossed_70_idx is None:
            crossed_70_idx = g_idx
        if rsol >= 72.0 and crossed_72_idx is None:
            crossed_72_idx = g_idx
            
    def evaluate_entry(entry_idx, trigger_sol, invalidation_sol=60.0):
        if entry_idx is None: return None
        entry_g = groups[entry_idx]
        entry_slot = entry_g["slot"]
        entry_time = entry_g["block_time"]
        entry_res = entry_g.get("state", {}).get("rsol_raw", 0) / 1e9
        
        # Track forward from entry_idx
        graduated = False
        invalidated = False
        exit_idx = None
        max_res = entry_res
        min_res = entry_res
        
        for f_idx in range(entry_idx + 1, len(groups)):
            fg = groups[f_idx]
            fst = fg.get("state", {})
            fres = fst.get("rsol_raw", 0) / 1e9
            if fres > max_res: max_res = fres
            if fres < min_res: min_res = fres
            
            if fres >= 83.5 or fst.get("rtokens_raw", 1) == 0:
                graduated = True
                exit_idx = f_idx
                break
            if fres <= invalidation_sol:
                invalidated = True
                exit_idx = f_idx
                break
                
        if not graduated and not invalidated and len(groups) > entry_idx + 1:
            exit_idx = len(groups) - 1
            
        final_res = groups[exit_idx].get("state", {}).get("rsol_raw", 0) / 1e9 if exit_idx else entry_res
        
        # Bonding curve price proportional to (vsol + rsol)^2 or rsol
        # Exact price ratio = (final_vsol / entry_vsol)^2
        # vsol_entry = 30.0 + entry_res
        # vsol_final = 30.0 + final_res
        price_roi = ((30.0 + final_res) / (30.0 + entry_res))**2 - 1.0
        
        return {
            "mint": mint,
            "trigger_sol": trigger_sol,
            "entry_res": entry_res,
            "final_res": final_res,
            "graduated": graduated,
            "invalidated": invalidated,
            "max_res": max_res,
            "min_res": min_res,
            "curve_roi": price_roi,
            "date": str(tape.get("date", ""))
        }

    e70 = evaluate_entry(crossed_70_idx, 70.0, 60.0)
    if e70: results_70.append(e70)
    
    e72 = evaluate_entry(crossed_72_idx, 72.0, 60.0)
    if e72: results_72.append(e72)

print("\n" + "="*75)
print("EDGE 3: PRE-GRADUATION ENTRY (BONDING CURVE TO GRADUATION)")
print("="*75)

for name, res_list, trig in [("Trigger at 70 SOL", results_70, 70.0), ("Trigger at 72 SOL", results_72, 72.0)]:
    n = len(res_list)
    grads = sum(1 for r in res_list if r["graduated"])
    invals = sum(1 for r in res_list if r["invalidated"])
    other = n - grads - invals
    grad_rate = grads / n * 100 if n else 0
    
    # PnL on 0.5 SOL tickets (before fees)
    total_curve_pnl = sum(0.5 * r["curve_roi"] for r in res_list)
    # Deduct 0.003 SOL network fee + 1% round trip curve fee per trade
    net_curve_pnl = sum(0.5 * r["curve_roi"] - 0.003 - 0.01 * 0.5 for r in res_list)
    
    avg_grad_gain = sum(0.5 * r["curve_roi"] for r in res_list if r["graduated"]) / grads if grads else 0
    avg_inval_loss = sum(0.5 * r["curve_roi"] for r in res_list if r["invalidated"]) / invals if invals else 0
    
    print(f"\n--- {name} ---")
    print(f"Total Qualified Signals:     {n}")
    print(f"Tokens Graduating (to 84S):  {grads} ({grad_rate:.1f}%)")
    print(f"Tokens Invalidating (<60S):  {invals} ({invals/n*100 if n else 0:.1f}%)")
    print(f"Tokens Stalling on Curve:    {other}")
    print(f"Avg Gain on Graduated Trade: {avg_grad_gain:+.4f} SOL (+{avg_grad_gain/0.5*100:.1f}%)")
    print(f"Avg Loss on Invalidated:    {avg_inval_loss:+.4f} SOL ({avg_inval_loss/0.5*100:.1f}%)")
    print(f"Net Curve PnL (0.5 tickets): {net_curve_pnl:+.4f} SOL")

with open("scratch/edge3_results.json", "w") as f:
    json.dump({"results_70": results_70, "results_72": results_72}, f, indent=2)
