import json

with open("scratch/graduated_tokens.json") as f:
    grad_data = json.load(f)
grad_mints = set(t["mint"] for t in grad_data["graduated"])
near_mints = set(t["mint"] for t in grad_data["near_grad"])
print(f"Loaded {len(grad_mints)} graduated mints, {len(near_mints)} near-grad mints.")

# Check bot_edge_gap CANDIDATE_TRADES.jsonl
matches_grad = []
matches_near = []
all_trades = 0

with open("research/bot_edge_gap_20261006/CANDIDATE_TRADES.jsonl") as f:
    for line in f:
        t = json.loads(line)
        all_trades += 1
        mint = t.get("mint")
        if mint in grad_mints:
            matches_grad.append(t)
        elif mint in near_mints:
            matches_near.append(t)

print(f"\nTotal candidate trades checked: {all_trades}")
print(f"Matches that fully graduated (84 SOL): {len(matches_grad)}")
print(f"Matches that reached 50-83 SOL: {len(matches_near)}")

if matches_grad:
    print("\n--- SAMPLE GRADUATED TRADES ---")
    for t in matches_grad[:10]:
        m = t.get("mint", "")[:12]
        rule = t.get("rule", "")
        net = t.get("net_SOL", 0.0)
        entry_t = t.get("entry_time", 0)
        exit_r = t.get("exit_reason", "")
        print(f"Mint: {m}... | Rule: {rule} | Net SOL: {net:+.4f} | Exit reason: {exit_r}")
