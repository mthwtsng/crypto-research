"""Causal canonical and source-current entries for the frozen day sample.

This module only discovers entries and evaluates the current admission screens.
It does not quote buys, model exits, or make profitability claims.  Historical
RPC holder screens are accepted only with a timestamped row; missing history is
unknown and never an implicit clear.
"""
from __future__ import annotations

import collections
import datetime as _datetime
import importlib.util
import pathlib
import sys
from typing import Any

P = pathlib.Path(__file__).resolve().parent
ROOT = P.parents[1]
HELPERS = ROOT / "research/day_general_20261004/helpers"
CORE_SIGNALS_PATH = ROOT / "research/core_plan_audit_20261007/signals.py"

if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))
_spec = importlib.util.spec_from_file_location("day_sample_core_plan_signals", CORE_SIGNALS_PATH)
if _spec is None or _spec.loader is None:
    raise ImportError(f"cannot load canonical signal source: {CORE_SIGNALS_PATH}")
_core_signals = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_core_signals)

TOTAL_SUPPLY_RAW = 1_000_000_000_000_000
CURRENT_MIN_SCAN_MCAP_USD = 6_400.0
CURRENT_SCREEN_SOL_USD = 145.0
HOLDER_SCREEN_CLEAR_TTL_MS = 30_000
HOLDER_SCREEN_IN_FLIGHT_TTL_MS = 40_000
LOW_SOL_THRESHOLD_LAMPORTS = 300_000_000
LOW_SOL_SUPPLY_BLOCK_PCT = 50.0
TOP10_LOW_SOL_BLOCK_COUNT = 8
SINGLE_LOW_SOL_WHALE_PCT = 7.0
RECLAIM_PULLBACK = 0.08
RECLAIM_WINDOW_MS = 180_000
RULES = {
    "s1_dev_absorption",
    "s2_survival_shelf",
    "s3_deadman",
    "s4_upper_ath",
    "s5_carryover",
}


def _spot(group: dict[str, Any]) -> float:
    state = group["state"]
    tokens = state.get("vtokens_raw", 0)
    return state.get("vsol_raw", 0) / tokens if tokens else 0.0


def _event_spot(event: dict[str, Any], group: dict[str, Any]) -> float:
    tokens = event.get("vtokens_raw", 0)
    if tokens:
        return event.get("vsol_raw", 0) / tokens
    return _spot(group)


def _event_reserve(event: dict[str, Any], group: dict[str, Any]) -> float:
    raw = event.get("rsol_raw")
    if raw is None:
        raw = group["state"].get("rsol_raw", 0)
    return raw / 1e9


def _group_index(t: dict[str, Any], signal: dict[str, Any]) -> int:
    if signal.get("index") is not None:
        return int(signal["index"])
    signature = signal.get("signal_signature")
    return next(i for i, group in enumerate(t["groups"]) if group["signature"] == signature)


def _confirm_s3_two_buy_groups(t: dict[str, Any], signal: dict[str, Any]) -> dict[str, Any] | None:
    """The frozen recovery_sequence two_buy_groups chooser, without imports."""
    i = _group_index(t, signal)
    eventful_groups = 0
    first_buyers: set[str] = set()
    buy_groups = 0
    for group in t["groups"][i + 1 :]:
        if group["slot"] > signal["slot"] + 2 or group["state"].get("rtokens_raw", 1) == 0:
            break
        if not group.get("events"):
            continue
        eventful_groups += 1
        buyers = {
            event["user"]
            for event in group["events"]
            if event.get("buy")
            and event.get("user") != t["creator"]
            and event.get("sol_raw", 0) >= 50_000_000
        }
        if buyers:
            buy_groups += 1
            if buy_groups == 1:
                first_buyers = buyers
        if buy_groups >= 2 and bool(buyers - first_buyers):
            reserve = group["state"].get("rsol_raw", 0) / 1e9
            if not 8.0 <= reserve <= 18.0:
                return None
            return dict(
                signal,
                original_signal_signature=signal["signal_signature"],
                original_signal_slot=signal["slot"],
                signal_signature=group["signature"],
                index=t["groups"].index(group),
                slot=group["slot"],
                time=group["block_time"],
                reserve=reserve,
                confirmation_groups=eventful_groups,
                confirmation_buy_groups=buy_groups,
            )
    return None


def _canonical_candidates(t: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    signals, errors = _core_signals.detect(t)
    confirmed = []
    for signal in signals:
        if signal["rule"] == "s3_deadman":
            chosen = _confirm_s3_two_buy_groups(t, signal)
            if chosen is not None:
                confirmed.append(chosen)
        else:
            confirmed.append(signal)
    return confirmed, errors


def _signal(t: dict[str, Any], rule: str, i: int, **features: Any) -> dict[str, Any]:
    group = t["groups"][i]
    return dict(
        mint=t["mint"],
        curve=t["curve"],
        rule=rule,
        index=i,
        slot=group["slot"],
        time=group["block_time"],
        signal_signature=group["signature"],
        reserve=group["state"].get("rsol_raw", 0) / 1e9,
        age_seconds=group["block_time"] - t["creation_time"],
        **features,
    )


def _current_non_s2_candidates(
    t: dict[str, Any], allow_screened_retries: bool = False
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Port the current Rust S1/S3/S4/S5 predicates at transaction boundaries.

    S3 confirmations count qualifying TradeEvents, including multiple events
    in one completed transaction, matching the current Rust tracker. When
    screens are active, retain repeated source candidates so an earlier
    screen-rejected event cannot suppress a later eligible trigger.
    """
    if not t.get("normal", False):
        return [], [dict(reason="unsupported_non_normal_tape")]

    creator = t["creator"]
    balances: collections.Counter[str] = collections.Counter()
    all_buyers: set[str] = set()
    qualified_buyers: set[str] = set()
    creator_bought = 0
    creator_sold = 0
    creator_held = 0
    prior_spot: float | None = None
    peak_spot = 0.0
    trough_spot: float | None = None
    trough_slot: int | None = None
    trough_buyers: set[str] = set()
    trough_buy_raw = 0
    dip_slot: int | None = None
    dip_index: int | None = None
    dip_buy_count = 0
    dip_buyers: set[str] = set()
    dip_buy_signatures: set[str] = set()
    dip_buy_trades_by_signature: collections.Counter[str] = collections.Counter()
    outside_flow_by_slot: collections.Counter[int] = collections.Counter()
    previous_reserve = 0.0
    seen: set[str] = set()
    out: list[dict[str, Any]] = []

    for i, group in enumerate(t["groups"]):
        if group["state"].get("rtokens_raw", 1) == 0:
            break
        group_slot = int(group["slot"])
        events = group.get("events", [])
        last_event = events[-1] if events else None
        last_event_prior_reserve = previous_reserve

        # TradeEvent records carry post-trade reserves, so event-level state
        # remains causal. Signal rows still point to the complete transaction.
        for event in group.get("events", []):
            wallet = event["user"]
            buy = bool(event.get("buy"))
            sol_raw = int(event.get("sol_raw", 0))
            tokens_raw = int(event.get("tokens_raw", 0))
            slot = int(group_slot)
            current = _event_spot(event, group)
            reserve = _event_reserve(event, group)
            is_creator = wallet == creator

            if buy:
                balances[wallet] += tokens_raw
                if not is_creator:
                    all_buyers.add(wallet)
                    if sol_raw >= 50_000_000:
                        qualified_buyers.add(wallet)
                    outside_flow_by_slot[slot] += sol_raw
                elif is_creator:
                    creator_bought += tokens_raw
                    creator_held += tokens_raw
            else:
                balances[wallet] = max(0, balances[wallet] - tokens_raw)
                if not is_creator:
                    outside_flow_by_slot[slot] -= sol_raw
                else:
                    creator_sold += tokens_raw
                    creator_held = max(0, creator_held - tokens_raw)

            if current > 0:
                if current >= peak_spot:
                    peak_spot = current
                    trough_spot = current
                    trough_slot = slot
                    trough_buyers.clear()
                    trough_buy_raw = 0
                elif trough_spot is None or current < trough_spot:
                    trough_spot = current
                    trough_slot = slot
                    trough_buyers.clear()
                    trough_buy_raw = 0
                elif trough_slot is not None and slot <= trough_slot + 35 and buy and not is_creator:
                    trough_buyers.add(wallet)
                    trough_buy_raw += sol_raw

                if (
                    prior_spot is not None
                    and 8.0 <= reserve <= 18.0
                    and current <= prior_spot * 0.85
                    and not buy
                    and not is_creator
                    and sol_raw >= 1_500_000_000
                ):
                    dip_slot = slot
                    dip_index = i
                    dip_buy_count = 0
                    dip_buyers.clear()
                    dip_buy_signatures.clear()
                    dip_buy_trades_by_signature.clear()

                # Match the current Rust tracker: its counter increments for
                # each qualifying TradeEvent, including multiple events in one
                # transaction. This is intentionally different from canonical
                # S3's separate completed-group chooser below.
                if dip_slot is not None:
                    if slot > dip_slot + 2:
                        dip_slot = None
                        dip_index = None
                        dip_buy_count = 0
                        dip_buyers.clear()
                        dip_buy_signatures.clear()
                        dip_buy_trades_by_signature.clear()
                    elif buy and not is_creator and sol_raw >= 50_000_000:
                        dip_buy_count += 1
                        dip_buyers.add(wallet)
                        dip_buy_signatures.add(group["signature"])
                        dip_buy_trades_by_signature[group["signature"]] += 1

                prior_spot = current
                last_event_prior_reserve = previous_reserve
                previous_reserve = reserve

        # Rust applies every event in a transaction, then checks safety and
        # evaluates once with the final event. Counters above retain all
        # per-event changes, including same-transaction S3 confirmations.
        group_spot = _spot(group)
        group_reserve = group["state"].get("rsol_raw", 0) / 1e9
        last_is_outside_buy = bool(last_event and last_event.get("buy") and last_event.get("user") != creator)

        # Current S3 counts qualified TradeEvents, but trigger evaluation waits
        # for the completed transaction and requires its final event to be an
        # outside buy. This preserves same-signature count behavior without
        # using an intermediate event as the transaction trigger.
        if (
            last_is_outside_buy
            and (allow_screened_retries or "s3_deadman" not in seen)
            and dip_slot is not None
            and group_slot <= dip_slot + 2
            and dip_buy_count >= 2
            and len(dip_buyers) >= 2
            and len(qualified_buyers) >= 35
            and 8.0 <= group_reserve <= 18.0
        ):
            seen.add("s3_deadman")
            same_tx_count = dip_buy_trades_by_signature[group["signature"]]
            out.append(_signal(
                t,
                "s3_deadman",
                i,
                outside_buyers=len(all_buyers),
                qualified_outside_buyers=len(qualified_buyers),
                holders=sum(v > 0 for v in balances.values()),
                dip_slot=dip_slot,
                confirmation_trade_count=dip_buy_count,
                confirmation_distinct_buyers=len(dip_buyers),
                confirmation_completed_groups=len(dip_buy_signatures),
                same_transaction_confirmation_possible=same_tx_count >= 2,
                confirming_trades_in_signal_transaction=same_tx_count,
            ))

        # Test current-source S1 after applying the complete transaction, using
        # the final event's buy side exactly as evaluate_entry_triggers does.
        dev_liquidated = creator_bought > 0 and creator_sold > 0 and (
            creator_held == 0 or creator_sold >= creator_bought * 95 // 100
        )
        if (
            (allow_screened_retries or "s1_dev_absorption" not in seen)
            and dev_liquidated
            and 1.0 <= group_reserve <= 5.0
            and peak_spot > 0
            and 0.25 <= 1.0 - group_spot / peak_spot <= 0.60
            and trough_slot is not None
            and group_slot <= trough_slot + 35
            and len(trough_buyers) >= 2
            and trough_buy_raw >= 300_000_000
            and last_is_outside_buy
        ):
            seen.add("s1_dev_absorption")
            out.append(_signal(t, "s1_dev_absorption", i, outside_buyers=len(all_buyers), holders=sum(v > 0 for v in balances.values()), trough_spot=trough_spot))

        # Rust updates peak_spot before evaluating this signal, so equality at
        # the newly observed ATH is accepted. Source threshold is 0.95 SOL.
        if (
            (allow_screened_retries or "s4_upper_ath" not in seen)
            and 16.0 <= group_reserve <= 22.0
            and group_spot >= peak_spot
            and len(qualified_buyers) >= 35
            and last_is_outside_buy
            and int(last_event.get("sol_raw", 0)) >= 950_000_000
        ):
            seen.add("s4_upper_ath")
            out.append(_signal(t, "s4_upper_ath", i, outside_buyers=len(all_buyers), qualified_outside_buyers=len(qualified_buyers), holders=sum(v > 0 for v in balances.values())))

        # Current source S5 requires >=100 observed holders and >=50 unique
        # outside buyers, plus positive five-slot outside net flow.
        if (
            "s5_carryover" not in seen
            and last_event is not None
            and last_event_prior_reserve < 72.0 <= group_reserve
        ):
            flow = sum(value for slot, value in outside_flow_by_slot.items() if group_slot - 4 <= slot <= group_slot)
            if sum(v > 0 for v in balances.values()) >= 100 and len(all_buyers) >= 50 and flow > 0:
                seen.add("s5_carryover")
                out.append(_signal(t, "s5_carryover", i, outside_buyers=len(all_buyers), holders=sum(v > 0 for v in balances.values()), five_slot_net_flow_raw=flow))

        previous_reserve = group_reserve

    return out, []


def _holder_rows(holder_screens: Any, mint: str) -> list[dict[str, Any]]:
    if holder_screens is None:
        return []
    if isinstance(holder_screens, dict):
        if "mint" in holder_screens:
            return [holder_screens] if holder_screens.get("mint") == mint else []
        value = holder_screens.get(mint)
        if value is None:
            return []
        return list(value) if isinstance(value, (list, tuple)) else [value]
    if isinstance(holder_screens, (list, tuple)):
        return [row for row in holder_screens if isinstance(row, dict) and row.get("mint") == mint]
    return []


def _as_ms(value: Any) -> int | None:
    if isinstance(value, (int, float)):
        number = int(value)
        return number * 1000 if abs(number) < 10**12 else number
    if isinstance(value, str):
        try:
            return int(_datetime.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)
        except ValueError:
            return None
    return None


def _holder_verdict(holder_screens: Any, mint: str, at_ms: int) -> dict[str, Any]:
    usable = []
    for row in _holder_rows(holder_screens, mint):
        report = row.get("report") if isinstance(row.get("report"), dict) else row
        completed_raw = report.get("audit_completed_at_ms", row.get("audit_completed_at_ms", row.get("completed_at_ms")))
        if completed_raw is not None:
            completed = int(completed_raw)
        else:
            completed = _as_ms(row.get("timestamp_ms", row.get("timestamp")))
        status = report.get("status", row.get("status"))
        if status not in {"clear", "blocked", "unknown"} or completed is None:
            continue
        if completed <= at_ms:
            usable.append((completed, status, row, report))
    if not usable:
        return dict(status="unknown", reason="no_timestamped_prior_holder_screen")
    completed, status, row, report = max(usable, key=lambda item: item[0])
    age_ms = at_ms - completed
    in_flight = row.get("rescreen_in_flight") is True or row.get("audit_in_flight") is True
    ttl_ms = HOLDER_SCREEN_IN_FLIGHT_TTL_MS if in_flight else HOLDER_SCREEN_CLEAR_TTL_MS
    if age_ms >= ttl_ms:
        return dict(status="unknown", reason="holder_screen_stale", completed_at_ms=completed, age_ms=age_ms, ttl_ms=ttl_ms)

    # The Oct 10 screen log's prose/policy metadata can still say 1.0 SOL /
    # older concentration rules. When raw evidence exists, recompute under the
    # active 0.3 SOL / 50% / 8-of-top-10 / 7% policy instead of trusting status.
    evidence = report.get("evidence", row.get("evidence"))
    if isinstance(evidence, list):
        recomputed = _recompute_holder_status(evidence, report)
        recomputed.update(completed_at_ms=completed, age_ms=age_ms, ttl_ms=ttl_ms, rpc_provider=row.get("rpc_provider"))
        return recomputed

    policy = row.get("policy", report.get("policy", {}))
    policy = policy if isinstance(policy, dict) else {}
    recorded_low = policy.get("low_balance_lamports")
    if recorded_low is not None and int(recorded_low) != LOW_SOL_THRESHOLD_LAMPORTS:
        return dict(status="unknown", reason="stale_holder_screen_policy_without_raw_evidence", completed_at_ms=completed, age_ms=age_ms, ttl_ms=ttl_ms)
    recorded_share = policy.get("low_sol_supply_block_pct")
    if recorded_share is None and policy.get("low_balance_fraction_gte") is not None:
        recorded_share = float(policy["low_balance_fraction_gte"]) * 100.0
    if recorded_share is not None and float(recorded_share) != LOW_SOL_SUPPLY_BLOCK_PCT:
        return dict(status="unknown", reason="stale_holder_screen_policy_without_raw_evidence", completed_at_ms=completed, age_ms=age_ms, ttl_ms=ttl_ms)
    recorded_top10 = policy.get("top10_low_sol_block_count")
    if recorded_top10 is not None and int(recorded_top10) != TOP10_LOW_SOL_BLOCK_COUNT:
        return dict(status="unknown", reason="stale_holder_screen_policy_without_raw_evidence", completed_at_ms=completed, age_ms=age_ms, ttl_ms=ttl_ms)
    return dict(
        status=status,
        reason=report.get("reason") or row.get("reason"),
        completed_at_ms=completed,
        age_ms=age_ms,
        ttl_ms=ttl_ms,
        rpc_provider=row.get("rpc_provider"),
    )


def _recompute_holder_status(evidence: list[dict[str, Any]], report: dict[str, Any]) -> dict[str, Any]:
    def first_value(row: dict[str, Any], keys: tuple[str, ...]) -> Any:
        return next((row[key] for key in keys if row.get(key) is not None), None)

    low_sol_tokens = 0
    top10_low_count = 0
    top10_low_tokens = 0
    single_low_whale = False
    unresolved = False
    if len(evidence) < 5:
        return dict(status="unknown", reason="fewer_than_five_holder_wallets", sampled_wallets=len(evidence))
    for i, holder in enumerate(evidence):
        raw_tokens = first_value(holder, ("summed_token_amount_raw", "token_amount_raw", "tokens_raw"))
        sol_lamports = first_value(holder, ("sol_balance_lamports", "lamports", "sol_lamports"))
        try:
            raw_tokens = int(raw_tokens)
        except (TypeError, ValueError):
            unresolved = True
            continue
        try:
            is_low_sol = int(sol_lamports) < LOW_SOL_THRESHOLD_LAMPORTS
        except (TypeError, ValueError):
            unresolved = True
            continue
        if not is_low_sol:
            continue
        low_sol_tokens += raw_tokens
        if i < 10:
            top10_low_count += 1
            top10_low_tokens += raw_tokens
        if raw_tokens * 100 >= TOTAL_SUPPLY_RAW * int(SINGLE_LOW_SOL_WHALE_PCT):
            single_low_whale = True

    low_supply_pct = 100.0 * low_sol_tokens / TOTAL_SUPPLY_RAW
    top10_low_supply_pct = 100.0 * top10_low_tokens / TOTAL_SUPPLY_RAW
    reasons = []
    if low_supply_pct >= LOW_SOL_SUPPLY_BLOCK_PCT:
        reasons.append("low_sol_holders_at_least_50pct_supply")
    elif top10_low_count >= TOP10_LOW_SOL_BLOCK_COUNT:
        reasons.append("at_least_8_of_top10_low_sol_holders")
    elif single_low_whale:
        reasons.append("single_low_sol_holder_at_least_7pct_supply")
    if reasons:
        return dict(
            status="blocked",
            reason=", ".join(reasons),
            reasons=reasons,
            low_sol_supply_pct=low_supply_pct,
            top10_low_sol_count=top10_low_count,
            top10_low_sol_supply_pct=top10_low_supply_pct,
            raw_policy_recomputed=True,
            incomplete_evidence=unresolved or report.get("unknown_wallets", 0) > 0,
        )
    if unresolved or report.get("unknown_wallets", 0) > 0:
        return dict(status="unknown", reason="incomplete_holder_raw_evidence", raw_policy_recomputed=True)
    return dict(
        status="clear",
        reason=None,
        low_sol_supply_pct=low_supply_pct,
        top10_low_sol_count=top10_low_count,
        top10_low_sol_supply_pct=top10_low_supply_pct,
        raw_policy_recomputed=True,
    )


def _local_screen(t: dict[str, Any], index: int) -> dict[str, Any]:
    """Reconstruct checks visible in curve trade history; never infer Jito."""
    creation_slot = int(t.get("creation_slot", t["groups"][0]["slot"]))
    creation_time = int(t["creation_time"])
    balances: collections.Counter[str] = collections.Counter()
    first_two_slot_buys = 0
    first_eleven_slot_buys = 0
    creator_bought = creator_sold = creator_held = 0
    max_seen_slot = creation_slot
    for group in t["groups"][: index + 1]:
        max_seen_slot = max(max_seen_slot, int(group["slot"]))
        for event in group.get("events", []):
            wallet = event["user"]
            is_buy = bool(event.get("buy"))
            tokens = int(event.get("tokens_raw", 0))
            if is_buy:
                balances[wallet] += tokens
                if int(group["slot"]) <= creation_slot + 1:
                    first_two_slot_buys += tokens
                if int(group["slot"]) <= creation_slot + 10:
                    first_eleven_slot_buys += tokens
                if wallet == t["creator"]:
                    creator_bought += tokens
                    creator_held += tokens
            else:
                balances[wallet] = max(0, balances[wallet] - tokens)
                if wallet == t["creator"]:
                    creator_sold += tokens
                    creator_held = max(0, creator_held - tokens)

    group = t["groups"][index]
    state = group["state"]
    reserve = state.get("rsol_raw", 0) / 1e9
    spot = _spot(group)
    age = max(0, int(group["block_time"]) - creation_time)
    market_cap_usd = spot * 1_000_000.0 * CURRENT_SCREEN_SOL_USD
    dev_liquidated = creator_bought > 0 and creator_sold > 0 and (
        creator_held == 0 or creator_sold >= creator_bought * 95 // 100
    )
    in_scan_window = market_cap_usd >= CURRENT_MIN_SCAN_MCAP_USD or (dev_liquidated and reserve >= 1.0)

    explicit_whitelist = t.get("is_whitelisted")
    if explicit_whitelist is None:
        metadata = t.get("creation_metadata") or {}
        explicit_whitelist = metadata.get("is_whitelisted")
    whitelist_status = "explicit_true" if explicit_whitelist is True else "explicit_false" if explicit_whitelist is False else "unknown"
    if explicit_whitelist is True:
        return dict(status="clear", reasons=[], whitelist_status=whitelist_status, market_cap_usd=market_cap_usd, scan_window=True)

    reasons = []
    if not in_scan_window:
        reasons.append("outside_current_scan_window")

    early_spawn = age <= 10 and market_cap_usd < 10_000.0
    if early_spawn and first_two_slot_buys > TOTAL_SUPPLY_RAW * 0.20:
        reasons.append("block_0_bundle_rule_gt20pct_first_two_slots")
    elif early_spawn and first_eleven_slot_buys > TOTAL_SUPPLY_RAW * 0.20:
        reasons.append("early_sniper_rule_gt20pct_first_eleven_slots")

    sorted_balances = sorted((max(0, value) for value in balances.values()), reverse=True)
    if sorted_balances and sorted_balances[0] > 75_000_000_000_000 and reserve < 15.0:
        reasons.append("single_holder_gt7_5pct_below15_sol_reserve")
    if sum(sorted_balances[:3]) > 180_000_000_000_000:
        reasons.append("top3_gt18pct_supply")
    if sum(sorted_balances[:5]) > 250_000_000_000_000:
        reasons.append("top5_gt25pct_supply")
    if sum(sorted_balances[:10]) > 350_000_000_000_000:
        reasons.append("top10_gt35pct_supply")
    return dict(
        status="blocked" if reasons else "clear",
        reasons=reasons,
        whitelist_status=whitelist_status,
        market_cap_usd=market_cap_usd,
        scan_window=in_scan_window,
        early_spawn=early_spawn,
        first_two_slot_buy_supply_pct=100.0 * first_two_slot_buys / TOTAL_SUPPLY_RAW,
        first_eleven_slot_buy_supply_pct=100.0 * first_eleven_slot_buys / TOTAL_SUPPLY_RAW,
        reserve_sol=reserve,
        holder_count=sum(value > 0 for value in balances.values()),
        source_note="block-0-named rule counts all buys in creation slot and next slot; tape does not prove Jito bundle membership",
    )


def _screen_signal(t: dict[str, Any], signal: dict[str, Any], holder_screens: Any) -> dict[str, Any]:
    index = _group_index(t, signal)
    group = t["groups"][index]
    at_ms = int(group["block_time"]) * 1000
    local = _local_screen(t, index)
    if local["status"] == "blocked":
        return dict(status="blocked", reasons=local["reasons"], local=local, holder=dict(status="not_needed"))
    if local["whitelist_status"] == "explicit_true":
        return dict(status="clear", reasons=[], local=local, holder=dict(status="bypassed_explicit_whitelist"))
    holder = _holder_verdict(holder_screens, t["mint"], at_ms)
    if holder["status"] == "blocked":
        return dict(status="blocked", reasons=[holder.get("reason") or "holder_screen_blocked"], local=local, holder=holder)
    if holder["status"] != "clear":
        return dict(status="unknown", reasons=[holder.get("reason") or "holder_screen_unknown"], local=local, holder=holder)
    return dict(status="clear", reasons=[], local=local, holder=holder)


def _local_only_signal(t: dict[str, Any], signal: dict[str, Any]) -> dict[str, Any]:
    """Apply tape-visible gates and leave the uncollected RPC check explicit."""
    local = _local_screen(t, _group_index(t, signal))
    return dict(
        status="blocked" if local["status"] == "blocked" else "local_only",
        reasons=list(local["reasons"]),
        local=local,
        holder_status="not_applied_historical_missing",
        holder=dict(status="not_applied_historical_missing"),
    )


def _screen_reclaim_entry(t: dict[str, Any], base: dict[str, Any], index: int, holder_screens: Any) -> dict[str, Any]:
    at_ms = int(t["groups"][index]["block_time"]) * 1000
    verdict = _holder_verdict(holder_screens, t["mint"], at_ms)
    if verdict["status"] == "blocked":
        return dict(status="blocked", reasons=[verdict.get("reason") or "holder_screen_blocked"], holder=verdict)
    if verdict["status"] != "clear":
        return dict(status="unknown", reasons=[verdict.get("reason") or "holder_screen_unknown"], holder=verdict)
    return dict(status="clear", reasons=[], holder=verdict)


def _apply_reclaim(
    t: dict[str, Any],
    candidates: list[dict[str, Any]],
    screen_mode: str,
    holder_screens: Any,
    screen_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Apply the launcher-default S2/S4 8%-dip then original-level reclaim."""
    out: list[dict[str, Any]] = []
    admitted_rules: set[str] = set()
    armed_rules: set[str] = set()
    for base in candidates:
        if base["rule"] in admitted_rules or base["rule"] in armed_rules:
            continue
        if base["rule"] not in {"s2_survival_shelf", "s4_upper_ath"}:
            if screen_mode == "off":
                out.append(base)
                continue
            verdict = (
                _local_only_signal(t, base)
                if screen_mode == "local"
                else _screen_signal(t, base, holder_screens)
            )
            screen_rows.append(dict(mint=t["mint"], rule=base["rule"], index=base["index"], phase="entry", **verdict))
            if verdict["status"] in {"clear", "local_only"}:
                signal = dict(base, screen_status=verdict["status"])
                if screen_mode == "local":
                    signal["holder_status"] = "not_applied_historical_missing"
                out.append(signal)
                admitted_rules.add(base["rule"])
            continue

        base_index = _group_index(t, base)
        level = _spot(t["groups"][base_index])
        if level <= 0:
            screen_rows.append(dict(mint=t["mint"], rule=base["rule"], index=base_index, phase="arm", status="unknown", reasons=["invalid_breakout_spot"]))
            continue
        if screen_mode in {"local", "onchain"}:
            arm_screen = _local_only_signal(t, base)
            if screen_mode == "onchain" and arm_screen["status"] == "local_only":
                arm_screen["status"] = "clear"
                arm_screen["holder_status"] = "deferred_to_reclaim_entry"
                arm_screen["holder"] = {"status": "deferred_to_reclaim_entry"}
            screen_rows.append(dict(mint=t["mint"], rule=base["rule"], index=base_index, phase="arm", **arm_screen))
            if arm_screen["status"] not in {"clear", "local_only"}:
                continue
        # A source signal arms at most one reclaim watch per strategy. Only a
        # blocked local gate leaves the strategy eligible for a later trigger.
        armed_rules.add(base["rule"])

        armed_ms = int(t["groups"][base_index]["block_time"]) * 1000
        pulled_back = False
        trough = level
        chosen = None
        for j in range(base_index + 1, len(t["groups"])):
            group = t["groups"][j]
            now_ms = int(group["block_time"]) * 1000
            if now_ms - armed_ms > RECLAIM_WINDOW_MS:
                break
            spot = _spot(group)
            if spot < trough:
                trough = spot
            if not pulled_back and spot <= level * (1.0 - RECLAIM_PULLBACK):
                pulled_back = True
            events = group.get("events", [])
            # The runtime advances the reclaim arm once after the complete
            # transaction, using its final trade's side.
            has_buy = bool(events and events[-1].get("buy"))
            if pulled_back and spot >= level and has_buy:
                chosen = dict(
                    base,
                    original_signal_signature=base["signal_signature"],
                    original_signal_slot=base["slot"],
                    signal_signature=group["signature"],
                    index=j,
                    slot=group["slot"],
                    time=group["block_time"],
                    reserve=group["state"].get("rsol_raw", 0) / 1e9,
                    breakout_spot=level,
                    reclaim_trough_spot=trough,
                    reclaim_age_seconds=(now_ms - armed_ms) / 1000,
                    entry_mode="reclaim",
                )
                break
        if chosen is None:
            screen_rows.append(dict(
                mint=t["mint"], rule=base["rule"], index=base_index,
                phase="reclaim", status="no_reclaim_within_180s" if pulled_back else "no_8pct_pullback_within_180s",
                level_spot=level, pulled_back=pulled_back,
            ))
            continue
        if screen_mode == "onchain":
            entry_screen = _screen_reclaim_entry(t, base, chosen["index"], holder_screens)
            screen_rows.append(dict(mint=t["mint"], rule=base["rule"], index=chosen["index"], phase="entry", **entry_screen))
            if entry_screen["status"] != "clear":
                continue
            chosen["screen_status"] = "clear"
        elif screen_mode == "local":
            # Runtime repeats the historical holder check at reclaim. This
            # diagnostic intentionally reports that unobservable gate as absent.
            entry_screen = dict(
                status="local_only",
                reasons=[],
                holder_status="not_applied_historical_missing",
                holder=dict(status="not_applied_historical_missing"),
            )
            screen_rows.append(dict(mint=t["mint"], rule=base["rule"], index=chosen["index"], phase="entry", **entry_screen))
            chosen["screen_status"] = "local_only"
            chosen["holder_status"] = "not_applied_historical_missing"
        out.append(chosen)
        admitted_rules.add(base["rule"])
    return out


def detect(
    t: dict[str, Any],
    mode: str = "canonical",
    screen_mode: str = "off",
    holder_screens: Any = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return causal entry signals plus a provenance and screen audit.

    ``mode='canonical'`` uses core_plan's exact S1-S5 signal detector and the
    frozen separate-two-buy-group S3 confirmation. ``mode='current'`` ports
    current Rust S1/S3/S4/S5 predicates, keeps canonical S2, and applies the
    launcher's default S2/S4 reclaim wrapper. ``screen_mode='onchain'`` admits
    only signals with clear local screens and a clear, fresh historical holder
    row (except an explicitly whitelisted mint). Unknown history fails closed.
    Reclaim strategies check local gates at arm and holder history at entry.
    ``screen_mode='local'`` is diagnostic only: it applies tape-reconstructable
    local screens and explicitly records that the historical holder gate was
    not applied.
    """
    if mode not in {"canonical", "current"}:
        raise ValueError("mode must be 'canonical' or 'current'")
    if screen_mode not in {"off", "local", "onchain"}:
        raise ValueError("screen_mode must be 'off', 'local', or 'onchain'")
    errors: list[dict[str, Any]] = []
    screen_rows: list[dict[str, Any]] = []
    if not t.get("normal", False):
        return [], dict(
            mint=t.get("mint"), mode=mode, screen_mode=screen_mode,
            candidate_count=0, admitted_count=0, errors=[dict(reason="unsupported_non_normal_tape")],
            screen_results=[],
        )

    if mode == "canonical":
        candidates, errors = _canonical_candidates(t)
        if screen_mode == "off":
            signals = candidates
        else:
            signals = []
            for candidate in candidates:
                verdict = (
                    _local_only_signal(t, candidate)
                    if screen_mode == "local"
                    else _screen_signal(t, candidate, holder_screens)
                )
                screen_rows.append(dict(mint=t["mint"], rule=candidate["rule"], index=_group_index(t, candidate), phase="entry", **verdict))
                if verdict["status"] in {"clear", "local_only"}:
                    signal = dict(candidate, screen_status=verdict["status"])
                    if screen_mode == "local":
                        signal["holder_status"] = "not_applied_historical_missing"
                    signals.append(signal)
    else:
        current_candidates, current_errors = _current_non_s2_candidates(
            t, allow_screened_retries=screen_mode != "off"
        )
        errors.extend(current_errors)
        s2_candidates, s2_errors = _canonical_candidates(t)
        errors.extend(s2_errors)
        candidates = current_candidates + [s for s in s2_candidates if s["rule"] == "s2_survival_shelf"]
        candidates.sort(key=lambda signal: (_group_index(t, signal), signal["rule"]))
        signals = _apply_reclaim(t, candidates, screen_mode, holder_screens, screen_rows)

    counts = collections.Counter(signal["rule"] for signal in signals)
    audit = dict(
        mint=t["mint"],
        mode=mode,
        screen_mode=screen_mode,
        current_entry_mode="reclaim" if mode == "current" else None,
        candidate_count=len(candidates),
        admitted_count=len(signals),
        signals_by_rule=dict(counts),
        errors=errors,
        screen_results=screen_rows,
        data_limits=[
            "historical holder RPC screens are not derived from trade tapes; missing or stale rows remain unknown",
            "local screen mode omits historical holder balance checks and labels admitted rows local_only",
            f"holder clear freshness is limited to {HOLDER_SCREEN_CLEAR_TTL_MS // 1000}s; only explicitly in-flight rescreens use {HOLDER_SCREEN_IN_FLIGHT_TTL_MS // 1000}s",
            "whitelist bypass applies only when an explicit is_whitelisted=true field is present",
            "the source calls the first-two-slot token rule a block-0/Jito bundle, but tape history cannot verify Jito membership",
        ],
    )
    return signals, audit

