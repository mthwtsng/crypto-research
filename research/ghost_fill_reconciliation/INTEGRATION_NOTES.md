# Ghost fill repair integration contract

October 9 local / October 10 UTC, 2026. Receipt decoding and the quote helper are now integrated into the runner source. PaperPosition queues buys with frozen output guards and partial/final sells with a zero minimum output; the binary applies complete source transactions before evaluating/landing intents and drives deadlines independently. Live probes use isolated report paths. The previously running host process has not been replaced by this agent; it must be restarted to load the rebuilt binary.

## Integrated runtime behavior

The default 70 ms delay is a provisional receive-clock assumption, not a calibrated source-to-validator landing distribution. Runtime records carry `execution_model=provisional_receive_clock_quote_v2`, `placement_calibrated=false`, and `actual_fill_established=false`. Post-exit RPC audits separately estimate Central80/85 and brackets; no ghost order has a submitted signature. Source signatures/slots/indexes, intent/position IDs, raw observations and raw fill/fee states are persisted. Instruction-limit fallback is removed.

Reserved tickets remain unspent capital until landing. Filled buys refund unused budget; failed guards charge only attempt fees. Partial proceeds enter cash at landing, and final exits credit only the remaining proceeds. Unknown inventory marks serialize as null, and the dashboard displays them explicitly. Stream gaps invalidate market coverage until each affected mint receives a fresh authenticated reserve observation.

After each full exit, the runner freezes that position's buy, partial-sell and final-sell actions and starts a read-only RPC audit under `reports/ghost_post_exit/`. Original records remain immutable. The restart script builds current source and preserves the previous summary (including open inventory) under `data/archive/`; restarting begins a separately identified paper run rather than fabricating exits for previous positions.

This is still per-fill forward quote telemetry, not the approved counterfactual portfolio replay: later historical snapshots do not model participant reactions to our unsubmitted orders. Network fees, account setup/rent and delivery remain assumptions. Authenticated migrated-AMM execution is not integrated; migrated tokens remain in custody with unresolved marks. Strategy changes made concurrently by another writer are not validated by these fill checks.

## Modules

- src/bot/pump_receipt_decoder.rs: successful whole-transaction actual Pump events, integer reserve snapshots, fees, creators, source signature/slot/index, receipt time and raw event logs. Instruction caps/minimums must never substitute for executed values.
- src/bot/ghost_execution.rs: integer quote math matching the repaired approved curve adapter. Buy budget includes protocol/creator fees. Sell finite token amount includes own impact. Fees ceil separately. Completed curves reject curve fills.
- src/bot/ghost_fill_scheduler.rs: pending buy/sell intents, immutable trigger cursor, due boundary, min-output guard, explicit fees, changed states after each hypothetical partial fill. Caller provides source coverage and complete-transaction ordering. Missing coverage waits; completed sell retains custody for AMM repair. Late scheduling records the actual evaluation time rather than a backdated fill.
- scripts/reconcile_ghost_fills.py: append-only receipt/placement reconciliation of post-exit records. An unsubmitted paper trade has estimated placement, never a confirmed exact fill.

## Runtime integration requirements

1. Ingest all instructions/events of each atomic successful source transaction before evaluating a strategy trigger. Set creator from authentic creation/TradeEvent metadata; unknown identity is not zero holdings. Qualify quote currency and fee policy.
2. Persist the observation before recording an intent. Carry source_signature, source_slot, source_transaction_index, intent_id, position_id, source clock and received_at_ms through intent/fill/exit records.
3. Enqueue orders at the frozen clock/placement assumption. Do not substitute a blanket next-slot wait for Central80/85. Local receive time is provisional and must not be called source landing time.
4. Apply every complete competing transaction ahead of the selected boundary; quote remaining actual tokens there. The stop is a trigger, never the guaranteed sell price. Apply each own partial fill before the next quote. Never place a fill inside the triggering transaction.
5. Drive deadlines independently of same-mint market trades, anchored to modeled entry landing. Prove source coverage; never force an exit at tape end.
6. Keep authentic historical state separate from counterfactual state/custody. Do not reset a changed path to a new historical event snapshot after every quote. The approved replay engine handles counterparties' instruction limits, atomic reverts and scaled custody; this helper is not a replacement replay engine.
7. Retain tokens across real completion; authenticate PumpSwap/Raydium opening and liquidity before selling there. No 84-SOL synthetic curve sale or graduation multiplier.
8. Charge failed guard network fees; credit partial delivered proceeds at each landing; reserve rent and release it only under an explicit account policy. Distinguish settled cashflow, open inventory marks and unresolved exposure.
9. Reconcile after each exit using canonical getBlock order. Keep original provisional records immutable; append revisions with provenance. Existing legacy logs lack signal signatures/slots, so exact retroactive reconciliation is unavailable.

## Verification

Quote helper: six focused Rust tests passed and 100 buy / 100 sell cases matched the approved Python adapter field-for-field. Combined quote/scheduler harness: twelve tests pass, including post-dump and intervening-trade sell quotes, sequential partial impact, delayed/quiet timer landing, guard failure, coverage gaps, completion custody and late-scheduler timestamps. These prove plumbing behavior, not portfolio profitability or live enablement.

Receipt decoder: nine focused tests passed in an offline temporary Cargo harness, including the frozen actual 490,196,077-lamport receipt versus its 500,000,000-lamport instruction cap, atomic events, creator mapping, unsupported quote/fee modes, failed ancestry and truncated logs. Parser rejects incomplete observations rather than silently quoting a partial transaction.

Reconciliation CLI: fourteen focused Python tests pass, covering canonical order, full source-slot tails before next-slot prefixes, paper FILL/CLOSE estimates, actual receipt limits versus amounts, unsupported currency/fees, provisional captured observations and unresolved legacy/migrated records. The frozen 40-record legacy log was audited again with the final tool; all 40 records remain unresolved because their source anchors were never logged.

Durable offline test harness:

```sh
rustc --edition=2021 --test research/ghost_fill_reconciliation/component_tests.rs -o /tmp/ghost_scheduler_tests
/tmp/ghost_scheduler_tests
```

The harness imports the quote and scheduler modules by repository-relative paths. For the integrated runtime, `cargo test --offline --bin curve_detector ghost` checks 21 quote, scheduler, position and cash-accounting cases. The receipt decoder has nine separate tests and the Python reconciler fourteen. The isolated live probe exercised buys, a guard failure, a partial sale, final exits and automatic RPC report generation; these observations are not a profitability result.

## October 10 UTC / October 9 local — User-directed exit policy

The user clarified that entry slippage should reject buys, while exits should accept the available price after triggering. Integrated `PaperPosition::queue_exit` now uses `min_output_raw = 0` for both partial and full exits; the trigger quote remains audit evidence. Landing still uses the delayed finite-size quote, fees and own impact. Buy guards retain their existing 3.5% tolerance. This changes the forward paper execution policy, not historical records or the canonical replay control. Missing authenticated state, unsupported liquidity and curve completion still retain inventory rather than invent a sale. Generic offline schedulers/replay utilities retain caller-supplied guards; they are not the active PaperPosition exit path. Source changes require a rebuilt/restarted host process before becoming deployment evidence.
