#!/usr/bin/env python3
"""Attach frozen-input/source hashes and receive-vs-chain parity to both metas."""
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path("/home/mthwt/code/Crypto")
REPORT = ROOT / "reports/blocked_coin_audit_20261011"
MANIFEST = REPORT / "MANIFEST.json"
INPUT = ROOT / "data/ghost_observations.jsonl"
RECEIVE_ROWS = REPORT / "candidate_rows.jsonl"
CHAIN_ROWS = REPORT / "candidate_rows_chain_order.jsonl"
RECEIVE_META = REPORT / "candidate_meta.json"
CHAIN_META = REPORT / "candidate_meta_chain_order.json"


def sha256_file(path: Path, limit: int | None = None) -> str:
    digest = hashlib.sha256()
    remaining = limit
    with path.open("rb") as stream:
        while remaining is None or remaining > 0:
            block = stream.read(1024 * 1024 if remaining is None else min(1024 * 1024, remaining))
            if not block:
                break
            digest.update(block)
            if remaining is not None:
                remaining -= len(block)
    if remaining not in (None, 0):
        raise RuntimeError(f"{path} ended before frozen byte limit")
    return digest.hexdigest()


def read_rows(path: Path) -> dict[tuple[str, str, str], dict]:
    output = {}
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            key = (row["mint"], row["family"], row["signature"])
            if key in output:
                raise RuntimeError(f"duplicate candidate key: {key}")
            output[key] = row
    return output


def input_order_diagnostics(byte_limit: int, cutoff_ms: int) -> dict:
    used = rows = rows_after_cutoff = 0
    same_slot_inversions = slot_regressions = 0
    eligible_same_slot_inversions = eligible_slot_regressions = 0
    timestamp_regressions = 0
    previous_key = previous_eligible_key = previous_received_ms = None
    with INPUT.open("rb") as stream:
        while used < byte_limit:
            line = stream.readline()
            if not line or used + len(line) > byte_limit or not line.endswith(b"\n"):
                break
            used += len(line)
            row = json.loads(line)
            rows += 1
            received_ms = int(row.get("received_at_ms", 0))
            key = (int(row.get("slot", 0)), int(row.get("transaction_index", 0)))
            if previous_received_ms is not None and received_ms < previous_received_ms:
                timestamp_regressions += 1
            previous_received_ms = received_ms
            if previous_key is not None and key < previous_key:
                if key[0] < previous_key[0]:
                    slot_regressions += 1
                else:
                    same_slot_inversions += 1
            previous_key = key
            if received_ms > cutoff_ms:
                rows_after_cutoff += 1
                continue
            if previous_eligible_key is not None and key < previous_eligible_key:
                if key[0] < previous_eligible_key[0]:
                    eligible_slot_regressions += 1
                else:
                    eligible_same_slot_inversions += 1
            previous_eligible_key = key
    return {
        "frozen_prefix_bytes_read": used,
        "complete_receipts_in_manifest_prefix": rows,
        "eligible_receipts_at_or_before_cutoff": rows - rows_after_cutoff,
        "rows_after_cutoff_in_manifest_prefix": rows_after_cutoff,
        "same_slot_transaction_index_inversions_all_prefix": same_slot_inversions,
        "same_slot_transaction_index_inversions_eligible": eligible_same_slot_inversions,
        "slot_regressions_all_prefix": slot_regressions,
        "slot_regressions_eligible": eligible_slot_regressions,
        "receive_timestamp_regressions": timestamp_regressions,
    }


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    input_limit = manifest["inputs"]["data/ghost_observations.jsonl"]["size_bytes"]
    receive = read_rows(RECEIVE_ROWS)
    chain = read_rows(CHAIN_ROWS)
    keys_equal = receive.keys() == chain.keys()
    fields = (
        "timestamp_ms", "slot", "transaction_index", "signal_reserve_sol", "spot",
        "qualified_buyer_count", "anti_bundle_clear", "anti_bundle_first_reason",
        "creation_observed",
    )
    changed = []
    receipt_differences = 0
    for key in receive.keys() & chain.keys():
        if any(receive[key].get(field) != chain[key].get(field) for field in fields):
            changed.append(key)
        if receive[key].get("receipt") != chain[key].get("receipt"):
            receipt_differences += 1

    source_paths = [
        ROOT / "src/bot/curve_detector.rs",
        ROOT / "src/bot/ghost_execution.rs",
        ROOT / "src/bot/migration_amm.rs",
    ]
    helper_paths = [
        REPORT / "helpers/Cargo.toml",
        REPORT / "helpers/Cargo.lock",
        REPORT / "helpers/main.rs",
        REPORT / "helpers/sort_receipts_chain_order.py",
        REPORT / "helpers/finalize_candidate_meta.py",
    ]
    provenance = {
        "repository_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "input_manifest_sha256": sha256_file(MANIFEST),
        "input_observations_frozen_prefix_sha256": sha256_file(INPUT, input_limit),
        "input_observations_frozen_prefix_bytes": input_limit,
        "rust_source_sha256": {str(path.relative_to(ROOT)): sha256_file(path) for path in source_paths},
        "helper_sha256": {str(path.relative_to(ROOT)): sha256_file(path) for path in helper_paths},
        "receive_order_rows_sha256": sha256_file(RECEIVE_ROWS),
        "chain_order_rows_sha256": sha256_file(CHAIN_ROWS),
    }
    parity = {
        "receive_candidate_rows": len(receive),
        "chain_order_candidate_rows": len(chain),
        "candidate_keys_equal": keys_equal,
        "candidate_snapshot_differences": len(changed),
        "candidate_receipt_payload_differences": receipt_differences,
        "chain_candidates_using_prior_same_mint_receipt_received_later": sum(
            row.get("prior_chain_state_uses_later_received_data", False) for row in chain.values()
        ),
        "compared_snapshot_fields": list(fields),
        "receive_and_chain_order_row_key": ["mint", "family", "signature"],
        "caveat": "The chain-order series is a chronology diagnostic. A source predicate reconstructed from slot/index state does not prove its inputs were available to the live process at the candidate receipt's receive timestamp.",
    }
    diagnostics = input_order_diagnostics(input_limit, manifest["cutoff_ms"])
    commands = [
        "cargo build --offline --manifest-path reports/blocked_coin_audit_20261011/helpers/Cargo.toml --target-dir target",
        "target/debug/blocked-source-candidates",
        "python3 reports/blocked_coin_audit_20261011/helpers/sort_receipts_chain_order.py /tmp/ghost_observations_chain_order_20261011.jsonl",
        "target/debug/blocked-source-candidates --chain-order /tmp/ghost_observations_chain_order_20261011.jsonl reports/blocked_coin_audit_20261011/candidate_rows_chain_order.jsonl reports/blocked_coin_audit_20261011/candidate_meta_chain_order.json",
        "python3 reports/blocked_coin_audit_20261011/helpers/finalize_candidate_meta.py",
    ]
    for path in (RECEIVE_META, CHAIN_META):
        meta = json.loads(path.read_text(encoding="utf-8"))
        meta["provenance"] = provenance
        meta["receive_vs_chain_order_check"] = parity
        meta["receive_log_order_diagnostics"] = diagnostics
        meta["reproduction_commands"] = commands
        path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(json.dumps({"parity": parity, "input_prefix_sha256": provenance["input_observations_frozen_prefix_sha256"]}))


if __name__ == "__main__":
    main()
