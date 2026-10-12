# Starting Five: repaired-engine backtest and later-window refinement

The four-strategy diagnostic is **negative-central, retrospective** on October 5–6. The original lower-endpoint plan with breakers loses 3.5077 SOL; the primary combined refinement loses 2.1241 SOL. Changes improve this sample but do not establish a profitable setup.

The complete five-strategy portfolio is **undetermined, retrospective**: the baseline Central85 account admits 40 attempts, with two unresolved carryover positions. Zero-recovery net is -2.3368 SOL; last-valid executable marked net is -1.2078 SOL. Unsold marks are not realized cash or common end-of-window marks. Every carryover signal remains in the primary study; the four-strategy table is a separate diagnostic.

## Funded central results

15 SOL shared account, 0.50 SOL tickets, maximum two pending/open positions, latest user circuit breakers enabled, 0.25 SOL cooldown probes. Base successful network fee/tip 0.001505 SOL, failed 0.000505 SOL, refundable rent 0.002039280 SOL; protocol fees and integer impact included. Entries enforce 97% signal-time quote. All exits urgent, with the same modeled central delivery distribution; timestamps are integer-second historical estimates, not measured 50–70 ms fills.

| Recipe / endpoint | Central80 SOL | Central85 SOL | Attempts / closed / failed / unresolved |
|---|---:|---:|---|
| baseline / lower | -3.4460 | -3.5077 | 103 / 75 / 28 / 0 |
| baseline / upper | -3.6673 | -3.7262 | 102 / 75 / 27 / 0 |
| ath_only / lower | -2.4235 | -2.4242 | 99 / 76 / 23 / 0 |
| joint_keep_targets_dead10 / lower | -2.1926 | -2.1241 | 102 / 71 / 31 / 0 |
| joint_confirmed_half10 / lower | -2.2244 | -2.1596 | 102 / 71 / 31 / 0 |

All table rows exclude S5 only to isolate known exits. They cannot be described as the full portfolio. Full five and all individual scenarios, both endpoint recipes, on/off breakers, brackets, tail stress and higher fees are in CANDIDATE_RESULT_CARDS.md.

## Scope and selection

Development: 600 creation-selected October 3–4 launches; original two endpoints plus 18 new mechanism/combination looks. Primary joint refinement on those inspected days produced +1.1145 SOL and the additional half-at-10% recipe +1.8054 SOL, both excluding carryover with breakers off. These development gains did not transfer.

Later sample: 1,200 normal-SOL creations selected by fixed hash, 25 per hour across all 48 hours October 5–6. Entry search is frozen to creation + 1,800 seconds; longer continuation history is used for custody and exits, not new late signals. 180 causal signals on 130 eligible mints. WINDOW_CORRECTION.json documents removal of one signal erroneously searched beyond that decision window, irrespective of its outcome. Lower replay 13,120 traces; upper replay 2,160 traces. These are repeated execution scenarios, not independent trades. Lower 560 funded accounts, upper 84; each is an alternative shared chronological ledger.

## Entry versus exit gap

| Strategy | Original Central85 SOL | Primary refined SOL |
|---|---:|---:|
| s1_dev_absorption | -0.0273 | -0.2618 |
| s2_survival_shelf | -1.7832 | -1.7832 |
| s3_deadman | -2.5930 | -0.8446 |
| s4_upper_ath | -0.0530 | +0.0840 |
| s5_carryover | -1.0071 | -1.0071 |

These standalone accounts must not be added together. Original S3 retains one undefined-runner-timeout exposure; S5 retains two displaced-completion positions. Their table values are zero-recovery bounds; executable marks are in the cards.

* **Dev absorption:** the added recent-breadth filter improves the development sample but worsens later standalone results from −0.0273 to −0.2618 SOL. It is not a usable quality gate yet; multiple addresses alone do not authenticate independent demand or exhausted associated supply.
* **Survival shelf:** development +0.6397 SOL becomes −1.7832 SOL later. Exit-free neutral paths reach executable +5% within 60 seconds on 13/32 later fills versus 8/11 development fills. The gap includes entry/regime quality; a timer adjustment alone cannot be assumed to fix it.
* **Dead-man:** causal recovery confirmation reduces failed-bounce exposure. Later 18 confirmed fills include 10 that reach executable +5% within 10 seconds, but only 7 reach +10%. The unchanged exit still loses 0.8446 SOL; half-at-10% loses 0.8801 SOL. A majority briefly rising does not outweigh the failed recoveries. Next bounded test: smaller full targets/earlier invalidation on the same confirmed entries, counting surrendered winners and total losses.
* **Upper ATH:** 20-second clip timeout and 15% reactive loss trigger improve standalone later net from −0.0530 to +0.0840 SOL. At 20 seconds only 18/41 neutral fills reach executable +5%; at 60 seconds 25/41 do, but terminal median return is strongly negative. This is a small positive sub-result, not portfolio confirmation. Test causal fresh-demand breadth and entry timing before expanding stops further.
* **Carryover:** token custody is preserved through authenticated migration when the changed path actually completes. Original exact-token completion orders can fail after our additional buy reduces remaining supply. It is invalid to force the historical AMM opening onto that incomplete path. Recovered landed-failed receipts are not pending orders and a compatible quote does not establish whole-router execution. Resolve this execution gap before selecting S5 exit winners.

Three Central85 placement seeds all lose on the later four-strategy diagnostic: original −3.9663/−4.1425/−4.6356SOL; primary joint −2.8723/−3.4533/−2.9660SOL (breakers off). The conclusion is not one unlucky placement seed. Breakers reduce realized losses but do not guarantee 13 SOL permanently safe; open exposure and overshoot remain possible.

## Repairs and verification

Repaired zero-initialized counterfactual token accounts after reverted source buys, included buys inside AMM opening transactions, preserved atomic opening failures, extended source histories through late completion and recovered a missing same-owner token-account transfer. Historical parity passes 61,020 whole token-account groups on 130 eligible mints, 65,418 curve groups on 164 bound tapes, 29,185 post-opening AMM groups and ten pool openings/custody audits. 15 focused regressions pass (7 replay, 5 ledger, 3 opening).

The saved funded ledgers were regenerated identically. CHECKS.json audits all eight contract alarms plus token conservation, causal order, timer deadlines and exceptions. Speed differences are decomposed by matching intents and their actual entry/exit positions; favorable slower quotes and different guard/cooldown admissions are not silently forced into monotonic PnL. No production settings were changed by this research.

Pessimism checks: retain executable marks and custody, use per-transaction urgent central delivery rather than slot-tail delay, fire timers independently of trades. Optimism checks: no revived router quote-only fills, authenticate opening deposits plus first swaps, and test higher measured fees. Source reconstruction parity establishes historical fidelity, not knowledge of counterfactual future orders or migration timing.

## Reproduction and next experiment

Run upper_endpoint.py for the second frozen endpoint; transfer.py for lower baseline and transfer refinements; variants.py then variants.py --ledger for development. fresh_collect.py/fresh_pipeline.py/account_repair.py retain collection and repair provenance. finish_report.py regenerates funded comparisons, checks and cards from saved traces. Repair continuations must not extend the frozen entry-search window.

Next entry-first test: recent independent demand proxies (three distinct ≥0.05 SOL buyers, wallet dominance ≤50%, sell/buy ≤50% in trailing 4 slots), evaluated causally at the first qualifying signal. Test first-time buyer expansion separately. These hypotheses are not measured improvements yet; October 3–6 now counts as inspected development. Confirmation requires frozen rules on later 14–21-day data and complete carryover execution.

## What I would investigate if data and tooling were unconstrained

Whole failed-router execution with archival account states and compute/guard evidence; sender intent-to-fill logs to calibrate buys and sells separately; contemporaneous wallet funding/cohort graphs to distinguish independent demand from associated inventory. None is an enabled signal.

## Required result card

```text
engine + revision: repaired approved day_general extensions; 35d8981; exact working-file hashes CHECKS.json
data: October 5–6 UTC, 2026; 1,200 fixed-hash creation-selected coins (25/hour, 48 complete hourly strata); 130 eligible mints; histories from creation
rules frozen before data: original plan predates later results; joint recipes frozen before inspecting later replay; all historical, not a future live confirmation
look count: two original endpoint recipes + 18 new mechanisms/combinations; placement, fee and seed repetitions are sensitivities
candidate: baseline; endpoint lower; scope portfolio; breakers True; bankroll15SOL/ticket0.50SOL/max2; cooldown probes0.25SOL
fast / central80 / central85 / slow funded zero SOL: -2.538781 / -2.340473 / -2.336759 / -2.358948
marked SOL in same order: -1.408442 / -1.187968 / -1.207832 / -1.208451
stress tail -2.307432; 0.002916SOL successful-leg fee -2.420749; scheduled sensitivity n/a, every exit urgent
central85 attempts/closed/failed/unresolved: 40/30/8/2; zero -2.336759; marked -1.207832; closed-only -1.325631
settled-only drawdown 1.439539; cash drawdown 2.446627; largest winner 0.197661; zero net without largest -2.534420
daily settled net: {"2026-10-05": -1.329670653}; skipped {"concurrency": 132, "strategy_pause": 8}
bug alarms: all eight checked; matched-intent speed differences and fast all-closed cases documented CHECKS.json; ledger regenerated identically
verdict: undetermined, retrospective
what changes verdict: resolve changed completion/exact routed execution; causal entry-quality test followed by frozen 14–21-day later data
```
