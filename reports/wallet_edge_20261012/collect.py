"""Collect finalized Solana transaction histories for the frozen 22-wallet cohort."""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import gzip
import hashlib
import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

try:
    from .rpc import rpc_with_meta
except ImportError:  # Running this file directly from the report directory.
    from rpc import rpc_with_meta


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
RAW_DIR = HERE / "raw_wallets"
WALLETS_PATH = HERE / "wallets.json"
MANIFEST_PATH = HERE / "collection.json"
FREEZE_PATH = RAW_DIR / "freeze.json"
DAYS = 21
SECONDS_PER_DAY = 86_400
RECENT_LIMIT = 250
HISTORY_LIMIT = 1_000
MAX_PAGES_PER_WALLET = 10
MAX_WORKERS = 4
COMMITMENT = "finalized"
ENCODING = "jsonParsed"
MAX_TX_VERSION = 1
SUCCESS_SUPPLEMENT_ADDRESSES = {
    "niggerd597QYedtvjQDVHZTCCGyJrwHNm2i49dkm5zS",  # nbot
    "7ovu7sqYQGcHwUnLfVfwjCx5VGBCiJmBrsrBv2ab1Ltx",  # bot
    "BuekUk3YMmm7Agnb4ni1qMCmShVpeBTdQZYNyihyzr7u",  # insane bot
    "94iQuYjVgTwGXxtM7ywfpzfLvx3gN4oQRuc9osRE2pEm",  # Bot
    "Fhbh1DTUDKt6qu9zVg8Q5VgnZa1WWWbxBxG6pCoJoggA",  # boooooot
}

_manifest_lock = threading.Lock()
_manifest: dict[str, Any] = {}


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_iso(timestamp: int | float | None) -> str | None:
    if timestamp is None:
        return None
    return dt.datetime.fromtimestamp(timestamp, dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def _atomic_gzip_json(path: Path, value: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as target:
            with gzip.GzipFile(fileobj=target, mode="wb", mtime=0) as zipped:
                zipped.write(raw)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise
    return digest


def _write_manifest() -> None:
    with _manifest_lock:
        _atomic_json(MANIFEST_PATH, _manifest)


def _update_wallet(address: str, section: str, value: dict[str, Any]) -> None:
    with _manifest_lock:
        _manifest["wallets"][address][section] = value
        _atomic_json(MANIFEST_PATH, _manifest)


def _load_wallets() -> list[dict[str, str]]:
    wallets = json.loads(WALLETS_PATH.read_text(encoding="utf-8"))
    if len(wallets) != 22:
        raise RuntimeError(f"Expected 22 wallets from the AST assignment; found {len(wallets)}")
    if len({wallet.get("address") for wallet in wallets}) != 22:
        raise RuntimeError("Wallet addresses are missing or duplicated")
    for wallet in wallets:
        if set(wallet) != {"address", "name"}:
            raise RuntimeError("wallets.json must contain only address and name")
    return wallets


def _safe_error(error: BaseException) -> dict[str, str]:
    # RPCError intentionally omits endpoint URLs; keep manifest errors concise.
    return {"type": error.__class__.__name__, "message": str(error)}


def _is_failed(tx: dict[str, Any]) -> bool:
    status = tx.get("status")
    if isinstance(status, str) and status.lower() in {"failed", "failure", "error", "err"}:
        return True
    if isinstance(status, dict) and ("Err" in status or "err" in status):
        return True
    meta = tx.get("meta")
    if isinstance(meta, dict) and "err" in meta and meta.get("err") is not None:
        return True
    error = tx.get("error")
    return error not in (None, False, {}, "")


def _payer(tx: dict[str, Any]) -> str | None:
    direct = tx.get("feePayer") or tx.get("fee_payer")
    if isinstance(direct, str):
        return direct
    transaction = tx.get("transaction")
    message = transaction.get("message") if isinstance(transaction, dict) else None
    if not isinstance(message, dict):
        message = tx.get("message")
    account_keys = message.get("accountKeys") if isinstance(message, dict) else None
    if not isinstance(account_keys, list) or not account_keys:
        return None
    first = account_keys[0]
    if isinstance(first, str):
        return first
    if isinstance(first, dict):
        key = first.get("pubkey") or first.get("publicKey")
        return key if isinstance(key, str) else None
    return None


def _signature(tx: dict[str, Any]) -> str | None:
    direct = tx.get("signature")
    if isinstance(direct, str):
        return direct
    transaction = tx.get("transaction")
    signatures = transaction.get("signatures") if isinstance(transaction, dict) else None
    if isinstance(signatures, list) and signatures and isinstance(signatures[0], str):
        return signatures[0]
    return None


def _row_summary(rows: list[Any], wallet_address: str) -> dict[str, Any]:
    counts = {"success": 0, "failed": 0, "unknown": 0}
    times: list[int] = []
    missing_time = 0
    payer_failed = 0
    failed_signatures: list[str] = []
    for tx in rows:
        if not isinstance(tx, dict):
            counts["unknown"] += 1
            continue
        if _is_failed(tx):
            counts["failed"] += 1
            signature = _signature(tx)
            if signature:
                failed_signatures.append(signature)
            if _payer(tx) == wallet_address:
                payer_failed += 1
        elif isinstance(tx.get("status"), (str, dict)) or (
            isinstance(tx.get("meta"), dict) and "err" in tx["meta"]
        ):
            counts["success"] += 1
        else:
            counts["unknown"] += 1
        block_time = tx.get("blockTime")
        if isinstance(block_time, (int, float)):
            times.append(int(block_time))
        else:
            missing_time += 1
    return {
        "status_counts": counts,
        "payer_failed_count": payer_failed,
        "failed_signatures": failed_signatures,
        "min_block_time": min(times) if times else None,
        "max_block_time": max(times) if times else None,
        "missing_block_time_count": missing_time,
    }


def _history_options(start: int, cutoff: int, token: str | None) -> dict[str, Any]:
    options: dict[str, Any] = {
        "commitment": COMMITMENT,
        "encoding": ENCODING,
        "transactionDetails": "full",
        "maxSupportedTransactionVersion": MAX_TX_VERSION,
        "sortOrder": "desc",
        "limit": HISTORY_LIMIT,
        "filters": {"blockTime": {"gte": start, "lt": cutoff}},
    }
    if token:
        options["paginationToken"] = token
    return options


def _recent_request(address: str, cutoff: int) -> list[Any]:
    options = {
        "commitment": COMMITMENT,
        "encoding": ENCODING,
        "transactionDetails": "full",
        "maxSupportedTransactionVersion": MAX_TX_VERSION,
        "sortOrder": "desc",
        "limit": RECENT_LIMIT,
        "filters": {"blockTime": {"lt": cutoff}},
    }
    return [address, options]


def _page_envelope(
    wallet: dict[str, str],
    response: dict[str, Any],
    *,
    provider: str,
    cache_hit: bool,
    request: dict[str, Any],
) -> dict[str, Any]:
    rows = response.get("data")
    if not isinstance(rows, list):
        raise RuntimeError("getTransactionsForAddress result has no `data` array")
    invalid_rows = [
        index for index, tx in enumerate(rows)
        if not isinstance(tx, dict)
        or not isinstance(tx.get("transaction"), dict)
        or not isinstance(tx.get("meta"), dict)
    ]
    token = response.get("paginationToken") or None
    return {
        "schema_version": 1,
        "wallet": {"address": wallet["address"], "name": wallet["name"]},
        "fetched_at_utc": _utc_now(),
        "provider": provider,
        "cache_hit": cache_hit,
        "request": request,
        "count": len(rows),
        "full_rows_verified": not invalid_rows,
        "rows_missing_transaction_or_meta": invalid_rows,
        "transactions": rows,
        "pagination_token": token,
        "response": response,
    }


def _manifest_page_path(path: Path) -> str:
    return path.relative_to(HERE).as_posix()


def _fetch_recent(wallet: dict[str, str]) -> None:
    address = wallet["address"]
    cutoff = int(_manifest["freeze_cutoff"]["block_time"])
    request_params = _recent_request(address, cutoff)
    path = RAW_DIR / f"recent_{address}.json.gz"
    try:
        result = rpc_with_meta("getTransactionsForAddress", request_params, cache=True)
        response = result["result"]
        if not isinstance(response, dict):
            raise RuntimeError("getTransactionsForAddress returned a non-object response")
        envelope = _page_envelope(
            wallet,
            response,
            provider=result["provider"],
            cache_hit=result["cache_hit"],
            request={"method": "getTransactionsForAddress", "params": request_params},
        )
        if not envelope["full_rows_verified"]:
            _atomic_gzip_json(RAW_DIR / "incomplete" / f"recent_{address}.json.gz", envelope)
            raise RuntimeError("nonempty response rows are missing full transaction or meta data")
        digest = _atomic_gzip_json(path, envelope)
        rows = envelope["transactions"]
        summary = _row_summary(rows, address)
        _update_wallet(address, "recent", {
            "status": "complete",
            "file": _manifest_page_path(path),
            "sha256_uncompressed_json": digest,
            "provider": result["provider"],
            "cache_hit": result["cache_hit"],
            "request_limit": RECENT_LIMIT,
            "cutoff_block_time_exclusive": cutoff,
            "full_rows_verified": True,
            "count": len(rows),
            "pagination_token_available": bool(envelope["pagination_token"]),
            **summary,
        })
    except Exception as error:
        failure = _safe_error(error)
        envelope = {
            "schema_version": 1,
            "wallet": {"address": address, "name": wallet["name"]},
            "fetched_at_utc": _utc_now(),
            "provider": "alchemy",
            "request": {"method": "getTransactionsForAddress", "params": request_params},
            "count": 0,
            "transactions": [],
            "pagination_token": None,
            "full_rows_verified": False,
            "error": failure,
        }
        digest = _atomic_gzip_json(path, envelope)
        _update_wallet(address, "recent", {
            "status": "error", "file": _manifest_page_path(path),
            "sha256_uncompressed_json": digest, "request_limit": RECENT_LIMIT,
            "count": 0, "full_rows_verified": False, "error": failure,
        })


def _fetch_balance(wallet: dict[str, str]) -> None:
    address = wallet["address"]
    try:
        result = rpc_with_meta("getBalance", [address, {"commitment": COMMITMENT}], cache=False)
        payload = result["result"]
        if not isinstance(payload, dict) or not isinstance(payload.get("value"), int):
            raise RuntimeError("getBalance returned no integer lamport value")
        value = payload["value"]
        _update_wallet(address, "balance_snapshot", {
            "status": "complete",
            "fetched_at_utc": _utc_now(),
            "provider": result["provider"],
            "commitment": COMMITMENT,
            "context_slot": payload.get("context", {}).get("slot") if isinstance(payload.get("context"), dict) else None,
            "lamports": value,
            "sol": value / 1_000_000_000,
        })
    except Exception as error:
        _update_wallet(address, "balance_snapshot", {"status": "error", "error": _safe_error(error)})


def _history_worker(wallet: dict[str, str], start: int, cutoff: int, requested_start: int) -> None:
    address = wallet["address"]
    existing = _manifest["wallets"][address].get("history") or {}
    pages = list(existing.get("pages", []))
    if existing.get("status") in {"complete", "truncated_page_cap"}:
        if existing.get("source_rows_status") == "full_transaction_and_meta":
            return
    if len(pages) >= MAX_PAGES_PER_WALLET:
        _update_wallet(address, "history", {**existing, "status": "truncated_page_cap"})
        return

    token = pages[-1].get("pagination_token") if pages else None
    seen_tokens = {page.get("pagination_token") for page in pages if page.get("pagination_token")}
    wallet_dir = RAW_DIR / "history" / address
    wallet_dir.mkdir(parents=True, exist_ok=True)
    errors = list(existing.get("errors", []))
    while len(pages) < MAX_PAGES_PER_WALLET:
        page_number = len(pages) + 1
        options = _history_options(start, cutoff, token)
        params = [address, options]
        try:
            result = rpc_with_meta("getTransactionsForAddress", params, cache=True)
            response = result["result"]
            if not isinstance(response, dict):
                raise RuntimeError("getTransactionsForAddress returned a non-object response")
            envelope = _page_envelope(
                wallet,
                response,
                provider=result["provider"],
                cache_hit=result["cache_hit"],
                request={"method": "getTransactionsForAddress", "params": params},
            )
            page_path = wallet_dir / f"page-{page_number:04d}.json.gz"
            if not envelope["full_rows_verified"]:
                incomplete = RAW_DIR / "incomplete" / "history" / address / page_path.name
                _atomic_gzip_json(incomplete, envelope)
                raise RuntimeError("nonempty response rows are missing full transaction or meta data")
            digest = _atomic_gzip_json(page_path, envelope)
            rows = envelope["transactions"]
            summary = _row_summary(rows, address)
            next_token = envelope["pagination_token"]
            page_meta = {
                "page": page_number,
                "file": _manifest_page_path(page_path),
                "sha256_uncompressed_json": digest,
                "provider": result["provider"],
                "cache_hit": result["cache_hit"],
                "request_limit": HISTORY_LIMIT,
                "count": len(rows),
                "full_rows_verified": True,
                "pagination_token": next_token,
                "min_block_time": summary["min_block_time"],
                "max_block_time": summary["max_block_time"],
                "status_counts": summary["status_counts"],
                "payer_failed_count": summary["payer_failed_count"],
                "failed_signatures": summary["failed_signatures"],
                "missing_block_time_count": summary["missing_block_time_count"],
                "out_of_requested_window_count": sum(
                    1 for tx in rows
                    if isinstance(tx, dict)
                    and isinstance(tx.get("blockTime"), (int, float))
                    and not (requested_start <= int(tx["blockTime"]) < cutoff)
                ),
            }
            pages.append(page_meta)
            status = "complete" if not next_token else "collecting"
            if next_token and len(pages) >= MAX_PAGES_PER_WALLET:
                status = "truncated_page_cap"
            history = {
                "status": status,
                "full_rows_verified": True,
                "source_rows_status": "full_transaction_and_meta",
                "requested_start_block_time": requested_start,
                "requested_start_utc": _utc_iso(requested_start),
                "cutoff_block_time_exclusive": cutoff,
                "cutoff_utc_exclusive": _utc_iso(cutoff),
                "page_limit": HISTORY_LIMIT,
                "page_cap": MAX_PAGES_PER_WALLET,
                "pages_fetched": len(pages),
                "pages": pages,
                "errors": errors,
            }
            _update_wallet(address, "history", history)
            if not next_token:
                return
            if next_token in seen_tokens:
                errors.append({"type": "PaginationError", "message": "Provider repeated a pagination token; stopped to avoid duplicate pages"})
                history["status"] = "error_repeated_pagination_token"
                history["errors"] = errors
                _update_wallet(address, "history", history)
                return
            seen_tokens.add(next_token)
            token = next_token
        except Exception as error:
            errors.append({"page": page_number, **_safe_error(error)})
            history = {
                "status": "partial_error",
                "full_rows_verified": bool(pages) and all(page.get("full_rows_verified") is True for page in pages),
                "source_rows_status": "full_transaction_and_meta" if pages and all(page.get("full_rows_verified") is True for page in pages) else "unverified",
                "requested_start_block_time": requested_start,
                "requested_start_utc": _utc_iso(requested_start),
                "cutoff_block_time_exclusive": cutoff,
                "cutoff_utc_exclusive": _utc_iso(cutoff),
                "page_limit": HISTORY_LIMIT,
                "page_cap": MAX_PAGES_PER_WALLET,
                "pages_fetched": len(pages),
                "pages": pages,
                "errors": errors,
            }
            _update_wallet(address, "history", history)
            return


def _collect_successful_supplement(wallets: list[dict[str, str]]) -> None:
    """Bounded success-only supplement; failed receipts/fees are excluded by design."""
    cutoff = int(_manifest["freeze_cutoff"]["block_time"])
    start = int(_manifest["requested_interval"]["start_block_time_inclusive"])
    supplement = _manifest.setdefault("successful_history", {
        "status": "collecting", "status_filter": "succeeded", "failed_receipts_included": False,
        "failed_receipt_fees_included": False, "fees_accounted": False,
        "window": {"start_inclusive": start, "end_exclusive": cutoff},
        "page_limit": HISTORY_LIMIT, "page_cap_per_wallet": MAX_PAGES_PER_WALLET, "wallets": {},
    })
    for wallet in wallets:
        address = wallet["address"]
        if address not in SUCCESS_SUPPLEMENT_ADDRESSES:
            continue
        state = supplement["wallets"].setdefault(address, {"name": wallet["name"], "status": "pending", "pages": [], "errors": []})
        pages = state["pages"]
        if state.get("status") in {"complete", "truncated_page_cap"} and state.get("source_rows_status") == "full_transaction_and_meta":
            continue
        token = pages[-1].get("pagination_token") if pages else None
        seen = {page.get("pagination_token") for page in pages if page.get("pagination_token")}
        target = RAW_DIR / "successful_history" / address
        target.mkdir(parents=True, exist_ok=True)
        while len(pages) < MAX_PAGES_PER_WALLET:
            options = _history_options(start, cutoff, token)
            options["filters"]["status"] = "succeeded"
            params = [address, options]
            page_no = len(pages) + 1
            try:
                result = rpc_with_meta("getTransactionsForAddress", params, cache=True)
                response = result["result"]
                envelope = _page_envelope(wallet, response, provider=result["provider"], cache_hit=result["cache_hit"], request={"method": "getTransactionsForAddress", "params": params})
                rows = envelope["transactions"]
                outside = sum(1 for tx in rows if tx.get("blockTime") is None or not (start <= tx["blockTime"] < cutoff))
                failed = sum(1 for tx in rows if tx.get("meta", {}).get("err") is not None)
                if not envelope["full_rows_verified"] or outside or failed:
                    bad = RAW_DIR / "incomplete" / "successful_history" / address / f"page-{page_no:04d}.json.gz"
                    _atomic_gzip_json(bad, envelope)
                    raise RuntimeError(f"success supplement validation failed: full={envelope['full_rows_verified']} out_of_window={outside} failed_rows={failed}")
                path = target / f"page-{page_no:04d}.json.gz"
                digest = _atomic_gzip_json(path, envelope)
                next_token = envelope["pagination_token"]
                counts = _row_summary(rows, address)
                pages.append({"page": page_no, "file": _manifest_page_path(path), "sha256_uncompressed_json": digest, "provider": result["provider"], "cache_hit": result["cache_hit"], "count": len(rows), "full_rows_verified": True, "status_counts": counts["status_counts"], "payer_failed_count": 0, "min_block_time": counts["min_block_time"], "max_block_time": counts["max_block_time"], "pagination_token": next_token})
                state.update({"status": "complete" if not next_token else "collecting", "source_rows_status": "full_transaction_and_meta", "page_count": len(pages), "transaction_count": sum(page["count"] for page in pages), "pagination_token_available": bool(next_token)})
                if next_token and len(pages) >= MAX_PAGES_PER_WALLET:
                    state["status"] = "truncated_page_cap"
                _write_manifest()
                if not next_token or state["status"] == "truncated_page_cap":
                    break
                if next_token in seen:
                    raise RuntimeError("provider repeated a pagination token")
                seen.add(next_token)
                token = next_token
            except Exception as error:
                state["status"] = "partial_error"
                state.setdefault("errors", []).append({"page": page_no, **_safe_error(error)})
                _write_manifest()
                break
    states = [supplement["wallets"].get(address, {}).get("status") for address in SUCCESS_SUPPLEMENT_ADDRESSES]
    supplement["status"] = "complete" if all(status in {"complete", "truncated_page_cap"} for status in states) else "partial_with_errors"
    supplement["completed_at_utc"] = _utc_now()
    _write_manifest()


def _sum_page_statuses(pages: list[dict[str, Any]]) -> dict[str, int]:
    result = {"success": 0, "failed": 0, "unknown": 0}
    for page in pages:
        for key in result:
            result[key] += int(page.get("status_counts", {}).get(key, 0))
    return result


def _coverage_summary(wallets: list[dict[str, str]], start: int, cutoff: int) -> dict[str, Any]:
    histories = [_manifest["wallets"][wallet["address"]].get("history", {}) for wallet in wallets]
    failed = [
        history for history in histories
        if history.get("status") not in {"complete", "truncated_page_cap"}
        or history.get("source_rows_status") != "full_transaction_and_meta"
    ]
    if failed:
        return {
            "status": "joint_interval_unavailable",
            "start_block_time_inclusive": None,
            "end_block_time_exclusive": cutoff,
            "end_utc_exclusive": _utc_iso(cutoff),
            "reason": "At least one wallet has incomplete or errored history retrieval",
            "affected_wallets": [
                wallets[index]["address"] for index, history in enumerate(histories)
                if history.get("status") not in {"complete", "truncated_page_cap"}
                or history.get("source_rows_status") != "full_transaction_and_meta"
            ],
        }

    clipped_starts = [start]
    for history in histories:
        if history.get("status") == "truncated_page_cap":
            oldest = min(
                (page.get("min_block_time") for page in history.get("pages", []) if page.get("min_block_time") is not None),
                default=None,
            )
            if oldest is not None:
                # The same blockTime second can straddle the page boundary.
                clipped_starts.append(max(start, int(oldest) + 1))
    common_start = max(clipped_starts)
    any_cap = any(history.get("status") == "truncated_page_cap" for history in histories)
    return {
        "status": "bounded_due_to_page_cap" if any_cap else "complete_requested_interval",
        "start_block_time_inclusive": common_start,
        "start_utc_inclusive": _utc_iso(common_start),
        "end_block_time_exclusive": cutoff,
        "end_utc_exclusive": _utc_iso(cutoff),
        "basis": "All 22 histories complete" if not any_cap else "Common interval clipped after the oldest included second for every capped wallet; descending finalized pagination",
        "page_capped_wallets": [
            wallet["address"] for wallet in wallets
            if _manifest["wallets"][wallet["address"]].get("history", {}).get("status") == "truncated_page_cap"
        ],
    }


def _new_manifest(wallets: list[dict[str, str]], freeze: dict[str, Any]) -> dict[str, Any]:
    cutoff = int(freeze["block_time"])
    start = cutoff - DAYS * SECONDS_PER_DAY
    return {
        "schema_version": 1,
        "study": "tracked bot wallet receipt collection",
        "created_at_utc": _utc_now(),
        "status": "collecting_recent",
        "wallet_source": "wallets.json generated from the `wallets` assignment AST in scratch/study_tracked_bots.py; the script was not executed",
        "wallet_count": len(wallets),
        "freeze_cutoff": {
            "commitment": COMMITMENT,
            "slot": int(freeze["slot"]),
            "block_time": cutoff,
            "utc": _utc_iso(cutoff),
            "provider_for_get_slot": freeze["slot_provider"],
            "provider_for_get_block_time": freeze["time_provider"],
            "frozen_at_utc": freeze["frozen_at_utc"],
        },
        "requested_interval": {
            "days": DAYS,
            "start_block_time_inclusive": start,
            "start_utc_inclusive": _utc_iso(start),
            "end_block_time_exclusive": cutoff,
            "end_utc_exclusive": _utc_iso(cutoff),
        },
        "rpc_policy": {
            "enhanced_method": "getTransactionsForAddress",
            "enhanced_provider": "Alchemy",
            "standard_provider_order": ["Shyft", "Alchemy fallback"],
            "commitment": COMMITMENT,
            "encoding": ENCODING,
            "max_supported_transaction_version": MAX_TX_VERSION,
            "transaction_details": "full",
            "history_sort_order": "desc",
            "history_page_size": HISTORY_LIMIT,
            "history_page_cap_per_wallet": MAX_PAGES_PER_WALLET,
            "source_rows_status_required": "full_transaction_and_meta",
            "recent_limit_per_wallet": RECENT_LIMIT,
            "success_and_failure_receipts_included": True,
            "status_filter": None,
            "global_start_rate_per_second": 4,
            "maximum_workers": MAX_WORKERS,
        },
        "wallets": {
            wallet["address"]: {
                "name": wallet["name"],
                "recent": {"status": "pending", "full_rows_verified": False},
                "balance_snapshot": {"status": "pending"},
                "history": {"status": "pending", "full_rows_verified": False, "source_rows_status": "pending", "pages": [], "pages_fetched": 0, "errors": []},
            }
            for wallet in wallets
        },
    }


def _establish_freeze() -> dict[str, Any]:
    slot_result = rpc_with_meta("getSlot", [{"commitment": COMMITMENT}], cache=False)
    slot = slot_result["result"]
    if not isinstance(slot, int):
        raise RuntimeError("getSlot(finalized) returned no integer slot")
    time_result = rpc_with_meta("getBlockTime", [slot], cache=True)
    block_time = time_result["result"]
    if not isinstance(block_time, int):
        raise RuntimeError(f"getBlockTime for finalized slot {slot} returned no timestamp")
    return {
        "slot": slot,
        "block_time": block_time,
        "slot_provider": slot_result["provider"],
        "time_provider": time_result["provider"],
        "frozen_at_utc": _utc_now(),
    }


def _load_or_freeze(wallets: list[dict[str, str]]) -> None:
    global _manifest
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    if MANIFEST_PATH.exists():
        existing = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        existing_addresses = set(existing.get("wallets", {}))
        expected_addresses = {wallet["address"] for wallet in wallets}
        if existing_addresses != expected_addresses:
            raise RuntimeError("Existing collection.json wallet set differs; refusing to mix cohorts")
        if existing.get("status") in {"complete", "complete_with_coverage_limits"}:
            print("Existing frozen collection is complete; leaving its cutoff and files unchanged.")
            raise SystemExit(0)
        if existing.get("freeze_cutoff", {}).get("block_time") is not None:
            _manifest = existing
            _atomic_json(FREEZE_PATH, existing["freeze_cutoff"])
            return

    try:
        freeze = _establish_freeze()
    except Exception as error:
        _manifest = {
            "schema_version": 1,
            "study": "tracked bot wallet receipt collection",
            "created_at_utc": _utc_now(),
            "status": "freeze_failed",
            "wallet_count": len(wallets),
            "wallet_addresses": [wallet["address"] for wallet in wallets],
            "error": _safe_error(error),
        }
        _write_manifest()
        raise
    _manifest = _new_manifest(wallets, freeze)
    _write_manifest()
    _atomic_json(FREEZE_PATH, _manifest["freeze_cutoff"])


def _collect(wallets: list[dict[str, str]]) -> None:
    cutoff = int(_manifest["freeze_cutoff"]["block_time"])
    start = int(_manifest["requested_interval"]["start_block_time_inclusive"])

    _manifest["status"] = "collecting_recent"
    _write_manifest()
    pending_recent = [
        wallet for wallet in wallets
        if _manifest["wallets"][wallet["address"]].get("recent", {}).get("status") != "complete"
        or _manifest["wallets"][wallet["address"]].get("recent", {}).get("full_rows_verified") is not True
        or not (HERE / _manifest["wallets"][wallet["address"]].get("recent", {}).get("file", "")).is_file()
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        list(pool.map(_fetch_recent, pending_recent))
    recent_count = sum(
        1 for wallet in wallets
        if _manifest["wallets"][wallet["address"]].get("recent", {}).get("status") == "complete"
    )
    print(f"Recent finalized receipt files ready: {recent_count}/22; cutoff {_manifest['freeze_cutoff']['utc']}", flush=True)

    _manifest["status"] = "collecting_balances"
    _write_manifest()
    pending_balances = [
        wallet for wallet in wallets
        if _manifest["wallets"][wallet["address"]].get("balance_snapshot", {}).get("status") != "complete"
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        list(pool.map(_fetch_balance, pending_balances))

    _manifest["status"] = "collecting_history"
    _write_manifest()
    pending_history = [
        wallet for wallet in wallets
        if _manifest["wallets"][wallet["address"]].get("history", {}).get("status") not in {"complete", "truncated_page_cap"}
        or _manifest["wallets"][wallet["address"]].get("history", {}).get("source_rows_status") != "full_transaction_and_meta"
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        list(pool.map(lambda wallet: _history_worker(wallet, start, cutoff, start), pending_history))

    for wallet in wallets:
        address = wallet["address"]
        history = _manifest["wallets"][address].get("history", {})
        pages = history.get("pages", [])
        _manifest["wallets"][address]["history_summary"] = {
            "status": history.get("status"),
            "full_rows_verified": history.get("full_rows_verified", False),
            "source_rows_status": history.get("source_rows_status", "unverified"),
            "page_count": len(pages),
            "transaction_count": sum(int(page.get("count", 0)) for page in pages),
            "status_counts": _sum_page_statuses(pages),
            "payer_failed_count": sum(int(page.get("payer_failed_count", 0)) for page in pages),
            "min_block_time": min((page["min_block_time"] for page in pages if page.get("min_block_time") is not None), default=None),
            "max_block_time": max((page["max_block_time"] for page in pages if page.get("max_block_time") is not None), default=None),
            "missing_block_time_count": sum(int(page.get("missing_block_time_count", 0)) for page in pages),
            "out_of_requested_window_count": sum(int(page.get("out_of_requested_window_count", 0)) for page in pages),
        }

    _manifest["joint_coverage"] = _coverage_summary(wallets, start, cutoff)
    has_errors = any(
        _manifest["wallets"][wallet["address"]].get("history", {}).get("status") not in {"complete", "truncated_page_cap"}
        or _manifest["wallets"][wallet["address"]].get("history", {}).get("source_rows_status") != "full_transaction_and_meta"
        for wallet in wallets
    ) or any(
        _manifest["wallets"][wallet["address"]].get("recent", {}).get("status") == "error"
        or _manifest["wallets"][wallet["address"]].get("balance_snapshot", {}).get("status") == "error"
        for wallet in wallets
    )
    capped = any(
        _manifest["wallets"][wallet["address"]].get("history", {}).get("status") == "truncated_page_cap"
        for wallet in wallets
    )
    _manifest["completed_at_utc"] = _utc_now()
    _manifest["status"] = "partial_with_errors" if has_errors else ("complete_with_coverage_limits" if capped else "complete")
    _write_manifest()


def main() -> int:
    global MAX_WORKERS, _manifest
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=MAX_WORKERS, help="worker count, capped at four")
    parser.add_argument(
        "--success-supplement",
        action="store_true",
        help="fetch bounded succeeded-only histories for the five explicitly selected wallets",
    )
    args = parser.parse_args()
    # The shared RPC client owns cross-process rate limiting. Keep collection
    # fan-out bounded even if a caller requests more workers.
    MAX_WORKERS = max(1, min(4, int(args.workers)))
    wallets = _load_wallets()
    if args.success_supplement:
        try:
            existing = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
            expected_addresses = {wallet["address"] for wallet in wallets}
            if set(existing.get("wallets", {})) != expected_addresses:
                raise RuntimeError("Existing collection.json wallet set differs; refusing to mix cohorts")
            if existing.get("freeze_cutoff", {}).get("block_time") is None:
                raise RuntimeError("No frozen cutoff is available in collection.json")
            _manifest = existing
            _atomic_json(FREEZE_PATH, _manifest["freeze_cutoff"])
            _collect_successful_supplement(wallets)
            print(json.dumps({
                "status": _manifest.get("successful_history", {}).get("status"),
                "wallets": {
                    address: {
                        "status": state.get("status"),
                        "pages_fetched": len(state.get("pages", [])),
                        "transaction_count": state.get("transaction_count", 0),
                    }
                    for address, state in _manifest.get("successful_history", {}).get("wallets", {}).items()
                },
                "cutoff_utc": _manifest["freeze_cutoff"]["utc"],
            }, indent=2), flush=True)
        except Exception as error:
            print(f"Could not collect successful-only supplement: {_safe_error(error)['message']}")
            return 1
        return 0
    try:
        _load_or_freeze(wallets)
    except SystemExit as error:
        return int(error.code or 0)
    except Exception as error:
        print(f"Could not freeze collection cutoff: {_safe_error(error)['message']}")
        return 1
    _collect(wallets)
    print(json.dumps({
        "status": _manifest["status"],
        "wallet_count": len(wallets),
        "cutoff_utc": _manifest["freeze_cutoff"]["utc"],
        "joint_coverage": _manifest.get("joint_coverage"),
        "manifest": str(MANIFEST_PATH.relative_to(REPO_ROOT)) if MANIFEST_PATH.is_relative_to(REPO_ROOT) else str(MANIFEST_PATH),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
