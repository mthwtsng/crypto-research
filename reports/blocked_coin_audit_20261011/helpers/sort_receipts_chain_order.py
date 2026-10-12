#!/usr/bin/env python3
"""Stream the frozen ReceiptObservation prefix in canonical slot/index order.

The shadow log is append/receive ordered. This bounded sorter buffers only one
slot, keeps complete original JSONL receipts intact, and excludes records after
the manifest byte or receive-time cutoff.
"""
import json
import sys

INPUT = "/home/mthwt/code/Crypto/data/ghost_observations.jsonl"
MANIFEST = "/home/mthwt/code/Crypto/reports/blocked_coin_audit_20261011/MANIFEST.json"


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: sort_receipts_chain_order.py OUTPUT_JSONL")
    output_path = sys.argv[1]
    manifest = json.load(open(MANIFEST, "r", encoding="utf-8"))
    byte_limit = manifest["inputs"]["data/ghost_observations.jsonl"]["size_bytes"]
    cutoff_ms = manifest["cutoff_ms"]

    used = 0
    rows_seen = 0
    eligible = 0
    after_cutoff = 0
    partial_or_outside = 0
    same_slot_inversions = 0
    slot_regressions = 0
    eligible_same_slot_inversions = 0
    eligible_slot_regressions = 0
    duplicate_slot_indexes = 0
    timestamp_regressions = 0
    previous_key = None
    previous_eligible_key = None
    previous_ts = None
    current_slot = None
    buffer = []
    stable_order = 0

    def flush(out):
        nonlocal buffer
        if not buffer:
            return
        buffer.sort(key=lambda item: (item[0], item[1]))
        for _, _, raw in buffer:
            out.write(raw)
        buffer = []

    with open(INPUT, "rb") as source, open(output_path, "wb") as out:
        while used < byte_limit:
            raw = source.readline()
            if not raw:
                break
            if used + len(raw) > byte_limit:
                partial_or_outside = byte_limit - used
                break
            used += len(raw)
            if not raw.endswith(b"\n"):
                partial_or_outside = len(raw)
                break
            receipt = json.loads(raw)
            rows_seen += 1
            received_ms = int(receipt.get("received_at_ms", 0))
            slot = int(receipt.get("slot", 0))
            tx_index = int(receipt.get("transaction_index", 0))
            key = (slot, tx_index)
            if previous_ts is not None and received_ms < previous_ts:
                timestamp_regressions += 1
            previous_ts = received_ms
            if previous_key is not None and key < previous_key:
                if slot < previous_key[0]:
                    slot_regressions += 1
                else:
                    same_slot_inversions += 1
            previous_key = key

            if current_slot is not None and slot != current_slot:
                if slot < current_slot:
                    raise RuntimeError(f"slot regressed: {slot} after {current_slot}")
                flush(out)
            current_slot = slot

            if received_ms > cutoff_ms:
                after_cutoff += 1
                continue
            eligible += 1
            if previous_eligible_key is not None and key < previous_eligible_key:
                if slot < previous_eligible_key[0]:
                    eligible_slot_regressions += 1
                else:
                    eligible_same_slot_inversions += 1
            previous_eligible_key = key
            if buffer and tx_index == buffer[-1][0]:
                duplicate_slot_indexes += 1
            buffer.append((tx_index, stable_order, raw))
            stable_order += 1

        flush(out)

    print(json.dumps({
        "output": output_path,
        "manifest_input_size_bytes": byte_limit,
        "bytes_read": used,
        "rows_seen": rows_seen,
        "eligible_rows_at_or_before_cutoff": eligible,
        "rows_after_cutoff": after_cutoff,
        "same_slot_transaction_index_inversions_in_receive_log": same_slot_inversions,
        "slot_regressions_in_receive_log": slot_regressions,
        "eligible_same_slot_transaction_index_inversions": eligible_same_slot_inversions,
        "eligible_slot_regressions": eligible_slot_regressions,
        "receive_timestamp_regressions": timestamp_regressions,
        "adjacent_duplicate_indexes_within_slot": duplicate_slot_indexes,
        "partial_or_outside_prefix_bytes": partial_or_outside,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
