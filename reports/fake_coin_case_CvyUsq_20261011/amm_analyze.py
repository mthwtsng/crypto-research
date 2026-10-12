#!/usr/bin/env python3
"""Reproducible, read-only summaries for the Cvy post-graduation AMM trace."""

from __future__ import annotations

import collections
import datetime as dt
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CASE = Path(__file__).resolve().parent
MINT = "CvyUsq67bCiZZwr1dZKu2y1HXojjrz6tvdkKY4XGpump"
POOL = "EjzRfGWpvRSqmayWnHT3WkKp63jXAzZwhEUVNkwapwdr"
BASE_VAULT = "F1FNLwTSUvHKjbhbt3vQxkgvLThtka3uXKThMtB16wRm"
QUOTE_VAULT = "HxYqEmJfdwT51M3bNgw11xFYTByM2yBjnqyqQ8pqCuPt"
WSOL = "So11111111111111111111111111111111111111112"
FROZEN_LAST_MS = 1791761901633  # 2026-10-11T23:38:21.633Z; freeze the local snapshot series here.


def read_json(path: Path):
    return json.loads(path.read_text())


def iso_ms(ms: int) -> str:
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def iso_s(seconds: int) -> str:
    return dt.datetime.fromtimestamp(seconds, dt.timezone.utc).isoformat().replace("+00:00", "Z")


def token_balance_index(tx: dict, vault: str, mint: str, field: str) -> int | None:
    meta = tx.get("meta") or {}
    for balance in meta.get(field) or []:
        if balance.get("mint") == mint:
            keys = tx["transaction"]["message"]["accountKeys"]
            index = balance.get("accountIndex")
            if index is None or index >= len(keys):
                continue
            key = keys[index]
            pubkey = key.get("pubkey") if isinstance(key, dict) else key
            if pubkey == vault:
                amount = (balance.get("uiTokenAmount") or {}).get("amount")
                return int(amount) if amount is not None else None
    return None


def owner_amounts(tx: dict, mint: str, field: str) -> dict[str, int]:
    out: dict[str, int] = collections.defaultdict(int)
    meta = tx.get("meta") or {}
    for balance in meta.get(field) or []:
        if balance.get("mint") != mint:
            continue
        owner = balance.get("owner")
        amount = (balance.get("uiTokenAmount") or {}).get("amount")
        if owner and amount is not None:
            out[owner] += int(amount)
    return dict(out)


def tx_signers(tx: dict) -> set[str]:
    out = set()
    for key in tx["transaction"]["message"].get("accountKeys", []):
        if isinstance(key, dict) and key.get("signer"):
            out.add(key["pubkey"])
    return out


def pool_deltas(sig: str, tx: dict) -> dict | None:
    meta = tx.get("meta") or {}
    q_pre = token_balance_index(tx, QUOTE_VAULT, WSOL, "preTokenBalances")
    q_post = token_balance_index(tx, QUOTE_VAULT, WSOL, "postTokenBalances")
    b_pre = token_balance_index(tx, BASE_VAULT, MINT, "preTokenBalances")
    b_post = token_balance_index(tx, BASE_VAULT, MINT, "postTokenBalances")
    if None in (q_pre, q_post, b_pre, b_post):
        return None
    pre_owner = owner_amounts(tx, MINT, "preTokenBalances")
    post_owner = owner_amounts(tx, MINT, "postTokenBalances")
    owners = set(pre_owner) | set(post_owner)
    owner_delta = {owner: post_owner.get(owner, 0) - pre_owner.get(owner, 0) for owner in owners}
    owner_delta.pop(POOL, None)
    sellers = sorted(owner for owner, delta in owner_delta.items() if delta < 0)
    logs = meta.get("logMessages") or []
    instruction_names = []
    for log in logs:
        if "Program log: Instruction:" in log:
            instruction_names.append(log.split("Program log: Instruction:", 1)[1].strip())
    signers = tx_signers(tx)
    return {
        "signature": sig,
        "slot": tx.get("slot"),
        "block_time_unix": tx.get("blockTime"),
        "block_time_utc": iso_s(tx["blockTime"]) if tx.get("blockTime") else None,
        "success": meta.get("err") is None,
        "quote_pre_lamports": q_pre,
        "quote_post_lamports": q_post,
        "quote_delta_lamports": q_post - q_pre,
        "base_pre_raw": b_pre,
        "base_post_raw": b_post,
        "base_delta_raw": b_post - b_pre,
        "instructions": instruction_names,
        "sellers": sellers,
        "seller_signers": sorted(set(sellers) & signers),
        "owner_token_deltas_raw": owner_delta,
    }


def chained_order(rows: list[dict]) -> list[dict]:
    """Sort same-slot reserve movements by exact quote-vault pre/post continuity."""
    out = []
    for slot in sorted({r["slot"] for r in rows}):
        pending = [r for r in rows if r["slot"] == slot]
        # The first movement has a pre-state no other transaction in the slot produced.
        produced = {r["quote_post_lamports"] for r in pending}
        starts = [r for r in pending if r["quote_pre_lamports"] not in produced]
        current = starts[0] if starts else min(pending, key=lambda r: r["quote_pre_lamports"])
        while current is not None:
            out.append(current)
            pending.remove(current)
            candidates = [r for r in pending if r["quote_pre_lamports"] == current["quote_post_lamports"]]
            current = candidates[0] if candidates else None
        out.extend(sorted(pending, key=lambda r: r["quote_pre_lamports"]))
    return out


def main() -> None:
    sigdata = read_json(CASE / "amm_pool_signatures.json")
    selection = read_json(CASE / "amm_tx_selection.json")
    fetched = read_json(CASE / "amm_pool_transactions.json")
    current = read_json(CASE / "amm_current_pool_state.json")

    snapshot_groups: dict[tuple[str, str], list[dict]] = collections.defaultdict(list)
    cvy_all_rows = []
    event_counts = collections.Counter()
    total_snapshot_rows = 0
    with (ROOT / "data/ghost_amm_evidence.jsonl").open() as stream:
        for line in stream:
            row = json.loads(line)
            event = row.get("event")
            event_counts[event] += 1
            if event not in ("AUTHENTICATED_AMM_SNAPSHOT", "POST_EXIT_AMM_SNAPSHOT"):
                continue
            snap = row.get("snapshot") or {}
            if not all(snap.get(key) is not None for key in ("pool", "mint", "observed_at_ms", "quote_reserve_raw", "virtual_quote_reserve_raw", "base_reserve_raw", "base_supply_raw")):
                continue
            total_snapshot_rows += 1
            item = {
                "event": event,
                "pool": snap["pool"],
                "mint": snap["mint"],
                "observed_at_ms": int(snap["observed_at_ms"]),
                "quote_reserve_raw": int(snap["quote_reserve_raw"]),
                "virtual_quote_reserve_raw": int(snap["virtual_quote_reserve_raw"]),
                "base_reserve_raw": int(snap["base_reserve_raw"]),
                "base_supply_raw": int(snap["base_supply_raw"]),
                "base_decimals": int(snap.get("base_decimals", 6)),
                "supply_decimals": int(snap.get("base_decimals", 6)),
                "quote_decimals": 9,
                "context_slot": snap.get("context_slot"),
            }
            snapshot_groups[(item["pool"], item["mint"])].append(item)
            if item["mint"] == MINT and item["pool"] == POOL:
                cvy_all_rows.append(item)

    other_deep = []
    for (pool, mint), rows in snapshot_groups.items():
        rows.sort(key=lambda r: r["observed_at_ms"])
        peak = max(rows, key=lambda r: r["quote_reserve_raw"])
        last = rows[-1]
        if mint == MINT and pool == POOL or peak["quote_reserve_raw"] <= 0:
            continue
        decline = (peak["quote_reserve_raw"] - last["quote_reserve_raw"]) / peak["quote_reserve_raw"]
        if decline < 0.90:
            continue
        def cap_proxy(row: dict) -> float:
            base = row["base_reserve_raw"] / 10**row["base_decimals"]
            supply = row["base_supply_raw"] / 10**row["supply_decimals"]
            quote = (row["quote_reserve_raw"] + row["virtual_quote_reserve_raw"]) / 10**row["quote_decimals"]
            return quote / base * supply if base else 0.0
        other_deep.append({
            "pool": pool,
            "mint": mint,
            "snapshot_count": len(rows),
            "first_observed_utc": iso_ms(rows[0]["observed_at_ms"]),
            "peak_raw_quote_observed_utc": iso_ms(peak["observed_at_ms"]),
            "last_observed_utc": iso_ms(last["observed_at_ms"]),
            "peak_quote_reserve_sol": peak["quote_reserve_raw"] / 1e9,
            "last_quote_reserve_sol": last["quote_reserve_raw"] / 1e9,
            "peak_to_last_quote_reserve_decline_pct": decline * 100,
            "peak_base_reserve_tokens": peak["base_reserve_raw"] / 10**peak["base_decimals"],
            "last_base_reserve_tokens": last["base_reserve_raw"] / 10**last["base_decimals"],
            "peak_supply_tokens": peak["base_supply_raw"] / 10**peak["supply_decimals"],
            "last_supply_tokens": last["base_supply_raw"] / 10**last["supply_decimals"],
            "peak_virtual_quote_sol": peak["virtual_quote_reserve_raw"] / 1e9,
            "last_virtual_quote_sol": last["virtual_quote_reserve_raw"] / 1e9,
            "peak_formula_sol_market_cap_proxy": cap_proxy(peak),
            "last_formula_sol_market_cap_proxy": cap_proxy(last),
            "coverage_type": "local authenticated/post-exit snapshots; not a complete transaction trace",
        })
    other_deep.sort(key=lambda r: r["peak_to_last_quote_reserve_decline_pct"], reverse=True)

    cvy_all_rows.sort(key=lambda r: r["observed_at_ms"])
    cvy_rows = [r for r in cvy_all_rows if r["observed_at_ms"] <= FROZEN_LAST_MS]
    peak = max(cvy_rows, key=lambda r: r["quote_reserve_raw"])
    trough = min(cvy_rows, key=lambda r: r["quote_reserve_raw"])
    last_snapshot = cvy_rows[-1]
    rapid_before = next(r for r in cvy_rows if r["observed_at_ms"] == 1791761445557)
    rapid_mid = next(r for r in cvy_rows if r["observed_at_ms"] == 1791761445776)
    rapid_low = next(r for r in cvy_rows if r["observed_at_ms"] == 1791761446138)

    tx_rows = []
    for sig, tx in fetched.get("transactions", {}).items():
        row = pool_deltas(sig, tx)
        if row:
            tx_rows.append(row)
    incident_rows = [r for r in tx_rows if r["success"] and 455832951 <= r["slot"] <= 455832959]
    incident_rows = chained_order(incident_rows)
    sells = [r for r in incident_rows if r["quote_delta_lamports"] < 0 and r["base_delta_raw"] > 0]
    buys = [r for r in incident_rows if r["quote_delta_lamports"] > 0 and r["base_delta_raw"] < 0]
    seller_owner = {}
    for row in sells:
        for seller in row["sellers"]:
            # A successful AMM sell normally has one target mint owner with a net token decrease.
            seller_owner[seller] = row["owner_token_deltas_raw"].get(seller, 0)
    target_wallets = read_json(CASE / "target_wallets.json")
    same_wallet_count = sum(owner in target_wallets for owner in seller_owner)
    pregrad_positive = sum(
        owner in target_wallets and target_wallets[owner]["buy_tokens"] > target_wallets[owner]["sell_tokens"]
        for owner in seller_owner
    )
    exact_net_match = 0
    for owner in seller_owner:
        if owner not in target_wallets:
            continue
        net = target_wallets[owner]["buy_tokens"] - target_wallets[owner]["sell_tokens"]
        # The owner-side net token delta is negative when their full remaining balance is sold.
        if -seller_owner[owner] == net and net > 0:
            exact_net_match += 1
    quote_sell_out_lamports = -sum(r["quote_delta_lamports"] for r in sells)
    quote_buy_in_lamports = sum(r["quote_delta_lamports"] for r in buys)
    base_sell_in_raw = sum(r["base_delta_raw"] for r in sells)
    base_buy_out_raw = -sum(r["base_delta_raw"] for r in buys)
    q_start = incident_rows[0]["quote_pre_lamports"]
    q_end = incident_rows[-1]["quote_post_lamports"]
    first_five = [r for r in incident_rows if r["slot"] == 455832954 and "Sell" in " ".join(r["instructions"])][:5]
    creator = "FcNHxPSqQ1ChyWmwW8C4zzXuUvQR3b7zBNBxk84VPmSv"
    creator_in_burst = any(creator in r["seller_signers"] for r in sells)

    failures = fetched.get("rpc_failures") or []
    unresolved = []
    for failure in failures:
        if failure.get("signature") in selection["signatures"]:
            sigrow = next((r for r in sigdata["signatures"] if r["signature"] == failure["signature"]), {})
            unresolved.append({
                "signature": failure["signature"],
                "slot": sigrow.get("slot"),
                "block_time_utc": iso_s(sigrow["blockTime"]) if sigrow.get("blockTime") else None,
                "error": failure.get("error"),
            })

    analysis = {
        "network": "solana-mainnet",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "target": {"mint": MINT, "pool": POOL, "base_vault": BASE_VAULT, "quote_vault": QUOTE_VAULT},
        "signature_coverage": {
            "fetched_at_utc": sigdata["fetched_at_utc"],
            "page_size": sigdata["page_size"],
            "max_pages": sigdata["max_pages"],
            "pages_returned": sigdata["pages_returned"],
            "unique_pool_signatures": sigdata["unique_signature_count"],
            "successful_pool_signatures": sigdata["successful_count"],
            "failed_pool_signatures": sigdata["failed_count"],
            "oldest_signature_utc": iso_s(sigdata["oldest_block_time_unix"]),
            "newest_signature_utc": iso_s(sigdata["newest_block_time_unix"]),
            "covers_observed_opening": sigdata["covers_opening_time"],
            "selected_successful_transactions": selection["selected_count"],
            "bodies_returned": fetched["returned_count"],
            "unresolved_transaction_bodies": unresolved,
            "body_selection_rule": selection["selection_rule"],
        },
        "snapshot_coverage": {
            "source": "data/ghost_amm_evidence.jsonl",
            "event_counts_in_source": dict(event_counts),
            "valid_snapshots_all_pools": total_snapshot_rows,
            "unique_pools": len(snapshot_groups),
            "target_snapshot_count_in_frozen_window": len(cvy_rows),
            "target_snapshot_count_all_rows_now": len(cvy_all_rows),
            "target_first_utc": iso_ms(cvy_rows[0]["observed_at_ms"]),
            "target_frozen_last_utc": iso_ms(last_snapshot["observed_at_ms"]),
            "frozen_window_cutoff_utc": iso_ms(FROZEN_LAST_MS),
            "target_local_capture_is_sparse": True,
        },
        "reserve_observations": {
            "opening": {
                "observed_at_utc": iso_ms(cvy_rows[0]["observed_at_ms"]),
                "slot": cvy_rows[0]["context_slot"],
                "quote_reserve_sol": cvy_rows[0]["quote_reserve_raw"] / 1e9,
                "virtual_quote_sol": cvy_rows[0]["virtual_quote_reserve_raw"] / 1e9,
                "base_reserve_tokens": cvy_rows[0]["base_reserve_raw"] / 1e6,
                "supply_tokens": cvy_rows[0]["base_supply_raw"] / 1e6,
            },
            "raw_quote_peak": {
                "observed_at_utc": iso_ms(peak["observed_at_ms"]),
                "slot": peak["context_slot"],
                "quote_reserve_sol": peak["quote_reserve_raw"] / 1e9,
                "virtual_quote_sol": peak["virtual_quote_reserve_raw"] / 1e9,
                "base_reserve_tokens": peak["base_reserve_raw"] / 1e6,
                "supply_tokens": peak["base_supply_raw"] / 1e6,
            },
            "raw_quote_trough": {
                "observed_at_utc": iso_ms(trough["observed_at_ms"]),
                "slot": trough["context_slot"],
                "quote_reserve_sol": trough["quote_reserve_raw"] / 1e9,
                "virtual_quote_sol": trough["virtual_quote_reserve_raw"] / 1e9,
                "base_reserve_tokens": trough["base_reserve_raw"] / 1e6,
                "supply_tokens": trough["base_supply_raw"] / 1e6,
            },
            "raw_quote_last_frozen_snapshot": {
                "observed_at_utc": iso_ms(last_snapshot["observed_at_ms"]),
                "slot": last_snapshot["context_slot"],
                "quote_reserve_sol": last_snapshot["quote_reserve_raw"] / 1e9,
                "virtual_quote_sol": last_snapshot["virtual_quote_reserve_raw"] / 1e9,
                "base_reserve_tokens": last_snapshot["base_reserve_raw"] / 1e6,
                "supply_tokens": last_snapshot["base_supply_raw"] / 1e6,
            },
            "peak_to_trough_actual_quote_reserve_decline_pct": (peak["quote_reserve_raw"] - trough["quote_reserve_raw"]) / peak["quote_reserve_raw"] * 100,
            "peak_to_last_actual_quote_reserve_decline_pct": (peak["quote_reserve_raw"] - last_snapshot["quote_reserve_raw"]) / peak["quote_reserve_raw"] * 100,
            "peak_to_trough_virtual_quote_change_pct": (trough["virtual_quote_reserve_raw"] - peak["virtual_quote_reserve_raw"]) / peak["virtual_quote_reserve_raw"] * 100,
            "rapid_local_samples": [
                {"observed_at_utc": iso_ms(r["observed_at_ms"]), "quote_reserve_sol": r["quote_reserve_raw"] / 1e9, "virtual_quote_sol": r["virtual_quote_reserve_raw"] / 1e9, "base_reserve_tokens": r["base_reserve_raw"] / 1e6, "formula_sol_market_cap_proxy": ((r["quote_reserve_raw"] + r["virtual_quote_reserve_raw"]) / 1e9) / (r["base_reserve_raw"] / 1e6) * (r["base_supply_raw"] / 1e6)}
                for r in (rapid_before, rapid_mid, rapid_low)
            ],
            "rapid_first_to_last_quote_reserve_decline_pct": (rapid_before["quote_reserve_raw"] - rapid_low["quote_reserve_raw"]) / rapid_before["quote_reserve_raw"] * 100,
            "rapid_interval_ms": rapid_low["observed_at_ms"] - rapid_before["observed_at_ms"],
            "interpretation": "actual spendable quote-vault reserve is separate from PumpSwap virtual quote reserve; dollar market cap is not verified here",
        },
        "current_finalized_state": {
            "observed_at_utc": current["observed_at_utc"],
            "context_slot": current["context_slot"],
            "commitment": current["commitment"],
            "raw_quote_reserve_sol": int(current["quote_reserve_raw"]) / 1e9,
            "virtual_quote_reserve_sol": None,
            "base_reserve_tokens": int(current["base_reserve_raw"]) / 1e6,
            "supply_tokens": int(current["base_supply_raw"]) / 1e6,
            "note": "separate later finalized account read; do not substitute for the frozen local snapshot endpoint",
        },
        "collapse_transaction_slice": {
            "slot_range": [455832951, 455832959],
            "successful_transactions_with_both_vault_balance_deltas": len(incident_rows),
            "pump_swap_sells": len(sells),
            "distinct_sell_owner_addresses": len(seller_owner),
            "sellers_that_are_signers": sum(len(r["seller_signers"]) for r in sells),
            "pump_swap_buys": len(buys),
            "gross_sell_quote_out_sol": quote_sell_out_lamports / 1e9,
            "gross_buy_quote_in_sol": quote_buy_in_lamports / 1e9,
            "net_quote_reserve_drop_sol": (quote_sell_out_lamports - quote_buy_in_lamports) / 1e9,
            "gross_sell_tokens_into_pool": base_sell_in_raw / 1e6,
            "gross_buy_tokens_out_of_pool": base_buy_out_raw / 1e6,
            "first_pool_quote_reserve_sol": q_start / 1e9,
            "last_pool_quote_reserve_sol": q_end / 1e9,
            "reserve_drop_pct_across_slice": (q_start - q_end) / q_start * 100,
            "top_five_sell_witnesses_slot_455832954": [
                {
                    "signature": r["signature"],
                    "seller_owner": r["sellers"][0] if r["sellers"] else None,
                    "seller_is_signer": bool(r["seller_signers"]),
                    "quote_pre_sol": r["quote_pre_lamports"] / 1e9,
                    "quote_post_sol": r["quote_post_lamports"] / 1e9,
                    "quote_out_sol": -r["quote_delta_lamports"] / 1e9,
                    "tokens_sold": -sum(r["owner_token_deltas_raw"].get(owner, 0) for owner in r["sellers"]) / 1e6,
                }
                for r in first_five
            ],
            "pregraduation_overlap": {
                "distinct_flash_seller_owners": len(seller_owner),
                "also_in_target_curve_wallet_ledger": same_wallet_count,
                "positive_net_target_tokens_at_curve_completion": pregrad_positive,
                "exact_sell_amount_matches_positive_pregrad_net": exact_net_match,
            },
            "creator_signer_observed_among_burst_sellers": creator_in_burst,
            "liquidity_withdrawal_instruction_observed_in_slice": any("Withdraw" in name for r in incident_rows for name in r["instructions"]),
        },
        "prior_pool_cohort_witness": {
            "mint": "77AXSFnjgfgsT261R8wkPSwSe94BgheBS9hbLiQVpump",
            "pool": "Bt8gmEqPWojBQqVsF4BuBNYKwTCX7JQevWb81Cyof4Yk",
            "source_artifact": "prior_77AXS_pool_sell_witnesses.json",
            "cvy_creation_utc": "2026-10-11T23:13:18Z",
            "prior_pool_observed_sell_window_utc": ["2026-10-11T23:06:10Z", "2026-10-11T23:06:11Z"],
            "prior_pool_witnesses": [
                {"wallet": "98MLcc4UVzeLaDWckcBUCMcwS5CgSeqAjC4g2JNQ714c", "quote_pre_sol": 77.385466319, "quote_post_sol": 68.635744042},
                {"wallet": "CGbLazQt5HXNPawzFct36WeFwj8dL4vGUd8KRHSJ1iCX", "quote_pre_sol": 50.479892998, "quote_post_sol": 42.022674846},
                {"wallet": "53MN5hAAGHu8Q8HM8ZCaenWYsBma4qTHD9Lp6ETKdLrL", "quote_pre_sol": 22.968058364, "quote_post_sol": 22.137004764},
                {"wallet": "mMpEUcCgvHmdXvkrawYszRZpXTVfp1E2rDCc4vtGfdw", "quote_pre_sol": 10.938489092, "quote_post_sol": 10.196666159},
            ],
            "scope_limit": "selected authenticated pre/post quote and token-balance witnesses from a bounded prior-pool sample, not a complete prior pool tape or identity/coordination proof",
        },
        "interpretation_limits": [
            "Reserve movement establishes a rapid, severe liquidity/price collapse; it does not by itself establish fraud or intent.",
            "No USD conversion or historical SOL/USD price source is included; the reported dollar market-cap values remain user estimates.",
            "The report does not infer creator control from wallet overlap. The creator signer is absent only from the selected fetched slice.",
            "Transaction bodies were selected around opening, the reserve peak/trough, and all later successful pool signatures; this is not a complete reconstruction of every successful pool transaction from opening.",
            "Snapshot cohort thresholds are exploratory outcome selection and are not causal evidence, a predictive filter, or a backtest.",
        ],
    }
    (CASE / "amm_analysis.json").write_text(json.dumps(analysis, indent=2, sort_keys=True) + "\n")
    (CASE / "amm_other_deep_declines.json").write_text(json.dumps({
        "selection": "Outcome-selected exploratory scan of local authenticated/post-exit AMM snapshot rows; other than Cvy, grouped by pool and mint; raw quote-vault peak to last observed snapshot decline >=90%.",
        "snapshot_source": "data/ghost_amm_evidence.jsonl",
        "rows_scanned": event_counts["AUTHENTICATED_AMM_SNAPSHOT"] + event_counts["POST_EXIT_AMM_SNAPSHOT"],
        "valid_snapshot_rows": total_snapshot_rows,
        "unique_pools": len(snapshot_groups),
        "target_excluded": {"pool": POOL, "mint": MINT},
        "threshold_pct": 90,
        "qualifying_other_pools": other_deep,
        "warnings": [
            "Outcome-selected cohort; descriptive only, not a random sample, predictive screen, causal test, strategy edge, or backtest.",
            "Coverage and last-observed times differ by pool; snapshots do not show complete pool transaction tape.",
            "Formula market-cap figures are SOL-denominated proxies using actual plus virtual quote reserve and total supply; no USD conversion is asserted.",
        ],
    }, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
