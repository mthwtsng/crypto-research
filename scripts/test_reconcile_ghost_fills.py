import importlib.util
import pathlib
import unittest


SCRIPT = pathlib.Path(__file__).with_name("reconcile_ghost_fills.py")
SPEC = importlib.util.spec_from_file_location("reconcile_ghost_fills", SCRIPT)
R = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(R)


def state(vsol=40_000_000_000, vtokens=1_000_000_000_000,
          rsol=10_000_000_000, rtokens=700_000_000_000,
          fee=95, creator_fee=30):
    return {"vsol_raw": vsol, "vtokens_raw": vtokens, "rsol_raw": rsol,
            "rtokens_raw": rtokens, "fee_bps": fee,
            "creator_fee_bps": creator_fee, "fee_policy_known": True}


def buy_event(mint, post, curve_sol=1_000_000_000, tokens=20_000_000_000):
    pre = {"vsol_raw": post["vsol_raw"] - curve_sol,
           "vtokens_raw": post["vtokens_raw"] + tokens,
           "rsol_raw": post["rsol_raw"] - curve_sol,
           "rtokens_raw": post["rtokens_raw"] + tokens,
           "fee_bps": post["fee_bps"], "creator_fee_bps": post["creator_fee_bps"]}
    return {"mint": mint, "buy": True, "tokens_raw": tokens, "sol_raw": curve_sol,
            "quote_is_sol": True, **post}, pre


def sell_event(mint, pre, curve_sol=3_000_000_000, tokens=100_000_000_000):
    post = {"vsol_raw": pre["vsol_raw"] - curve_sol,
            "vtokens_raw": pre["vtokens_raw"] + tokens,
            "rsol_raw": pre["rsol_raw"] - curve_sol,
            "rtokens_raw": pre["rtokens_raw"] + tokens,
            "fee_bps": pre["fee_bps"], "creator_fee_bps": pre["creator_fee_bps"]}
    return {"mint": mint, "buy": False, "tokens_raw": tokens, "sol_raw": curve_sol,
            "quote_is_sol": True, **post}


def tx(signature, events=None):
    return {"transaction": {"signatures": [signature]}, "meta": {"err": None},
            "events": list(events or [])}


class FakeReader:
    def __init__(self, source_events=None, groups=None, source_block=None,
                 transactions=None, blocks=None, observations=None):
        self.source_events = source_events or []
        self.groups = groups or []
        self.source_block = source_block
        self.transactions = transactions or {}
        self.blocks = blocks or {}
        self.observations = observations or {}

    def transaction(self, signature):
        return self.transactions.get(signature)

    def block(self, slot, details="full"):
        return self.blocks.get(slot, self.source_block if slot == 100 else None)

    def receipt_trade_events(self, tx_obj, signature, observations):
        return tx_obj.get("events", [])

    def receipt_events_for_mint(self, tx_obj, signature, mint, observations):
        events = [event for event in tx_obj.get("events", []) if R._event_mint(event) == mint]
        if events:
            return events, "canonical_getTransaction_logs"
        captured = [event for event in observations.get(signature, []) if R._event_mint(event) == mint]
        if captured:
            return captured, "captured_observation_events_unverified"
        return [], "no_trade_event"

    def _decoded_events(self, tx_obj):
        return tx_obj.get("events", [])

    def trade_groups(self, block, mint, observations, *, start_index=0, stop_after=None):
        if not block:
            return [], "full_block_transactions_unavailable"
        groups = block.get("groups", self.groups)
        groups = [group for group in groups if group.get("transaction_index", -1) >= start_index]
        if stop_after is not None:
            groups = groups[:stop_after]
        return groups, None

    def next_produced_block(self, anchor_slot):
        block = self.blocks.get(anchor_slot + 1)
        return (anchor_slot + 1, block, None) if block else (None, None, "next_produced_slot_unavailable")


class ReconcileGhostFillsTests(unittest.TestCase):
    def test_canonical_index_comes_from_getblock_order(self):
        block = {"transactions": [tx("competitor"), tx("source"), tx("other")]}
        canonical = R.canonical_block_index(block, "source")
        self.assertEqual(canonical, 1)
        self.assertEqual(R._logged_index_note(0, canonical),
                         "logged_transaction_index_differs_from_canonical_getBlock")

    def test_receipt_min_output_is_not_actual_received_tokens_and_raw_fee_aliases_work(self):
        mint = "Mint111"
        receipt = {"meta": {"err": None, "fee": 5_000,
                            "preTokenBalances": [{"mint": mint, "owner": "wallet", "uiTokenAmount": {"amount": "0"}}],
                            "postTokenBalances": [{"mint": mint, "owner": "wallet", "uiTokenAmount": {"amount": "160"}}]}}
        events = [{"mint": mint, "buy": True, "quote_is_sol": True, "user": "wallet",
                   "tokens_raw": 160, "sol_raw": 100, "fee_raw": 2, "creator_fee_raw": 3,
                   **state()}]
        fill = R._receipt_actual_fill({"wallet": "wallet"}, "buy", mint, receipt, events, 100)
        self.assertTrue(fill["actual_fill_established"])
        self.assertEqual(fill["min_output_raw"], 100)
        self.assertEqual(fill["actual_tokens_raw"], 160)
        self.assertEqual(fill["receipt_owner_token_delta_raw"], 160)
        self.assertTrue(fill["receipt_owner_token_delta_matches_event"])
        self.assertEqual(fill["protocol_fee_raw"], 2)
        self.assertEqual(fill["creator_fee_raw"], 3)

    def test_actual_receipt_without_wallet_rejects_multiple_users(self):
        mint = "Mint111"
        events = [{"mint": mint, "buy": True, "user": "A", "tokens_raw": 1, "sol_raw": 1, **state()},
                  {"mint": mint, "buy": True, "user": "B", "tokens_raw": 2, "sol_raw": 1, **state()}]
        fill = R._receipt_actual_fill({}, "buy", mint, {"meta": {"err": None}}, events, None)
        self.assertEqual(fill["status"], "ambiguous_receipt_users_without_wallet")
        self.assertFalse(fill["actual_fill_established"])

    def test_quote_is_after_whole_dump_and_includes_own_impact(self):
        mint = "Mint111"
        source_state = state()
        source_event, _ = buy_event(mint, source_state)
        dump = sell_event(mint, source_state)
        source_sig, dump_sig = "source", "dump"
        source_block = {"transactions": [tx(source_sig), tx(dump_sig)], "groups": [
            {"signature": source_sig, "transaction_index": 0, "events": [source_event], "state": source_state},
            {"signature": dump_sig, "transaction_index": 1, "events": [dump], "state": state(
                vsol=source_state["vsol_raw"] - 3_000_000_000,
                vtokens=source_state["vtokens_raw"] + 100_000_000_000,
                rsol=source_state["rsol_raw"] - 3_000_000_000,
                rtokens=source_state["rtokens_raw"] + 100_000_000_000)}]}
        reader = FakeReader(groups=source_block["groups"], source_block=source_block)
        row = {"quantity_tokens_raw": 50_000_000_000}
        quoted = R._scenario_boundary_state(reader, row, "sell", mint, source_sig, 100, 0,
                                             {"slot": 100, "events": [source_event]}, source_block, {},
                                             "fast", "intent-1")
        source_quote = R.CURVE.sell(source_state, row["quantity_tokens_raw"])
        dump_state = source_block["groups"][1]["state"]
        post_dump_quote = R.CURVE.sell(dump_state, row["quantity_tokens_raw"])
        self.assertEqual(quoted["classification"], "hypothetical_quote_only")
        self.assertFalse(quoted["exact_hypothetical_fill_claim"])
        self.assertEqual(quoted["boundary"]["after_signature"], dump_sig)
        self.assertEqual(quoted["state_before"], dump_state)
        self.assertEqual(quoted["net_sol_raw"], post_dump_quote[0])
        self.assertLess(post_dump_quote[0], source_quote[0])
        self.assertTrue(quoted["own_impact_applied"])

    def test_next_slot_applies_source_slot_tail_before_next_slot_prefix(self):
        mint = "Mint111"
        source_state = state()
        source_event, _ = buy_event(mint, source_state)
        first = sell_event(mint, source_state, curve_sol=1_000_000_000, tokens=10_000_000_000)
        after_first = state(vsol=source_state["vsol_raw"] - 1_000_000_000,
                            vtokens=source_state["vtokens_raw"] + 10_000_000_000,
                            rsol=source_state["rsol_raw"] - 1_000_000_000,
                            rtokens=source_state["rtokens_raw"] + 10_000_000_000)
        second_post = state(vsol=after_first["vsol_raw"] + 2_000_000_000,
                            vtokens=after_first["vtokens_raw"] - 20_000_000_000,
                            rsol=after_first["rsol_raw"] + 2_000_000_000,
                            rtokens=after_first["rtokens_raw"] - 20_000_000_000)
        second, _ = buy_event(mint, second_post, curve_sol=2_000_000_000, tokens=20_000_000_000)
        after_second = state(vsol=second_post["vsol_raw"], vtokens=second_post["vtokens_raw"],
                             rsol=second_post["rsol_raw"], rtokens=second_post["rtokens_raw"])
        third_post = state(vsol=after_second["vsol_raw"] + 1_500_000_000,
                           vtokens=after_second["vtokens_raw"] - 12_000_000_000,
                           rsol=after_second["rsol_raw"] + 1_500_000_000,
                           rtokens=after_second["rtokens_raw"] - 12_000_000_000)
        third, _ = buy_event(mint, third_post, curve_sol=1_500_000_000, tokens=12_000_000_000)
        source_block = {"transactions": [tx("source"), tx("tail1"), tx("tail2")],
                        "groups": [{"signature": "tail1", "transaction_index": 1, "events": [first]},
                                   {"signature": "tail2", "transaction_index": 2, "events": [second]}]}
        next_block = {"parentSlot": 100, "transactions": [tx("next")],
                      "groups": [{"signature": "next", "transaction_index": 0, "events": [third]}]}
        reader = FakeReader(source_block=source_block, blocks={101: next_block})
        identity = next(f"central-next-{i}" for i in range(10000)
                        if R._uniform(f"central-next-{i}", "central-slot-mixture") >= 0.80)
        source_event, _ = buy_event(mint, source_state)
        quoted = R._scenario_boundary_state(reader, {"quantity_tokens_raw": 1_000_000_000},
                                             "sell", mint, "source", 100, 0,
                                             {"slot": 100, "events": [source_event]}, source_block, {},
                                             "central80", identity)
        self.assertEqual(quoted["classification"], "hypothetical_quote_only")
        self.assertEqual(quoted["state_before"], third_post)
        self.assertEqual(quoted["boundary"]["source_slot_curve_groups_between"], 2)
        self.assertEqual(quoted["boundary"]["next_slot_curve_groups_between"], 1)
        self.assertEqual(quoted["boundary"]["curve_groups_between"], 3)

    def test_no_signature_paper_fill_estimates_and_uses_canonical_source_index(self):
        mint = "Mint111"
        source_state = state()
        source_event, _ = buy_event(mint, source_state)
        source_block = {"transactions": [tx("source")]}
        reader = FakeReader(source_block=source_block,
                            transactions={"source": {"slot": 100, "meta": {"err": None},
                                                      "events": [source_event]}})
        row = {"mint": mint, "side": "buy", "source_signature": "source", "source_slot": 100,
               "source_transaction_index": 99, "gross_budget_raw": 1_000_000_000,
               "fee_policy_known": True}
        item = {"key": "intent:x", "row": row, "action": {"_input_line": 2},
                "action_event": "FILL", "side": "buy", "position_id": "p", "intent_id": "x",
                "mint": mint, "records": [row]}
        audit = R.reconcile_one(item, reader, {}, 64)
        self.assertEqual(audit["status"], "estimated_placement_quotes_available")
        self.assertEqual(audit["source_transaction_index_canonical"], 0)
        self.assertIn("logged_transaction_index_differs_from_canonical_getBlock",
                      audit["source_rpc_notes"])
        self.assertFalse(audit["actual_fill_established"])
        self.assertEqual(audit["estimated_quotes"]["fast"]["classification"],
                         "hypothetical_quote_only")
        self.assertFalse(audit["estimated_quotes"]["fast"]["exact_hypothetical_fill_claim"])

    def test_close_without_signature_is_also_a_hypothetical_estimate(self):
        mint = "Mint111"
        source_state = state()
        source_event, _ = buy_event(mint, source_state)
        block = {"transactions": [tx("source")]}
        reader = FakeReader(source_block=block,
                            transactions={"source": {"slot": 100, "events": [source_event],
                                                      "meta": {"err": None}}})
        row = {"mint": mint, "side": "sell", "source_signature": "source", "source_slot": 100,
               "quantity_tokens_raw": 1_000_000_000}
        item = {"key": "intent:close", "row": row, "action": {}, "action_event": "CLOSE",
                "side": "sell", "position_id": "p", "intent_id": "i", "mint": mint, "records": [row]}
        audit = R.reconcile_one(item, reader, {}, 64)
        self.assertEqual(audit["status"], "estimated_placement_quotes_available")
        self.assertFalse(audit["actual_fill_established"])

    def test_recorded_fill_state_is_never_used_as_source_quote_state(self):
        mint = "Mint111"
        block = {"transactions": [tx("source")]}
        reader = FakeReader(source_block=block,
                            transactions={"source": {"slot": 100, "events": [], "meta": {"err": None}}})
        row = {"mint": mint, "side": "buy", "source_signature": "source", "source_slot": 100,
               "gross_budget_raw": 1_000_000_000, "fill_state": state()}
        item = {"key": "intent:legacy-state", "row": row, "action": {}, "action_event": "FILL",
                "side": "buy", "position_id": "p", "intent_id": "i", "mint": mint, "records": [row]}
        audit = R.reconcile_one(item, reader, {}, 64)
        self.assertEqual(audit["status"], "estimated_placement_unresolved")
        self.assertTrue(all(value["classification"] == "unresolved"
                            for value in audit["estimated_quotes"].values()))

    def test_captured_observation_fallback_is_marked_provisional(self):
        mint = "Mint111"
        source_state = state()
        source_event, _ = buy_event(mint, source_state)
        block = {"transactions": [tx("source")]}
        reader = FakeReader(source_block=block)
        quote = R._scenario_boundary_state(
            reader, {"gross_budget_raw": 1_000_000_000}, "buy", mint, "source", 100, 0,
            {"slot": 100, "events": []}, block, {"source": [source_event]}, "fast", "provisional")
        self.assertEqual(quote["classification"], "hypothetical_quote_only")
        self.assertEqual(quote["status"], "provisional_observation_quote")
        self.assertTrue(quote["evidence_provisional"])
        self.assertIn("captured_observation_events_unverified", quote["event_evidence_provenance"])

    def test_explicit_non_sol_quote_mint_overrides_quote_is_sol(self):
        event = {"venue": "curve", "quote_mint": "USDC111", "quote_is_sol": True}
        self.assertFalse(R._event_is_sol_curve(event))

    def test_fee_policy_unknown_prevents_quote_and_network_fee_is_reported(self):
        event_state = {**state(), "fee_policy_known": False}
        quote = R.quote_at_state({"gross_budget_raw": 1_000_000_000}, "buy", event_state,
                                 source="test", boundary={}, placement="central80", seed="s")
        self.assertEqual(quote["status"], "fee_policy_unknown_at_boundary")
        valid_quote = R.quote_at_state({"gross_budget_raw": 1_000_000_000, "network_fee_raw": 123},
                                       "buy", state(), source="test", boundary={},
                                       placement="fast", seed="s")
        self.assertEqual(valid_quote["network_fee_raw"], 123)
        self.assertIsNone(R.quote_at_state({"gross_budget_raw": 1_000_000_000}, "buy", state(),
                                           source="test", boundary={}, placement="fast", seed="s")
                          ["network_fee_raw"])

    def test_missing_source_anchor_stays_unresolved(self):
        item = {"key": "legacy:1:CLOSE", "row": {"mint": "Mint111", "proceeds_sol": 0.4},
                "action": {"_input_line": 1}, "action_event": "CLOSE", "side": "sell",
                "position_id": None, "intent_id": None, "mint": "Mint111", "records": []}
        audit = R.reconcile_one(item, object(), {}, 64)
        self.assertEqual(audit["status"], "missing_source_signature_or_slot")
        self.assertFalse(audit["actual_fill_established"])
        self.assertNotIn("estimated_quotes", audit)

    def test_central_seed_is_stable_and_independent_of_result(self):
        self.assertEqual(R.placement_seed("intent-7"), R.placement_seed("intent-7"))
        self.assertNotEqual(R.placement_seed("intent-7"), R.placement_seed("intent-8"))
        self.assertEqual(R._central_same_slot_k("intent-7"), R._central_same_slot_k("intent-7"))

    def test_graduated_curve_sell_remains_unresolved(self):
        result = R.quote_at_state({"quantity_tokens_raw": 1_000}, "sell",
                                  state(rtokens=0), source="test",
                                  boundary={}, placement="central85", seed="seed")
        self.assertEqual(result["status"], "graduated_requires_authenticated_amm_continuation")
        self.assertFalse(result["curve_sell_created"])


if __name__ == "__main__":
    unittest.main()
