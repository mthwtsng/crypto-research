#!/usr/bin/env python3
"""Causal descriptive features at first live-observed 16 SOL curve crossing.

This is an exploratory receipt diagnostic, not a classifier, replay, or PnL test.
The features are computed from the 10 seconds ending at and including the crossing
receipt. The future label is evaluated separately after the features are frozen.
"""
from __future__ import annotations

import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MANIFEST = json.loads((ROOT / "MANIFEST.json").read_text())
SOURCE = ROOT / "observations_slim.jsonl"
CUTOFF_MS = int(MANIFEST["cutoff_ms"])
SOL_MINT = "11111111111111111111111111111111"
TOTAL_SUPPLY_RAW = 1_000_000_000_000_000
WINDOW_MS = 10_000
LABEL_MS = 120_000
MIN_RESERVE_SOL = 16.0


def ratio(n: float, d: float) -> float | None:
    return n / d if d else None


def spot_proxy(e: dict) -> float | None:
    vsol, vtokens = e.get("vsol_raw"), e.get("vtokens_raw")
    if not vsol or not vtokens:
        return None
    # Raw reserve ratio differs from SOL/token only by a constant decimal factor;
    # the ratio is sufficient for within-mint price multiples.
    return float(vsol) / float(vtokens)


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    xs = sorted(values)
    pos = (len(xs) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    if lo == hi:
        return xs[lo]
    return xs[lo] * (hi - pos) + xs[hi] * (pos - lo)


def median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def main() -> None:
    # Keep creation provenance and each event in live receive/file order.
    created: dict[str, tuple[int, str | None]] = {}
    paths: dict[str, list[dict]] = defaultdict(list)
    receipt_count = 0
    event_count = 0
    receipt_index_inversions = 0
    last_index_by_slot: dict[int, int] = {}
    quote_counts = Counter()

    with SOURCE.open() as f:
        for seq, line in enumerate(f):
            receipt_count += 1
            o = json.loads(line)
            received_ms = int(o.get("received_at_ms") or 0)
            slot = int(o.get("slot") or 0)
            tx_index = int(o.get("transaction_index") or 0)
            if slot in last_index_by_slot and tx_index < last_index_by_slot[slot]:
                receipt_index_inversions += 1
            last_index_by_slot[slot] = tx_index

            for pair in o.get("creators") or []:
                if isinstance(pair, (list, tuple)) and len(pair) >= 2:
                    created.setdefault(str(pair[0]), (received_ms, str(pair[1])))

            receipt_events = o.get("events") or []
            last_event_by_mint = {str(e.get("mint")): i for i, e in enumerate(receipt_events) if e.get("mint")}
            for event_i, e in enumerate(receipt_events):
                event_count += 1
                mint = e.get("mint")
                if not mint:
                    continue
                quote = e.get("quote_mint")
                supported_sol = bool(e.get("supported_sol_quote")) and quote == SOL_MINT
                quote_counts["supported_sol" if supported_sol else "other_or_unknown"] += 1
                paths[str(mint)].append({
                    "seq": seq,
                    "event_i": event_i,
                    "received_ms": received_ms,
                    "slot": slot,
                    "tx_index": tx_index,
                    "user": str(e.get("user") or ""),
                    "creator": str(e.get("creator") or ""),
                    "is_buy": bool(e.get("is_buy")),
                    "sol_raw": int(e.get("sol_raw") or 0),
                    "tokens_raw": int(e.get("tokens_raw") or 0),
                    "rsol_raw": int(e.get("rsol_raw") or 0),
                    "rtokens_raw": int(e.get("rtokens_raw") or 0),
                    "vsol_raw": int(e.get("vsol_raw") or 0),
                    "vtokens_raw": int(e.get("vtokens_raw") or 0),
                    "supported_sol": supported_sol,
                    "mayhem_mode": e.get("mayhem_mode"),
                    "receipt_final_mint_state": event_i == last_event_by_mint.get(str(mint)),
                })

    # Frozen feature definitions. Outside-wallet volume excludes the observed
    # creator address; wallet counts indicate addresses, not independent people.
    feature_rows: list[dict] = []
    exclusions = Counter()
    for mint, (created_ms, creator_hint) in created.items():
        evs = paths.get(mint, [])
        if not evs:
            exclusions["creation_without_trade_event"] += 1
            continue
        all_sol_evs = [e for e in evs if e["supported_sol"] and e["received_ms"] >= created_ms]
        if not all_sol_evs:
            exclusions["no_supported_sol_trade_after_creation"] += 1
            continue
        # State marks use only the last same-mint event in each complete receipt.
        # Feature-window volumes below retain every supported event.
        sol_evs = [e for e in all_sol_evs if e["receipt_final_mint_state"]]
        cross_i = next((i for i, e in enumerate(sol_evs)
                        if e["rsol_raw"] >= int(MIN_RESERVE_SOL * 1e9)), None)
        if cross_i is None:
            exclusions["no_16_sol_crossing"] += 1
            continue
        cross = sol_evs[cross_i]
        cross_ms = cross["received_ms"]
        cross_spot = spot_proxy(cross)
        if cross_spot is None or cross_spot <= 0:
            exclusions["invalid_cross_spot"] += 1
            continue
        cross_seq = (cross["seq"], cross["event_i"])
        prior = [e for e in sol_evs if (e["seq"], e["event_i"]) < cross_seq]
        win = [e for e in all_sol_evs
               if cross_ms - WINDOW_MS <= e["received_ms"] <= cross_ms
               and (e["seq"], e["event_i"]) <= cross_seq]

        outside_buys: list[dict] = []
        gross_sell_sol = 0.0
        gross_buy_sol = 0.0
        buy_volume_by_wallet: dict[str, float] = defaultdict(float)
        buy_count_by_wallet: Counter = Counter()
        size_counts: Counter = Counter()
        size_volume: Counter = Counter()
        one_sec_buys: Counter = Counter()
        slot_buys: Counter = Counter()
        meaningful: set[str] = set()
        for e in win:
            amount = e["sol_raw"] / 1e9
            if e["is_buy"]:
                gross_buy_sol += amount
                if e["user"] and e["user"] != e["creator"]:
                    outside_buys.append(e)
                    buy_volume_by_wallet[e["user"]] += amount
                    buy_count_by_wallet[e["user"]] += 1
                    if amount >= 0.05:
                        meaningful.add(e["user"])
                    # Fixed 0.01 SOL ticket-size bins; this is a descriptive
                    # standardization, not an optimized threshold.
                    bucket = int(math.floor(amount * 100.0 + 0.5))
                    size_counts[bucket] += 1
                    size_volume[bucket] += amount
                    second_bucket = (e["received_ms"] - (cross_ms - WINDOW_MS)) // 1000
                    one_sec_buys[second_bucket] += amount
                    slot_buys[e["slot"]] += amount
            else:
                gross_sell_sol += amount

        outside_buy_sol = sum(buy_volume_by_wallet.values())
        repeated_wallets = {w for w, n in buy_count_by_wallet.items() if n >= 2}
        top3_wallet_volume = sorted(buy_volume_by_wallet.values(), reverse=True)[:3]
        top3_size_counts = sorted(size_counts.values(), reverse=True)[:3]
        top3_size_volume = sorted(size_volume.values(), reverse=True)[:3]
        preceding = [e for e in sol_evs
                     if e["received_ms"] < cross_ms - WINDOW_MS]
        reserve_start = (preceding[-1]["rsol_raw"] / 1e9) if preceding else 0.0
        reserve_delta = cross["rsol_raw"] / 1e9 - reserve_start

        # Creator residual comes only from visible creator buy/sell trade events;
        # it is not custody-adjusted and can miss seeded/transfer inventory.
        creator_tokens = 0
        for e in all_sol_evs:
            if (e["seq"], e["event_i"]) > cross_seq:
                break
            if creator_hint and e["user"] == creator_hint:
                if e["is_buy"]:
                    creator_tokens += e["tokens_raw"]
                else:
                    creator_tokens = max(0, creator_tokens - e["tokens_raw"])

        feature = {
            "mint": mint,
            "created_at_ms": created_ms,
            "cross_received_at_ms": cross_ms,
            "cross_age_seconds": (cross_ms - created_ms) / 1000.0,
            "cross_slot": cross["slot"],
            "cross_tx_index": cross["tx_index"],
            "cross_receipt_seq": cross["seq"],
            "cross_event_i": cross["event_i"],
            "cross_real_reserve_sol": cross["rsol_raw"] / 1e9,
            "cross_spot_proxy": cross_spot,
            "mayhem_mode_at_cross": cross["mayhem_mode"],
            "window_event_count": len(win),
            "window_outside_buy_count": len(outside_buys),
            "window_gross_buy_sol": gross_buy_sol,
            "window_gross_sell_sol": gross_sell_sol,
            "window_sell_buy_churn": ratio(gross_sell_sol, gross_buy_sol),
            "window_outside_buy_sol": outside_buy_sol,
            "window_outside_sell_sol": sum(e["sol_raw"] / 1e9 for e in win
                                             if not e["is_buy"] and e["user"] != e["creator"]),
            "window_meaningful_outside_buyers_ge_0_05": len(meaningful),
            "window_repeat_buyer_count": len(repeated_wallets),
            "window_repeat_buyer_volume_share": ratio(sum(buy_volume_by_wallet[w] for w in repeated_wallets), outside_buy_sol),
            "window_top3_buyer_volume_share": ratio(sum(top3_wallet_volume), outside_buy_sol),
            "window_modal_size_bin_sol": (max(size_counts, key=size_counts.get) / 100.0) if size_counts else None,
            "window_modal_size_event_share": ratio(max(size_counts.values()), len(outside_buys)) if size_counts else None,
            "window_top3_size_bins_event_share": ratio(sum(top3_size_counts), len(outside_buys)) if size_counts else None,
            "window_top3_size_bins_volume_share": ratio(sum(top3_size_volume), outside_buy_sol),
            "window_max_1s_buy_volume_share": ratio(max(one_sec_buys.values()), outside_buy_sol) if one_sec_buys else None,
            "window_max_slot_buy_volume_share": ratio(max(slot_buys.values()), outside_buy_sol) if slot_buys else None,
            "window_real_reserve_delta_sol": reserve_delta,
            "window_reserve_delta_vs_gross_buy": ratio(reserve_delta, gross_buy_sol),
            "creator_observed_residual_tokens": creator_tokens if creator_hint else None,
            "creator_observed_residual_supply_pct": (creator_tokens / TOTAL_SUPPLY_RAW * 100.0) if creator_hint else None,
            "same_slot_index_inversion_in_window": any(
                win[i]["slot"] == win[i-1]["slot"] and win[i]["tx_index"] < win[i-1]["tx_index"]
                for i in range(1, len(win))),
        }
        feature_rows.append(feature)

    # Only after all feature rows are constructed, read the forward path to make
    # the requested exploratory labels. Curves completing before 120s are
    # censored unless the collapse label was already observed before completion.
    for f in feature_rows:
        mint = f["mint"]
        evs = [e for e in paths[mint] if e["supported_sol"] and e["receipt_final_mint_state"]]
        # Receive/file order, then event order: source's live-observed order.
        cross_event = next((e for e in evs if e["seq"] == f["cross_receipt_seq"]
                            and e["event_i"] == f["cross_event_i"]), None)
        if cross_event is None:
            f["label"] = "invalid_path_join"
            continue
        if CUTOFF_MS - f["cross_received_at_ms"] < LABEL_MS:
            f["label"] = "censored_recent"
            f["label_followup_seconds"] = max(0.0, (CUTOFF_MS - f["cross_received_at_ms"]) / 1000.0)
            continue
        cross_pair = (cross_event["seq"], cross_event["event_i"])
        future = [e for e in evs if (e["seq"], e["event_i"]) > cross_pair
                  and e["received_ms"] <= f["cross_received_at_ms"] + LABEL_MS]
        peak = f["cross_spot_proxy"]
        max_drawdown = 0.0
        peak_real_reserve = f["cross_real_reserve_sol"]
        min_after_real_peak = peak_real_reserve
        max_real_reserve_drawdown = 0.0
        reached_125 = False
        reached_150 = False
        collapse = None
        migrated_at_ms = None
        same_slot_inversion_future = False
        previous = cross_event
        for e in future:
            sp = spot_proxy(e)
            if sp is not None:
                peak = max(peak, sp)
                if sp >= f["cross_spot_proxy"] * 1.25:
                    reached_125 = True
                if sp >= f["cross_spot_proxy"] * 1.50:
                    reached_150 = True
                max_drawdown = max(max_drawdown, 1.0 - sp / peak if peak else 0.0)
                if reached_125 and sp <= peak * 0.20 and collapse is None:
                    collapse = e
            real_reserve = e["rsol_raw"] / 1e9
            if real_reserve >= peak_real_reserve:
                peak_real_reserve = real_reserve
                min_after_real_peak = real_reserve
            else:
                min_after_real_peak = min(min_after_real_peak, real_reserve)
                if peak_real_reserve:
                    max_real_reserve_drawdown = max(max_real_reserve_drawdown,
                                                    1.0 - min_after_real_peak / peak_real_reserve)
            if e["slot"] == previous["slot"] and e["tx_index"] < previous["tx_index"]:
                same_slot_inversion_future = True
            previous = e
            if e["rtokens_raw"] == 0:
                migrated_at_ms = e["received_ms"]
                break
        f["reached_1_25x"] = reached_125
        f["reached_1_5x"] = reached_150
        f["peak_spot_multiple"] = peak / f["cross_spot_proxy"] if f["cross_spot_proxy"] else None
        f["max_observed_drawdown_pct"] = max_drawdown * 100.0
        f["peak_real_reserve_after_cross_sol"] = peak_real_reserve
        f["minimum_real_reserve_after_peak_sol"] = min_after_real_peak
        f["max_real_reserve_drawdown_pct"] = max_real_reserve_drawdown * 100.0
        f["real_reserve_drain_ge_90pct"] = max_real_reserve_drawdown >= 0.90
        f["same_slot_index_inversion_in_forward_window"] = same_slot_inversion_future
        f["migrated_at_ms"] = migrated_at_ms
        f["rise_then_80pct_collapse_ms"] = collapse["received_ms"] if collapse else None
        f["rise_then_80pct_collapse_delay_seconds"] = ((collapse["received_ms"] - f["cross_received_at_ms"]) / 1000.0) if collapse else None
        f["forward_event_count"] = len(future)
        if collapse is not None:
            f["label"] = "rise_then_80pct_collapse"
        elif migrated_at_ms is not None:
            f["label"] = "censored_migration_before_120s"
        elif reached_150:
            f["label"] = "curve_tape_1_5x_no_observed_80pct_drawdown_120s"
        elif not future:
            f["label"] = "no_postcross_receipt_observed"
        else:
            f["label"] = "other_observed_path"

    # Save one row per eligible, creation-observed crossing. This can be joined
    # by mint to shield/screen outcomes, but must not be read as a strategy score.
    out_csv = HERE / "crossings.csv"
    fields = sorted({k for r in feature_rows for k in r})
    with out_csv.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(feature_rows)

    labels = Counter(r.get("label") for r in feature_rows)
    real_drain_labels = Counter(r.get("label") for r in feature_rows if r.get("real_reserve_drain_ge_90pct"))
    feature_names = [
        "cross_age_seconds", "window_gross_buy_sol", "window_gross_sell_sol",
        "window_sell_buy_churn", "window_meaningful_outside_buyers_ge_0_05",
        "window_repeat_buyer_volume_share", "window_top3_buyer_volume_share",
        "window_modal_size_event_share", "window_top3_size_bins_event_share",
        "window_max_1s_buy_volume_share", "window_max_slot_buy_volume_share",
        "window_reserve_delta_vs_gross_buy", "creator_observed_residual_supply_pct",
        "max_observed_drawdown_pct", "max_real_reserve_drawdown_pct",
    ]
    groups = {}
    for label in ["rise_then_80pct_collapse", "curve_tape_1_5x_no_observed_80pct_drawdown_120s", "other_observed_path"]:
        rows = [r for r in feature_rows if r.get("label") == label]
        groups[label] = {"n": len(rows), "features": {}}
        for name in feature_names:
            values = [float(r[name]) for r in rows if isinstance(r.get(name), (int, float))]
            groups[label]["features"][name] = {
                "n": len(values), "p25": percentile(values, .25), "median": median(values), "p75": percentile(values, .75)
            }

    # Illustrations are the earliest crossing in each named outcome group,
    # selected by time only; they are not classifier examples or validation.
    illustrations = []
    for label in ["rise_then_80pct_collapse", "curve_tape_1_5x_no_observed_80pct_drawdown_120s"]:
        eligible = sorted((r for r in feature_rows if r.get("label") == label), key=lambda r: r["cross_received_at_ms"])
        for r in eligible[:2]:
            illustrations.append({k: r.get(k) for k in [
                "mint", "cross_received_at_ms", "label", "window_gross_buy_sol", "window_sell_buy_churn",
                "window_meaningful_outside_buyers_ge_0_05", "window_repeat_buyer_volume_share",
                "window_top3_buyer_volume_share", "window_modal_size_bin_sol",
                "window_modal_size_event_share", "window_top3_size_bins_event_share",
                "window_max_1s_buy_volume_share", "window_max_slot_buy_volume_share",
                "window_reserve_delta_vs_gross_buy", "creator_observed_residual_supply_pct",
                "peak_spot_multiple", "drawdown_from_peak_pct", "forward_event_count",
                "same_slot_index_in_window", "same_slot_index_in_forward_window",
            ]})

    summary = {
        "source": str(SOURCE),
        "cutoff_utc": MANIFEST["cutoff_utc"],
        "cutoff_ms": CUTOFF_MS,
        "source_head": "9dcff3f509b40d78d51921509ca09e79a2eafe63",
        "receipt_count": receipt_count,
        "event_count": event_count,
        "creation_observed_mints": len(created),
        "quote_event_counts": dict(quote_counts),
        "receive_order_same_slot_index_inversions_global": receipt_index_inversions,
        "crossing_count": len(feature_rows),
        "crossing_labels": dict(labels),
        "observed_real_reserve_drain_ge_90pct_by_label": dict(real_drain_labels),
        "exclusions": dict(exclusions),
        "feature_definitions": {
            "crossing": "First creation-observed supported native-SOL receipt whose last event for this mint has rsol_raw >= 16 SOL, in file/receive order.",
            "feature_window": "Prior 10,000ms by received_at_ms, through and including the complete crossing receipt; all supported trade events count toward gross volume, and outside-buyer features use user != event creator.",
            "meaningful_buyer": "Distinct outside address with at least one individual buy event >=0.05 SOL.",
            "repeat_buyer_share": "Outside buy volume attributable to addresses with >=2 buy events in the feature window / all outside buy volume.",
            "top3_share": "Top three outside addresses by buy volume / all outside buy volume.",
            "size_bins": "Outside buys rounded to nearest 0.01 SOL; top-bin metrics are descriptive only.",
            "burst_share": "Largest fixed 1-second received-time bucket or on-chain slot's outside buy volume / all outside buy volume.",
            "reserve_retention": "Crossing rsol minus last observed rsol before feature-window start, divided by gross buy volume; initial reserve assumed zero only when no prior observation exists after observed creation.",
            "creator_residual": "Visible creator-user buy tokens minus visible creator-user sell tokens through crossing, saturated at zero; excludes transfers and unobserved seeded inventory.",
            "spot": "vsol_raw/vtokens_raw within-mint ratio proxy from the last event for this mint in each complete receipt; decimal scale cancels in multiples.",
            "collapse_label": "Within 120s, spot first reaches >=1.25x crossing proxy, then observed spot <=20% of its running post-cross peak.",
            "runner_label": "Exploratory curve-tape proxy only: within 120s, spot reaches >=1.5x crossing proxy without an observed 80% running-peak drawdown; this does not establish complete market coverage, stability, or post-migration behavior. Migration before 120s is censored.",
            "order": "Live-observed receipt/file order only; price/reserve trajectory uses one final same-mint state per receipt. The global receipt stream has cross-mint same-slot transaction-index inversions; per-mint path audit found none. Fine receipt timing is not calibrated to chain time.",
        },
        "groups": groups,
        "illustrations_earliest_by_crossing_time": illustrations,
        "interpretation_limits": [
            "Behavioral volume patterns cannot prove bot control, fake volume, common ownership, or organic participation.",
            "Live receive order is not canonical chain order and fine receipt timing is not calibrated. A separate audit found all global same-slot index inversions are cross-mint, with none within a per-mint path.",
            "No post-migration AMM path is included; graduation before a label is resolved is censored. Sparse per-mint receipts cannot establish quiet, stable, or rug-free periods.",
            "Creator residuals are receipt-derived trade deltas, not complete custody accounting.",
            "This is descriptive only: no classifier, threshold selection, profitability estimate, or live filter.",
        ],
        "outputs": ["crossings.csv"],
    }
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: summary[k] for k in ["receipt_count", "event_count", "creation_observed_mints", "crossing_count", "crossing_labels", "exclusions", "receive_order_same_slot_index_inversions_global"]}, indent=2))


if __name__ == "__main__":
    main()
