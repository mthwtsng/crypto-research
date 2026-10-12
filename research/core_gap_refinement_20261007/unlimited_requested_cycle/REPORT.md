# Unlimited cash-funded portfolio with S3 relative stop

Central85: settled closed-plus-failed PnL -2.787669 SOL + open marked PnL +1.059240 SOL = combined last-valid marked estimate -1.728429 SOL. The12open holdings are all positive at their individual last-valid curve quotes; none is counted as a realized losing trade.152attempts,99closed,41failed,12unresolved. Full-five verdict: undetermined, retrospective. Zero-recovery -8.830201 SOL is only a downside bound, not expected loss or realized PnL. S5including its positive open marks is +0.124525 SOL; its actual delivered exits remain incomplete.

## Exact change and matched controls

15SOL shared account,0.50SOL tickets, no concurrency cap. Available cash remains mandatory; unresolved custody, commitment and same-mint blocking remain. S3 replaces immediate reserve8floor with a12%relative marginal-price fall from actual fee-inclusive average buy fill(entry_bill/entry_tokens), evaluated after completed transactions and independently at8s grace expiration. The stop is deferred through grace; full executable20/35%TP remains immediate. Original20%-armed8percentage-point trail and60/120s timeout retained; other four strategies unchanged. Price return and executable net return differ;12% is a trigger, not a guaranteed maximum delivered loss. Controls retain the old floor and2position ledger to isolate both changes.

## Central85 continuous full-five, breakers on, no position cap

| Horizon | FullTP | Creator gate | Attempts/closed/failed/unresolved | Zero-recovery downside bound SOL | Last-valid marked estimate SOL |
|---|---|---|---|---:|---:|
| 60s | 20% | False | 152/99/41/12 | -8.830201 | -1.728429 |
| 60s | 20% | True | 152/99/41/12 | -8.830201 | -1.728429 |
| 60s | 35% | False | 152/99/41/12 | -8.687803 | -1.586032 |
| 60s | 35% | True | 152/99/41/12 | -8.687803 | -1.586032 |
| 120s | 20% | False | 152/99/41/12 | -8.830201 | -1.728429 |
| 120s | 20% | True | 152/99/41/12 | -8.830201 | -1.728429 |
| 120s | 35% | False | 152/99/41/12 | -8.687803 | -1.586032 |
| 120s | 35% | True | 152/99/41/12 | -8.687803 | -1.586032 |

## Admission and cap/stop decomposition

223 signals across166mints; with breakers on 152attempts, {'same_mint_open': 9, 'strategy_pause': 62}; peak13pending/open. No concurrency or cash skips. Creator filter rejects one ATH candidate and its effects are reported in all eight rows. Breaker-off comparison admits210, skips{'same_mint_open': 13}, closes147, fails52, unresolved11; zero-9.022459, marked-2.529482SOL. All223signals are evaluated; this does not promise223admitted buys.

| Stop / capacity control,60s TP20%,gate off | Attempts | Zero-recovery SOL | Marked SOL |
|---|---:|---:|---:|
| reserve_floor_control / 2 | 8 | -1.029040 | +0.174363 |
| reserve_floor_control / None | 154 | -8.990792 | -1.889021 |
| relative_price_stop / 2 | 8 | -1.013558 | +0.189845 |
| relative_price_stop / None | 152 | -8.830201 | -1.728429 |

Uncapped relative-stop vs uncapped old-floor improvement: +0.160592SOL marked at60s/TP20. This is the whole-policy comparison with changed same-mint admission timing, not a proof that every stop change helps. Both remain negative on known outcomes.60and120second versions coincide in this cohort because exits/censoring precede the differing deadlines.

## Family contributions in the actual shared account

| Family | Closed | Failed | Unresolved | Closed-plus-failed SOL |
|---|---:|---:|---:|---:|
| s1_dev_absorption | 22 | 8 | 0 | -0.446812 |
| s2_survival_shelf | 22 | 4 | 0 | +0.023950 |
| s3_deadman | 21 | 8 | 0 | -0.907725 |
| s4_upper_ath | 28 | 20 | 0 | -0.522366 |
| s5_carryover | 6 | 1 | 12 | -0.934715 |

## Migration mark provenance and accounting correction

UNRESOLVED_MARK_PROVENANCE.json identifies all12marks as curve-side; all12source histories contain authenticated AMM continuation, but the changed replay does not establish those exits.11paths encounter displaced completion and one hits an undefined runner horizon before historical opening. These are migration-model coverage gaps, not12realized losses. ACCOUNTING_CORRECTION.json proves all8064old numeric results, admissions and fills unchanged while adding explicit settled/open fields. Positive marks were already included in the combined estimate, so adding their value again would double-count.

1392S3 replay jobs recomputed; unchanged four-family outcomes reused from checked saved replay.10704assembled trace repetitions,8064alternative ledger scenarios regenerate identically.10704entry outcome/position/bill/token comparisons against the old-floor source pass. Eight funded-ledger tests plus two independent price/grace clock fixtures pass; the latter proves a relative stop waits until8s even without another trade and TP remains active at1s. No production changes. Historical blockTime has whole-second precision, central80/85 placement is an assumption, and failed routed completion remains unverified.11of12unresolved positions have counterfactual_completion_displaced;one runner_timeout_undefined. Last-valid marks are not synchronized end-date wealth. Uncapped occupancy reveals rather than fixes those gaps.

## Reproduction

Run unlimited_requested.py then unlimited_report.py. Source/relative traces, complete admission lists, cap/floor controls, hashes and alarm decompositions are retained. Each funded ledger is a separate scenario; do not sum profits across cards.

## What I would investigate if data and tooling were unconstrained

Authenticate complete changed router/completion execution, migration timing and sell intent-to-fill telemetry; define the missing runner deadline with user-approved rules before fresh prospective testing.

## Required result card

```text
engine + revision: approved day_general repaired extensions; exact hashes CHECKS.json
source: 1800creation-selected launches October3–6UTC;223signals across166mints;complete authenticated genesis histories
rules frozen before data: no; previously inspected retrospective cohort; user-prescribed change frozen before this replay
look count:42prior,8new relative-stop horizon/TP/developer cases; original2position/reserve-floor controls retained
candidate: S3relative12% marginal-price trigger vs fee-inclusive average fill;8s grace;fullTP20%;timeout60s;creator_gateFalse;scopeportfolio;breakersTrue
15SOL cash-funded shared ledger;0.50SOL tickets,0.25SOL cooldown probes;no position cap; unresolved custody retained;one position per mint
downside-bound fast/central80/central85/slow zero-recovery SOL: -8.542872 / -8.777508 / -8.830201 / -8.251567
headline last-valid finite marked SOL, fast/central80/central85/slow: -0.852061 / -1.652293 / -1.728429 / -1.099567
stress: tail-7.781012;0.002916legfee-8.829412;allurgent scheduled n/a
settled closed-plus-failed SOL:-2.787669; open marked PnL SOL:+1.059240; combined marked SOL:-1.728429
central85attempts/closed/failed/unresolved:152/99/41/12;zero-8.830201;marked-1.728429;closed-only-2.766964
settledDD3.373227;cashDD9.458981;largestwinner0.302827;zero_withoutlargest-9.133027
maxsimultaneous13;skips{"same_mint_open": 9, "strategy_pause": 62};unresolvedreasons{"counterfactual_completion_displaced": 11, "runner_timeout_undefined": 1}
PF0.5037353673925763;WR0.26262626262626265;dailysettlednet{"2026-10-03": -0.026867219, "2026-10-04": 0.168502339, "2026-10-05": -1.935778664, "2026-10-06": -0.993525649}
8bug alarms reviewed;entryparity10704;8064reproduciblefundedledgers;10focusedregressions;cash/token/timer/causalchecks pass
verdict:undetermined,retrospective
what changes verdict:resolve unknown counterfactual completion/undefined runner horizon; frozen later14–21-day cohort with measured execution

```
