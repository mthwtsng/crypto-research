import gzip, pickle

with gzip.open("research/multi_timeframe_audit_20261005/own_trade_replacement_v3/TAPES.pkl.gz", "rb") as f:
    tapes = pickle.load(f)

emz_tape = None
for t in tapes:
    if "EMZGhHQWyu3G" in t.get("mint", ""):
        emz_tape = t
        break

if not emz_tape:
    print("EMZGhHQWyu3G tape not found!")
else:
    print("Found EMZ tape! Mint:", emz_tape["mint"])
    groups = emz_tape.get("groups", [])
    print(f"Total groups: {len(groups)}")
    
    # Entry was at slot 453091827 (idx 26)
    for i, g in enumerate(groups[:35]):
        slot = g.get("slot")
        st = g.get("state", {})
        rsol = st.get("rsol_raw", 0) / 1e9
        evs = g.get("events", [])
        sides = [("BUY" if e.get("is_buy") else "SELL", e.get("sol_amount", 0)/1e9) for e in evs]
        print(f"Group {i:2d} | Slot: {slot} | Res: {rsol:5.2f} SOL | Events: {sides}")
