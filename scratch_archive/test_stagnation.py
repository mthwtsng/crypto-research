import json, gzip

with gzip.open("research/amm_multiday_20261006/OPPORTUNITY_TRACES.json.gz", "rt") as f:
    traces = json.load(f)

pb_traces = [t for t in traces if t["rule"] == "amm_pullback_recovery" and t["ticket"] == 0.5 and t["scenario"] == "central85" and not t["control"]]

print("=== EXPERIMENT: 10s STAGNATION SCRATCH VS 15s FIXED TIMER ===")

def eval_policy(scratch_at_10=False, scratch_thresh=0.02, max_hold=15):
    pnl = 0.0
    wins = 0
    losses = 0
    scratches = 0
    by_date = {}
    
    for t in pb_traces:
        if t.get("entry_time"):
            import datetime
            d = datetime.datetime.fromtimestamp(t["entry_time"], datetime.timezone.utc).strftime("%Y-%m-%d")
        else:
            d = "unknown"
        if d not in by_date: by_date[d] = 0.0
        
        if t.get("status") == "failed":
            pnl -= 0.000505
            losses += 1
            by_date[d] -= 0.000505
            continue
            
        bill = t["entry_bill_SOL"]
        quotes = t.get("quotes", [])
        entry_t = t["entry_time"]
        
        # Check ROI at 10s
        q10 = None
        for q in quotes:
            if q["time"] - entry_t >= 10:
                q10 = q
                break
        if not q10 and quotes: q10 = quotes[-1]
        
        roi10 = q10["net_ROI"] if q10 else 0.0
        
        # Check exit
        if scratch_at_10 and roi10 <= scratch_thresh:
            exit_roi = roi10
            scratches += 1
        else:
            # Hold to max_hold
            q_exit = None
            for q in quotes:
                if q["time"] - entry_t >= max_hold:
                    q_exit = q
                    break
            if not q_exit and quotes: q_exit = quotes[-1]
            exit_roi = q_exit["net_ROI"] if q_exit else 0.0
            
        trade_pnl = bill * exit_roi
        pnl += trade_pnl
        by_date[d] += trade_pnl
        if trade_pnl > 0: wins += 1
        else: losses += 1
        
    return pnl, wins, losses, scratches, by_date

pnl_base, w_base, l_base, _, d_base = eval_policy(scratch_at_10=False, max_hold=15)
print(f"Blind 15s Timer: Total PnL = {pnl_base:+.4f} SOL (W: {w_base}, L: {l_base})")
for d, v in sorted(d_base.items()):
    print(f"  {d}: {v:+.4f} SOL")

print("\n--- Testing 10s Stagnation Scratch (if ROI@10s <= +2%, exit at 10s, else hold to 15s) ---")
pnl_scratch, w_scratch, l_scratch, n_scratches, d_scratch = eval_policy(scratch_at_10=True, scratch_thresh=0.02, max_hold=15)
print(f"10s Scratch + 15s Hold: Total PnL = {pnl_scratch:+.4f} SOL (W: {w_scratch}, L: {l_scratch}, Scratches: {n_scratches})")
for d, v in sorted(d_scratch.items()):
    print(f"  {d}: {v:+.4f} SOL")
print(f"Difference: {pnl_scratch - pnl_base:+.4f} SOL")
