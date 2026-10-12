# Recent trade log audit — October 11, 2026

Frozen at 22:21:03 UTC (15:21:03 Vancouver), VM `ghost-v2-20261011T220021`, approximately 21 minutes since reset. Recorded paper settled PnL **−0.951079036 SOL + open marked PnL 0 = combined −0.951079036 SOL**. Cash/equity **14.048920964 SOL**, down **6.34%** from the 15 SOL session bankroll. **16 closes, 3 wins/13 losses, 18.75% win rate, profit factor 0.244**. Zero open inventory, unavailable marks or failed buys. These are shadow quotes: all current-session rows explicitly say `actual_fill_established=false`, have no own transaction signature and uncalibrated placement.

| Family | Closed | Wins / losses | Settled paper SOL |
|---|---:|---:|---:|
| S1 absorption | 5 | 1 / 4 | −0.084120 |
| S2 shelf | 2 | 0 / 2 | −0.194642 |
| S3 bounce | 1 | 0 / 1 | −0.297482 |
| S4 breakout/reclaim | 5 | 1 / 4 | −0.322340 |
| S5 migration carryover | 3 | 1 / 2 | −0.052495 |

## Findings

1. **S3 grace exposes the position to a large collapse.** `4tvJ2EZAawYTFw84obX1ewozi7vUvBLe6oCwd8Bypump` entered at 22:03:32.747 UTC with 17.90 SOL real reserves. The exit source receipt was available at 22:03:40.721; at the 18-second timer trigger, reserves were just 1.043 SOL. The exit intent fired at 22:03:50.762 and landed at 22:03:50.864, losing 59.3% (0.297482 SOL). The loss was already 59.3% at trigger; the quote did not show a major additional trigger-to-fill loss. Current source has no unconditional catastrophic stop in S3: the −18% stop waits for 18 seconds, while trailing requires a prior +20% peak. This position's peak was +11.8%. An earlier exit's savings require causal replay; none are claimed here. See `src/bot/curve_detector.rs:1643` and frozen CLOSE row/runtime last fill.

2. **The latest S2/S4 reclaim entries are weak in this short sample.** All seven entries have corresponding `RECLAIM_ENTRY` telemetry. Both S2 trades lose (−14.2%, −24.6%). S4 has four losses (−18.7% to −24.3%) and one +17.3% win. S4 losses have recorded executable peaks of 0%, 0%, +0.5% and +9.5%. Reclaim requires a dip and return to the prior breakout level; it is not a discounted fill at the trough. Source rejection is >=25 slots, net <=−18%, peak <+10%, with an immediate −22% severe-dump trigger. These differ from the registry's original >=2-slot/−8% rejection. No alternate recipe was tested.

3. **Breaker enforcement is incomplete.** Both summary and saved runtime expose only S4, though the summary says breakers enabled. Current `try_open_signal` uses `get(...).map_or(false, ...)`, so missing S1/S2/S3/S5 entries do not block admission; closed-result updates also require an existing map entry. Checkpoint restore replaces the initial all-five breaker map with the saved partial map (`src/bin/curve_detector.rs:383`); an independent GPT-6 Luna xhigh review confirmed this cause. This is a real control defect, but the latest 16 trades alone do not show that every family's canonical breaker threshold should already have tripped. Repeated session resets also make the displayed 15 SOL balance a session baseline, not cumulative wealth.

4. **Post-exit labels overstate what they measure.** Curve `post_exit_change_pct` is `(current_real_reserves / exit_real_reserves − 1)`, not token-price return or an executable holding return. For example S1 `CkUgb...` says “Left on table +601.6%”, reflecting reserves rising from ~0.503 to ~3.528 SOL. It cannot be read as a missed +601.6% trade. Two losing S4 coins also rebounded after exit, whereas others continued down. A blanket claim that all losses were bad entries, or all stops were premature, is unsupported.

5. **Carryover exits work in this sample.** All three current-session S5 positions have closed through AMM quotes; no position is stranded at migration. One wins +0.085007 SOL; two lose −0.010601 and −0.126901 SOL. The small loser peaked +22.6% and ended −2.1%, showing giveback under the currently logged 18% AMM trail. The winning S5 subsequently dropped sharply by the AMM watch's spot comparison. No alternate-exit profit is inferred from these observations.

## Checks and scope

The trade file contains 48 rows across three VM IDs. Filtering by the current VM yields 16 unique OPEN/CLOSE pairs; their CLOSE PnL exactly reconciles to summary settled PnL and 15 SOL plus settled PnL equals equity. No old-session closes were added to this baseline. Summary trade datetimes are refresh times; actual chronology here uses JSONL close times. Runtime evidence was captured shortly after the summary and has the same ledger counts and balances. Existing user/source changes were preserved. No trades, strategy changes, restarts or configuration changes were performed.

Priority for follow-up is complete breaker initialization/restoration, then a bounded causal examination of S3 collapse protection and S2/S4 reclaim demand. This audit does not establish that adjusting a stop would improve portfolio profitability.

What I would investigate if data and tooling were unconstrained: replay the full receipt sequence with calibrated own-order landing telemetry to distinguish grace exposure, failed reclaim demand, migration liquidity changes and executable rebounds. Required data: authenticated creation-to-AMM tapes, actual submission/inclusion timing and pinned deployed configuration epochs.


## Final refresh

At 2026-10-11T22:23:23.277184474+00:00, same VM: 19 closed paper positions, 5 wins/14 losses; settled -0.786696695 SOL + open marked 0 = combined -0.786696695 SOL. Cash/equity 14.213303305 SOL. Zero open/unavailable marks/failed buys. Full current-VM close rows reconcile. This is an improvement from the frozen main audit and is still negative. Findings above refer to the original 16-close cohort. Recorded observations only; central placement/stress unavailable, verdict undetermined, retrospective. Supplemental files preserve this refresh.

## Required result card

```text
engine + git revision: observational paper-log audit; source HEAD in MANIFEST.json; deployed binary/config hash unavailable.
data: current VM, 22:00:21–22:21:03 UTC on 2026-10-11; all 16 current-session closes, no outcome-selected subset; creation coverage not established.
rules frozen before data?: deployed configuration epoch not verified; no tuning during audit.
look count: one descriptive log audit, zero strategy variants.
placement: fast / central80 / central85 / slow not run; central estimate unavailable from these provisional 70ms receive-clock quotes.
stress: not run; no replay or modeled alternative PnL claimed.
attempts / closed / failed / unresolved: 16 / 16 / 0 / 0; pending/open 0.
settled + open marked = combined: −0.951079036 + 0 = −0.951079036 SOL.
zero-recovery: equals settled, because no open inventory; no mark venue/time needed.
max drawdown: closed-settlement curve 0.951079036 SOL; intraposition equity drawdown not reconstructed.
largest winner: +0.135041424 SOL; PnL without it: −1.086120460 SOL.
bug alarms: placement/speed comparison not evaluated; timer anchor checked for standout S3 (trigger 18.015s after buy, fill 18.117s); delayed zero-failure alarm (>30), all-closed (>50), PF>3/WR>70% (>50) do not trigger at n=16; exact-threshold fill not observed in closes; curve-after-completion and genesis coverage not exhaustively checked. Accounting/unique-close reconciliation passed.
verdict: undetermined, retrospective (negative recorded paper subset; no calibrated central estimate).
what would change verdict: calibrated landing/quotes, pinned source/config epochs, complete receipts/migration and later frozen evaluation.
```
