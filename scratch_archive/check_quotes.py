import json, gzip, datetime

with gzip.open("research/amm_multiday_20261006/OPPORTUNITY_TRACES.json.gz", "rt") as f:
    traces = json.load(f)

pb_traces = [t for t in traces if t["rule"] == "amm_pullback_recovery" and t["ticket"] == 0.5 and t["scenario"] == "central85" and not t["control"]]

print("=== TRADES ON 2026-10-04 ===")
for i, t in enumerate(pb_traces):
    d = datetime.datetime.fromtimestamp(t["entry_time"], datetime.timezone.utc).strftime("%Y-%m-%d") if t.get("entry_time") else "unknown"
    p = t["pool"][:8]
    if d == "2026-10-04":
        if t.get("status") == "failed":
            print(f"#{i+1:2d} {p} | FAILED ENTRY")
            continue
        quotes = t.get("quotes", [])
        entry_t = t["entry_time"]
        q15 = [q for q in quotes if q["time"] - entry_t >= 15]
        q = q15[0] if q15 else (quotes[-1] if quotes else None)
        roi15 = q["net_ROI"] if q else 0
        mfe = max(q["net_ROI"] for q in quotes[:300]) if quotes else 0
        mae = min(q["net_ROI"] for q in quotes[:300]) if quotes else 0
        print(f"#{i+1:2d} {p} | 15s ROI: {roi15*100:+6.2f}% | MFE: {mfe*100:+6.2f}% | MAE: {mae*100:+6.2f}%")
