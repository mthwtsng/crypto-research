import json, gzip

with gzip.open("research/amm_multiday_20261006/REPLAY_TRADES.json.gz", "rt") as f:
    trades = json.load(f)

pullback = [t for t in trades if t["rule"] == "amm_pullback_recovery" and t["recipe"] == "timer15" and t["ticket"] == 0.5 and t["scenario"] == "central85" and t["fee"] == 1505000]
print(f"Pullback central85 records: {len(pullback)}")

for i, t in enumerate(pullback):
    p = t["pool"][:8]
    net_sol = t["net"] / 1e9
    entry_bill = t["entry_bill"] / 1e9
    roi = (net_sol / entry_bill) * 100 if entry_bill > 0 else 0
    dur = t["close_time"] - t["entry_time"] if t.get("close_time") else 0
    status = t["status"]
    legs = t.get("legs", [])
    reason = legs[0]["reason"] if legs else "N/A"
    age = t["age"]
    print(f"{i+1:2d}. Pool: {p} | Status: {status:6s} | Net: {net_sol:+.4f} SOL | ROI: {roi:+.2f}% | Age: {age:4d}s | Dur: {dur:2d}s | Exit: {reason}")
