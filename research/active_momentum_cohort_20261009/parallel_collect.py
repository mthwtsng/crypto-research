"""Parallel, ordered, restartable coordinator for the active cohort collection.

Workers call the frozen ``collect_cohort.verify`` implementation.  Each worker
writes into a per-mint staging directory; only the single coordinator promotes
an admitted result into the canonical manifest and artifact directories.
"""
import sys
sys.dont_write_bytecode = True

import argparse
import concurrent.futures
import datetime
import fcntl
import hashlib
import json
import multiprocessing
import os
import pathlib
import re
import time
from typing import Any, Mapping, Sequence

import collect_cohort as C


P = pathlib.Path(__file__).resolve().parent
QUEUE_PATH = P / "CANDIDATE_QUEUE.json"
QUEUE_EXCLUSIONS_PATH = P / "CANDIDATE_QUEUE_EXCLUSIONS.json"
STATUS_PATH = P / "PARALLEL_STATUS.json"
EVENTS_PATH = P / "PARALLEL_OUTCOMES.jsonl"
STAGE_ROOT = P / "parallel_stage" / "candidates"
QUEUE_VERSION = 1
QUEUE_SALT = "active_cohort_v1"
RETRY_ATTEMPTS_PER_RUN = 3
STATUS_HEARTBEAT_SECONDS = 15

# Only explicit, source-backed verifier outcomes are final rejections.  Unknown
# errors remain retryable so a provider outage cannot be reported as parity
# failure.
DEFINITIVE_REASONS = (
    "local_source_not_eligible:",
    "creation_outside_requested_window",
    "unsupported_mode",
    "unsupported_quote_or_token_mode",
    "unsupported_quote",
    "unsupported_buy_instruction",
    "unsupported_custody_op",
    "unverified_custody",
    "creation_count_not_one",
    "multiple_migration_bindings",
    "creation_initial_reserves_mismatch",
    "no_curve_trades",
    "source_token_prebalance_mismatch",
    "source_token_postbalance_mismatch",
    "whole_source_parity",
    "block_order_signature_mismatch",
    "fewer_than_50_successful_curve_trade_transactions",
    "peak_below_12_no_migration",
    "fewer_than_25_qualified_buyers",
    "unknown_peak_holder_ownership",
    "creator_monopoly_at_peak",
    "unsupported_receipt_custody:",
    "counterfactual_revert",
    "instruction_event_binding_count",
    "unresolvable_inventory_gap",
    "inventory_gap_account_not_identified",
    "custody_repair_limit",
)
TRANSIENT_MARKERS = (
    "timeout",
    "timed out",
    "connection reset",
    "connection aborted",
    "connection refused",
    "temporarily unavailable",
    "rate limit",
    "too many requests",
    "http error 429",
    "http error 500",
    "http error 502",
    "http error 503",
    "http error 504",
    "historical_block_unavailable",
    "historical_transaction_unavailable",
    "migration_curve_binding_missing",
    "migration_receipt_coverage_missing",
    "coverage_missing",
    "incomplete_post_migration_history",
    "authenticated_pool_open_missing",
    "pagination_cycle",
    "urlopen error",
    "server disconnected",
    "server error",
    "-32005",
    "-32603",
)
SECRET_PATTERNS = (
    (re.compile(r"(https://rpc\.shyft\.to\?api_key=)[^\s'\"]+", re.I), r"\1[REDACTED]"),
    (re.compile(r"(https://solana-mainnet\.g\.alchemy\.com/v2/)[A-Za-z0-9_-]+", re.I), r"\1[REDACTED]"),
    (re.compile(r"([?&]api[-_]key=)[^&\s'\"]+", re.I), r"\1[REDACTED]"),
    (re.compile(r"\bsk_[A-Za-z0-9_-]+\b"), "[REDACTED]"),
)


def utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _atomic_json(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.partial")
    with tmp.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)


def _append_jsonl(path: pathlib.Path, row: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n").encode()
    fd = os.open(path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
    try:
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)


def redact(text: Any) -> str:
    value = str(text)
    for pattern, replacement in SECRET_PATTERNS:
        value = pattern.sub(replacement, value)
    return value[:1000]


def classify_failure(reason: Any, error_type: str = "") -> str:
    """Return ``rejected`` only for known definitive verifier findings."""
    message = redact(reason).lower()
    if message.startswith('local_source_not_eligible:') and error_type in {'', 'ValueError'}:
        return 'rejected'
    if any(marker in message for marker in TRANSIENT_MARKERS):
        return "retryable"
    if error_type in {"TimeoutError", "ConnectionError", "OSError"}:
        return "retryable"
    if any(marker in message for marker in DEFINITIVE_REASONS):
        return "rejected" if error_type in {"", "ValueError"} else "retryable"
    return "retryable"


def _mint(candidate: Mapping[str, Any]) -> str:
    value = candidate.get("mint")
    if not isinstance(value, str) or not value:
        raise ValueError("candidate_missing_mint")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("unsafe_candidate_mint")
    return value


def _hash_candidate(candidate: Mapping[str, Any]) -> str:
    return hashlib.sha256((QUEUE_SALT + _mint(candidate)).encode()).hexdigest()


def build_candidate_queue(
    shortlist: Sequence[Mapping[str, Any]],
    daily_censuses: Sequence[Mapping[str, Any]],
    start: int = C.START,
    end_exclusive: int = C.END,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Mirror ``collect_cohort.main`` ordering, then dedupe by first occurrence.

    Daily migrations are hash-ordered. Cached shortlist rows are inserted at
    index zero one by one, matching the existing collector's behavior (which
    reverses same-day shortlist order). Daily queues are then interleaved by
    row number. Cached entries win duplicate-mint precedence because they are
    inserted before that day's migration rows.
    """
    if end_exclusive <= start or (end_exclusive - start) % 86400:
        raise ValueError("candidate_window_must_contain_whole_utc_days")
    day_count = (end_exclusive - start) // 86400
    daily: list[list[dict[str, Any]]] = [[] for _ in range(day_count)]

    if len(daily_censuses) != day_count:
        raise ValueError(f"expected_{day_count}_daily_censuses_got_{len(daily_censuses)}")
    for day_index, census in enumerate(daily_censuses):
        day = start + day_index * 86400
        if census.get("day") != day:
            raise ValueError("migration_census_day_order_mismatch")
        if census.get("decoder_version") != "bound_curve_v1":
            raise ValueError("migration_census_decoder_version_mismatch")
        rows = [dict(row) for row in census.get("migrations", [])]
        rows.sort(key=_hash_candidate)
        for row in rows:
            row.setdefault("source", "authenticated_migration_census")
        daily[day_index].extend(rows)

    for item in shortlist:
        row = dict(item)
        creation_time = row.get("creation_time")
        if creation_time is None:
            creation_time = row.get("creation", {}).get("timestamp")
        if creation_time is None:
            raise ValueError("cached_candidate_missing_creation_time")
        day_index = (int(creation_time) - start) // 86400
        if not 0 <= day_index < day_count:
            continue
        # Keep the existing main() insertion semantics byte-for-byte in spirit.
        daily[day_index].insert(0, row)

    interleaved: list[dict[str, Any]] = []
    for round_index in range(max((len(rows) for rows in daily), default=0)):
        interleaved.extend(rows[round_index] for rows in daily if round_index < len(rows))

    queue: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    first_by_mint: dict[str, tuple[int, dict[str, Any]]] = {}
    for occurrence_index, row in enumerate(interleaved):
        mint = _mint(row)
        if mint in first_by_mint:
            kept_index, kept_row = first_by_mint[mint]
            exclusions.append(
                {
                    "mint": mint,
                    "excluded_occurrence": occurrence_index,
                    "kept_queue_index": kept_index,
                    "kept_source": kept_row.get("source"),
                    "excluded_source": row.get("source"),
                    "reason": "duplicate_mint_first_candidate_retained",
                }
            )
            continue
        first_by_mint[mint] = (len(queue), row)
        queue.append(row)
    return queue, exclusions


def _queue_digest(candidates: Sequence[Mapping[str, Any]]) -> str:
    return hashlib.sha256(_canonical_json(list(candidates))).hexdigest()


def load_or_create_candidate_queue() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if QUEUE_PATH.exists():
        data = C.read(QUEUE_PATH)
        candidates = data.get("candidates")
        if not isinstance(candidates, list) or data.get("schema_version") != QUEUE_VERSION:
            raise ValueError("durable_candidate_queue_schema_invalid")
        if data.get("target") != C.TARGET or data.get("start") != C.START or data.get("end_exclusive") != C.END:
            raise ValueError("durable_candidate_queue_freeze_mismatch")
        if data.get("candidate_count") != len(candidates) or data.get("queue_sha256") != _queue_digest(candidates):
            raise ValueError("durable_candidate_queue_integrity_mismatch")
        if len({_mint(item) for item in candidates}) != len(candidates):
            raise ValueError("durable_candidate_queue_contains_duplicate_mints")
        return [dict(item) for item in candidates], data

    shortlist_path = P / "CACHED_SHORTLIST.json"
    if not shortlist_path.exists():
        raise FileNotFoundError(shortlist_path)
    shortlist = C.read(shortlist_path)
    daily_censuses = []
    day = C.START
    while day < C.END:
        path = P / "migration_census" / f"{day}.json.gz"
        if not path.exists():
            raise FileNotFoundError(f"required_completed_census_missing:{path.name}")
        census = C.read(path)
        coverage = census.get("coverage", {})
        if not coverage.get("exhausted"):
            raise ValueError(f"migration_census_not_exhausted:{path.name}")
        daily_censuses.append(census)
        day += 86400

    candidates, exclusions = build_candidate_queue(shortlist, daily_censuses, C.START, C.END)
    data = {
        "schema_version": QUEUE_VERSION,
        "target": C.TARGET,
        "start": C.START,
        "end_exclusive": C.END,
        "verifier_version": C.VERIFIER_VERSION,
        "ordering": "per-day migration hash ascending; same-day cached shortlist inserted at index zero in shortlist iteration order; daily queues interleaved by row; first mint occurrence retained",
        "shortlist_count": len(shortlist),
        "census_day_count": len(daily_censuses),
        "candidate_count": len(candidates),
        "duplicate_exclusion_count": len(exclusions),
        "queue_sha256": _queue_digest(candidates),
        "created_utc": utc_now(),
        "candidates": candidates,
    }
    _atomic_json(QUEUE_PATH, data)
    _atomic_json(
        QUEUE_EXCLUSIONS_PATH,
        {
            "queue_sha256": data["queue_sha256"],
            "count": len(exclusions),
            "duplicates": exclusions,
        },
    )
    return candidates, data


def ordered_prefix(
    candidates: Sequence[Mapping[str, Any]],
    outcomes: Mapping[str, Mapping[str, Any]],
    target: int,
) -> dict[str, Any]:
    """Compute the deterministic admitted prefix without exceeding target."""
    selected: list[str] = []
    rejected: list[str] = []
    staged_extras: list[str] = []
    cursor = 0
    for candidate in candidates:
        mint = _mint(candidate)
        outcome = outcomes.get(mint)
        if not outcome or outcome.get("status") not in {"verified", "rejected"}:
            break
        if outcome["status"] == "rejected":
            rejected.append(mint)
        elif len(selected) < target:
            selected.append(mint)
        else:
            staged_extras.append(mint)
        cursor += 1
        if len(selected) == target:
            break
    return {"selected": selected, "rejected": rejected, "staged_extras": staged_extras, "cursor": cursor}


def can_submit_candidate(
    selected_count: int,
    inflight_count: int,
    buffered_verified_count: int,
    target: int,
) -> bool:
    """Reserve one success slot for every active or buffered verification.

    In-flight work is treated as successful until it returns a definitive
    rejection or retryable failure. Buffered verified outcomes count only
    until the ordered coordinator accounts them. This keeps speculative
    verification from exceeding the exact selection target.
    """
    if min(selected_count, inflight_count, buffered_verified_count) < 0 or target < 0:
        raise ValueError("submission_reservation_counts_must_be_nonnegative")
    return selected_count + inflight_count + buffered_verified_count < target


def seed_known_outcomes(
    candidates: Sequence[Mapping[str, Any]],
    manifest_rows: Sequence[Mapping[str, Any]],
    rejected_rows: Sequence[Mapping[str, Any]],
    validated_audits: Mapping[str, Mapping[str, Any]],
    journal: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Merge resume evidence without trusting stale or transient failures."""
    rejected_by_mint = {
        row.get("mint"): row
        for row in rejected_rows
        if isinstance(row, Mapping)
        and row.get("mint")
        and row.get("verifier_version") == C.VERIFIER_VERSION
    }
    outcomes: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        mint = _mint(candidate)
        audit = validated_audits.get(mint)
        if (
            isinstance(audit, Mapping)
            and audit.get("mint", mint) == mint
            and audit.get("verifier_version") == C.VERIFIER_VERSION
            and audit.get("status") == "verified"
        ):
            outcomes[mint] = {"status": "verified", "audit": dict(audit), "legacy": True}
            continue
        row = rejected_by_mint.get(mint)
        if row and classify_failure(row.get("reason", ""), "ValueError") == "rejected":
            outcomes[mint] = {"status": "rejected", "rejection": dict(row), "legacy": True}
            continue
        event = journal.get(mint)
        if event and event.get("status") == "rejected":
            reason = event.get("reason", "")
            if classify_failure(reason, event.get("error_type", "")) == "rejected":
                outcomes[mint] = {"status": "rejected", "rejection": dict(event), "legacy": True}
                continue
        # A manifest row without a validated audit is retried below.
    return outcomes


def _last_journal_rows() -> dict[str, dict[str, Any]]:
    if not EVENTS_PATH.exists():
        return {}
    latest: dict[str, dict[str, Any]] = {}
    with EVENTS_PATH.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                mint = _mint(row)
            except Exception as exc:
                raise ValueError(f"parallel_outcome_journal_corrupt_line_{line_number}") from exc
            latest[mint] = row
    return latest


def _validated_audit(mint: str, root: pathlib.Path) -> dict[str, Any] | None:
    """Use collect_cohort's receipt validator; never trust an audit JSON alone."""
    validator = getattr(C, "validated_cached_audit", None)
    if validator is None:
        raise RuntimeError("collect_cohort.validated_cached_audit_required_before_parallel_resume")
    old_root = C.P
    try:
        C.P = root
        value = validator(mint)
    finally:
        C.P = old_root
    if isinstance(value, tuple):
        value = next((part for part in value if isinstance(part, dict)), None)
    if value is True:
        path = root / "audits" / f"{mint}.json"
        value = C.read(path) if path.exists() else None
    if not isinstance(value, dict):
        return None
    if value.get("mint", mint) != mint:
        return None
    if value.get("verifier_version") != C.VERIFIER_VERSION or value.get("status") != "verified":
        return None
    return value


def _load_legacy_state(
    candidates: Sequence[Mapping[str, Any]], journal: Mapping[str, Mapping[str, Any]]
) -> tuple[
    dict[str, dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, dict[str, Any]],
]:
    """Seed successes/rejections from validated durable artifacts and old progress."""
    existing_manifest = P / "COHORT_MANIFEST.json"
    existing_rejected = P / "REJECTED_CANDIDATES.json"
    manifest_rows = C.read(existing_manifest).get("coins", []) if existing_manifest.exists() else []
    rejected_rows = C.read(existing_rejected) if existing_rejected.exists() else []
    validated_audits: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        mint = _mint(candidate)
        audit_path = P / "audits" / f"{mint}.json"
        if not audit_path.exists():
            continue
        audit = _validated_audit(mint, P)
        if audit is not None:
            validated_audits[mint] = audit
    outcomes = seed_known_outcomes(candidates, manifest_rows, rejected_rows, validated_audits, journal)
    # A prior coordinator can stop after the worker atomically wrote both
    # staged files but before its parent journaled or promoted them. Validate
    # such results before letting the ordered cursor consume them on resume.
    for candidate in candidates:
        mint = _mint(candidate)
        if mint in outcomes or journal.get(mint, {}).get("status") != "verified":
            continue
        stage = _safe_stage_path(mint)
        audit_path = stage / "audits" / f"{mint}.json"
        if not audit_path.exists():
            continue
        audit = _validated_audit(mint, stage)
        if audit is not None:
            outcomes[mint] = {"status": "verified", "audit": audit, "legacy": False}
    return outcomes, manifest_rows, rejected_rows, validated_audits


def _safe_stage_path(mint: str) -> pathlib.Path:
    _mint({"mint": mint})
    return STAGE_ROOT / mint


def _quarantine_stage_audit(stage: pathlib.Path, mint: str) -> None:
    quarantine = stage / "_invalid_cached_artifacts"
    for rel in (pathlib.Path("audits") / f"{mint}.json", pathlib.Path("bound_curve_tapes") / f"{mint}.json.gz"):
        path = stage / rel
        if path.exists() or path.is_symlink():
            quarantine.mkdir(parents=True, exist_ok=True)
            dest = quarantine / (rel.parent.name + "_" + rel.name + "." + str(time.time_ns()))
            os.replace(path, dest)


def _prepare_worker_stage(stage: pathlib.Path, mint: str) -> None:
    stage.mkdir(parents=True, exist_ok=True)
    # Read through existing canonical raw receipts without modifying them.
    # R.save writes a temp file then replaces this symlink if it must extend or
    # repair a receipt, leaving the original canonical cache intact.
    for folder in ("raw_curves", "raw_pools"):
        name = f"{mint}.json.gz"
        target = stage / folder / name
        source = P / folder / name
        if not target.exists() and not target.is_symlink() and source.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(source.resolve())


def _worker_init(provider_preference: str | None) -> None:
    global _WORKER_C
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.dont_write_bytecode = True
    if provider_preference:
        os.environ["COHORT_RPC_PREFERRED_PROVIDER"] = provider_preference
    import collect_cohort as worker_cohort

    _WORKER_C = worker_cohort


def _worker_verify(candidate: Mapping[str, Any], stage_root: str) -> dict[str, Any]:
    mint = _mint(candidate)
    stage = pathlib.Path(stage_root) / mint
    _prepare_worker_stage(stage, mint)
    _WORKER_C.P = stage
    try:
        stage_audit = stage / "audits" / f"{mint}.json"
        stage_bound = stage / "bound_curve_tapes" / f"{mint}.json.gz"
        if (stage_audit.exists() or stage_bound.exists()) and _WORKER_C.validated_cached_audit(mint) is None:
            _quarantine_stage_audit(stage, mint)
        result = _WORKER_C.verify(dict(candidate))
        return {"status": "verified", "mint": mint, "audit": result}
    except Exception as exc:
        message = redact(exc)
        return {
            "status": classify_failure(message, type(exc).__name__),
            "mint": mint,
            "reason": message,
            "error_type": type(exc).__name__,
        }


def _promote_stage_artifacts(mint: str, stage: pathlib.Path, include_audit: bool) -> list[str]:
    promoted: list[str] = []
    relative_paths = [
        pathlib.Path("raw_curves") / f"{mint}.json.gz",
        pathlib.Path("raw_pools") / f"{mint}.json.gz",
    ]
    if include_audit:
        relative_paths.extend(
            [
                pathlib.Path("bound_curve_tapes") / f"{mint}.json.gz",
                pathlib.Path("audits") / f"{mint}.json",
            ]
        )
    for rel in relative_paths:
        source = stage / rel
        if not source.is_file() or source.is_symlink():
            continue
        dest = P / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            # A stage symlink is an unchanged read-through cache. A regular
            # staged receipt can be a custody repair or extension; preserve
            # the previous canonical copy before promoting the verified one.
            replaceable = {"raw_curves", "raw_pools"}
            if include_audit:
                replaceable |= {"bound_curve_tapes", "audits"}
            if rel.parts[0] in replaceable and not source.is_symlink():
                preserved = stage / "_prior_canonical_cache" / rel
                preserved.parent.mkdir(parents=True, exist_ok=True)
                if preserved.exists():
                    preserved = preserved.with_name(preserved.name + "." + str(time.time_ns()))
                os.replace(dest, preserved)
            else:
                continue
        os.replace(source, dest)
        promoted.append(rel.as_posix())
    return promoted


def _write_status(
    *,
    state: str,
    queue_data: Mapping[str, Any],
    selected_count: int,
    rejected_count: int,
    cursor: int,
    workers: int,
    pilot_attempts: int | None,
    attempted_this_run: int,
    retryable_count: int,
    legacy_audits: int,
    last_mint: str | None = None,
    last_error: str | None = None,
    provider_preference: str | None = None,
    progress_fields: Mapping[str, Any] | None = None,
) -> None:
    value = {
        "state": state,
        "target": C.TARGET,
        "total_selected": selected_count,
        "ordered_admitted_coins": selected_count,
        "rejected_candidate_count": rejected_count,
        "retryable_candidate_count": retryable_count,
        "queue_count": queue_data.get("candidate_count"),
        "queue_sha256": queue_data.get("queue_sha256"),
        "ordered_prefix_cursor": cursor,
        "workers": workers,
        "attempted_unique_candidates_this_run": attempted_this_run,
        "pilot_attempts": pilot_attempts,
        "legacy_validated_audits_found": legacy_audits,
        "provider_preference": provider_preference,
        "admission_order": "validated existing manifest rows are preserved as resume preseeds; additional cached and new outcomes are admitted in candidate queue order",
        "resume_policy": "manifest-backed current-version audits remain preseeded; audit-only cached successes wait for their candidate queue position",
        "worker_artifacts": "per-mint parallel_stage/candidates/<mint>; only admitted audits and tapes are promoted",
        "network_errors": "retryable/unresolved, never counted as definitive parity rejections",
        "last_mint": last_mint,
        "last_error": redact(last_error) if last_error else None,
        "updated_utc": utc_now(),
    }
    if progress_fields:
        value.update(progress_fields)
    _atomic_json(STATUS_PATH, value)
    # Keep human-readable progress current even when the ordered cursor waits.
    notes_path = STATUS_PATH.with_name('STATUS.md')
    marker = '\n<!-- worker-progress -->\n'
    notes = notes_path.read_text() if notes_path.exists() else '# Active cohort collection\n'
    notes = notes.split(marker)[0]
    notes += marker + (
        f"\nOrdered admissions: {selected_count}/{C.TARGET}; cursor: {cursor}.\n\n"
        f"Worker task completions this run: {value.get('total_completed_by_workers', 0)} "
        f"(retries count separately); status counts: {value.get('worker_completion_counts_this_run', {})}.\n\n"
        f"Buffered verified: {value.get('buffered_verified_count', 0)}; "
        f"validated resumed stages: {value.get('resumed_staged_valid_count', 0)}; "
        f"in flight: {value.get('worker_inflight_count', 0)}. Updated {value['updated_utc']}.\n"
    )
    temporary = notes_path.with_name(notes_path.name + f'.{os.getpid()}.partial')
    temporary.write_text(notes)
    temporary.replace(notes_path)


def _write_complete_marker(
    selected: Sequence[Mapping[str, Any]], rejected_count: int, staged_verified_extras: int
) -> None:
    if len(selected) != C.TARGET or len({_mint(row) for row in selected}) != C.TARGET:
        raise ValueError("refusing_completion_marker_before_exact_target")
    C.R.save(
        P / "COLLECTION_COMPLETE.json",
        {
            "total_selected": C.TARGET,
            "total_verified": C.TARGET,
            "dropped_admitted_coins": 0,
            "rejected_candidates_replaced": rejected_count,
            "staged_verified_extras": staged_verified_extras,
            "whole_source_parity_pass_rate": 1.0,
            "complete": True,
        },
    )


def _candidate_by_mint(candidates: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    return {_mint(candidate): dict(candidate) for candidate in candidates}


def _staged_verified_extras(candidates: Sequence[Mapping[str, Any]], selected: Sequence[Mapping[str, Any]]) -> list[str]:
    selected_mints = {_mint(row) for row in selected}
    extras = []
    for candidate in candidates:
        mint = _mint(candidate)
        if mint in selected_mints:
            continue
        stage = _safe_stage_path(mint)
        if not (stage / "audits" / f"{mint}.json").exists():
            continue
        if _validated_audit(mint, stage) is not None:
            extras.append(mint)
    return extras


def _validated_staged_mints(candidates: Sequence[Mapping[str, Any]]) -> set[str]:
    """Return independently validated staged audits, without consulting the cursor.

    This is status-only resume evidence. It does not seed outcomes or alter
    deterministic admission; it makes valid staged work visible even when its
    queue position is beyond an unresolved head candidate.
    """
    if not STAGE_ROOT.exists():
        return set()
    queued_mints = {_mint(candidate) for candidate in candidates}
    staged: set[str] = set()
    for stage in STAGE_ROOT.iterdir():
        mint = stage.name
        if not stage.is_dir() or mint not in queued_mints:
            continue
        if not (stage / "audits" / f"{mint}.json").exists():
            continue
        if _validated_audit(mint, stage) is not None:
            staged.add(mint)
    return staged


def _worker_progress_fields(
    *,
    completion_counts: Mapping[str, int],
    completed_mints: set[str],
    inflight_count: int,
    outcomes: Mapping[str, Mapping[str, Any]],
    selected_mints: set[str],
    accounted_mints: set[str],
    resumed_staged_mints: set[str],
    last_worker_status: str | None,
) -> dict[str, Any]:
    """Build explicit progress fields; worker counts never include cached work."""
    statuses = ("verified", "rejected", "retryable")
    counts = {status: int(completion_counts.get(status, 0)) for status in statuses}
    buffered = {
        mint
        for mint, outcome in outcomes.items()
        if outcome.get("status") == "verified"
        and mint not in selected_mints
        and mint not in accounted_mints
    }
    worker_buffered = buffered & completed_mints
    resumed_buffered = buffered & resumed_staged_mints
    return {
        "worker_progress_scope": "current_run_task_completions; retries count as separate completions; resumed and cached audits are excluded",
        "total_completed_by_workers": sum(counts.values()),
        "worker_completion_counts_this_run": counts,
        "worker_completed_unique_candidates_this_run": len(completed_mints),
        "worker_inflight_count": max(0, int(inflight_count)),
        "resumed_staged_valid_count": len(resumed_staged_mints),
        "resumed_staged_valid_unadmitted_count": len(resumed_staged_mints - selected_mints),
        "buffered_verified_count": len(buffered),
        "buffered_verified_by_current_run_workers": len(worker_buffered),
        "buffered_verified_from_resumed_stages": len(resumed_buffered),
        "buffered_verified_from_other_cached_outcomes": len(buffered - worker_buffered - resumed_buffered),
        "last_worker_status": last_worker_status,
    }


def run_collection(
    workers: int = 6,
    pilot_attempts: int | None = None,
    provider_preference: str | None = None,
    retry_attempts_per_run: int = RETRY_ATTEMPTS_PER_RUN,
) -> dict[str, Any]:
    if workers < 1:
        raise ValueError("workers_must_be_positive")
    if pilot_attempts is not None and pilot_attempts < 1:
        raise ValueError("pilot_attempts_must_be_positive")
    if provider_preference not in (None, "alchemy", "shyft", "solami", "helius"):
        raise ValueError("invalid_provider_preference")

    candidates, queue_data = load_or_create_candidate_queue()
    journal = _last_journal_rows()
    outcomes, manifest_rows, rejected_rows, validated_audits = _load_legacy_state(candidates, journal)
    candidate_map = _candidate_by_mint(candidates)
    legacy_audits = len(validated_audits)
    # These are validated local stage artifacts present at resume time. Keep
    # their count separate from completions performed by workers in this run.
    resumed_staged_valid_mints = _validated_staged_mints(candidates)

    # Preserve validated rows from older manifests that fall outside the newly
    # materialized queue. Such rows count against the exact target and are
    # called out in coordinator status instead of being silently discarded.
    queued_mints = set(candidate_map)
    orphan_selected = []
    for row in manifest_rows:
        if not isinstance(row, dict) or row.get("verifier_version") != C.VERIFIER_VERSION:
            continue
        mint = row.get("mint")
        if mint and mint not in queued_mints:
            validated = _validated_audit(mint, P)
            if validated is not None:
                orphan_selected.append(validated)
    orphan_rejected = [
        row
        for row in rejected_rows
        if isinstance(row, dict)
        and row.get("mint") not in queued_mints
        and row.get("verifier_version") == C.VERIFIER_VERSION
        and classify_failure(row.get("reason", ""), "ValueError") == "rejected"
    ]

    old_progress = P / "PROGRESS.json"
    original_progress = C.read(old_progress) if old_progress.exists() else {}
    original_selected_count = len(manifest_rows)
    original_rejected_count = len(rejected_rows)
    if original_selected_count or original_rejected_count:
        _append_jsonl(
            EVENTS_PATH,
            {
                "event": "resume_snapshot",
                "mint": "resume_snapshot",
                "manifest_selected_count": original_selected_count,
                "rejected_count": original_rejected_count,
                "prior_progress_updated_utc": original_progress.get("updated_utc"),
                "legacy_validated_audits_found": legacy_audits,
                "at_utc": utc_now(),
            },
        )

    selected: list[dict[str, Any]] = []
    selected_mints: set[str] = set()
    # Preserve the existing sequential pilot admissions first. Then salvage
    # every additional current-version audit only after the verifier's source,
    # parity and migration-coverage validator approves it.
    for row in manifest_rows:
        if not isinstance(row, dict) or row.get("verifier_version") != C.VERIFIER_VERSION:
            continue
        mint = row.get("mint")
        audit = validated_audits.get(mint)
        if audit is not None and mint not in selected_mints and len(selected) < C.TARGET:
            selected.append(audit)
            selected_mints.add(mint)
    for row in orphan_selected:
        mint = row.get("mint")
        if mint and mint not in selected_mints and len(selected) < C.TARGET:
            selected.append(row)
            selected_mints.add(mint)

    rejected: list[dict[str, Any]] = []
    rejected_mints: set[str] = set()
    for row in rejected_rows:
        if (
            isinstance(row, dict)
            and row.get("verifier_version") == C.VERIFIER_VERSION
            and classify_failure(row.get("reason", ""), "ValueError") == "rejected"
        ):
            mint = row.get("mint")
            if mint and mint not in rejected_mints:
                rejected.append(dict(row))
                rejected_mints.add(mint)
    for candidate in candidates:
        mint = _mint(candidate)
        outcome = outcomes.get(mint)
        if outcome and outcome.get("status") == "rejected" and mint not in rejected_mints:
            row = dict(outcome.get("rejection", {}))
            if not row:
                row = {
                    "mint": mint,
                    "verifier_version": C.VERIFIER_VERSION,
                    "reason": outcome.get("reason", "frozen_verifier_rejection"),
                    "source": candidate.get("source"),
                }
            rejected.append(row)
            rejected_mints.add(mint)
    for row in orphan_rejected:
        mint = row.get("mint")
        if mint and mint not in rejected_mints:
            rejected.append(dict(row))
            rejected_mints.add(mint)

    accounted_mints = selected_mints | rejected_mints
    if len(selected) != len(selected_mints) or len(selected) > C.TARGET:
        raise ValueError("duplicate_or_over_target_resume_selection")
    C.progress(selected, rejected, "collecting")

    worker_completion_counts = {"verified": 0, "rejected": 0, "retryable": 0}
    worker_completed_mints: set[str] = set()
    last_worker_status: str | None = None

    cursor = 0
    while cursor < len(candidates):
        mint = _mint(candidates[cursor])
        outcome = outcomes.get(mint)
        if not outcome or outcome.get("status") not in {"verified", "rejected"}:
            break
        if mint not in accounted_mints:
            if outcome["status"] == "verified" and len(selected) < C.TARGET:
                if not outcome.get("legacy"):
                    _promote_stage_artifacts(mint, _safe_stage_path(mint), include_audit=True)
                selected.append(outcome["audit"])
                selected_mints.add(mint)
            elif outcome["status"] == "rejected":
                rejected.append(dict(outcome.get("rejection", {})))
                rejected_mints.add(mint)
            accounted_mints.add(mint)
        cursor += 1
    if len(selected) != len(selected_mints) or len(selected) > C.TARGET:
        raise ValueError("duplicate_or_over_target_resume_selection")
    C.progress(selected, rejected, "collecting")
    if len(selected) >= C.TARGET:
        selected = selected[: C.TARGET]
        C.progress(selected, rejected, "complete")
        staged_extras = _staged_verified_extras(candidates, selected)
        _write_complete_marker(selected, len(rejected), len(staged_extras))
        _write_status(
            state="complete",
            queue_data=queue_data,
            selected_count=len(selected),
            rejected_count=len(rejected),
            cursor=cursor,
            workers=workers,
            pilot_attempts=pilot_attempts,
            attempted_this_run=0,
            retryable_count=0,
            legacy_audits=legacy_audits,
            provider_preference=provider_preference,
            progress_fields=_worker_progress_fields(
                completion_counts=worker_completion_counts,
                completed_mints=worker_completed_mints,
                inflight_count=0,
                outcomes=outcomes,
                selected_mints=selected_mints,
                accounted_mints=accounted_mints,
                resumed_staged_mints=resumed_staged_valid_mints,
                last_worker_status=last_worker_status,
            ),
        )
        status = C.read(STATUS_PATH)
        status["staged_verified_extra_count"] = len(staged_extras)
        status["staged_verified_extra_mints"] = staged_extras
        _atomic_json(STATUS_PATH, status)
        return status

    inflight: dict[concurrent.futures.Future, tuple[int, str]] = {}
    retries: list[tuple[int, str]] = []
    attempts_this_run: dict[str, int] = {}
    total_attempts_this_run = 0
    scheduled_unique: set[str] = set()
    retryable_errors: dict[str, str] = {}
    stop_reason: str | None = None
    last_mint: str | None = None
    last_error: str | None = None

    # Limit speculative work to a short queue window. Workers are continuously
    # refilled as calls complete, while slow earlier candidates cannot cause an
    # unbounded pile of extra verified artifacts. All speculative outputs stay
    # explicitly staged until the order cursor admits them.
    speculation_window = max(100, workers * 15)
    next_to_submit = 0
    while next_to_submit < len(candidates) and _mint(candidates[next_to_submit]) in outcomes:
        next_to_submit += 1

    executor = concurrent.futures.ProcessPoolExecutor(
        max_workers=workers,
        mp_context=multiprocessing.get_context("spawn"),
        initializer=_worker_init,
        initargs=(provider_preference,),
    )

    def flush_ordered() -> None:
        nonlocal cursor, selected, rejected
        old_cursor = cursor
        while cursor < len(candidates) and len(selected) < C.TARGET:
            candidate = candidates[cursor]
            mint = _mint(candidate)
            outcome = outcomes.get(mint)
            if not outcome or outcome.get("status") not in {"verified", "rejected"}:
                break
            if mint in accounted_mints:
                cursor += 1
                continue
            if outcome["status"] == "verified":
                audit = outcome["audit"]
                if not outcome.get("legacy"):
                    stage = _safe_stage_path(mint)
                    _promote_stage_artifacts(mint, stage, include_audit=True)
                selected.append(audit)
                selected_mints.add(mint)
            else:
                row = dict(outcome.get("rejection", {}))
                if not row:
                    row = {
                        "mint": mint,
                        "verifier_version": C.VERIFIER_VERSION,
                        "reason": outcome.get("reason", "frozen_verifier_rejection"),
                        "source": candidate.get("source"),
                    }
                rejected.append(row)
                rejected_mints.add(mint)
                _promote_stage_artifacts(mint, _safe_stage_path(mint), include_audit=False)
            accounted_mints.add(mint)
            cursor += 1
        if len(selected) != len(selected_mints) or len(selected) > C.TARGET:
            raise ValueError("duplicate_or_over_target_ordered_selection")
        state = "complete" if len(selected) == C.TARGET else "collecting"
        if cursor != old_cursor:
            C.progress(selected, rejected, state)
        _write_status(
            state=state,
            queue_data=queue_data,
            selected_count=len(selected),
            rejected_count=len(rejected),
            cursor=cursor,
            workers=workers,
            pilot_attempts=pilot_attempts,
            attempted_this_run=total_attempts_this_run,
            retryable_count=len(retryable_errors),
            legacy_audits=legacy_audits,
            last_mint=last_mint,
            last_error=last_error,
            provider_preference=provider_preference,
            progress_fields=_worker_progress_fields(
                completion_counts=worker_completion_counts,
                completed_mints=worker_completed_mints,
                inflight_count=sum(not future.done() for future in inflight),
                outcomes=outcomes,
                selected_mints=selected_mints,
                accounted_mints=accounted_mints,
                resumed_staged_mints=resumed_staged_valid_mints,
                last_worker_status=last_worker_status,
            ),
        )

    try:
        while len(selected) < C.TARGET:
            flush_ordered()
            if len(selected) == C.TARGET:
                break
            if stop_reason == "retryable_candidate_unresolved" and not inflight:
                break
            if pilot_attempts is not None and len(scheduled_unique) >= pilot_attempts and not inflight:
                stop_reason = "pilot_complete"
                break

            # Submit one worker-sized window without waiting for a whole batch.
            while len(inflight) < workers:
                if stop_reason == "retryable_candidate_unresolved":
                    break
                buffered_verified_count = sum(
                    1
                    for mint, outcome in outcomes.items()
                    if mint not in accounted_mints and outcome.get("status") == "verified"
                )
                if not can_submit_candidate(
                    len(selected), len(inflight), buffered_verified_count, C.TARGET
                ):
                    break
                if retries:
                    idx, mint = retries.pop(0)
                    candidate = candidate_map[mint]
                    if attempts_this_run.get(mint, 0) >= retry_attempts_per_run:
                        retryable_errors[mint] = retryable_errors.get(mint, "retry_budget_exhausted")
                        stop_reason = "retryable_candidate_unresolved"
                        break
                else:
                    max_index = min(len(candidates), cursor + speculation_window)
                    while next_to_submit < max_index and _mint(candidates[next_to_submit]) in outcomes:
                        next_to_submit += 1
                    if next_to_submit >= max_index:
                        break
                    if pilot_attempts is not None and len(scheduled_unique) >= pilot_attempts:
                        break
                    idx = next_to_submit
                    candidate = candidates[idx]
                    mint = _mint(candidate)
                    next_to_submit += 1
                    scheduled_unique.add(mint)
                attempts_this_run[mint] = attempts_this_run.get(mint, 0) + 1
                total_attempts_this_run += 1
                try:
                    future = executor.submit(_worker_verify, candidate, str(STAGE_ROOT))
                except Exception as exc:
                    stop_reason = "worker_pool_failed"
                    last_error = redact(exc)
                    break
                inflight[future] = (idx, mint)

            if inflight:
                # Publish the active worker count as soon as the first window
                # is submitted, then refresh on completions or heartbeats.
                flush_ordered()

            if not inflight:
                if stop_reason:
                    break
                # A completely known interval may have been skipped above.
                flush_ordered()
                if cursor >= len(candidates):
                    stop_reason = "candidate_pool_exhausted"
                    break
                if pilot_attempts is not None and len(scheduled_unique) >= pilot_attempts:
                    stop_reason = "pilot_complete"
                    break
                # No eligible work inside the speculation window means the
                # cursor is waiting on a retryable candidate at its head.
                head_mint = _mint(candidates[cursor])
                if head_mint in retryable_errors:
                    stop_reason = "retryable_candidate_unresolved"
                    break
                next_to_submit = min(next_to_submit, cursor)
                continue

            done, _ = concurrent.futures.wait(
                inflight,
                timeout=STATUS_HEARTBEAT_SECONDS,
                return_when=concurrent.futures.FIRST_COMPLETED,
            )
            if not done:
                # Refresh visible liveness even during a long provider call.
                # Calling flush_ordered also preserves the existing immediate
                # status write after every completion and never advances past
                # the deterministic cursor.
                flush_ordered()
                continue
            # Stable handling for simultaneous completions does not determine
            # admission; the queue cursor does.
            for future in sorted(done, key=lambda item: inflight[item][0]):
                idx, mint = inflight.pop(future)
                try:
                    row = future.result()
                except Exception as exc:
                    row = {
                        "status": "retryable",
                        "mint": mint,
                        "reason": redact(exc),
                        "error_type": type(exc).__name__,
                    }
                last_mint = mint
                if row.get("status") == "verified":
                    stage = _safe_stage_path(mint)
                    audit = _validated_audit(mint, stage)
                    if audit is None:
                        _quarantine_stage_audit(stage, mint)
                        row = {
                            "status": "retryable",
                            "mint": mint,
                            "reason": "staged_audit_failed_independent_cached_audit_validation",
                            "error_type": "CachedArtifactValidationError",
                        }
                    else:
                        row["audit"] = audit
                        outcomes[mint] = {"status": "verified", "audit": audit, "legacy": False}
                        retryable_errors.pop(mint, None)
                if row.get("status") == "rejected":
                    outcomes[mint] = {
                        "status": "rejected",
                        "reason": redact(row.get("reason", "")),
                        "rejection": {
                            "mint": mint,
                            "verifier_version": C.VERIFIER_VERSION,
                            "reason": redact(row.get("reason", "")),
                            "source": candidate_map[mint].get("source"),
                        },
                    }
                    retryable_errors.pop(mint, None)
                elif row.get("status") == "retryable":
                    reason = redact(row.get("reason", "unknown_verification_error"))
                    last_error = reason
                    retryable_errors[mint] = reason
                    _append_jsonl(
                        EVENTS_PATH,
                        {
                            "event": "verification_attempt",
                            "mint": mint,
                            "queue_index": idx,
                            "status": "retryable",
                            "attempt_in_run": attempts_this_run.get(mint),
                            "reason": reason,
                            "error_type": row.get("error_type"),
                            "at_utc": utc_now(),
                        },
                    )
                    if attempts_this_run.get(mint, 0) < retry_attempts_per_run:
                        retries.append((idx, mint))
                        retries.sort()
                    else:
                        stop_reason = "retryable_candidate_unresolved"
                elif row.get("status") != "verified":
                    raise RuntimeError(f"worker_returned_unknown_status_for_{mint}")

                last_worker_status = row["status"]
                worker_completion_counts[last_worker_status] += 1
                worker_completed_mints.add(mint)

                if row.get("status") in {"verified", "rejected"}:
                    _append_jsonl(
                        EVENTS_PATH,
                        {
                            "event": "verification_attempt",
                            "mint": mint,
                            "queue_index": idx,
                            "status": row["status"],
                            "attempt_in_run": attempts_this_run.get(mint),
                            "reason": row.get("reason"),
                            "at_utc": utc_now(),
                        },
                    )
                    # Rejected raw receipts remain useful cached provenance;
                    # verified results stay staged until ordered admission.
                    if row["status"] == "rejected":
                        _promote_stage_artifacts(mint, _safe_stage_path(mint), include_audit=False)
                flush_ordered()

            if stop_reason == "retryable_candidate_unresolved" and not retries:
                # Already submitted later jobs may finish into staging; no
                # later candidate is committed past the unresolved queue head.
                if not inflight:
                    break

            if pilot_attempts is not None and len(scheduled_unique) >= pilot_attempts and not inflight:
                stop_reason = "pilot_complete"
                break
    finally:
        # Cancels queued speculative tasks when we hit the target or a bounded
        # pilot. Running tasks may finish in staging and are safe to resume.
        executor.shutdown(wait=True, cancel_futures=True)

    if len(selected) == C.TARGET:
        C.progress(selected, rejected, "complete")
        staged_extras = _staged_verified_extras(candidates, selected)
        _write_complete_marker(selected, len(rejected), len(staged_extras))
        state = "complete"
    elif stop_reason == "pilot_complete":
        C.progress(selected, rejected, "pilot_complete")
        state = "pilot_complete"
    elif stop_reason == "candidate_pool_exhausted" or cursor >= len(candidates):
        C.progress(selected, rejected, "candidate_pool_exhausted")
        state = "candidate_pool_exhausted"
    elif retryable_errors or stop_reason == "retryable_candidate_unresolved":
        C.progress(selected, rejected, "retryable_candidate_unresolved")
        state = "retryable_candidate_unresolved"
    elif stop_reason == "worker_pool_failed":
        C.progress(selected, rejected, "worker_pool_failed")
        state = "worker_pool_failed"
    else:
        C.progress(selected, rejected, "stopped_incomplete")
        state = "stopped_incomplete"

    staged_extras = _staged_verified_extras(candidates, selected)
    final_progress = _worker_progress_fields(
        completion_counts=worker_completion_counts,
        completed_mints=worker_completed_mints,
        # Executor shutdown(wait=True) has stopped all worker activity. Any
        # result not consumed before stop is exposed separately below.
        inflight_count=0,
        outcomes=outcomes,
        selected_mints=selected_mints,
        accounted_mints=accounted_mints,
        resumed_staged_mints=resumed_staged_valid_mints,
        last_worker_status=last_worker_status,
    )
    final_status = {
        "state": state,
        "target": C.TARGET,
        "total_selected": len(selected),
        "ordered_admitted_coins": len(selected),
        "rejected_candidate_count": len(rejected),
        "retryable_candidate_count": len(retryable_errors),
        "queue_count": len(candidates),
        "queue_sha256": queue_data["queue_sha256"],
        "ordered_prefix_cursor": cursor,
        "workers": workers,
        "attempted_unique_candidates_this_run": len(scheduled_unique),
        "pilot_attempts": pilot_attempts,
        "legacy_validated_audits_found": legacy_audits,
        "provider_preference": provider_preference,
        "last_mint": last_mint,
        "last_error": last_error,
        "staged_candidate_count": sum(1 for path in STAGE_ROOT.iterdir() if path.is_dir()) if STAGE_ROOT.exists() else 0,
        "staged_verified_extra_count": len(staged_extras),
        "staged_verified_extra_mints": staged_extras,
        "unadmitted_canonical_verified_audit_count": sum(
            1 for mint in validated_audits if mint not in selected_mints
        ),
        "admission_order": "validated existing manifest rows are preserved as resume preseeds; additional cached and new outcomes are admitted in candidate queue order",
        "resume_policy": "manifest-backed current-version audits remain preseeded; audit-only cached successes wait for their candidate queue position",
        "worker_artifacts": "per-mint parallel_stage/candidates/<mint>; only admitted audits and tapes are promoted",
        "network_errors": "retryable/unresolved, never counted as definitive parity rejections",
        "worker_results_unreconciled_count": len(inflight),
        "updated_utc": utc_now(),
        **final_progress,
    }
    _atomic_json(STATUS_PATH, final_status)
    return final_status


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--pilot-attempts", type=int, default=None)
    parser.add_argument("--provider", choices=("alchemy", "shyft", "solami", "helius"), default=None)
    args = parser.parse_args()
    lock_path = P / "RUN.lock"
    lock = lock_path.open("a+")
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        lock.close()
        raise SystemExit("another cohort coordinator holds RUN.lock") from exc
    try:
        status = run_collection(args.workers, args.pilot_attempts, args.provider)
        print(json.dumps(status, indent=2), flush=True)
        if status["state"] == "complete":
            return
        if status["state"] in {"pilot_complete", "retryable_candidate_unresolved"}:
            return
        if status["state"] == "candidate_pool_exhausted":
            raise SystemExit("candidate pool exhausted before target")
    finally:
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        lock.close()


if __name__ == "__main__":
    main()
