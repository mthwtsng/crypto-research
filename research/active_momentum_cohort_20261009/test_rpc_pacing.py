"""Deterministic tests for the shared RPC pacing and throttle backoff."""
import concurrent.futures
import json
import os
import pathlib
import tempfile
import threading
import unittest
from unittest import mock

import rpc_pool as R


class FakeClock:
    def __init__(self, value=100.0):
        self.value = value

    def now(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


class RpcPacingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.temp.name)
        self.control = root / "control"
        self.events = root / "events.jsonl"
        self.control.mkdir()
        self.control_patch = mock.patch.object(R, "CONTROL", self.control)
        self.events_patch = mock.patch.object(R, "EVENTS", self.events)
        self.control_patch.start()
        self.events_patch.start()
        self.addCleanup(self.control_patch.stop)
        self.addCleanup(self.events_patch.stop)
        self.addCleanup(self.temp.cleanup)
        self.clock = FakeClock()
        self.wall_patch = mock.patch.object(R, "_wall_time", self.clock.now)
        self.wall_patch.start()
        self.addCleanup(self.wall_patch.stop)

    def _state(self, provider="alchemy"):
        path = R._control_path(f"{provider}.pace.json")
        with R._locked_file(path) as fd:
            return R._read_locked_json(fd, {})

    def test_mixed_alchemy_methods_use_weighted_shared_spacing(self):
        with mock.patch.dict(os.environ, {"COHORT_ALCHEMY_CU_PER_SECOND": "400"}):
            self.assertEqual(R._reserve_provider_start("alchemy", "getBlock"), 0)
            first_start = self._state()["next_start"]

            wait = R._reserve_provider_start("alchemy", "getTransactionsForAddress")
            self.assertAlmostEqual(wait, 0.1)
            self.assertEqual(self._state()["next_start"], first_start)
            self.clock.advance(wait)
            self.assertEqual(R._reserve_provider_start("alchemy", "getTransactionsForAddress"), 0)
            history_start = self._state()["next_start"] - self.clock.now()
            self.assertAlmostEqual(history_start, 0.25)

            wait = R._reserve_provider_start("alchemy", "getBlock")
            self.assertAlmostEqual(wait, 0.25)
            self.assertAlmostEqual(
                self._state()["next_start"], self.clock.now() + history_start
            )

    def test_block_rate_ceiling_defaults_to_ten_and_is_configurable(self):
        with mock.patch.dict(
            os.environ, {"COHORT_ALCHEMY_CU_PER_SECOND": "800"}, clear=True
        ):
            self.assertAlmostEqual(R._provider_interval("alchemy", "getBlock", 1.0), 0.1)
            with mock.patch.dict(os.environ, {"COHORT_ALCHEMY_BLOCK_MAX_RPS": "20"}):
                self.assertAlmostEqual(R._provider_interval("alchemy", "getBlock", 1.0), 0.05)

    def test_invalid_budget_and_block_ceiling_are_rejected(self):
        for env, key in (
            ({"COHORT_ALCHEMY_CU_PER_SECOND": "0"}, "COHORT_ALCHEMY_CU_PER_SECOND"),
            ({"COHORT_ALCHEMY_BLOCK_MAX_RPS": "nan"}, "COHORT_ALCHEMY_BLOCK_MAX_RPS"),
        ):
            with self.subTest(key=key), mock.patch.dict(os.environ, env, clear=False):
                with self.assertRaisesRegex(ValueError, key):
                    R._provider_interval("alchemy", "getBlock", 1.0)

    def test_concurrent_callers_share_one_due_start(self):
        barrier = threading.Barrier(8)

        def reserve():
            barrier.wait()
            return R._reserve_provider_start("alchemy", "getBlock")

        with mock.patch.dict(os.environ, {"COHORT_ALCHEMY_CU_PER_SECOND": "0.4"}):
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                waits = list(executor.map(lambda _: reserve(), range(8)))
        self.assertEqual(sum(wait == 0 for wait in waits), 1)
        self.assertTrue(all(wait >= 0 for wait in waits))

    def test_stale_sleeper_rechecks_backoff_before_transport(self):
        with mock.patch.dict(os.environ, {"COHORT_ALCHEMY_CU_PER_SECOND": "400"}):
            self.assertEqual(R._reserve_provider_start("alchemy", "getBlock"), 0)
            sleeps = []
            dispatches = []

            def sleep_and_throttle(delay):
                sleeps.append(delay)
                self.clock.advance(delay)
                if len(sleeps) == 1:
                    R._note_provider_throttle("alchemy", retry_after=5)

            def fake_transport(provider, method, params):
                dispatches.append(self.clock.now())
                return {"ok": True}

            with mock.patch.object(R, "_sleep", side_effect=sleep_and_throttle), mock.patch.object(
                R, "_request_once", side_effect=fake_transport
            ):
                result = R.request("alchemy", "getBlock", [1, {}])

        self.assertEqual(result, {"ok": True})
        self.assertEqual(len(dispatches), 1)
        self.assertGreaterEqual(dispatches[0], 105.1)
        self.assertEqual(len(sleeps), 2)
        telemetry = json.loads(self.events.read_text().strip())
        self.assertEqual(telemetry["pace_algorithm_version"], R.PACE_ALGORITHM_VERSION)

    def test_throttle_burst_halves_once_extends_and_later_burst_halves_again(self):
        R._note_provider_throttle("alchemy", retry_after=0)
        first = self._state()
        self.assertEqual(first["scale"], 0.5)
        self.assertEqual(first["rate_limit_streak"], 1)
        self.assertEqual(first["backoff_until"], 101.0)

        self.clock.advance(0.2)
        R._note_provider_throttle("alchemy", retry_after=0)
        second = self._state()
        self.assertEqual(second["scale"], 0.5)
        self.assertEqual(second["rate_limit_streak"], 1)
        self.assertEqual(second["backoff_until"], 101.2)

        self.clock.advance(0.1)
        R._note_provider_throttle("alchemy", retry_after=8)
        extended = self._state()
        self.assertEqual(extended["scale"], 0.5)
        self.assertEqual(extended["backoff_until"], 108.3)

        self.clock.value = 108.31
        R._note_provider_throttle("alchemy", retry_after=0)
        later = self._state()
        self.assertEqual(later["scale"], 0.25)
        self.assertEqual(later["rate_limit_streak"], 2)
        self.assertEqual(later["backoff_until"], 109.31)


if __name__ == "__main__":
    unittest.main()
