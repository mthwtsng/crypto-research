import os
import sys
import json
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

MINT = "RkjcLPAtjbKUXSi7Ln9RpaCr2qyzD8rFv9jiNEMpump"
ALCHEMY_RPC = "https://solana-mainnet.g.alchemy.com/v2/8jufMAGFyazXvclfVdzH_e-TxbvZHvqG"
SHYFT_RPC = "https://rpc.shyft.to?api_key=owfc3zuSXH37YG0U"

TRACKED_WALLETS = {
    "88887QrRZPZmsstEXsoXXB8E7nbmUDde4Gp5s7jG3ENu": "Real Coin Bot (18 real coins)",
    "4FpuSLX6TLffEk9U9jQ9pwbwd4Aw2NCRBFZYQdf4X4Uk": "Real Coin Bot (18 real coins)",
    "8bXQt4YVBjE3EE7cFAFjcJVbZ7tgAqK3AfCQmX18aYh2": "Real Coin Bot (18 real coins)",
}

def rpc_call(method, params, rpc=ALCHEMY_RPC, retries=5):
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    for attempt in range(retries):
        try:
            r = requests.post(rpc, json=payload, timeout=12)
            if r.status_code == 200:
                res = r.json()
                if "result" in res:
                    return res["result"]
            time.sleep(0.2 * (attempt + 1))
        except Exception:
            time.sleep(0.3 * (attempt + 1))
    if rpc == ALCHEMY_RPC:
        return rpc_call(method, params, rpc=SHYFT_RPC, retries=3)
    return None

def check_address_signatures(addr):
    print(f"Fetching signatures for tracked wallet {addr}...")
    res = rpc_call("getSignaturesForAddress", [addr, {"limit": 100}])
    return res or []

def main():
    # Check signatures for the 3 tracked wallets
    for addr, label in TRACKED_WALLETS.items():
        sigs = check_address_signatures(addr)
        print(f"\nWallet {addr} ({label}): {len(sigs)} recent signatures")
        found = []
        for s in sigs:
            # Check if this tx involves MINT
            sig = s["signature"]
            tx = rpc_call("getTransaction", [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}])
            if not tx:
                continue
            accs = [a["pubkey"] for a in tx["transaction"]["message"]["accountKeys"]]
            if MINT in accs:
                found.append((s, tx))
                print(f"  -> FOUND TX for {MINT}: {sig} at slot {s['slot']}")
        print(f"Total mint matches for {addr}: {len(found)}")

        for s, tx in found:
            meta = tx.get("meta", {})
            logs = meta.get("logMessages", [])
            print(f"Tx Details: {s['signature']}")
            print(f"Slot: {tx['slot']} BlockTime: {tx.get('blockTime')}")
            for l in logs:
                if "Instruction:" in l or "Program data:" in l:
                    print(f"  {l}")
            for tb in meta.get("postTokenBalances", []):
                if tb.get("mint") == MINT:
                    print(f"  Post token: owner={tb.get('owner')} amount={tb.get('uiTokenAmount', {}).get('uiAmountString')}")

if __name__ == "__main__":
    main()
