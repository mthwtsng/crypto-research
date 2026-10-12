# Shadow refresh — 07:57 UTC, October 11

At the frozen summary **2026-10-11T07:57:05.495343902+00:00**, settled paper PnL is **+0.082764863 SOL**, open lifecycle marked PnL **+0.079239695 SOL**, and combined marked estimate **+0.162004558 SOL**. Thirty closed positions (12 wins/18 losses), zero failed buys, two open S4 positions, zero unavailable marks. Full VM close rows reconcile to the summary. Cash is 14.388364359 SOL; equity 15.162004558 SOL. Open marks are curve paper quotes at the summary's snapshot, not on-chain sales.

The 07:34 snapshot had +0.643900894 SOL settled and no open positions. Nine additional closes lost **0.561136031 SOL**. Combined marked value declined **0.481896336 SOL** after accounting for the two new open marks. The largest winner remains +0.320828694 SOL; excluding it leaves settled **-0.238063831 SOL**, or combined **-0.158824136 SOL**. The earlier positive-with-largest-removed finding applied to its frozen 21-close snapshot and no longer describes this later run.

| Family | Closed | Wins / losses | Settled paper SOL |
|---|---:|---:|---:|
| S1 | 8 | 3 / 5 | +0.080316423 |
| S2 | 4 | 2 / 2 | +0.145953023 |
| S3 | 1 | 0 / 1 | -0.099977489 |
| S4 | 13 | 5 / 8 | -0.425368547 |
| S5 | 4 | 2 / 2 | +0.381841453 |

S4 moved from +0.116090241 to −0.425368547 SOL after four further losses. The two open S4 lifecycle marks remain separate from its settled results. This increases concern about entry quality and how the longer rejection stop bears downside; it does not prove a replacement stop or entry would improve profit.

The latest runtime snapshot has the same 30 closed/two open counts, saved later at 07:57:12 UTC. Per-file capture times remain distinct in MANIFEST.json. All current-VM close rows remain quote-only with actual fills and placement unestablished; runtime/build configuration attribution and the S4-only breaker-map defect remain unresolved.

```text
engine + git revision: descriptive shadow audit; source HEAD 9dcff3f; deployed hash unknown.
data: current VM 30 closes through this frozen 2026-10-11T07:57:05.495343902+00:00 summary; two open marks, curve venue.
rules frozen before this data?: configuration epoch unverified; no changes made in audit.
look count: one additional descriptive snapshot; no optimized variants.
placement: fast/central80/central85/slow not applicable to observed paper quote accounting.
stress: not run for this observational snapshot.
attempts / closed / failed / unresolved: 32 / 30 / 0 / 2; quote marks available for both.
settled + open marked = combined SOL: +0.082764863 + +0.079239695 = +0.162004558.
zero-recovery open-inventory downside bound (cash minus starting bankroll): -0.611635641 SOL; not realized loss or expected PnL.
max drawdown: not reconstructed; largest winner +0.320828694; combined without largest -0.158824136 SOL.
bug alarms: no replay placement/timer tests applicable; 30 closes below >50 win/PF/closure alarm thresholds; receipt coverage not tested here.
verdict: undetermined, retrospective.
what would change verdict: calibrated actual fills, stable source/config epoch, complete causal replay and later frozen 14–21 day evaluation.
```
