# Codex calibration: you have been underestimating

Created: 2026-10-04 from an audit of recent research. Read with [the shared accuracy contract](BACKTEST_ACCURACY_CONTRACT.md), which you must follow.

Your engine (`research/day_general_20261004`) is the most correct one in the repository: integer quotes, custody, independent timers and post-dump stop fills. But your reported conclusions lean pessimistic because your scenarios and accounting are slower and harsher than the user's real setup. Keep your rigor. Remove the pessimism that is not evidence.

## What went wrong, with evidence

| Issue | Effect |
|---|---|
| `next_slot_tail` presented as a co-equal headline with `same_slot_one` | It fills after **every** trade in the next slot (about 400–800 ms). The user lands in 50–70 ms, 80–85% same slot. Most negative headlines come from this column: day study mature −0.21, combined router −0.64, velocity −0.86. |
| Exits checked once per slot, on the state after the slot's last trade | Adds detection delay the live bot does not have. Stops and take-profits react late. |
| Urgent sells land after the whole next slot; scheduled sells after 3 slots in the slow case | Far slower than the 50–70 ms sell assumption. Overstates cascade losses, which makes tight exits look worse than they are. |
| Migration / curve completion → unresolved at zero recovery; unresolved positions block ledger capacity | Graduation usually means the coin went up. Zero recovery plus blocked capacity treats winners as losses and removes later trades (combined study older account −2.629 SOL with two unresolved). |
| Tone: "not confirmed", "negative" and "fails" used for one-day or bracket-dependent results | The user reads this as "will lose money". Unconfirmed is not negative. |

Your fast scenario also has optimistic parts. Keep these honest too: `same_slot_one` allows at most one intervening curve group, while the matched audit found only 49/132 copies within the first two curve positions. Your base fee of 0.001505 SOL is below the measured historical entry average of 0.002916 SOL.

## Rules for you specifically

1. **Implement the central placement mixture** from contract section 3 and make it the headline. Move `next_slot_tail` to a stress section.
2. **Evaluate exit triggers after each transaction**, and land reactive sells using the same placement model as buys, anchored to the triggering transaction. Do not land them at the end of the next slot.
3. **Do not value graduated positions at zero.** Collect PumpSwap continuation where feasible. Otherwise report graduated-unresolved separately with a completion-state mark, alongside the zero-recovery bound.
4. **State what is positive as clearly as what is negative.** Lead with the central-scenario number and the verdict from contract section 8.
5. **"Unconfirmed" ≠ "negative".** A one-day positive central result is `positive-central, retrospective`, not a failure. The 2–3 week horizon determines confirmation, not sign.
6. **Do not add caveats that don't change the verdict.** Put routine limitations in one short limitations section. Keep the finding readable in the first three sentences.
7. **Before finishing, red-team your own result in the other direction**: name the three most likely ways it is *understated* and check each one.

## Self-check before you submit

- [ ] Central scenario implemented and used as the headline; `next_slot_tail` only in stress.
- [ ] Per-transaction exit triggers; reactive sells land at user-latency placement.
- [ ] Graduated and unresolved positions reported with a mark, not only zero.
- [ ] Fast-scenario optimism (≤1 group, low fees) also disclosed.
- [ ] Verdict uses contract section 8; first paragraph states it plainly.
- [ ] Contract section 9 result card filled.


## Mandatory migration accounting and reporting correction (2026-10-08 UTC)

User instruction: do not classify unresolved migration inventory as losing trades, or promote an account cash decrease caused by open holdings into evidence that a strategy is unprofitable.

1. **Lead with the decomposition.** Report settled PnL (all closed trades plus failed-attempt costs), open inventory's last-valid executable marked PnL, their combined marked estimate, and unresolved count. A zero-recovery number is a separately labeled downside bound, never the headline estimate or a realized loss. Cash drawn down by purchases is liquidity usage, not equity drawdown.
2. **Never use unknown inventory to train losses or trip loss breakers.** Unresolved trades do not enter closed-trade win rate, profit factor, loss streaks, rolling settled PnL, or deployer feedback labels. Actual failed fees and delivered realized legs remain accounted for under explicit rules.
3. **Identify each mark.** Record mint, retained amount, fees, time, venue and source/counterfactual custody status. A last-valid curve quote is not an authenticated AMM exit, nor a common end-date mark. Historical completion and changed-path completion are separate facts. Positive unsold marks are positive marked outcomes, not confirmed closed wins.
4. **Repair migration first.** Collect and bind full continuation, authenticate the actual PumpSwap/Raydium venue and custody, replay the whole opening transaction, and execute the declared exit with the same causal placement and fees. Do not force historical migration when the changed curve has not completed. Do not invent a zero value, sale, graduation multiplier or cash recovery to bridge a missing fill.
5. **Coverage must not silently suppress the experiment.** Disclose eligible signals, admitted attempts, capacity/cash skips and unresolved occupancy. Honor the user's current cap (the current cash-funded research comparison has no position cap). Never infer a live multi-day holding policy from an incomplete replay. Broader standalone/opportunity diagnostics are separate from shared funded profits.
6. **Verdict scope.** If unresolved exposure can change the conclusion, the full portfolio is undetermined. Negative settled outcomes can be reported as negative for that resolved subset. Do not generalize either result to all strategies or to all possible migration exits. Paper observation does not eliminate hypothetical own impact, fee or inclusion uncertainty and cannot guarantee truth within 24–48 hours.

Measured example: uncapped S3 relative-stop full portfolio, October3–6, Central85,60s/+20%,breakers on: settled -2.787669193 SOL,12open positions' marked PnL +1.059239785 SOL, combined last-valid marked -1.728429408 SOL. Open cashflow -6.042531360 SOL is committed capital/cost, not twelve realized losses; adding executable inventory value7.101771145 SOL gives the positive open marked PnL. Zero-recovery -8.830200553 SOL is only a bound. These marks are not proven AMM exits. This accounting correction does not by itself establish profitability or finish the missing migration simulation.

Regression requirement: a funded open position with positive executable marked PnL must have zero settled PnL until a real exit, positive open marked PnL, and no closed win/loss label. Assert settled plus open marked PnL equals the combined marked estimate.


## Exit-family fidelity and runner opportunity (October8UTC)

Before blaming entries for an unprofitable exit result, compare raw executable post-fill opportunities against the family's actual delivered exit. Report stop/timeout/TP-specific loser savings and surrendered winner upside; high MFE alone is not realized profit. Preserve each strategy's documented invalidations, tranche sizes, trail definitions and timers as controls; label user-approved changes separately. Do not describe S4halfTP as a full sell, a stop available after2slots as only within2slots, or generic four-family paths as identical five-family signals. Count unique mint/setup and scenario repetitions separately. Declare percent-relative versus percentage-point trailing and state the price/return basis. A best exit chosen retrospectively is development, not proof; replay with intervening transactions, partial own-impact, all fees, actual migration and funded admissions before promoting it. See core_gap_refinement_20261007/exit_claim_audit/REPORT.md.


## Grace attribution and deleted-dependency recovery (2026-10-08)

Do not assume early stopouts are noise, or that a profitable bracket proves edge. Verify exact control conditions, unique setup counts and whole-second timing limits. In the S1/S4grace6 rerun, S4saved .810532SOL on old losers but added1.183124SOL damage; S1improvedzero/worsenedthree. Shared Central85combined marked moved+.274068 to-.037392SOL, with12open positions; verdictundetermined,retrospective. Preserve the control and show both loser savings and extra downside. Report: [grace verification](core_gap_refinement_20261007/grace_verification_cycle/REPORT.md).

After deleted research source/data are recovered, require complete saved-control output parity before attributing new PnL to strategy changes. Pin original official artifacts by hash/version and verify whole receipt/reserve/custody parity. This recovery achieved3024exact control output comparisons and171138AMM source-group checks. A missing old funded file cannot be claimed bitwise-matched; state what was actually compared (saved headline/card and unchanged ledger source).

Undefined runners remain open inventory unless a declared causal deadline produces a delivered sale. A600s deadline sensitivity is a different policy, not permission to liquidate at the final observed tape price. Keep net hard-stop scope explicit when deferring only trough invalidation, and keep profit targets active during grace. Do not erase or revalue displaced-completion inventory to force profitability.
