#!/usr/bin/env python3
"""Descriptive execution-cost audit from captured, full Solana receipts.

This is not a replay or a PnL estimator. Trades are admitted only when a
successful official Pump event is signed by its event user and exactly matches
that user's one-mint token-balance delta. Costs are sampled by signature hash,
independent of transaction outcome or price.
"""
from __future__ import annotations

import gzip
import hashlib
import heapq
import json
import math
import pathlib
import re
import statistics
import sys
from collections import Counter

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
HELPERS = ROOT / "research/day_general_20261004/helpers"
sys.path.insert(0, str(HELPERS))
import decoder as D  # approved official-IDL Pump event decoder

LAMPORTS = 1_000_000_000
WSOL = "So11111111111111111111111111111111111111112"
SYSTEM = "11111111111111111111111111111111"
SAMPLE_N = 200
BASE_COST = 1_505_000
SENSITIVITY_COST = 2_916_000
WALLETS = HERE / "wallets.json"
MANIFEST = HERE / "collection.json"
HISTORY = HERE / "raw_wallets/history"
OUT_JSON = HERE / "execution_costs.json"
OUT_MD = HERE / "execution_costs.md"


def keys(tx: dict) -> list[str]:
    msg = tx["transaction"]["message"]
    vals = [x.get("pubkey", "") if isinstance(x, dict) else x
            for x in msg.get("accountKeys", [])]
    loaded = (tx.get("meta", {}).get("loadedAddresses") or {})
    # Enhanced jsonParsed receipts normally include loaded addresses in
    # accountKeys; append only if the balance-vector length proves they are out.
    needed = len(tx["meta"].get("preBalances", []))
    if len(vals) < needed:
        vals.extend(loaded.get("writable", []) or [])
        vals.extend(loaded.get("readonly", []) or [])
    return vals


def signers(tx: dict) -> set[str]:
    msg = tx["transaction"]["message"]
    account_keys = msg.get("accountKeys", []) or []
    header = msg.get("header") or {}
    required = header.get("numRequiredSignatures", 0)
    result = set()
    for i, item in enumerate(account_keys):
        key = item.get("pubkey") if isinstance(item, dict) else item
        is_signer = item.get("signer") if isinstance(item, dict) else i < required
        if is_signer and isinstance(key, str):
            result.add(key)
    return result


def owner_token_amounts(tx: dict, owner: str, side: str) -> dict[str, int]:
    totals: Counter[str] = Counter()
    for b in tx["meta"].get(side + "TokenBalances", []) or []:
        if b.get("owner") == owner:
            totals[b["mint"]] += int(b["uiTokenAmount"]["amount"])
    return dict(totals)


def owner_rent(tx: dict, owner: str, side: str, account_keys: list[str]) -> int | None:
    """Rent-reserve lamports in this owner's token accounts, excluding WSOL."""
    meta = tx["meta"]
    balances = meta.get(side + "Balances", []) or []
    rows = meta.get(side + "TokenBalances", []) or []
    rent = 0
    for b in rows:
        if b.get("owner") != owner:
            continue
        i = b.get("accountIndex")
        if not isinstance(i, int) or i >= len(balances) or i >= len(account_keys):
            return None
        lamports = int(balances[i])
        raw = int(b["uiTokenAmount"]["amount"])
        reserve = lamports - raw if b.get("mint") == WSOL else lamports
        if reserve < 0:
            return None
        rent += reserve
    return rent


def native_transfer_rows(tx: dict) -> list[dict]:
    rows = list(tx["transaction"]["message"].get("instructions", []) or [])
    for group in tx["meta"].get("innerInstructions", []) or []:
        rows.extend(group.get("instructions", []) or [])
    found = []
    for ix in rows:
        parsed = ix.get("parsed") or {}
        if not isinstance(parsed, dict):
            continue
        info = parsed.get("info") or {}
        if not isinstance(info, dict):
            continue
        if parsed.get("type") not in ("transfer", "transferWithSeed"):
            continue
        if ix.get("program") not in (None, "system") and ix.get("programId") != SYSTEM:
            continue
        src, dst, amount = info.get("source"), info.get("destination"), info.get("lamports")
        if isinstance(src, str) and isinstance(dst, str) and isinstance(amount, int):
            found.append({"source": src, "destination": dst, "lamports": amount})
    return found


def provider_recipients() -> tuple[dict[str, str], dict[str, str]]:
    """Project-configured static tip recipients plus externally published sets."""
    source = (ROOT / "src/bot/bot_types.rs").read_text(encoding="utf-8")
    local: dict[str, str] = {}
    pattern = re.compile(r"pub const ([A-Z0-9_]+TIP_ACCOUNTS):\s*&\[&str\]\s*=\s*&\[(.*?)\];", re.S)
    for match in pattern.finditer(source):
        name = match.group(1).removesuffix("_TIP_ACCOUNTS").replace("_", " ").title()
        for address in re.findall(r'"([1-9A-HJ-NP-Za-km-z]{32,44})"', match.group(2)):
            local[address] = name

    # Jito Labs' public getTipAccounts list (documentation link in the report).
    jito = {
        "96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5",
        "HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe",
        "Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY",
        "ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49",
        "DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh",
        "ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt",
        "DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL",
        "3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT",
    }
    zero_slot = {
        "DiTmWENJsHQdawVUUKnUXkconcpW4Jv52TnMWhkncF6t",
        "HRyRhQ86t3H4aAtgvHVpUJmw64BDrb61gRiKcdKUXs5c",
        "7y4whZmw388w1ggjToDLSBLv47drw5SUXcLk6jtmwixd",
        "J9BMEWFbCBEjtQ1fG5Lo9kouX1HfrKQxeUxetwXrifBw",
        "8U1JPQh3mVQ4F5jwRdFTBzvNRQaYFQppHQYoH38DJGSQ",
        "Eb2KpSC8uMt9GmzyAEm5Eb1AAAgTjRaXWFjKyFXHZxF3",
        "FCjUJZ1qozm1e8romw216qyfQMaaWKxWsuySnumVCCNe",
        "ENxTEjSQ1YabmUpXAdCgevnHQ9MHdLv8tzFiuiYJqa13",
        "6rYLG55Q9RpsPGvqdPNJs4z5WTxJVatMB8zV3WJhs5EK",
        "Cix2bHfqPcKcM233mzxbLk14kSggUUiz2A87fJtGivXr",
    }
    helius = {k for k, v in local.items() if v == "Helius"}
    helius = {k for k in helius if k in {
        "4ACfpUFoaSD9bfPdeu6DBt89gB6ENTeHBXCAi87NhDEE",
        "D2L6yPZ2FmmmTKPgzaMKdhu6EWZcTpLy1Vhx8uvZe7NZ",
        "9bnz4RShgq1hAnLnZbP8kbgBg1kEmcJBYQq3gQbmnSta",
        "5VY91ws6B2hMmBFRsXkoAAdsPHBJwRfBht4DXox3xkwn",
        "2nyhqdwKcJZR2vcqCyrYsaPVdAnFoJjiksCXJ7hfEYgD",
        "2q5pghRs6arqVjRvT5gfgWfWcHWmw1ZuCzphgd5KfWGJ",
        "wyvPkWjVZz1M8fHQnMMCDTQDbkManefNNhweYk5WkcF",
        "3KCKozbAaF75qEU33jtzozcJ29yJuaLJTy2jFdzUY8bT",
        "4vieeGHPYPG2MmyPRcYjdiDmmhN3ww7hsFNap8pVN3Ey",
        "4TQLFNWK8AovT1gFvda5jfw2oJeRMKEmw7aH6MGBJ3or",
    }}
    external = {a: "Jito" for a in jito}
    external.update({a: "Helius" for a in helius})
    external.update({a: "0slot" for a in zero_slot})
    # All configured recipients remain separately labeled. A recipient match
    # establishes destination identity, not which submission route was used.
    merged = dict(local)
    for a, v in external.items():
        merged[a] = v
    return merged, external


def iter_history(address: str):
    files = sorted((HISTORY / address).glob("page-*.json.gz"))
    if not files:
        raise FileNotFoundError(f"No canonical full history pages for {address}")
    seen: set[str] = set()
    for path in files:
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            page = json.load(stream)
        rows = page.get("transactions")
        if not isinstance(rows, list):
            raise ValueError(f"missing transactions array: {path}")
        for tx in rows:
            if "transaction" not in tx or "meta" not in tx:
                raise ValueError(f"signatures-only source rejected: {path}")
            sigs = tx["transaction"].get("signatures") or []
            sig = sigs[0] if sigs else None
            if not sig:
                raise ValueError(f"receipt missing signature: {path}")
            if sig in seen:
                continue
            seen.add(sig)
            yield tx


def quantiles(values: list[int | float]) -> dict | None:
    if not values:
        return None
    s = sorted(values)
    return {
        "n": len(s), "min": s[0], "median": statistics.median(s),
        "p95_nearest_rank": s[max(0, math.ceil(.95 * len(s)) - 1)], "max": s[-1],
    }


def sample_heap_add(heap: list, item: dict) -> None:
    h = int(hashlib.sha256(item["signature"].encode()).hexdigest(), 16)
    entry = (-h, item["signature"], item)
    if len(heap) < SAMPLE_N:
        heapq.heappush(heap, entry)
    elif h < -heap[0][0]:
        heapq.heapreplace(heap, entry)


def exact_trade(tx: dict, user: str, events: list[dict]) -> tuple[dict | None, str]:
    """Return one exact single-mint owner trade or a strict exclusion reason."""
    if tx["meta"].get("err") is not None:
        return None, "failed"
    if user not in signers(tx):
        return None, "event_user_not_signer"
    selected = [e for e in events if e.get("user") == user]
    if not selected:
        return None, "no_user_event"
    required = ("mint", "is_buy", "token_amount", "sol_amount", "quote_is_sol",
                "fee_basis_points", "fee", "creator_fee_basis_points", "creator_fee")
    if any(any(e.get(k) is None for k in required) for e in selected):
        return None, "missing_required_event_fields"
    if not all(e.get("quote_is_sol") for e in selected):
        return None, "non_native_quote"
    by_mint: dict[str, list[dict]] = {}
    for e in selected:
        by_mint.setdefault(e["mint"], []).append(e)
    before = owner_token_amounts(tx, user, "pre")
    after = owner_token_amounts(tx, user, "post")
    changes = {m: after.get(m, 0) - before.get(m, 0)
               for m in set(before) | set(after) if m != WSOL and after.get(m, 0) != before.get(m, 0)}
    if len(by_mint) != 1 or len(changes) != 1:
        return None, "multiple_or_no_owned_mint_changes"
    mint, ee = next(iter(by_mint.items()))
    delta = changes.get(mint)
    expected = sum(int(e["token_amount"]) * (1 if e["is_buy"] else -1) for e in ee)
    if delta is None or delta != expected or delta == 0:
        return None, "owned_token_delta_mismatch"
    if len({bool(e["is_buy"]) for e in ee}) != 1 or ((delta > 0) != bool(ee[0]["is_buy"])):
        return None, "mixed_or_wrong_trade_direction"
    expected_cash = sum(
        -(int(e["sol_amount"]) + int(e["fee"]) + int(e["creator_fee"]))
        if e["is_buy"] else
        int(e["sol_amount"]) - int(e["fee"]) - int(e["creator_fee"])
        for e in ee
    )
    ks = keys(tx)
    meta = tx["meta"]
    native_delta = 0
    found_owner_key = False
    for i, key in enumerate(ks):
        if key == user:
            found_owner_key = True
            native_delta += int(meta["postBalances"][i]) - int(meta["preBalances"][i])
    if not found_owner_key:
        return None, "owner_missing_from_account_keys"
    wsol_delta = after.get(WSOL, 0) - before.get(WSOL, 0)
    cash_delta = native_delta + wsol_delta
    rent_pre = owner_rent(tx, user, "pre", ks)
    rent_post = owner_rent(tx, user, "post", ks)
    payer = ks[0] if ks else None
    fee_lamports = int(meta["fee"]) if payer == user else 0
    rent_change = rent_post - rent_pre if rent_pre is not None and rent_post is not None else None
    residual = cash_delta + rent_change - expected_cash + fee_lamports if rent_change is not None else None
    return {
        "signature": tx["transaction"]["signatures"][0],
        "slot": tx.get("slot"), "transaction_index": tx.get("transactionIndex"),
        "block_time": tx.get("blockTime"), "mint": mint,
        "side": "buy" if delta > 0 else "sell", "events": len(ee),
        "event_quote_lamports": sum(int(e["sol_amount"]) for e in ee),
        "event_fee_lamports": sum(int(e["fee"]) for e in ee),
        "event_creator_fee_lamports": sum(int(e["creator_fee"]) for e in ee),
        "event_buyback_fee_lamports": sum(int(e.get("buyback_fee") or 0) for e in ee),
        "event_holder_rewards_lamports": sum(int(e.get("holder_rewards") or 0) for e in ee),
        "fee_basis_points": sorted(set(int(e["fee_basis_points"]) for e in ee)),
        "creator_fee_basis_points": sorted(set(int(e["creator_fee_basis_points"]) for e in ee)),
        "payer": payer, "network_fee_lamports": int(meta["fee"]),
        "network_fee_charged_to_user": payer == user,
        "native_plus_wsol_delta_lamports": cash_delta,
        "recoverable_rent_change_lamports": rent_change,
        "event_expected_cash_delta_lamports": expected_cash,
        "adjusted_cash_residual_lamports": residual,
        "transfers": native_transfer_rows(tx),
    }, "exact"


def summarize_rows(rows: list[dict], recipient_map: dict[str, str], external_map: dict[str, str], user: str) -> dict:
    network = [r["network_fee_lamports"] for r in rows if r["network_fee_charged_to_user"]]
    tips = []
    official_tips = []
    tip_receipts = 0
    official_tip_receipts = 0
    sample_costs = []
    official_costs = []
    physical_costs = []
    by_side: dict[str, list[dict]] = {"buy": [], "sell": []}
    quotes = [r["event_quote_lamports"] for r in rows]
    residuals = [r["adjusted_cash_residual_lamports"] for r in rows
                 if r["adjusted_cash_residual_lamports"] is not None]
    residual_reconciled = 0
    unexplained = []
    positive_residuals = []
    other_direct = 0
    other_direct_count = 0
    for r in rows:
        recognized = [x for x in r["transfers"] if x["source"] == user and x["destination"] in recipient_map]
        published = [x for x in r["transfers"] if x["source"] == user and x["destination"] in external_map]
        tip_sum = sum(x["lamports"] for x in recognized)
        official_sum = sum(x["lamports"] for x in published)
        tips.append(tip_sum)
        official_tips.append(official_sum)
        tip_receipts += tip_sum > 0
        official_tip_receipts += official_sum > 0
        other = [x for x in r["transfers"] if x["source"] == user and x["destination"] not in recipient_map]
        other_direct += sum(x["lamports"] for x in other)
        other_direct_count += len(other)
        if r["network_fee_charged_to_user"]:
            sample_costs.append(r["network_fee_lamports"] + tip_sum)
            official_costs.append(r["network_fee_lamports"] + official_sum)
        residual = r["adjusted_cash_residual_lamports"]
        if residual is not None:
            if abs(residual + tip_sum) <= 1:
                residual_reconciled += 1
            unexplained.append(-residual - tip_sum)
            residual_outflow = max(0, -residual)
            overhead = (r["network_fee_lamports"] if r["network_fee_charged_to_user"] else 0) + residual_outflow
            if residual > 0:
                positive_residuals.append(residual)
            physical_costs.append(overhead)
            by_side[r["side"]].append({
                "network_fee_lamports": r["network_fee_lamports"] if r["network_fee_charged_to_user"] else 0,
                "adjusted_residual_outflow_lamports": residual_outflow,
                "observed_overhead_lamports": overhead,
            })

    def counts(field: str) -> dict:
        c = Counter(v for r in rows for v in r[field])
        return {str(k): c[k] for k in sorted(c)}

    return {
        "sample_n": len(rows), "hash_sample": "smallest SHA-256(signature) values among exact receipts",
        "native_quote_lamports": quantiles(quotes),
        "event_fee_lamports": quantiles([r["event_fee_lamports"] for r in rows]),
        "creator_fee_lamports": quantiles([r["event_creator_fee_lamports"] for r in rows]),
        "event_fee_basis_points": counts("fee_basis_points"),
        "creator_fee_basis_points": counts("creator_fee_basis_points"),
        "network_fee_charged_to_user_lamports": quantiles(network),
        "configured_provider_tip_lamports_including_zero": quantiles(tips),
        "published_provider_tip_lamports_including_zero": quantiles(official_tips),
        "receipts_with_configured_provider_transfer": tip_receipts,
        "receipts_with_published_provider_transfer": official_tip_receipts,
        "network_fee_plus_configured_tip_lamports": quantiles(sample_costs),
        "network_fee_plus_published_tip_lamports": quantiles(official_costs),
        "observed_network_fee_plus_adjusted_residual_outflow_lamports": quantiles(physical_costs),
        "observed_overhead_by_trade_side": {
            side: {
                "n": len(values),
                "network_fee_lamports": quantiles([v["network_fee_lamports"] for v in values]),
                "adjusted_residual_outflow_lamports": quantiles([v["adjusted_residual_outflow_lamports"] for v in values]),
                "paired_network_fee_plus_adjusted_residual_outflow_lamports": quantiles([v["observed_overhead_lamports"] for v in values]),
            }
            for side, values in by_side.items()
        },
        "cost_vs_assumptions": {
            "base_1505000_lamports": {
                "observed_overhead_receipts_at_or_below": sum(x <= BASE_COST for x in physical_costs),
                "observed_overhead_receipts_above": sum(x > BASE_COST for x in physical_costs),
                "share_of_median_native_quote_pct": (100 * BASE_COST / statistics.median(quotes)
                                                        if quotes else None),
            },
            "sensitivity_2916000_lamports": {
                "observed_overhead_receipts_at_or_below": sum(x <= SENSITIVITY_COST for x in physical_costs),
                "observed_overhead_receipts_above": sum(x > SENSITIVITY_COST for x in physical_costs),
                "share_of_median_native_quote_pct": (100 * SENSITIVITY_COST / statistics.median(quotes)
                                                        if quotes else None),
            },
            "configured_tip_attribution_only": {
                "base_receipts_at_or_below": sum(x <= BASE_COST for x in sample_costs),
                "base_receipts_above": sum(x > BASE_COST for x in sample_costs),
                "sensitivity_receipts_at_or_below": sum(x <= SENSITIVITY_COST for x in sample_costs),
                "sensitivity_receipts_above": sum(x > SENSITIVITY_COST for x in sample_costs),
            },
        },
        "cash_residual": {
            "receipts_with_computable_residual": len(residuals),
            "receipts_reconciled_to_configured_tip_within_1_lamport": residual_reconciled,
            "adjusted_residual_lamports": quantiles(residuals),
            "positive_adjusted_residual_unclassified_inflow_lamports": quantiles(positive_residuals),
            "unexplained_residual_after_configured_tip_lamports": quantiles(unexplained),
        },
        "other_direct_system_transfers_not_counted_as_tips": {
            "count": other_direct_count, "sample_sum_lamports": other_direct,
            "note": "Includes Pump quote/fee movements and possible account funding; never added to tip totals.",
        },
    }


def analyze_wallet(wallet: dict, manifest: dict, recipient_map: dict[str, str], external_map: dict[str, str]) -> dict:
    address = wallet["address"]
    coverage = manifest["wallets"][address]["history_summary"]
    if not coverage.get("full_rows_verified") or coverage.get("source_rows_status") != "full_transaction_and_meta":
        raise ValueError(f"noncanonical rows for {address}")
    exact_total = 0
    fail_count = fail_fee = payer_total_fee = payer_total_count = 0
    rows_seen = 0
    status_counts = Counter()
    exclusion_counts = Counter()
    heap: list = []
    all_block_times = []
    for tx in iter_history(address):
        rows_seen += 1
        meta = tx["meta"]
        ks = keys(tx)
        payer = ks[0] if ks else None
        if meta.get("err") is None:
            status_counts["success"] += 1
        else:
            status_counts["failed"] += 1
        if tx.get("blockTime") is not None:
            all_block_times.append(int(tx["blockTime"]))
        if payer == address:
            payer_total_count += 1
            payer_total_fee += int(meta["fee"])
            if meta.get("err") is not None:
                fail_count += 1
                fail_fee += int(meta["fee"])
        if meta.get("err") is not None:
            continue
        try:
            events = D.events(tx)
        except Exception:
            exclusion_counts["decoder_error"] += 1
            continue
        user_events = [e for e in events if e.get("user") == address]
        if not user_events:
            continue
        candidate, reason = exact_trade(tx, address, events)
        if candidate is None:
            exclusion_counts[reason] += 1
            continue
        exact_total += 1
        sample_heap_add(heap, candidate)

    if rows_seen != coverage["transaction_count"]:
        raise ValueError(f"manifest/input row count mismatch for {address}: {rows_seen} != {coverage['transaction_count']}")
    if fail_count != coverage["payer_failed_count"]:
        raise ValueError(f"manifest payer-failure mismatch for {address}: {fail_count} != {coverage['payer_failed_count']}")
    sample = [entry[2] for entry in sorted(heap, key=lambda x: (-x[0], x[1]))]
    sample_summary = summarize_rows(sample, recipient_map, external_map, address)

    # bottimus pays for authenticated child-owned trades; report these in a
    # separate sample because those receipts are not bottimus-owned positions.
    child_output = None
    if address == "bcnzSs3F6F3MG7utvEQHpd8A53nRBM8ZM4TfEs2Zmcp":
        child_count = 0
        child_heap: list = []
        child_exclusions = Counter()
        for tx in iter_history(address):
            if tx["meta"].get("err") is not None:
                continue
            ks = keys(tx)
            payer = ks[0] if ks else None
            if payer != address:
                continue
            try:
                events = D.events(tx)
            except Exception:
                child_exclusions["decoder_error"] += 1
                continue
            child_users = sorted({e.get("user") for e in events if e.get("user") and e.get("user") != address})
            exact_children = []
            for user in child_users:
                leg, reason = exact_trade(tx, user, events)
                if leg:
                    leg["payer_fee_lamports"] = int(tx["meta"]["fee"])
                    leg["network_fee_charged_to_user"] = True
                    leg["payer"] = address
                    leg["payer_transfers"] = [x for x in native_transfer_rows(tx) if x["source"] == address]
                    leg["recoverable_rent_change_lamports"] = None
                    leg["adjusted_cash_residual_lamports"] = None
                    exact_children.append(leg)
                else:
                    child_exclusions[reason] += 1
            # One exact child group per transaction avoids allocating one payer
            # fee or one tip among several owner/mint legs.
            if len(exact_children) == 1:
                leg = exact_children[0]
                leg["transfers"] = leg.pop("payer_transfers")
                child_count += 1
                sample_heap_add(child_heap, leg)
            elif len(exact_children) > 1:
                child_exclusions["multi_child_trade_receipt_unallocated"] += 1
        child_sample = [entry[2] for entry in sorted(child_heap, key=lambda x: (-x[0], x[1]))]
        child_output = {
            "exact_payer_linked_child_receipts": child_count,
            "sample": summarize_rows(child_sample, recipient_map, external_map, address),
            "sample_owner": "child event.user; each receipt has one exact child/mint group",
            "payer": address,
            "excluded": dict(child_exclusions),
            "interpretation": "Separate payer execution-cost evidence; not a direct bottimus-owned trade count or cycle.",
        }

    return {
        "name": wallet["name"], "address": address,
        "capture": {
            "status": coverage["status"], "full_transaction_meta_rows": rows_seen,
            "captured_from_unix": min(all_block_times) if all_block_times else None,
            "captured_to_unix": max(all_block_times) if all_block_times else None,
            "observed_status_counts": dict(status_counts),
            "payer_transactions": payer_total_count,
            "payer_network_fee_lamports": payer_total_fee,
            "payer_failed_transactions": fail_count,
            "payer_failed_network_fee_lamports": fail_fee,
            "payer_failed_average_fee_lamports": fail_fee / fail_count if fail_count else None,
        },
        "authenticated_direct_trade_receipts": exact_total,
        "sample": sample_summary,
        "strict_exclusions": dict(exclusion_counts),
        "payer_linked_children": child_output,
        "scope": "Captured receipts only. Not a complete 21-day comparison where page-cap truncation is reported.",
    }


def sol(lamports: int | float | None) -> float | None:
    return None if lamports is None else lamports / LAMPORTS


def make_markdown(report: dict) -> str:
    lines = [
        "# Observed execution costs for the 22-wallet sample",
        "",
        "This is a receipt-based cost audit, not a trade replay, profitability result or edge claim. It uses finalized captured history through the shared freeze **2026-10-12 04:12:05 UTC**. Six histories reached their natural end before the 10-page cap; sixteen are explicitly truncated at that cap and cover different date ranges. The 200-receipt sample per wallet is selected by the smallest SHA-256 signature hashes among exact authenticated trades, independent of outcomes.",
        "",
        "An authenticated row requires a successful official-IDL Pump trade event, `event.user` present as a transaction signer, a native-SOL quote, one changed owner-held mint, and exact equality between the event token amount(s) and the owner's pre/post token delta. The displayed Pump `fee` and `creator_fee` are protocol trade charges, separate from the transaction `meta.fee` and provider-recipient transfers. `buyback_fee` is a component of `fee`, not an additional charge.",
        "",
        "Provider-recipient transfers are counted only when the enhanced receipt parses a System transfer from the trade owner to a matching account. The locally configured recipient map comes from [bot_types.rs](../../src/bot/bot_types.rs); route used cannot be proven from the destination alone. Published addresses were checked against [0slot's tip-account list](https://0slot.trade/docs.php), [Jito's tip-account documentation](https://docs.jito.wtf/lowlatencytxnsend/), and [Helius Sender's account list](https://www.helius.dev/blog/zero-slot). Other System outflows are excluded from tip totals. These are minimum observed transfer amounts, not a claim that every provider or account family has been identified.",
        "",
        "## Per-wallet capture and sampled cost",
        "",
        "`observed overhead` is calculated per receipt as the wallet-paid `meta.fee` plus any negative rent-adjusted residual against the Pump event's expected cash delta. Positive residuals are reported separately as unclassified net inflows and are not treated as costs or offsets. Negative residuals can include unrecognized recipients, so they are not assigned to tip providers. Configured and externally published recipient transfers are shown separately as attribution evidence. Medians of paired per-receipt overhead need not equal the sum of component medians.",
        "",
        "| Wallet | History capture | Exact receipts | Sample | Median network fee (SOL) | Median published tip (SOL) | Median configured tip (SOL) | Median fee + adjusted residual outflow (SOL) | Median Pump fee / creator fee (SOL) | Payer-failed tx / fees (SOL) |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for w in report["wallets"]:
        s = w["sample"]
        net = s["network_fee_charged_to_user_lamports"]
        pub = s["published_provider_tip_lamports_including_zero"]
        cfg = s["configured_provider_tip_lamports_including_zero"]
        cost = s["observed_network_fee_plus_adjusted_residual_outflow_lamports"]
        pf = s["event_fee_lamports"]
        cf = s["creator_fee_lamports"]
        failed = w["capture"]["payer_failed_network_fee_lamports"]
        lines.append(
            f"| {w['name']} | {w['capture']['status']} / {w['capture']['full_transaction_meta_rows']:,} rows | "
            f"{w['authenticated_direct_trade_receipts']:,} | {s['sample_n']} | "
            f"{sol(net['median']) if net else 'n/a'} | {sol(pub['median']) if pub else 'n/a'} | "
            f"{sol(cfg['median']) if cfg else 'n/a'} | {sol(cost['median']) if cost else 'n/a'} | "
            f"{sol(pf['median']) if pf else 'n/a'} / {sol(cf['median']) if cf else 'n/a'} | "
            f"{w['capture']['payer_failed_transactions']:,} / {sol(failed):.9f} |"
        )
    russian = next(w for w in report["wallets"] if w["name"].lower() == "russianbot")
    bottom = next(w for w in report["wallets"] if w["name"].lower() == "bottom bidder")
    russian_base = russian["sample"]["cost_vs_assumptions"]["base_1505000_lamports"]
    bottom_base = bottom["sample"]["cost_vs_assumptions"]["base_1505000_lamports"]
    lines += [
        "",
        "## Russianbot and Bottom Bidder",
        "",
        "On the hash-selected exact-trade samples, Russianbot's median paired observed overhead was **{:.9f} SOL** (p95 {:.9f}); **all {}/{}** sampled receipts were at or below the 0.001505 SOL base reference. Only **{}/{}** residuals reconciled to a configured provider-recipient transfer; the rest remain unclassified but are included as outflows. Bottom Bidder's median was **{:.9f} SOL** (p95 {:.9f}), with **{} of {}** receipts above that base. The overhead uses each receipt's own payer fee plus any negative rent-adjusted event-cash residual, so unknown net outflows contribute without being called tips; positive residuals are kept separate as unclassified inflows. Russianbot's reported ticket is 0.095 SOL: the study's 0.001505 / 0.002916 SOL reference costs would equal {:.2f}% / {:.2f}% of that ticket. These figures compare explicit user-supplied assumptions with observed per-leg costs; they do not estimate profitability. The captured wallet samples differ in coverage and routing, so this is descriptive rather than a controlled sender comparison.".format(
            sol(russian["sample"]["observed_network_fee_plus_adjusted_residual_outflow_lamports"]["median"] or 0),
            sol(russian["sample"]["observed_network_fee_plus_adjusted_residual_outflow_lamports"]["p95_nearest_rank"] or 0),
            russian_base["observed_overhead_receipts_at_or_below"], russian["sample"]["sample_n"],
            russian["sample"]["cash_residual"]["receipts_reconciled_to_configured_tip_within_1_lamport"], russian["sample"]["sample_n"],
            sol(bottom["sample"]["observed_network_fee_plus_adjusted_residual_outflow_lamports"]["median"] or 0),
            sol(bottom["sample"]["observed_network_fee_plus_adjusted_residual_outflow_lamports"]["p95_nearest_rank"] or 0),
            bottom_base["observed_overhead_receipts_above"], bottom["sample"]["sample_n"],
            100 * BASE_COST / 95_000_000, 100 * SENSITIVITY_COST / 95_000_000),
        "",
        "| Wallet | Side | Sample n | Median network fee (SOL) | Median residual outflow (SOL) | Median paired overhead (SOL) | p95 paired overhead (SOL) |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for wallet in (russian, bottom):
        for side in ("buy", "sell"):
            s = wallet["sample"]["observed_overhead_by_trade_side"][side]
            nf = s["network_fee_lamports"]
            rr = s["adjusted_residual_outflow_lamports"]
            paired = s["paired_network_fee_plus_adjusted_residual_outflow_lamports"]
            lines.append(
                f"| {wallet['name']} | {side} | {s['n']} | {sol(nf['median']) if nf else 'n/a'} | "
                f"{sol(rr['median']) if rr else 'n/a'} | {sol(paired['median']) if paired else 'n/a'} | "
                f"{sol(paired['p95_nearest_rank']) if paired else 'n/a'} |"
            )
    lines += [
        "",
        "The source-checked examples below show why `meta.fee` alone and outbound transfers alone each miss part of execution cost. They are case checks, not added to the hash-selected samples:",
        "",
        "| Wallet / signature prefix | Pump event SOL amount | Pump `fee` + `creator_fee` | Rent reserve change | `meta.fee` | Provider-recipient transfer | Adjusted residual | Observed overhead |",
        "|---|---:|---:|---:|---:|---|---:|---:|",
    ]
    for c in report["source_receipt_checks"]:
        lines.append(
            f"| {c['wallet']} / `{c['signature_prefix']}` | {sol(c['event_quote_lamports']):.9f} | "
            f"{sol(c['event_fee_lamports']):.9f} + {sol(c['event_creator_fee_lamports']):.9f} | "
            f"{sol(c['recoverable_rent_change_lamports']):.9f} | {sol(c['meta_fee_lamports']):.9f} | "
            f"{c['recipient_label']} {sol(c['recipient_lamports']):.9f} | "
            f"{sol(c['adjusted_cash_residual_lamports']):.9f} | {sol(c['observed_overhead_lamports']):.9f} |"
        )
    lines += [
        "",
        "Russianbot's checked 0slot destination matches the published 0slot address list. Cbot7's destination also appears there. Bottom Bidder's recipient is mapped to Nozomi by the project's configured account list; the provider route itself is not inferable from a successful transfer. Pump `fee` and `creator_fee` are event-level protocol charges and are distinct from `meta.fee` and the residual. No unclassified residual is labeled as a tip.",
        "",
        "## Residual and payer failures",
        "",
        "For each sampled exact trade, the script compares owner native-plus-WSOL balance change (adjusted for the change in rent held by that owner's token accounts) to the official Pump event cash amount. It adds back `meta.fee` when the trade owner paid it. A residual is considered reconciled only when it equals the negative of parsed configured-recipient transfers within one lamport. Negative residuals unmatched to configured recipients remain unexplained and contribute to the overhead proxy; positive residuals are shown separately as unclassified net inflows. Russianbot's paired cost is not the lower identified-recipient-only subtotal: only receipts with a matching configured account transfer receive that label. Full captured-history payer-failed fee sums are listed separately above, including failed receipts beyond the 200-trade samples.",
        "",
        "bottimus (`bcnz...`) payer-linked child trades are stored separately in JSON. Child event-user token ownership is kept distinct from the payer's network fee/tip; they are not counted as direct bottimus-owned trade receipts.",
        "",
        "## Limits",
        "",
        "The enhanced API capture stopped at 10 history pages per wallet where that cap was reached. Consequently, failed-fee totals are complete only for each wallet's captured pages, and wallet medians are not aligned to a common interval. The SHA-256 sample is a reproducible descriptive sample, not a randomized population estimate. Provider recipient identity does not reveal the sender route; locally configured provider accounts beyond published lists are labeled as configured rather than independently verified. No hypothetical fill, PnL, or strategy edge is estimated.",
        "",
    ]
    return "\n".join(lines)


def source_receipt_checks(recipient_map: dict[str, str]) -> list[dict]:
    # Three direct signature proofs supplied and independently inspected by the parent.
    checks = [
        ("russianbot", "nya666pQkP3PzWxi7JngU3rRMHuc7zbLK8c8wxQ4qpT", "6WbajoMNCCMPAbUcKgsM7KJ5pdy6skgc8hezrPMtfD5jnsiNqVwX2BgHu2jJkndkMtWyi2YVWhcXpkMnMj6JQEc"),
        ("Cbot7", "97jv9pjCf5D7VUZEyj6XnXBC5JF23Vsagc3bvSF6GRmL", "4fi1SbrMj7S4RtKi9QZ4FN59GfkkYKzsYts3vGRkvTaYzMHogB7Ny56zZJ8foCfx5asW1iQyS4JiF4p2nNux2Cxi"),
        ("Bottom Bidder", "8dtx2tr4TuJsYpri2suggFu1pg3DVjFLBBVmhtDy1MEF", "3azUGwM3ReSynsPfZfBg9TzgGUCH3QR3Lfam4eKhAq2qQEdhYCbCCRVd9KS6eL7P1DS3cQJWLssDnoxyzXKro4AJ"),
    ]
    result = []
    for name, address, signature in checks:
        found = None
        for tx in iter_history(address):
            sig = (tx.get("transaction", {}).get("signatures") or [None])[0]
            if sig == signature:
                found = tx
                break
        if found is None:
            raise ValueError(f"source proof missing from full history: {signature}")
        events = [e for e in D.events(found) if e.get("user") == address]
        if len(events) != 1:
            raise ValueError(f"source proof event count changed: {signature}")
        event = events[0]
        leg, reason = exact_trade(found, address, D.events(found))
        if leg is None:
            raise ValueError(f"source proof failed exact owner-delta check ({reason}): {signature}")
        transfers = [x for x in native_transfer_rows(found)
                     if x["source"] == address and x["destination"] in recipient_map]
        if len(transfers) != 1:
            raise ValueError(f"source proof provider transfer mismatch: {signature}")
        result.append({
            "wallet": name, "address": address, "signature_prefix": signature[:12],
            "event_quote_lamports": int(event["sol_amount"]),
            "event_fee_lamports": int(event["fee"]),
            "event_creator_fee_lamports": int(event["creator_fee"]),
            "meta_fee_lamports": int(found["meta"]["fee"]),
            "recoverable_rent_change_lamports": leg["recoverable_rent_change_lamports"],
            "adjusted_cash_residual_lamports": leg["adjusted_cash_residual_lamports"],
            "observed_overhead_lamports": ((int(found["meta"]["fee"]) if leg["network_fee_charged_to_user"] else 0)
                                           + max(0, -(leg["adjusted_cash_residual_lamports"] or 0))),
            "recipient": transfers[0]["destination"],
            "recipient_label": recipient_map[transfers[0]["destination"]],
            "recipient_lamports": transfers[0]["lamports"],
            "payer": keys(found)[0],
        })
    return result


def main() -> None:
    wallets = json.loads(WALLETS.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if len(wallets) != 22 or manifest.get("wallet_count") != 22:
        raise ValueError("expected the frozen 22-wallet roster")
    recipient_map, external_map = provider_recipients()
    results = []
    for i, wallet in enumerate(wallets, 1):
        item = analyze_wallet(wallet, manifest, recipient_map, external_map)
        results.append(item)
        print(f"{i:02d}/22 {wallet['name']}: {item['authenticated_direct_trade_receipts']} exact; sample {item['sample']['sample_n']}; failed payer fees {item['capture']['payer_failed_network_fee_lamports']} lamports", flush=True)

    check_rows = source_receipt_checks(recipient_map)
    freeze = json.loads((HERE / "raw_wallets/freeze.json").read_text(encoding="utf-8"))
    report = {
        "schema_version": 1,
        "study": "observed_execution_costs",
        "generated_from": {
            "wallet_roster": "wallets.json", "canonical_history": "raw_wallets/history/{address}/page-*.json.gz",
            "collection_manifest": "collection.json", "strict_decoder": "research/day_general_20261004/helpers/decoder.py",
        },
        "freeze": freeze,
        "sample_size_cap_per_wallet": SAMPLE_N,
        "sample_selection": "exact authenticated trade receipts ranked by SHA-256(signature), lowest first; independent of outcomes",
        "assumed_per_leg_cost_lamports": {"base": BASE_COST, "sensitivity": SENSITIVITY_COST},
        "recognized_provider_recipient_accounts": {
            "local_project_static_count": len(recipient_map), "published_external_count": len(external_map),
            "local_project_map_source": "src/bot/bot_types.rs; maps are configured account identities, not route evidence",
            "externally_published_sources": [
                "https://0slot.trade/docs.php", "https://docs.jito.wtf/lowlatencytxnsend/", "https://www.helius.dev/blog/zero-slot",
            ],
        },
        "wallets": results,
        "source_receipt_checks": check_rows,
        "notes": [
            "meta.fee is attributed only to the first account key transaction payer; a signed transaction may be sponsored.",
            "Provider-recipient transfers are observed transfers to configured/published addresses. This does not prove which route carried the transaction.",
            "Pump fee and creator_fee event fields are kept separate from network fee and tips; buyback_fee and holder_rewards are not added to fee again.",
            "Payer-failed transaction fee totals are complete only within captured pages; histories with status truncated_page_cap are not full 21-day histories.",
            "No hypothetical execution, profitability, PnL, or strategy-edge claim is made.",
        ],
    }
    OUT_JSON.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    OUT_MD.write_text(make_markdown(report), encoding="utf-8")
    print(f"wrote {OUT_JSON.name} and {OUT_MD.name}; 22 wallets; source-checks={len(check_rows)}")


if __name__ == "__main__":
    main()
