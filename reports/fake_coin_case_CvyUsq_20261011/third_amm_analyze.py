#!/usr/bin/env python3
"""Summarize the frozen DgT6h snapshots and one bounded AMM RPC capture."""
from __future__ import annotations

import collections
import datetime as dt
import json
from pathlib import Path

CASE = Path(__file__).resolve().parent
MINT = "DgT6hpeJzS3yW5UjcUvT4grfXogM1XvMwFKmrU4Vpump"
POOL = "7LAx8jrRB5zXgeH69RXs2FwXjmoXzTUXwfUU1fPrHbpc"
BASE_VAULT = "CXa9yFKacD14aorShxWcL1x7MwGhBG18K6KtQN9nVWge"
QUOTE_VAULT = "DLx6wfCAdH2t9WJ7oUcxYo4A1yFP6Lfh5DmGpbwKU57y"
WSOL = "So11111111111111111111111111111111111111112"


def read_json(name):
    return json.loads((CASE / name).read_text())


def iso_ms(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def iso_s(sec):
    return dt.datetime.fromtimestamp(sec, dt.timezone.utc).isoformat().replace("+00:00", "Z")


def vault_amount(tx, vault, mint, field):
    meta = tx.get("meta") or {}
    keys = tx["transaction"]["message"].get("accountKeys", [])
    for b in meta.get(field) or []:
        if b.get("mint") != mint:
            continue
        i = b.get("accountIndex")
        if i is None or i >= len(keys):
            continue
        key = keys[i]
        pubkey = key.get("pubkey") if isinstance(key, dict) else key
        if pubkey == vault:
            amount = (b.get("uiTokenAmount") or {}).get("amount")
            return int(amount) if amount is not None else None
    return None


def owner_amounts(tx, field):
    amounts = collections.defaultdict(int)
    for b in (tx.get("meta") or {}).get(field) or []:
        if b.get("mint") != MINT:
            continue
        owner = b.get("owner")
        raw = (b.get("uiTokenAmount") or {}).get("amount")
        if owner and raw is not None:
            amounts[owner] += int(raw)
    return dict(amounts)


def signers(tx):
    out = set()
    for k in tx["transaction"]["message"].get("accountKeys", []):
        if isinstance(k, dict) and k.get("signer"):
            out.add(k.get("pubkey"))
    return out


def decoded(sig, tx):
    meta = tx.get("meta") or {}
    q0, q1 = vault_amount(tx, QUOTE_VAULT, WSOL, "preTokenBalances"), vault_amount(tx, QUOTE_VAULT, WSOL, "postTokenBalances")
    b0, b1 = vault_amount(tx, BASE_VAULT, MINT, "preTokenBalances"), vault_amount(tx, BASE_VAULT, MINT, "postTokenBalances")
    if None in (q0, q1, b0, b1):
        return None
    pre, post = owner_amounts(tx, "preTokenBalances"), owner_amounts(tx, "postTokenBalances")
    changes = {w: post.get(w, 0) - pre.get(w, 0) for w in set(pre) | set(post)}
    changes.pop(POOL, None)
    names = [line.split("Program log: Instruction:", 1)[1].strip() for line in (meta.get("logMessages") or []) if "Program log: Instruction:" in line]
    sold = sorted(w for w, change in changes.items() if change < 0)
    return {
        "signature": sig, "slot": tx.get("slot"), "block_time": tx.get("blockTime"),
        "success": meta.get("err") is None,
        "quote_pre_lamports": q0, "quote_post_lamports": q1, "quote_delta_lamports": q1 - q0,
        "base_pre_raw": b0, "base_post_raw": b1, "base_delta_raw": b1 - b0,
        "instructions": names, "seller_owners": sold, "seller_signers": sorted(set(sold) & signers(tx)),
        "owner_token_delta_raw": changes,
    }


def main():
    snap_rows = [json.loads(line) for line in (CASE / "third_ghost_amm_evidence.jsonl").open()]
    snaps = []
    for row in snap_rows:
        s = row.get("snapshot") or {}
        if s.get("pool") != POOL or s.get("mint") != MINT:
            continue
        snaps.append({
            "event": row.get("event"), "observed_at_ms": int(s["observed_at_ms"]),
            "slot": s.get("context_slot"), "quote_raw": int(s["quote_reserve_raw"]),
            "virtual_raw": int(s["virtual_quote_reserve_raw"]), "base_raw": int(s["base_reserve_raw"]),
            "supply_raw": int(s["base_supply_raw"]), "source": s.get("source"),
        })
    snaps.sort(key=lambda x: x["observed_at_ms"])
    deltas = []
    for a, b in zip(snaps, snaps[1:]):
        dq = a["quote_raw"] - b["quote_raw"]
        if dq > 0:
            deltas.append({
                "from": a, "to": b, "quote_drop_sol": dq / 1e9,
                "drop_pct": dq / a["quote_raw"] * 100,
                "observer_elapsed_ms": b["observed_at_ms"] - a["observed_at_ms"],
            })
    largest = max(deltas, key=lambda x: x["drop_pct"])
    largest_abs = max(deltas, key=lambda x: x["quote_drop_sol"])
    peak, trough = max(snaps, key=lambda x: x["quote_raw"]), min(snaps, key=lambda x: x["quote_raw"])
    last = snaps[-1]

    sigs = read_json("third_amm_pool_signatures.json")
    selection = read_json("third_amm_tx_selection.json")
    fetched = read_json("third_amm_pool_transactions.json")
    state = read_json("third_amm_current_pool_state.json")
    tx_rows = [x for sig, tx in fetched["transactions"].items() if (x := decoded(sig, tx)) is not None]
    incident = [x for x in tx_rows if x["block_time"] is not None and 1791762910 <= x["block_time"] <= 1791762925]
    sells = [x for x in incident if x["quote_delta_lamports"] < 0 and x["base_delta_raw"] > 0]
    buys = [x for x in incident if x["quote_delta_lamports"] > 0 and x["base_delta_raw"] < 0]
    all_sells = [x for x in tx_rows if x["quote_delta_lamports"] < 0 and x["base_delta_raw"] > 0]
    all_buys = [x for x in tx_rows if x["quote_delta_lamports"] > 0 and x["base_delta_raw"] < 0]
    fee_sweep_rows = []
    withdrawal_rows = []
    for sig, tx in fetched.get("transactions", {}).items():
        if not tx:
            continue
        logs = (tx.get("meta") or {}).get("logMessages") or []
        instructions = [line.split("Program log: Instruction:", 1)[1].strip() for line in logs if "Program log: Instruction:" in line]
        slot, block_time = tx.get("slot"), tx.get("blockTime")
        q0 = vault_amount(tx, QUOTE_VAULT, WSOL, "preTokenBalances")
        q1 = vault_amount(tx, QUOTE_VAULT, WSOL, "postTokenBalances")
        b0 = vault_amount(tx, BASE_VAULT, MINT, "preTokenBalances")
        b1 = vault_amount(tx, BASE_VAULT, MINT, "postTokenBalances")
        if any("sweep" in name.lower() for name in instructions):
            fee_sweep_rows.append({"signature": sig, "slot": slot, "block_time_utc": iso_s(block_time) if block_time else None, "instructions": instructions, "quote_delta_sol": (q1 - q0) / 1e9 if q0 is not None and q1 is not None else None, "base_delta_tokens": (b1 - b0) / 1e6 if b0 is not None and b1 is not None else None})
        if any("withdraw" in name.lower() for name in instructions):
            withdrawal_rows.append({"signature": sig, "slot": slot, "block_time_utc": iso_s(block_time) if block_time else None, "instructions": instructions})
    by_seller = collections.defaultdict(lambda: {"sell_quote_lamports": 0, "tokens_sold_raw": 0, "signer_tx_count": 0, "signatures": []})
    for x in sells:
        for seller in x["seller_owners"]:
            item = by_seller[seller]
            item["sell_quote_lamports"] += -x["quote_delta_lamports"]
            item["tokens_sold_raw"] += -x["owner_token_delta_raw"].get(seller, 0)
            item["signer_tx_count"] += seller in x["seller_signers"]
            item["signatures"].append(x["signature"])
    top_sellers = [{"owner": owner, **values} for owner, values in by_seller.items()]
    top_sellers.sort(key=lambda x: x["sell_quote_lamports"], reverse=True)
    for row in top_sellers:
        row["sell_quote_sol"] = row["sell_quote_lamports"] / 1e9
        row["tokens_sold"] = row["tokens_sold_raw"] / 1e6

    curve_ledger = collections.defaultdict(lambda: {"buy_count": 0, "sell_count": 0, "buy_tokens_raw": 0, "sell_tokens_raw": 0})
    curve_event_count = 0
    with (CASE / "third_ghost_observations.jsonl").open() as stream:
        for line in stream:
            observation = json.loads(line)
            for event in observation.get("events", []):
                if event.get("mint") != MINT or not event.get("user"):
                    continue
                curve_event_count += 1
                record = curve_ledger[event["user"]]
                side = "buy" if event.get("is_buy") else "sell"
                record[f"{side}_count"] += 1
                record[f"{side}_tokens_raw"] += int(event.get("tokens_raw") or 0)
    incident_seller_set = {owner for x in sells for owner in x["seller_owners"]}
    curve_overlap = incident_seller_set & set(curve_ledger)
    pregrad_top_sellers = []
    for seller in top_sellers[:5]:
        provenance = curve_ledger.get(seller["owner"])
        pregrad_top_sellers.append({
            "owner": seller["owner"], "amm_tokens_sold": seller["tokens_sold"],
            "curve_observed": provenance is not None,
            "curve_buy_count": provenance["buy_count"] if provenance else 0,
            "curve_sell_count": provenance["sell_count"] if provenance else 0,
            "curve_buy_tokens": provenance["buy_tokens_raw"] / 1e6 if provenance else None,
            "curve_sell_tokens": provenance["sell_tokens_raw"] / 1e6 if provenance else None,
            "curve_net_at_frozen_cutoff_tokens": (provenance["buy_tokens_raw"] - provenance["sell_tokens_raw"]) / 1e6 if provenance else None,
            "amm_sell_matches_curve_net_raw": provenance is not None and seller["tokens_sold_raw"] == provenance["buy_tokens_raw"] - provenance["sell_tokens_raw"],
            "curve_net_minus_amm_sold_raw": (provenance["buy_tokens_raw"] - provenance["sell_tokens_raw"] - seller["tokens_sold_raw"]) if provenance else None,
        })

    # Cvy's fully decoded rapid-burst seller set and the earlier repeat sellers.
    cvy_body = read_json("amm_pool_transactions.json").get("transactions", {})
    cvy_sellers = set()
    for sig, tx in cvy_body.items():
        if not (455832951 <= tx.get("slot", 0) <= 455832959) or (tx.get("meta") or {}).get("err") is not None:
            continue
        pre, post = owner_amounts(tx, "preTokenBalances"), owner_amounts(tx, "postTokenBalances")
        for owner in set(pre) | set(post):
            if owner != "EjzRfGWpvRSqmayWnHT3WkKp63jXAzZwhEUVNkwapwdr" and post.get(owner, 0) < pre.get(owner, 0):
                cvy_sellers.add(owner)
    repeated_77axs = {
        "98MLcc4UVzeLaDWckcBUCMcwS5CgSeqAjC4g2JNQ714c",
        "CGbLazQt5HXNPawzFct36WeFwj8dL4vGUd8KRHSJ1iCX",
        "53MN5hAAGHu8Q8HM8ZCaenWYsBma4qTHD9Lp6ETKdLrL",
        "mMpEUcCgvHmdXvkrawYszRZpXTVfp1E2rDCc4vtGfdw",
    }
    top20_repeat = {
        "B9ksmPhuhj43BBWXJxm1SUXDbVZRthmvf8FZMpYhVhoH",
        "CMcKT7wshBUjRrPy6uH4bdTRkmxFLngQh2kTXrrzRVdC",
        "Hy4ZuryDVXuytB3TGXmAdcqHQeF7WMQD4dZLdAipyVFt",
        "7dGV2auDmovmUbb27KBW1QNN52aLXd4ZZbafG9nyr5VT",
    }
    # Parent's prior bounded funding sample for the Cfiyy second case.
    second_manifest = read_json("second_rpc_manifest.json")
    second_transfers = read_json("second_rpc_incoming_transfers.json")
    third_manifest = read_json("third_rpc_manifest.json")
    cfiyy_sample_wallets = set(second_manifest.get("wallets", []))
    for item in second_transfers:
        cfiyy_sample_wallets.update(x for x in (item.get("source"), item.get("destination")) if x)
    seller_set = set(by_seller)
    all_seller_owners = {owner for x in all_sells for owner in x["seller_owners"]}
    current_state = {
        "observed_at_utc": state["observed_at_utc"], "slot": state["context_slot"],
        "actual_quote_reserve_sol": int(state["quote_reserve_raw"]) / 1e9,
        "base_reserve_tokens": int(state["base_reserve_raw"]) / 1e6,
        "supply_tokens": int(state["base_supply_raw"]) / 1e6,
    }
    result = {
        "target": {"mint": MINT, "pool": POOL, "base_vault": BASE_VAULT, "quote_vault": QUOTE_VAULT},
        "frozen_snapshot_coverage": {"rows": len(snaps), "first_utc": iso_ms(snaps[0]["observed_at_ms"]), "last_utc": iso_ms(last["observed_at_ms"]), "first_source": snaps[0]["source"], "last_source": last["source"]},
        "largest_sequential_observed_quote_drop": {
            "from_utc": iso_ms(largest["from"]["observed_at_ms"]), "from_slot": largest["from"]["slot"], "from_quote_sol": largest["from"]["quote_raw"] / 1e9,
            "to_utc": iso_ms(largest["to"]["observed_at_ms"]), "to_slot": largest["to"]["slot"], "to_quote_sol": largest["to"]["quote_raw"] / 1e9,
            "decline_pct": largest["drop_pct"], "observer_elapsed_ms": largest["observer_elapsed_ms"],
            "from_virtual_quote_sol": largest["from"]["virtual_raw"] / 1e9, "to_virtual_quote_sol": largest["to"]["virtual_raw"] / 1e9,
            "from_base_tokens": largest["from"]["base_raw"] / 1e6, "to_base_tokens": largest["to"]["base_raw"] / 1e6,
        },
        "largest_absolute_sequential_quote_drop": {
            "from_utc": iso_ms(largest_abs["from"]["observed_at_ms"]), "from_quote_sol": largest_abs["from"]["quote_raw"] / 1e9,
            "to_utc": iso_ms(largest_abs["to"]["observed_at_ms"]), "to_quote_sol": largest_abs["to"]["quote_raw"] / 1e9,
            "decline_pct": largest_abs["drop_pct"], "observer_elapsed_ms": largest_abs["observer_elapsed_ms"],
        },
        "sample_peak_to_trough": {
            "peak_utc": iso_ms(peak["observed_at_ms"]), "peak_quote_sol": peak["quote_raw"] / 1e9,
            "trough_utc": iso_ms(trough["observed_at_ms"]), "trough_quote_sol": trough["quote_raw"] / 1e9,
            "decline_pct": (peak["quote_raw"] - trough["quote_raw"]) / peak["quote_raw"] * 100,
            "last_utc": iso_ms(last["observed_at_ms"]), "last_quote_sol": last["quote_raw"] / 1e9,
        },
        "rpc_signature_coverage": {
            "fetched_at_utc": sigs["fetched_at_utc"], "pages_returned": sigs["pages_returned"],
            "page_cap": sigs["max_pages"], "unique_signatures": sigs["unique_signature_count"],
            "success_signatures": sigs["successful_count"], "failed_signatures": sigs["failed_count"],
            "oldest_signature_time_utc": iso_s(sigs["oldest_block_time_unix"]), "newest_signature_time_utc": iso_s(sigs["newest_block_time_unix"]),
            "history_exhausted": sigs["stop_reason"] == "history_exhausted",
            "selected_success_bodies": selection["selected_count"], "returned_bodies": fetched["returned_count"],
            "unresolved_bodies": fetched["rpc_failures"],
        },
        "incident_transaction_slice": {
            "block_time_window_utc": selection["incident_block_time_window_utc"],
            "returned_transactions_with_both_vault_deltas": len(incident), "observed_sells": len(sells), "observed_buys": len(buys),
            "distinct_seller_owners": len(by_seller), "seller_owner_is_signer_tx_count": sum(x["signer_tx_count"] for x in top_sellers),
            "gross_sell_quote_out_sol": sum(-x["quote_delta_lamports"] for x in sells) / 1e9,
            "gross_buy_quote_in_sol": sum(x["quote_delta_lamports"] for x in buys) / 1e9,
            "net_quote_vault_change_sol": sum(x["quote_delta_lamports"] for x in incident) / 1e9,
            "gross_tokens_sold_into_pool": sum(x["base_delta_raw"] for x in sells) / 1e6,
            "withdraw_instruction_seen": any("withdraw" in name.lower() for x in incident for name in x["instructions"]),
            "program_instructions": dict(collections.Counter(name for x in incident for name in x["instructions"])),
            "top_sellers": top_sellers[:12],
            "txs": [{k: x[k] for k in ("signature", "slot", "block_time", "quote_pre_lamports", "quote_post_lamports", "quote_delta_lamports", "base_delta_raw", "instructions", "seller_owners", "seller_signers")} for x in incident],
        },
        "all_selected_transaction_slice": {
            "returned_transactions_with_both_vault_deltas": len(tx_rows),
            "block_time_start_utc": iso_s(min((x["block_time"] for x in tx_rows if x["block_time"] is not None), default=0)),
            "block_time_end_utc": iso_s(max((x["block_time"] for x in tx_rows if x["block_time"] is not None), default=0)),
            "observed_sells": len(all_sells), "observed_buys": len(all_buys),
            "distinct_seller_owners": len(all_seller_owners),
            "gross_sell_quote_out_sol": sum(-x["quote_delta_lamports"] for x in all_sells) / 1e9,
            "gross_buy_quote_in_sol": sum(x["quote_delta_lamports"] for x in all_buys) / 1e9,
            "seller_owners": sorted(all_seller_owners),
        },
        "withdrawal_and_fee_sweep_checks": {
            "withdraw_instruction_count_in_recovered_pool_transactions": len(withdrawal_rows),
            "withdraw_instructions": withdrawal_rows,
            "fee_sweep_instruction_transactions": fee_sweep_rows,
            "note": "Fee-sweep instructions are recorded separately from a PumpSwap liquidity withdrawal; no withdrawal instruction was logged in the recovered body set.",
        },
        "known_wallet_match": {
            "incident_seller_count": len(seller_set),
            "all_selected_seller_count": len(all_seller_owners),
            "all_selected_sellers_matching_third_manifest_wallets": sorted(all_seller_owners & set(third_manifest.get("wallets", []))),
            "incident_sellers_matching_third_manifest_wallets": sorted(incident_seller_set & set(third_manifest.get("wallets", []))),
            "all_selected_sellers_matching_cvy_rapid_burst": sorted(all_seller_owners & cvy_sellers),
            "all_selected_sellers_matching_prior_77axs_repeat_sellers": sorted(all_seller_owners & repeated_77axs),
            "all_selected_sellers_matching_cvy_top_repeat20_four": sorted(all_seller_owners & top20_repeat),
            "all_selected_sellers_matching_cfiyy_bounded_funding_sample": sorted(all_seller_owners & cfiyy_sample_wallets),
            "all_selected_sellers_matching_root_reported_cross_case_funded_wallets": sorted(w for w in all_seller_owners if w.startswith(("B1f", "BMx", "7pVS", "Bbi", "Fabbi"))),
            "cfiyy_bounded_wallet_scope_size": len(cfiyy_sample_wallets),
            "pregraduation_curve_receipt_comparison": {
                "frozen_curve_event_count": curve_event_count,
                "frozen_curve_user_count": len(curve_ledger),
                "incident_sellers_in_frozen_curve_user_set": len(curve_overlap),
                "incident_seller_count": len(incident_seller_set),
                "top_five_incident_seller_curve_provenance": pregrad_top_sellers,
            "scope": "owner membership/observed receipts from the frozen local curve file; absence is not proof of no prior tokens or outside transfer",
            },
            "warning": "address overlap is not proof of common ownership; Cfiyy comparison is limited to the selected manifest wallets and recipients/sources in its bounded transfer sample",
        },
        "finalized_account_state": current_state,
        "limits": [
            "The 124-snapshot local series measures observer arrival time, not exact transaction-to-transaction elapsed execution time.",
            "Pool signature history hit the two-page cap and does not reach the AMM opening; it covers the successful activity in the observed reserve-break window.",
            "Transaction bodies are bounded; two selected bodies remain unavailable, one inside the steep sampled-reserve-break second and one later. A third previously missing body was recovered by the one targeted Alchemy retry.",
            "The confirmed/finalized account sample is a later point in time than the frozen post-exit series and is not an estimate of stop execution quality.",
            "No market-cap USD conversion or profitability/PnL estimate is made.",
        ],
    }
    (CASE / "third_amm_analysis.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
