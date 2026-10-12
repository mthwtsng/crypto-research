import json

with open("scratch/graduated_tokens.json") as f:
    grad_data = json.load(f)
grad_mints = {t["mint"]: t for t in grad_data["graduated"]}
near_mints = {t["mint"]: t for t in grad_data["near_grad"]}

with open("research/bot_edge_gap_20261006/POOLED_FUNDED_RESULTS.json") as f:
    res = json.load(f)
c85 = res[2]
trace_mints = [tk[0] for tk in c85["trace_keys"]]

print(f"Total candidate entered mints: {len(trace_mints)}")
grad_hits = [m for m in trace_mints if m in grad_mints]
near_hits = [m for m in trace_mints if m in near_mints]

print(f"Mints that reached 84 SOL graduation: {len(grad_hits)}")
for m in grad_hits:
    info = grad_mints[m]
    print(f"  Graduated: {m[:12]}... (Max SOL: {info['max_sol']:.2f}, Complete: {info['complete']})")

print(f"Mints that reached 50-83 SOL: {len(near_hits)}")
for m in near_hits:
    info = near_mints[m]
    print(f"  Near grad: {m[:12]}... (Max SOL: {info['max_sol']:.2f})")
