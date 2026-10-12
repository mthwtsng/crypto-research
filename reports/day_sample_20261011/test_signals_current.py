import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import signals_current as S


CREATOR = "creator"
SUPPLY = S.TOTAL_SUPPLY_RAW


def event(user, buy, sol, tokens, spot, reserve):
    return dict(
        user=user,
        buy=buy,
        sol_raw=round(sol * 1e9),
        tokens_raw=tokens,
        vsol_raw=round(spot * 1e15),
        vtokens_raw=1_000_000_000_000_000,
        rsol_raw=round(reserve * 1e9),
    )


def group(signature, slot, tm, reserve, spot, events):
    return dict(
        signature=signature,
        slot=slot,
        block_time=tm,
        events=events,
        state=dict(
            vsol_raw=round(spot * 1e15),
            vtokens_raw=1_000_000_000_000_000,
            rsol_raw=round(reserve * 1e9),
            rtokens_raw=500_000_000_000_000,
        ),
    )


def tape(groups, creation_slot=100, creation_time=0):
    return dict(
        mint="mint-test",
        creator=CREATOR,
        curve="curve-test",
        creation_slot=creation_slot,
        creation_time=creation_time,
        normal=True,
        groups=groups,
        end_time=1000,
    )


def s4_reclaim_tape(reclaim_time=31):
    buyers = [event(f"w{i}", True, 0.05, 1_000_000_000, 0.020, 15.0) for i in range(35)]
    buyers.append(event("seller", True, 0.05, 1_000_000_000, 0.020, 15.0))
    return tape([
        group("breadth", 100, 0, 15.0, 0.020, buyers),
        group("breakout", 101, 30, 16.0, 0.030, [event("breakout-buyer", True, 0.95, 2_000_000_000, 0.030, 16.0)]),
        group("pullback", 102, 30, 16.0, 0.027, [event("seller", False, 0.10, 100_000_000, 0.027, 16.0)]),
        group("reclaim", 103, reclaim_time, 16.5, 0.030, [event("reclaim-buyer", True, 0.05, 100_000_000, 0.030, 16.5)]),
    ])


class SignalCurrentTests(unittest.TestCase):
    def test_canonical_s3_waits_for_separate_confirming_buy_group(self):
        t = tape([
            group("a", 100, 0, 10.0, 0.10, [event("a", True, 0.10, 1_000_000, 0.10, 10.0)]),
            group("b", 100, 1, 10.5, 0.11, [event("b", True, 0.10, 1_000_000, 0.11, 10.5)]),
            group("dip", 101, 2, 10.0, 0.08, [event("a", False, 1.50, 100_000, 0.08, 10.0)]),
            group("confirm-1", 102, 3, 10.2, 0.085, [event("a", True, 0.05, 100_000, 0.085, 10.2)]),
            group("confirm-2", 103, 4, 10.4, 0.09, [event("c", True, 0.05, 100_000, 0.09, 10.4)]),
        ])
        partial, _ = S.detect(dict(t, groups=t["groups"][:4]), mode="canonical")
        full, _ = S.detect(t, mode="canonical")
        s3 = [row for row in full if row["rule"] == "s3_deadman"]
        self.assertFalse(any(row["rule"] == "s3_deadman" for row in partial))
        self.assertEqual(len(s3), 1)
        self.assertEqual(s3[0]["signal_signature"], "confirm-2")
        self.assertEqual(s3[0]["confirmation_buy_groups"], 2)

    def test_current_prefix_cannot_use_future_reclaim(self):
        t = s4_reclaim_tape()
        before_breakout = dict(t, groups=t["groups"][:1])
        after_breakout = dict(t, groups=t["groups"][:2])
        after_pullback = dict(t, groups=t["groups"][:3])
        self.assertEqual(S.detect(before_breakout, mode="current")[0], [])
        self.assertEqual(S.detect(after_breakout, mode="current")[0], [])
        self.assertEqual(S.detect(after_pullback, mode="current")[0], [])
        signals, _ = S.detect(t, mode="current")
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["rule"], "s4_upper_ath")
        self.assertEqual(signals[0]["original_signal_signature"], "breakout")
        self.assertEqual(signals[0]["signal_signature"], "reclaim")

    def test_current_s3_counts_trade_events_and_audits_same_transaction_confirmation(self):
        initial = [event(f"w{i}", True, 0.05, 1_000_000, 0.10, 10.0) for i in range(35)]
        initial.append(event("seller", True, 0.05, 1_000_000, 0.10, 10.0))
        t = tape([
            group("breadth", 100, 0, 10.0, 0.10, initial),
            group("dip", 101, 1, 10.0, 0.08, [event("seller", False, 1.50, 500_000, 0.08, 10.0)]),
            group("same-tx-confirmations", 102, 2, 10.2, 0.085, [
                event("buyer-a", True, 0.05, 100_000, 0.085, 10.2),
                event("buyer-b", True, 0.05, 100_000, 0.085, 10.2),
            ]),
        ])
        signals, _ = S.detect(t, mode="current")
        s3 = [row for row in signals if row["rule"] == "s3_deadman"]
        self.assertEqual(len(s3), 1)
        self.assertEqual(s3[0]["signal_signature"], "same-tx-confirmations")
        self.assertEqual(s3[0]["confirmation_trade_count"], 2)
        self.assertEqual(s3[0]["confirmation_distinct_buyers"], 2)
        self.assertTrue(s3[0]["same_transaction_confirmation_possible"])
        self.assertEqual(s3[0]["confirmation_completed_groups"], 1)

    def test_current_s3_counts_events_but_waits_for_completed_transaction_buy(self):
        initial = [event(f"w{i}", True, 0.05, 1_000_000, 0.10, 10.0) for i in range(35)]
        initial.append(event("seller", True, 0.05, 1_000_000, 0.10, 10.0))
        t = tape([
            group("breadth", 100, 0, 10.0, 0.10, initial),
            group("dip", 101, 1, 10.0, 0.08, [event("seller", False, 1.50, 500_000, 0.08, 10.0)]),
            group("same-tx-buys-then-sell", 102, 2, 10.2, 0.085, [
                event("buyer-a", True, 0.05, 100_000, 0.085, 10.2),
                event("buyer-b", True, 0.05, 100_000, 0.085, 10.2),
                event("seller", False, 0.01, 10_000, 0.085, 10.2),
            ]),
        ])
        signals, _ = S.detect(t, mode="current")
        self.assertFalse(any(row["rule"] == "s3_deadman" for row in signals))

    def test_current_reclaim_accepts_exact_180_second_boundary_only_after_pullback(self):
        inside, _ = S.detect(s4_reclaim_tape(reclaim_time=210), mode="current")
        outside, _ = S.detect(s4_reclaim_tape(reclaim_time=211), mode="current")
        self.assertEqual([row["signal_signature"] for row in inside], ["reclaim"])
        self.assertEqual(outside, [])

    def test_local_bundle_boundary_is_strictly_greater_than_twenty_percent(self):
        twenty_pct = 200_000_000_000_000
        events = [event(f"h{i}", True, 0.05, twenty_pct // 10, 0.00005, 5.0) for i in range(10)]
        t = tape([group("launch", 100, 0, 5.0, 0.00005, events)])
        exact = S._local_screen(t, 0)
        self.assertEqual(exact["first_two_slot_buy_supply_pct"], 20.0)
        self.assertNotIn("block_0_bundle_rule_gt20pct_first_two_slots", exact["reasons"])
        events[0]["tokens_raw"] += 1
        over = S._local_screen(t, 0)
        self.assertIn("block_0_bundle_rule_gt20pct_first_two_slots", over["reasons"])

    def test_local_mode_admits_only_local_subset_and_names_missing_holder_gate(self):
        signals, audit = S.detect(s4_reclaim_tape(), mode="current", screen_mode="local")
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["screen_status"], "local_only")
        self.assertEqual(signals[0]["holder_status"], "not_applied_historical_missing")
        self.assertEqual(audit["screen_mode"], "local")
        entry = next(row for row in audit["screen_results"] if row["phase"] == "entry")
        self.assertEqual(entry["status"], "local_only")
        self.assertEqual(entry["holder_status"], "not_applied_historical_missing")

    def test_screen_rejection_does_not_suppress_later_current_candidate(self):
        # The first S4 arm is rejected by the local top-3 concentration gate.
        # After those wallets sell, a fresh S4 predicate can pass and arm the
        # 8% pullback/reclaim wrapper.
        initial = [event(f"w{i}", True, 0.05, 1_000_000_000, 0.020, 15.0) for i in range(35)]
        initial.extend(event(f"whale{i}", True, 0.05, 70_000_000_000_000, 0.020, 15.0) for i in range(3))
        t = tape([
            group("base", 100, 0, 15.0, 0.020, initial),
            group("s4-blocked", 101, 1, 16.0, 0.030, [event("arm-a", True, 0.95, 1_000_000_000, 0.030, 16.0)]),
            group("sell-whales-and-rearm", 102, 2, 16.0, 0.030, [
                event("whale0", False, 0.10, 70_000_000_000_000, 0.029, 16.0),
                event("whale1", False, 0.10, 70_000_000_000_000, 0.029, 16.0),
                event("whale2", False, 0.10, 70_000_000_000_000, 0.029, 16.0),
                event("arm-b", True, 0.95, 1_000_000_000, 0.030, 16.0),
            ]),
            group("pullback", 103, 3, 16.0, 0.027, [event("seller", False, 0.10, 100_000_000, 0.027, 16.0)]),
            group("reclaim", 104, 4, 16.5, 0.030, [event("reclaim-buyer", True, 0.05, 100_000_000, 0.030, 16.5)]),
        ])
        signals, audit = S.detect(t, mode="current", screen_mode="local")
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["original_signal_signature"], "sell-whales-and-rearm")
        arm_rows = [row for row in audit["screen_results"] if row["phase"] == "arm"]
        self.assertEqual([row["status"] for row in arm_rows], ["blocked", "local_only"])

    def test_onchain_mode_keeps_missing_holder_history_unknown(self):
        signals, audit = S.detect(s4_reclaim_tape(), mode="current", screen_mode="onchain")
        self.assertEqual(signals, [])
        entry = next(row for row in audit["screen_results"] if row["phase"] == "entry")
        self.assertEqual(entry["status"], "unknown")
        self.assertIn("no_timestamped_prior_holder_screen", entry["reasons"])

    def test_current_screen_requires_a_fresh_timestamped_clear_holder_row(self):
        t = s4_reclaim_tape()
        clear = {
            "mint": t["mint"],
            "report": {"status": "clear", "audit_completed_at_ms": 30_000},
            "policy": {"low_balance_lamports": 300_000_000, "low_sol_supply_block_pct": 50.0, "top10_low_sol_block_count": 8},
        }
        fresh, _ = S.detect(t, mode="current", screen_mode="onchain", holder_screens=[clear])
        self.assertEqual([row["signal_signature"] for row in fresh], ["reclaim"])
        stale = {"mint": t["mint"], "report": {"status": "clear", "audit_completed_at_ms": 0}}
        missed, audit = S.detect(t, mode="current", screen_mode="onchain", holder_screens=[stale])
        self.assertEqual(missed, [])
        entry = next(row for row in audit["screen_results"] if row["phase"] == "entry")
        self.assertEqual(entry["status"], "unknown")
        self.assertEqual(entry["reasons"], ["holder_screen_stale"])

    def test_holder_raw_evidence_recomputes_stale_policy_status_at_current_thresholds(self):
        evidence = [
            {"summed_token_amount_raw": str(30_000_000_000_000), "sol_balance_lamports": 500_000_000}
            for _ in range(10)
        ]
        old_row = {
            "mint": "mint-test",
            "report": {"status": "blocked", "audit_completed_at_ms": 30_000, "evidence": evidence, "unknown_wallets": 0},
            "policy": {"low_balance_lamports": 1_000_000_000, "low_balance_fraction_gte": 0.5},
        }
        verdict = S._holder_verdict([old_row], "mint-test", 30_000)
        self.assertEqual(verdict["status"], "clear")
        self.assertTrue(verdict["raw_policy_recomputed"])


if __name__ == "__main__":
    unittest.main()
