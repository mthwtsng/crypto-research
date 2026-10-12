# Starting Five: repaired-engine pilot backtest

October 7, 2026. Research only; production code, keys and live settings unchanged.

**The complete five-strategy portfolio remains undetermined.** Central85 admits eight attempts, closes four, rejects two and retains two unresolved carryover positions. Its zero-recovery net is −0.9379 SOL and its last-valid executable marked net is +0.2655 SOL. The difference is unsold inventory, not realized profit. Those two unresolved positions fill the concurrency cap; a positive marked balance cannot establish portfolio profitability.

**The control excluding carryover is negative-central, retrospective:** with breakers, Central85 loses 0.6352–0.6606 SOL across the two exit endpoints. Central80 loses 0.6736–0.6990 SOL. Breakers reduce losses slightly but do not make central placement positive.

The survival shelf is the promising exception: standalone Central85 +0.6397 SOL across 12 attempts (11 closed, one failed), +0.3369 SOL without its largest winner. That sample is too small to establish repeatable expected value.

## Actual test scope

- 600 creation-selected October 3–4 launches: 426 on October 3, 174 on October 4. This is not two full census days or the previously quoted 21-day sample.
- 76 causal signals on 58 mints: dev absorption 11; survival shelf 12; dead-man 19; upper ATH 27; carryover 7. All eligible mints retained before reviewing outcomes.
- Two prescribed exit endpoints; fast, central80, central85, slow and next-slot-tail stress; central85 historical-fee sensitivity. 1,824 individual traces include both 0.50 SOL base and 0.25 SOL post-cooldown probes. These are repeated scenarios on 76 signals, not 1,824 independent trades.
- Shared 15 SOL ledger, max two pending/open positions, same-mint overlaps skipped, cash credited at delivered partial sell legs, rent refunded only on complete close. Strategy-specific cooldowns and global brake use the latest user matrix. Failed fees enter rolling net; loss streaks count completed losing positions.
- Original quote budgets, limits, integer fees and custody are repriced. 97% signal-output protection applies to buys. All exits in this pilot use urgent delivery/fees; no zero-tip instant fills.

## Central funded results

| Scope / endpoints | Breakers | Central80 SOL | Central85 SOL | Central85 attempts / closed / failed / unresolved |
|---|---|---:|---:|---|
| portfolio / lower | off | -0.9424 | -0.9379 | 8 / 4 / 2 / 2 |
| portfolio / lower | on | -0.9424 | -0.9379 | 8 / 4 / 2 / 2 |
| portfolio / upper | off | -0.9489 | -0.9445 | 8 / 4 / 2 / 2 |
| portfolio / upper | on | -0.9489 | -0.9445 | 8 / 4 / 2 / 2 |
| portfolio_without_carryover / lower | off | -0.7214 | -0.6829 | 62 / 47 / 15 / 0 |
| portfolio_without_carryover / lower | on | -0.6736 | -0.6352 | 55 / 41 / 14 / 0 |
| portfolio_without_carryover / upper | off | -0.7468 | -0.7083 | 62 / 47 / 15 / 0 |
| portfolio_without_carryover / upper | on | -0.6990 | -0.6606 | 55 / 41 / 14 / 0 |

The full portfolio rows are zero-recovery bounds. Their corresponding last-valid marks are +0.2655 / +0.2589 SOL under Central85 and +0.2610 / +0.2545 SOL under Central80. The carryover-excluded control was added after observing blocked migration custody to isolate the other rules; it is a diagnostic scope, not a proposed production removal.

## Individual strategies

These are separate funded accounts, **not numbers to add into the shared portfolio**. Breakers off exposes the rule itself; on/off details are in FUNDED_RESULTS.json.

| Strategy | Central85 lower SOL | Central85 upper SOL | Lower attempts / closed / failed / unresolved | Finding |
|---|---:|---:|---|---|
| Dev absorption | -0.3258 | -0.3671 | 11 / 9 / 2 / 0 | Negative pilot; 9 closes, thin sample |
| Survival shelf | +0.6397 | +0.6397 | 12 / 11 / 1 / 0 | Positive pilot; 11 closes, thin sample |
| Dead-man dislocation | -0.9213 | -0.9213 | 19 / 15 / 4 / 0 | Negative pilot; scratches outweigh runners |
| Upper ATH | -0.1175 | -0.1533 | 27 / 16 / 11 / 0 | Negative central, positive fast; execution-sensitive |
| Carryover | -1.0076 | -1.0076 | 3 / 0 / 1 / 2 | Completion execution unresolved; two funded positions remain open |

Carryover standalone marked net is +0.1958 SOL, versus −1.0076 SOL zero-recovery. At the unfunded signal-replay level all seven are represented: one closed, one failed and five unresolved. Funded admissions stop after the first two unresolved fills occupy both slots.

## What is still unresolved under the hood

The source-path repairs pass: all 60 locally present bound curve tapes reconcile across 37,480 whole groups (58 mints belong to this test); earlier account-level source parity passed 41,344 curve groups and 202,868 AMM groups. Five ledger regressions and six replay-repair regressions pass; all 1,824 traces finish without Python exceptions.

Those checks establish historical reconstruction, not complete counterfactual execution. Our buy reduces remaining curve supply; an original exact-token completion order can then exceed the remaining tokens and fail. This is consistent with the [official buy instruction limits](https://github.com/pump-fun/pump-public-docs/blob/main/docs/instructions/BUY.md). When recorded completion is displaced, the historical AMM opening cannot simply be reused. Later landed-failed routed transactions may restore completion, but a compatible quote does not authenticate their full execution, funding, account transfers or compute limits.

This replay preserves original successful counterparty intents and their guards. Landed-failed router receipts are not promoted to fills. Consequently, carryover outcomes are explicitly incomplete. The first two shared-account positions retain their tokens, funded cash commitment and last-valid curve liquidation marks. They are not sold at graduation, forced closed at file end or assumed to earn a fictitious migration windfall. Marks come from each path’s last valid state, not a common end-of-window liquidation.

## Loss diagnosis and next refinements to test

1. **Dead-man is the first target.** Under Central85 lower, nine 10-second scratch exits lose −1.5938 SOL while six trailing runners earn +0.6745 SOL. The worst scratch loses 0.2933 SOL on a 0.50 SOL ticket. Waiting ten seconds is not a small-loss guarantee. Test a causal recovery-confirmation entry and an earlier failed-recovery exit as separate hypotheses; compare saved losers against surrendered runners. Neither refinement has been tested here.
2. **Keep the survival shelf as a research candidate.** Five runner exits total +0.9761 SOL; five shelf failures total −0.3325 SOL; one breakeven ratchet fills −0.0035 SOL. Its largest winner is +0.3028 SOL. Profit remains +0.3369 SOL without it including the failed fee. Freeze this version before collecting fresh data rather than retuning the 10.8 threshold on these 12 attempts.
3. **Dev absorption needs selection evidence before more exit tuning.** Four floor invalidations cost −0.2870 SOL; five timer closes total −0.0377 SOL. Longer endpoint holding makes this pilot worse. An emptied creator address does not prove associated supply is exhausted; funding/associated-wallet evidence remains unknown.
4. **Upper ATH is placement-sensitive.** Lower endpoint standalone is +0.6896 SOL fast, −0.1175 central85 and −0.3800 slow. Eleven central entries fail the token-output guard. Research whether broad fresh demand survives after the initiating large buy; do not assume a faster sender alone fixes the central result.
5. **Finish carryover execution coverage before optimizing its exits.** Reexecute/authenticate whole failed routed orders and changed completion/migration timing. Otherwise choosing a better AMM exit on these missing paths risks optimizing a fabricated opening.

The breaker matrix reduces the four-strategy Central85 lower loss from −0.6829 to −0.6352 SOL and settled drawdown from 1.1981 to 0.9291 SOL. Three dead-man cooldown/probe events occur. The 2 SOL global brake is not reached in this pilot. No evidence here justifies changing its thresholds. A rolling realized-net brake does not guarantee 13 SOL stays permanently safe: open losses, fill overshoot, repeated windows and expiring earlier profits remain possible.

## Placement, fees and alarm review

| Four-strategy control, breakers on | Fast | Central80 | Central85 | Slow | Tail stress | Central85 historical fees |
|---|---:|---:|---:|---:|---:|---:|
| lower | +0.3144 | -0.6736 | -0.6352 | -0.5618 | -0.3936 | -0.7954 |
| upper | +0.5133 | -0.6990 | -0.6606 | -0.6364 | -0.4868 | -0.8207 |

Slower placement can outperform faster placement without implying a timing bug. The matched-intent audit records why: on 4LuGz5Hm the fast entry gets 7.54 trillion raw tokens and loses 0.2933 SOL; after the next-slot sell flow, slow gets 17.33 trillion and loses 0.0168 SOL. Both buys pass the one-sided min-output guard. On 3RS5vNdM, a later partial sale changes the counterfactual path and trailing exit (slot 452964712 versus 452964510). Guard selection and breaker admissions also differ. CHECKS.json retains every paired entry and exit position; PnL monotonicity is not artificially imposed.

All eight contract alarms are checked. Fast K=0 has all attempts closed on the four-rule control because it inserts immediately after the signal; delayed scenarios have failed guards. There are no pre-deadline timer fills, completed-curve sells, exact full-profit threshold fills, high-PF/high-win-rate cases above 50 closes, missing creation histories or replay exceptions. Fast is an optimistic bracket, not an observed sub-30ms execution requirement.

Unspecified rules remain explicit: S2 runners and S3 runners have no final maximum hold in the plan; the 600-second observation cap censors rather than sells. S3 active history means at least two outside buyers; “outside” excludes the creator address, not unknown associated addresses. S3 runner trail uses an eight-percentage-point giveback after +20%; S5 unspecified trail uses an 8% relative buffer with 30/60-second AMM timeout endpoints. These interpretations need live implementation agreement before deployment. Base buyer-history clips are at least 0.05 SOL. Dev trough resets at a preceding peak, corrected before replay results were read.

Three pessimism checks: graduation is not written off (marks retained); reactive sells use same central placement mixture as buys rather than slot-tail placement; timers use real produced blocks independently of trades. Three optimism checks: failed router quote passes are not fills; migration opening deposits are authenticated; successful network fees also receive the measured higher-fee sensitivity.

## Artifacts and reproduction

- SPEC_FREEZE.json, SIGNAL_AUDIT.json, SIGNALS.json: definitions, provenance and complete eligible census.
- REPLAY_RESULTS.json.gz, REPLAY_ERRORS.json: all 1,824 traces and exception check.
- FUNDED_RESULTS.json: 168 separate account scenarios with admission skips, delivered cash legs, cooldowns, marks and daily results.
- CURVE_REPLAY_PARITY.json, CHECKS.json, test_ledger.py: source parity, placement decomposition and alarm checks.
- CANDIDATE_RESULT_CARDS.md: each family’s result card.

Reproduce with `python3 signals.py`, `python3 intake.py`, `python3 engine.py`, `python3 ledger.py`, `python3 checks.py`, `python3 report.py` from this directory. RPC receipts are cached. Intake includes all eligible mints; no additional outcome filtering.

## Required portfolio result card

```text
engine + revision: repaired approved day_general extensions; git 35d8981; file hashes in CHECKS.json
data: Oct 3–4, 2026; 600 creation-selected launches, 58 eligible mints; creation/custody checks pass
frozen before data: no; retrospective plan test; not exit-optimized on these results
looks: two endpoint recipes; breaker on/off; 6 placement/cost cases; carryover-excluded scope is a post-result diagnostic
candidate: portfolio; endpoint lower; breakers True; 15 SOL / 0.50 SOL / max 2; probes 0.25 SOL
fast / central80 / central85 / slow zero-recovery funded SOL: -1.0009 / -0.9424 / -0.9379 / -1.0628
marked funded SOL, same order: +0.2121 / +0.2610 / +0.2655 / +0.1406
stress tail: -1.0628; historical fee: -0.9535; scheduled sells: n/a (all exits urgent)
central85 attempts / closed / failed / unresolved: 8 / 4 / 2 / 2; zero -0.9379; marked +0.2655
settled-only drawdown 0.0465; largest winner 0.0904; zero net without largest -1.0284
bug alarms: all 8 checked; speed reversals and fast all-closed cases explained in CHECKS.json
verdict: undetermined, retrospective
what changes verdict: resolve changed completion/router execution; then frozen fresh 14–21-day funded replay
```

Carryover-excluded diagnostic card:

```text
engine + revision: repaired approved day_general extensions; git 35d8981; file hashes in CHECKS.json
data: Oct 3–4, 2026; 600 creation-selected launches, 58 eligible mints; creation/custody checks pass
frozen before data: no; retrospective plan test; not exit-optimized on these results
looks: two endpoint recipes; breaker on/off; 6 placement/cost cases; carryover-excluded scope is a post-result diagnostic
candidate: portfolio_without_carryover; endpoint lower; breakers True; 15 SOL / 0.50 SOL / max 2; probes 0.25 SOL
fast / central80 / central85 / slow zero-recovery funded SOL: +0.3144 / -0.6736 / -0.6352 / -0.5618
marked funded SOL, same order: +0.3144 / -0.6736 / -0.6352 / -0.5618
stress tail: -0.3936; historical fee: -0.7954; scheduled sells: n/a (all exits urgent)
central85 attempts / closed / failed / unresolved: 55 / 41 / 14 / 0; zero -0.6352; marked -0.6352
settled-only drawdown 0.9291; largest winner 0.3028; zero net without largest -0.9380
bug alarms: all 8 checked; speed reversals and fast all-closed cases explained in CHECKS.json
verdict: negative-central, retrospective
what changes verdict: resolve changed completion/router execution; then frozen fresh 14–21-day funded replay
```
