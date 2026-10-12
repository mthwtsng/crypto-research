import os
import sys
import json
import time
import base64
import struct
import requests
from collections import defaultdict, Counter

MINT = "RkjcLPAtjbKUXSi7Ln9RpaCr2qyzD8rFv9jiNEMpump"
PUMP_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
PUMPSWAP_PROGRAM = "pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ"

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
            r = requests.post(rpc, json=payload, timeout=15)
            if r.status_code == 200:
                res = r.json()
                if "result" in res:
                    return res["result"]
                elif "error" in res:
                    # if rate limit or error, retry
                    pass
            time.sleep(0.25 * (attempt + 1))
        except Exception as e:
            time.sleep(0.35 * (attempt + 1))
    if rpc == ALCHEMY_RPC:
        return rpc_call(method, params, rpc=SHYFT_RPC, retries=3)
    return None

def get_all_signatures(mint):
    print(f"Fetching all signatures for mint {mint}...")
    signatures = []
    before = None
    while True:
        params = [mint, {"limit": 1000}]
        if before:
            params[1]["before"] = before
        res = rpc_call("getSignaturesForAddress", params)
        if not res:
            break
        signatures.extend(res)
        print(f"  Fetched {len(signatures)} signatures so far...")
        if len(res) < 1000:
            break
        before = res[-1]["signature"]
    return signatures

def main():
    os.makedirs("scratch/rkjc_cache", exist_ok=True)
    cache_sigs = "scratch/rkjc_cache/signatures.json"
    if os.path.exists(cache_sigs):
        with open(cache_sigs) as f:
            sigs = json.load(f)
    else:
        sigs = get_all_signatures(MINT)
        with open(cache_sigs, "w") as f:
            json.dump(sigs, f, indent=2)
    print(f"Total signatures found: {len(sigs)}")

    # Sort chronological (oldest first)
    # getSignaturesForAddress returns newest first
    sigs_chronological = list(reversed(sigs))

    print("\n--- 1. FIRST 10 SIGNATURES (CREATION & INITIAL SLOTS) ---")
    for idx, s in enumerate(sigs_chronological[:10]):
        print(f"{idx}: sig={s['signature']} slot={s['slot']} blockTime={s.get('blockTime')} err={s.get('err')}")

    print("\n--- 2. LAST 10 SIGNATURES (LATEST ACTIVITY) ---")
    for idx, s in enumerate(sigs_chronological[-10:]):
        print(f"{idx}: sig={s['signature']} slot={s['slot']} blockTime={s.get('blockTime')} err={s.get('err')}")

if __name__ == "__main__":
    main()
