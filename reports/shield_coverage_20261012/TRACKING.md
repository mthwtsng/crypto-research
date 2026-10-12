# Tracking coverage audit

This is a read-only audit of `ghost-v2-20261012T032117`, frozen at runtime checkpoint `saved_at_ms=1791776454023` (2026-10-12 03:40:54.023 UTC). The checkpoint contained 7,621 curves. No source, runtime, checkpoint, tape, or cash state was changed.

The live checkpoint and append-only tape have since advanced. The exact raw byte-prefix digest for this 03:40:54.023 UTC snapshot was not preserved in the audit handoff, so this report records the VM ID and checkpoint timestamp and does not attach a later live-file hash to these counts. A separate digest from 03:40:31 is a different checkpoint. Full structured counts, cohort definitions, signatures, and source hashes are in [tracking.json](tracking.json).

## What the counts mean

`complete` in the summary is the `entry_tracking_ready()` predicate: no tracking error; positive token supply; known decimals; authoritative reserves; known fee policy; supported SOL quote. It does **not** require `creation_receipt_seen`. `incomplete_history` is simply a present `tracking_error`. Those two counts are disjoint. `missing_creation` independently counts curves without an authenticated creation receipt and overlaps both; at least 153 post-start curves were both ready and missing creation. There were also 339 curves with no tracking error that still failed one or more readiness fields.

At the cutoff, 408/7,621 curves were entry-ready, 6,874 had a tracking error, 3,715 lacked a creation receipt, and 339 had no tracking error but were not ready. The first-error histogram was: 3,225 restart gaps; 1,610 missing creation history; 581 ordered custody gaps; 475 unscoped receipt gaps; 544 reserve-transition mismatches; 311 unrecognized successful trades; 126 wallet-custody mismatches; and 2 out-of-order/duplicate receipts.

## Why few entries appeared

The largest group of incomplete records was the pre-VM/restored cohort: 6,853 curves, of which 6,754 had tracking errors and only 61 were entry-ready. The restart-gap and missing-history labels dominate that cohort. These errors represent unresolved old state, not evidence that the current VM missed every corresponding receipt.

For authenticated creations first observed after this VM started, 486 unique mints were present in the checkpoint. Of the 303 with at least one accepted decoded trade, 194 were ready (64.0%). The other 109 were not ready: 76 had reserve-transition mismatches and 32 had unrecognized trades; one additional traded mint had no tracking error but still lacked a readiness field. Another 183 new creations had no accepted trade yet: 182 had no error and one was invalidated by an unrecognized successful trade. Creation-only rows therefore did not establish authoritative reserves or fee readiness.

A further 282 post-start event mints had no authenticated creation receipt. 153 nevertheless passed `entry_tracking_ready()`, illustrating the creation-flag overlap and the pump-suffix supply/decimals fallback. That fallback does not itself establish reserves or fee policy.

The 295 current-VM variant rows were mostly tracking audits (286); the rest were four breakout signals, three reclaim-entry diagnostics, and two reclaim expirations. They are not 295 buy signals. Source requires holder readiness or whitelist status, tracking readiness, screening-window eligibility, and a strategy trigger. The intent tape recorded eight `INTENT` and eight `FILL` rows across four distinct mints. Circuit breakers were disabled in the checkpoint summary, so they do not explain the low count.

During the VM interval the decoded tape contained 33,385 observations, 30,487 decoded trade events, and all 486 new authenticated creation receipts matched checkpoint mints. There were 24,729 unresolved-receipt audit rows, including 328 scoped rows affecting 1,228 mint references and no `global_coverage_gap=true` row. The 475 unscoped-coverage errors in state belonged to the pre-VM/restored cohort. The largest persisted decoded-observation receive gap was 1,561 ms; this tape is not the raw Yellowstone ingress stream, so it cannot by itself rule out every ingress gap above the source's two-second threshold.

## Verified mismatch example

For `25tNnrcR4eeBqBeg8cddT5dPVccfAQYAFSpGUtQPpump`, the authenticated creation receipt at slot 455897254/index 494 established `r_sol=244,424,325` and `v_sol=30,244,424,325` lamports. The next receipt, a decoded sell at slot 455897269/index 510, sold 27,253,311 lamports. Decoded post-state `r_sol=217,171,014` matches the reserve-balance delta, while `v_sol=26,896,211,704`; applying the same delta to the prior virtual reserve would give 30,217,171,014, a 3,320,959,310-lamport (3.32095931 SOL) difference. Read-only Shyft `getTransaction` confirmed the exact successful transaction and consistent token balances/logs. That does not prove a missing feed transaction. The observed discrepancy could reflect decoder/layout interpretation, protocol virtual-reserve semantics, or a real transition inconsistency; the tracker quarantined the curve.

## Runtime identity limit

Local source hashes and the release-binary hash are recorded in [tracking.json](tracking.json). Local build completion and binary timestamps preceded this VM's start, which is consistent with the repaired source having been built before launch. The runtime summary exposes no build ID or source/binary hash, so it does not prove which exact line was deployed.

No backtest, replay, strategy-performance, or PnL claim is made.
