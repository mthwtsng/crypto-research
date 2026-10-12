# User-requested unified two-buyer and longer-exit backtest

Research only. All five families retained, S5 eligible from its first signal; no rolling positive10 gate and no ten-trade warmup. 15SOL shared continuous account,0.50SOL tickets,max2pending/open positions. Latest original circuit breakers on headline; off as a control.

## Exact requested scope

S3enters after two separate whole buying transactions, with a new distinct noncreator buyer purchasing>=0.05SOL, within2slots after the original qualifying>=1.5SOL/15% dip; reserve8–18SOL. Other four entries unchanged. The eight-second grace applies only to S3loss/trailing exits; its emergency reserve<8SOL floor is active immediately. There is no scratch at3,8,10or21seconds. Full executable targets+20%/+35% are separate versions, active during grace. A+20%armed8percentage-point trail can fire after grace; hard timeout60/120seconds from our actual entry landing. Other strategies keep their documented lower-endpoint exits. Creator<=15%total authenticated creation-event supply is a separate universal entry ablation. Known associated wallets are not inferred from address count.

## Central85 full-five portfolio

| S3timeout | Full profit target | Developer gate | Zero-recovery netSOL | Executable marked netSOL | Attempts/closed/failed/unresolved |
|---|---|---|---:|---:|---|
| 60s | 20% | False | -1.0290 | +0.1744 | 8/5/1/2 |
| 60s | 20% | True | -1.0290 | +0.1744 | 8/5/1/2 |
| 60s | 35% | False | -1.0290 | +0.1744 | 8/5/1/2 |
| 60s | 35% | True | -1.0290 | +0.1744 | 8/5/1/2 |
| 120s | 20% | False | -1.0290 | +0.1744 | 8/5/1/2 |
| 120s | 20% | True | -1.0290 | +0.1744 | 8/5/1/2 |
| 120s | 35% | False | -1.0290 | +0.1744 | 8/5/1/2 |
| 120s | 35% | True | -1.0290 | +0.1744 | 8/5/1/2 |

Marks are last-valid finite-size liquidation quotes, not realized profit or common end-date liquidation. Unsold positions retain tokens, funded cash commitment and occupancy. Every S5signal is represented; early unresolved positions can block later admissions, independently of warmup.

## Separate known-exit diagnostic and S3alone

| S3timeout / target | Creator gate | Four-strategy diagnostic netSOL | S3 standalone netSOL |
|---|---|---:|---:|
| 60s / 20% | False | -2.0135 | -0.9938 |
| 60s / 20% | True | -2.0135 | -0.9938 |
| 60s / 35% | False | -1.8298 | -0.8101 |
| 60s / 35% | True | -1.8298 | -0.8101 |
| 120s / 20% | False | -2.0285 | -1.0087 |
| 120s / 20% | True | -2.0285 | -1.0087 |
| 120s / 35% | False | -1.8447 | -0.8250 |
| 120s / 35% | True | -1.8447 | -0.8250 |

The diagnostic excludes S5only to isolate measured exits; it is not the requested full portfolio. Standalone strategy accounts must not be added together. All brackets, on/off breakers, earlier/later reset comparisons and continuous results remain in FUNDED.json and cards.

## What currently causes S3 losses

For the 60-second/+20% Central85 S3 account, 13 reserve-floor exits lose 1.714401 SOL; seven profit-target exits earn 0.807575 SOL; one timeout loses 0.082959 SOL; eight failed entries cost 0.004040 SOL. Total: -0.993826 SOL. These are delivered replay outcomes, not peak returns. Several emergency exits occur during the user-required grace exception. No short stagnation scratch remains. An absolute 8 SOL floor gives different risk distances at different entry reserves; whether a different entry distance or floor improves outcomes requires a separate ablation, not an assumption that these losses can be recovered. See S3_LOSS_ATTRIBUTION.json.

## Trajectory claims and developer filter

The quoted150covered curves are150covered trace repetitions across42unique mints, with modes and Central80/85 repeated. Central85two-buyer entries have21fills (29attempts across both windows),8/21positive at10seconds and9/21with net executable MFE>=20% by60seconds. Mean10second return+5.66%, mean60second return−2.50%, mean60second MFE+47.68%. They are promising opportunity diagnostics, not a majority of profitable delivered exits or150independent coins. A small number of large favorable excursions can lift the average.

All223candidate entry holdings have an authenticated creation-event supply denominator and reconstructed creator balance. The15%gate rejects1entry: [{"window": "later", "mint": "Czn5jjKYiMPEDyUGTZ1rDJLHfQp8ostxUjM5B7Erpump", "rule": "s4_upper_ath", "share": 0.300972252579018}]. Most creators are already below this threshold in this selected cohort. This filter does not identify related wallets retaining supply.

## Engine and verification

One scheduling correction is included: after completing migration freeze, evaluate exits against the authentic whole AMM-opening transaction before advancing another swap. Its recorded opening swap and original guards are preserved. Real9Bena carryover regression proves the fast half-sale trigger and landing occur directly after that opening transaction, with token conservation. All four unchanged strategy families were replayed again; their old exit rules were not replaced. Source bootstrap and custody repairs remain covered by prior regressions.

Sixteen focused regression tests pass (opening execution, ledger, repair and the real carryover test). INITIAL_FLOOR_AUDIT.json reconstructs initial own-fill reserves across placement/ticket/fee versions; no successful entry starts below the emergency floor.

10704assembled trace repetitions, zero replay exceptions,2016funded ledgers regenerate identically; all eight alarms reviewed. No3/10/21second scratch, no pre-grace trailing fills, no pre-deadline timeouts, no completed-curve sells, no exact threshold-price fills, and no token/cash conservation errors. Whole-second block timestamps are historical clock estimates; central probabilities are80/85%same-slot assumptions, not85th-percentile measured latency. Fast is the optimistic bracket; tail is stress only.

Changed completion remains a real counterfactual execution gap: our added buy reduces supply, so an original exact-token finishing order may fail. The historical AMM opening cannot be imposed on an incomplete changed path. No fee-only failed quote is promoted to an authenticated router fill, no graduation windfall is invented, and no file-end liquidation is used. This limits full-five profitability conclusions even though S5has no admission warmup.

## Reproduction

Run unified_requested.py then unified_report.py. SPEC.json freezes the user clarification; before_user_target_floor_clarification retains the superseded no-target/no-floor exploratory versions without mixing them into this result. Creator observations, trajectories, all traces, funded histories and checks are saved. These are retrospective tests on inspected October3–6data, not a frozen future14–21-day confirmation.

## What I would investigate if data and tooling were unconstrained

Authenticate complete failed-router execution and changed migration timing; collect true sell intent-to-fill telemetry; validate creator-associated supply through funding/account graphs and evaluate on a broader frozen creation cohort.

## Required full-portfolio result card

## hold60, TP20%, gateFalse, portfolio, breakersTrue

```text
engine + revision: repaired approved day_general extensions; git35d8981; exact working hashes CHECKS.json
data: October3–6UTC,2026;1800creation-selected launches; all eligible histories from creation; both inspected windows
rules frozen before data: no; user-prescribed retrospective comparison after inspecting trajectories
look count:42logged configurations/evaluations including8requested horizon×target×creator cases; all retained
candidate: S3two_buy_groups,8s grace,full TP20%,timeout60s,creator_gateFalse,scopeportfolio,breakersTrue
bankroll15SOL/ticket0.50SOL/max2;cooldown probes0.25SOL;no positive10,no warmup,S5 eligible from first signal
fast/central80/central85/slow all-attempt zeroSOL: -1.083207 / -1.033463 / -1.029040 / -1.162459
markedSOL in same order: +0.129785 / +0.169941 / +0.174363 / +0.040945
stress tail-1.162459;historical0.002916legfee-1.047383;scheduled n/a(allurgent)
central85 attempts/closed/failed/unresolved:8/5/1/2;zero-1.029040;marked+0.174363;closed-only-0.021447
drawdown settled0.092106,cash1.099194;largestwinner0.090447;zero netwithoutlargest-1.119487
PF0.844733291954902;WR0.4;dailysettlednet{"2026-10-03": -0.02195173};skips{"same_mint_open": 1, "concurrency": 214};developer_rejections0;unresolved reasons{"counterfactual_completion_displaced": 2}
bug alarms:8checked; independent timer deadlines, no fictional threshold fills, source/custody provenance and whole opening-tx exit regression
verdict:undetermined,retrospective
what changes verdict:resolve changed completion/migration/router execution; frozen14–21-day later-data replay with measured sell delivery
```

