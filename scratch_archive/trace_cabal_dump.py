import os
import sys
import json
import time
import requests
from collections import defaultdict

MINT = "RkjcLPAtjbKUXSi7Ln9RpaCr2qyzD8rFv9jiNEMpump"
ALCHEMY_RPC = "https://solana-mainnet.g.alchemy.com/v2/8jufMAGFyazXvclfVdzH_e-TxbvZHvqG"
SHYFT_RPC = "https://rpc.shyft.to?api_key=owfc3zuSXH37YG0U"

CABAL_WALLETS = {
    "BDQt8y8vpuPUwfj2zK9X9zvDtw8Ar3QnqDVsJp534ARj": "Dev Creator",
    "7erX79DLCvP1JWXBb9ZDQtC5vVCJQHqmwc24KYZmNTr3": "Bundle Signer 1 / Holder",
    "5KeWW1WafpEX17p7pfV2uDCbxS5TFPf9pnG8A2qoMgcN": "Bundle Sybil 1A",
    "9yofrgbqZdef45f3frXp1cAnXqGouqXQHArj57rLkt9d": "Bundle Sybil 1B",
    "G1LMaGQ6eTT2A27Xuw5v31bDkHBJqdhd5sxw5qmrqUCJ": "Bundle Sybil 1C",
    "7qigJDiUmsUskTjgqa3mtk4frMN4EqauESGBL2Vz7tin": "Bundle Signer 2 / Holder",
    "2KTXftK6FEmzw8p6Vn3eJzJpPEExb1bPrX4WB3y8Ap8g": "Bundle Sybil 2A",
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

def main():
    print("Tracing cabal wallets on-chain...")

    # 1. Check current token balances of cabal wallets
    token_balances = {}
    sol_balances = {}
    for addr, label in CABAL_WALLETS.items():
        # SOL balance
        sol_res = rpc_call("getBalance", [addr])
        sol_balances[addr] = sol_res.get("value", 0) / 1e9 if sol_res else 0

        # Token accounts by owner
        token_res = rpc_call("getTokenAccountsByOwner", [addr, {"mint": MINT}, {"encoding": "jsonParsed"}])
        tokens = 0
        if token_res and "value" in token_res:
            for acc in token_res["value"]:
                info = acc["account"]["data"]["parsed"]["info"]
                tokens += float(info["tokenAmount"]["uiAmountString"] or 0)
        token_balances[addr] = tokens

    print("\n--- CURRENT CABAL BALANCES ---")
    for addr, label in CABAL_WALLETS.items():
        print(f"{label} ({addr[:10]}...): Tokens Held = {token_balances[addr]:,.2f} | SOL Balance = {sol_balances[addr]:.4f}")

    # 2. Check signatures for each cabal wallet to see their sales
    print("\n--- CABAL SALES / DUMPS ---")
    for addr, label in CABAL_WALLETS.items():
        sigs = rpc_call("getSignaturesForAddress", [addr, {"limit": 20}])
        print(f"\n{label} ({addr}): {len(sigs or [])} signatures")
        if not sigs:
            continue
        for s in sigs:
            tx = rpc_call("getTransaction", [s["signature"], {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}])
            if not tx:
                continue
            meta = tx.get("meta", {})
            logs = meta.get("logMessages", [])
            # check token balance delta for addr
            pre_tb = {tb.get("owner"): float(tb.get("uiTokenAmount", {}).get("uiAmountString", 0) or 0) for tb in meta.get("preTokenBalances", []) if tb.get("mint") == MINT}
            post_tb = {tb.get("owner"): float(tb.get("uiTokenAmount", {}).get("uiAmountString", 0) or 0) for tb in meta.get("postTokenBalances", []) if tb.get("mint") == MINT}
            d_tok = post_tb.get(addr, 0) - pre_tb.get(addr, 0)
            if abs(d_tok) > 1.0:
                # check sol delta
                sol_delta = 0
                acc_keys = [a["pubkey"] for a in tx["transaction"]["message"]["accountKeys"]]
                if addr in acc_keys:
                    idx = acc_keys.index(addr)
                    sol_delta = (meta.get("postBalances", [])[idx] - meta.get("preBalances", [])[idx]) / 1e9
                print(f"  Slot {tx['slot']} | Sig: {s['signature'][:20]}... | Token Delta: {d_tok:,.2f} | SOL Delta: {sol_delta:+.4f} SOL")

    # 3. Check largest current holders of MINT
    print("\n--- TOP CURRENT TOKEN HOLDERS ---")
    holders_res = rpc_call("getTokenLargestAccounts", [MINT])
    if holders_res and "value" in holders_res:
        for idx, h in enumerate(holders_res["value"][:15]):
            addr = h["address"]
            amt = float(h.get("uiAmountString") or 0)
            pct = (amt / 1_000_000_000) * 100
            print(f"  Top {idx+1}: {addr} | Amount: {amt:,.2f} ({pct:.2f}%)")

if __name__ == "__main__":
    main()
