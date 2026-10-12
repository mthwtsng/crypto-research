import gzip, json

with open("scratch/graduated_tokens.json") as f:
    grad_data = json.load(f)
grad_mints = {t["mint"]: t for t in grad_data["graduated"]}

print("=== INSPECTING THE 57 GRADUATING TRADES OF 8tpkr_fixed_05 ===")

# We look up their rows in own_trade_replacement_v3 or CANDIDATE_TRADES / REPLAY_TRADES
# Let's inspect EXIT_PATH_LABELS.jsonl.gz for 8tpkr_fixed_05
grad_trades = []
with gzip.open("research/multi_timeframe_audit_20261005/own_trade_replacement_v3/EXIT_PATH_LABELS.jsonl.gz", "rt") as f:
    for line in f:
        row = json.loads(line)
        if row.get("rule") == "8tpkr_fixed_05" and row.get("scenario") == "central85":
            mint = row.get("mint")
            if mint in grad_mints:
                grad_trades.append(row)

print(f"Loaded {len(grad_trades)} 8tpkr central85 trades on graduated tokens.")

total_realized_pnl = 0.0
total_mfe_potential = 0.0
exit_seconds = []

for t in grad_trades:
    pnl = t.get("pnl", 0.0)
    mfe = t.get("observed_mfe", 0.0)
    dur = t.get("last_exit_seconds")
    dur_val = dur if dur is not None else 999
    total_realized_pnl += pnl
    total_mfe_potential += 0.5 * mfe
    exit_seconds.append(dur_val)

valid_durs = [d for d in exit_seconds if d != 999]
avg_dur = sum(valid_durs) / len(valid_durs) if valid_durs else 0

print(f"\nRealized Net SOL under legacy exits: {total_realized_pnl:+.4f} SOL")
print(f"Max MFE Potential (0.5 ticket * MFE):  {total_mfe_potential:+.4f} SOL")
print(f"Average Hold Duration:               {avg_dur:.1f} seconds")
print(f"Exit Durations: Min={min(exit_seconds)}s, Median={sorted(exit_seconds)[len(exit_seconds)//2]}s, Max={max(exit_seconds)}s")

print("\n--- SAMPLE GRADUATED 8TPKR TRADES ---")
for t in grad_trades[:15]:
    m = t["mint"][:12]
    pnl = t.get("pnl", 0.0)
    mfe = t.get("observed_mfe", 0.0)
    dur = t.get("last_exit_seconds", 0)
    tags = t.get("tags", [])
    print(f"Mint: {m}... | Dur: {dur:2d}s | Realized PnL: {pnl:+.4f} SOL | MFE: {mfe*100:+6.1f}% | Tags: {tags[:2]}")
