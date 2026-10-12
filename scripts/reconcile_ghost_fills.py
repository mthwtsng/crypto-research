#!/usr/bin/env python3
"""Append-only RPC audit for paper trade intents and fills.

This tool authenticates observed transaction order and, when an intent has no
submitted signature, reports quote-only placement sensitivities. It never
claims an unsubmitted transaction filled and never creates a portfolio PnL
replay.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import importlib
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Iterable


ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_SHYFT_RPC = "https://rpc.shyft.to?api_key=owfc3zuSXH37YG0U"
LAMPORTS_PER_SOL = 1_000_000_000
RESERVE_KEYS = ("vsol_raw", "vtokens_raw", "rsol_raw", "rtokens_raw")
NATIVE_MINTS = {"11111111111111111111111111111111", "So11111111111111111111111111111111111111112"}
CENTRAL_K_COUNTS = ((0, 29), (1, 20), (2, 83))


def _load_approved_curve_helpers():
    """Load the approved day_general integer quote implementation lazily."""
    helper = ROOT / "research" / "day_general_20261004" / "helpers"
    adapter = ROOT / "research" / "wallet_curve_entry_discovery_20261007"
    for path in (str(helper), str(adapter)):
        if path not in sys.path:
            sys.path.insert(0, path)
    # The adapter delegates integer fees, moved-reserve and sell quotes to the
    # approved day_general family, and supplies the exact fee-inclusive buy.
    return importlib.import_module("curve_adapter")


CURVE = _load_approved_curve_helpers()


class ReconcileError(RuntimeError):
    pass


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json_hash(value: Any) -> str:
    return _sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value, 10)
        except ValueError:
            return None
    return None


def _read_jsonl(path: pathlib.Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as source:
        for line_no, line in enumerate(source, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ReconcileError(f"invalid JSONL at {path}:{line_no}: {exc.msg}") from exc
            if not isinstance(value, dict):
                raise ReconcileError(f"expected JSON object at {path}:{line_no}")
            value = dict(value)
            value.setdefault("_input_line", line_no)
            rows.append(value)
    return rows


def _event_name(row: dict[str, Any]) -> str:
    return str(row.get("event") or row.get("type") or row.get("record_type") or "").upper()


def _signature_from_tx(tx: dict[str, Any]) -> str | None:
    transaction = tx.get("transaction") or {}
    if isinstance(transaction, list):
        signatures = transaction
    else:
        signatures = transaction.get("signatures") or []
    return str(signatures[0]) if signatures else None


def _block_transactions(block: dict[str, Any]) -> list[dict[str, Any]]:
    txs = block.get("transactions")
    if isinstance(txs, list):
        return txs
    return []


def canonical_block_index(block: dict[str, Any] | None, signature: str) -> int | None:
    """Return the zero-based position from the canonical getBlock response."""
    if not isinstance(block, dict):
        return None
    txs = _block_transactions(block)
    if txs:
        for index, tx in enumerate(txs):
            if _signature_from_tx(tx) == signature:
                return index
        return None
    signatures = block.get("signatures")
    if isinstance(signatures, list):
        try:
            return signatures.index(signature)
        except ValueError:
            return None
    return None


def _rpc_url(cli_value: str | None) -> str:
    if cli_value:
        return cli_value
    for name in ("SOLANA_RPC_URL", "SHYFT_RPC_URL", "ALCHEMY_RPC_URL"):
        value = os.environ.get(name)
        if value:
            return value
    return DEFAULT_SHYFT_RPC


class RpcClient:
    """Small read-only JSON-RPC client with immutable per-call raw cache."""

    def __init__(self, url: str, cache_dir: pathlib.Path, timeout: float = 25.0):
        self._url = url
        self.cache_dir = cache_dir
        self.timeout = timeout
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def call(self, method: str, params: list[Any]) -> Any:
        key = _json_hash({"method": method, "params": params})
        cache_path = self.cache_dir / f"{method}_{key}.json"
        if cache_path.exists():
            envelope = json.loads(cache_path.read_text(encoding="utf-8"))
        else:
            request_body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
            request = urllib.request.Request(self._url, data=request_body,
                                             headers={"Content-Type": "application/json"}, method="POST")
            last_error: Exception | None = None
            envelope = None
            for attempt in range(3):
                try:
                    with urllib.request.urlopen(request, timeout=self.timeout) as response:
                        envelope = json.loads(response.read())
                    break
                except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                    last_error = exc
                    if attempt < 2:
                        time.sleep(0.25 * (attempt + 1))
            if envelope is None:
                raise ReconcileError(f"RPC {method} failed: {type(last_error).__name__ if last_error else 'unknown'}")
            # Preserve the untouched RPC envelope; it contains no request URL.
            cache_path.write_text(json.dumps(envelope, separators=(",", ":")) + "\n", encoding="utf-8")
        if not isinstance(envelope, dict):
            raise ReconcileError(f"RPC {method} returned a non-object envelope")
        if envelope.get("error"):
            raise ReconcileError(f"RPC {method} error: {envelope['error'].get('code', 'unknown')}")
        return envelope.get("result")


class ChainReader:
    def __init__(self, rpc: RpcClient, commitment: str, max_version: int, next_slot_limit: int,
                 actual_slot_limit: int):
        self.rpc = rpc
        self.commitment = commitment
        self.max_version = max_version
        self.next_slot_limit = next_slot_limit
        self.actual_slot_limit = actual_slot_limit
        self._blocks: dict[tuple[int, str], dict[str, Any] | None] = {}
        self._transactions: dict[str, dict[str, Any] | None] = {}
        self._decoder = importlib.import_module("decoder")

    def transaction(self, signature: str) -> dict[str, Any] | None:
        if signature not in self._transactions:
            self._transactions[signature] = self.rpc.call(
                "getTransaction", [signature, {"encoding": "jsonParsed", "commitment": self.commitment,
                                               "maxSupportedTransactionVersion": self.max_version}])
        return self._transactions[signature]

    def block(self, slot: int, details: str = "full") -> dict[str, Any] | None:
        key = (slot, details)
        if key not in self._blocks:
            config = {"commitment": self.commitment, "transactionDetails": details,
                      "encoding": "jsonParsed", "rewards": False,
                      "maxSupportedTransactionVersion": self.max_version}
            self._blocks[key] = self.rpc.call("getBlock", [slot, config])
        return self._blocks[key]

    def next_produced_block(self, anchor_slot: int) -> tuple[int | None, dict[str, Any] | None, str | None]:
        prior_slot = anchor_slot
        for slot in range(anchor_slot + 1, anchor_slot + self.next_slot_limit + 1):
            block = self.block(slot)
            if block is None:
                continue
            parent = _int_or_none(block.get("parentSlot"))
            if parent != prior_slot:
                return None, None, "next_slot_parent_link_gap_or_fork"
            return slot, block, None
        return None, None, "next_produced_slot_unavailable"

    def trade_groups(self, block: dict[str, Any] | None, mint: str,
                     observations: dict[str, list[dict[str, Any]]], *,
                     start_index: int = 0, stop_after: int | None = None) -> tuple[list[dict[str, Any]], str | None]:
        if not isinstance(block, dict) or not isinstance(block.get("transactions"), list):
            return [], "full_block_transactions_unavailable"
        groups = []
        for index, tx in enumerate(block["transactions"][start_index:], start_index):
            if stop_after is not None and len(groups) >= stop_after:
                break
            if not isinstance(tx, dict) or not isinstance(tx.get("meta"), dict):
                return groups, "transaction_metadata_missing_in_full_block"
            sig = _signature_from_tx(tx)
            meta = tx["meta"]
            if meta.get("err") is not None:
                continue
            events = self._decoded_events(tx)
            relevant = [event for event in events if _event_mint(event) == mint and _event_is_sol_curve(event)]
            event_source = "canonical_getBlock_transaction_logs"
            if not relevant and sig:
                relevant = [event for event in observations.get(sig, [])
                            if _event_mint(event) == mint and _event_is_sol_curve(event)]
                event_source = "captured_observation_events_unverified"
            states = [state for event in relevant if (state := state_from_event(event)) is not None]
            if not states:
                continue
            groups.append({"signature": sig, "transaction_index": index, "events": relevant,
                           "state": states[-1], "event_source": event_source})
        return groups, None

    def _decoded_events(self, tx: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            return [dict(event) for event in self._decoder.events(tx)]
        except (KeyError, TypeError, ValueError, IndexError):
            return []

    def receipt_trade_events(self, tx: dict[str, Any], signature: str,
                             observations: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
        if (tx.get("meta") or {}).get("err") is not None:
            return []
        return self._decoded_events(tx)

    def receipt_events_for_mint(self, tx: dict[str, Any], signature: str, mint: str,
                                observations: dict[str, list[dict[str, Any]]]) -> tuple[list[dict[str, Any]], str]:
        events = self.receipt_trade_events(tx, signature, observations)
        relevant = [event for event in events if _event_mint(event) == mint]
        if relevant:
            return relevant, "canonical_getTransaction_logs"
        if (tx.get("meta") or {}).get("err") is None:
            relevant = [event for event in observations.get(signature, []) if _event_mint(event) == mint]
            if relevant:
                return relevant, "captured_observation_events_unverified"
        return [], "no_trade_event"


def _event_mint(event: dict[str, Any]) -> str | None:
    return _first_str(event, "mint", "token_mint")


def _event_is_sol_curve(event: dict[str, Any]) -> bool:
    venue = str(event.get("venue") or "curve").lower()
    if venue not in {"curve", "pump_curve", "bonding_curve"}:
        return False
    quote_mint = _first_str(event, "quote_mint", "quote_asset")
    if quote_mint is not None:
        return quote_mint in NATIVE_MINTS
    return event.get("quote_is_sol") is not False


def _first_str(row: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def state_from_event(event: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(event, dict):
        return None
    state = event.get("state") if isinstance(event.get("state"), dict) else event
    aliases = {
        "vsol_raw": ("vsol_raw", "virtual_sol_reserves", "virtual_quote_reserves"),
        "vtokens_raw": ("vtokens_raw", "virtual_token_reserves"),
        "rsol_raw": ("rsol_raw", "real_sol_reserves", "real_quote_reserves"),
        "rtokens_raw": ("rtokens_raw", "real_token_reserves"),
        "fee_bps": ("fee_bps", "fee_basis_points"),
        "creator_fee_bps": ("creator_fee_bps", "creator_fee_basis_points"),
    }
    out: dict[str, int] = {}
    for target, names in aliases.items():
        value = next((_int_or_none(state.get(name)) for name in names if _int_or_none(state.get(name)) is not None), None)
        if value is not None:
            out[target] = value
    if not all(key in out for key in RESERVE_KEYS):
        return None
    explicit_policy = state.get("fee_policy_known", event.get("fee_policy_known"))
    out["fee_policy_known"] = (explicit_policy is not False and
                               "fee_bps" in out and "creator_fee_bps" in out)
    return out


def _event_side(event: dict[str, Any]) -> str | None:
    value = event.get("buy", event.get("is_buy"))
    return "buy" if value is True else "sell" if value is False else None


def _event_amount(event: dict[str, Any], side: str) -> tuple[int | None, int | None]:
    tokens = _int_or_none(event.get("tokens_raw", event.get("token_amount")))
    sol = _int_or_none(event.get("sol_raw", event.get("sol_amount", event.get("quote_amount"))))
    return tokens, sol


def _pre_state_from_event(event: dict[str, Any]) -> dict[str, int] | None:
    post = state_from_event(event)
    side = _event_side(event)
    tokens, sol = _event_amount(event, side or "")
    if post is None or side is None or tokens is None or sol is None:
        return None
    sign = 1 if side == "buy" else -1
    pre = dict(post)
    pre["vsol_raw"] -= sign * sol
    pre["rsol_raw"] -= sign * sol
    pre["vtokens_raw"] += sign * tokens
    pre["rtokens_raw"] += sign * tokens
    if any(pre[key] < 0 for key in RESERVE_KEYS):
        return None
    return pre


def _reserves_equal(left: dict[str, int], right: dict[str, int]) -> bool:
    return all(_int_or_none(left.get(k)) == _int_or_none(right.get(k)) for k in RESERVE_KEYS)


def _advance_trade_group(state: dict[str, int], group: dict[str, Any]) -> tuple[dict[str, int] | None, str | None]:
    prior = dict(state)
    for event in group["events"]:
        pre = _pre_state_from_event(event)
        post = state_from_event(event)
        if post is None:
            return None, "trade_event_reserve_state_missing"
        if pre is not None and not _reserves_equal(prior, pre):
            return None, "reserve_transition_gap"
        if pre is None:
            return None, "curve_trade_transition_unverifiable"
        prior = post
    return prior, None


def _input_events_by_signature(rows: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in rows:
        sig = _first_str(row, "signature", "source_signature", "tx_signature")
        if not sig:
            continue
        events = row.get("events")
        if isinstance(events, list):
            result[sig].extend(event for event in events if isinstance(event, dict))
        elif state_from_event(row) is not None:
            result[sig].append(row)
    return dict(result)


def _source_signature(row: dict[str, Any]) -> str | None:
    return _first_str(row, "source_signature", "anchor_signature", "trigger_signature")


def _source_slot(row: dict[str, Any]) -> int | None:
    for name in ("source_slot", "anchor_slot", "trigger_slot"):
        value = _int_or_none(row.get(name))
        if value is not None:
            return value
    return None


def _source_logged_index(row: dict[str, Any]) -> int | None:
    for name in ("source_transaction_index", "anchor_transaction_index", "transaction_index"):
        value = _int_or_none(row.get(name))
        if value is not None:
            return value
    return None


def _actual_signature(row: dict[str, Any], event: str) -> str | None:
    for name in ("our_signature", "submitted_signature", "tx_signature", "fill_signature", "signature"):
        value = _first_str(row, name)
        if value:
            if name == "signature" and value == _source_signature(row):
                continue
            if name == "signature" and event not in {"FILL", "FAIL", "CLOSE", "TRADE"}:
                continue
            return value
    return None


def _normalize_side(row: dict[str, Any], event: str) -> str | None:
    side = str(row.get("side") or "").lower()
    if side in {"buy", "sell"}:
        return side
    if event in {"OPEN", "BUY"}:
        return "buy"
    if event in {"CLOSE", "SELL"}:
        return "sell"
    return None


def _group_action_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for index, row in enumerate(rows):
        event = _event_name(row)
        if event not in {"INTENT", "FILL", "FAIL", "CLOSE", "OPEN", "BUY", "SELL", "TRADE"}:
            continue
        intent_id = _first_str(row, "intent_id")
        position_id = _first_str(row, "position_id")
        if intent_id:
            key = "intent:" + intent_id
        elif event in {"OPEN", "CLOSE"}:
            # Old rows lack a stable intent identifier; do not infer a link from
            # mint/timestamps because that can merge competing positions.
            key = f"legacy:{row.get('_input_line', index)}:{event}"
        elif position_id:
            key = f"position:{position_id}:{row.get('side', event)}"
        else:
            key = f"row:{row.get('_input_line', index)}"
        groups[key].append(row)

    normalized = []
    for key, records in groups.items():
        intent = next((row for row in records if _event_name(row) == "INTENT"), None)
        fills = [row for row in records if _event_name(row) == "FILL"]
        failures = [row for row in records if _event_name(row) == "FAIL"]
        closes = [row for row in records if _event_name(row) == "CLOSE"]
        legacy = intent or (fills[-1] if fills else failures[-1] if failures else closes[-1] if closes else records[0])
        merged: dict[str, Any] = {}
        for row in records:
            merged.update({k: v for k, v in row.items() if not k.startswith("_")})
        # Intent anchors and sizing remain the base if a post-execution event
        # omits them; fill receipt fields always win when present.
        if intent:
            merged = {**intent, **merged}
        action = fills[-1] if fills else failures[-1] if failures else closes[-1] if closes else legacy
        event = _event_name(action)
        side = _normalize_side(merged, event)
        if event == "CLOSE" and not merged.get("side"):
            side = "sell"
        normalized.append({"key": key, "row": merged, "action": action,
                           "action_event": event, "side": side,
                           "position_id": _first_str(merged, "position_id"),
                           "intent_id": _first_str(merged, "intent_id"),
                           "mint": _first_str(merged, "mint"), "records": records})
    return normalized


def _placement_hash(identity: str, label: str) -> bytes:
    return hashlib.sha256(f"ghost-placement-v1|{identity}|{label}".encode()).digest()


def placement_seed(identity: str) -> str:
    """Stable seed independent of any observed fill or outcome."""
    return hashlib.sha256(f"ghost-placement-v1|{identity}".encode()).hexdigest()


def _uniform(identity: str, label: str) -> float:
    return int.from_bytes(_placement_hash(identity, label)[:8], "big") / 2**64


def _central_same_slot_k(identity: str) -> int:
    u = _uniform(identity, "same-slot-k")
    threshold = 0
    for k, count in CENTRAL_K_COUNTS:
        threshold += count
        if u < threshold / 132:
            return k
    return 2


def _action_amount(row: dict[str, Any], side: str) -> int | None:
    fields = ("gross_budget_raw", "quote_amount_raw", "amount_in_raw") if side == "buy" else (
        "quantity_tokens_raw", "tokens_raw", "amount_tokens_raw")
    for name in fields:
        value = _int_or_none(row.get(name))
        if value is not None:
            return value
    return None


def _min_output(row: dict[str, Any]) -> int | None:
    for name in ("min_output_raw", "min_tokens_raw", "minimum_output_raw", "minimum_quote_raw"):
        value = _int_or_none(row.get(name))
        if value is not None:
            return value
    return None


def quote_at_state(row: dict[str, Any], side: str, state: dict[str, Any],
                   *, source: str, boundary: dict[str, Any], placement: str,
                   seed: str, outcome_independent: bool = True) -> dict[str, Any]:
    """Quote finite intent size against one integer reserve state.

    The quote includes its own curve impact and protocol/creator fees. It does
    not simulate subsequent participant reactions or claim actual inclusion.
    """
    if (row.get("fee_policy_known") is False or state.get("fee_policy_known") is False or
            "fee_bps" not in state or "creator_fee_bps" not in state):
        return {"status": "fee_policy_unknown_at_boundary", "classification": "unresolved",
                "actual_fill_established": False, "state_source": source,
                "boundary": boundary, "placement": placement,
                "placement_seed": seed,
                "limitation": "The intent or source event does not establish the applicable fee policy; no fee-dependent hypothetical quote is produced."}
    amount = _action_amount(row, side)
    if amount is None or amount <= 0:
        return {"status": "missing_intent_size", "classification": "unresolved"}
    if state.get("rtokens_raw", 1) == 0:
        return {"status": "graduated_requires_authenticated_amm_continuation",
                "classification": "graduated_unresolved", "curve_sell_created": False}
    before = dict(state)
    if side == "buy":
        result = CURVE.buy_budget(before, amount)
        if not result:
            return {"status": "unquotable_buy_at_boundary", "classification": "unresolved"}
        curve_sol, tokens = result
        protocol_fee = CURVE.fee(curve_sol, before["fee_bps"])
        creator_fee = CURVE.fee(curve_sol, before["creator_fee_bps"])
        gross_cost = curve_sol + protocol_fee + creator_fee
        after = CURVE.moved(before, curve_sol, tokens, True)
        output = tokens
        output_name = "tokens_raw"
        actual_from_instruction = False
    else:
        tokens = amount
        result = CURVE.sell(before, tokens)
        if not result:
            return {"status": "unquotable_sell_at_boundary", "classification": "unresolved"}
        net_sol, curve_sol = result
        protocol_fee = CURVE.fee(curve_sol, before["fee_bps"])
        creator_fee = CURVE.fee(curve_sol, before["creator_fee_bps"])
        gross_cost = 0
        after = CURVE.moved(before, curve_sol, tokens, False)
        output = net_sol
        output_name = "net_sol_raw"
        actual_from_instruction = False
    minimum = _min_output(row)
    return {
        "status": "quote_only",
        "classification": "hypothetical_quote_only",
        "actual_fill_established": False,
        "exact_hypothetical_fill_claim": False,
        "placement": placement,
        "placement_seed": seed,
        "placement_seed_independent_of_outcome": outcome_independent,
        "boundary": boundary,
        "state_source": source,
        "side": side,
        "state_before": before,
        "curve_sol_raw": curve_sol,
        "tokens_raw": tokens,
        "gross_cost_raw": gross_cost if side == "buy" else None,
        "protocol_fee_raw": protocol_fee,
        "creator_fee_raw": creator_fee,
        "network_fee_raw": _int_or_none(row.get("network_fee_raw")),
        output_name: output,
        "minimum_output_raw": minimum,
        "minimum_guard_pass": None if minimum is None else output >= minimum,
        "state_after_own_impact": after,
        "own_impact_applied": True,
        "participant_reactions_after_quote_simulated": False,
        "quote_engine": "research/wallet_curve_entry_discovery_20261007/curve_adapter.py over approved research/day_general_20261004/helpers/replay.py",
        "_unused_actual_from_instruction": actual_from_instruction,
    }


def _transaction_slot(tx: dict[str, Any]) -> int | None:
    return _int_or_none(tx.get("slot"))


def _group_for_signature(groups: list[dict[str, Any]], signature: str) -> dict[str, Any] | None:
    return next((group for group in groups if group.get("signature") == signature), None)


def _event_state_for_signature(reader: ChainReader, tx: dict[str, Any], signature: str,
                               mint: str, observations: dict[str, list[dict[str, Any]]]) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str]:
    events, provenance = reader.receipt_events_for_mint(tx, signature, mint, observations)
    relevant = [event for event in events if _event_mint(event) == mint and _event_is_sol_curve(event)]
    states = [state for event in relevant if (state := state_from_event(event)) is not None]
    return (states[-1] if states else None), relevant, provenance


def _canonical_position(reader: ChainReader, signature: str, expected_slot: int | None = None) -> tuple[dict[str, Any] | None, dict[str, Any] | None, int | None, list[str]]:
    notes: list[str] = []
    tx = reader.transaction(signature)
    if not isinstance(tx, dict):
        return None, None, None, ["getTransaction_unavailable"]
    slot = _transaction_slot(tx)
    if expected_slot is not None and slot != expected_slot:
        notes.append("logged_slot_differs_from_getTransaction")
    if slot is None:
        return tx, None, None, notes + ["transaction_slot_missing"]
    block = reader.block(slot)
    if not isinstance(block, dict):
        return tx, None, None, notes + ["canonical_full_block_unavailable"]
    index = canonical_block_index(block, signature)
    if index is None:
        notes.append("signature_absent_from_canonical_getBlock")
    return tx, block, index, notes


def _logged_index_note(logged: int | None, canonical: int | None) -> str | None:
    if logged is not None and canonical is not None and logged != canonical:
        return "logged_transaction_index_differs_from_canonical_getBlock"
    return None


def _scenario_boundary_state(reader: ChainReader, row: dict[str, Any], side: str, mint: str,
                             source_signature: str, source_slot: int, source_index: int,
                             source_tx: dict[str, Any], source_block: dict[str, Any],
                             observations: dict[str, list[dict[str, Any]]], label: str,
                             identity: str) -> dict[str, Any]:
    source_state, source_events, source_provenance = _event_state_for_signature(
        reader, source_tx, source_signature, mint, observations)
    source_state_source = ("source_transaction_trade_event_post_state"
                           if source_provenance == "canonical_getTransaction_logs"
                           else "captured_observation_events_unverified")
    if source_state is None:
        source_state_source = None
        return {"status": "missing_authenticated_or_recorded_quote_state", "placement": label,
                "classification": "unresolved", "actual_fill_established": False}
    txs = _block_transactions(source_block)
    if not 0 <= source_index < len(txs) or _signature_from_tx(txs[source_index]) != source_signature:
        return {"status": "source_index_not_canonical", "placement": label,
                "classification": "unresolved", "actual_fill_established": False}
    seed = placement_seed(identity)
    mix_u = _uniform(identity, "central-slot-mixture")
    same_k = _central_same_slot_k(identity)

    if label == "fast":
        slot_kind, desired_groups = "same_slot", 1
    elif label == "slow":
        slot_kind, desired_groups = "next_slot", 2
    else:
        p = 0.80 if label == "central80" else 0.85
        if mix_u < p:
            slot_kind, desired_groups = "same_slot", same_k
        else:
            slot_kind, desired_groups = "next_slot", 1

    group_path = []
    event_provenance = {source_provenance}
    slot = source_slot
    start_state = source_state
    boundary = {"slot": source_slot, "after_signature": source_signature,
                "after_transaction_index": source_index, "curve_groups_between": 0,
                "hypothetical_block_index_claimed": False}
    if slot_kind == "same_slot":
        after_source, error = reader.trade_groups(source_block, mint, observations,
                                                  start_index=source_index + 1,
                                                  stop_after=desired_groups)
        if error:
            return {"status": error, "placement": label, "classification": "unresolved",
                    "actual_fill_established": False, "placement_seed": seed,
                    "source_state_source": source_state_source}
        take = min(desired_groups, len(after_source))
        group_path = after_source[:take]
        event_provenance.update(group.get("event_source", "canonical_getBlock_transaction_logs")
                                 for group in group_path)
        if take:
            boundary.update(after_signature=group_path[-1]["signature"],
                            after_transaction_index=group_path[-1]["transaction_index"])
    else:
        source_slot_groups, error = reader.trade_groups(source_block, mint, observations,
                                                        start_index=source_index + 1)
        if error:
            return {"status": error, "placement": label, "classification": "unresolved",
                    "actual_fill_established": False, "placement_seed": seed,
                    "source_state_source": source_state_source}
        state_at_source_slot_end = dict(source_state)
        for group in source_slot_groups:
            event_provenance.add(group.get("event_source", "canonical_getBlock_transaction_logs"))
            next_state, transition_error = _advance_trade_group(state_at_source_slot_end, group)
            if transition_error:
                return {"status": transition_error, "placement": label,
                        "classification": "unresolved", "actual_fill_established": False,
                        "placement_seed": seed, "boundary": {"slot": source_slot,
                        "after_signature": group.get("signature"),
                        "after_transaction_index": group.get("transaction_index")},
                        "failed_transition_signature": group.get("signature"),
                        "source_state_source": source_state_source}
            state_at_source_slot_end = next_state
        next_slot, next_block, error = reader.next_produced_block(source_slot)
        if error:
            return {"status": error, "placement": label, "classification": "unresolved",
                    "actual_fill_established": False, "placement_seed": seed,
                    "source_state_source": source_state_source}
        slot = next_slot
        next_groups, error = reader.trade_groups(next_block, mint, observations,
                                                  start_index=0, stop_after=desired_groups)
        if error:
            return {"status": error, "placement": label, "classification": "unresolved",
                    "actual_fill_established": False, "placement_seed": seed,
                    "source_state_source": source_state_source}
        if len(next_groups) < desired_groups:
            return {"status": f"insufficient_curve_groups_for_{label}", "placement": label,
                    "classification": "unresolved", "actual_fill_established": False,
                    "placement_seed": seed, "source_state_source": source_state_source,
                    "observed_curve_groups": len(next_groups)}
        start_state = state_at_source_slot_end
        group_path = next_groups[:desired_groups]
        event_provenance.update(group.get("event_source", "canonical_getBlock_transaction_logs")
                                 for group in group_path)
        boundary = {"slot": slot, "after_signature": group_path[-1]["signature"],
                    "after_transaction_index": group_path[-1]["transaction_index"],
                    "curve_groups_between": len(source_slot_groups) + desired_groups,
                    "source_slot_curve_groups_between": len(source_slot_groups),
                    "next_slot_curve_groups_between": desired_groups,
                    "hypothetical_block_index_claimed": False,
                    "produced_slot_parent": _int_or_none(next_block.get("parentSlot"))}
    current = dict(start_state)
    for group in group_path:
        next_state, transition_error = _advance_trade_group(current, group)
        if transition_error:
            return {"status": transition_error, "placement": label,
                    "classification": "unresolved", "actual_fill_established": False,
                    "placement_seed": seed, "boundary": boundary,
                    "failed_transition_signature": group.get("signature"),
                    "source_state_source": source_state_source}
        current = next_state
    if slot_kind == "same_slot":
        boundary["curve_groups_between"] = len(group_path)
    quote = quote_at_state(row, side, current, source=source_state_source, boundary=boundary,
                           placement=label, seed=seed)
    quote["event_evidence_provenance"] = sorted(event_provenance)
    if "captured_observation_events_unverified" in event_provenance:
        quote["status"] = ("provisional_observation_quote" if quote.get("classification") == "hypothetical_quote_only"
                           else quote.get("status"))
        quote["evidence_provisional"] = True
    else:
        quote["evidence_provisional"] = False
    return quote


def _token_balance_delta(receipt: dict[str, Any], mint: str, owner: str | None) -> int | None:
    if not owner:
        return None
    meta = receipt.get("meta") or {}
    totals = {"preTokenBalances": 0, "postTokenBalances": 0}
    found = False
    for side in totals:
        for item in meta.get(side, []) or []:
            if item.get("mint") == mint and item.get("owner") == owner:
                value = _int_or_none((item.get("uiTokenAmount") or {}).get("amount"))
                if value is not None:
                    totals[side] += value
                    found = True
    return totals["postTokenBalances"] - totals["preTokenBalances"] if found else None


def _receipt_actual_fill(row: dict[str, Any], side: str, mint: str, receipt: dict[str, Any],
                         events: list[dict[str, Any]], min_output: int | None) -> dict[str, Any]:
    meta = receipt.get("meta") or {}
    if meta.get("err") is not None:
        return {"status": "landed_failed_transaction", "classification": "actual_failed_attempt",
                "actual_fill_established": False, "transaction_error": meta.get("err"),
                "network_fee_raw": _int_or_none(meta.get("fee"))}
    candidates = [event for event in events if _event_mint(event) == mint and
                  _event_is_sol_curve(event) and _event_side(event) == side]
    wallet = _first_str(row, "wallet", "trader", "owner", "fee_payer")
    if wallet:
        wallet_matches = [event for event in candidates if _first_str(event, "user", "trader") == wallet]
        candidates = wallet_matches
    else:
        users = {_first_str(event, "user", "trader") for event in candidates}
        if len(users) > 1:
            return {"status": "ambiguous_receipt_users_without_wallet", "classification": "unresolved",
                    "actual_fill_established": False, "network_fee_raw": _int_or_none(meta.get("fee")),
                    "candidate_user_count": len(users)}
    if not candidates:
        return {"status": "successful_receipt_without_decoded_curve_trade", "classification": "unresolved",
                "actual_fill_established": False, "network_fee_raw": _int_or_none(meta.get("fee"))}
    amounts = [_event_amount(event, side) for event in candidates]
    if any(token is None or sol is None for token, sol in amounts):
        return {"status": "receipt_trade_amount_missing", "classification": "unresolved",
                "actual_fill_established": False, "network_fee_raw": _int_or_none(meta.get("fee"))}
    tokens = sum(token for token, _ in amounts if token is not None)
    curve_sol = sum(sol for _, sol in amounts if sol is not None)
    state = state_from_event(candidates[-1])
    def fee_total(*names: str) -> int | None:
        values = [_int_or_none(next((event[name] for name in names if event.get(name) is not None), None))
                  for event in candidates]
        return sum(values) if all(value is not None for value in values) else None
    protocol_fee = fee_total("fee_raw", "fee", "protocol_fee_raw")
    creator_fee = fee_total("creator_fee_raw", "creator_fee")
    # Min output is an instruction guard, while the decoded event is the amount
    # that actually moved on chain. Keep both values distinct in the audit.
    actual_output = (tokens if side == "buy" else
                     max(0, curve_sol - protocol_fee - creator_fee)
                     if protocol_fee is not None and creator_fee is not None else None)
    owner_delta = _token_balance_delta(receipt, mint, wallet)
    parity = None if owner_delta is None else (owner_delta == tokens if side == "buy" else owner_delta == -tokens)
    return {
        "status": "actual_receipt_reconciled",
        "classification": "actual_receipt_reconciled",
        "actual_fill_established": True,
        "side": side,
        "actual_tokens_raw": tokens,
        "actual_curve_sol_raw": curve_sol,
        "actual_net_sol_raw": (curve_sol + protocol_fee + creator_fee
                               if side == "buy" and protocol_fee is not None and creator_fee is not None
                               else actual_output if side == "sell" else None),
        "protocol_fee_raw": protocol_fee,
        "creator_fee_raw": creator_fee,
        "network_fee_raw": _int_or_none(meta.get("fee")),
        "min_output_raw": min_output,
        "actual_output_raw": actual_output,
        "minimum_guard_pass_from_actual_receipt": (None if min_output is None or actual_output is None
                                                    else actual_output >= min_output),
        "receipt_owner_token_delta_raw": owner_delta,
        "receipt_owner_token_delta_matches_event": parity,
        "post_trade_state": state,
        "event_count": len(candidates),
        "trade_event_signatures_and_users": [{"user": _first_str(event, "user", "trader"),
                                               "event_side": _event_side(event)} for event in candidates],
    }


def _actual_prestate_audit(reader: ChainReader, row: dict[str, Any], mint: str, side: str,
                           source_sig: str, source_slot: int, source_index: int,
                           source_tx: dict[str, Any], source_block: dict[str, Any],
                           actual_sig: str, actual_tx: dict[str, Any], actual_block: dict[str, Any],
                           actual_index: int, observations: dict[str, list[dict[str, Any]]],
                           max_slot_gap: int) -> dict[str, Any]:
    actual_slot = _transaction_slot(actual_tx)
    if actual_slot is None:
        return {"status": "actual_slot_missing", "classification": "unresolved"}
    if actual_slot < source_slot or (actual_slot == source_slot and actual_index <= source_index):
        return {"status": "landing_precedes_source", "classification": "unresolved"}
    slot_gap = actual_slot - source_slot
    if slot_gap > max_slot_gap:
        return {"status": "actual_slot_gap_exceeds_replay_limit", "classification": "unresolved",
                "slot_gap": slot_gap}
    state, source_events, source_provenance = _event_state_for_signature(
        reader, source_tx, source_sig, mint, observations)
    state_source = ("source_transaction_trade_event_post_state"
                    if source_provenance == "canonical_getTransaction_logs"
                    else "captured_observation_events_unverified")
    if state is None:
        return {"status": "missing_source_state", "classification": "unresolved", "slot_gap": slot_gap,
                "source_state_source": None}
    event_provenance = {source_provenance}
    # The source transaction is the immutable anchor; its last trade event is
    # already the post-state for the complete atomic source transaction.
    slots: list[tuple[int, dict[str, Any], int | None, int | None]] = []
    if actual_slot == source_slot:
        slots.append((source_slot, source_block, source_index, actual_index))
    else:
        slots.append((source_slot, source_block, source_index, None))
        prior_produced_slot = source_slot
        for slot in range(source_slot + 1, actual_slot + 1):
            block = reader.block(slot)
            if block is None:
                continue
            parent = _int_or_none(block.get("parentSlot"))
            if parent != prior_produced_slot:
                return {"status": "intervening_block_parent_gap_or_fork", "classification": "unresolved",
                        "slot_gap": slot_gap, "slot_checked": slot, "parent_slot": parent,
                        "prior_produced_slot": prior_produced_slot}
            prior_produced_slot = slot
            slots.append((slot, block, None, actual_index if slot == actual_slot else None))
        if not slots or slots[-1][0] != actual_slot:
            return {"status": "actual_block_unavailable", "classification": "unresolved", "slot_gap": slot_gap}
    for slot, block, first_index, final_index in slots:
        txs = _block_transactions(block)
        if not txs:
            return {"status": "full_intervening_block_unavailable", "classification": "unresolved",
                    "slot_gap": slot_gap, "slot_checked": slot}
        begin = (first_index + 1) if first_index is not None else 0
        end = final_index if final_index is not None else len(txs)
        if end < begin or end > len(txs):
            return {"status": "invalid_canonical_boundary", "classification": "unresolved",
                    "slot_gap": slot_gap}
        for index in range(begin, end):
            tx = txs[index]
            if not isinstance(tx, dict) or not isinstance(tx.get("meta"), dict):
                return {"status": "transaction_metadata_missing_in_full_block", "classification": "unresolved",
                        "slot_gap": slot_gap, "slot_checked": slot, "transaction_index": index}
            if tx["meta"].get("err") is not None:
                continue
            sig = _signature_from_tx(tx)
            events = reader._decoded_events(tx)
            trades = [event for event in events if _event_mint(event) == mint and _event_is_sol_curve(event)]
            if not trades and sig:
                trades = [event for event in observations.get(sig, [])
                          if _event_mint(event) == mint and _event_is_sol_curve(event)]
                if trades:
                    event_provenance.add("captured_observation_events_unverified")
            elif trades:
                event_provenance.add("canonical_getBlock_transaction_logs")
            if trades:
                group = {"events": trades, "signature": sig, "transaction_index": index}
                next_state, error = _advance_trade_group(state, group)
                if error:
                    return {"status": error, "classification": "unresolved", "slot_gap": slot_gap,
                            "slot_checked": slot, "failed_transition_signature": sig}
                state = next_state
    # The event's reverse-quoted prestate independently checks whether every
    # intervening successful curve transaction was covered.
    actual_events = reader.receipt_trade_events(actual_tx, actual_sig, observations)
    matching = [event for event in actual_events if _event_mint(event) == mint and _event_is_sol_curve(event)
                and _event_side(event) == side]
    if not matching:
        return {"status": "actual_trade_event_unavailable_for_prestate_check", "classification": "unresolved",
                "slot_gap": slot_gap, "source_state_source": state_source}
    first_pre = _pre_state_from_event(matching[0])
    if first_pre is not None and not _reserves_equal(state, first_pre):
        return {"status": "actual_fill_prestate_does_not_match_reconstructed_tape",
                "classification": "unresolved", "slot_gap": slot_gap,
                "source_state_source": state_source, "reconstructed_prestate": state,
                "receipt_implied_prestate": first_pre}
    amount_row = dict(row)
    if side == "sell" and _action_amount(amount_row, side) is None:
        amount_row["quantity_tokens_raw"] = sum((_event_amount(event, side)[0] or 0) for event in matching)
    quote = quote_at_state(amount_row, side, state, source=state_source,
                           boundary={"slot": actual_slot, "after_signature": None,
                                     "before_signature": actual_sig, "before_transaction_index": actual_index,
                                     "curve_groups_between": "decoded_full_transactions",
                                     "hypothetical_block_index_claimed": False},
                           placement="actual_recorded_boundary_quote", seed=placement_seed(
                               _first_str(row, "intent_id") or actual_sig))
    if quote.get("classification") == "hypothetical_quote_only":
        if "captured_observation_events_unverified" in event_provenance:
            quote["status"] = "provisional_observation_boundary_quote"
            quote["classification"] = "provisional_observation_comparison"
            quote["evidence_provisional"] = True
        else:
            quote["status"] = "actual_boundary_quote_checked"
            quote["classification"] = "observed_boundary_quote_comparison"
            quote["evidence_provisional"] = False
    quote["actual_fill_established"] = False
    quote["boundary_source"] = "canonical_getBlock_order_and_successful_curve_trade_events"
    quote["source_state_source"] = state_source
    quote["event_evidence_provenance"] = sorted(event_provenance)
    quote["actual_signature"] = actual_sig
    quote["actual_slot"] = actual_slot
    quote["actual_transaction_index"] = actual_index
    return quote


def reconcile_one(item: dict[str, Any], reader: ChainReader,
                  observations: dict[str, list[dict[str, Any]]], max_actual_slot_gap: int) -> dict[str, Any]:
    row = item["row"]
    action = item["action"]
    side = item["side"]
    mint = item["mint"]
    event = item["action_event"]
    audit: dict[str, Any] = {
        "audit_event": "RPC_FILL_RECONCILIATION",
        "created_at_utc": _utc_now(),
        "intent_id": item["intent_id"],
        "position_id": item["position_id"],
        "mint": mint,
        "side": side,
        "source_event": event,
        "source_input_line": action.get("_input_line"),
        "input_source_rows": [record.get("_input_line") for record in item.get("records", [])],
    }
    source_sig = _source_signature(row)
    source_slot = _source_slot(row)
    if not mint or not side:
        audit.update(status="missing_mint_or_side", classification="unresolved")
        return audit
    if not source_sig or source_slot is None:
        audit.update(status="missing_source_signature_or_slot", classification="unresolved",
                     actual_fill_established=False,
                     limitation="Legacy ghost rows without source signature and slot are not guessed from reserve values or timestamps.")
        return audit
    try:
        source_tx, source_block, source_index, source_notes = _canonical_position(
            reader, source_sig, source_slot)
    except ReconcileError as exc:
        audit.update(status="source_rpc_error", classification="unresolved", rpc_error=str(exc))
        return audit
    audit["source_signature"] = source_sig
    audit["source_slot_logged"] = source_slot
    audit["source_transaction_index_logged"] = _source_logged_index(row)
    audit["source_rpc_notes"] = source_notes
    if source_tx is None:
        audit.update(status="source_transaction_not_found", classification="unresolved")
        return audit
    canonical_slot = _transaction_slot(source_tx)
    audit["source_slot_canonical"] = canonical_slot
    audit["source_transaction_index_canonical"] = source_index
    idx_note = _logged_index_note(_source_logged_index(row), source_index)
    if idx_note:
        audit["source_rpc_notes"].append(idx_note)
    if source_block is None or source_index is None:
        audit.update(status="source_canonical_order_unavailable", classification="unresolved")
        return audit
    source_tx_block = _block_transactions(source_block)
    if source_index >= len(source_tx_block):
        audit.update(status="source_index_out_of_block", classification="unresolved")
        return audit
    if _signature_from_tx(source_tx_block[source_index]) != source_sig:
        audit.update(status="source_index_signature_mismatch", classification="unresolved")
        return audit
    # A logged slot/index is only a claim. Use the slot proven by the receipt
    # and the exact index found in its canonical block for every later step.
    source_slot = canonical_slot
    actual_sig = _actual_signature(row, event)
    min_output = _min_output(row)
    if actual_sig:
        audit["actual_signature"] = actual_sig
        try:
            actual_tx, actual_block, actual_index, actual_notes = _canonical_position(reader, actual_sig)
        except ReconcileError as exc:
            audit.update(status="actual_rpc_error", classification="unresolved", rpc_error=str(exc))
            return audit
        audit["actual_rpc_notes"] = actual_notes
        if actual_tx is None:
            audit.update(status="actual_transaction_not_found", classification="unresolved",
                         actual_fill_established=False)
            return audit
        if actual_block is None or actual_index is None:
            audit.update(status="actual_canonical_order_unavailable", classification="unresolved",
                         actual_fill_established=False)
            return audit
        logged_slot = _int_or_none(row.get("filled_slot", row.get("landing_slot")))
        if logged_slot is not None and logged_slot != _transaction_slot(actual_tx):
            audit["actual_rpc_notes"].append("logged_landing_slot_differs_from_getTransaction")
        logged_index = _int_or_none(row.get("transaction_index", row.get("landing_transaction_index")))
        if logged_index is not None and logged_index != actual_index:
            audit["actual_rpc_notes"].append("logged_landing_index_differs_from_canonical_getBlock")
        actual_events = reader.receipt_trade_events(actual_tx, actual_sig, observations)
        audit["actual_receipt"] = _receipt_actual_fill(row, side, mint, actual_tx, actual_events, min_output)
        audit["actual_slot_canonical"] = _transaction_slot(actual_tx)
        audit["actual_transaction_index_canonical"] = actual_index
        if audit["actual_receipt"].get("actual_fill_established"):
            try:
                audit["actual_boundary_quote"] = _actual_prestate_audit(
                    reader, row, mint, side, source_sig, source_slot, source_index,
                    source_tx, source_block, actual_sig, actual_tx, actual_block,
                    actual_index, observations, max_actual_slot_gap)
            except ReconcileError as exc:
                audit["actual_boundary_quote"] = {"status": "boundary_rpc_error", "classification": "unresolved",
                                                  "rpc_error": str(exc)}
            audit["status"] = "actual_receipt_reconciled"
            audit["classification"] = "actual_receipt_reconciled"
            audit["actual_fill_established"] = True
        else:
            audit["status"] = audit["actual_receipt"].get("status", "actual_receipt_unresolved")
            audit["classification"] = audit["actual_receipt"].get("classification", "unresolved")
            audit["actual_fill_established"] = False
        return audit

    try:
        audit["placement_seed"] = placement_seed(item["intent_id"] or item["key"])
        audit["estimated_quotes"] = {
            label: _scenario_boundary_state(reader, row, side, mint, source_sig, source_slot,
                                             source_index, source_tx, source_block, observations,
                                             label, item["intent_id"] or item["key"])
            for label in ("fast", "central80", "central85", "slow")
        }
    except ReconcileError as exc:
        audit.update(status="scenario_rpc_error", classification="unresolved", rpc_error=str(exc))
        return audit
    completed = sum(1 for value in audit["estimated_quotes"].values()
                    if value.get("classification") == "hypothetical_quote_only")
    audit["status"] = "estimated_placement_quotes_available" if completed else "estimated_placement_unresolved"
    audit["classification"] = "hypothetical_quote_only" if completed else "unresolved"
    audit["actual_fill_established"] = False
    audit["estimated_scenario_count"] = completed
    audit["placement_model"] = {
        "central_same_slot_probability": [0.80, 0.85],
        "same_slot_curve_group_distribution": {"0": "29/132", "1": "20/132", "2_or_more_capped_at_2": "83/132"},
        "same_slot_distribution_note": "Historical matched-copy audit from an older configuration; model assumption, not measured runtime landing calibration.",
        "next_produced_slot_central_groups": 1,
        "next_produced_slot_slow_groups": 2,
        "seed_identity": item["intent_id"] or item["key"],
        "outcome_independent_seed": True,
        "next_slot_branch_weights_are_user_reported_assumptions": True,
    }
    return audit


def run(args: argparse.Namespace) -> dict[str, Any]:
    input_path = pathlib.Path(args.intents).expanduser().resolve()
    observation_path = pathlib.Path(args.observations).expanduser().resolve() if args.observations else None
    output_dir = pathlib.Path(args.output_dir).expanduser().resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ReconcileError(f"output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = _read_jsonl(input_path)
    observation_rows = _read_jsonl(observation_path) if observation_path else []
    observations = _input_events_by_signature(observation_rows)
    action_items = _group_action_rows(rows)
    rpc = RpcClient(_rpc_url(args.rpc_url), output_dir / "rpc_cache", timeout=args.timeout)
    reader = ChainReader(rpc, args.commitment, args.max_transaction_version,
                         args.next_slot_search_limit, args.max_actual_slot_gap)
    audits = [reconcile_one(item, reader, observations, args.max_actual_slot_gap) for item in action_items]
    status_counts = collections.Counter(row.get("status", "unknown") for row in audits)
    unresolved = [row for row in audits if row.get("classification") == "unresolved"]
    unresolved_coverage = len(unresolved)
    for row in audits:
        boundary = row.get("actual_boundary_quote")
        if isinstance(boundary, dict) and boundary.get("classification") == "unresolved":
            unresolved_coverage += 1
        unresolved_coverage += sum(1 for quote in row.get("estimated_quotes", {}).values()
                                   if quote.get("classification") == "unresolved")
    graduated = [row for row in audits if "graduated" in str(row.get("status", "")) or
                 any("graduated" in str(q.get("status", "")) for q in row.get("estimated_quotes", {}).values())]
    report = {
        "schema_version": 1,
        "generated_at_utc": _utc_now(),
        "scope": "read-only post-exit Rust ghost intent/fill RPC audit; no order submission and no profitability replay",
        "input": {"intents_path": str(input_path), "intents_rows": len(rows),
                  "observations_path": str(observation_path) if observation_path else None,
                  "observation_rows": len(observation_rows)},
        "rpc": {"commitment": args.commitment, "max_supported_transaction_version": args.max_transaction_version,
                "raw_response_cache": "rpc_cache/", "endpoint_recorded": False},
        "counts": {"action_records": len(audits), "status": dict(status_counts),
                   "unresolved_records": len(unresolved), "graduated_unresolved_records": len(graduated),
                   "unresolved_coverage_items": unresolved_coverage,
                   "actual_receipts_reconciled": sum(row.get("classification") == "actual_receipt_reconciled" for row in audits),
                   "quote_only_records": sum(row.get("classification") == "hypothetical_quote_only" for row in audits)},
        "accounting": {"settled_pnl_sol": None, "open_marked_pnl_sol": None,
                       "combined_marked_estimate_sol": None,
                       "unresolved_inventory_count": None,
                       "note": "This tool audits individual receipts/quotes and produces no account PnL or inventory ledger. Graduated inventory remains unresolved because this CLI only decodes Pump curve trades; it does not fabricate an AMM sale."},
        "placement_model": {
            "central_scenarios": ["central80", "central85"],
            "brackets": ["fast", "slow"],
            "seed_rule": "sha256('ghost-placement-v1|' + stable intent identity + scenario label); no outcome or RPC result enters the seed",
            "hypothetical_boundary": "curve-state boundary after the selected full transaction group; no within-transaction insertion or exact hypothetical block index asserted",
        },
        "quote_method": "Approved day_general integer quote helpers plus repaired Pump curve adapter; finite intent amount, protocol/creator fees and own reserve impact. Counterparty reactions after the hypothetical quote are not replayed.",
        "migration": {"graduation_sell_created": False,
                      "post_migration_decoder": "not implemented in this bounded curve-fill audit; migrated positions remain unresolved and require separate authenticated PumpSwap/Raydium continuation coverage"},
        "audits": audits,
        "limitations": [
            "A hypothetical quote is not a filled transaction or a profitability estimate.",
            "Actual source and landing indexes come from canonical getBlock transaction arrays; logged indexes are retained only for comparison.",
            "Missing signature, block, event, reserve continuity or migrated-pool execution is reported as unresolved coverage.",
            "Existing OPEN/CLOSE rows without source signature and slot are not assigned guessed transaction positions.",
        ],
    }
    audit_path = output_dir / "audit_append.jsonl"
    # This is a new audit artifact in an isolated run directory. Open in append
    # mode so reruns into the same empty-or-existing artifact never truncate it.
    with audit_path.open("a", encoding="utf-8") as out:
        for audit in audits:
            out.write(json.dumps(audit, sort_keys=True, separators=(",", ":")) + "\n")
    (output_dir / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "README.txt").write_text(
        "Read-only ghost fill reconciliation output. audit_append.jsonl contains additive audit rows; "
        "rpc_cache/ retains raw JSON-RPC response envelopes. No input rows were modified.\n",
        encoding="utf-8")
    return report


def _default_output_dir() -> pathlib.Path:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return ROOT / "reports" / "ghost_fill_reconciliation" / f"run_{stamp}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intents", default=str(ROOT / "data" / "ghost_trades.jsonl"),
                        help="Rust INTENT/FILL/FAIL/CLOSE JSONL (legacy OPEN/CLOSE rows are retained as unresolved).")
    parser.add_argument("--observations", default=str(ROOT / "data" / "ghost_observations.jsonl"),
                        help="Captured transaction observations JSONL; missing file is allowed.")
    parser.add_argument("--output-dir", default=None, help="New isolated report directory (default: timestamped reports path).")
    parser.add_argument("--rpc-url", default=None,
                        help="Read-only Solana RPC URL; overrides SOLANA_RPC_URL, SHYFT_RPC_URL, ALCHEMY_RPC_URL.")
    parser.add_argument("--commitment", choices=("confirmed", "finalized"), default="finalized")
    parser.add_argument("--max-transaction-version", type=int, default=1)
    parser.add_argument("--next-slot-search-limit", type=int, default=8)
    parser.add_argument("--max-actual-slot-gap", type=int, default=64)
    parser.add_argument("--timeout", type=float, default=25.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.output_dir is None:
        args.output_dir = str(_default_output_dir())
    if args.max_transaction_version < 0 or args.next_slot_search_limit < 1 or args.max_actual_slot_gap < 0:
        parser.error("transaction version and slot limits must be nonnegative (search limit >= 1)")
    try:
        report = run(args)
    except (ReconcileError, OSError, json.JSONDecodeError) as exc:
        parser.exit(2, f"reconciliation failed: {exc}\n")
    counts = report["counts"]
    print(json.dumps({"output_dir": str(pathlib.Path(args.output_dir).resolve()),
                      "action_records": counts["action_records"],
                      "actual_receipts_reconciled": counts["actual_receipts_reconciled"],
                      "quote_only_records": counts["quote_only_records"],
                      "unresolved_records": counts["unresolved_records"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
