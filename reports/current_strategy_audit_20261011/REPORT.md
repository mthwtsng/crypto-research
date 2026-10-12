# Current strategies, old/new logs, and backtest accuracy

Audit cutoff: **2026-10-11 23:12:55.541 UTC**. This is a frozen read-only audit, not a strategy deployment or a new backtest. See `MANIFEST.json`, frozen ledgers, `session_statistics.json`, the source review and the backtest review in this folder. GPT-6 Luna at max performed bounded source/provenance reviews; GPT-6.1 Luna is unavailable in this runtime. Root reviewed the accounting and recommendations.

## Main finding

The main gap is **entry quality plus consistency between the tested rules and the running rules**. Several entries never reach a positive executable return, while S3/S5 allow substantial loss or giveback. A better fake-coin filter alone does not establish that an admitted coin is a good trade. The new V3 detector is visible in runtime telemetry, but has too little trade history to judge its effectiveness.

## What the logs actually say

The last completed 22:00:21 UTC paper session had 45 closes, 13 wins and 32 losses. Its archived summary reconciles to **−1.104530542 SOL**, zero open positions, zero unresolved marks, and 13.895469458 SOL equity from 15 SOL. Results include paper entry/exit fees; these are not actual onchain fills.

| Family | Closes | Wins / losses | Settled SOL | Losing trades with no positive executable peak |
|---|---:|---:|---:|---:|
| S1 absorption | 13 | 1 / 12 | −0.536209 | 10 / 12 |
| S2 shelf/reclaim | 4 | 0 / 4 | −0.362306 | 3 / 4 |
| S3 dip bounce | 8 | 4 / 4 | −0.049888 | 2 / 4 |
| S4 upper breakout/reclaim | 15 | 7 / 8 | +0.179781 | 4 / 8 |
| S5 migration carryover | 5 | 1 / 4 | −0.335909 | 0 / 4 |

S4 recovered after the earlier 19-close audit; describing it as the largest loser would now be wrong. Conversely, the earlier 06:40:58 session had S2 positive (+0.286363 SOL) and S4 negative (−0.807084 SOL). Both windows are small, different admission populations. Neither identifies a universally profitable family.

The newest 23:10:14 session, after the V3 rollout, had **two S4 closes, both losses, settled −0.207524420 SOL** at cutoff. Open marked PnL is zero, unresolved count zero, combined marked estimate equals settled PnL; cash/equity is 14.792475580 SOL. Their peaks were only +4.8% and +3.4%. One continued into a roughly 70% real-reserve fall after exit; this is a reserve observation, not a proof of the coin's terminal price or a replay of alternative exits.

We inspected 290 unique closes across archived/current ledgers. Do not sum their PnL into a continuous-account claim: the logs span resets, different rule epochs, cross-session closures and migration repair/force-sell artifacts. The delayed historical S5 closure after 9,538 seconds particularly needs execution-coverage diagnosis rather than interpretation as normal S5 behavior. JSONL event timestamps were used; dashboard recent-close datetimes can reflect summary refresh time.

## Concrete flaws and the next bounded tests

1. **S1 buys weak bounces.** Ten of twelve recent losers never achieved a positive executable peak. Its signal trough window is 35 slots rather than the canonical three, changing what counts as a fresh absorption event. First compare the canonical fresh-window control with the current window, and require completed-receipt independent absorption evidence. Compare smaller tickets using actual finite-size quotes. Do not infer true price impact from the log's `buy_impact_pct`, which measures real-reserve change. Wider stops have no supporting evidence here.

2. **S2/S4 reclaim can reuse an obsolete setup.** The wrapper arms at a breakout, waits for an 8% pullback, then buys an outside-buy reclaim within 180 seconds. It refreshes reserve/time/slot but does not rerun the original structural setup or cap overshoot before submitting. A deep collapse and later retest can therefore inherit the old setup. Revalidate the original structure and buyer evidence at confirmation, and compare a bounded overshoot/freshness condition against the exact current control. This is entry research, not a proposal to classify ordinary sell pressure as fake activity.

   S2 also arms its breakeven exit at **+20% in executable code**, versus +10% in the adjacent comment and canonical control. Include this mismatch in parity repair and test it separately; the comment is not the effective setting.

3. **S3 tolerates large losses before its stop becomes eligible.** Actual code is 18 seconds / −18%, versus canonical eight seconds / −12%. One recent loss was roughly −59% after 18 seconds, costing 0.297482168 SOL; the other seven closes together were positive, which shows concentration, not that deleting this trade creates an edge. Test the canonical stop package first, then a separately declared catastrophe guard during grace. Executable delayed fills must determine PnL: a stop threshold cannot guarantee its fill. S3's dip-buy counter counts decoded buy events, not necessarily distinct complete transactions; two events in one transaction are not two independent confirmations. Solana instructions execute atomically, so confirmation should use completed successful receipts ([official transaction documentation](https://solana.com/docs/core/transactions)).

4. **S4 has a protection gap after a modest bounce.** The ordinary rejection exit requires at least 25 slots, ROI ≤−18%, and lifetime peak <+10%. A trade that peaks between +10% and +20% disables this exit before reaching the +20% partial sale; its remaining pre-tranche safeguard is −22%. Test protection for that interval as a separate change. Keep its winning paths in the comparison: this family was positive in the completed session. The saved one-day matched-entry comparison improved when using the canonical exit package, but it was developed on that sample and is not an isolated, validated S4 improvement.

5. **S5 gives back opening gains and uses a delayed opening reference.** Four recent losers had positive peaks; one peaked around +45.9% and closed around −27.6%. Current rules use a 60-second grace, an 18% trail, and a half-sale target 50 percentage points above the first observed pool ROI. A strong opening can therefore set a very high profit target. The opening clock/reference is the first authenticated snapshot acquired by the bot, which can be later than actual pool opening. Repair opening provenance/coverage first; then compare the canonical migration exit with the current package and one earlier partial-sale/protection variant. Preserve token custody through migration and sell only into authenticated pool liquidity.

6. **Risk controls differ from the backtest.** The frozen running checkpoint reports only S4 in its enforced breaker map; the saved day replay uses canonical all-family/global breakers. Restoring checkpoint state can replace the initialized map. Restore/verify all intended family controls and global pause/probe behavior before treating the replay as a runtime risk estimate. This is a parity defect, not evidence that a particular cooldown threshold is optimal.

## Are the backtest levels accurate?

The underlying approved replay has considerably stronger mechanics than a spot-price spreadsheet: integer finite-size quotes, whole-transaction placement, fees, guards, independent timers, own-impact/counterparty repricing and migration custody. Its saved Oct 11 results reconcile. But **correct quote arithmetic does not validate the entry levels, stop settings or expected profitability of today's bot**.

The best saved fixed-hash one-day current/local replay is Central80 **−1.238073788 SOL**, Central85 **−1.238466812 SOL**; fast −1.045396720 and slow −1.357544916. It has 18 attempts, 16 closes, two guard failures and no unresolved positions. This omits unavailable historical holder evidence: the fully screened historical run has zero eligible setups because coverage is insufficient. It also predates the new V3 relationships detector, does not reproduce current reclaim admission, and uses different breakers. It is not an exact replay of today's bot.

The older large positive active-cohort claims are **unverified in this checkout**: the referenced report/output and engine dependency are missing, while the available manifest is incomplete and explicitly selected on later activity. A cohort selected because it subsequently traded actively cannot establish performance over all launches using information available at entry. Recover the artifacts before using those figures as benchmarks; do not label them fabricated or a banned-engine result without evidence.

Live shadow accuracy has a separate limitation. A paper buy changes local reserves, but the next authoritative external receipt resets those reserves to the historical public path. Its own impact does not persist as it does in the approved replay. The 70ms receive-clock placement and AMM snapshot delivery are uncalibrated; telemetry explicitly says actual fills=false, placement_calibrated=false and performance_validated=false. Bias direction is unknown. Likewise, a 90% retained-token output guard is not a guaranteed 10% loss cap.

At cutoff, V3 recorded Watch/Unknown evidence and zero hard blocks in its short new log window. Watch admits partial evidence; many probes lacked completed funding/receipt/cross-launch coverage. This is a coverage finding, not proof that admitted coins are organic. Preserve these uncertainty fields and whitelisted admissions in the next evaluation.

## Priority and validation

First fix test/runtime parity and receipt/opening provenance. Then evaluate S1 freshness, S2/S4 confirmation revalidation, S3 downside protection, S4's intermediate-peak gap, and S5 profit protection **one change at a time**. Keep the exact current control and canonical control, cash-funded 15 SOL accounting, Central80/85 placement, fees, full transaction boundaries, all declared risk controls and authentic AMM carryover. Freeze the chosen candidates before an untouched 14–21 day creation-selected holdout. Report eligibility/coverage alongside PnL so blocking most coins cannot masquerade as improvement. No threshold in this audit is claimed to be profitably optimized.

Unconstrained investigations: causal wallet/funder cluster persistence across launches, executable absorption after independent buyers, migration opening coverage, ticket-size sensitivity to actual liquidity, and regime-dependent admission are reasonable hypotheses beyond fixed reserve levels. These need decision-time data and frozen controls, not selection of later winners.

## Result card

```text
mode: read-only source/log/provenance audit; no new replay or deployment
data: frozen logs through 2026-10-11 23:12:55.541 UTC; separate reset/rule epochs
engine: running provisional receive-clock paper quotes; saved backtest approved day_general/core_plan family (details in backtest_accuracy_review.md)
rules frozen before data: no prospective validation; retrospective diagnostics
look count: five strategy families, two detailed log sessions, saved historical comparisons; no optimization sweep
current paper accounting: settled −0.207524420 + open marked 0 = combined −0.207524420 SOL; unresolved 0; equity 14.792475580 SOL
completed prior session: settled −1.104530542 + open marked 0 = combined −1.104530542 SOL; unresolved 0; equity 13.895469458 SOL
saved current/local replay: Central80 −1.238073788 / Central85 −1.238466812 SOL; fast −1.045396720 / slow −1.357544916; 16 closed / 2 failed / 0 unresolved
saved stresses/alarms: see backtest_accuracy_review.md; no fresh replay alarms run
placement: current paper uncalibrated; replay central assumptions not measured for today's intents
verdict: UNDETERMINED, RETROSPECTIVE; evidence of losses and concrete parity/control defects; no demonstrated profitable tweak
what changes verdict: exact current-rule replay, causal detector/opening coverage, calibrated execution and later untouched 14–21 day results
```
