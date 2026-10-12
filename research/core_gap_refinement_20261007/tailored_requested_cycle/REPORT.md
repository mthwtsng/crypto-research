# Tailored exit retest on the five current entries

Central85 primary60s/percentage-point trail: settled -0.758305 SOL + open marked +1.032373 SOL = combined last-valid marked +0.274068 SOL. 134attempts/86closed/35failed/13unresolved. Full-five verdict: undetermined, retrospective while incomplete exits remain. Open inventory is not a settled loss; zero-recovery is only a downside bound.

## Scope and exit definitions

Five current entry families, including S3two_buy_groups, not the four generic420filled-path families. Optional scope questions received no answer before execution; this assumption and primary percentage-point interpretation match the pasted S1–S5 architecture. No new entry thresholds were supplied or invented. Relative trail sensitivity is separate. All entries and entry fills are matched to the preceding223signal study.

S1:retain trough/net-10%invalidation;40%original tokens at+25%,remaining15pptrail;remove6s timeout. S2:retain9.8shelf,10%armed breakeven;40%at+30%,remaining15pptrail. S3:12%fill-relative price stop after8s grace,trailarms at executable+75%,20ppgiveback,no hardTP;60/120s timeout. S4:retain>=2slot-8%invalidation,half+20%and6%relative trail;remove7s pre-clip timeout. S5:unchanged curve<=60stop,halfafterwholeAMMopening,8%relative remainder trail,30s AMMtimeout. The S4proposal provided no new arm or width, so retained values are explicit. No short timer or file-end sale is invented for S1/S2/S4;undefined long runners retain custody at coverage600s.

## All prescribed central85 continuous full-five comparisons

| S3hold | Trail basis | Creator gate | Attempts/closed/failed/unresolved | Settled SOL | Open marked PnL SOL | Combined marked SOL |
|---|---|---|---|---:|---:|---:|
| 60s | percentage_points | False | 134/86/35/13 | -0.758305 | +1.032373 | +0.274068 |
| 60s | percentage_points | True | 134/86/35/13 | -0.758305 | +1.032373 | +0.274068 |
| 60s | relative | False | 133/85/35/13 | -0.968816 | +1.032373 | +0.063557 |
| 60s | relative | True | 133/85/35/13 | -0.968816 | +1.032373 | +0.063557 |
| 120s | percentage_points | False | 134/86/35/13 | -0.854618 | +1.032373 | +0.177755 |
| 120s | percentage_points | True | 134/86/35/13 | -0.854618 | +1.032373 | +0.177755 |
| 120s | relative | False | 133/85/35/13 | -1.201860 | +1.032373 | -0.169486 |
| 120s | relative | True | 133/85/35/13 | -1.201860 | +1.032373 | -0.169486 |

Matched old tailored-family baseline (S3fullTP20%): settled-2.787669,openmarked+1.059240,combined-1.728429SOL;152attempts/99closed/41failed/12unresolved. New-minus-old combined +2.002497SOL includes changed funded timing/admissions and coverage, not solely target replacement.

## Actual shared-account family contributions

| Family | Closed | Failed | Open | Settled SOL | Open marked PnL SOL | Combined SOL |
|---|---:|---:|---:|---:|---:|---:|
| s1_dev_absorption | 10 | 2 | 1 | -0.017122 | -0.026867 | -0.043989 |
| s2_survival_shelf | 21 | 4 | 0 | +0.140202 | +0.000000 | +0.140202 |
| s3_deadman | 21 | 8 | 0 | +0.450919 | +0.000000 | +0.450919 |
| s4_upper_ath | 28 | 20 | 0 | -0.397588 | +0.000000 | -0.397588 |
| s5_carryover | 6 | 1 | 12 | -0.934715 | +1.059240 | +0.124525 |

MATCHED_ATTRIBUTION.json separates savings on old losers and forfeited/added old-winner upside for both-closed identical entries. Changed unresolved/closed cases are listed separately, never silently discarded. Standalone funded cards are diagnostics, not additive portfolio returns.

## Checks and limits

4740actual simulations/10704assembled scenario repetitions;2016funded ledgers regenerated twice;zero replay exceptions.12focused regression tests include quiet-market grace,immediateTPduringgrace,40/60token conservation and distinct pp/relative trails. Entry position/bill/tokens parity passes10704rows. No completed-curve sale,no before-deadline timer or file-end liquidation. Eight alarms reviewed in CHECKS.json with funded placement/admission decompositions.

Whole-second historical clocks and assumed central80/85inclusion remain. Marks are each path’s last-valid finite-size quote,not common end-date wealth or delivered AMM liquidation. Changed router completion and undeclared runner timeouts remain model/definition gaps; cash commitment retained. No fictionalAMMinflow or universal pool reserves. No production settings or live orders changed.

## Reproduction

Run tailored_requested.py then tailored_report.py. Full traces, frozenSPEC, financial histories and all112continuouscards retained.

## What I would investigate if data and tooling were unconstrained

Resolve complete changed completion/router execution and observed exit inclusion; specify currently undefined runner deadlines before untouched later confirmation.

## Required result card

```text
engine:approved repaired day_general extensions;working hashes CHECKS.json
data:1800creation-selected October3–6launches,223setups166mints;authenticated from-creation histories
rules frozen before data:no;user-directed retrospective comparison;SPEC records inferred entry/trail scope
looks:50prior;8new horizon×trail-basis×creator cases;no winner selected as confirmation
recipe:tailoredS1–S5;S3timeout60s;basispercentage_points;creatorFalse;scopeportfolio;breakersTrue;15SOL/.50SOL/no position cap/.25SOL probes
fast/central80/central85/slow combined last-valid markedSOL:+2.090149 / +0.300923 / +0.274068 / -0.920323
central85settled-0.758305+openmarked+1.032373=combined+0.274068
separate downside zero bounds in same order:-6.161979 / -7.050969 / -7.054381 / -8.299001
stress tailmarked-1.137529;higherfee marked-0.213088;scheduledn/a(allurgent)
attempts/closed/failed/unresolved:134/86/35/13;closedonly-0.740630;openmarkedvalue7.328449
settleddrawdown2.863082;cashdrawdown7.819620;largestwinner0.772639;combinedwithoutlargest-0.498571
PF0.8698677034638324;WR0.23255813953488372;maxopen14;skips{"same_mint_open": 10, "strategy_pause": 59, "probe_pending": 20};unresolved{"counterfactual_completion_displaced": 11, "runner_timeout_undefined": 2};dailysettled{"2026-10-03": 0.755250438, "2026-10-04": 0.690632393, "2026-10-05": -1.600117766, "2026-10-06": -0.604070241}
checks:12focusedregressions;10704entryparity;2016ledgerreproductions;8alarms reviewed
verdict:undetermined,retrospective
changesverdict:complete actual migration exits and undefined runner deadlines;frozen fresh14–21day cohort

```
