# How to measure and estimate where our buys and sells land

Updated: October 3, 2026; reviewed against the proposed fee, timer, placement and graduation refinements. Scope: Solana, especially Pump bonding curves, the project's Alchemy/Shyft RPCs, and our Triton Deshred ingress.

**For a transaction we actually submitted, RPC can establish its slot, its position in the recorded block, the intervening curve trades, and its actual result. For a hypothetical transaction we never submitted, RPC alone cannot establish exactly where it would have landed. Estimate that placement from our measured execution history, then replay several possible positions.**

The useful output is: **“Our buy would probably execute after these curve transactions, against these reserves, receiving approximately this many tokens.”** A timestamp or same-slot percentage alone is insufficient.

## Required replay policy for our execution setup

User clarification, October 3: model buys within **100 ms**, with the central landing window **50–70 ms**, and calibrate the buy same-slot share to **80–85%**. These are user-reported execution assumptions for our replay, not a new measurement from historical RPC. Preserve the clock: the previously reported buy interval was signal/source on-chain landing to our buy landing. Do not add another feed/build/send delay on top of that total interval. If a later measurement starts at local fire instead, store it as a separate clock.

Run explicit 50 ms, 70 ms and 100 ms buy scenarios. Do not invent a uniform latency distribution or an exact 82.5% probability from a reported range. Use measured distributions when available; otherwise report the scenario results and the 80%/85% same-slot calibration bounds.

The primary replay must not replace these with an automatic one-slot or 400 ms delay. A next-slot landing can still be inside 100 ms if the signal occurred near the slot boundary. The same-slot probability and elapsed-time assumption must describe one consistent placement model, not two independent penalties.

### Entry: include only executions before our landing

```text
t_signal = availability of the causal signal, with its clock recorded
t_buy_land = t_signal + modeled total buy latency

state_before_our_buy = state after the complete signal transaction
                      + relevant successful transactions ordered after it
                        and before our buy's landing boundary
```

For another reactive bot to get ahead, its observation, decision and delivery must allow its transaction to execute before our landing. A bot that reacts later does not affect our initial buy quote. Do not automatically put every later sniper ahead of us just because it is in the same slot or appears in the eventual launch history.

RPC usually shows a competitor's recorded execution, not its private fire time. Use execution-before-our-landing as the inclusion criterion; do not fabricate competitor reaction times. An order already in flight can also affect us if it executes inside this interval, even if its submission preceded our signal.

Quote our buy after the qualifying intervening transactions, apply our own impact, and continue replaying the later transactions afterward. Those later bots can affect our held position and exit; they simply must not be moved ahead of our entry.

### Exit: the fill follows the trigger and everything that lands before us

```text
t_exit_fire = when our sell is actually fired
t_sell_land = t_exit_fire + modeled sell delivery/landing latency

state_before_our_sell = state known at exit fire
                       + relevant successful transactions executing
                         between exit fire and our sell landing
```

The transaction that crosses the stop or causes the exit signal has already changed the curve when we react. Include its **entire atomic effect** in the state at fire. Then include subsequent qualifying transactions ahead of our sell. Do not count the triggering transaction twice.

**If a hard dump passes through our stop or take-profit level, our reactive sell is after that dump. Never fill us at the crossed threshold or inside the dumping transaction.** Calculate proceeds from the resulting reserves and our actual remaining position size, with fees and own impact.

Illustrative sequence, not a measured trade:

| Time | Event | Replay treatment |
|---|---|---|
| 0 ms | A sell takes executable return from −5% to −28%, crossing a −10% stop | Apply the whole sell; the stop is now triggered |
| 8 ms | Our sell fires after observing the change | Record actual fire and the post-dump state |
| 35 ms | Another sell lands | Apply it before our fill |
| 68 ms | Our sell lands | Quote at this state; do not assign a −10% fill |
| 95 ms | A further sell lands | It does not affect our already completed full exit |

Use actual executable returns rather than the illustrative percentages above. If a buy lands before our sell, include it too: replay all relevant state changes in order, not only adverse sells. For a partial exit, later events still affect the remainder.

A timer exit uses the curve state available when we fire, then the same fire-to-land replay. Price movement before fire is already embedded in that state. If a stop was crossed earlier but detection was delayed, retain that detection delay and its intervening state changes rather than starting from the old stop price.

Clarification, October 4: for reactive sells, the default replay clock is **triggering-transaction landing to our sell landing, 50–70 ms (at most 100 ms)**. This is the same total-interval clock as buys. Do not add a separate detection delay on top of a 50–70 ms fire-to-land window. Concrete scenario definitions are in [the backtest accuracy contract](BACKTEST_ACCURACY_CONTRACT.md).

The user's current exit requirement specifies the **fire-to-land window**; it does not provide a measured sell-latency distribution or sell same-slot percentage. Until measured, run explicit 50/70/100 ms urgent-sell scenarios and label them assumptions. For non-urgent sells, declare a separate route-specific delay range or report that delivery is uncalibrated; cheap delivery is not instantaneous delivery. Do not silently apply the buy's 80–85% same-slot rate to sells. If the sell fires in response to a transaction, distinguish trigger-to-fire from fire-to-land; only add each interval once. A slot gap of one is a placement outcome, not a synonym for 50–70 ms.

Classify urgency **at fire**, using the strategy's permitted delay. An emergency exit or reactive trailing stop is urgent even when it sells a moon bag. A scheduled tranche can use the non-urgent policy only when deferral is actually allowed. Crossing a take-profit level does not guarantee that level is available when a tipless sale lands. An escalation or retry gets its own route, costs and landing window. The fee policy is specified in Step D below.

### Historical RPC without within-slot timing

Historical slot/index ordering alone cannot tell us whether a particular competitor was 30 ms or 120 ms after our signal. With missing timing:

1. Use our own matched execution records to calibrate within-slot curve placement under the stated latency regime.
2. Preserve the 80–85% buy same-slot calibration and its denominator. If based only on landed trades, model non-landings separately rather than treating every intent as landed.
3. Carry central and adverse plausible placements when competitor timing is unresolved. Label them estimates; do not move all same-slot transactions into the 100 ms window by default.
4. Use live observation timing only with its delivery-lag uncertainty. It is not automatically execution timing.

The 100 ms cap is the modeled normal execution envelope, not a reason to discard recorded slower attempts or failed sends. Report observed exceptions separately. A min-output failure means no fill at the stop price: retain the fee and simulate the retry at its own later landing boundary. Several individually fast attempts can produce a total exit delay longer than 100 ms.

### Timer replay when only slot and whole-second blockTime exist

Anchor the holding deadline to **our successful buy landing**, not the signal or a requested slot. In a measured replay use its supported clock. With historical RPC, use `blockTime` elapsed seconds as the primary coarse clock for holds over five seconds; shorter holds need the same uncertainty treatment and cannot become exact by switching to slots. Null timestamps, inconsistent clocks and gaps require an explicit missing-data classification. Block timestamps are estimates, so a one-second quantization interval is not a guaranteed bound on true execution time. [RPC timestamp definition](https://solana.com/docs/rpc/http/getblocktime).

Under an explicitly declared within-second convention, a buy anchored in second `B` gives a hold-`H` deadline somewhere in `[B + H, B + H + 1)`. Transactions in overlapping timestamp buckets have ambiguous order relative to that timer. Preserve known atomic/curve order and run feasible early/late timer boundaries for those buckets; label these as ordering sensitivities, not measured times. Do not distribute transactions uniformly within a second. Extra timestamp-estimation, detection and delivery uncertainty must be added separately when known.

The replay scheduler must create a timer event **even if no trade occurs then**. Apply transactions preceding the modeled deadline, evaluate the timeout/scratch using that state, fire, then replay the sell's delivery window. Do not wait for the next transaction to start the timer exit: that transaction might arrive much later and contain a dump. A quiet interval permits a timer sale only when collection proves coverage through its modeled landing.

For nominal slot-clock sensitivity only, publish `ceil(H / 0.420)` and `ceil(H / 0.500)` slot offsets alongside the blockTime cases. For 45 seconds these are 108 and 90 slots. These are assumed 420/500 ms scenarios, not calibrated central/congested bounds; actual elapsed time can fall outside them. `ceil` avoids an early deadline under the assumed clock; `round` does not. Do not convert these hold-clock sensitivities into buy/sell delivery penalties.

Coverage must extend through entry, the actual exit condition, delivery and any retries/AMM continuation. If not, retain unresolved inventory and occupancy. Never sell at `rem[-1]` merely because the file ends. Record `unresolved_coverage` separately from a known reverted sell or a genuine zero-recovery outcome.

### Event-loop implementation contract

```python
on_complete_external_transaction(tx):
    apply_successful_state_changes(tx)  # whole trigger/dump first
    update_existing_positions_and_signals()
    if new_entry_signal:
        schedule_buy(signal_time + modeled_total_buy_latency)
    if exit_condition and no_exit_already_pending:
        record_exit_fire()
        schedule_sell(exit_fire_time + modeled_sell_latency)

on_our_successful_buy(fill):
    schedule_timer(fill.landing_time + holding_deadline_duration)

on_timer_deadline(position):
    # Runs independently of incoming market transactions.
    if timer_exit_condition(position, current_state) and no_exit_already_pending:
        record_exit_fire_and_urgency()
        schedule_sell(exit_fire_time + sell_latency_for_selected_route)

on_our_landing_boundary(order):
    # Every relevant external transaction ahead of this boundary is applied.
    validate_venue_and_curve_completion(current_state, order)
    quote = executable_quote(current_state, order.remaining_size)
    enforce_actual_min_output_or_max_cost(quote, order)
    record_fill_or_failure_and_costs()
    apply_our_successful_fill_and_update_inventory()
```

In a replay, process these items by the supported execution ordering and clock. Do not use future trades to choose a better landing boundary. For a boundary inside an atomic transaction, place our order at a valid boundary consistent with observed account ordering; we cannot execute midway through it. Missing timing produces a placement range, not a fabricated exact answer.

## 1. Keep these three questions separate

| Question | Evidence | Result |
|---|---|---|
| Where did a real buy/sell land? | Our signature, `getTransaction`, `getBlock`, decoded successful curve trades | Observed placement and fill |
| How long did our pipeline take? | Local receive/decision/send timestamps, outcome notifications, clock provenance | Measured pipeline and observation delays |
| Where would an unsubmitted strategy trade land? | Causal trigger plus a calibrated placement distribution | Estimated placements and executable quotes, with uncertainty |

`blockTime` is an estimated block production timestamp with second resolution, not an execution timestamp for each transaction. Standard RPC does not expose an exact wall-clock landing time for every transaction. Do not derive a 50–75 ms landing interval by subtracting block times. See [Solana RPC structures](https://solana.com/docs/rpc/json-structures).

The latest user-reported model is 50–70 ms normally, at most 100 ms normally, and 80–85% same-slot buys. The older 50–75 ms/80–90% reports remain historical context; measurement method and recent all-intents sample remain unspecified. Earlier matched history found 88/132 same-slot entries, but only 19/132 were both same-slot and immediately next on the curve. Those are different samples and different metrics; neither silently replaces the other. See [setup context](../SETUP_CONTEXT.md).

## 2. For real transactions: recover exact recorded placement

Start with an **intent**, not just a successful signature. Match:

- Buy: the source transaction or market event that caused our decision, plus our submitted buy signatures.
- Event-driven sell: the transaction that caused the exit decision, plus our sell signatures.
- Timer sell: the position identifier, intended deadline, last state available at the deadline, actual decision time, and sell signatures. Do not invent an external transaction anchor for a timer.

### Step A — locate the transactions

Use the RPC URLs in [AGENTS.md](../AGENTS.md). Batch `getSignatureStatuses` for recent submitted signatures; use `searchTransactionHistory: true` when researching older signatures. The response's **per-signature `slot`** is the transaction's slot. The surrounding `context.slot` is the RPC evaluation context, not its landing slot. Preserve `err` and `confirmationStatus`. [Method reference](https://solana.com/docs/rpc/http/getsignaturestatuses).

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "getSignatureStatuses",
  "params": [["SOURCE_SIGNATURE", "OUR_SIGNATURE"], {"searchTransactionHistory": true}]
}
```

Fetch each transaction with `getTransaction`, `encoding: "jsonParsed"`, and explicit commitment. Use confirmed results for provisional analysis and reconcile finalized results for the durable audit. Specify the highest transaction version the decoder actually supports; the example uses legacy/v0 support. Unsupported versions are coverage errors, not empty transactions.

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "getTransaction",
  "params": ["OUR_SIGNATURE", {
    "encoding": "jsonParsed",
    "commitment": "confirmed",
    "maxSupportedTransactionVersion": 0
  }]
}
```

A null result can mean unavailable, not yet visible, or missing history. An RPC error is not a transaction failure. Do not classify either as “never landed.”

### Step B — locate both signatures in their blocks

Call `getBlock` for the source and our landing slots. For lightweight ordinal lookup:

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "getBlock",
  "params": [452856591, {
    "commitment": "confirmed",
    "transactionDetails": "signatures",
    "rewards": false,
    "maxSupportedTransactionVersion": 0
  }]
}
```

Build `signature → zero-based block index` from the returned array. Fetch `transactionDetails: "full"` when decoding intervening transactions. Cache blocks by slot **and blockhash/commitment**, reconcile forks, and preserve raw responses. [Method reference](https://solana.com/docs/rpc/http/getblock).

Do not substitute a provider's enhanced `transactionIndex` without checking it against `getBlock`. This repository previously found different absolute provider indices even when relative ordering agreed. Do not sort same-slot transactions by signatures or `blockTime`.
October 3 rescue-validation check: enhanced provider indices disagreed with `getBlock` absolute positions in 11 of 50 sampled blocks, while sampled per-curve relative order agreed and 99,693 decoded reserve transitions reconciled exactly. Reserve continuity can validate the curve-trade sequence; it cannot authenticate a global block index or a 50–70 ms landing boundary. Also distinguish an explicitly skipped slot from archive cleanup/missing long-term storage before advancing to another slot. See [the rescue audit](rescue_validation_20261003/AUDIT.md).


Recorded block order is a ledger position, not a millisecond schedule for all transactions. Independent accounts can execute in parallel. For a shared writable bonding curve, verify the successful state-transition sequence against its decoded reserves.

### Step C — reconstruct the relevant curve sequence

Resolve account lookup tables, decode outer instructions and inner calls, and identify the exact mint, bonding curve, quote currency, authenticated trader, and trade amounts. Curve-account association alone does not prove a trade occurred.

- Count only successful state-changing transactions when computing **curve-trade distance**.
- Retain reverted transactions separately: they can consume fees but do not commit their trade state.
- A failed transaction can contain trade-looking logs from an earlier instruction. Reject those as committed fills; require transaction success and successful invocation ancestry.
- Treat each transaction as atomic. Our hypothetical order cannot be inserted between two instructions in someone else's transaction.
- Preserve multiple trades within one successful transaction, but distinguish event count from transaction-group count.
- Fetch intervening produced blocks if slots differ. A skipped slot is different from an unavailable block. Missing data invalidates an exact distance.

Useful metrics:

```text
slot_gap = our_slot - anchor_slot

# Only when both transactions are in the same recorded block:
block_index_gap = our_block_index - anchor_block_index

curve_groups_between = count of successful relevant curve transaction groups
                       strictly after anchor and strictly before our transaction
```

Example: source index 739, our buy index 742, same slot. There are two intervening global block transactions. If both changed this curve successfully, there are two intervening curve groups. If neither touched this curve, the curve state may still be the source's post-state. Both are “same slot,” but they imply different fills.

For a timer exit, count the curve groups between the last causally observed state at the decision and the sell. That observation is an anchor for measuring stale-state exposure, not a claim the timer was caused by it.

### Step D — identify the actual fill and costs

Validate our `meta.err`, actual token/SOL or quote-token changes, decoded trade amounts, and fee payer. Resolve multiple token accounts by owner. Include trading fees, network/priority fees, tips, account setup and any refunds. Attribute lamport changes carefully: transaction fees, rent and transfers can coexist with a swap. Do not subtract a fee twice if it is already included in a wallet balance delta.

Store both the decision-time quote and actual fill:

```text
buy adverse_fill = 1 - actual_tokens_received / decision_quote_tokens
sell adverse_fill = 1 - actual_net_proceeds / decision_quote_net_proceeds
```

Keep quote/ticket/fee conventions identical. Partial sells need their actual sold quantity and individual costs. Buy execution statistics do not calibrate sell execution.

### Step D.1 — the user's asymmetric fee policy

The following are **user-specified policy targets**, recorded in [setup context](../SETUP_CONTEXT.md), not verified deployment settings or measured delivery guarantees:

| Leg class | Sender tip | Priority fee | Delivery model |
|---|---|---|---|
| Buys and urgent/reactive sells | At least 0.001 SOL; higher if the actual route requires it | At least 0.0005 SOL **total priority fee per transaction** | Current fast-route buy or urgent-sell cohort, separately calibrated |
| Non-urgent scheduled/milestone sells | 0 SOL on a route supporting tipless delivery | Minimum needed by the selected route/policy; record the amount | Separate non-urgent cohort; include delay, expiry, failures and escalation |

Fast senders/Jito and direct leader TPU are possible route classes, not proof of currently enabled routing. A provider's own minimum is distinct from the user's target; Jito documents a bundle minimum of 1,000 lamports, whereas the user's 0.001 SOL floor is 1,000,000 lamports. [Jito sender documentation](https://docs.jito.wtf/lowlatencytxnsend/).

Keep costs separate per attempt and per partial leg. For legacy/v0 transactions:

```text
priority_lamports = ceil(cu_limit * cu_price_micro_lamports_per_cu / 1_000_000)
network_lamports = signature_base_fee_lamports + priority_lamports
execution_cost = network_lamports + committed_sender_tips
                 + separately paid sender charges + setup/rent - actual refunds
```

The current ordinary base fee is 5,000 lamports per signature; priority is charged on requested CU limit, not consumed CU. Use actual metadata/format for other transaction versions. [Solana fee calculation](https://solana.com/docs/core/fees/fee-structure).

A successful one-signature speed leg at both user floors costs about **0.001505 SOL** in network fees plus tip, before trading fees/setup. A **0.000010 SOL total** non-urgent network-cost example is an assumption about base plus priority, not a mandatory 0.000010 SOL priority fee or zero cost. Zero tip does not remove trading fees, signature fees, failures or price movement during delivery.

On a landed-reverted transaction, retain actual network fees. An inline tip transfer reverts with the transaction; a separately committed tip/payment may still cost money. Do not charge the successful tip unconditionally to every failure. Distinct retry signatures can incur additional costs; identical-signature fanout must not be charged as multiple landed transactions. [Atomicity and failure fees](https://solana.com/docs/core/transactions).

### Step D.2 — exact quote conventions, not just integer variables

Use decoded, authenticated pre/post reserves and the instruction version's rounding and trade semantics. Keep lamports/raw token units as integers; products of u64 reserves require checked wider intermediates, commonly u128 in Rust. Do not reconstruct reserves from fee-payer deltas or repeatedly reset all trades to one hard-coded genesis `K`.

Distinguish gross wallet budget, net curve input, exact-input buys and exact-output buys with maximum cost. For a gross budget, solve the instruction's fee-inclusive input requirement; multiplying by `1 - total_bps / 10000` is not generally the inverse of fees added to net input. If a decoded event's input is already curve input, do not deduct its fees again.

Protocol and creator fees must use the applicable historical configuration/event and instruction rounding. **95 + 30 bps is not a universal constant**: Pump supports fee schedules tied to state. Our intervention can change the applicable tier. Unknown historical fee configuration or counterparty limits are explicit replay uncertainty. [Pump fee-program reference](https://github.com/pump-fun/pump-public-docs/blob/main/docs/FEE_PROGRAM_README.md).

Validate no-intervention state transitions before own-impact replay. Apply whole atomic groups, mutate real/virtual reserves on our fill, preserve partial inventory, and enforce liquidity/guard/completion constraints. Integer arithmetic alone does not establish executable PnL.

## 3. What to log live, including unsuccessful attempts

Record one row per decision intent and separate rows for every send attempt and resulting fill. Suggested fields:

```text
intent_id, position_id, strategy_revision, config_hash, side, mint, curve
region, process_id, clock_epoch_id, ingress_provider, sender_route
urgency_at_fire, exit_reason, fee_policy_revision, fee_policy_evidence
anchor_signature, anchor_slot, anchor_evidence, anchor_event_index
state_observation_slot, state_observation_signature, state_observed_at_ns
feed_received_monotonic_ns, normalized_monotonic_ns, decision_monotonic_ns
signed_monotonic_ns, send_started_monotonic_ns, send_ack_monotonic_ns
first_outcome_observed_monotonic_ns, finalized_observed_monotonic_ns
wall_clock_unix_ns, clock_sync_error_bound_ns
our_signature, attempt_number, retry_reason, nonce_or_blockhash_id
quote_amount, token_amount, min_output, max_cost, slippage_policy
cu_limit, cu_price_micro_lamports_per_cu, priority_fee_lamports, tip_lamports
tip_committed, separate_sender_charge, setup_rent, refunds
timer_deadline, timer_clock, timer_uncertainty, placement_timing_grade
curve_complete, quote_mint, venue_at_landing, migration_signature, pool
provider_response, outcome_error
landing_slot, landing_blockhash, landing_block_index
curve_groups_between, actual_fill, actual_fees, final_outcome
```

Use process-local monotonic clocks for stage durations. Do not subtract monotonic timestamps from different processes or regions. Wall clocks require a measured synchronization error bound before comparing FRA with NY.

Existing hooks worth extending:

- `src/bot/ingress/triton_deshred.rs`: `received_unix_ns`, `frame_complete_ns`, normalization timestamp.
- `src/bot/ingress/mod.rs`: stage telemetry and `ingress_observation` output, including region, slot, signature and evidence.
- The actual send and sell paths: append intent/signature correlation, attempt timestamps and final reconciliation. Existing ingress timestamps alone do not supply this correlation.

Deshred currently marks observations `DeshredOutcomeUnknown`. The received transaction is not yet authenticated as a successful state transition. Preserve that distinction in both live decisions and backtests. If we act speculatively, record speculative intents even when the source later fails.

A `sendTransaction` acknowledgement only means the RPC accepted the request; it does not prove landing. A WebSocket `receivedSignature` notification likewise does not prove successful execution. Execution-status notifications arrive after processing and provider delivery; their local arrival time is not an exact validator execution timestamp. [Send reference](https://solana.com/docs/rpc/http/sendtransaction), [subscription reference](https://solana.com/docs/rpc/websocket/signaturesubscribe).

Label local timing honestly:

```text
build_duration = signed_time - decision_time
send_ack_duration = ack_time - send_start_time
decision_to_outcome_observation = outcome_observed_time - decision_time
```

The third value includes execution and observation delivery. Even subtracting source/own observations on one feed measures observation separation, which can include different delivery lags. Call it “on-chain landing milliseconds” only if its timestamp source actually establishes that clock.

## 4. Estimate a hypothetical landing using our actual history

For our primary scenarios use the execution policy above. Do not turn 75 ms into `round(75 / 400)` slots, put every simulated buy immediately after its source, or spread block transactions evenly through a synthetic 400 ms slot. Historical RPC lacks the within-slot times to justify those choices.

### Build two empirical models

**Buy model:** condition on the information available at decision time: region, feed, route, fee/tip settings, speculative versus confirmed anchor, current curve activity, ticket, transaction shape and any causally available slot-phase/leader information.

**Sell model:** additionally distinguish timer versus event exits, urgent versus ordinary exits, partial versus full sells, and quote/liquidity state. Measure retries and failures independently.

For each cohort, retain the JOINT distribution of:

```text
outcome: successful / landed-reverted / expired / unresolved
slot_gap
successful_curve_groups_between
recorded block position, where observed
fill deterioration and costs
```

Do not sample slot gap and curve distance independently: busy-curve placement and delay are related. Begin with broad cohorts if samples are thin; state sample sizes and uncertainty. Use prior chronological observations only when simulating a later decision. Never train on that simulated trade's future outcome.

Count all intents. Identical-signature fanout is one transaction sent through several routes; distinct signatures can create multiple transactions and fees. Keep route attribution honest when more than one route could have delivered the same signature. A null status remains unresolved until sufficient history/expiry evidence exists; durable-nonce transactions need nonce-state reasoning rather than ordinary blockhash expiry rules.

### Insert at plausible transaction boundaries

For each simulated decision:

1. Freeze the information actually available when we decide, including whether source success was still unknown.
2. Draw a measured outcome/placement from a comparable earlier execution cohort, or run explicit early/central/late ordering scenarios if calibration is unavailable. These are not guaranteed PnL bounds.
3. Walk the authenticated subsequent curve transaction groups to that boundary, respecting the sampled slot constraints. Do not select a favorable boundary using future price.
4. If the requested position lies outside coverage, mark it missing; do not clamp it to the last profitable trade.
5. Quote our finite-size buy or sell against the state **immediately before our hypothetical transaction**. Apply its actual min-output/max-cost rule, fees and setup assumptions. A guard failure is a submitted failed attempt with its appropriate costs.
6. Apply our fill to reserves. Reprice subsequent counterparties sequentially before simulating the exit. Disclose counterparty constraints/reactions that historical RPC cannot determine.
7. At the exit decision, use the separate sell model and repeat the same process. Credit cash only when the modeled sale executes.

If the historical tape already contains our real trade, remove/replace it for the hypothetical run; otherwise we would buy twice. Account for its downstream impact consistently. If the source strategy is a copied wallet, that wallet's trade normally remains in the tape: we are an additional order after it.

### Concrete placement rule: calibrate the distribution, not an invented rank

For successful buys, let `G` be slot gap, `N` the intervening successful curve groups, `B` the insertion boundary and `X` the causally available route/feed/state features. Use the joint conditional model:

```text
P(B | X, latency_case)
    = p * P(B | G = 0, X, latency_case)
      + (1 - p) * P(B | G > 0, X, latency_case)

p scenarios: 0.80 and 0.85, from the user's reported buy range
boundary sample: (G, N, block-position evidence) together
```

Keep failed/expired intents outside that successful-placement conditional and specify the denominator. The report does not establish that all non-same-slot buys land at `S + 1`; retain longer gaps if observed. Draw from chronologically earlier, comparable records with compatible latency evidence. If timestamps cannot support the requested latency case, label it uncalibrated rather than attaching a fictional 70 ms value to an index.

For `G = 0`, valid boundaries are after the complete signal and among the later atomic groups in that slot. Use the measured conditional ranks. **Do not default to the slot tail:** it can include executions after our landing. For `G > 0`, require the sampled produced slot and valid boundary there; a skipped `S + 1` is not a produced landing block. Do not jump to the next observed curve trade if it occurs outside the modeled interval.

Without calibration, publish immediate-after-signal, signal-slot-tail and next-produced-slot boundaries after zero/one/two curve groups as **ordering sensitivities only**. Report whether timing/coverage makes each case admissible; top one/two next-slot trades have no guaranteed Jito priority or 100 ms meaning. Mixing scenarios with 80%/85% weights matches a marginal assumption, not a measured performance forecast. Do not choose a boundary because future price is favorable.

### Graduation and venue changes are hard execution boundaries

Use the venue and state **at landing**, not at decision. For standard Pump curves, authenticate `BondingCurve.complete` and `real_token_reserves`; completion is set when a successful buy exhausts real tokens. The completing buy can succeed; subsequent Pump curve trades cannot be treated as ordinary executable curve fills. Graduation and later pool availability are separate ordered facts. The current documented migration destination is **PumpSwap**; Raydium applies to authenticated historical routes. [Pump program reference](https://github.com/pump-fun/pump-public-docs/blob/main/docs/PUMP_PROGRAM_README.md).

For illustration only, classic initial virtual reserves of 30 SOL/1,073 million tokens and 793.1 million real tokens imply about **85.005 SOL real** and **115.005 SOL virtual** at exhaustion, ignoring rounding. Derivation: `virtual_end = 30 * 1073 / (1073 - 793.1)`; `real_end = virtual_end - 30`. These values are not universal completion triggers. Never substitute 28–32 SOL real or 85 SOL virtual as graduation for that configuration.

If the curve completes before our pending curve order lands, record its known revert and applicable attempt costs; retain unsold inventory after a failed sell. If pool history or route support is missing, record unsupported AMM continuation/unresolved inventory, not an invented terminal sale. Preserve already realized partial proceeds.

If our counterfactual buy completes the curve earlier than history, recompute that boundary and stop ordinary curve replay. Later historical curve trades and historical AMM timing are no longer a feasible unchanged path; classify unmodeled continuation explicitly. Never clip a full-token sell's quote to available SOL and call it a successful full liquidation.

## 5. Minimal estimator pseudocode

```python
for intent in chronological_intents:
    observed_prefix = data_available_at(intent.decision)
    model = buy_model if intent.side == "buy" else sell_model
    placement = model.sample(condition_on(observed_prefix, intent))

    if placement.outcome != "successful":
        ledger.record_attempt_outcome(placement)
        continue

    boundary = locate_transaction_boundary(
        tape, intent.anchor, placement.slot_gap,
        placement.curve_groups_between,
    )
    if boundary is None:
        ledger.record_missing_coverage(intent)
        continue

    state = counterfactual_state_before(boundary)
    fill = quote_with_fees_impact_and_guards(state, intent)
    ledger.execute_or_record_guard_failure(fill, boundary)
    apply_committed_state_change(fill)
```

This is a design sketch, not an implemented landing predictor. Record the probability/model sample behind every hypothetical fill so the estimate can be reproduced.

## 6. Acceptance checks before using this in an edge claim

- Reconstruct known source/own signatures into their actual recorded slots and positions.
- Validate chronological curve state transitions and lookup-table resolution; retain failures and missing blocks.
- Compare predicted versus observed same-slot rates, curve-distance distributions, failed attempts and fill deterioration on later data.
- Evaluate buys and sells separately, and stratify FRA/NY and materially different sender settings.
- Audit urgent versus non-urgent costs and delivery separately; count failed/retried legs and committed tips without double charging.
- Verify independent timer events, timestamp-bucket sensitivity, and coverage through each actual modeled landing; retain unresolved inventory rather than file-end liquidation.
- Verify completion before pending fills and authenticate post-graduation pool/route coverage; reject invented curve sells or unchanged historical paths after counterfactual completion.
- Report central and adverse placement scenarios, capital constraints, pending orders and unresolved exits.
- Check prefix invariance: appending future data must not change an earlier signal or the model available to it.
- Use a later 2–3 week evaluation horizon for edge validation where applicable, with complete execution-intent coverage rather than successful-match-only statistics.

**The immediate implementation priority is an intent-to-signature-to-block-position reconciler for both buys and sells.** RPC already provides the observed chain placement needed for that. Live logs provide the missing decision/send correlation. Together they can calibrate a defensible historical landing model without pretending RPC supplies exact within-slot milliseconds.

### Null timer metadata: verified skipped slots

A null `getBlockTime` response or archive lookup failure is not proof that a slot was skipped. Before advancing a replay clock past it, obtain a later canonical produced block header: if its `parentSlot` is below the queried slot and its slot is above it, the parent link proves the gap. Otherwise retain unresolved timing or recover the actual timestamp; do not silently substitute a later slot. The October 3 rescue validation verified all 33 null timestamp queries this way; see [the saved proofs](rescue_validation_20261003/NULL_CLOCK_RESOLUTIONS.json). This does not recover within-slot landing times.
