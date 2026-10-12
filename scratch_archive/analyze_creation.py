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

def fetch_tx(sig):
    return rpc_call("getTransaction", [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}])

def main():
    cache_dir = "scratch/rkjc_cache"
    os.makedirs(cache_dir, exist_ok=True)
    with open(f"{cache_dir}/signatures.json") as f:
        sigs = json.load(f)

    sigs_chrono = list(reversed(sigs))
    print(f"Total signatures: {len(sigs_chrono)}")

    # 1. Inspect first 20 transactions in detail (Slot 455953385)
    first_20_file = f"{cache_dir}/first_20_txs.json"
    if os.path.exists(first_20_file):
        with open(first_20_file) as f:
            first_20 = json.load(f)
    else:
        first_20 = []
        with ThreadPoolExecutor(max_workers=10) as exe:
            futures = {exe.submit(fetch_tx, s["signature"]): idx for idx, s in enumerate(sigs_chrono[:20])}
            results = {}
            for fut in as_completed(futures):
                idx = futures[fut]
                results[idx] = fut.result()
        first_20 = [results[i] for i in range(20)]
        with open(first_20_file, "w") as f:
            json.dump(first_20, f, indent=2)

    print("\n--- ANALYSIS OF FIRST 20 TRANSACTIONS (SLOT 0) ---")
    creation_tx = first_20[0]
    print(f"Creation Tx: {sigs_chrono[0]['signature']}")
    if creation_tx:
        msg = creation_tx["transaction"]["message"]
        signers = [a["pubkey"] for a in msg["accountKeys"] if a.get("signer")]
        print(f"Signers: {signers}")
        meta = creation_tx.get("meta", {})
        pre_bal = meta.get("preBalances", [])
        post_bal = meta.get("postBalances", [])
        print(f"Pre/Post SOL: {pre_bal[0]/1e9:.4f} -> {post_bal[0]/1e9:.4f} (diff: {(post_bal[0]-pre_bal[0])/1e9:.4f})")
        # Check token balances
        for tb in meta.get("postTokenBalances", []):
            if tb.get("mint") == MINT:
                print(f"Post Token Balance: owner={tb.get('owner')} amount={tb.get('uiTokenAmount', {}).get('uiAmountString')}")

    # Inspect all transactions in slot 455953385
    slot_0_count = sum(1 for s in sigs_chrono if s["slot"] == sigs_chrono[0]["slot"])
    print(f"\nTotal transactions in creation slot {sigs_chrono[0]['slot']}: {slot_0_count}")

    # Check transactions in slot 0
    for idx, tx in enumerate(first_20):
        if not tx:
            continue
        sig = sigs_chrono[idx]["signature"]
        slot = tx["slot"]
        msg = tx["transaction"]["message"]
        signers = [a["pubkey"] for a in msg["accountKeys"] if a.get("signer")]
        meta = tx.get("meta", {})
        err = meta.get("err")
        logs = meta.get("logMessages", [])
        action = "other"
        for log in logs:
            if "Instruction: Create" in log:
                action = "CREATE"
            elif "Instruction: Buy" in log:
                action = "BUY"
            elif "Instruction: Sell" in log:
                action = "SELL"
        
        # Token balance changes
        post_tb = {tb.get("owner"): float(tb.get("uiTokenAmount", {}).get("uiAmountString", 0) or 0) for tb in meta.get("postTokenBalances", []) if tb.get("mint") == MINT}
        pre_tb = {tb.get("owner"): float(tb.get("uiTokenAmount", {}).get("uiAmountString", 0) or 0) for tb in meta.get("preTokenBalances", []) if tb.get("mint") == MINT}
        delta_tokens = {}
        for o in set(post_tb) | set(pre_tb):
            d = post_tb.get(o, 0) - pre_tb.get(o, 0)
            if abs(d) > 0.01:
                delta_tokens[o] = d

        # SOL change for signers
        pre_bal = meta.get("preBalances", [0])[0] / 1e9
        post_bal = meta.get("postBalances", [0])[0] / 1e9
        sol_diff = post_bal - pre_bal

        print(f"Tx {idx:2d} (slot {slot}) | Signer: {signers[0][:10]}... | Action: {action} | SOL diff: {sol_diff:+.4f} | Token deltas: {delta_tokens} | err: {err is not None}")

if __name__ == "__main__":
    main()
