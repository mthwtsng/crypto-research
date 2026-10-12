"""Read-only reuse of the frozen first-hour local curve source.

The manifest is a prefilter. Queue construction reads only bounded gzip
headers; source import reads the selected tape and issues a coverage
certificate only when the frozen collector contract, real creation, and
canonical receipt order are verified. Nonterminal tapes remain fixed first-hour
observations. This module never calls RPC and never writes into the frozen tree.
"""
from __future__ import annotations

import collections
import datetime as dt
import gzip
import hashlib
import importlib.util
import json
import pathlib
import sys
from functools import lru_cache
from typing import Any

sys.dont_write_bytecode = True

ROOT = pathlib.Path(__file__).resolve().parents[2]
SOURCE_ROOT = ROOT / "research" / "frozen_21day_validation_20261008"
MANIFEST_PATH = SOURCE_ROOT / "ACTIVE_COINS_MANIFEST.json"
RAW_DIR = SOURCE_ROOT / "raw_curves"
SOURCE = "local_active_manifest_prefilter"

START_TIME = int(dt.datetime(2026, 8, 18, tzinfo=dt.timezone.utc).timestamp())
EARLY_END_EXCLUSIVE = int(dt.datetime(2026, 9, 8, tzinfo=dt.timezone.utc).timestamp())
OVERALL_END_EXCLUSIVE = int(dt.datetime(2026, 10, 1, tzinfo=dt.timezone.utc).timestamp())

HEADER_MAX_CHARS = 131_072
HEADER_CHUNK_CHARS = 4_096
_FROZEN_SOURCES = SOURCE_ROOT / "frozen_sources"
_COLLECTOR_REL = "research/frozen_21day_validation_20261008/collect_validation.py"
_DECODER_REL = "research/day_general_20261004/helpers/decoder.py"
_IDL_REL = "research/day_general_20261004/helpers/OFFICIAL_PUMP_IDL.json"

COVERAGE_POLICY = (
    "Queue uses bounded gzip header metadata only. Import requires the pinned "
    "frozen all-status first-hour collector contract, a decoded genuine "
    "creation, and unique canonical slot/index order. A complete first-hour "
    "observation is eligible without migration or terminal evidence; it is "
    "not labeled full-lifetime coverage. Authenticated migrations retain the "
    "migration+240 coverage requirement. No curve RPC requery is performed."
)


class LocalSourceCoverageError(ValueError):
    """A local tape cannot prove the required source/observation coverage."""

    def __init__(self, reason: str, details: dict[str, Any] | None = None):
        self.reason = reason
        self.details = details or {}
        super().__init__(reason if not self.details else f"{reason}: {self.details}")


def _sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_header_prefix(path: pathlib.Path, max_chars: int = HEADER_MAX_CHARS) -> tuple[dict[str, Any], int]:
    """Decode top-level header fields and stop before the transactions value."""
    decoder = json.JSONDecoder()
    fields: dict[str, Any] = {}
    buf = ""
    pos = 0
    chars_read = 0

    with gzip.open(path, "rt", encoding="utf-8") as stream:
        def refill() -> None:
            nonlocal buf, chars_read
            remaining = max_chars - chars_read
            if remaining <= 0:
                raise ValueError("gzip_header_prefix_limit")
            chunk = stream.read(min(HEADER_CHUNK_CHARS, remaining))
            if not chunk:
                raise ValueError("gzip_header_ended_before_transactions")
            chars_read += len(chunk)
            buf += chunk

        def skip_space(index: int) -> int:
            while True:
                while index < len(buf) and buf[index].isspace():
                    index += 1
                if index < len(buf):
                    return index
                refill()

        def decode_value(index: int) -> tuple[Any, int]:
            while True:
                try:
                    return decoder.raw_decode(buf, index)
                except json.JSONDecodeError:
                    if chars_read >= max_chars:
                        raise ValueError("gzip_header_prefix_limit")
                    refill()

        pos = skip_space(pos)
        if buf[pos] != "{":
            raise ValueError("gzip_source_not_json_object")
        pos += 1

        while True:
            pos = skip_space(pos)
            if buf[pos] == "}":
                raise ValueError("gzip_header_missing_transactions")
            key, pos = decode_value(pos)
            if not isinstance(key, str):
                raise ValueError("gzip_header_key_not_string")
            pos = skip_space(pos)
            if buf[pos] != ":":
                raise ValueError("gzip_header_missing_colon")
            pos = skip_space(pos + 1)
            if key == "transactions":
                required = {"mint", "creation_metadata", "requested_end_time"}
                missing = sorted(required - fields.keys())
                if missing:
                    raise ValueError(f"gzip_header_missing_fields:{','.join(missing)}")
                return fields, chars_read
            value, pos = decode_value(pos)
            if key in fields:
                raise ValueError(f"gzip_header_duplicate_key:{key}")
            fields[key] = value
            pos = skip_space(pos)
            if buf[pos] == ",":
                pos += 1
                continue
            if buf[pos] == "}":
                raise ValueError("gzip_header_missing_transactions")
            raise ValueError("gzip_header_invalid_separator")


def _manifest_rows(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    rows = manifest.get("coins")
    if not isinstance(rows, list):
        raise ValueError("active_manifest_coins_not_list")
    declared = manifest.get("total_active")
    if declared is not None and declared != len(rows):
        raise ValueError("active_manifest_count_mismatch")
    return rows


def _round_robin_days(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_day: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in rows:
        by_day[row["time_stratum_utc_day"]].append(row)
    days = sorted(by_day)
    for day in days:
        by_day[day].sort(key=lambda row: (row["creation_time"], row["mint"]))
    ordered: list[dict[str, Any]] = []
    max_count = max((len(by_day[day]) for day in days), default=0)
    for index in range(max_count):
        for day in days:
            if index < len(by_day[day]):
                ordered.append(by_day[day][index])
    return ordered


def load_local_candidates(
    manifest_path: str | pathlib.Path = MANIFEST_PATH,
    raw_dir: str | pathlib.Path = RAW_DIR,
) -> list[dict[str, Any]]:
    """Return local manifest candidates, early window first, without loading tapes."""
    manifest_path = pathlib.Path(manifest_path)
    raw_dir = pathlib.Path(raw_dir)
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    rows = _manifest_rows(manifest)
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    seen: set[str] = set()
    early: list[dict[str, Any]] = []
    later: list[dict[str, Any]] = []
    outside_window = 0

    for entry in rows:
        mint = entry.get("mint")
        if not isinstance(mint, str) or not mint or "/" in mint or "\\" in mint:
            raise ValueError("active_manifest_invalid_mint")
        if mint in seen:
            raise ValueError(f"active_manifest_duplicate_mint:{mint}")
        seen.add(mint)
        expected_name = mint + ".json.gz"
        if entry.get("file") != expected_name:
            raise ValueError(f"active_manifest_filename_mismatch:{mint}")
        local_path = raw_dir / expected_name
        if not local_path.is_file():
            raise ValueError(f"active_manifest_raw_file_missing:{mint}")
        header, prefix_chars = _read_header_prefix(local_path)
        creation = header.get("creation_metadata")
        if not isinstance(creation, dict) or creation.get("mint") != mint or header.get("mint") != mint:
            raise ValueError(f"active_manifest_source_mint_mismatch:{mint}")
        creation_time = creation.get("timestamp")
        requested_end = header.get("requested_end_time")
        if not isinstance(creation_time, int) or not isinstance(requested_end, int):
            raise ValueError(f"active_manifest_time_metadata_invalid:{mint}")
        if not START_TIME <= creation_time < OVERALL_END_EXCLUSIVE:
            outside_window += 1
            continue

        created = dt.datetime.fromtimestamp(creation_time, tz=dt.timezone.utc)
        day = created.date().isoformat()
        candidate = {
            "mint": mint,
            "creation": creation,
            "creation_metadata": creation,
            "creation_time": creation_time,
            "creation_slot": creation.get("creation_slot"),
            "source": SOURCE,
            "local_raw_path": str(local_path.resolve()),
            "local_raw_file_size_bytes": local_path.stat().st_size,
            "local_source_root": str(raw_dir.parent.resolve()),
            "manifest_path": str(manifest_path.resolve()),
            "manifest_sha256": manifest_sha,
            "manifest_total_raw_metadata": manifest.get("total_raw"),
            "manifest_total_active": manifest.get("total_active"),
            "manifest_prefilter": {
                "total_transactions": entry.get("total_transactions"),
                "peak_reserve_sol": entry.get("peak_reserve_sol"),
                "unique_buyers": entry.get("unique_buyers"),
                "creator": entry.get("creator"),
                "filter_definition": manifest.get("filter"),
                "trust": "prefilter_snapshot_only; metrics are not used for source coverage or qualification",
            },
            "raw_header": {
                "requested_end_time": requested_end,
                "decision_end_time": header.get("decision_end_time"),
                "source_coverage_metadata": header.get("coverage"),
                "bounded_prefix_chars_read": prefix_chars,
            },
            "time_stratum_utc_day": day,
            "time_stratum_utc_hour": created.hour,
            "queue_window": "early_aug18_sep07" if creation_time < EARLY_END_EXCLUSIVE else "later_sep08_sep30",
            "coverage_policy": COVERAGE_POLICY,
        }
        (early if creation_time < EARLY_END_EXCLUSIVE else later).append(candidate)

    queue = _round_robin_days(early) + _round_robin_days(later)
    for index, candidate in enumerate(queue):
        candidate["local_queue_order"] = index
        candidate["local_queue_window_rank"] = 0 if candidate["queue_window"] == "early_aug18_sep07" else 1
    # Internal diagnostics are kept in an attribute-like row field rather than
    # a separate on-disk queue artifact; the caller can recompute counts.
    if outside_window:
        for candidate in queue:
            candidate["manifest_rows_outside_overall_window"] = outside_window
    return queue


def _read_json_gzip(path: pathlib.Path) -> dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise LocalSourceCoverageError("local_source_not_json_object")
    return value


def _canonical_transactions(transactions: Any, mint: str, start: int, end: int) -> list[dict[str, Any]]:
    if not isinstance(transactions, list) or not transactions:
        raise LocalSourceCoverageError("local_source_transactions_missing")
    by_signature: dict[str, dict[str, Any]] = {}
    position_to_signature: dict[tuple[int, int], str] = {}
    for tx in transactions:
        try:
            signature = tx["transaction"]["signatures"][0]
            slot = tx["slot"]
            index = tx["transactionIndex"]
            block_time = tx["blockTime"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LocalSourceCoverageError("local_source_order_fields_missing") from exc
        if not isinstance(signature, str) or not signature:
            raise LocalSourceCoverageError("local_source_signature_invalid")
        if not all(isinstance(x, int) for x in (slot, index, block_time)):
            raise LocalSourceCoverageError("local_source_order_fields_not_integer")
        if slot < 0 or index < 0 or not start <= block_time < end:
            raise LocalSourceCoverageError("local_source_receipt_outside_requested_interval")
        if tx.get("meta") is None:
            raise LocalSourceCoverageError("local_source_receipt_metadata_missing")
        key = (slot, index)
        if key in position_to_signature:
            raise LocalSourceCoverageError("local_source_conflicting_transaction_index")
        if signature in by_signature:
            raise LocalSourceCoverageError("local_source_duplicate_signature")
        position_to_signature[key] = signature
        by_signature[signature] = tx
    ordered = sorted(by_signature.values(), key=lambda tx: (tx["slot"], tx["transactionIndex"]))
    if not ordered:
        raise LocalSourceCoverageError("local_source_transactions_missing")
    return ordered


def _collector_source_hashes(source_root: pathlib.Path) -> dict[str, Any]:
    freeze_path = source_root / "FREEZE.json"
    if not freeze_path.is_file():
        raise LocalSourceCoverageError("frozen_source_freeze_metadata_missing")
    freeze_bytes = freeze_path.read_bytes()
    freeze = json.loads(freeze_bytes)
    pin_map = freeze.get("execution_code_pin", {})
    expected = {
        _COLLECTOR_REL: pin_map.get(_COLLECTOR_REL),
        _DECODER_REL: pin_map.get(_DECODER_REL, freeze.get("hashes", {}).get(_DECODER_REL)),
        _IDL_REL: pin_map.get(_IDL_REL, freeze.get("hashes", {}).get(_IDL_REL)),
    }
    if any(not isinstance(value, str) or len(value) != 64 for value in expected.values()):
        raise LocalSourceCoverageError("frozen_source_required_hash_pin_missing")
    actual: dict[str, dict[str, str]] = {}
    for rel, pin in expected.items():
        active = ROOT / rel
        archived = _FROZEN_SOURCES / rel
        if not active.is_file() or not archived.is_file():
            raise LocalSourceCoverageError("frozen_source_code_copy_missing", {"path": rel})
        active_hash = _sha256_file(active)
        archived_hash = _sha256_file(archived)
        if active_hash != pin or archived_hash != pin:
            raise LocalSourceCoverageError(
                "frozen_source_code_hash_mismatch",
                {"path": rel, "expected": pin, "active": active_hash, "archived": archived_hash},
            )
        actual[rel] = {"sha256": active_hash, "archived_sha256": archived_hash}
    return {
        "freeze_sha256": hashlib.sha256(freeze_bytes).hexdigest(),
        "freeze_pinned_at": freeze.get("execution_pinned_at"),
        "code": actual,
        "collector_path": str((source_root / "collect_validation.py").resolve()),
        "archived_collector_path": str((_FROZEN_SOURCES / _COLLECTOR_REL).resolve()),
        "coverage_contract": (
            "collect_validation.history queries the bonding-curve address with status=None, "
            "blockTime gte creation_time and lt creation_time+3600; it returns only when the "
            "pagination token is absent, raises at the 500-page cap, validates each transaction "
            "index and time bound, and curve() saves only after history returns."
        ),
    }


@lru_cache(maxsize=2)
def _load_pinned_decoder(source_root_string: str):
    source_root = pathlib.Path(source_root_string)
    hashes = _collector_source_hashes(source_root)
    decoder_path = _FROZEN_SOURCES / _DECODER_REL
    spec = importlib.util.spec_from_file_location("local_active_seed_frozen_decoder", decoder_path)
    if spec is None or spec.loader is None:
        raise LocalSourceCoverageError("frozen_creation_decoder_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, hashes


def _migration_decoder(decoder: Any):
    path = ROOT / "research" / "amm_multiday_20261006" / "collect.py"
    if not path.is_file():
        raise LocalSourceCoverageError("authenticated_migration_decoder_unavailable")
    spec = importlib.util.spec_from_file_location("local_active_seed_migration_decoder", path)
    if spec is None or spec.loader is None:
        raise LocalSourceCoverageError("authenticated_migration_decoder_unavailable")
    prior = sys.modules.get("decoder")
    sys.modules["decoder"] = decoder
    try:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        if prior is None:
            sys.modules.pop("decoder", None)
        else:
            sys.modules["decoder"] = prior
    return module


def _decoded_migrations(tx: dict[str, Any], mint: str, curve: str, mig: Any) -> list[dict[str, Any]]:
    if tx.get("meta", {}).get("err") is not None:
        return []
    found: dict[tuple[str, str, str], dict[str, Any]] = {}
    for instruction in mig.allix(tx):
        if instruction.get("programId") != mig.D.PUMP:
            continue
        spec = mig.MIG.get(mig.raw(instruction.get("data", ""))[:8])
        if not spec or spec.get("name") not in ("migrate", "migrate_v2"):
            continue
        accounts = dict(zip([entry["name"] for entry in spec["accounts"]], instruction.get("accounts", [])))
        if accounts.get("withdraw_authority") != mig.AUTH:
            raise LocalSourceCoverageError("migration_withdraw_authority_unverified")
        if accounts.get("pump_amm") != mig.AMM:
            continue
        observed_mint = accounts.get("mint", accounts.get("base_mint"))
        if observed_mint != mint:
            continue
        observed_curve = accounts.get("bonding_curve")
        if not observed_curve or observed_curve != curve:
            raise LocalSourceCoverageError("migration_curve_binding_mismatch")
        signature = tx["transaction"]["signatures"][0]
        key = (signature, observed_mint, accounts.get("pool", ""))
        found[key] = {
            "mint": observed_mint,
            "pool": accounts.get("pool"),
            "bonding_curve": observed_curve,
            "quote_mint": accounts.get("quote_mint", accounts.get("wsol_mint")),
            "signature": signature,
            "slot": tx["slot"],
            "index": tx["transactionIndex"],
            "time": tx["blockTime"],
            "instruction": spec["name"],
            "withdraw_authority": accounts.get("withdraw_authority"),
            "pump_amm": accounts.get("pump_amm"),
            "base_vault": accounts.get("pool_base_token_account"),
            "quote_vault": accounts.get("pool_quote_token_account"),
            "creator": accounts.get("user"),
            "authentication": "successful transaction; official Pump IDL migrate/migrate_v2; configured withdraw authority and Pump AMM; mint, pool, bonding_curve instruction account binding",
        }
    return list(found.values())


def _creation_events(tx: dict[str, Any], decoder: Any) -> list[dict[str, Any]]:
    if tx.get("meta", {}).get("err") is not None:
        return []
    return decoder.creations(tx)


def _terminal_event(transactions: list[dict[str, Any]], mint: str, decoder: Any) -> dict[str, Any] | None:
    terminals = []
    for tx in transactions:
        if tx.get("meta", {}).get("err") is not None:
            continue
        for event in decoder.events(tx):
            if event.get("mint") == mint and event.get("quote_is_sol") and event.get("real_token_reserves") == 0:
                terminals.append(
                    {
                        "signature": tx["transaction"]["signatures"][0],
                        "slot": tx["slot"],
                        "index": tx["transactionIndex"],
                        "time": tx["blockTime"],
                        "remaining_real_token_reserves": 0,
                        "proof": "successful, program-log-ancestry-validated official Pump TradeEvent with zero real token reserves",
                    }
                )
    return terminals[0] if terminals else None


def _verified_cached_custody(source_root: pathlib.Path, mint: str, base_transactions: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    extended_path = source_root / "custody" / "custody_extended" / f"{mint}.json.gz"
    audit_path = source_root / "prepare_audits" / f"{mint}.json"
    if not extended_path.is_file():
        return base_transactions, []
    if not audit_path.is_file():
        return base_transactions, [{"status": "ignored_unverified", "reason": "cached_custody_audit_missing", "source_path": str(extended_path)}]
    try:
        audit_bytes = audit_path.read_bytes()
        audit = json.loads(audit_bytes)
        evidence = audit.get("custody", {})
        if audit.get("mint") != mint or audit.get("status") != "prepared" or evidence.get("status") != "supported":
            return base_transactions, [{"status": "ignored_unverified", "reason": "cached_custody_audit_not_supported", "source_path": str(extended_path)}]
        extended = _read_json_gzip(extended_path)
        if extended.get("mint") != mint or not isinstance(extended.get("transactions"), list):
            return base_transactions, [{"status": "ignored_unverified", "reason": "cached_custody_mint_mismatch", "source_path": str(extended_path)}]
        original_signatures = {tx["transaction"]["signatures"][0] for tx in base_transactions}
        added = [tx for tx in extended["transactions"] if tx["transaction"]["signatures"][0] not in original_signatures]
        merged = base_transactions + added
        provenance = {
            "status": "reused_supported_local_account_repair",
            "source_path": str(extended_path.resolve()),
            "source_sha256": _sha256_file(extended_path),
            "audit_path": str(audit_path.resolve()),
            "audit_sha256": hashlib.sha256(audit_bytes).hexdigest(),
            "audit_custody_status": evidence.get("status"),
            "passes": evidence.get("passes", []),
            "added_signatures": [tx["transaction"]["signatures"][0] for tx in added],
            "added_receipts": len(added),
            "limit": "cached repair rows only; root must validate merged custody replay and block indexes",
        }
        return merged, [provenance]
    except (OSError, EOFError, json.JSONDecodeError, KeyError, TypeError):
        return base_transactions, [{"status": "ignored_unverified", "reason": "cached_custody_source_unreadable", "source_path": str(extended_path)}]


def import_source(candidate: dict[str, Any]) -> dict[str, Any]:
    """Return a collector-compatible local raw envelope or raise a skip reason.

    This function performs no network access and does not write the source or
    any copy. The caller owns any destination and should preserve
    ``source_provenance`` verbatim with the imported tape.
    """
    if candidate.get("source") != SOURCE:
        raise LocalSourceCoverageError("candidate_not_from_local_active_manifest")
    mint = candidate.get("mint")
    if not isinstance(mint, str) or not mint:
        raise LocalSourceCoverageError("candidate_mint_missing")
    source_root = pathlib.Path(candidate.get("local_source_root", SOURCE_ROOT)).resolve()
    raw_path = pathlib.Path(candidate.get("local_raw_path", "")).resolve()
    raw_dir = (source_root / "raw_curves").resolve()
    if raw_path.parent != raw_dir or raw_path.name != mint + ".json.gz" or not raw_path.is_file():
        raise LocalSourceCoverageError("candidate_local_raw_path_invalid")

    decoder, frozen_hashes = _load_pinned_decoder(str(source_root))
    migration_decoder = _migration_decoder(decoder)
    raw_sha = _sha256_file(raw_path)
    raw = _read_json_gzip(raw_path)
    if raw.get("mint") != mint or not isinstance(raw.get("creation_metadata"), dict):
        raise LocalSourceCoverageError("local_source_mint_or_creation_metadata_mismatch")
    metadata = raw["creation_metadata"]
    creation_time = metadata.get("timestamp")
    requested_end = raw.get("requested_end_time")
    if not isinstance(creation_time, int) or not isinstance(requested_end, int):
        raise LocalSourceCoverageError("local_source_time_metadata_invalid")
    if requested_end != creation_time + 3600:
        raise LocalSourceCoverageError("local_source_not_frozen_first_hour", {"requested_end_time": requested_end})
    if raw.get("decision_end_time") != creation_time + 1800:
        raise LocalSourceCoverageError("local_source_decision_boundary_mismatch")
    if not START_TIME <= creation_time < OVERALL_END_EXCLUSIVE:
        raise LocalSourceCoverageError("local_source_outside_requested_overall_window")
    if candidate.get("creation_time") != creation_time:
        raise LocalSourceCoverageError("candidate_creation_time_mismatch")

    transactions = raw.get("transactions")
    if not isinstance(transactions, list):
        raise LocalSourceCoverageError("local_source_transactions_missing")
    transactions, custody_sources = _verified_cached_custody(source_root, mint, transactions)
    ordered = _canonical_transactions(transactions, mint, creation_time, requested_end)
    creation_rows = [(tx, event) for tx in ordered for event in _creation_events(tx, decoder) if event.get("mint") == mint]
    if len(creation_rows) != 1:
        raise LocalSourceCoverageError("genuine_creation_count_not_one", {"count": len(creation_rows)})
    creation_tx, decoded_creation = creation_rows[0]
    creation_signature = creation_tx["transaction"]["signatures"][0]
    if creation_tx["blockTime"] != creation_time or decoded_creation.get("timestamp") != creation_time:
        raise LocalSourceCoverageError("genuine_creation_time_mismatch")
    compare_keys = (
        "mint",
        "bonding_curve",
        "user",
        "creator",
        "timestamp",
        "virtual_token_reserves",
        "virtual_sol_reserves",
        "real_token_reserves",
        "token_total_supply",
        "token_program",
        "is_mayhem_mode",
        "is_holder_reward",
        "quote_mint",
    )
    mismatches = [
        key for key in compare_keys
        if key in metadata and key in decoded_creation and metadata.get(key) != decoded_creation.get(key)
    ]
    required_creation = ("mint", "bonding_curve", "user", "virtual_token_reserves", "virtual_sol_reserves", "real_token_reserves")
    missing_creation = [key for key in required_creation if key not in decoded_creation]
    if mismatches or missing_creation:
        raise LocalSourceCoverageError("genuine_creation_metadata_mismatch", {"mismatches": mismatches, "missing": missing_creation})
    if creation_tx["slot"] < 0:
        raise LocalSourceCoverageError("genuine_creation_slot_invalid")

    migration_rows: list[dict[str, Any]] = []
    for tx in ordered:
        migration_rows.extend(_decoded_migrations(tx, mint, metadata["bonding_curve"], migration_decoder))
    unique_migrations = {(row["signature"], row["mint"], row["pool"]): row for row in migration_rows}
    if len(unique_migrations) > 1:
        raise LocalSourceCoverageError("multiple_authenticated_curve_migrations")
    migration = next(iter(unique_migrations.values()), None)
    if migration and migration["time"] < creation_time:
        raise LocalSourceCoverageError("authenticated_migration_precedes_creation")

    terminal = _terminal_event(ordered, mint, decoder)
    completion: dict[str, Any] | None = None
    if migration:
        completion = {
            "kind": "authenticated_migration",
            "time": migration["time"],
            "signature": migration["signature"],
            "slot": migration["slot"],
            "transaction_index": migration["index"],
        }
    elif terminal:
        completion = {"kind": "curve_terminal_completion", **terminal}
    else:
        completion = {
            "kind": "fixed_first_hour_observation",
            "time": requested_end - 1,
            "observation_end_time_exclusive": requested_end,
            "proof": "pinned all-status first-hour pagination exhausted; no migration or terminal completion decoded within the observed interval",
        }

    imported_end = requested_end - 1
    if migration:
        imported_end = migration["time"] + 240
        if imported_end > requested_end - 1:
            raise LocalSourceCoverageError(
                "local_source_post_migration_curve_interval_incomplete",
                {"required_through_time": imported_end, "covered_through_time": requested_end - 1},
            )
    imported_transactions = [tx for tx in ordered if tx["blockTime"] <= imported_end]
    imported_signatures = {tx["transaction"]["signatures"][0] for tx in imported_transactions}
    required_signatures = {creation_signature}
    if migration:
        required_signatures.add(migration["signature"])
    if not required_signatures.issubset(imported_signatures):
        raise LocalSourceCoverageError("local_import_boundary_dropped_required_receipt")

    source_provenance = {
        "source_kind": "frozen_first_hour_local_curve_tape",
        "source_path": str(raw_path),
        "source_sha256": raw_sha,
        "source_file_size_bytes": raw_path.stat().st_size,
        "source_date_utc": dt.datetime.fromtimestamp(creation_time, tz=dt.timezone.utc).isoformat(),
        "source_requested_end_time": requested_end,
        "imported_requested_end_time": imported_end,
        "curve_lifetime_complete": bool(migration or terminal),
        "curve_observation_complete": True,
        "curve_completion_kind": completion["kind"],
        "source_decision_end_time": raw["decision_end_time"],
        "source_manifest_path": candidate.get("manifest_path"),
        "source_manifest_sha256": candidate.get("manifest_sha256"),
        "source_manifest_prefilter": candidate.get("manifest_prefilter"),
        "collector_contract": frozen_hashes,
        "creation_decode": {
            "decoder_path": str((_FROZEN_SOURCES / _DECODER_REL).resolve()),
            "decoder_sha256": frozen_hashes["code"][_DECODER_REL]["sha256"],
            "signature": creation_signature,
            "slot": creation_tx["slot"],
            "transaction_index": creation_tx["transactionIndex"],
            "decoded_metadata_matches_source": True,
        },
        "receipt_order": {
            "method": "unique signatures and unique (slot, transactionIndex), sorted ascending",
            "source_index_present": True,
            "independent_finalized_block_index_check": "not performed by this read-only helper; root may check against its owned RPC cache",
            "source_transactions": len(ordered),
            "imported_transactions": len(imported_transactions),
        },
        "curve_completion": completion,
        "cached_custody_sources": custody_sources,
    }
    coverage = {
        "source": "frozen_local_collector_contract",
        "address": metadata["bonding_curve"],
        "exhausted": True,
        "lower_time": creation_time,
        "upper_time": requested_end - 1,
        "upper_time_exclusive": requested_end,
        "source_requested_end_time": requested_end,
        "requested_end_time": imported_end,
        "interval_semantics": "blockTime gte creation_time and lt requested_end_time",
        "pagination_completion": "inferred from retained successful output plus exact pinned collector; collector returns only at no pagination token and raises at page cap",
        "pages": None,
        "receipts": len(imported_transactions),
        "order_source": "frozen enhanced RPC transactionIndex; uniqueness checked locally",
        "independent_block_index_proof": False,
        "curve_complete_through_time": imported_end,
        "curve_lifetime_complete": bool(migration or terminal),
        "curve_observation_complete": True,
        "curve_completion_kind": completion["kind"],
        "source_file_sha256": raw_sha,
        "source_file_path": str(raw_path),
        "source_collector_sha256": frozen_hashes["code"][_COLLECTOR_REL]["sha256"],
    }
    envelope = dict(raw)
    envelope.update(
        mint=mint,
        creation_metadata=metadata,
        creation_signature=creation_signature,
        creation_time=creation_time,
        creation_slot=creation_tx["slot"],
        requested_end_time=imported_end,
        coverage=coverage,
        migration=migration,
        transactions=imported_transactions,
        custody_extensions=custody_sources,
        source_provenance=source_provenance,
        imported_from_local_source=True,
        local_import_version="local_active_seed_v1",
    )
    return envelope


def build_local_seed_report(
    output_path: str | pathlib.Path = pathlib.Path(__file__).resolve().parent / "LOCAL_SEED_REPORT.json",
    manifest_path: str | pathlib.Path = MANIFEST_PATH,
    raw_dir: str | pathlib.Path = RAW_DIR,
) -> dict[str, Any]:
    """Write a compact provenance/count report; never touches source files."""
    manifest_path = pathlib.Path(manifest_path)
    raw_dir = pathlib.Path(raw_dir)
    manifest = json.loads(manifest_path.read_text())
    queue = load_local_candidates(manifest_path, raw_dir)
    early = [row for row in queue if row["queue_window"] == "early_aug18_sep07"]
    later = [row for row in queue if row["queue_window"] == "later_sep08_sep30"]
    counts = collections.Counter(row["time_stratum_utc_day"] for row in queue)
    raw_count = sum(1 for path in raw_dir.glob("*.json.gz") if path.is_file())
    contract: dict[str, Any]
    try:
        contract = _collector_source_hashes(SOURCE_ROOT)
        contract_status = "pinned_collector_and_decoder_sources_match_freeze"
    except (LocalSourceCoverageError, OSError, json.JSONDecodeError) as exc:
        contract = {"error": str(exc)}
        contract_status = "source_contract_unverified"
    report = {
        "status": "local candidate queue prepared; source remains read-only; no RPC used",
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": {
            "manifest_path": str(manifest_path.resolve()),
            "manifest_sha256": _sha256_file(manifest_path),
            "manifest_rows": len(_manifest_rows(manifest)),
            "manifest_total_raw_metadata": manifest.get("total_raw"),
            "manifest_total_active": manifest.get("total_active"),
            "raw_curve_directory": str(raw_dir.resolve()),
            "raw_curve_files": raw_count,
            "manifest_filter": manifest.get("filter"),
            "filter_metrics_trust": "prefilter only; peak_reserve_sol may reflect decoder/venue contamination and is never treated as a verified curve metric",
            "collector_contract_status": contract_status,
            "collector_contract_provenance": contract,
            "frozen_source_mutations": 0,
        },
        "queue": {
            "source_label": SOURCE,
            "total_in_overall_window": len(queue),
            "early_window": {"utc_inclusive_dates": ["2026-08-18", "2026-09-07"], "end_exclusive": "2026-09-08T00:00:00Z", "count": len(early)},
            "later_window": {"utc_inclusive_dates": ["2026-09-08", "2026-09-30"], "end_exclusive": "2026-10-01T00:00:00Z", "count": len(later)},
            "counts_by_utc_creation_day": dict(sorted(counts.items())),
            "ordering": "early then later; round-robin one candidate per UTC day at each depth; within each day chronological by creation_time then mint",
            "header_read_policy": {"max_decompressed_chars": HEADER_MAX_CHARS, "chunk_chars": HEADER_CHUNK_CHARS, "stops_before": "transactions array"},
        },
        "import_contract": {
            "function": "import_source(candidate)",
            "returns": "collector-compatible raw envelope with original creation metadata/transactions plus coverage and source_provenance certificates",
            "coverage_required": ["pinned all-status pagination contract for the complete first-hour interval", "real unique creation decode", "unique canonical slot/transactionIndex ordering"],
            "nonterminal_first_hour_behavior": "accepted as a complete fixed first-hour observation with curve_lifetime_complete=false and curve_observation_complete=true; no lifetime completion is inferred",
            "migration_behavior": "authenticated local migration remains eligible only when curve history is covered through migration+240",
            "rpc_behavior": "no RPC calls; no curve requery",
            "block_index_limit": "index uniqueness/order is checked; independent finalized getBlock signature parity is left to root using existing/authorized cache",
            "cached_custody_behavior": "reuse a frozen custody_extended tape only when its per-mint audit says prepared and custody supported; retain source and audit hashes; caller must revalidate merged custody and block indices",
            "provenance_preserved": ["source compressed-file SHA-256", "manifest SHA-256", "creation UTC and slot/signature/index", "collector/decoder/IDL pinned hashes", "requested interval and coverage rule", "migration, terminal, or fixed-first-hour observation classification", "cached custody source/audit hashes when reused"],
        },
        "limitations": [
            "Manifest activity, peak-reserve, buyer-count fields are prefilter snapshots, not authenticated curve measurements.",
            "Queue construction does not load transaction arrays and does not certify any candidate's coverage.",
            "A first-hour nonterminal tape is complete only as a fixed first-hour observation; activity after that boundary and full curve lifetime remain unknown.",
            "The helper does not independently compare transactionIndex with finalized block signatures.",
        ],
    }
    output_path = pathlib.Path(output_path)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


if __name__ == "__main__":
    result = build_local_seed_report()
    print(json.dumps({"queue_count": result["queue"]["total_in_overall_window"], "early_count": result["queue"]["early_window"]["count"], "late_count": result["queue"]["later_window"]["count"]}, sort_keys=True))
