"""Synthetic checks for the current-shadow derivative's policy and accounting."""
import contextlib
import hashlib
import importlib.util
import pathlib
import sys
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, "/tmp/amm_research_deps")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CURRENT_PATH = pathlib.Path(__file__).with_name("current_engine.py")
BASE_PATH = ROOT / "research/core_plan_audit_20261007/engine.py"
CURRENT = load_module("day_sample_current_engine_test", CURRENT_PATH)
BASE = load_module("day_sample_approved_engine_test", BASE_PATH)
LEDGER = load_module("day_sample_core_ledger_test", ROOT / "research/core_plan_audit_20261007/ledger.py")

L = 10**9
BILL = 500_000_000
NETWORK_FEE = 1_505_000
ENTRY_COST = BILL + NETWORK_FEE


def quote_for_roi(roi, *, realized=0, accumulated_fees=NETWORK_FEE):
    """Create an executable quote yielding the requested net ROI in engine.roi()."""
    return round(roi * ENTRY_COST + BILL + accumulated_fees + NETWORK_FEE - realized)


def state(roi=0.0, *, quote_raw=None, quote_tokens=100, rtokens=1_000, rsol=100 * L, spot=1.0):
    return dict(
        vsol_raw=round(spot * L),
        vtokens_raw=L,
        rsol_raw=rsol,
        rtokens_raw=rtokens,
        fee_bps=0,
        creator_fee_bps=0,
        quote_raw=quote_for_roi(roi) if quote_raw is None else quote_raw,
        quote_tokens=quote_tokens,
    )


def group(signature, slot, when, value, venue="curve"):
    return dict(
        signature=signature,
        slot=slot,
        index=0,
        time=when,
        block_time=when,
        venue=venue,
        state=value,
        events=[],
        trades=[],
        tokenpre={},
        other_liquidity_events=[],
    )


def tape(groups, *, end_time=1_000, inventory_key="wallet"):
    return dict(groups=groups, end_time=end_time, curve="fixture", inventory_key=inventory_key)


def signal(rule, *, signature="signal", trough=None):
    return dict(
        mint="fixture-mint",
        signal_signature=signature,
        slot=0,
        time=0,
        rule=rule,
        trough_spot=trough,
    )


@contextlib.contextmanager
def mocked_replay(*, buy_tokens=None):
    """Stub only quote/clock adapters; run the real current simulate function."""
    token_iter = iter(buy_tokens or [100, 100])

    def buy(_st, _ticket):
        return BILL, next(token_iter)

    def curve_sell(st, amount):
        supply = st.get("quote_tokens", 100)
        return st["quote_raw"] * amount // supply, amount

    def amm_sell(st, amount):
        supply = st.get("quote_tokens", 100)
        return {"total": st["quote_raw"] * amount // supply, "base": amount}

    def apply(_st, g, hist, custody):
        return dict(g["state"]), hist, custody, dict(g), None

    def advance(_st, g, hist, custody):
        return dict(g["state"]), hist, custody, None

    with contextlib.ExitStack() as stack:
        stack.enter_context(patch.object(CURRENT.O, "branch", side_effect=lambda *_a, **_k: ("same", 0)))
        stack.enter_context(patch.object(CURRENT.O, "landing", side_effect=lambda _gs, index, slot, _br: (index, slot)))
        stack.enter_context(patch.object(CURRENT.O, "block_at", side_effect=lambda slot: (slot, slot)))
        stack.enter_context(patch.object(CURRENT.W, "timer_slot", side_effect=lambda _t, _entry, target: target))
        stack.enter_context(patch.object(CURRENT.A, "buy", side_effect=buy))
        stack.enter_context(patch.object(CURRENT.A, "fee", side_effect=lambda _q, _bps: 0))
        stack.enter_context(patch.object(CURRENT.A, "sell", side_effect=curve_sell))
        stack.enter_context(patch.object(CURRENT.A, "moved", side_effect=lambda st, *_a: dict(st)))
        stack.enter_context(patch.object(CURRENT.A.build, "inventory", return_value={}))
        stack.enter_context(patch.object(CURRENT.A, "apply", side_effect=apply))
        stack.enter_context(patch.object(CURRENT.M.A, "sell", side_effect=amm_sell))
        stack.enter_context(patch.object(CURRENT.M, "moved", side_effect=lambda st, *_a: dict(st)))
        stack.enter_context(patch.object(CURRENT.M, "advance", side_effect=advance))
        stack.enter_context(
            patch.object(
                CURRENT,
                "opening_state",
                side_effect=lambda _curve, g, _t, hist, custody: (dict(g["state"]), hist, custody, None),
            )
        )
        yield


def completed_partial_roi_quote(target_roi, tranche_fraction, *, previous_realized=0, previous_fees=NETWORK_FEE):
    full = quote_for_roi(target_roi, realized=previous_realized, accumulated_fees=previous_fees)
    delivered = full * tranche_fraction // 10_000
    return full, delivered


class CurrentEngineTests(unittest.TestCase):
    def run_current(self, rule, groups, *, end_time=1_000, cfg=None, trough=None, inventory_key="wallet"):
        with mocked_replay():
            return CURRENT.simulate(
                tape(groups, end_time=end_time, inventory_key=inventory_key),
                signal(rule, trough=trough),
                "fast",
                "lower",
                0.5,
                cfg=cfg,
            )

    def test_source_hash_is_pinned_to_approved_engine(self):
        digest = hashlib.sha256(BASE_PATH.read_bytes()).hexdigest()
        self.assertEqual(CURRENT.SOURCE_ENGINE_PATH, "research/core_plan_audit_20261007/engine.py")
        self.assertEqual(CURRENT.SOURCE_ENGINE_SHA256, digest)

    def test_untriggered_current_derivative_matches_approved_engine_accounting(self):
        groups = [group("signal", 0, 0, state(0.0))]
        t = tape(groups, end_time=20)
        s = signal("s1_dev_absorption")
        with mocked_replay(buy_tokens=[100, 100, 100, 100]):
            # Disable the approved engine's research-only legacy short timeout
            # to compare the shared open-position accounting/censoring path.
            cfg = {"min_tokens_bps": 9700, "s1_dynamic_exit": True}
            old = BASE.simulate(t, s, "fast", "lower", 0.5, cfg=cfg)
            current = CURRENT.simulate(t, s, "fast", "lower", 0.5, cfg=cfg)
        shared = ("status", "net", "mark", "entry_bill", "entry_tokens", "remaining", "reason", "legs", "entry_position", "close_time")
        self.assertEqual({k: old.get(k) for k in shared}, {k: current.get(k) for k in shared})
        self.assertEqual(current["status"], "unresolved")
        self.assertEqual(current["legs"], [], "coverage end must not liquidate an undefined runner")

    def test_current_entry_guard_accepts_exactly_90_percent_token_retention(self):
        groups = [group("signal", 0, 0, state(0.0))]
        with mocked_replay(buy_tokens=[10_000, 9_000]):
            result = CURRENT.simulate(
                tape(groups, end_time=10), signal("s1_dev_absorption"), "fast", "lower", 0.5,
                cfg={"min_tokens_bps": 9700},
            )
        self.assertEqual(result["status"], "unresolved")
        self.assertEqual(result["entry_tokens"], 9_000)

    def test_entry_roi_denominator_includes_entry_network_fee(self):
        initial = state(0.20)
        result = self.run_current("s1_dev_absorption", [group("signal", 0, 0, initial)], end_time=10)
        self.assertAlmostEqual(result["entry_roi"], 0.20, places=8)
        self.assertEqual(result["entry_bill"], BILL)
        self.assertEqual(result["entry_bill"] + NETWORK_FEE, ENTRY_COST)

    def test_capped_curve_quote_matches_rust_max_payable_formula(self):
        depleted = dict(
            vsol_raw=1_000,
            vtokens_raw=10_000,
            rsol_raw=10,
            rtokens_raw=1_000,
            fee_bps=100,
            creator_fee_bps=300,
        )
        with patch.object(CURRENT.A, "sell", return_value=None):
            quote = CURRENT.curve_sell_capped(depleted, 2_000)
        self.assertEqual(quote, (8, 10, 111))
        self.assertLessEqual(quote[1], depleted["rsol_raw"])
        next_gross = depleted["vsol_raw"] * 112 // (depleted["vtokens_raw"] + 112)
        self.assertGreater(next_gross, depleted["rsol_raw"])

    def test_full_capped_exit_records_only_paid_tokens_and_explicit_writeoff(self):
        groups = [
            group("signal", 0, 0, state(0.0)),
            group("dump", 1, 1, state(-0.20)),
        ]

        def capped_on_dump(st, requested):
            if st["quote_raw"] == quote_for_roi(-0.20):
                return quote_for_roi(-0.20), 1, min(requested, 60)
            return quote_for_roi(0.0), 1, requested

        with mocked_replay(), patch.object(CURRENT, "curve_sell_capped", side_effect=capped_on_dump):
            result = CURRENT.simulate(tape(groups), signal("s1_dev_absorption"), "fast", "lower", 0.5)
        self.assertEqual(result["status"], "closed")
        self.assertEqual(result["legs"][0]["requested_tokens"], 100)
        self.assertEqual(result["legs"][0]["tokens"], 60)
        self.assertEqual(result["legs"][0]["written_off_tokens"], 40)
        self.assertEqual(result["remaining"], 0)

    def test_partial_capped_tranche_preserves_unsold_inventory(self):
        groups = [group("signal", 0, 0, state(0.0)), group("rally", 1, 1, state(0.25))]

        def capped_tranche(st, requested):
            if st["quote_raw"] == quote_for_roi(0.25):
                return quote_for_roi(0.25), 1, min(requested, 30)
            return quote_for_roi(0.0), 1, requested

        with mocked_replay(), patch.object(CURRENT, "curve_sell_capped", side_effect=capped_tranche):
            result = CURRENT.simulate(tape(groups, end_time=10), signal("s1_dev_absorption"), "fast", "lower", 0.5)
        self.assertEqual(result["status"], "unresolved")
        self.assertEqual(result["legs"][0]["requested_tokens"], 40)
        self.assertEqual(result["legs"][0]["tokens"], 30)
        self.assertEqual(result["legs"][0]["written_off_tokens"], 0)
        self.assertEqual(result["remaining"], 70)

    def test_s1_sells_40_percent_at_25_and_trails_remaining_15_percentage_points(self):
        up_quote, up_partial = completed_partial_roi_quote(0.25, 4_000)
        down_quote = quote_for_roi(0.09, realized=up_partial, accumulated_fees=2 * NETWORK_FEE)
        groups = [
            group("signal", 0, 0, state(0.0)),
            group("up", 1, 1, state(0.25, quote_raw=up_quote)),
            group("down", 2, 2, state(0.09, quote_tokens=60, quote_raw=down_quote)),
        ]
        result = self.run_current("s1_dev_absorption", groups)
        self.assertEqual(result["status"], "closed")
        self.assertEqual([(x["tokens"], x["reason"]) for x in result["legs"]], [(40, "tailored_40pct_profit_target"), (60, "tailored_runner_trail")])
        self.assertEqual(result["legs"][0]["delivery"], "reactive_placement")

    def test_s1_trough_invalidation_precedes_first_tranche(self):
        groups = [
            group("signal", 0, 0, state(0.0)),
            group("up-below-trough", 1, 1, state(0.25, spot=0.10)),
        ]
        result = self.run_current("s1_dev_absorption", groups, trough=0.20)
        self.assertEqual(result["legs"][0]["reason"], "floor_invalidation")
        self.assertEqual(result["legs"][0]["tokens"], 100)

    def test_s2_plus20_ratchet_arms_before_the_plus30_tranche(self):
        groups = [
            group("signal", 0, 0, state(0.0)),
            group("arm", 1, 1, state(0.20)),
            group("back-to-even", 2, 2, state(0.0)),
        ]
        result = self.run_current("s2_survival_shelf", groups)
        self.assertEqual(result["legs"][0]["reason"], "breakeven_ratchet")
        self.assertEqual(result["legs"][0]["tokens"], 100)

    def test_s2_curve_reserve_floor_precedes_plus30_tranche(self):
        groups = [
            group("signal", 0, 0, state(0.0)),
            group("reserve-floor-and-target", 1, 1, state(0.30, rsol=9_800_000_000)),
        ]
        result = self.run_current("s2_survival_shelf", groups)
        self.assertEqual(result["legs"][0]["reason"], "shelf_invalidation")
        self.assertEqual(result["legs"][0]["tokens"], 100)

    def test_s2_tranche_and_15_point_remainder_trail(self):
        up_quote, up_partial = completed_partial_roi_quote(0.30, 4_000)
        down_quote = quote_for_roi(0.14, realized=up_partial, accumulated_fees=2 * NETWORK_FEE)
        groups = [
            group("signal", 0, 0, state(0.0)),
            group("target", 1, 1, state(0.30, quote_raw=up_quote)),
            group("trail", 2, 2, state(0.14, quote_tokens=60, quote_raw=down_quote)),
        ]
        result = self.run_current("s2_survival_shelf", groups)
        self.assertEqual([leg["reason"] for leg in result["legs"]], ["tailored_40pct_profit_target", "tailored_runner_trail"])
        self.assertEqual([leg["tokens"] for leg in result["legs"]], [40, 60])

    def test_s3_trail_is_active_before_18_second_loss_grace(self):
        groups = [
            group("signal", 0, 0, state(0.0)),
            group("arm", 1, 1, state(0.20)),
            group("trail", 2, 2, state(0.08)),
        ]
        result = self.run_current("s3_deadman", groups)
        self.assertEqual(result["legs"][0]["reason"], "runner_trail")
        self.assertEqual(result["legs"][0]["time"], 2)

    def test_s3_minus18_stop_fires_on_grace_heartbeat_without_a_new_trade(self):
        groups = [
            group("signal", 0, 0, state(0.0)),
            group("below-stop", 1, 1, state(-0.19)),
        ]
        result = self.run_current("s3_deadman", groups, end_time=30)
        self.assertEqual(result["legs"][0]["reason"], "relative_price_stop")
        self.assertEqual(result["legs"][0]["timer_target"], 18)
        self.assertEqual(result["legs"][0]["time"], 18)
        self.assertEqual(result["legs"][0]["delivery"], "reactive_placement")

    def test_s3_exact_grace_timestamp_processes_the_group_before_timer(self):
        groups = [group("signal", 0, 0, state(0.0)), group("at-deadline", 18, 18, state(-0.19))]
        result = self.run_current("s3_deadman", groups, end_time=30)
        self.assertEqual(result["legs"][0]["reason"], "relative_price_stop")
        self.assertIsNone(result["legs"][0]["timer_target"], "exact-time group is evaluated as a market update")
        self.assertEqual(result["legs"][0]["time"], 18)

    def test_s3_timeout_supports_one_and_three_produced_slot_sensitivities(self):
        groups = [group("signal", 0, 0, state(0.0))]
        groups.extend(group(f"quiet-{slot}", slot, slot, state(0.0)) for slot in range(60, 66))
        for delay, expected_slot in ((1, 61), (3, 63)):
            with self.subTest(scheduled_slots=delay), mocked_replay():
                result = CURRENT.simulate(
                    tape(groups, end_time=100),
                    signal("s3_deadman"),
                    "fast",
                    "lower",
                    0.5,
                    cfg={"scheduled_slots": delay},
                )
            leg = result["legs"][0]
            self.assertEqual(leg["reason"], "s3_timeout")
            self.assertEqual(leg["scheduled_slots"], delay)
            self.assertEqual(leg["landing_slot"], expected_slot)
            self.assertGreaterEqual(leg["time"], leg["timer_target"])

    def test_s4_uses_relative_wealth_trail_and_disables_catastrophic_label_after_tranche(self):
        target_quote, half = completed_partial_roi_quote(0.20, 5_000)
        deep_quote = quote_for_roi(-0.23, realized=half, accumulated_fees=2 * NETWORK_FEE)
        groups = [
            group("signal", 0, 0, state(0.0)),
            group("half", 1, 1, state(0.20, quote_raw=target_quote)),
            group("after-half", 2, 2, state(-0.23, quote_tokens=50, quote_raw=deep_quote)),
        ]
        result = self.run_current("s4_upper_ath", groups)
        self.assertEqual(result["legs"][0]["reason"], "half_profit_target")
        self.assertEqual(result["legs"][0]["tokens"], 50)
        self.assertEqual(result["legs"][1]["reason"], "runner_trail")
        self.assertNotEqual(result["legs"][1]["reason"], "severe_dump_stop")

    def test_s4_delayed_rejection_requires_25_slots_and_sub_10_percent_peak(self):
        groups = [
            group("signal", 0, 0, state(0.0)),
            group("rejection", 25, 25, state(-0.18)),
        ]
        result = self.run_current("s4_upper_ath", groups)
        self.assertEqual(result["legs"][0]["reason"], "breakout_rejected")

    def test_s4_catastrophic_stop_only_before_first_tranche(self):
        groups = [group("signal", 0, 0, state(0.0)), group("dump", 1, 1, state(-0.22))]
        result = self.run_current("s4_upper_ath", groups)
        self.assertEqual(result["legs"][0]["reason"], "severe_dump_stop")

    def test_s4_delayed_rejection_requires_peak_below_ten_percent(self):
        groups = [
            group("signal", 0, 0, state(0.0)),
            group("peak-ten", 1, 1, state(0.10)),
            group("later-dip", 25, 25, state(-0.18)),
        ]
        result = self.run_current("s4_upper_ath", groups)
        self.assertEqual(result["status"], "unresolved")
        self.assertEqual(result["legs"], [])

    def s5_groups(self, *, open_roi=0.20, later_roi=0.20, later_time=70):
        return [
            group("signal", 0, 0, state(0.0)),
            group("curve-run", 1, 1, state(1.0)),
            group("curve-complete", 2, 2, state(0.0, rtokens=0)),
            group("whole-amm-opening", 10, 10, state(open_roi), venue="amm"),
            group("post-opening", later_time, later_time, state(later_roi), venue="amm"),
        ]

    def test_s5_resets_peak_to_whole_opening_and_open_mark_reconciles(self):
        result = self.run_current(
            "s5_carryover",
            self.s5_groups(),
            end_time=100,
            inventory_key="token_account",
        )
        self.assertEqual(result["status"], "unresolved", "coverage end is not an exit")
        self.assertEqual(result["mark_venue"], "amm")
        self.assertEqual(result["last_valid_time"], 70)
        self.assertAlmostEqual(result["peak_roi"], 0.20, places=8, msg="curve peak must not seed AMM trail")
        self.assertGreater(result["mark"], result["entry_bill"] + NETWORK_FEE)
        report = LEDGER.funded([result], position_limit=None)
        self.assertEqual(report["settled_net_SOL"], 0)
        self.assertEqual(report["unresolved"], 1)
        self.assertGreater(report["unresolved_marked_pnl_SOL"], 0)
        self.assertIsNone(report["win_rate"])
        self.assertAlmostEqual(
            report["last_valid_marked_net_SOL"],
            report["settled_net_SOL"] + report["unresolved_marked_pnl_SOL"],
        )

    def test_s5_amm_hard_stop_uses_wealth_change_from_open(self):
        groups = self.s5_groups(open_roi=0.20, later_roi=-0.23, later_time=20)
        result = self.run_current("s5_carryover", groups, end_time=30, inventory_key="token_account")
        self.assertEqual(result["legs"][0]["reason"], "s5_amm_hard_stop")

    def test_s5_amm_absolute_minus45_stop_is_independent_of_open_drawdown(self):
        groups = self.s5_groups(open_roi=-0.40, later_roi=-0.60, later_time=20)
        result = self.run_current("s5_carryover", groups, end_time=30, inventory_key="token_account")
        self.assertEqual(result["legs"][0]["reason"], "s5_amm_hard_stop")

    def test_s5_half_tranche_is_50_percentage_points_above_open_roi(self):
        groups = self.s5_groups(open_roi=0.20, later_roi=0.70, later_time=20)
        result = self.run_current("s5_carryover", groups, end_time=30, inventory_key="token_account")
        self.assertEqual(result["status"], "unresolved")
        self.assertEqual(result["legs"][0]["reason"], "AMM_open_half")
        self.assertEqual(result["legs"][0]["tokens"], 50)

    def test_s5_curve_reserve_floor_and_600_second_timeout(self):
        floor_groups = [
            group("signal", 0, 0, state(0.0)),
            group("curve-floor", 1, 1, state(0.0, rsol=60_000_000_000)),
        ]
        floor = self.run_current("s5_carryover", floor_groups, end_time=700)
        self.assertEqual(floor["legs"][0]["reason"], "carryover_invalidation")
        with mocked_replay():
            timeout = CURRENT.simulate(
                tape([group("signal", 0, 0, state(0.0))], end_time=700),
                signal("s5_carryover"), "fast", "lower", 0.5,
            )
        self.assertEqual(timeout["legs"][0]["reason"], "s5_curve_timeout")
        self.assertEqual(timeout["legs"][0]["timer_target"], 600)

    def test_s5_amm_600_second_timeout_uses_scheduled_timer_sensitivity(self):
        groups = self.s5_groups(open_roi=0.0, later_roi=0.0, later_time=20)
        with mocked_replay():
            result = CURRENT.simulate(
                tape(groups, end_time=700, inventory_key="token_account"),
                signal("s5_carryover"), "fast", "lower", 0.5,
                cfg={"scheduled_slots": 1},
            )
        leg = result["legs"][0]
        self.assertEqual(leg["reason"], "s5_amm_timeout")
        self.assertEqual(leg["timer_target"], 610)
        self.assertEqual(leg["scheduled_slots"], 1)
        self.assertEqual(leg["landing_slot"], 611)

    def test_s5_amm_trail_can_fire_at_60_second_heartbeat_without_new_trade(self):
        groups = self.s5_groups(open_roi=0.20, later_roi=-0.05, later_time=20)
        result = self.run_current("s5_carryover", groups, end_time=100, inventory_key="token_account")
        self.assertEqual(result["legs"][0]["reason"], "AMM_runner_trail")
        self.assertEqual(result["legs"][0]["timer_target"], 70)
        self.assertEqual(result["legs"][0]["time"], 70)


if __name__ == "__main__":
    unittest.main()
