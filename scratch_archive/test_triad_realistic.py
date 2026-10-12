import json, gzip

with gzip.open("research/amm_multiday_20261006/OPPORTUNITY_TRACES.json.gz", "rt") as f:
    traces = json.load(f)

pb_traces = [t for t in traces if t["rule"] == "amm_pullback_recovery" and t["ticket"] == 0.5 and t["scenario"] == "central85" and not t["control"]]

def simulate_triad(t1_target=0.15, max_hold=20):
    total_pnl = 0.0
    wins = 0
    losses = 0
    by_date = {}
    
    for t in pb_traces:
        import datetime
        d = datetime.datetime.fromtimestamp(t["entry_time"], datetime.timezone.utc).strftime("%Y-%m-%d") if t.get("entry_time") else "unknown"
        if d not in by_date: by_date[d] = 0.0
        
        if t.get("status") == "failed":
            total_pnl -= 0.000505
            losses += 1
            by_date[d] -= 0.000505
            continue
            
        bill = t["entry_bill_SOL"]
        quotes = t.get("quotes", [])
        entry_t = t["entry_time"]
        
        # We track 2 tranches: 50% each
        # Tranche 1 exits at t1_target or at stagnation/timeout
        # Tranche 2 exits with trailing stop or at timeout
        
        t1_sold = False
        t1_roi = None
        t2_sold = False
        t2_roi = None
        
        peak_roi = -1.0
        ratchet_armed = False
        
        for q in quotes:
            dt = q["time"] - entry_t
            roi = q["net_ROI"]
            if roi > peak_roi: peak_roi = roi
            
            # Check T1 target
            if not t1_sold and roi >= t1_target:
                t1_sold = True
                t1_roi = roi
                ratchet_armed = True
                
            # Stagnation scratch at t=10s
            if dt >= 10:
                if roi <= 0.02 and not ratchet_armed:
                    if not t1_sold:
                        t1_sold = True
                        t1_roi = roi
                    if not t2_sold:
                        t2_sold = True
                        t2_roi = roi
                    break
                    
            # Trailing stop on T2 if armed
            if ratchet_armed and not t2_sold:
                # 8% trail from peak or breakeven (+2%)
                trail_stop = max(0.02, peak_roi - 0.08)
                if roi <= trail_stop:
                    t2_sold = True
                    t2_roi = roi
                    break
                    
            # Hard timeout
            if dt >= max_hold:
                if not t1_sold:
                    t1_sold = True
                    t1_roi = roi
                if not t2_sold:
                    t2_sold = True
                    t2_roi = roi
                break
                
        # If reached end of tape
        last_roi = quotes[-1]["net_ROI"] if quotes else 0.0
        if not t1_sold: t1_roi = last_roi
        if not t2_sold: t2_roi = last_roi
        
        trade_pnl = 0.5 * bill * t1_roi + 0.5 * bill * t2_roi
        total_pnl += trade_pnl
        by_date[d] += trade_pnl
        if trade_pnl > 0: wins += 1
        else: losses += 1
        
    return total_pnl, wins, losses, by_date

for t1 in [0.15, 0.20]:
    for mh in [15, 18, 20, 25]:
        pnl, w, l, bd = simulate_triad(t1_target=t1, max_hold=mh)
        print(f"Tranche1 target: {t1*100:.0f}% | Max hold: {mh:2d}s -> Net PnL: {pnl:+.4f} SOL (W: {w:2d}, L: {l:2d})")
        print(f"   Daily: Oct2: {bd.get('2026-10-02', 0):+.4f} | Oct3: {bd.get('2026-10-03', 0):+.4f} | Oct4: {bd.get('2026-10-04', 0):+.4f}")
