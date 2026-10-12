#!/usr/bin/env python3
"""One bounded read-only Solana RPC capture for the DgT6h post-graduation pool."""
from __future__ import annotations

import concurrent.futures
import datetime as dt
import json
import re
import time
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[2]
MINT = "DgT6hpeJzS3yW5UjcUvT4grfXogM1XvMwFKmrU4Vpump"
POOL = "7LAx8jrRB5zXgeH69RXs2FwXjmoXzTUXwfUU1fPrHbpc"
BASE_VAULT = "CXa9yFKacD14aorShxWcL1x7MwGhBG18K6KtQN9nVWge"
QUOTE_VAULT = "DLx6wfCAdH2t9WJ7oUcxYo4A1yFP6Lfh5DmGpbwKU57y"
WSOL = "So11111111111111111111111111111111111111112"
PAGE_SIZE = 1000
MAX_PAGES = 2
TX_CAP = 200
INCIDENT_START = 1791762910  # 23:55:10 UTC, around the first marked reserve break.
INCIDENT_END = 1791762925    # 23:55:25 UTC, includes the first two steep drops.


def urls() -> list[str]:
    found = re.findall(r"`(https://[^`]+)`", (ROOT / "AGENTS.md").read_text())
    if len(found) < 2:
        raise RuntimeError("configured RPC endpoints unavailable")
    return found[:2]


def call(endpoint: str, method: str, params: list, request_id: int = 1):
    body = json.dumps({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}).encode()
    request = urllib.request.Request(endpoint, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read())
    if data.get("error"):
        err = data["error"]
        raise RuntimeError(f"{method} RPC error {err.get('code')}: {str(err.get('message', ''))[:120]}")
    return data.get("result")


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def get_signatures(endpoint: str) -> dict:
    rows = []
    before = None
    page_counts = []
    stop = "page_cap"
    for page in range(1, MAX_PAGES + 1):
        opts = {"limit": PAGE_SIZE, "commitment": "finalized"}
        if before:
            opts["before"] = before
        result = call(endpoint, "getSignaturesForAddress", [POOL, opts], page)
        if not isinstance(result, list):
            raise RuntimeError("signature result was not an array")
        page_counts.append(len(result))
        rows.extend(result)
        if not result:
            stop = "empty_page"
            break
        before = result[-1]["signature"]
        times = [r.get("blockTime") for r in rows if r.get("blockTime") is not None]
        if len(result) < PAGE_SIZE:
            stop = "history_exhausted"
            break
    unique = list({r["signature"]: r for r in rows}.values())
    record = {
        "network": "solana-mainnet", "fetched_at_utc": now(),
        "rpc_source": "AGENTS.md Shyft primary endpoint", "pool": POOL, "mint": MINT,
        "page_size": PAGE_SIZE, "max_pages": MAX_PAGES, "pages_returned": page_counts,
        "stop_reason": stop, "unique_signature_count": len(unique),
        "successful_count": sum(r.get("err") is None for r in unique),
        "failed_count": sum(r.get("err") is not None for r in unique),
        "oldest_block_time_unix": min((r.get("blockTime") for r in unique if r.get("blockTime") is not None), default=None),
        "newest_block_time_unix": max((r.get("blockTime") for r in unique if r.get("blockTime") is not None), default=None),
        "signatures": unique,
    }
    (OUT / "third_amm_pool_signatures.json").write_text(json.dumps(record, separators=(",", ":")) + "\n")
    return record


def state_snapshot(endpoints: list[str]) -> dict:
    keys = [BASE_VAULT, QUOTE_VAULT, MINT]
    options = {"encoding": "jsonParsed", "commitment": "finalized"}
    source = "Shyft"
    try:
        result = call(endpoints[0], "getMultipleAccounts", [keys, options])
    except Exception:
        source = "Alchemy"
        result = call(endpoints[1], "getMultipleAccounts", [keys, options])
    values = result.get("value") or []
    if len(values) != 3 or any(v is None for v in values):
        raise RuntimeError("one or more state accounts unavailable")
    infos = [v.get("data", {}).get("parsed", {}).get("info", {}) for v in values]
    base, quote, mint = infos
    payload = {
        "network": "solana-mainnet", "observed_at_utc": now(),
        "rpc_source": f"AGENTS.md {source} endpoint", "commitment": "finalized",
        "context_slot": result.get("context", {}).get("slot"), "pool": POOL, "mint": MINT,
        "base_vault": BASE_VAULT, "quote_vault": QUOTE_VAULT,
        "base_reserve_raw": (base.get("tokenAmount") or {}).get("amount"),
        "base_decimals": (base.get("tokenAmount") or {}).get("decimals"),
        "quote_reserve_raw": (quote.get("tokenAmount") or {}).get("amount"),
        "quote_decimals": (quote.get("tokenAmount") or {}).get("decimals"),
        "base_supply_raw": mint.get("supply"), "supply_decimals": mint.get("decimals"),
    }
    (OUT / "third_amm_current_pool_state.json").write_text(json.dumps(payload, separators=(",", ":")) + "\n")
    return payload


def fetch_transactions(endpoints: list[str], sigs: dict) -> dict:
    # Pool history is usually far below the cap. If not, cover the sharp-reserve
    # interval first, then use remaining capacity for the earliest pool trades.
    successful = [s for s in sigs["signatures"] if s.get("err") is None]
    incident = [s for s in successful if s.get("blockTime") is not None and INCIDENT_START <= s["blockTime"] <= INCIDENT_END]
    chosen = list(incident)
    if len(chosen) < TX_CAP:
        chosen_sigs = {s["signature"] for s in chosen}
        tail = [s for s in successful if s["signature"] not in chosen_sigs]
        # Fill the cap with the nearest in time to the incident, not an unbounded history.
        tail.sort(key=lambda s: (abs((s.get("blockTime") or INCIDENT_START) - INCIDENT_START), s.get("slot", 0)))
        chosen.extend(tail[:TX_CAP - len(chosen)])
    chosen = chosen[:TX_CAP]
    selection = {
        "selected_count": len(chosen), "transaction_cap": TX_CAP,
        "incident_block_time_window_utc": [dt.datetime.fromtimestamp(INCIDENT_START, dt.timezone.utc).isoformat(), dt.datetime.fromtimestamp(INCIDENT_END, dt.timezone.utc).isoformat()],
        "selection_rule": "successful transactions in the 23:55:10–23:55:25 UTC reserve-break window first; if the window contains fewer than 200, fill by closeness in block time to that window start; hard cap 200",
        "signatures": [s["signature"] for s in chosen],
    }
    (OUT / "third_amm_tx_selection.json").write_text(json.dumps(selection, separators=(",", ":")) + "\n")
    by_sig = {s["signature"]: s for s in sigs["signatures"]}
    def get_one(pair):
        i, sig = pair
        params = [sig, {"encoding": "jsonParsed", "commitment": "finalized", "maxSupportedTransactionVersion": 1}]
        try:
            return sig, call(endpoints[0], "getTransaction", params, i + 1), "Shyft", None
        except Exception as first:
            try:
                return sig, call(endpoints[1], "getTransaction", params, i + 1), "Alchemy", None
            except Exception as second:
                return sig, None, None, f"primary/fallback failure: {type(second).__name__}"
    results, providers, failures = {}, collections.Counter(), []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(get_one, (i, s["signature"])) for i, s in enumerate(chosen)]
        for future in concurrent.futures.as_completed(futures):
            sig, tx, provider, error = future.result()
            if tx is not None:
                results[sig] = tx
                providers[provider] += 1
            else:
                meta = by_sig[sig]
                failures.append({"signature": sig, "slot": meta.get("slot"), "blockTime": meta.get("blockTime"), "error": error})
    payload = {
        "network": "solana-mainnet", "fetched_at_utc": now(),
        "encoding": "jsonParsed", "commitment": "finalized", "max_supported_transaction_version": 1,
        "requested_count": len(chosen), "returned_count": len(results), "provider_counts": dict(providers),
        "rpc_failures": failures, "transactions": results,
    }
    (OUT / "third_amm_pool_transactions.json").write_text(json.dumps(payload, separators=(",", ":")) + "\n")
    return payload


def main() -> None:
    endpoints = __import__("re").findall(r"`(https://[^`]+)`", (ROOT / "AGENTS.md").read_text())[:2]
    if len(endpoints) < 2:
        raise RuntimeError("configured RPC endpoints unavailable")
    signatures = get_signatures(endpoints[0])
    state = state_snapshot(endpoints)
    txs = fetch_transactions(endpoints, signatures)
    print(json.dumps({
        "signature_count": signatures["unique_signature_count"],
        "success_count": signatures["successful_count"], "failed_count": signatures["failed_count"],
        "pages": signatures["pages_returned"], "state_slot": state["context_slot"],
        "state_quote_raw": state["quote_reserve_raw"], "selected_bodies": txs["requested_count"],
        "returned_bodies": txs["returned_count"], "body_errors": len(txs["rpc_failures"]),
    }, indent=2))


if __name__ == "__main__":
    import collections
    main()
