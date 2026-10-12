"""Offline tests for optional Helius routing and historical proof gates."""
import json
import pathlib
import tempfile
import unittest
from unittest import mock

import rpc_pool as R


class HeliusRoutingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.temp.name)
        self.capabilities = root / "RPC_CAPABILITIES.json"
        self.cache = root / "rpc"
        self.control = root / ".rpc_control"

        self.providers = dict(R.PROVIDERS)
        self.providers["helius"] = "https://mainnet.helius-rpc.com/?api-key=test-only"
        self.patches = [
            mock.patch.object(R, "PROVIDERS", self.providers),
            mock.patch.object(
                R,
                "PROVIDER_ORDER",
                tuple(name for name in ("alchemy", "shyft", "solami", "helius") if name in self.providers),
            ),
            mock.patch.object(R, "CAPABILITIES", self.capabilities),
            mock.patch.object(R, "RPC_CACHE", self.cache),
            mock.patch.object(R, "CONTROL", self.control),
            mock.patch.object(R, "request", side_effect=AssertionError("network RPC forbidden in tests")),
            mock.patch.object(R, "_request_once", side_effect=AssertionError("network RPC forbidden in tests")),
        ]
        for patcher in self.patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self.temp.cleanup)

    @staticmethod
    def _provider_probe(
        *,
        status="ok",
        exact=True,
        routing=True,
        same_blockhash=True,
        same_block_time=True,
    ):
        return {
            "status": status,
            "exact_signature_order_match": exact,
            "routing_eligible": routing,
            "same_blockhash": same_blockhash,
            "same_block_time": same_block_time,
        }

    def _period(self, helius=None, alchemy_first_attempt=True):
        return {
            "alchemy_first_attempt": alchemy_first_attempt,
            "providers": {
                "alchemy": {"status": "ok", "signature_count": 10},
                "shyft": {
                    "status": "ok",
                    "exact_signature_order_match": True,
                    "routing_eligible": False,
                },
                "solami": {
                    "status": "ok",
                    "exact_signature_order_match": False,
                    "routing_eligible": True,
                },
                "helius": helius or self._provider_probe(),
            },
        }

    def _write_capabilities(self, *, aug=None, sep=None):
        report = {
            "probe_version": 1,
            "periods": {
                "2026-08": aug or self._period(),
                "2026-09": sep or self._period(),
            },
            "slot_ranges": {
                "2026-08": {"start_slot": None, "end_slot_exclusive": 100},
                "2026-09": {"start_slot": 100, "end_slot_exclusive": 200},
            },
        }
        self.capabilities.write_text(json.dumps(report))

    @staticmethod
    def _signature_params(slot):
        return [slot, {"transactionDetails": "signatures", "commitment": "finalized"}]

    def _cache_helius_record(self, params):
        path = R._cache_path("getBlock", params)
        R.save(
            path,
            {
                "provider": "helius",
                "method": "getBlock",
                "params": params,
                "result": {"signatures": ["sig-a", "sig-b"]},
            },
        )
        return path

    def test_optional_config_keeps_helius_absent_without_valid_config(self):
        root = pathlib.Path(self.temp.name)
        missing = root / "missing.json"
        base = {"alchemy": "https://example.invalid"}
        self.assertIsNone(R._load_helius_endpoint(missing))
        self.assertEqual(R._provider_endpoints(base, missing), base)

        config = root / "provider.json"
        config.write_text(json.dumps({"helius": "https://mainnet.helius-rpc.com/?api-key=test-only"}))
        self.assertEqual(set(R._provider_endpoints(base, config)), {"alchemy", "helius"})

        config.write_text(json.dumps({"helius": "https://example.invalid/?api-key=test-only"}))
        self.assertEqual(R._provider_endpoints(base, config), base)

    def test_helius_rate_target_and_concurrency_are_independent(self):
        self.assertEqual(R.TARGET_RPS["helius"], 8.0)
        self.assertEqual(R.MAX_IN_FLIGHT["helius"], 4)
        self.assertAlmostEqual(R._provider_interval("helius", "getBlock", 1.0), 0.125)
        # Alchemy continues to use the existing weighted CU budget.
        self.assertAlmostEqual(R._provider_interval("alchemy", "getBlock", 1.0), 0.1)

    def test_both_enabled_month_routes_include_alchemy_and_helius_only(self):
        self._write_capabilities()
        with mock.patch.dict("os.environ", {"COHORT_RPC_PREFERRED_PROVIDER": "helius"}):
            for slot in (50, 150):
                with self.subTest(slot=slot):
                    route = R._route("getBlock", self._signature_params(slot), "a" * 64)
                    self.assertEqual(set(route), {"alchemy", "helius"})
                    self.assertNotIn("shyft", route)
                    self.assertNotIn("solami", route)

    def test_helius_route_requires_every_month_probe_proof(self):
        invalid_probes = (
            {"exact": False},
            {"routing": False},
            {"same_blockhash": False},
            {"same_block_time": False},
            {"status": "error"},
        )
        for invalid in invalid_probes:
            with self.subTest(invalid=invalid):
                helius = self._provider_probe(**invalid)
                self._write_capabilities(aug=self._period(helius=helius))
                route = R._route("getBlock", self._signature_params(50), "b" * 64)
                self.assertEqual(route, ["alchemy"])

        self._write_capabilities(aug=self._period(alchemy_first_attempt=False))
        route = R._route("getBlock", self._signature_params(50), "b" * 64)
        self.assertEqual(route, ["alchemy"])

    def test_helius_block_cache_is_consumed_only_with_exact_month_proof(self):
        params = self._signature_params(50)
        cache = self._cache_helius_record(params)

        self._write_capabilities()
        self.assertIsNotNone(R._read_cache(cache, "getBlock", params))

        for invalid in (
            {"exact": False},
            {"routing": False},
            {"same_blockhash": False},
            {"same_block_time": False},
            {"status": "error"},
        ):
            with self.subTest(invalid=invalid):
                self._write_capabilities(aug=self._period(helius=self._provider_probe(**invalid)))
                self.assertIsNone(R._read_cache(cache, "getBlock", params))

        self._write_capabilities(aug=self._period(alchemy_first_attempt=False))
        self.assertIsNone(R._read_cache(cache, "getBlock", params))

    def test_history_and_full_block_routing_remain_alchemy_only(self):
        self._write_capabilities()
        history_params = [{"address": "wallet"}, {"limit": 1000}]
        self.assertEqual(
            R._route("getTransactionsForAddress", history_params, "c" * 64),
            ["alchemy"],
        )
        self.assertFalse(
            R._cache_provider_allowed("getTransactionsForAddress", history_params, "helius")
        )
        self.assertTrue(
            R._cache_provider_allowed("getTransactionsForAddress", history_params, "alchemy")
        )
        self.assertEqual(
            R._route("getBlock", [50, {"transactionDetails": "full"}], "d" * 64),
            ["alchemy"],
        )


if __name__ == "__main__":
    unittest.main()
