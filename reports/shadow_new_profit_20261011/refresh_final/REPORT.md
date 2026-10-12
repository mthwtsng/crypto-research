# Latest reconciled shadow snapshot

At **2026-10-11T16:34:14.077555637+00:00**, VM `ghost-v2-20261011T064058` has **39 closed paper outcomes, 16 wins/23 losses, settled −0.218531123 SOL, zero open positions and zero unavailable marks**. Cash/equity is 14.781468877 SOL. Full current-VM closes sum exactly to the summary.

The earlier 07:34 snapshot (+0.643900894 SOL) was positive, but subsequent closed outcomes gave back 0.862432017 SOL. The largest winner remains +0.320828694 SOL; settled PnL without it is −0.539359817 SOL. These are recorded paper outcomes, not established on-chain fills.

| Family | Closed | Wins/losses | Paper settled SOL |
|---|---:|---:|---:|
| S1 | 10 | 3/7 | -0.080546390 |
| S2 | 5 | 3/2 | +0.257892420 |
| S3 | 2 | 0/2 | -0.285183079 |
| S4 | 16 | 7/9 | -0.347693735 |
| S5 | 6 | 3/3 | +0.236999661 |

The live files continue changing. This report describes the frozen timestamp above, not subsequent activity. Historical 07:34 and 07:57 snapshots are preserved in sibling reports. Runtime/build attribution, the saved S4-only breaker map and uncalibrated RPC/receive-clock paper placement remain unresolved. No strategy or runtime changes were made in this audit.

```text
engine + revision: observational paper ledger; original audit source HEAD 9dcff3f; deployed build/config identity unavailable.
data: current-VM closed rows through 2026-10-11T16:34:14.077555637+00:00; snapshot raw files and hashes in MANIFEST.json.
rules frozen before data?: no verified deployed configuration epoch.
look count: descriptive refresh; no tuned variants.
placement: fast / central80 / central85 / slow not run for this observational snapshot.
stress: not run for this observational snapshot.
attempts / closed / failed / unresolved: 39 / 39 / 0 / 0.
settled + open marked = combined SOL: −0.218531123 + 0 = −0.218531123.
zero-recovery equals settled because no inventory remains open; no committed capital treated as loss.
max drawdown: not reconstructed; largest winner +0.320828694; without largest −0.539359817 SOL.
bug alarms: replay placement/timer alarms not applicable; closure/win-rate/PF alarms requiring >50 do not trigger; receipt creation coverage not tested by this observational audit.
verdict: undetermined, retrospective.
what would change verdict: stable source/config epoch, calibrated actual fills, complete causal screen/receipt coverage and later frozen 14–21 day evaluation.
```
