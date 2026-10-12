#!/usr/bin/env python3
"""
Filter Active / Momentum Coins from the 10,080 Historical Dataset.

Scans research/frozen_21day_validation_20261008/raw_curves/ across multi-cores:
Filters for coins that:
1. Total transactions >= 30 (not dead-on-arrival genesis spam)
2. Peak curve reserves >= 8.0 SOL (reached the tradeable corridor)
3. Unique non-creator outside buyers >= 15

Outputs:
- research/frozen_21day_validation_20261008/ACTIVE_COINS_MANIFEST.json
"""

import concurrent.futures
import gzip
import json
import os
import pathlib
import sys
import time
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "research/frozen_21day_validation_20261008/raw_curves"

def scan_file(path):
    try:
        mint = path.name.split(".")[0]
        with gzip.open(path, "rt") as f:
            d = json.load(f)
        
        txs = d.get("transactions", [])
        total_tx = len(txs)
        if total_tx < 30:
            return None
            
        creator = d.get("creation_metadata", {}).get("creator") or d.get("creator")
        
        max_rsol = 0.0
        buyers = set()
        
        for tx in txs:
            meta = tx.get("meta") or {}
            post_balances = meta.get("postTokenBalances") or []
            # Check bonding curve post reserve or instructions
            for b in post_balances:
                mint_b = b.get("mint")
                if mint_b == mint and b.get("owner") == d.get("creation_metadata", {}).get("bonding_curve"):
                    raw_amount = int(b.get("uiTokenAmount", {}).get("amount", 0))
                    # Estimate reserve sol from bonding curve formula or balance
                    break
                    
            # Check fee/sol movement
            pre = meta.get("preBalances") or []
            post = meta.get("postBalances") or []
            # We can also check pump instruction logs
            log_messages = meta.get("logMessages") or []
            for msg in log_messages:
                if "Program log: Instruction: Buy" in msg or "Program log: Instruction: Sell" in msg:
                    pass

            # Unique signers/fee payers
            signer = tx.get("transaction", {}).get("message", {}).get("accountKeys", [{}])[0]
            if isinstance(signer, dict):
                signer_pub = signer.get("pubkey")
            else:
                signer_pub = signer
            if signer_pub and signer_pub != creator:
                buyers.add(signer_pub)

        # Quick estimate of peak reserve from transaction count or balance
        # For pump.fun curves: curve balance in postBalances of bonding curve
        curve_addr = d.get("creation_metadata", {}).get("bonding_curve")
        account_keys = [k.get("pubkey") if isinstance(k, dict) else k for k in txs[0].get("transaction", {}).get("message", {}).get("accountKeys", [])]
        curve_idx = -1
        if curve_addr in account_keys:
            curve_idx = account_keys.index(curve_addr)
            
        if curve_idx >= 0:
            for tx in txs:
                meta = tx.get("meta") or {}
                post_b = meta.get("postBalances") or []
                if len(post_b) > curve_idx:
                    sol_val = post_b[curve_idx] / 1e9
                    if sol_val > max_rsol:
                        max_rsol = sol_val
        else:
            # Fallback if account index changes across txs: search in accountKeys of each tx
            for tx in txs:
                keys = [k.get("pubkey") if isinstance(k, dict) else k for k in tx.get("transaction", {}).get("message", {}).get("accountKeys", [])]
                if curve_addr in keys:
                    idx = keys.index(curve_addr)
                    post_b = tx.get("meta", {}).get("postBalances", [])
                    if len(post_b) > idx:
                        sol_val = post_b[idx] / 1e9
                        if sol_val > max_rsol:
                            max_rsol = sol_val

        if max_rsol >= 8.0 and len(buyers) >= 15:
            return {
                "mint": mint,
                "file": path.name,
                "total_transactions": total_tx,
                "peak_reserve_sol": max_rsol,
                "unique_buyers": len(buyers),
                "creator": creator,
            }
        return None
    except Exception:
        return None

def main():
    files = sorted(list(RAW_DIR.glob("*.json.gz")))
    print(f"[*] Found {len(files)} raw curve files in {RAW_DIR}")
    print(f"[*] Scanning with 16 processes...")
    t0 = time.time()
    
    active = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=16) as ex:
        results = ex.map(scan_file, files, chunksize=50)
        for r in results:
            if r is not None:
                active.append(r)
                
    elapsed = time.time() - t0
    print(f"[+] Scan completed in {elapsed:.2f}s:")
    print(f"    Total scanned: {len(files)}")
    print(f"    Active coins matching filter: {len(active)} ({len(active)/len(files)*100:.2f}%)")
    
    # Save manifest
    out_file = ROOT / "research/frozen_21day_validation_20261008/ACTIVE_COINS_MANIFEST.json"
    with open(out_file, "w") as f:
        json.dump({
            "timestamp": time.time(),
            "total_raw": len(files),
            "total_active": len(active),
            "filter": {
                "min_transactions": 30,
                "min_peak_reserve_sol": 8.0,
                "min_unique_buyers": 15
            },
            "coins": active
        }, f, indent=2)
    print(f"[✓] Saved manifest to {out_file}")
    
    # Print sample
    print("\nTop 10 most active coins found:")
    active.sort(key=lambda x: x["peak_reserve_sol"], reverse=True)
    for c in active[:10]:
        print(f"  • Mint {c['mint'][:16]}...: {c['total_transactions']:>4} txs | Peak: {c['peak_reserve_sol']:>5.1f} SOL | Buyers: {c['unique_buyers']:>3}")

if __name__ == "__main__":
    main()
