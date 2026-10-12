"""Focused offline regressions for current-run coordinator progress fields."""
import sys
sys.dont_write_bytecode = True

import json
import pathlib
import tempfile
import unittest
from unittest import mock

import parallel_collect as P


class WorkerProgressTests(unittest.TestCase):
    def test_worker_completions_exclude_resumed_and_cached_audits(self):
        fields = P._worker_progress_fields(
            completion_counts={"verified": 2, "rejected": 1, "retryable": 1},
            completed_mints={"worker-verified", "worker-retried"},
            inflight_count=2,
            outcomes={
                "worker-verified": {"status": "verified"},
                "resumed-verified": {"status": "verified"},
                "cached-verified": {"status": "verified"},
                "admitted-verified": {"status": "verified"},
                "rejected": {"status": "rejected"},
            },
            selected_mints={"admitted-verified"},
            accounted_mints={"admitted-verified", "rejected"},
            resumed_staged_mints={"resumed-verified", "admitted-verified"},
            last_worker_status="verified",
        )

        self.assertEqual(fields["total_completed_by_workers"], 4)
        self.assertEqual(fields["worker_completion_counts_this_run"], {
            "verified": 2,
            "rejected": 1,
            "retryable": 1,
        })
        self.assertEqual(fields["worker_progress_scope"].split(";")[0], "current_run_task_completions")
        self.assertEqual(fields["worker_completed_unique_candidates_this_run"], 2)
        self.assertEqual(fields["worker_inflight_count"], 2)
        self.assertEqual(fields["resumed_staged_valid_count"], 2)
        self.assertEqual(fields["resumed_staged_valid_unadmitted_count"], 1)
        self.assertEqual(fields["buffered_verified_count"], 3)
        self.assertEqual(fields["buffered_verified_by_current_run_workers"], 1)
        self.assertEqual(fields["buffered_verified_from_resumed_stages"], 1)
        self.assertEqual(fields["buffered_verified_from_other_cached_outcomes"], 1)

    def test_status_writer_keeps_cursor_and_admissions_separate(self):
        with tempfile.TemporaryDirectory() as temp:
            status_path = pathlib.Path(temp) / "status.json"
            with mock.patch.object(P, "STATUS_PATH", status_path):
                P._write_status(
                    state="collecting",
                    queue_data={"candidate_count": 5, "queue_sha256": "digest"},
                    selected_count=2,
                    rejected_count=1,
                    cursor=3,
                    workers=2,
                    pilot_attempts=None,
                    attempted_this_run=4,
                    retryable_count=1,
                    legacy_audits=2,
                    progress_fields={"total_completed_by_workers": 7},
                )
            payload = json.loads(status_path.read_text())

        self.assertEqual(payload["ordered_prefix_cursor"], 3)
        self.assertEqual(payload["ordered_admitted_coins"], 2)
        self.assertEqual(payload["total_completed_by_workers"], 7)

    def test_resume_stage_scan_includes_valid_tail_independent_of_cursor(self):
        with tempfile.TemporaryDirectory() as temp:
            stage_root = pathlib.Path(temp)
            (stage_root / "later-queue-candidate").mkdir()
            (stage_root / "later-queue-candidate" / "audits").mkdir()
            (stage_root / "later-queue-candidate" / "audits" / "later-queue-candidate.json").write_text('{}')
            (stage_root / "not-in-queue").mkdir()
            with mock.patch.object(P, "STAGE_ROOT", stage_root), mock.patch.object(
                P,
                "_validated_audit",
                side_effect=lambda mint, _root: {"mint": mint} if mint == "later-queue-candidate" else None,
            ):
                staged = P._validated_staged_mints(
                    [{"mint": "head"}, {"mint": "later-queue-candidate"}]
                )

        self.assertEqual(staged, {"later-queue-candidate"})

    def test_heartbeat_interval_is_at_most_thirty_seconds(self):
        self.assertGreater(P.STATUS_HEARTBEAT_SECONDS, 0)
        self.assertLessEqual(P.STATUS_HEARTBEAT_SECONDS, 30)


if __name__ == "__main__":
    unittest.main()
