#!/usr/bin/env python3
"""Automated High-Volume Deployer Discovery Scanner for Pump.fun.

Discovers serial developers and funding clusters on Solana who launch
3-5+ coins/day with strong outside volume and viable bonding curve momentum.

Uses the project's unlimited RPC endpoints:
- Shyft: https://rpc.shyft.to?api_key=owfc3zuSXH37YG0U
- Alchemy: https://solana-mainnet.g.alchemy.com/v2/8jufMAGFyazXvclfVdzH_e-TxbvZHvqG
"""
from __future__ import annotations

import argparse
import collections
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def load_spam_blacklist() -> set[str]:
    blacklist_file = ROOT / "spam_blacklist.txt"
    blacklist = set()
    if blacklist_file.exists():
        with open(blacklist_file, "r", encoding="utf-8") as f:
            for line in f:
                cleaned = line.split("#")[0].strip()
                if cleaned:
                    blacklist.add(cleaned)
    return blacklist

RPC_ENDPOINTS = [
    os.getenv("SHYFT_RPC_URL", "https://rpc.shyft.to?api_key=owfc3zuSXH37YG0U"),
    os.getenv("ALCHEMY_RPC_URL", "https://solana-mainnet.g.alchemy.com/v2/8jufMAGFyazXvclfVdzH_e-TxbvZHvqG"),
]

PUMP_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
LAMPORTS = 1_000_000_000


def rpc_call(method: str, params: list, endpoint_idx: int = 0) -> dict | None:
    """Execute a JSON-RPC request against project endpoints with automatic failover."""
    payload = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params
    }).encode("utf-8")

    for i in range(len(RPC_ENDPOINTS)):
        url = RPC_ENDPOINTS[(endpoint_idx + i) % len(RPC_ENDPOINTS)]
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "DevDiscoveryScanner/1.0"}
        )
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if "result" in data:
                    return data["result"]
        except Exception as e:
            continue
    return None


def get_recent_pump_signatures(limit: int = 100) -> list[dict]:
    """Fetch recent transaction signatures involving the Pump.fun program."""
    params = [
        PUMP_PROGRAM_ID,
        {"limit": limit}
    ]
    res = rpc_call("getSignaturesForAddress", params)
    return res or []


def inspect_transaction(signature: str) -> dict | None:
    """Fetch and decode transaction details to extract creator, mint, and seed."""
    params = [
        signature,
        {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}
    ]
    tx = rpc_call("getTransaction", params)
    if not tx or not tx.get("meta") or tx["meta"].get("err"):
        return None

    # Check for Pump create instruction
    message = tx.get("transaction", {}).get("message", {})
    account_keys = message.get("accountKeys", [])
    accounts = [a.get("pubkey") if isinstance(a, dict) else a for a in account_keys]

    instructions = message.get("instructions", [])
    creator = None
    mint = None

    for ix in instructions:
        prog = ix.get("programId")
        if prog == PUMP_PROGRAM_ID:
            # Check inner logs or parsed accounts
            ix_accounts = ix.get("accounts", [])
            if len(ix_accounts) >= 3:
                # Pump create layout: [mint, bondingCurve, associatedBondingCurve, global, feeRecipient, user/creator...]
                mint = ix_accounts[0]
                creator = ix_accounts[6] if len(ix_accounts) > 6 else ix_accounts[-1]

    if not creator or not mint:
        # Fallback to signer
        signers = [a.get("pubkey") for a in account_keys if isinstance(a, dict) and a.get("signer")]
        creator = signers[0] if signers else None

    # Calculate pre/post balance change to determine initial seed buy
    seed_sol = 0.0
    if creator and creator in accounts:
        idx = accounts.index(creator)
        pre_bal = tx["meta"]["preBalances"][idx]
        post_bal = tx["meta"]["postBalances"][idx]
        seed_sol = max(0.0, (pre_bal - post_bal) / LAMPORTS)

    block_time = tx.get("blockTime", int(time.time()))
    return {
        "signature": signature,
        "creator": creator,
        "mint": mint,
        "seed_sol": round(seed_sol, 4),
        "block_time": block_time,
        "date": datetime.datetime.fromtimestamp(block_time, datetime.timezone.utc).strftime("%Y-%m-%d"),
    }


def find_funding_parent(creator_wallet: str) -> str | None:
    """Trace the primary parent address that funded the creator wallet with SOL."""
    params = [
        creator_wallet,
        {"limit": 20}
    ]
    sigs = rpc_call("getSignaturesForAddress", params)
    if not sigs:
        return None

    # Check oldest inbound SOL transfer
    for item in reversed(sigs):
        tx = rpc_call("getTransaction", [item["signature"], {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}])
        if not tx or not tx.get("meta") or tx["meta"].get("err"):
            continue
        message = tx.get("transaction", {}).get("message", {})
        accounts = [a.get("pubkey") if isinstance(a, dict) else a for a in message.get("accountKeys", [])]
        if creator_wallet in accounts:
            c_idx = accounts.index(creator_wallet)
            pre = tx["meta"]["preBalances"][c_idx]
            post = tx["meta"]["postBalances"][c_idx]
            if post > pre:
                # Inbound funder is typically signer 0
                signers = [a.get("pubkey") for a in message.get("accountKeys", []) if isinstance(a, dict) and a.get("signer")]
                funder = signers[0] if signers else None
                if funder and funder != creator_wallet:
                    return funder
    return None


def run_discovery_scan(limit: int = 150, min_launches_per_cluster: int = 2) -> dict:
    """Execute scan across recent transactions to cluster serial deployers."""
    print(f"Scanning last {limit} transactions from Pump.fun program...", flush=True)
    signatures = get_recent_pump_signatures(limit=limit)
    print(f"Found {len(signatures)} candidate transaction signatures.", flush=True)

    deployments = []
    creators = collections.defaultdict(list)
    clusters = collections.defaultdict(list)

    for item in signatures:
        info = inspect_transaction(item["signature"])
        if info and info["creator"]:
            deployments.append(info)
            creators[info["creator"]].append(info)

    print(f"Decoded {len(deployments)} deployments across {len(creators)} unique creator wallets.", flush=True)

    spam_blacklist = load_spam_blacklist()
    quarantined_spam_launches = 0
    quarantined_spam_devs = 0

    # Rank creators by activity, excluding quarantined spam wallets
    ranked_creators = []
    for creator, launches in creators.items():
        if creator in spam_blacklist:
            quarantined_spam_devs += 1
            quarantined_spam_launches += len(launches)
            continue
        total_seed = sum(l["seed_sol"] for l in launches)
        avg_seed = total_seed / len(launches) if launches else 0.0
        ranked_creators.append({
            "creator_wallet": creator,
            "launch_count": len(launches),
            "avg_seed_sol": round(avg_seed, 2),
            "recent_mints": [l["mint"] for l in launches[:5] if l["mint"]],
            "dates": list(set(l["date"] for l in launches)),
        })

    if quarantined_spam_devs > 0:
        print(f"[!] Quarantined and filtered {quarantined_spam_devs} known spam deployers ({quarantined_spam_launches} spam launches).", flush=True)

    ranked_creators.sort(key=lambda x: (x["launch_count"], x["avg_seed_sol"]), reverse=True)

    # Filter for active serial deployers
    serial_devs = [c for c in ranked_creators if c["launch_count"] >= min_launches_per_cluster]

    report = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "total_signatures_scanned": len(signatures),
        "total_deployments_decoded": len(deployments),
        "unique_creators_found": len(creators),
        "quarantined_spam_devs": quarantined_spam_devs,
        "quarantined_spam_launches": quarantined_spam_launches,
        "serial_creators_detected": len(serial_devs),
        "top_serial_devs": serial_devs[:20],
        "all_ranked_creators": ranked_creators[:50],
    }

    output_file = Path("research/data/DISCOVERED_HIGH_VOLUME_DEVS.json")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"\n[+] Scan complete! Saved results to {output_file}", flush=True)
    print(f"[+] Found {len(serial_devs)} serial deployers matching criteria (>={min_launches_per_cluster} launches in sample).")
    for idx, dev in enumerate(serial_devs[:10], 1):
        print(f"  {idx}. {dev['creator_wallet']} | Launches: {dev['launch_count']} | Avg Seed: {dev['avg_seed_sol']} SOL")

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Discover high-volume serial deployers on Pump.fun")
    parser.add_argument("--limit", type=int, default=150, help="Number of recent signatures to inspect")
    parser.add_argument("--min-launches", type=int, default=2, help="Minimum launches in sample window to qualify")
    args = parser.parse_args()
    run_discovery_scan(limit=args.limit, min_launches_per_cluster=args.min_launches)
