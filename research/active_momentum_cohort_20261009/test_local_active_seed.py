import gzip
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import local_active_seed as S


def _utc_timestamp(value):
    import datetime

    return int(datetime.datetime.fromisoformat(value).replace(tzinfo=datetime.timezone.utc).timestamp())


def _creation(mint, timestamp, curve="curve-address", user="creator-address"):
    return {
        "mint": mint,
        "bonding_curve": curve,
        "user": user,
        "creator": user,
        "timestamp": timestamp,
        "virtual_token_reserves": 1_073_000_000_000_000,
        "virtual_sol_reserves": 30_000_000_000,
        "real_token_reserves": 793_100_000_000_000,
        "token_total_supply": 1_000_000_000_000_000,
        "token_program": "token-program",
        "is_mayhem_mode": False,
        "is_holder_reward": False,
        "quote_mint": "11111111111111111111111111111111",
    }


def _tx(signature, slot, index, block_time):
    return {
        "blockTime": block_time,
        "slot": slot,
        "transactionIndex": index,
        "transaction": {"signatures": [signature], "message": {"instructions": []}},
        "meta": {"err": None, "innerInstructions": [], "logMessages": []},
    }


def _write_raw(raw_dir, mint, creation_time, transactions=None, terminal=False):
    raw_dir.mkdir(parents=True, exist_ok=True)
    creation = _creation(mint, creation_time)
    txs = transactions or [_tx("creation-signature", 100, 0, creation_time)]
    value = {
        "mint": mint,
        "creation_metadata": creation,
        "requested_end_time": creation_time + 3600,
        "decision_end_time": creation_time + 1800,
        "transactions": txs,
    }
    path = raw_dir / f"{mint}.json.gz"
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        json.dump(value, stream)
    return path, creation


class LocalActiveSeedTests(unittest.TestCase):
    def test_queue_is_bounded_and_interleaves_utc_days(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = pathlib.Path(temporary)
            raw_dir = base / "source" / "raw_curves"
            entries = [
                ("aug18-a", "2026-08-18T01:00:00"),
                ("aug18-b", "2026-08-18T03:00:00"),
                ("aug19-a", "2026-08-19T02:00:00"),
                ("sep07-a", "2026-09-07T22:00:00"),
                ("sep08-a", "2026-09-08T00:00:01"),
            ]
            manifest_rows = []
            for mint, iso in entries:
                created = _utc_timestamp(iso)
                raw_dir.mkdir(parents=True, exist_ok=True)
                path = raw_dir / f"{mint}.json.gz"
                header = {
                    "mint": mint,
                    "creation_metadata": _creation(mint, created),
                    "requested_end_time": created + 3600,
                    "decision_end_time": created + 1800,
                    "transactions": ["a very large array that queue loading must not decode"],
                }
                # Keep a large suffix to ensure the queue reads only the gzip prefix.
                with gzip.open(path, "wt", encoding="utf-8") as stream:
                    stream.write(json.dumps(header)[:-1] + ",\"transactions\":[" + ("x" * 400_000))
                manifest_rows.append(
                    {
                        "mint": mint,
                        "file": path.name,
                        "total_transactions": 30,
                        "peak_reserve_sol": 18_973.4,
                        "unique_buyers": 15,
                        "creator": "creator-address",
                    }
                )
            manifest_path = base / "ACTIVE_COINS_MANIFEST.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "total_raw": 10_080,
                        "total_active": len(manifest_rows),
                        "filter": {"tx": 30, "peak_sol": 8, "buyers": 15},
                        "coins": manifest_rows,
                    }
                )
            )

            queue = S.load_local_candidates(manifest_path, raw_dir)
            self.assertEqual(
                [row["mint"] for row in queue],
                ["aug18-a", "aug19-a", "sep07-a", "aug18-b", "sep08-a"],
            )
            self.assertEqual(queue[0]["source"], "local_active_manifest_prefilter")
            self.assertIsNone(queue[0]["creation_slot"])
            self.assertEqual(queue[0]["manifest_prefilter"]["trust"].split(";")[0], "prefilter_snapshot_only")
            self.assertLessEqual(queue[0]["raw_header"]["bounded_prefix_chars_read"], S.HEADER_CHUNK_CHARS)

    def test_import_returns_migration_coverage_certificate(self):
        with tempfile.TemporaryDirectory() as temporary:
            source_root = pathlib.Path(temporary) / "source"
            raw_dir = source_root / "raw_curves"
            start = S.START_TIME + 123
            mint = "candidate-mint"
            migration_tx = _tx("migration-signature", 101, 0, start + 5)
            creation_tx = _tx("creation-signature", 100, 0, start)
            raw_path, creation = _write_raw(raw_dir, mint, start, [migration_tx, creation_tx])
            candidate = {
                "mint": mint,
                "creation": creation,
                "creation_metadata": creation,
                "creation_time": start,
                "source": S.SOURCE,
                "local_raw_path": str(raw_path),
                "local_source_root": str(source_root),
            }
            fake_decoder = mock.Mock()
            fake_decoder.creations.side_effect = lambda tx: [creation] if tx["transaction"]["signatures"][0] == "creation-signature" else []
            fake_decoder.events.return_value = []
            fake_hashes = {
                "freeze_sha256": "f" * 64,
                "freeze_pinned_at": "2026-10-09T00:00:00Z",
                "code": {
                    "research/frozen_21day_validation_20261008/collect_validation.py": {"sha256": "c" * 64},
                    "research/day_general_20261004/helpers/decoder.py": {"sha256": "d" * 64},
                    "research/day_general_20261004/helpers/OFFICIAL_PUMP_IDL.json": {"sha256": "i" * 64},
                },
            }
            migration = {
                "mint": mint,
                "pool": "pool-address",
                "bonding_curve": "curve-address",
                "signature": "migration-signature",
                "slot": 101,
                "index": 0,
                "time": start + 5,
            }
            with (
                mock.patch.object(S, "_load_pinned_decoder", return_value=(fake_decoder, fake_hashes)),
                mock.patch.object(S, "_migration_decoder", return_value=object()),
                mock.patch.object(S, "_decoded_migrations", side_effect=lambda tx, *_: [migration] if tx["transaction"]["signatures"][0] == "migration-signature" else []),
            ):
                imported = S.import_source(candidate)

            self.assertTrue(imported["coverage"]["exhausted"])
            self.assertEqual(imported["coverage"]["curve_completion_kind"], "authenticated_migration")
            self.assertTrue(imported["coverage"]["curve_lifetime_complete"])
            self.assertTrue(imported["coverage"]["curve_observation_complete"])
            self.assertEqual(imported["creation_signature"], "creation-signature")
            self.assertEqual([tx["slot"] for tx in imported["transactions"]], [100, 101])
            self.assertEqual(imported["requested_end_time"], start + 245)
            self.assertEqual(imported["source_provenance"]["source_sha256"], S._sha256_file(raw_path))

    def test_nonterminal_first_hour_imports_without_lifetime_claim(self):
        with tempfile.TemporaryDirectory() as temporary:
            source_root = pathlib.Path(temporary) / "source"
            raw_dir = source_root / "raw_curves"
            start = S.START_TIME + 500
            mint = "nonterminal-mint"
            path, creation = _write_raw(raw_dir, mint, start)
            candidate = {
                "mint": mint,
                "creation_metadata": creation,
                "creation_time": start,
                "source": S.SOURCE,
                "local_raw_path": str(path),
                "local_source_root": str(source_root),
            }
            fake_decoder = mock.Mock()
            fake_decoder.creations.return_value = [creation]
            fake_decoder.events.return_value = []
            fake_hashes = {"code": {"research/frozen_21day_validation_20261008/collect_validation.py": {"sha256": "c" * 64}, "research/day_general_20261004/helpers/decoder.py": {"sha256": "d" * 64}}}
            with (
                mock.patch.object(S, "_load_pinned_decoder", return_value=(fake_decoder, fake_hashes)),
                mock.patch.object(S, "_migration_decoder", return_value=object()),
                mock.patch.object(S, "_decoded_migrations", return_value=[]),
            ):
                imported = S.import_source(candidate)
            self.assertTrue(imported["coverage"]["exhausted"])
            self.assertEqual(imported["coverage"]["curve_completion_kind"], "fixed_first_hour_observation")
            self.assertFalse(imported["coverage"]["curve_lifetime_complete"])
            self.assertTrue(imported["coverage"]["curve_observation_complete"])
            self.assertEqual(imported["requested_end_time"], start + 3599)
            self.assertEqual(imported["coverage"]["upper_time"], start + 3599)


if __name__ == "__main__":
    unittest.main()
