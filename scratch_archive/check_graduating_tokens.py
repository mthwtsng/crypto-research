import gzip, pickle, json

print("Loading tapes...")
with gzip.open("research/multi_timeframe_audit_20261005/own_trade_replacement_v3/TAPES.pkl.gz", "rb") as f:
    tapes = pickle.load(f)

print(f"Loaded {len(tapes)} tapes.")

graduated_tokens = []
near_grad_tokens = []

for i, tape in enumerate(tapes):
    mint = tape["mint"]
    groups = tape.get("groups", [])
    max_sol_res = 0.0
    complete_event = False
    
    for g in groups:
        st = g.get("state")
        if st and "rsol_raw" in st:
            sol = st["rsol_raw"] / 1e9
            if sol > max_sol_res: max_sol_res = sol
            if st.get("rtokens_raw", 1) == 0:
                complete_event = True
                
        for ev in g.get("events", []):
            if ev.get("complete", False) or ev.get("is_complete", False):
                complete_event = True
            r_sol = ev.get("real_sol_reserves", 0) / 1e9
            if r_sol > max_sol_res: max_sol_res = r_sol
            
    if max_sol_res >= 83.5 or complete_event:
        graduated_tokens.append({
            "index": i,
            "mint": mint,
            "max_sol": max_sol_res,
            "complete": complete_event,
            "date": str(tape.get("date", "")),
            "groups_count": len(groups),
        })
    elif max_sol_res >= 50.0:
        near_grad_tokens.append({
            "index": i,
            "mint": mint,
            "max_sol": max_sol_res,
            "date": str(tape.get("date", "")),
            "groups_count": len(groups),
        })

print(f"\nResults across 5,040 tapes:")
print(f"Graduated to 84 SOL: {len(graduated_tokens)} tokens")
print(f"Reached 50–83 SOL: {len(near_grad_tokens)} tokens")

with open("scratch/graduated_tokens.json", "w") as f:
    json.dump({
        "graduated": graduated_tokens,
        "near_grad": near_grad_tokens
    }, f, indent=2)

print("Saved to scratch/graduated_tokens.json")
