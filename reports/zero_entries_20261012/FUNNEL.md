# Zero-entry funnel: VM `ghost-v2-20261012T011751`

At the frozen prefix cut (2026-10-12 01:28:19.814814 UTC; runtime summary age 620 seconds), the VM had a connected stream, 15.0 SOL virtual cash/equity, zero open positions, zero failed buy attempts and zero buys. The decisive observation is **zero recorded source-predicate entry candidates and zero buy-intent rows**. Tracking coverage is the main blind spot: all 850 setup-audit rows are tracking errors, and the source intentionally skips candidate evaluation when entry tracking is unready; those 850 rows therefore cannot be labeled missed signals.

The screen was not observed rejecting a candidate. In the VM's 210 holder-screen audit rows, 192 were `watch` and 18 were `unknown`; there were zero hard blocks. Separately, the fake-detector stream recorded 1,184 verdict observations: 1,106 Unknown across 919 mints and 78 Watch across 48 mints, with no blocked verdict. Those are repeated checks, not unique opportunities. The saved policy allows Watch with partial-coverage logging and skips Unknown. The breakers were disabled in the summary, which removes a possible veto and does not suppress candidates. The launcher defaults S2/S4 to Reclaim, but the frozen runtime artifacts do not record the active override and contain no breakout-signal rows.

## Funnel counts

- `ghost_variant_signals.jsonl`: 850 `SETUP_TRACKING_AUDIT` rows across 850 unique mints; zero rows with a nonempty candidate list. Tracking errors: 657 missing creation history, 156 incomplete ordered custody, 30 wallet-custody mismatch, 5 unrecognized successful trades, 2 reserve-transition mismatches.
- `ghost_intents.jsonl`: 21,032 rows, all `TRACKING_RECEIPT_UNRESOLVED`; zero `INTENT` or buy-attempt rows. Of these diagnostics, 20,773 have no affected mint and none declare a global coverage gap. These are receipt-resolution records, not trade attempts.
- Holder-screen audit: 210 rows across 64 unique mint/status pairs: 192 Watch events (48 mints) and 18 Unknown events (16 mints). No Clear or Blocked event appears in that append-only slice. The fake-detector verdict stream has repeated status checks: 1,106 Unknown rows (919 unique mints), 78 Watch rows (48 unique mints), zero Blocked. Unknown mostly reflects a missing holder snapshot; Watch reflects incomplete funding, receipt, or cross-launch probes. These event histories and the runtime summary’s current-state counters have different scopes.
- `ghost_trades.jsonl` and `ghost_force_sells.jsonl` were empty at the cut; the existing `ghost_trades_master.jsonl` has no rows for this VM. No `ghost_entry_candidates*` file exists under `data/`.
- The runtime summary reports `active_fake_coin_blocks: []`, `circuit_breakers_enabled: false`, 15.0 SOL equity and no position. Its coverage/status counters (complete 58, incomplete 844, missing creation 653; Clear current 23, completed Unknown/expired 33, in flight 1) are snapshot summary fields, not reconciled unique-mint counts for the append-only audit rows above.

## Attribution and examples

The source observer computes `audit_entry_candidates` only when `entry_tracking_ready()` is true. For tracking-ready states it logs a nonempty candidate list before the holder admission gate, so a source-predicate candidate blocked only by screening would be visible in this log. None was recorded. For unready states it emits a tracking-error audit with an empty candidate array without evaluating the predicates. This makes the result decisive for observed candidates and inconclusive for the untrackable universe.

Two concrete review items were near necessary reserve bands, but neither is a proven strategy signal:

- `5YEXqwMiz2tgxyYRcKnhPKDPjt9z8wpTyqMxmpMdLBwZ` was at 21.9214 SOL, inside S4's 16–22 SOL reserve band, with incomplete ordered custody and `holder_ready=false`. New-high, breadth, and signal-buy conditions were not evaluated.
- `G4PKy7bKdxaDYxV4DSdi8AjS928Q95wPZaQYBWZgjury` was at 9.5802 SOL, inside S3's 8–18 SOL band, with an unrecognized successful trade; its screen verdict was Unknown for missing mint supply. The dip, sell-size, two-buyer, and confirmation conditions were not evaluated.

These examples identify repair targets, not blocked trades. There is no evidence in this prefix that a setup would have fired but for the screen, tracking gate, breaker setting, or S2/S4 mode. The clearest next diagnostic is to restore creation and ordered custody coverage, then capture the same candidate audit; no admission-policy change is supported by this funnel.

## Freeze and scope

The byte-prefix sizes and SHA-256 hashes are recorded in [funnel_counts.json](funnel_counts.json); representative rows and their source signatures are in [funnel_examples.json](funnel_examples.json). The frozen summary says the stream was connected and its `updated_at_utc` was 01:28:12.145. The process had run about 10m20s from the VM identifier timestamp. These are persisted local artifacts; no external host environment or deployed binary hash was available, and the active S2/S4 mode is not recorded. Source attribution was checked against the local working tree and hashes/revision are recorded in the counts JSON.

This is a read-only funnel diagnosis. It contains no PnL, backtest, or edge claim and makes no strategy or runtime changes.
