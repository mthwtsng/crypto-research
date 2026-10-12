import urllib.request
import json
import time

RPC_URL = "https://solana-mainnet.g.alchemy.com/v2/8jufMAGFyazXvclfVdzH_e-TxbvZHvqG"
MINT = "RkjcLPAtjbKUXSi7Ln9RpaCr2qyzD8rFv9jiNEMpump"

def rpc(method, params):
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(RPC_URL, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())["result"]

print("1. Fetching signatures for mint...")
sigs = rpc("getSignaturesForAddress", [MINT, {"limit": 1000}])
print(f"Total signatures fetched: {len(sigs)}")

creation_sig = sigs[-1]
print(f"Oldest / Creation signature: {creation_sig['signature']} slot={creation_sig['slot']}")

# Look for 4FpuSLX6 transactions
tracked_wallet = "4FpuSLX6TLffEk9U9jQ9pwbwd4Aw2NCRBFZYQdf4X4Uk"
print(f"2. Fetching signatures for tracked wallet {tracked_wallet}...")
tracked_sigs = rpc("getSignaturesForAddress", [tracked_wallet, {"limit": 50}])
print(f"Total signatures for tracked wallet: {len(tracked_sigs)}")

tracked_trades_on_mint = []
for s in tracked_sigs:
    # get tx
    tx = rpc("getTransaction", [s["signature"], {"maxSupportedTransactionVersion": 0, "encoding": "jsonParsed"}])
    if tx:
        # check if mint in accountKeys
        accs = tx["transaction"]["message"]["accountKeys"]
        pubkeys = [a["pubkey"] if isinstance(a, dict) else a for a in accs]
        if MINT in pubkeys:
            tracked_trades_on_mint.append({
                "sig": s["signature"],
                "slot": s["slot"],
                "blockTime": s.get("blockTime"),
            })
            print(f"  -> Found trade on mint: slot={s['slot']} sig={s['signature']}")

print(f"Tracked trades on mint: {len(tracked_trades_on_mint)}")
