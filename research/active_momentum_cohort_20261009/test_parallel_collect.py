"""Offline regressions for deterministic queueing and parallel admission."""
import sys
sys.dont_write_bytecode = True

import pathlib
import tempfile
import unittest
from unittest import mock

import parallel_collect as P
import collect_cohort as C


def candidate(mint, source, creation_time=None):
    row = {"mint": mint, "source": source}
    if creation_time is not None:
        row["creation_time"] = creation_time
    return row


class ParallelCollectionTests(unittest.TestCase):
    def test_candidate_queue_matches_daily_insert_and_interleave_order(self):
        start = 0
        shortlist = [
            candidate("cache-a", "cached_creation_sample_prefilter", 100),
            candidate("cache-b", "cached_creation_sample_prefilter", 200),
            candidate("cache-c", "cached_creation_sample_prefilter", 86400 + 100),
        ]
        day0 = [candidate("migration-a", "authenticated_migration_census"), candidate("migration-b", "authenticated_migration_census")]
        day1 = [candidate("migration-c", "authenticated_migration_census"), candidate("migration-d", "authenticated_migration_census")]
        daily = [
            {"day": 0, "decoder_version": "bound_curve_v1", "migrations": list(reversed(day0))},
            {"day": 86400, "decoder_version": "bound_curve_v1", "migrations": list(reversed(day1))},
        ]

        queue, exclusions = P.build_candidate_queue(shortlist, daily, start, 2 * 86400)

        # Repeated insert(0, cached) reverses same-day shortlist order. The
        # collector then takes one row per day before advancing each day.
        sorted_day0 = sorted(day0, key=P._hash_candidate)
        sorted_day1 = sorted(day1, key=P._hash_candidate)
        expected = [
            "cache-b",
            "cache-c",
            "cache-a",
            sorted_day1[0]["mint"],
            sorted_day0[0]["mint"],
            sorted_day1[1]["mint"],
            sorted_day0[1]["mint"],
        ]
        self.assertEqual([row["mint"] for row in queue], expected)
        self.assertEqual(exclusions, [])

    def test_cached_candidate_wins_duplicate_and_duplicate_is_recorded(self):
        start = 0
        cached = candidate("shared-mint", "cached_creation_sample_prefilter", 60)
        migration = candidate("shared-mint", "authenticated_migration_census")
        queue, exclusions = P.build_candidate_queue(
            [cached],
            [{"day": 0, "decoder_version": "bound_curve_v1", "migrations": [migration]}],
            start,
            86400,
        )
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]["source"], "cached_creation_sample_prefilter")
        self.assertEqual(len(exclusions), 1)
        self.assertEqual(exclusions[0]["mint"], "shared-mint")
        self.assertEqual(exclusions[0]["kept_queue_index"], 0)
        self.assertEqual(exclusions[0]["excluded_source"], "authenticated_migration_census")

    def test_dedup_keeps_first_across_daily_interleave(self):
        queue, exclusions = P.build_candidate_queue(
            [],
            [
                {"day": 0, "decoder_version": "bound_curve_v1", "migrations": [candidate("same", "day0"), candidate("day0-only", "day0")]},
                {"day": 86400, "decoder_version": "bound_curve_v1", "migrations": [candidate("same", "day1")]},
            ],
            0,
            2 * 86400,
        )
        self.assertEqual([row["mint"] for row in queue].count("same"), 1)
        self.assertEqual(exclusions[0]["kept_source"], "day0")
        self.assertEqual(exclusions[0]["excluded_source"], "day1")

    def test_ordered_admission_never_exceeds_target(self):
        rows = [candidate(f"mint-{n}", "source") for n in range(6)]
        outcomes = {
            "mint-0": {"status": "verified"},
            "mint-1": {"status": "rejected"},
            "mint-2": {"status": "verified"},
            "mint-3": {"status": "verified"},
            "mint-4": {"status": "verified"},
        }
        prefix = P.ordered_prefix(rows, outcomes, target=2)
        self.assertEqual(prefix["selected"], ["mint-0", "mint-2"])
        self.assertEqual(prefix["rejected"], ["mint-1"])
        self.assertEqual(prefix["cursor"], 3)
        self.assertLessEqual(len(prefix["selected"]), 2)

    def test_scheduler_reserves_target_slots_for_inflight_and_buffered_successes(self):
        target = 2000
        # One spare slot may be assigned; once that task is inflight, no more
        # candidate can be submitted until a rejection frees its reservation.
        self.assertTrue(P.can_submit_candidate(1998, 1, 0, target))
        self.assertFalse(P.can_submit_candidate(1998, 2, 0, target))
        # A verified outcome waiting behind the queue cursor also reserves a
        # slot, even though its worker is no longer inflight.
        self.assertFalse(P.can_submit_candidate(1998, 1, 1, target))
        self.assertTrue(P.can_submit_candidate(1998, 0, 1, target))
        self.assertFalse(P.can_submit_candidate(1999, 0, 1, target))

    def test_resume_salvages_only_valid_current_version_audits(self):
        rows = [candidate("in-manifest", "source"), candidate("audit-only", "source"), candidate("stale", "source")]
        manifest = [{"mint": "in-manifest", "verifier_version": C.VERIFIER_VERSION}]
        valid = {
            "in-manifest": {"mint": "in-manifest", "verifier_version": C.VERIFIER_VERSION, "status": "verified"},
            "audit-only": {"mint": "audit-only", "verifier_version": C.VERIFIER_VERSION, "status": "verified"},
            "stale": {"mint": "stale", "verifier_version": "older", "status": "verified"},
        }
        outcomes = P.seed_known_outcomes(rows, manifest, [], valid, {})
        self.assertEqual(outcomes["in-manifest"]["status"], "verified")
        self.assertEqual(outcomes["audit-only"]["status"], "verified")
        self.assertNotIn("stale", outcomes)

    def test_network_failures_remain_retryable_and_policy_failures_are_final(self):
        self.assertEqual(P.classify_failure("HTTP Error 429: too many requests"), "retryable")
        self.assertEqual(P.classify_failure("historical_block_unavailable", "ValueError"), "retryable")
        self.assertEqual(P.classify_failure("migration_curve_binding_missing", "ValueError"), "retryable")
        self.assertEqual(P.classify_failure("creator_monopoly_at_peak", "ValueError"), "rejected")
        self.assertEqual(P.classify_failure("unsupported_buy_instruction", "ValueError"), "rejected")
        self.assertEqual(P.classify_failure("unsupported_custody_op", "ValueError"), "rejected")
        self.assertEqual(P.classify_failure("unverified_custody", "ValueError"), "rejected")
        self.assertEqual(P.classify_failure("unresolvable_inventory_gap", "ValueError"), "rejected")
        self.assertEqual(P.classify_failure("unresolvable_inventory_gap", "RuntimeError"), "retryable")
        self.assertEqual(P.classify_failure("unrecognized verifier error", "RuntimeError"), "retryable")

    def test_status_redaction_removes_rpc_credentials(self):
        value = P.redact("https://rpc.shyft.to?api_key=secret123 and https://solana-mainnet.g.alchemy.com/v2/secret456")
        self.assertNotIn("secret123", value)
        self.assertNotIn("secret456", value)
        self.assertIn("[REDACTED]", value)

    def test_promotion_replaces_invalid_canonical_audit_and_preserves_old_copy(self):
        mint = "promote-mint"
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp) / "canonical"
            stage = pathlib.Path(temp) / "parallel_stage" / mint
            old_audit = root / "audits" / f"{mint}.json"
            new_audit = stage / "audits" / f"{mint}.json"
            old_bound = root / "bound_curve_tapes" / f"{mint}.json.gz"
            new_bound = stage / "bound_curve_tapes" / f"{mint}.json.gz"
            for path, value in (
                (old_audit, "old invalid audit"),
                (new_audit, "new validated audit"),
                (old_bound, "old invalid tape"),
                (new_bound, "new validated tape"),
            ):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(value)

            with mock.patch.object(P, "P", root):
                promoted = P._promote_stage_artifacts(mint, stage, include_audit=True)

            self.assertIn(f"audits/{mint}.json", promoted)
            self.assertIn(f"bound_curve_tapes/{mint}.json.gz", promoted)
            self.assertEqual(old_audit.read_text(), "new validated audit")
            self.assertEqual(old_bound.read_text(), "new validated tape")
            preserved = list((stage / "_prior_canonical_cache").rglob("*"))
            preserved_files = [path for path in preserved if path.is_file()]
            self.assertEqual(len(preserved_files), 2)
            self.assertCountEqual([path.read_text() for path in preserved_files], ["old invalid audit", "old invalid tape"])

    def test_window_requires_whole_utc_days(self):
        with self.assertRaises(ValueError):
            P.build_candidate_queue([], [{"day": 0, "decoder_version": "bound_curve_v1", "migrations": []}], 0, 86401)

    def test_queue_requires_day_and_current_migration_decoder(self):
        row = candidate("migration", "authenticated_migration_census")
        with self.assertRaisesRegex(ValueError, "migration_census_decoder_version_mismatch"):
            P.build_candidate_queue([], [{"day": 0, "migrations": [row]}], 0, 86400)
        with self.assertRaisesRegex(ValueError, "migration_census_day_order_mismatch"):
            P.build_candidate_queue(
                [], [{"day": 1, "decoder_version": "bound_curve_v1", "migrations": [row]}], 0, 86400
            )


if __name__ == "__main__":
    unittest.main()
