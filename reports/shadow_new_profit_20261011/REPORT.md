# Shadow new-results audit — October 11, 2026

At the 07:34:47.754946230 UTC summary, the 15 SOL shadow ledger shows **21 closed paper outcomes, +0.643900894 SOL, 10 wins and 11 losses**, with no failed buys or open positions. The paper ledger is positive, but this is not a central-placement backtest or actual wallet PnL: every current-VM close lacks an established fill and has uncalibrated placement, so the verdict remains **undetermined, retrospective**.

Compared with the [07:19:47 frozen audit](../shadow_situation_20261011/REPORT.md), closed PnL rose by **+0.802118146 SOL** across 12 closes. One close, **+0.320828694 SOL on the S5 position already open at the earlier snapshot**, resolved an earlier +0.399675151 SOL open mark. The other 11 positions were opened after that snapshot and closed for **+0.481289452 SOL (6 wins, 5 losses)**. Including the earlier open mark, account marked value improved by **+0.402442995 SOL** between snapshots.

## Reconciled account and contributions

At the current snapshot, virtual cash and equity are both **15.643900894 SOL** against the recorded 15.0 SOL starting bankroll. The runtime has 21 closed positions, no open paper positions, and no failed-buy fees. The 21 current-VM `CLOSE` rows sum exactly to the summary’s **+0.643900894 SOL**.

The summary’s `recent_closed_trades` contains 20 rows and sums to +0.737717606 SOL. It omits the oldest current-VM close, an S4 loss of **−0.093816712 SOL** (`AgpQqukiTNoT...`). The frozen trade log and runtime state contain all 21 closes; including that omitted row reconciles exactly to the account total. The 111-row source trade log spans five VM IDs, so this report uses only the 42 OPEN/CLOSE rows for `ghost-v2-20261011T064058`.

The file freeze is per-file, not a simultaneous filesystem image: the last trade event is timestamped 07:34:07 UTC, the summary was updated at 07:34:47, and runtime state was saved at 07:34:55. The state reconciles across them, and the timestamps remain distinct in the manifest.

| Strategy | Closed | Wins / losses | Paper PnL (SOL) |
|---|---:|---:|---:|
| S1 | 5 | 2 / 3 | +0.164861040 |
| S2 | 2 | 1 / 1 | +0.081085649 |
| S3 | 1 | 0 / 1 | −0.099977489 |
| S4 | 9 | 5 / 4 | +0.116090241 |
| S5 | 4 | 2 / 2 | +0.381841453 |
| **All** | **21** | **10 / 11** | **+0.643900894** |

The largest winner was the carried S5 position at **+0.320828694 SOL**. Removing it leaves **+0.323072200 SOL** for the other 20 closes. Other leading winners were S1 `FsTCTf...` (+0.242749819), S4 `GEp6zF...` (+0.175735865), and S2 `J9pbNm...` (+0.142703258). S5 contributed +0.381841453 SOL in total, including the carried position.

At 07:19, settled closed PnL was −0.158217252 SOL and the one open S5 lifecycle mark was +0.399675151 SOL, giving a combined marked estimate of +0.241457899 SOL. That S5 position later recorded +0.320828694 SOL on closure, 0.078846457 SOL below its prior mark. At 07:34, settled paper PnL is +0.643900894 SOL, open marked PnL is zero, and combined marked estimate is +0.643900894 SOL. No open capital is being treated as a loss.

## What this snapshot establishes

The outcome is positive for this recorded paper ledger, including after removing its largest winner. It does not establish strategy profitability under live fills: all 21 current-VM close records have `actual_fill_established=false`, `placement_calibrated=false`, and no `our_signature`. The summary also sets `performance_validated=false`. It describes the execution model as provisional 70 ms receive-clock curve/AMM quotes; AMM execution is explicitly “authenticated RPC snapshot paper quotes, no on-chain sales,” with the first fresh pool snapshot after intent-ready time uncalibrated.

The current VM label is unchanged from the prior snapshot, but it does not establish one unchanged process or configuration epoch. The archived 07:03:05 summary for this ID had four closes and `uptime_secs=742`; the 07:19:47 summary had nine closes and `uptime_secs=920`; the current summary has 21 closes and `uptime_secs=1880`. That counter progression does not match elapsed wall time, so it suggests a restart/restore or a non-comparable uptime field; the exact boundary is unknown. The current source tree remains at `9dcff3f` and its five runtime-related hashes match the prior audit, but runtime state records no deployed build or effective-config hash. The summary says its execution model is v3 while all current event rows say quote-v2; whether this is schema-label drift or a runtime difference is unresolved. Current status still says breakers are enabled while the saved breaker map contains only S4. The prior audit documents material differences between this shadow package and the canonical S1–S5 controls. These outcomes therefore cannot be attributed to one verified, frozen strategy configuration.

The broader trade log contains other VM IDs and older failures; those are not combined with this account. The current VM’s event rows span 06:57:59–07:34:07 UTC. No replay, RPC fill reconstruction, or strategy change was performed for this audit.

Frozen files: [snapshot manifest](evidence/SNAPSHOT_MANIFEST.json), [summary](evidence/ghost_summary.json), [current-VM events](evidence/current_vm_trades.jsonl), and [runtime excerpt](evidence/runtime_state_excerpt.json). Full raw summary, trade log, and runtime snapshot are also held at `/tmp/new_profit_20261011_snapshot/`; their hashes are recorded in the manifest.

## Entry and exit implications of the new winners

The new S4 sample has five winners and four losers. Three losers still recorded essentially no positive executable return; the fourth (`HVUTqm`) reached +18.12% before closing −0.155603430 SOL. That makes it a useful case for testing an earlier protection rule, but it does not establish that changing the +20% half tranche improves the family. The same early rule could sell the five winners sooner. The two S1 winners entered at 5.66 and 5.94 SOL after signals at 4.48 and 4.46 SOL; blindly enforcing the signal's 5 SOL reserve ceiling at landing would exclude both. Entry quality needs price/demand evidence, not just a rigid reserve cutoff.

S5's four closed positions expose the current exit tradeoff particularly clearly. The +0.320829 SOL winner sold a tranche; the other three did not. `ABEHCN` opened its AMM mark at +19.83% net, peaked at +31.57%, and closed −0.007037 SOL. `2TioXz` opened at +24.88%, peaked at +30.74%, and closed −0.011564 SOL. Their required first-tranche levels were approximately +69.83% and +74.88% net, respectively, because the current rule requires **50 percentage points above the AMM-open return**. An absolute first profit tranche or protection after a smaller post-open gain is a plausible development experiment, preserving a runner for post-migration upside. No alternative-exit profit is established by those peaks. The four AMM-open anchors, peaks and tranche flags come from the frozen runtime, with quote-only and polling limitations described above.

## Result card

```text
engine + git revision: observational shadow ledger; no approved replay run. Workspace source HEAD is 9dcff3f509b40d78d51921509ca09e79a2eafe63 and matches prior audited source hashes; runtime has no bound binary/config revision.
data: 2026-10-11 06:57:59–07:34:07 UTC; VM ghost-v2-20261011T064058; live-runner admitted positions, not an outcome-selected tape; creation-complete tape coverage not checked.
rules frozen before this data?: no verifiable configuration epoch; runtime/config hashes absent and prior audit records deviations from canonical controls.
look count: one descriptive snapshot audit; zero new replay variants.
placement: fast / central(p=0.80) / central(p=0.85) / slow -> not run; no central placement estimate.
stress (next_slot_tail, 0.002916 fees, 3-slot scheduled sells): not run.
attempts / closed / failed / unresolved: 21 / 21 / 0 / 0. Paper closed PnL +0.643900894 SOL; open marked PnL 0; combined marked estimate +0.643900894 SOL; zero-recovery bound 0 for open inventory.
max drawdown, largest winner, PnL without largest winner: not reconstructed; +0.320828694 SOL; +0.323072200 SOL.
bug alarms checked (section 6): no replay, so placement/trigger alarms not applicable or not checked; attempts==closed with >50 is not triggered (21); PF>3 or win-rate>70% with >50 trades is not triggered (21, PF 1.78, win rate 47.6%); creation coverage unknown.
verdict: undetermined, retrospective.
what would change the verdict: a frozen source/config epoch, complete causal tape and migration coverage, approved replay with central80 and central85 placement, and calibrated fills over the required later evaluation window.
```
