import json, gzip

with gzip.open("research/amm_multiday_20261006/OPPORTUNITY_TRACES.json.gz", "rt") as f:
    traces = json.load(f)

pb_traces = [t for t in traces if t["rule"] == "amm_pullback_recovery" and t["ticket"] == 0.5 and t["scenario"] == "central85" and not t["control"]]
print(f"Loaded {len(pb_traces)} pullback central85 traces")

# Baseline: 15s fixed timer
print("\n=== BASELINE: CODEX BLIND 15s TIMER ===")
baseline_total = 0.0
baseline_wins = 0
baseline_losses = 0

for i, t in enumerate(pb_traces):
    if t.get("status") == "failed":
        baseline_total -= 0.000505
        baseline_losses += 1
        continue
        
    bill = t["entry_bill_SOL"]
    quotes = t.get("quotes", [])
    entry_time = t["entry_time"]
    
    # 15s exit
    q15 = None
    for q in quotes:
        if q["time"] - entry_time >= 15:
            q15 = q
            break
    if not q15 and quotes:
        q15 = quotes[-1]
    
    roi = q15["net_ROI"] if q15 else 0.0
    net_sol = bill * roi
    baseline_total += net_sol
    if net_sol > 0: baseline_wins += 1
    else: baseline_losses += 1

print(f"Blind 15s Total: {baseline_total:+.4f} SOL (Wins: {baseline_wins}, Losses: {baseline_losses})")

# Triad Exit:
# 1. Hard stop at -10%
# 2. At t=10s: if ROI <= +2%, scratch immediately
# 3. If ROI >= +10%, ratchet stop to +2% (breakeven)
# 4. Take profit at +20%
print("\n=== TRIAD SELL STRATEGY (TRAJECTORY-DERIVED) ===")
triad_total = 0.0
triad_wins = 0
triad_losses = 0

for i, t in enumerate(pb_traces):
    if t.get("status") == "failed":
        triad_total -= 0.000505
        triad_losses += 1
        p = t["pool"][:8]
        print(f"{i+1:2d}. Pool: {p} | Status: failed | Net: -0.0005 SOL")
        continue
        
    bill = t["entry_bill_SOL"]
    quotes = t.get("quotes", [])
    entry_time = t["entry_time"]
    
    ratchet_armed = False
    stop_loss = -0.10  # -10% hard stop
    exit_roi = None
    exit_reason = None
    exit_dur = 0
    
    for q in quotes:
        dt = q["time"] - entry_time
        roi = q["net_ROI"]
        
        # Check if ratchet armed
        if roi >= 0.10 and not ratchet_armed:
            ratchet_armed = True
            stop_loss = 0.02  # Lock breakeven at +2%
        
        # Check stop loss hit
        if roi <= stop_loss:
            exit_roi = stop_loss
            exit_reason = "ratchet_stop" if ratchet_armed else "hard_stop_-10%"
            exit_dur = dt
            break
            
        # Check take profit at +20%
        if roi >= 0.20:
            exit_roi = 0.20
            exit_reason = "take_profit_+20%"
            exit_dur = dt
            break
            
        # Check 10s stagnation scratch
        if dt >= 10 and not ratchet_armed:
            if roi <= 0.02:
                exit_roi = roi
                exit_reason = "10s_stagnation_scratch"
                exit_dur = dt
                break
                
        # Maximum hold: 25s
        if dt >= 25:
            exit_roi = roi
            exit_reason = "25s_timeout"
            exit_dur = dt
            break
            
    if exit_roi is None and quotes:
        exit_roi = quotes[-1]["net_ROI"]
        exit_reason = "end_of_tape"
        exit_dur = quotes[-1]["time"] - entry_time
        
    net_sol = bill * exit_roi
    triad_total += net_sol
    if net_sol > 0: triad_wins += 1
    else: triad_losses += 1
    p = t["pool"][:8]
    print(f"{i+1:2d}. Pool: {p} | Exit ROI: {exit_roi*100:+.2f}% | Net: {net_sol:+.4f} SOL | Dur: {exit_dur:2d}s | Reason: {exit_reason}")

print(f"\nTriad Total: {triad_total:+.4f} SOL (Wins: {triad_wins}, Losses: {triad_losses})")
print(f"Improvement over blind 15s timer: {triad_total - baseline_total:+.4f} SOL")
