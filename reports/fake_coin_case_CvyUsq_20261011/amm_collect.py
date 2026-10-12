#!/usr/bin/env python3
"""Bounded, read-only RPC collector for the CvyUsq PumpSwap pool case.

Reads the project RPC URLs from AGENTS.md without printing or persisting them.
The default signature-history cap is three pages of 1,000; transaction fetches
are limited to 400 and use at most four concurrent requests.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
POOL = "EjzRfGWpvRSqmayWnHT3WkKp63jXAzZwhEUVNkwapwdr"
BASE_VAULT = "F1FNLwTSUvHKjbhbt3vQxkgvLThtka3uXKThMtB16wRm"
QUOTE_VAULT = "HxYqEmJfdwT51M3bNgw11xFYTByM2yBjnqyqQ8pqCuPt"
MINT = "CvyUsq67bCiZZwr1dZKu2y1HXojjrz6tvdkKY4XGpump"
OPENING_TS = 1791761074
PAGE_SIZE = 1000
MAX_PAGES = 3
MAX_TX = 400


class RpcFailure(RuntimeError):
    pass


def get_urls() -> list[str]:
    text = (ROOT / "AGENTS.md").read_text()
    urls = re.findall(r"`(https://[^`]+)`", text)
    if len(urls) < 2:
        raise RpcFailure("could not read both configured RPC endpoints")
    return urls[:2]


def rpc(url: str, method: str, params: list, req_id: int = 1):
    body = json.dumps({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=35) as response:
            payload = json.loads(response.read())
    except Exception as exc:
        code = getattr(exc, "code", None)
        detail = f"HTTP {code}" if code is not None else type(exc).__name__
        raise RpcFailure(f"{method} transport failure ({detail})") from None
    if payload.get("error"):
        error = payload["error"]
        raise RpcFailure(f"{method} RPC error {error.get('code')}: {str(error.get('message', ''))[:180]}")
    return payload.get("result")


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def collect_signatures() -> dict:
    urls = get_urls()
    endpoint = urls[0]
    pages = []
    before = None
    stop_reason = "page_cap"
    for page_no in range(1, MAX_PAGES + 1):
        config = {"limit": PAGE_SIZE, "commitment": "finalized"}
        if before:
            config["before"] = before
        result = rpc(endpoint, "getSignaturesForAddress", [POOL, config], page_no)
        if not isinstance(result, list):
            raise RpcFailure("signature response was not a list")
        pages.append(result)
        if not result:
            stop_reason = "empty_page"
            break
        before = result[-1]["signature"]
        oldest_time = result[-1].get("blockTime")
        if oldest_time is not None and oldest_time < OPENING_TS:
            stop_reason = "reached_before_pool_open"
            break
        if len(result) < PAGE_SIZE:
            stop_reason = "history_exhausted"
            break
    flattened = [sig for page in pages for sig in page]
    # Do not silently accept duplicate pagination rows.
    unique = {s["signature"]: s for s in flattened}
    ordered = list(unique.values())
    record = {
        "network": "solana-mainnet",
        "fetched_at_utc": utc_now(),
        "rpc_source": "AGENTS.md Shyft primary endpoint",
        "address": POOL,
        "page_size": PAGE_SIZE,
        "max_pages": MAX_PAGES,
        "pages_returned": [len(p) for p in pages],
        "stop_reason": stop_reason,
        "opening_timestamp_utc": dt.datetime.fromtimestamp(OPENING_TS, dt.timezone.utc).isoformat(),
        "opening_timestamp_unix": OPENING_TS,
        "unique_signature_count": len(ordered),
        "successful_count": sum(s.get("err") is None for s in ordered),
        "failed_count": sum(s.get("err") is not None for s in ordered),
        "oldest_block_time_unix": min((s.get("blockTime") for s in ordered if s.get("blockTime") is not None), default=None),
        "newest_block_time_unix": max((s.get("blockTime") for s in ordered if s.get("blockTime") is not None), default=None),
        "covers_opening_time": min((s.get("blockTime") for s in ordered if s.get("blockTime") is not None), default=10**20) <= OPENING_TS,
        "signatures": ordered,
    }
    (OUT / "amm_pool_signatures.json").write_text(json.dumps(record, separators=(",", ":")) + "\n")
    return record


def fetch_one(args):
    urls, index, sig = args
    params = [sig, {"encoding": "jsonParsed", "commitment": "finalized", "maxSupportedTransactionVersion": 1}]
    try:
        return sig, rpc(urls[0], "getTransaction", params, index + 1), "Shyft"
    except RpcFailure:
        # Retry provider-level gaps against the configured Alchemy endpoint.
        return sig, rpc(urls[1], "getTransaction", params, index + 1), "Alchemy"


def collect_transactions(signatures_path: Path, selected_path: Path) -> dict:
    source = json.loads(signatures_path.read_text())
    selected = json.loads(selected_path.read_text())
    wanted = selected.get("signatures", [])
    if len(wanted) > MAX_TX:
        raise RpcFailure(f"selection exceeds transaction cap {MAX_TX}")
    available = {s["signature"]: s for s in source["signatures"]}
    if any(sig not in available for sig in wanted):
        raise RpcFailure("selection includes a signature outside the collected pages")
    successful = [sig for sig in wanted if available[sig].get("err") is None]
    urls = get_urls()
    results = {}
    providers = {}
    failures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(fetch_one, (urls, i, sig)): sig for i, sig in enumerate(successful)}
        for future in concurrent.futures.as_completed(futures):
            sig = futures[future]
            try:
                _, tx, provider = future.result()
                results[sig] = tx
                providers[sig] = provider
            except Exception as exc:
                failures.append({"signature": sig, "error": str(exc)[:240]})
    payload = {
        "network": source["network"],
        "fetched_at_utc": utc_now(),
        "rpc_source": source["rpc_source"],
        "encoding": "jsonParsed",
        "max_supported_transaction_version": 1,
        "commitment": "finalized",
        "requested_count": len(wanted),
        "successful_requested_count": len(successful),
        "returned_count": sum(tx is not None for tx in results.values()),
        "null_count": sum(tx is None for tx in results.values()),
        "provider_counts": {name: sum(value == name for value in providers.values()) for name in ("Shyft", "Alchemy")},
        "rpc_failures": failures,
        "transactions": results,
    }
    (OUT / "amm_pool_transactions.json").write_text(json.dumps(payload, separators=(",", ":")) + "\n")
    return payload


def repair_missing() -> dict:
    path = OUT / "amm_pool_transactions.json"
    payload = json.loads(path.read_text())
    urls = get_urls()
    missing = [item["signature"] for item in payload.get("rpc_failures", [])]
    still_missing = []
    repaired = 0
    for index, sig in enumerate(missing):
        try:
            tx = rpc(urls[1], "getTransaction", [sig, {"encoding": "jsonParsed", "commitment": "finalized", "maxSupportedTransactionVersion": 1}], index + 1)
            payload["transactions"][sig] = tx
            payload.setdefault("provider_counts", {}).setdefault("Alchemy", 0)
            payload["provider_counts"]["Alchemy"] += 1
            repaired += 1
        except RpcFailure as exc:
            still_missing.append({"signature": sig, "error": str(exc)[:240]})
        time.sleep(0.35)
    payload["rpc_failures"] = still_missing
    payload["returned_count"] = sum(tx is not None for tx in payload["transactions"].values())
    payload["null_count"] = sum(tx is None for tx in payload["transactions"].values())
    payload["repair_fetched_at_utc"] = utc_now()
    payload["repair_source"] = "AGENTS.md Alchemy fallback endpoint"
    payload["repair_attempted_count"] = len(missing)
    payload["repair_success_count"] = repaired
    path.write_text(json.dumps(payload, separators=(",", ":")) + "\n")
    return payload


def collect_current_state() -> dict:
    urls = get_urls()
    pubkeys = [BASE_VAULT, QUOTE_VAULT, MINT]
    options = {"encoding": "jsonParsed", "commitment": "finalized"}
    source = "Shyft"
    try:
        result = rpc(urls[0], "getMultipleAccounts", [pubkeys, options])
    except RpcFailure:
        result = rpc(urls[1], "getMultipleAccounts", [pubkeys, options])
        source = "Alchemy"
    values = result.get("value") or []
    if len(values) != 3 or any(v is None for v in values):
        raise RpcFailure("one or more pool state accounts were unavailable")
    def parsed_info(value):
        return value.get("data", {}).get("parsed", {}).get("info", {})
    base_info, quote_info, mint_info = map(parsed_info, values)
    payload = {
        "network": "solana-mainnet",
        "observed_at_utc": utc_now(),
        "rpc_source": f"AGENTS.md {source} primary/fallback endpoint",
        "commitment": "finalized",
        "context_slot": result.get("context", {}).get("slot"),
        "pool": POOL,
        "mint": MINT,
        "base_vault": BASE_VAULT,
        "quote_vault": QUOTE_VAULT,
        "base_reserve_raw": base_info.get("tokenAmount", {}).get("amount"),
        "base_decimals": base_info.get("tokenAmount", {}).get("decimals"),
        "quote_reserve_raw": quote_info.get("tokenAmount", {}).get("amount"),
        "quote_decimals": quote_info.get("tokenAmount", {}).get("decimals"),
        "base_supply_raw": mint_info.get("supply"),
        "supply_decimals": mint_info.get("decimals"),
    }
    (OUT / "amm_current_pool_state.json").write_text(json.dumps(payload, separators=(",", ":")) + "\n")
    return payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("signatures", "transactions", "repair", "snapshot"))
    parser.add_argument("--selection", type=Path, help="JSON containing a signatures array")
    args = parser.parse_args()
    try:
        if args.mode == "signatures":
            result = collect_signatures()
            print(json.dumps({k: result[k] for k in result if k != "signatures"}, indent=2))
        elif args.mode == "transactions":
            if not args.selection:
                parser.error("--selection is required in transactions mode")
            result = collect_transactions(OUT / "amm_pool_signatures.json", args.selection)
            summary = {k: v for k, v in result.items() if k not in ("transactions", "rpc_failures")}
            summary["rpc_failure_count"] = len(result["rpc_failures"])
            print(json.dumps(summary, indent=2))
        elif args.mode == "repair":
            result = repair_missing()
            print(json.dumps({k: result[k] for k in ("repair_fetched_at_utc", "repair_source", "repair_attempted_count", "repair_success_count", "returned_count", "null_count")}, indent=2))
        else:
            result = collect_current_state()
            print(json.dumps(result, indent=2))
    except RpcFailure as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
