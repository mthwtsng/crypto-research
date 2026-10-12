import gzip, json
from collections import defaultdict

with open("scratch/graduated_tokens.json") as f:
    grad_data = json.load(f)

grad_mints = {t["mint"]: t for t in grad_data["graduated"]}
near_mints = {t["mint"]: t for t in grad_data["near_grad"]}

print(f"Loaded {len(grad_mints)} graduated mints and {len(near_mints)} near-grad mints.")

# Inspect EXIT_PATH_LABELS.jsonl.gz
by_rule = defaultdict(lambda: {"total": 0, "grad_entries": 0, "near_grad_entries": 0, "mfes": [], "pnls": []})

with gzip.open("research/multi_timeframe_audit_20261005/own_trade_replacement_v3/EXIT_PATH_LABELS.jsonl.gz", "rt") as f:
    for line in f:
        row = json.loads(line)
        if row.get("scenario") != "central85":
            continue
        rule = row.get("rule")
        mint = row.get("mint")
        mfe = row.get("observed_mfe", 0.0)
        pnl = row.get("pnl", 0.0)
        
        by_rule[rule]["total"] += 1
        if mint in grad_mints:
            by_rule[rule]["grad_entries"] += 1
            by_rule[rule]["mfes"].append(mfe)
            by_rule[rule]["pnls"].append(pnl)
        elif mint in near_mints:
            by_rule[rule]["near_grad_entries"] += 1

print("\n=== PRE-MIGRATION STRATEGY ENTRIES INTO GRADUATING TOKENS ===")
print(f"{'Strategy':32} | {'Total Entries':13} | {'Graduated':10} | {'Near-Grad':10} | {'Grad Win Rate':13} | {'Avg MFE on Grad':15}")
print("-" * 105)

for rule, st in sorted(by_rule.items()):
    tot = st["total"]
    g_cnt = st["grad_entries"]
    ng_cnt = st["near_grad_entries"]
    mfes = st["mfes"]
    pnls = st["pnls"]
    
    win_rate = (sum(1 for p in pnls if p > 0) / len(pnls) * 100) if pnls else 0.0
    avg_mfe = (sum(mfes) / len(mfes) * 100) if mfes else 0.0
    
    print(f"{rule:32} | {tot:13d} | {g_cnt:10d} | {ng_cnt:10d} | {win_rate:12.1f}% | {avg_mfe:+14.1f}%")
