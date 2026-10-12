#!/usr/bin/env python3
"""Receipt-authenticated descriptive entry patterns for the frozen 22-wallet sample.

This is an observational study only. It does not replay hypothetical fills or
estimate profitability. Curve history is fetched before each selected buy using
the shared, cached RPC client, and all same-slot chronology uses transactionIndex.
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import gzip
import hashlib
import json
import math
import pathlib
import statistics
import sys
from collections import Counter, defaultdict
from typing import Any


HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "research/day_general_20261004/helpers"))
import decoder  # noqa: E402 — approved strict Pump receipt decoder
from rpc import rpc_with_meta  # noqa: E402 — shared cached and rate-limited client


LAMPORTS = 1_000_000_000
TARGETS_PATH = HERE / "wallets.json"
RAW_WALLETS = HERE / "raw_wallets"
PREFIX_DIR = HERE / "prefixes"
OUTPUT_JSON = HERE / "entry_patterns.json"
OUTPUT_MD = HERE / "entry_patterns.md"
IDL_PATH = ROOT / "research/day_general_20261004/helpers/OFFICIAL_PUMP_IDL.json"
KOL_PATH = ROOT / "kol_wallets.txt"
TRACKED_PATH = ROOT / "tracked_wallets.txt"


def read_gzip_json(path: pathlib.Path) -> Any:
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def write_gzip_json(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as zipped:
            zipped.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())


def tx_body(tx: dict[str, Any]) -> dict[str, Any]:
    return tx.get("result", tx)


def signature(tx: dict[str, Any]) -> str | None:
    body = tx_body(tx)
    sigs = ((body.get("transaction") or {}).get("signatures") or [])
    return sigs[0] if sigs else body.get("signature") or tx.get("signature")


def tx_index(tx: dict[str, Any]) -> int | None:
    body = tx_body(tx)
    value = body.get("transactionIndex", body.get("index"))
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def order_key(row: dict[str, Any]) -> tuple[int, int, str, int]:
    idx = row.get("transaction_index")
    return (int(row.get("slot") or -1), idx if idx is not None else -1,
            str(row.get("signature") or ""), int(row.get("event_index") or 0))


def strictly_before(row: dict[str, Any], anchor: dict[str, Any]) -> bool:
    if row.get("signature") and row.get("signature") == anchor.get("signature"):
        return False  # atomic transaction; never insert inside it
    rs, ass = row.get("slot"), anchor.get("slot")
    if not isinstance(rs, int) or not isinstance(ass, int):
        return False
    if rs < ass:
        return True
    if rs > ass:
        return False
    ri, ai = row.get("transaction_index"), anchor.get("transaction_index")
    # A same-slot comparison without both indexes has no authenticated order.
    return isinstance(ri, int) and isinstance(ai, int) and ri < ai


def address_set(path: pathlib.Path) -> set[str]:
    found: set[str] = set()
    if not path.exists():
        return found
    for raw in path.read_text(encoding="utf-8").splitlines():
        value = raw.split("#", 1)[0].strip()
        if value and 32 <= len(value) <= 44 and all(c in "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz" for c in value):
            found.add(value)
    return found


def active_tracked_set() -> set[str]:
    """Read only the explicitly named Active Tracked Wallets section (16 rows)."""
    if not TRACKED_PATH.exists():
        return set()
    text = TRACKED_PATH.read_text(encoding="utf-8")
    active = text.split("# Active Tracked Wallets", 1)[-1]
    if "# Reverse-Engineered Top Bot Wallets" in active:
        active = active.split("# Reverse-Engineered Top Bot Wallets", 1)[0]
    found: set[str] = set()
    for raw in active.splitlines():
        value = raw.split("#", 1)[0].strip()
        if value and 32 <= len(value) <= 44 and all(c in "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz" for c in value):
            found.add(value)
    return found


def roster_snapshot() -> dict[str, Any]:
    kol, tracked = address_set(KOL_PATH), active_tracked_set()
    return {
        "kol_file": str(KOL_PATH.relative_to(ROOT)),
        "kol_count": len(kol),
        "tracked_file": str(TRACKED_PATH.relative_to(ROOT)),
        "tracked_count": len(tracked),
        "kol_tracked_overlap": len(kol & tracked),
        "kol_addresses": sorted(kol),
        "tracked_addresses": sorted(tracked),
        "qualification": "Current roster snapshot only; not proof that an address was known at the historical decision time.",
    }


def decode_b58(text: str) -> bytes:
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    n = 0
    for char in text:
        n = n * 58 + alphabet.index(char)
    body = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(text) - len(text.lstrip("1"))) + body


def load_instruction_layout() -> tuple[str, dict[bytes, tuple[str, list[str]]]]:
    idl = json.loads(IDL_PATH.read_text(encoding="utf-8"))
    result: dict[bytes, tuple[str, list[str]]] = {}
    for ix in idl.get("instructions", []):
        disc = ix.get("discriminator")
        if isinstance(disc, list) and len(disc) == 8:
            result[bytes(disc)] = (ix["name"], [a["name"] for a in ix.get("accounts", [])])
    return idl["address"], result


PUMP_PROGRAM, IX_LAYOUT = load_instruction_layout()


def account_keys(body: dict[str, Any]) -> list[str]:
    message = ((body.get("transaction") or {}).get("message") or {})
    keys = []
    for key in message.get("accountKeys", []) or []:
        keys.append(key.get("pubkey") if isinstance(key, dict) else key)
    meta = body.get("meta") or {}
    loaded = meta.get("loadedAddresses") or {}
    keys.extend(loaded.get("writable", []) or [])
    keys.extend(loaded.get("readonly", []) or [])
    return [key if isinstance(key, str) else "" for key in keys]


def signer_keys(body: dict[str, Any]) -> list[str]:
    message = ((body.get("transaction") or {}).get("message") or {})
    raw_keys = message.get("accountKeys", []) or []
    required = (message.get("header") or {}).get("numRequiredSignatures")
    output = []
    for index, key in enumerate(raw_keys):
        address = key.get("pubkey") if isinstance(key, dict) else key
        is_signer = key.get("signer") if isinstance(key, dict) else (isinstance(required, int) and index < required)
        if is_signer is True and isinstance(address, str):
            output.append(address)
    return output


def instruction_rows(body: dict[str, Any]) -> list[dict[str, Any]]:
    message = ((body.get("transaction") or {}).get("message") or {})
    rows = list(message.get("instructions", []) or [])
    for group in ((body.get("meta") or {}).get("innerInstructions", []) or []):
        rows.extend(group.get("instructions", []) or [])
    return rows


def parsed_nonce_authorities(body: dict[str, Any]) -> list[str]:
    found = set()
    for ix in instruction_rows(body):
        parsed = ix.get("parsed") or {}
        info = parsed.get("info") if isinstance(parsed, dict) else None
        if isinstance(info, dict):
            authority = info.get("nonceAuthority") or info.get("nonce_authority")
            if isinstance(authority, str):
                found.add(authority)
    return sorted(found)


def parsed_native_transfers(body: dict[str, Any], related: set[str]) -> list[dict[str, Any]]:
    output = []
    for ix in instruction_rows(body):
        parsed = ix.get("parsed") or {}
        info = parsed.get("info") if isinstance(parsed, dict) else None
        if not isinstance(info, dict) or parsed.get("type") not in ("transfer", "transferWithSeed"):
            continue
        source = info.get("source")
        destination = info.get("destination")
        amount = info.get("lamports")
        if isinstance(source, str) and isinstance(destination, str) and isinstance(amount, int):
            if source in related or destination in related:
                output.append({"source": source, "destination": destination, "lamports": amount,
                               "sol": amount / LAMPORTS, "transfer_type": parsed.get("type")})
    return output


def ix_program(ix: dict[str, Any], keys: list[str]) -> str | None:
    if isinstance(ix.get("programId"), str):
        return ix["programId"]
    idx = ix.get("programIdIndex")
    return keys[idx] if isinstance(idx, int) and 0 <= idx < len(keys) else None


def ix_account_values(ix: dict[str, Any], keys: list[str]) -> list[str]:
    accounts = ix.get("accounts", [])
    output = []
    for item in accounts:
        if isinstance(item, int):
            output.append(keys[item] if 0 <= item < len(keys) else "")
        elif isinstance(item, str):
            output.append(item)
        elif isinstance(item, dict) and isinstance(item.get("pubkey"), str):
            output.append(item["pubkey"])
        else:
            output.append("")
    return output


def official_curve_from_entry(tx: dict[str, Any], mint: str) -> dict[str, Any] | None:
    """Resolve the bonding-curve account by official Pump instruction account order."""
    body = tx_body(tx)
    message = ((body.get("transaction") or {}).get("message") or {})
    keys = account_keys(body)
    instructions = list(message.get("instructions", []) or [])
    for group in ((body.get("meta") or {}).get("innerInstructions", []) or []):
        instructions.extend(group.get("instructions", []) or [])
    found = []
    for ix in instructions:
        if ix_program(ix, keys) != PUMP_PROGRAM:
            continue
        # jsonParsed Pump instructions may expose named fields directly.
        parsed = ix.get("parsed") or {}
        info = parsed.get("info") if isinstance(parsed, dict) else None
        if isinstance(info, dict):
            imint = info.get("mint") or info.get("baseMint") or info.get("base_mint")
            curve = info.get("bondingCurve") or info.get("bonding_curve")
            if imint == mint and isinstance(curve, str):
                found.append({"address": curve, "instruction": parsed.get("type"), "source": "parsed_official_instruction"})
        data = ix.get("data")
        if not isinstance(data, str):
            continue
        try:
            decoded = decode_b58(data)
        except (ValueError, IndexError):
            continue
        if len(decoded) < 8 or decoded[:8] not in IX_LAYOUT:
            continue
        name, names = IX_LAYOUT[decoded[:8]]
        if not any(part in name.lower() for part in ("buy", "sell")):
            continue
        values = ix_account_values(ix, keys)
        mapped = {account_name: values[i] for i, account_name in enumerate(names) if i < len(values)}
        imint = mapped.get("mint") or mapped.get("base_mint")
        curve = mapped.get("bonding_curve")
        if imint == mint and curve:
            found.append({"address": curve, "instruction": name, "source": "official_idl_account_order"})
    unique = {(x["address"], x["source"], x["instruction"]) for x in found}
    if len(unique) == 1:
        return found[0]
    if found:
        # Several Pump invocations in one transaction can touch the same mint;
        # accept them only when they resolve to one address.
        addresses = {x["address"] for x in found}
        if len(addresses) == 1:
            return found[0]
    return None


def normalize_tx(tx: dict[str, Any]) -> dict[str, Any]:
    body = tx_body(tx)
    return body


def successful_trade_rows(txs: list[dict[str, Any]], *, mint: str | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for tx in txs:
        body = normalize_tx(tx)
        try:
            events = decoder.events(body)
        except (KeyError, TypeError, ValueError, IndexError):
            continue
        sig = signature(tx)
        for event_index, event in enumerate(events):
            if mint is not None and event.get("mint") != mint:
                continue
            if not event.get("quote_is_sol"):
                continue
            try:
                rows.append({
                    "mint": event["mint"], "user": event["user"], "buy": bool(event["buy"]),
                    "tokens_raw": int(event["tokens_raw"]), "sol_raw": int(event["sol_raw"]),
                    "vsol_raw": int(event["vsol_raw"]), "vtokens_raw": int(event["vtokens_raw"]),
                    "rsol_raw": int(event["rsol_raw"]), "rtokens_raw": int(event["real_token_reserves"]),
                    "quote_mint": event.get("quote_mint"), "fee_bps": event.get("fee_basis_points"),
                    "creator_fee_bps": event.get("creator_fee_basis_points"),
                    "slot": body.get("slot"), "transaction_index": tx_index(tx),
                    "block_time": body.get("blockTime"), "signature": sig,
                    "event_index": event_index,
                })
            except (KeyError, TypeError, ValueError):
                continue
    rows.sort(key=order_key)
    return rows


def event_pre_state(row: dict[str, Any]) -> dict[str, Any]:
    # Pump TradeEvent states are post-trade; exact event inputs undo this event.
    sign = 1 if row["buy"] else -1
    pre_vsol = row["vsol_raw"] - sign * row["sol_raw"]
    pre_rsol = row["rsol_raw"] - sign * row["sol_raw"]
    pre_vtokens = row["vtokens_raw"] + sign * row["tokens_raw"]
    pre_rtokens = row["rtokens_raw"] + sign * row["tokens_raw"]
    price = (pre_vsol / pre_vtokens) if pre_vsol > 0 and pre_vtokens > 0 else None
    return {"vsol_raw": pre_vsol, "rsol_raw": pre_rsol, "vtokens_raw": pre_vtokens,
            "rtokens_raw": pre_rtokens, "price_ratio": price}


def post_price(row: dict[str, Any]) -> float | None:
    if row["vsol_raw"] <= 0 or row["vtokens_raw"] <= 0:
        return None
    return row["vsol_raw"] / row["vtokens_raw"]


def flow_summary(rows: list[dict[str, Any]], creator: str | None) -> dict[str, Any]:
    outside = [r for r in rows if not creator or r["user"] != creator]
    buys = [r for r in outside if r["buy"]]
    sells = [r for r in outside if not r["buy"]]
    return {
        "buy_events": len(buys), "sell_events": len(sells),
        "creator_identity_known": creator is not None,
        "scope": "excludes authenticated creator" if creator is not None else "all observed users; creator unknown",
        "transaction_groups": len({r["signature"] for r in outside}),
        "buy_sol": sum(r["sol_raw"] for r in buys) / LAMPORTS,
        "sell_sol": sum(r["sol_raw"] for r in sells) / LAMPORTS,
        "net_sol": (sum(r["sol_raw"] for r in buys) - sum(r["sol_raw"] for r in sells)) / LAMPORTS,
        "unique_buyers": len({r["user"] for r in buys}),
        "unique_sellers": len({r["user"] for r in sells}),
        "buyer_addresses": sorted({r["user"] for r in buys}),
    }


def window_rows(prior: list[dict[str, Any]], anchor: dict[str, Any], slots: int) -> list[dict[str, Any]]:
    if not isinstance(anchor.get("slot"), int):
        return []
    return [r for r in prior if isinstance(r.get("slot"), int)
            and 0 <= anchor["slot"] - r["slot"] <= slots]


def roster_counts(prior: list[dict[str, Any]], anchor: dict[str, Any], creator: str | None,
                  kol: set[str], tracked: set[str], targets: set[str],
                  genesis_found: bool) -> dict[str, Any]:
    # Only successful buy users count as observed buyers; membership snapshots are current.
    buys = [r for r in prior if r["buy"] and (not creator or r["user"] != creator)]
    groups = {
        "kol_current_snapshot": kol,
        "tracked16_current_file": tracked,
        "other_22_targets": targets,
    }
    out: dict[str, Any] = {}
    all_addrs = {r["user"] for r in buys}
    out["all_observed_prior_unique_buyers"] = len(all_addrs)
    out["all_observed_prior_buyers_complete_from_genesis"] = genesis_found
    for label, roster in groups.items():
        cohort = [r for r in buys if r["user"] in roster]
        prior_addresses = {r["user"] for r in cohort}
        lag_counts = {}
        cumulative = {}
        for slots in (0, 1, 2, 5, 20):
            subset = [r for r in cohort if isinstance(anchor.get("slot"), int)
                      and isinstance(r.get("slot"), int) and anchor["slot"] - r["slot"] == slots]
            lag_counts[str(slots)] = sorted({r["user"] for r in subset})
            recent = [r for r in cohort if isinstance(anchor.get("slot"), int)
                      and isinstance(r.get("slot"), int) and 0 <= anchor["slot"] - r["slot"] <= slots]
            cumulative[str(slots)] = sorted({r["user"] for r in recent})
        out[label] = {
            "all_observed_prior_unique_buyers": len(prior_addresses),
            "all_observed_prior_addresses": sorted(prior_addresses),
            "exact_slot_lag_addresses": lag_counts,
            "cumulative_slot_window_addresses": cumulative,
        }
    out["other_observed_prior_unique_buyers"] = len(all_addrs - kol - tracked - targets)
    return out


def immediate_prior(prior: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not prior:
        return None
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in prior:
        groups[str(row["signature"])].append(row)
    last = max(groups.values(), key=lambda g: order_key(g[-1]))
    # This is an atomic predecessor transaction group, even when it emits multiple events.
    return {
        "signature": last[0]["signature"], "slot": last[0]["slot"],
        "transaction_index": last[0]["transaction_index"], "event_count": len(last),
        "users": sorted({r["user"] for r in last}),
        "sides": ["buy" if r["buy"] else "sell" for r in last],
        "sol_amounts": [r["sol_raw"] / LAMPORTS for r in last],
        "net_buy_sol": (sum(r["sol_raw"] for r in last if r["buy"])
                        - sum(r["sol_raw"] for r in last if not r["buy"])) / LAMPORTS,
        "atomic_group_multiple_events": len(last) != 1,
    }


def two_buyer_recovery(prior: list[dict[str, Any]], anchor: dict[str, Any], creator: str | None) -> dict[str, Any]:
    outside = [r for r in prior if not creator or r["user"] != creator]
    sells = [r for r in outside if not r["buy"]]
    if not sells:
        return {"qualifies": None if creator is None else False,
                "reason": "creator_identity_unknown" if creator is None else "no_prior_outside_sell",
                "creator_identity_known": creator is not None, "buyers": []}
    last_sell = sells[-1]
    # Keep only events after the latest sell by authenticated transaction order.
    after = [r for r in outside if r["buy"] and order_key(r) > order_key(last_sell)
             and r["signature"] != last_sell["signature"]
             and isinstance(anchor.get("slot"), int) and isinstance(r.get("slot"), int)
             and 0 <= r["slot"] - last_sell["slot"] <= 2]
    meaningful = [r for r in after if r["sol_raw"] >= 50_000_000]
    by_wallet: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in meaningful:
        by_wallet[row["user"]].append(row)
    # Distinct completed transaction groups are required for distinct buyers.
    # Latest outside sell to the observed entry is the diagnostic, not a performance rule.
    before_entry = {w: [r for r in vals if strictly_before(r, anchor)]
                    for w, vals in by_wallet.items()}
    buyer_signatures = {w: {r["signature"] for r in vals if r.get("signature")}
                        for w, vals in before_entry.items() if vals}
    # Maximum bipartite matching ensures each qualifying buyer can be assigned
    # a distinct transaction signature; one atomic bundle cannot count twice.
    signature_owner: dict[str, str] = {}
    def assign(wallet: str, seen: set[str]) -> bool:
        for sig in sorted(buyer_signatures.get(wallet, set())):
            if sig in seen:
                continue
            seen.add(sig)
            if sig not in signature_owner or assign(signature_owner[sig], seen):
                signature_owner[sig] = wallet
                return True
        return False
    for wallet in sorted(buyer_signatures):
        assign(wallet, set())
    wallet_names = sorted(set(signature_owner.values()))
    return {
        "qualifies": None if creator is None else len(wallet_names) >= 2,
        "reason": ("creator_identity_unknown" if creator is None else
                   "at_least_two_distinct_noncreator_buyers_in_separate_transactions" if len(wallet_names) >= 2 else
                   "fewer_than_two_distinct_buyers_or_transaction_groups"),
        "latest_prior_sell": {"signature": last_sell["signature"], "user": last_sell["user"],
                              "slot": last_sell["slot"], "sol_out": last_sell["sol_raw"] / LAMPORTS},
        "distinct_buyers": len(wallet_names), "buyers": wallet_names,
        "buyer_signatures": {w: sorted({r["signature"] for r in before_entry[w]}) for w in wallet_names},
        "creator_identity_known": creator is not None,
        "rule": "Two distinct noncreator users each made an authenticated SOL buy of >=0.05 SOL in a separate transaction within two slots after the latest prior outside sell and before the target buy; descriptive diagnostic only.",
    }


def observed_peak_drawdown(prior: list[dict[str, Any]], anchor: dict[str, Any],
                           creation: dict[str, Any] | None) -> tuple[float | None, dict[str, Any] | None, float | None]:
    anchor_pre = event_pre_state(anchor)
    peak = None
    peak_row = None
    if creation:
        cv, ct = creation.get("virtual_sol_reserves"), creation.get("virtual_token_reserves")
        if isinstance(cv, int) and isinstance(ct, int) and cv > 0 and ct > 0:
            peak = cv / ct
            peak_row = {"source": "authenticated_CreateEvent", "slot": creation.get("slot"), "block_time": creation.get("block_time")}
    for row in sorted(prior, key=order_key):
        price = post_price(row)
        if price is not None and (peak is None or price > peak):
            peak = price
            peak_row = {"source": "authenticated_TradeEvent", "slot": row["slot"], "block_time": row["block_time"],
                        "signature": row["signature"], "user": row["user"]}
    # Include the marker's derived pre-state as the final observation so drawdown
    # is never positive when the marker itself sets a new observed high.
    if anchor_pre["price_ratio"] is not None and (peak is None or anchor_pre["price_ratio"] > peak):
        peak = anchor_pre["price_ratio"]
        peak_row = {"source": "entry_derived_pre_state", "slot": anchor.get("slot"),
                    "block_time": anchor.get("block_time"), "signature": anchor.get("signature")}
    drawdown = (anchor_pre["price_ratio"] / peak - 1.0) if anchor_pre["price_ratio"] is not None and peak else None
    return peak, peak_row, drawdown


def recent_roster_presence(flow: dict[str, Any], kol: set[str], tracked: set[str]) -> dict[str, Any]:
    buyers = set(flow.get("buyer_addresses", []))
    kol_hits, tracked_hits = sorted(buyers & kol), sorted(buyers & tracked)
    return {
        "kol_current_snapshot_present": bool(kol_hits), "kol_current_snapshot_buyer_addresses": kol_hits,
        "tracked16_current_file_present": bool(tracked_hits), "tracked16_current_file_buyer_addresses": tracked_hits,
    }


def build_context(prior: list[dict[str, Any]], anchor: dict[str, Any], creator: str | None,
                  kol: set[str], tracked: set[str], targets: set[str], genesis_found: bool,
                  creation: dict[str, Any] | None) -> dict[str, Any]:
    windows = {str(k): flow_summary(window_rows(prior, anchor, k), creator) for k in (1, 5, 20)}
    groups = defaultdict(list)
    for row in prior:
        groups[row["signature"]].append(row)
    last = immediate_prior(prior)
    all_prior = sorted(prior, key=order_key)
    pre_state = event_pre_state(anchor)
    peak, peak_row, drawdown = observed_peak_drawdown(all_prior, anchor, creation)
    five_slot_roster = recent_roster_presence(windows["5"], kol, tracked)
    return {
        "pre_entry_reserve_state": {
            "real_sol_raw": pre_state["rsol_raw"], "real_sol": pre_state["rsol_raw"] / LAMPORTS,
            "virtual_sol_raw": pre_state["vsol_raw"], "virtual_token_raw": pre_state["vtokens_raw"],
            "marginal_spot_ratio_sol_per_raw_token": pre_state["price_ratio"],
            "source": "entry TradeEvent post-state minus exact authenticated event SOL/token input",
        },
        "post_entry_reserve_state": {
            "real_sol_raw": anchor["rsol_raw"], "real_sol": anchor["rsol_raw"] / LAMPORTS,
            "virtual_sol_raw": anchor["vsol_raw"], "virtual_token_raw": anchor["vtokens_raw"],
            "marginal_spot_ratio_sol_per_raw_token": post_price(anchor),
        },
        "observed_pre_entry_peak": {"price_ratio_sol_per_raw_token": peak, **(peak_row or {})},
        "observed_drawdown_from_peak_pct": drawdown * 100 if drawdown is not None else None,
        "price_path_coverage": "from authenticated creation" if genesis_found else "only queried prefix; genesis not found",
        "pre_entry_flow_by_cumulative_slot_window": windows,
        "current_roster_buyers_in_last5slots": five_slot_roster,
        "immediate_prior_trade_group": last,
        "two_buyer_recovery": two_buyer_recovery(all_prior, anchor, creator),
        "roster_pre_entry_participation": roster_counts(all_prior, anchor, creator, kol, tracked,
                                                        targets - {anchor.get("user")}, genesis_found),
        "prior_event_count": len(all_prior),
        "prior_transaction_group_count": len(groups),
        "same_slot_prior_event_count": sum(r["slot"] == anchor.get("slot") for r in all_prior),
    }


def matched_controls(prior: list[dict[str, Any]], anchor: dict[str, Any], target_pre_real: int,
                     targets: set[str], creator: str | None, creation: dict[str, Any] | None,
                     kol: set[str], tracked: set[str]) -> list[dict[str, Any]]:
    if target_pre_real <= 0 or not isinstance(anchor.get("slot"), int):
        return []
    # A state per completed transaction only; bundling multiple Pump trade events
    # into one transaction does not provide a separate decision point.
    event_counts = Counter(r["signature"] for r in prior)
    controls = []
    for row in prior:
        if not row["buy"] or row["user"] in targets or (creator and row["user"] == creator):
            continue
        if event_counts[row["signature"]] != 1:
            continue
        gap = anchor["slot"] - row["slot"] if isinstance(row.get("slot"), int) else None
        if gap is None or not 0 <= gap <= 32:
            continue
        pre = event_pre_state(row)
        reserve = pre["rsol_raw"]
        if not (0.8 * target_pre_real <= reserve <= 1.2 * target_pre_real):
            continue
        control_prior = [earlier for earlier in prior if strictly_before(earlier, row)]
        control_window = flow_summary(window_rows(control_prior, row, 5), creator)
        control_creation = creation if creation is not None and strictly_before(creation, row) else None
        control_peak, control_peak_row, control_drawdown = observed_peak_drawdown(control_prior, row, control_creation)
        control_last = immediate_prior(control_prior)
        controls.append({
            "signature": row["signature"], "user": row["user"], "slot": row["slot"],
            "transaction_index": row["transaction_index"], "slot_gap_before_target": gap,
            "buy_sol": row["sol_raw"] / LAMPORTS, "pre_real_sol": reserve / LAMPORTS,
            "pre_price_ratio": pre["price_ratio"],
            "roster_role": "kol" if row["user"] in KOL_ROSTER else "tracked16" if row["user"] in TRACKED_ROSTER else "other",
            "pre_control_outside_flow_last5slots": {
                "net_sol": control_window["net_sol"], "buy_events": control_window["buy_events"],
                "sell_events": control_window["sell_events"], "unique_buyers": control_window["unique_buyers"],
                "unique_sellers": control_window["unique_sellers"],
                "current_roster_buyer_presence": recent_roster_presence(control_window, kol, tracked),
            },
            "observed_drawdown_from_precontrol_peak_pct": control_drawdown * 100 if control_drawdown is not None else None,
            "observed_precontrol_peak": {"price_ratio_sol_per_raw_token": control_peak, **(control_peak_row or {})},
            "immediate_prior_trade_group_before_control": control_last,
        })
    return controls


def creation_rows(txs: list[dict[str, Any]], mint: str, anchor: dict[str, Any]) -> list[dict[str, Any]]:
    creates = []
    for tx in txs:
        body = tx_body(tx)
        try:
            rows = decoder.creations(body)
        except (KeyError, TypeError, ValueError, IndexError):
            continue
        for event in rows:
            if event.get("mint") != mint:
                continue
            row = {"slot": body.get("slot"), "transaction_index": tx_index(tx), "block_time": body.get("blockTime"),
                   "signature": signature(tx), "curve": event.get("curve"), "creator": event.get("deployer"),
                   "virtual_sol_reserves": event.get("virtual_sol_reserves"),
                   "virtual_token_reserves": event.get("virtual_token_reserves"),
                   "real_token_reserves": event.get("real_token_reserves")}
            if strictly_before(row, anchor):
                creates.append(row)
    creates.sort(key=order_key)
    return creates


def freeze_info() -> dict[str, Any]:
    path = RAW_WALLETS / "freeze.json"
    if not path.exists():
        return {"error": "raw_wallets/freeze.json missing"}
    freeze = json.loads(path.read_text(encoding="utf-8"))
    if "blockTime" not in freeze:
        freeze["blockTime"] = freeze.get("block_time")
    if "blockTime_utc" not in freeze:
        freeze["blockTime_utc"] = freeze.get("utc")
    return freeze


def recent_candidates(limit: int, freeze: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    wallets = json.loads(TARGETS_PATH.read_text(encoding="utf-8"))
    cutoff_time = freeze.get("blockTime", freeze.get("block_time"))
    if not isinstance(cutoff_time, int):
        raise ValueError("freeze.json has no integer finalized blockTime")
    roster = roster_snapshot()
    kol, tracked = set(roster.pop("kol_addresses")), set(roster.pop("tracked_addresses"))
    candidates: list[dict[str, Any]] = []
    coverage = []
    for wallet in wallets:
        address = wallet["address"]
        path = RAW_WALLETS / f"recent_{address}.json.gz"
        if not path.exists():
            coverage.append({"address": address, "name": wallet.get("name"), "status": "missing_recent_file", "tx_count": 0})
            continue
        document = read_gzip_json(path)
        txs = document.get("transactions", [])
        found: dict[str, dict[str, Any]] = {}
        decoded_n = 0
        failed_n = 0
        newer_n = 0
        missing_time_n = 0
        payer_linked_events = []
        payer_tx_count = 0
        signer_tx_count = 0
        for tx in txs:
            body = tx_body(tx)
            bt = body.get("blockTime")
            if not isinstance(bt, int):
                missing_time_n += 1
                continue
            if bt > cutoff_time:
                newer_n += 1
                continue
            events = successful_trade_rows([tx])
            if not events:
                if (body.get("meta") or {}).get("err") is not None:
                    failed_n += 1
                continue
            tx_keys = account_keys(body)
            tx_signers = signer_keys(body)
            fee_payer = tx_keys[0] if tx_keys else None
            target_is_fee_payer = fee_payer == address
            target_is_signer = address in tx_signers
            if target_is_fee_payer:
                payer_tx_count += 1
            if target_is_signer:
                signer_tx_count += 1
            if target_is_fee_payer or target_is_signer:
                nonce_authorities = parsed_nonce_authorities(body)
                program_ids = sorted({p for ix in instruction_rows(body) if (p := ix_program(ix, tx_keys))})
                for linked_event in events:
                    if linked_event["user"] == address:
                        continue
                    related = {address, linked_event["user"]}
                    payer_linked_events.append({
                        "signature": linked_event["signature"], "slot": linked_event["slot"],
                        "transaction_index": linked_event["transaction_index"], "blockTime": linked_event["block_time"],
                        "mint": linked_event["mint"], "event_user": linked_event["user"],
                        "side": "buy" if linked_event["buy"] else "sell",
                        "event_sol": linked_event["sol_raw"] / LAMPORTS,
                        "target_is_fee_payer": target_is_fee_payer, "target_is_signer": target_is_signer,
                        "target_is_parsed_nonce_authority": address in nonce_authorities,
                        "event_user_is_signer": linked_event["user"] in tx_signers,
                        "event_user_is_target_account_reference": linked_event["user"] in tx_keys,
                        "parsed_native_transfers_touching_target_or_event_user": parsed_native_transfers(body, related),
                        "invoked_program_ids": program_ids,
                        "association_only_note": "Co-occurrence, signer, payer, nonce-authority, transfer, and account references are transaction-level associations; they do not prove shared ownership or copying.",
                    })
            for event in events:
                if event["user"] != address or not event["buy"]:
                    continue
                decoded_n += 1
                mint = event["mint"]
                candidate = dict(event)
                # Select signatures with a fixed, outcome-blind hash.
                candidate["selection_hash"] = hashlib.sha256(f"{address}\0{event['signature']}".encode()).hexdigest()
                candidate["wallet"] = address
                candidate["wallet_name"] = wallet.get("name")
                candidate["amount_sol"] = event["sol_raw"] / LAMPORTS
                candidate["fee_payer"] = fee_payer
                candidate["fee_payer_is_event_user"] = bool(fee_payer == address)
                candidate["transaction_account_keys"] = tx_keys
                candidate["transaction_signers"] = tx_signers
                candidate["curve_resolution"] = official_curve_from_entry(tx, mint)
                candidate["receipt_status"] = "successful_full_transaction_and_pump_invocation"
                candidate["sample_source"] = "frozen_latest_250_receipts"
                prior = found.get(mint)
                if prior is None or candidate["selection_hash"] < prior["selection_hash"]:
                    found[mint] = candidate
        distinct = sorted(found.values(), key=lambda row: (row["selection_hash"], row["mint"], row["signature"]))
        chosen = distinct[:limit]
        candidates.extend(chosen)
        coverage.append({
            "address": address, "name": wallet.get("name"), "status": document.get("error", "complete"),
            "recent_receipt_count": len(txs), "auth_successful_sol_pump_buy_events": decoded_n,
            "distinct_authenticated_buy_mints": len(found), "selected_distinct_mints": len(chosen),
            "failed_recent_receipts": failed_n, "missing_block_time_receipts": missing_time_n,
            "after_freeze_cutoff_receipts_excluded": newer_n, "pagination_token": document.get("pagination_token"),
            "target_as_fee_payer_successful_trade_tx_count": payer_tx_count,
            "target_as_signer_successful_trade_tx_count": signer_tx_count,
            "other_event_user_trade_event_count_in_target_payer_or_signer_transactions": len(payer_linked_events),
            "other_event_user_distinct_addresses_in_target_payer_or_signer_transactions": len({x["event_user"] for x in payer_linked_events}),
            "other_event_user_linked_trade_observations": payer_linked_events,
            "error": document.get("error"),
        })
        print(f"wallet candidates {len(coverage)}/{len(wallets)}: {wallet.get('name')} {len(chosen)}/{len(found)}", flush=True)
    roster["kol_count"] = len(kol)
    roster["tracked_count"] = len(tracked)
    return candidates, {"wallet_coverage": coverage, "roster": roster, "target_addresses": [w["address"] for w in wallets]}


def successful_history_extension_candidates(limit: int, freeze: dict[str, Any],
                                            primary_candidates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Fill only below-cap wallets from separately retained succeeded-only histories."""
    wallets = json.loads(TARGETS_PATH.read_text(encoding="utf-8"))
    hi = int(freeze["blockTime"])
    lo = hi - 21 * 24 * 60 * 60
    primary_by_wallet: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in primary_candidates:
        primary_by_wallet[row["wallet"]].append(row)
    selected: list[dict[str, Any]] = []
    coverage = []
    base = RAW_WALLETS / "successful_history"
    for wallet in wallets:
        address = wallet["address"]
        main_rows = primary_by_wallet.get(address, [])
        needed = max(0, limit - len(main_rows))
        history_dir = base / address
        files = sorted(history_dir.glob("page-*.json.gz")) if history_dir.exists() else []
        found: dict[str, dict[str, Any]] = {}
        raw_rows = 0
        decode_buy_events = 0
        outside_window = 0
        for path in files:
            document = read_gzip_json(path)
            page_rows = document.get("transactions", [])
            raw_rows += len(page_rows)
            for tx in page_rows:
                body = tx_body(tx)
                bt = body.get("blockTime")
                if not isinstance(bt, int) or bt < lo or bt >= hi:
                    outside_window += 1
                    continue
                for event in successful_trade_rows([tx]):
                    if event["user"] != address or not event["buy"]:
                        continue
                    decode_buy_events += 1
                    candidate = dict(event)
                    candidate["selection_hash"] = hashlib.sha256(f"{address}\0{event['signature']}".encode()).hexdigest()
                    candidate["wallet"] = address
                    candidate["wallet_name"] = wallet.get("name")
                    candidate["amount_sol"] = event["sol_raw"] / LAMPORTS
                    keys = account_keys(body)
                    candidate["fee_payer"] = keys[0] if keys else None
                    candidate["fee_payer_is_event_user"] = bool(keys and keys[0] == address)
                    candidate["transaction_account_keys"] = keys
                    candidate["transaction_signers"] = signer_keys(body)
                    candidate["curve_resolution"] = official_curve_from_entry(tx, event["mint"])
                    candidate["receipt_status"] = "successful_full_transaction_and_pump_invocation"
                    candidate["sample_source"] = "succeeded_only_21day_history_supplement"
                    candidate["history_page"] = path.name
                    candidate["event_index"] = event["event_index"]
                    previous = found.get(event["mint"])
                    rank = (candidate["selection_hash"], candidate["signature"], candidate["event_index"])
                    if previous is None or rank < (previous["selection_hash"], previous["signature"], previous["event_index"]):
                        found[event["mint"]] = candidate
        excluded_primary_mints = {row["mint"] for row in main_rows}
        remaining = [row for mint, row in found.items() if mint not in excluded_primary_mints]
        remaining.sort(key=lambda row: (row["selection_hash"], row["mint"], row["signature"]))
        chosen = remaining[:needed]
        selected.extend(chosen)
        coverage.append({
            "address": address, "name": wallet.get("name"), "history_directory": str(history_dir.relative_to(HERE)) if history_dir.exists() else None,
            "pages": len(files), "raw_rows": raw_rows, "authenticated_sol_pump_buy_events": decode_buy_events,
            "distinct_authenticated_buy_mints": len(found), "primary_mints_excluded": len(found) - len(remaining),
            "selected_extension_mints": len(chosen), "below_cap_capacity_before_extension": needed,
            "blockTime_window": {"gte": lo, "lt": hi},
            "page_cap_truncated": any(bool(read_gzip_json(path).get("pagination_token")) for path in files),
            "raw_rows_outside_21day_window": outside_window,
            "status": "available" if files else "no_supplemental_history",
            "request_scope": "succeeded-only full receipts; failed receipts excluded by collector request filter",
        })
        if files:
            print(f"history supplement {wallet.get('name')}: {len(chosen)} selected from {len(found)} authenticated mints", flush=True)
    return selected, coverage


def payer_linked_child_candidates(limit: int, freeze: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Select real child-user buys from the bottimus payer/signer's recent receipts."""
    wallets = json.loads(TARGETS_PATH.read_text(encoding="utf-8"))
    parent = next((w for w in wallets if w.get("name", "").lower() == "bottimus"), None)
    if parent is None:
        return [], {"status": "linked_parent_not_found", "selected_count": 0}
    address = parent["address"]
    path = RAW_WALLETS / f"recent_{address}.json.gz"
    if not path.exists():
        return [], {"status": "missing_recent_file", "selected_count": 0}
    document = read_gzip_json(path)
    found: dict[str, dict[str, Any]] = {}
    event_count = 0
    eligible_tx_count = 0
    user_counts = Counter()
    freeze_time = int(freeze["blockTime"])
    for tx in document.get("transactions", []):
        body = tx_body(tx)
        bt = body.get("blockTime")
        if not isinstance(bt, int) or bt > freeze_time:
            continue
        decoded = successful_trade_rows([tx])
        if not decoded:
            continue
        keys = account_keys(body)
        signers = signer_keys(body)
        payer = keys[0] if keys else None
        if payer != address and address not in signers:
            continue
        eligible_tx_count += 1
        for event in decoded:
            if not event["buy"] or event["user"] == address:
                continue
            event_count += 1
            user_counts[event["user"]] += 1
            candidate = dict(event)
            candidate["selection_hash"] = hashlib.sha256(f"{address}\0{event['signature']}".encode()).hexdigest()
            candidate["wallet"] = address
            candidate["wallet_name"] = f"{parent.get('name')} linked event users"
            candidate["amount_sol"] = event["sol_raw"] / LAMPORTS
            candidate["fee_payer"] = payer
            candidate["fee_payer_is_event_user"] = payer == event["user"]
            candidate["transaction_account_keys"] = keys
            candidate["transaction_signers"] = signers
            candidate["curve_resolution"] = official_curve_from_entry(tx, event["mint"])
            candidate["receipt_status"] = "successful_full_transaction_and_pump_invocation"
            candidate["sample_source"] = "payer_linked_child_event_user_recent250"
            candidate["linked_parent_wallet"] = address
            candidate["linked_parent_is_signer"] = address in signers
            candidate["linked_parent_is_parsed_nonce_authority"] = address in parsed_nonce_authorities(body)
            candidate["event_user_is_signer"] = event["user"] in signers
            candidate["linked_event_user"] = event["user"]
            candidate["related_native_transfers"] = parsed_native_transfers(body, {address, event["user"]})
            previous = found.get(event["mint"])
            rank = (candidate["selection_hash"], candidate["signature"], candidate["event_index"])
            if previous is None or rank < (previous["selection_hash"], previous["signature"], previous["event_index"]):
                found[event["mint"]] = candidate
    ordered = sorted(found.values(), key=lambda row: (row["selection_hash"], row["mint"], row["signature"]))
    chosen = ordered[:limit]
    return chosen, {
        "status": document.get("error", "complete"), "parent_wallet": address, "parent_name": parent.get("name"),
        "receipt_count": len(document.get("transactions", [])), "target_as_fee_payer_or_signer_successful_trade_tx_count": eligible_tx_count,
        "authenticated_nonparent_sol_pump_buy_events": event_count, "distinct_mints": len(found),
        "distinct_child_event_users": len(user_counts), "child_event_user_event_counts": dict(user_counts),
        "selected_distinct_mints": len(chosen), "per_wallet_cap": limit,
        "selection_rule": "Among successful SOL-quoted Pump buy events with event.user != payer wallet in a transaction where payer wallet is fee payer or signer, keep the minimum sha256(parent_wallet + NUL + signature) event per mint; sort by hash and select first N mints. Child TradeEvent.user remains the authenticated trader.",
        "association_caveat": "Payer/signer/nonce-authority/signature co-occurrence and transfers are associations, not proof of shared ownership, control, or copying.",
    }


def fetch_prefix(candidate: dict[str, Any], freeze: dict[str, Any]) -> dict[str, Any]:
    resolution = candidate.get("curve_resolution") or {"address": candidate["mint"], "source": "mint_address_fallback"}
    address = resolution.get("address") or candidate["mint"]
    cutoff = min(int(candidate["block_time"]), int(freeze["blockTime"]))
    cfg: dict[str, Any] = {
        "transactionDetails": "full", "encoding": "jsonParsed", "maxSupportedTransactionVersion": 1,
        "sortOrder": "desc", "limit": 500, "commitment": "finalized",
        "filters": {"blockTime": {"lte": cutoff}},
    }
    txs: list[dict[str, Any]] = []
    page_audits = []
    token = None
    for page_number in range(2):
        page_cfg = dict(cfg)
        if token:
            page_cfg["paginationToken"] = token
        response = rpc_with_meta("getTransactionsForAddress", [address, page_cfg])
        result = response["result"]
        data = result.get("data", []) if isinstance(result, dict) else []
        txs.extend(data)
        next_token = result.get("paginationToken") if isinstance(result, dict) else None
        page_audits.append({"page": page_number + 1, "request": page_cfg,
                            "provider": response.get("provider"), "cache_hit": response.get("cache_hit"),
                            "count": len(data), "had_pagination_token": bool(next_token)})
        if not next_token:
            token = None
            break
        if next_token == token:
            raise ValueError("prefix pagination token repeated")
        token = next_token
    return {
        "schema_version": 1, "mint": candidate["mint"], "wallet": candidate["wallet"],
        "entry_signature": candidate["signature"], "entry_slot": candidate["slot"],
        "entry_transaction_index": candidate["transaction_index"], "entry_blockTime": candidate["block_time"],
        "freeze": freeze, "query_address": address, "curve_resolution": resolution,
        "blockTime_cutoff": cutoff, "max_pages": 2, "page_audits": page_audits,
        "pagination_truncated": bool(token), "oldest_returned_slot": min((t.get("slot", 0) for t in txs), default=None),
        "transaction_count": len(txs), "transactions": txs,
    }


def prefix_path(candidate: dict[str, Any]) -> pathlib.Path:
    safe_sig = str(candidate["signature"])[:18]
    return PREFIX_DIR / f"{candidate['mint']}__{safe_sig}.json.gz"


def analyze_candidate(candidate: dict[str, Any], prefix: dict[str, Any],
                      roster: dict[str, Any], targets: set[str]) -> dict[str, Any]:
    raw_txs = prefix.get("transactions", [])
    target = {"signature": candidate["signature"], "slot": candidate["slot"],
              "transaction_index": candidate["transaction_index"]}
    all_rows = successful_trade_rows(raw_txs, mint=candidate["mint"])
    prior = [row for row in all_rows if strictly_before(row, target)]
    creates = creation_rows(raw_txs, candidate["mint"], target)
    creation = creates[0] if creates else None
    creator = creation.get("creator") if creation else None
    genesis_found = creation is not None
    kol, tracked = set(roster.get("kol_addresses", [])), set(roster.get("tracked_addresses", []))
    ctx = build_context(prior, candidate, creator, kol, tracked, targets, genesis_found, creation)
    entry_pre = event_pre_state(candidate)
    # Genesis/instruction mapping agreement and reserve continuity are audits, not filters.
    last_prior = max(prior, key=order_key) if prior else None
    continuity = None
    if last_prior:
        continuity = {
            "previous_post_real_sol_raw": last_prior["rsol_raw"],
            "entry_derived_pre_real_sol_raw": entry_pre["rsol_raw"],
            "real_sol_match": last_prior["rsol_raw"] == entry_pre["rsol_raw"],
            "previous_post_virtual_sol_raw": last_prior["vsol_raw"],
            "entry_derived_pre_virtual_sol_raw": entry_pre["vsol_raw"],
            "virtual_sol_match": last_prior["vsol_raw"] == entry_pre["vsol_raw"],
            "previous_post_virtual_token_raw": last_prior["vtokens_raw"],
            "entry_derived_pre_virtual_token_raw": entry_pre["vtokens_raw"],
            "virtual_token_match": last_prior["vtokens_raw"] == entry_pre["vtokens_raw"],
        }
        continuity["all_three_reserves_match"] = bool(
            continuity["real_sol_match"] and continuity["virtual_sol_match"]
            and continuity["virtual_token_match"])
    # If same-slot indexes are missing, their order is unresolved; strict prior excludes them.
    same_slot_unordered = sum(1 for row in all_rows if row.get("slot") == candidate.get("slot")
                              and row.get("signature") != candidate.get("signature")
                              and (row.get("transaction_index") is None or candidate.get("transaction_index") is None))
    controls = matched_controls(prior, candidate, entry_pre["rsol_raw"], targets, creator, creation, kol, tracked)
    pre_flow5 = ctx["pre_entry_flow_by_cumulative_slot_window"]["5"]
    pred = ctx["immediate_prior_trade_group"]
    target_before = ctx["roster_pre_entry_participation"]
    tx_accounts = set(candidate.get("transaction_account_keys", []))
    current_roster_references = {
        "kol_current_snapshot_account_keys": sorted(tx_accounts & kol),
        "tracked16_current_file_account_keys": sorted(tx_accounts & tracked),
        "other_22_targets_account_keys": sorted(tx_accounts & targets),
        "event_user_is_also_account_key": candidate.get("user") in tx_accounts,
        "interpretation": "Transaction account reference only; does not establish a TradeEvent user, knowledge, copying, or ownership relationship.",
    }
    return {
        "wallet": candidate["wallet"], "wallet_name": candidate["wallet_name"],
        "mint": candidate["mint"], "signature": candidate["signature"],
        "signature_sha256_wallet_plus_signature": candidate["selection_hash"],
        "slot": candidate["slot"], "transaction_index": candidate["transaction_index"],
        "blockTime": candidate["block_time"], "blockTime_clock_note": "Whole-second block timestamp; used only for cutoff and authenticated creation age, not within-slot ordering.",
        "event_user": candidate["user"], "fee_payer": candidate.get("fee_payer"),
        "fee_payer_is_event_user": candidate.get("fee_payer_is_event_user"),
        "transaction_signers": candidate.get("transaction_signers", []),
        "current_roster_transaction_account_references": current_roster_references,
        "sample_source": candidate.get("sample_source", "frozen_latest_250_receipts"),
        "entry_sol_input": candidate["amount_sol"], "quote_mint": candidate.get("quote_mint"),
        "receipt_authentication": candidate["receipt_status"],
        "official_curve_resolution": candidate.get("curve_resolution"),
        "prefix_query": {k: prefix.get(k) for k in ["query_address", "curve_resolution", "blockTime_cutoff", "transaction_count", "max_pages", "pagination_truncated", "page_audits", "oldest_returned_slot"]},
        "genesis": {"found": genesis_found, "event": creation,
                    "entry_age_seconds_from_authenticated_CreateEvent": (candidate["block_time"] - creation["block_time"] if creation and isinstance(creation.get("block_time"), int) else None),
                    "status": "found" if genesis_found else "missing_from_two_page_prefix"},
        "entry_creator_relation": {
            "creator_identity_known_from_authenticated_CreateEvent": creator is not None,
            "genesis_creator": creator,
            "event_user_equals_genesis_creator": (candidate["user"] == creator) if creator is not None else None,
            "interpretation": "A selected creator buy may reflect token creation/deployer participation; it is not treated as an independent follower entry.",
        },
        "pre_entry_context": ctx,
        "reserve_continuity_to_last_prior_curve_event": continuity,
        "same_slot_index_order_unresolved_event_count": same_slot_unordered,
        "entry_state_checks": {
            "event_pre_real_sol_raw": entry_pre["rsol_raw"],
            "event_post_real_sol_raw": candidate["rsol_raw"],
            "exact_event_sol_input_raw": candidate["sol_raw"],
            "pre_event_marginal_price_ratio": entry_pre["price_ratio"],
            "post_event_marginal_price_ratio": post_price(candidate),
        },
        "same_prefix_preceding_non_target_controls": {
            "rule": "Single-event authenticated SOL Pump buy transaction by a non-target, noncreator buyer, strictly before target (slot,index), within 32 slots, with pre-entry real SOL reserve within ±20% of target pre-entry reserve.",
            "match_assignment_count": len(controls), "unique_control_signatures": len({x["signature"] for x in controls}),
            "controls": controls,
            "status": "available" if controls else "no qualifying controls",
        },
    }


def target_control_comparison(entries: list[dict[str, Any]], controls: list[dict[str, Any]]) -> dict[str, Any]:
    def stats(values: list[Any]) -> dict[str, Any]:
        clean = [x for x in values if isinstance(x, (int, float)) and math.isfinite(x)]
        return {"n": len(clean), "median": statistics.median(clean) if clean else None}
    def side(group: dict[str, Any] | None) -> str:
        if group is None:
            return "none"
        sides = set(group.get("sides", []))
        if len(sides) > 1:
            return "mixed_atomic_group"
        return next(iter(sides), "none")
    target_net, target_buyers, target_dd, target_kol, target_tracked = [], [], [], [], []
    target_sides = Counter()
    for row in entries:
        ctx = row["pre_entry_context"]
        flow = ctx["pre_entry_flow_by_cumulative_slot_window"]["5"]
        presence = ctx["current_roster_buyers_in_last5slots"]
        target_net.append(flow["net_sol"])
        target_buyers.append(flow["unique_buyers"])
        target_dd.append(ctx["observed_drawdown_from_peak_pct"])
        target_kol.append(1.0 if presence["kol_current_snapshot_present"] else 0.0)
        target_tracked.append(1.0 if presence["tracked16_current_file_present"] else 0.0)
        target_sides[side(ctx["immediate_prior_trade_group"])] += 1
    control_net, control_buyers, control_dd, control_kol, control_tracked = [], [], [], [], []
    control_sides = Counter()
    for row in controls:
        flow = row["pre_control_outside_flow_last5slots"]
        presence = flow["current_roster_buyer_presence"]
        control_net.append(flow["net_sol"])
        control_buyers.append(flow["unique_buyers"])
        control_dd.append(row["observed_drawdown_from_precontrol_peak_pct"])
        control_kol.append(1.0 if presence["kol_current_snapshot_present"] else 0.0)
        control_tracked.append(1.0 if presence["tracked16_current_file_present"] else 0.0)
        control_sides[side(row["immediate_prior_trade_group_before_control"])] += 1
    def side_counts(counter: Counter) -> dict[str, Any]:
        total = sum(counter.values())
        return {"counts": dict(counter), "n": total}
    return {
        "targets": {
            "entry_count": len(entries), "median_outside_net_sol_last5slots": stats(target_net),
            "median_unique_outside_buyers_last5slots": stats(target_buyers),
            "median_observed_drawdown_pct": stats(target_dd),
            "current_kol_buyer_present_last5slots": {"count": int(sum(target_kol)), "n": len(target_kol)},
            "current_tracked16_buyer_present_last5slots": {"count": int(sum(target_tracked)), "n": len(target_tracked)},
            "immediate_prior_trade_group_side_counts": side_counts(target_sides),
        },
        "same_prefix_controls": {
            "assignment_count": len(controls), "unique_signatures": len({r["signature"] for r in controls}),
            "median_outside_net_sol_last5slots": stats(control_net),
            "median_unique_outside_buyers_last5slots": stats(control_buyers),
            "median_observed_drawdown_pct": stats(control_dd),
            "current_kol_buyer_present_last5slots": {"count": int(sum(control_kol)), "n": len(control_kol)},
            "current_tracked16_buyer_present_last5slots": {"count": int(sum(control_tracked)), "n": len(control_tracked)},
            "immediate_prior_trade_group_side_counts": side_counts(control_sides),
        },
        "caveat": "Descriptive, non-independent state comparison. Controls are selected from each target's same truncated prefix and reserve/slot matching rule; repeated signatures may appear across assignments.",
    }


def summarize(entries: list[dict[str, Any]], wallet_coverage: list[dict[str, Any]]) -> dict[str, Any]:
    wallets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in entries:
        wallets[row["wallet"]].append(row)
    per_wallet = []
    for coverage in wallet_coverage:
        address = coverage["address"]
        rows = wallets.get(address, [])
        def vals(fn):
            return [x for r in rows if (x := fn(r)) is not None and isinstance(x, (int, float)) and math.isfinite(x)]
        reserves = vals(lambda r: r["pre_entry_context"]["pre_entry_reserve_state"]["real_sol"])
        inputs = vals(lambda r: r["entry_sol_input"])
        drawdowns = vals(lambda r: r["pre_entry_context"]["observed_drawdown_from_peak_pct"])
        net5 = vals(lambda r: r["pre_entry_context"]["pre_entry_flow_by_cumulative_slot_window"]["5"]["net_sol"])
        buyers5 = vals(lambda r: r["pre_entry_context"]["pre_entry_flow_by_cumulative_slot_window"]["5"]["unique_buyers"])
        tbr = vals(lambda r: 1.0 if r["pre_entry_context"]["two_buyer_recovery"]["qualifies"] else 0.0)
        creator_matches = [r for r in rows if r["entry_creator_relation"]["event_user_equals_genesis_creator"] is True]
        prior_counter = Counter()
        for row in rows:
            for wallet in row["pre_entry_context"]["immediate_prior_trade_group"]["users"] if row["pre_entry_context"]["immediate_prior_trade_group"] else []:
                prior_counter[wallet] += 1
        per_wallet.append({
            "address": address, "name": coverage.get("name"), "selected": len(rows),
            "prefixes_fetched": sum(bool(r.get("prefix_query")) for r in rows),
            "genesis_found": sum(bool(r["genesis"]["found"]) for r in rows),
            "genesis_missing": sum(not r["genesis"]["found"] for r in rows),
            "median_pre_real_sol": statistics.median(reserves) if reserves else None,
            "median_entry_sol_input": statistics.median(inputs) if inputs else None,
            "median_observed_drawdown_pct": statistics.median(drawdowns) if drawdowns else None,
            "median_outside_net_sol_last5slots": statistics.median(net5) if net5 else None,
            "median_unique_outside_buyers_last5slots": statistics.median(buyers5) if buyers5 else None,
            "two_buyer_recovery_count": int(sum(tbr)), "two_buyer_recovery_n": len(tbr),
            "entry_user_equals_authenticated_creator_count": len(creator_matches),
            "entry_creator_identity_known_count": sum(r["entry_creator_relation"]["creator_identity_known_from_authenticated_CreateEvent"] for r in rows),
            "current_kol_account_reference_count": sum(bool(r["current_roster_transaction_account_references"]["kol_current_snapshot_account_keys"]) for r in rows),
            "current_tracked16_account_reference_count": sum(bool(r["current_roster_transaction_account_references"]["tracked16_current_file_account_keys"]) for r in rows),
            "most_repeated_immediate_predecessors": [{"address": a, "count": n} for a, n in prior_counter.most_common(3)],
            "recent_coverage": coverage,
        })
    controls = [c for row in entries for c in row["same_prefix_preceding_non_target_controls"]["controls"]]
    unique_controls = {c["signature"] for c in controls}
    curve_sources = Counter((r.get("prefix_query", {}).get("curve_resolution") or {}).get("source", "unknown") for r in entries)
    return {
        "selected_entry_count": len(entries),
        "distinct_target_wallets_with_selected_entries": len({r["wallet"] for r in entries}),
        "unique_target_mints": len({r["mint"] for r in entries}),
        "prefix_genesis_found": sum(r["genesis"]["found"] for r in entries),
        "prefix_genesis_missing": sum(not r["genesis"]["found"] for r in entries),
        "last_prior_state_real_sol_continuity_passed": sum(bool(r["reserve_continuity_to_last_prior_curve_event"] and r["reserve_continuity_to_last_prior_curve_event"]["real_sol_match"]) for r in entries),
        "last_prior_state_real_sol_continuity_checked": sum(r["reserve_continuity_to_last_prior_curve_event"] is not None for r in entries),
        "last_prior_state_all_three_reserves_continuity_passed": sum(bool(r["reserve_continuity_to_last_prior_curve_event"] and r["reserve_continuity_to_last_prior_curve_event"].get("all_three_reserves_match")) for r in entries),
        "last_prior_state_all_three_reserves_continuity_checked": sum(r["reserve_continuity_to_last_prior_curve_event"] is not None for r in entries),
        "entry_user_equals_authenticated_creator_count": sum(r["entry_creator_relation"]["event_user_equals_genesis_creator"] is True for r in entries),
        "entry_creator_identity_known_count": sum(r["entry_creator_relation"]["creator_identity_known_from_authenticated_CreateEvent"] for r in entries),
        "prefix_query_curve_resolution_sources": dict(curve_sources),
        "entry_index_missing": sum(r["transaction_index"] is None for r in entries),
        "same_slot_order_unresolved_events": sum(r["same_slot_index_order_unresolved_event_count"] for r in entries),
        "matched_control_assignments": len(controls), "matched_unique_control_signatures": len(unique_controls),
        "target_control_feature_comparison": target_control_comparison(entries, controls),
        "per_wallet": per_wallet,
    }


def markdown_report(document: dict[str, Any]) -> str:
    sample = document["summary"]
    run = document["run"]
    lines = [
        "# 22-wallet receipt-authenticated entry patterns",
        "",
        f"This is a descriptive prefix study of **{sample['selected_entry_count']} frozen target buys** across **{sample['distinct_target_wallets_with_selected_entries']} wallets** and **{sample['unique_target_mints']} mints**. It reports observable reserve, order-flow and preceding-wallet states; it does not estimate profitability, backtest a copy policy, or prove that a later wallet copied an earlier one.",
        "",
        f"Sample limit: up to **{run['per_wallet_limit']} distinct mints per wallet** (fixed-hash selection, independent of outcome). Finalized RPC cutoff: slot {run['freeze'].get('slot')} at blockTime {run['freeze'].get('blockTime')} ({run['freeze'].get('blockTime_utc') or run['freeze'].get('utc')}).",
        "",
        "## Coverage and authentication",
        "",
        f"- Successful SOL-quoted Pump trades are decoded with the strict IDL-discriminator and successful invocation-ancestry decoder; target identity is `TradeEvent.user`, kept separate from fee payer.",
        f"- Authenticated creation was found in **{sample['prefix_genesis_found']}** prefixes and missing in **{sample['prefix_genesis_missing']}**. A two-page cap means missing genesis is incomplete history, not evidence of a newly created token.",
        f"- Prefixes used official IDL instruction-to-curve mapping for **{sample['prefix_query_curve_resolution_sources'].get('official_idl_account_order', 0)}** entries and mint-address fallback for **{sample['prefix_query_curve_resolution_sources'].get('mint_address_fallback', 0)}**; fallback histories can be less complete if the mint address did not index curve trades.",
        f"- Entry pre/post reserves are reconstructed from the exact authenticated event SOL/token inputs. The independent last-prior-event continuity check matched real SOL, virtual SOL and virtual-token reserves in **{sample['last_prior_state_all_three_reserves_continuity_passed']}/{sample['last_prior_state_all_three_reserves_continuity_checked']}** checked prefixes.",
        f"- Same-prefix controls produced **{sample['matched_control_assignments']} target-control matches** over **{sample['matched_unique_control_signatures']} unique control signatures**. Matches are not independent observations; controls are selected by the stated prior-time/reserve window.",
        "- Same-second transactions are never ordered by blockTime: all prefix decisions use `(slot, transactionIndex)`. Same-slot rows lacking either index are excluded from the strictly prior set and counted as ambiguous.",
        "",
        "## Per-wallet clues",
        "",
        "Median reserve and flow values summarize only selected, covered prefixes; drawdown is against the highest authenticated pre-entry marginal-reserve price visible in that prefix. These are descriptive state ratios, not executable price returns.",
        "",
        "| Wallet | Selected | Genesis found | Median pre real SOL | Median buy SOL | Median observed drawdown | Median outside net SOL, last 5 slots | Median unique buyers, last 5 slots | Two-buyer recoveries |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in sample["per_wallet"]:
        def fmt(key, digits=2, suffix=""):
            value = item.get(key)
            return "—" if value is None else f"{value:.{digits}f}{suffix}"
        lines.append(f"| {item['name']} | {item['selected']} | {item['genesis_found']}/{item['selected']} | {fmt('median_pre_real_sol')} | {fmt('median_entry_sol_input')} | {fmt('median_observed_drawdown_pct', 1, '%')} | {fmt('median_outside_net_sol_last5slots')} | {fmt('median_unique_outside_buyers_last5slots', 1)} | {item['two_buyer_recovery_count']}/{item['two_buyer_recovery_n']} |")
    lines += [
        "",
        "## Same-prefix target/control feature comparison",
        "",
        "Controls are prior, non-target and noncreator single-event buys from the same queried prefix, within 32 slots and within ±20% of the target's pre-entry real-SOL reserve. Their features are measured causally before each control using the same slot-based windows; no control outcome profitability is calculated.",
        "",
        "| Sample | Observations | Median outside net SOL, last 5 slots | Median unique outside buyers, last 5 slots | Median observed drawdown | Current KOL buyers in last 5 slots | Current Tracked16 buyers in last 5 slots | Prior atomic group sides (buy / sell / mixed / none) |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    comparison = sample["target_control_feature_comparison"]
    for label, key in (("Target entries", "targets"), ("Matched controls", "same_prefix_controls")):
        item = comparison[key]
        count = item.get("entry_count", item.get("assignment_count", 0))
        kol = item["current_kol_buyer_present_last5slots"]
        tracked = item["current_tracked16_buyer_present_last5slots"]
        sides = item["immediate_prior_trade_group_side_counts"]["counts"]
        def med(key_name, digits=2, suffix=""):
            value = item[key_name]["median"]
            return "—" if value is None else f"{value:.{digits}f}{suffix}"
        side_summary = f"{sides.get('buy', 0)} / {sides.get('sell', 0)} / {sides.get('mixed_atomic_group', 0)} / {sides.get('none', 0)}"
        lines.append(f"| {label} | {count} | {med('median_outside_net_sol_last5slots')} | {med('median_unique_outside_buyers_last5slots', 1)} | {med('median_observed_drawdown_pct', 1, '%')} | {kol['count']}/{kol['n']} | {tracked['count']}/{tracked['n']} | {side_summary} |")
    lines += [
        "",
        "This comparison is descriptive and sample-conditioned; control assignments from one mint can overlap across target entries. Current roster membership is exploratory and does not prove historical knowledge.",
    ]
    linked = [row for row in document["coverage"] if row.get("other_event_user_trade_event_count_in_target_payer_or_signer_transactions", 0)]
    if linked:
        lines += [
            "",
            "## Payer/signer-linked receipt observations",
            "",
            "These are successful authenticated Pump events in target-wallet transactions where the target was fee payer or signer but a different `TradeEvent.user` executed the trade. They are recorded separately from target entry candidates and do not establish common ownership or copying.",
            "",
            "| Target label | Target payer txs | Target signer txs | Other-user trade events | Distinct other event users |",
            "|---|---:|---:|---:|---:|",
        ]
        for row in linked:
            lines.append(f"| {row['name']} | {row['target_as_fee_payer_successful_trade_tx_count']} | {row['target_as_signer_successful_trade_tx_count']} | {row['other_event_user_trade_event_count_in_target_payer_or_signer_transactions']} | {row['other_event_user_distinct_addresses_in_target_payer_or_signer_transactions']} |")
    linked_sample = document.get("bcnz_payer_linked_child_sample")
    if linked_sample:
        link_cov = linked_sample["coverage"]
        link_summary = linked_sample["summary"]
        child_counts: dict[str, dict[str, Any]] = {}
        for row in linked_sample["entries"]:
            child = row["event_user"]
            item = child_counts.setdefault(child, {"entries": 0, "genesis_found": 0})
            item["entries"] += 1
            item["genesis_found"] += int(row["genesis"]["found"])
        lines += [
            "",
            "### Bcnz payer-linked child-user entry prefixes",
            "",
            f"The parent payer/signer transaction window contains **{link_cov['authenticated_nonparent_sol_pump_buy_events']}** authenticated SOL Pump buy events across **{link_cov['distinct_mints']} mints** and **{link_cov['distinct_child_event_users']} child event users**. An outcome-blind hash selected **{link_summary['selected_entry_count']} distinct-mint entries**, each with its own causal pre-entry prefix; they are not counted as bcnz's own `TradeEvent.user` buys.",
            f"In the selected linked sample, the parent is a transaction signer in **{sum(r['linked_parent_relationship']['parent_is_signer'] for r in linked_sample['entries'])}/{len(linked_sample['entries'])}**, the authenticated child event user is a signer in **{sum(r['linked_parent_relationship']['event_user_is_signer'] for r in linked_sample['entries'])}/{len(linked_sample['entries'])}**, and the parent appears as parsed nonce authority in **{sum(r['linked_parent_relationship']['parent_is_parsed_nonce_authority'] for r in linked_sample['entries'])}/{len(linked_sample['entries'])}**. These are transaction-structure associations, not ownership evidence.",
            "",
            "| Authenticated child event user | Selected prefixes | Genesis found |",
            "|---|---:|---:|",
        ]
        for address, item in sorted(child_counts.items(), key=lambda kv: (-kv[1]["entries"], kv[0])):
            lines.append(f"| {address} | {item['entries']} | {item['genesis_found']}/{item['entries']} |")
    supplement = document.get("successful_history_supplement")
    if supplement:
        sup = supplement["summary"]
        lines += [
            "",
            "## Separate succeeded-history extension",
            "",
            f"A separate outcome-blind extension adds **{sup['selected_entry_count']} entries** across **{sup['distinct_target_wallets_with_selected_entries']} wallets** from succeeded-only 21-day histories. It fills each wallet only up to the overall 24-distinct-mint cap, excluding mints already in the recent250 sample. These are separate from the primary recent-receipt cohort, and source histories are page-capped.",
            "",
            "| Wallet | Extension entries | Authenticated distinct buy mints in fetched history | Genesis found | History rows | 10-page cap reached |",
            "|---|---:|---:|---:|---:|---|",
        ]
        sup_cov = {row["address"]: row for row in supplement["coverage"]}
        for item in sup["per_wallet"]:
            coverage_row = sup_cov[item["address"]]
            if not item["selected"] and not coverage_row["pages"]:
                continue
            lines.append(f"| {item['name']} | {item['selected']} | {coverage_row['distinct_authenticated_buy_mints']} | {item['genesis_found']}/{item['selected']} | {coverage_row['raw_rows']} | {'yes' if coverage_row['page_cap_truncated'] else 'no'} |")
        lines += [
            "",
            "The succeeded-only extension excludes failed transactions by request design. Capped pages bound the age and token diversity observed, so its counts do not represent wallet lifetime activity.",
        ]
    lines += [
        "",
        "## Entry mechanics and copy clues",
        "",
        "The JSON preserves each entry's immediate prior atomic curve transaction group, exact SOL input, pre/post real-SOL reserves, marginal spot ratio, observed peak drawdown, last 1/5/20-slot outside flows, distinct buyer/seller counts, current KOL/Tracked16 roster presence and prior target-wallet participation at lags 0/1/2/5/20. The two-buyer recovery flag requires two distinct noncreator wallets to make separate >=0.05 SOL SOL-quoted buys within two slots after the latest outside sell and before the target entry. It is a diagnostic only.",
        "Current KOL/Tracked16 addresses present in a target transaction's account keys are recorded as account references only; a reference does not establish a trade, signal, copy or ownership relationship. Entries whose authenticated `TradeEvent.user` equals the `CreateEvent` creator are flagged so deployer buys can be separated from follower behavior.",
        "",
        "A repeated predecessor, co-occurring wallet or positive lead-lag count is only an association. Public receipts do not reveal private observation time, intent, funding relationship, shared signals, or whether a follower independently reached the same decision. The current `kol_wallets.txt` and `tracked_wallets.txt` snapshots are exploratory labels, not proof they were historically known; observed token buyers are receipt-authenticated addresses, not verified independent people.",
        "",
        "The matched controls are non-target, noncreator single-event Pump buy transactions from the same observed prefix, strictly before the selected entry, within 32 slots and at pre-entry real-SOL reserve within +/-20%. Each matching state is counted; repeated use across entry matches is disclosed and does not increase the number of unique opportunities.",
        "",
        "## Result card",
        "",
        f"- Engine: strict `research/day_general_20261004/helpers/decoder.py`; no replay engine invoked.",
        f"- Data: frozen 22-address recent-receipt set; up to two finalized Alchemy `getTransactionsForAddress` pages of 500 per selected mint/curve, query cutoff no later than entry blockTime and frozen blockTime.",
        f"- Selection: sha256(`wallet + NUL + signature`), one deterministically chosen transaction per mint, then up to {run['per_wallet_limit']} distinct mints per wallet; no outcomes used.",
        "- Central placement, PnL, and profitability verdict: not applicable; no hypothetical entries/exits are simulated.",
        "- Known coverage risks: wallet source histories are capped at 250 receipts; each token prefix at 1,000 receipts; history may begin after creation; blockTime has one-second precision; transactionIndex is needed for same-slot order.",
        "- Status: exploratory descriptive evidence only; no copy edge or private wallet rule established.",
        "",
        "## What I would investigate if data and tooling were unconstrained",
        "",
        "Collect wallet decision/intent, received-signal, signing, send, route, failure and landing timestamps; complete creation-through-migration histories for every selected and matched-control mint; and pre-entry funding/acquisition relationships with account-owner custody. Freeze a small entry family on a development window, then measure fee-inclusive finite-size post-signal opportunity and actual migration continuation on untouched 2–3 week data with the approved central placement model.",
        "",
    ]
    return "\n".join(lines)


def run(limit: int, fetch: bool = True, include_history_supplement: bool = False) -> dict[str, Any]:
    freeze = freeze_info()
    if freeze.get("error"):
        raise ValueError(freeze["error"])
    candidates, coverage = recent_candidates(limit, freeze)
    target_set = set(coverage["target_addresses"])
    roster = roster_snapshot()
    entries = []
    prefix_audits = []
    for i, candidate in enumerate(candidates, 1):
        if not isinstance(candidate.get("block_time"), int) or not isinstance(candidate.get("slot"), int):
            prefix_audits.append({"mint": candidate["mint"], "signature": candidate["signature"], "status": "missing_entry_time_or_slot"})
            continue
        path = prefix_path(candidate)
        if path.exists():
            prefix = read_gzip_json(path)
            prefix_cache = True
        elif fetch:
            try:
                prefix = fetch_prefix(candidate, freeze)
                write_gzip_json(path, prefix)
                prefix_cache = False
            except Exception as error:
                prefix_audits.append({"mint": candidate["mint"], "signature": candidate["signature"],
                                      "status": "prefix_fetch_error", "error": f"{type(error).__name__}: {error}"})
                print(f"prefix {i}/{len(candidates)} ERROR {candidate['mint']}: {type(error).__name__}", flush=True)
                continue
        else:
            prefix_audits.append({"mint": candidate["mint"], "signature": candidate["signature"], "status": "prefix_missing"})
            continue
        result = analyze_candidate(candidate, prefix, roster, target_set)
        entries.append(result)
        prefix_audits.append({"mint": candidate["mint"], "signature": candidate["signature"],
                              "status": "analyzed", "cache_hit": prefix_cache,
                              "genesis_found": result["genesis"]["found"],
                              "prefix_transactions": prefix["transaction_count"],
                              "controls": result["same_prefix_preceding_non_target_controls"]["match_assignment_count"]})
        if i % 10 == 0 or i == len(candidates):
            print(f"prefixes {i}/{len(candidates)}; analyzed={len(entries)}", flush=True)
    summary = summarize(entries, coverage["wallet_coverage"])
    supplemental_document = None
    linked_child_document = None
    if include_history_supplement:
        extension_candidates, extension_coverage = successful_history_extension_candidates(limit, freeze, candidates)
        extension_entries = []
        extension_audits = []
        for i, candidate in enumerate(extension_candidates, 1):
            path = prefix_path(candidate)
            if path.exists():
                prefix = read_gzip_json(path)
                prefix_cache = True
            elif fetch:
                try:
                    prefix = fetch_prefix(candidate, freeze)
                    write_gzip_json(path, prefix)
                    prefix_cache = False
                except Exception as error:
                    extension_audits.append({"mint": candidate["mint"], "signature": candidate["signature"],
                                             "status": "prefix_fetch_error", "error": f"{type(error).__name__}: {error}"})
                    print(f"history prefix {i}/{len(extension_candidates)} ERROR {candidate['mint']}: {type(error).__name__}", flush=True)
                    continue
            else:
                extension_audits.append({"mint": candidate["mint"], "signature": candidate["signature"], "status": "prefix_missing"})
                continue
            result = analyze_candidate(candidate, prefix, roster, target_set)
            extension_entries.append(result)
            extension_audits.append({"mint": candidate["mint"], "signature": candidate["signature"],
                                     "status": "analyzed", "cache_hit": prefix_cache,
                                     "genesis_found": result["genesis"]["found"],
                                     "prefix_transactions": prefix["transaction_count"],
                                     "controls": result["same_prefix_preceding_non_target_controls"]["match_assignment_count"]})
            if i % 10 == 0 or i == len(extension_candidates):
                print(f"history prefixes {i}/{len(extension_candidates)}; analyzed={len(extension_entries)}", flush=True)
        supplemental_document = {
            "selection_scope": "Separate succeeded-only 21-day source, used only to fill wallets below their primary recent250 cap; primary sample mints excluded. Failed receipts are excluded by source request filter.",
            "coverage": extension_coverage, "prefix_audit": extension_audits,
            "summary": summarize(extension_entries, extension_coverage), "entries": extension_entries,
        }
        linked_candidates, linked_coverage = payer_linked_child_candidates(limit, freeze)
        linked_entries = []
        linked_audits = []
        for i, candidate in enumerate(linked_candidates, 1):
            path = prefix_path(candidate)
            if path.exists():
                prefix = read_gzip_json(path)
                prefix_cache = True
            elif fetch:
                try:
                    prefix = fetch_prefix(candidate, freeze)
                    write_gzip_json(path, prefix)
                    prefix_cache = False
                except Exception as error:
                    linked_audits.append({"mint": candidate["mint"], "signature": candidate["signature"],
                                          "status": "prefix_fetch_error", "error": f"{type(error).__name__}: {error}"})
                    print(f"payer-linked prefix {i}/{len(linked_candidates)} ERROR {candidate['mint']}: {type(error).__name__}", flush=True)
                    continue
            else:
                linked_audits.append({"mint": candidate["mint"], "signature": candidate["signature"], "status": "prefix_missing"})
                continue
            result = analyze_candidate(candidate, prefix, roster, target_set)
            result["linked_parent_relationship"] = {
                "parent_wallet": candidate["linked_parent_wallet"],
                "parent_is_signer": candidate["linked_parent_is_signer"],
                "parent_is_parsed_nonce_authority": candidate["linked_parent_is_parsed_nonce_authority"],
                "event_user_is_signer": candidate["event_user_is_signer"],
                "event_user": candidate["linked_event_user"],
                "related_native_transfers": candidate["related_native_transfers"],
                "association_only": True,
            }
            linked_entries.append(result)
            linked_audits.append({"mint": candidate["mint"], "signature": candidate["signature"],
                                  "event_user": candidate["user"], "status": "analyzed", "cache_hit": prefix_cache,
                                  "genesis_found": result["genesis"]["found"],
                                  "prefix_transactions": prefix["transaction_count"],
                                  "controls": result["same_prefix_preceding_non_target_controls"]["match_assignment_count"]})
            if i % 10 == 0 or i == len(linked_candidates):
                print(f"payer-linked prefixes {i}/{len(linked_candidates)}; analyzed={len(linked_entries)}", flush=True)
        linked_summary_coverage = [{"address": linked_coverage.get("parent_wallet"),
                                    "name": linked_coverage.get("parent_name", "payer-linked event users"),
                                    "status": linked_coverage.get("status"),
                                    "recent_receipt_count": linked_coverage.get("receipt_count", 0),
                                    "auth_successful_sol_pump_buy_events": linked_coverage.get("authenticated_nonparent_sol_pump_buy_events", 0),
                                    "distinct_authenticated_buy_mints": linked_coverage.get("distinct_mints", 0),
                                    "selected_distinct_mints": linked_coverage.get("selected_distinct_mints", 0)}]
        linked_child_document = {
            "coverage": linked_coverage, "prefix_audit": linked_audits,
            "summary": summarize(linked_entries, linked_summary_coverage), "entries": linked_entries,
        }
    run_info = {
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "per_wallet_limit": limit, "target_wallet_count": len(coverage["target_addresses"]),
        "freeze": freeze,
        "selection": "Authenticate successful SOL-quoted Pump TradeEvent where event.user is target wallet; per mint retain entry with minimum sha256(wallet + NUL + signature); order mints by hash; take first N. Outcome-independent.",
        "prefix_request": {"method": "Alchemy getTransactionsForAddress", "transactionDetails": "full", "encoding": "jsonParsed", "maxSupportedTransactionVersion": 1, "sortOrder": "desc", "limit": 500, "commitment": "finalized", "filter": "blockTime <= min(entry.blockTime, frozen blockTime)", "max_pages": 2},
        "time_ordering": "Only (slot, transactionIndex) determines same-slot order; blockTime is a cutoff/age clock only.",
        "roster_snapshots": {"kol_count": roster["kol_count"], "tracked_count": roster["tracked_count"], "kol_tracked_overlap": roster["kol_tracked_overlap"]},
        "supplemental_history_included": include_history_supplement,
        "supplemental_history_source": "raw_wallets/successful_history/; succeeded-only 21-day filters; up to10 pages/wallet; outcomes not used in selection" if include_history_supplement else None,
        "profitability_claim": False, "backtest": False,
    }
    document = {"schema_version": 1, "run": run_info,
                "coverage": coverage["wallet_coverage"], "prefix_audit": prefix_audits,
                "summary": summary, "entries": entries}
    if supplemental_document is not None:
        document["successful_history_supplement"] = supplemental_document
    if linked_child_document is not None:
        document["bcnz_payer_linked_child_sample"] = linked_child_document
    OUTPUT_JSON.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    OUTPUT_MD.write_text(markdown_report(document), encoding="utf-8")
    print(f"saved {len(entries)} entries to {OUTPUT_JSON}; genesis={summary['prefix_genesis_found']}/{len(entries)} controls={summary['matched_control_assignments']}", flush=True)
    return document


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=8, help="outcome-blind distinct mint cap per wallet")
    parser.add_argument("--no-fetch", action="store_true", help="analyze only retained prefixes")
    parser.add_argument("--include-history-supplement", action="store_true", help="fill below-cap wallets from the separate succeeded-only 21-day histories")
    args = parser.parse_args()
    if not 1 <= args.limit <= 24:
        raise SystemExit("--limit must be in [1,24]")
    run(args.limit, fetch=not args.no_fetch, include_history_supplement=args.include_history_supplement)


KOL_ROSTER = address_set(KOL_PATH)
TRACKED_ROSTER = active_tracked_set()


if __name__ == "__main__":
    main()
