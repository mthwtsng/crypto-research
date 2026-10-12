# Causal shadow-feedback experiment

**The positive-last-ten feedback gate remains negative-central, retrospective.** It reduces exposure and losses compared with the matching warmup control but does not repair expected value. Both recipes and all three policies are retained.

## Central funded results

| Recipe / admission policy | Central80 SOL | Central85 SOL | Attempts / closed / failed / unresolved |
|---|---:|---:|---|
| baseline / baseline | -4.6599 | -4.6493 | 224/168/56/0 |
| baseline / warmup10 | -4.1978 | -4.2228 | 190/141/49/0 |
| baseline / positive10 | -1.9080 | -1.9094 | 63/47/16/0 |
| confirmed_scratch3 / baseline | -1.9589 | -1.9661 | 201/145/56/0 |
| confirmed_scratch3 / warmup10 | -2.6085 | -2.5658 | 168/120/48/0 |
| confirmed_scratch3 / positive10 | -1.4168 | -1.4190 | 57/42/15/0 |

Table is the separate four-strategy diagnostic, breakers off, shared continuous15SOL/max2 account across all four dates. Individual strategy accounts are not summed. Full five, breakers on/off, placement brackets and cost stress are in the cards. Ungated full five remains blocked by two unsold migration paths; zero−0.9379SOL/mark+0.2655SOL. Gated full-five accounts have no carryover admissions because S5 never obtains ten resolved shadows; their equality to four-strategy accounts is not evidence of profitable migration carryover.

## Causal policy and control

Maintain the last ten resolved0.50SOL independently replayed shadow attempts for each strategy. The warmup control admits once ten outcomes are known. The positive gate additionally requires their all-cost net sum>0. Failures contribute their actual−0.000505SOL fee; unsent actual orders pay nothing. Unresolved shadows remain unknown, not zero or profitable. Shadow computation continues while actual admissions pause. Strategy/deployer gates were not added because this cohort is too sparse for a reliable ten-outcome history per deployer.

Only closes/failures strictly before each signal’s canonical position can enter feedback. Outcomes are not available at entry, and partial proceeds are not treated as resolved attempts. Three targeted regressions cover future closes, unresolved warmup, failed fees and recovery while paused. Production settings remain unchanged.

## What the result means

Recent strategy profitability is not enough to select profitable next trades in this sample. Original recipe gate loses1.9094SOL versus warmup4.2228SOL; confirmed3-second recipe gate loses1.4190SOL versus warmup2.5658SOL. Much of the difference comes from admitting only63/57trades instead of190/168, respectively. Even reduced exposure stays negative.

ATH is a counterexample: standalone ungated−0.1705SOL, warmup−0.2975SOL, positive gate−0.5183SOL. The gate drops opportunities that later recover and selects some losses after a previously good patch. Survival shelf improves its loss to−0.4598SOL but only seven attempts pass. Confirmed dead-man improves almost nothing after warmup:−0.2700SOL versus gated−0.2638SOL, while attempts fall from26to8. These small samples do not support treating feedback as an alpha signal.

## Scope and checks

Data are the existing1800fixed creation-selected launches across October3–6, not a full market census or14–21-day confirmation. Combining their traces creates one chronological account, not a sum of reset balances.5832input trace repetitions and504alternative funded ledgers; no new entry/exit fill recipes. Sampling may omit real strategy opportunities and change the live feedback history. Shadow own-impact trajectories are modeled, not observable live wallet PnL.

486decision-prefix checks pass;504funded ledgers regenerate identically. Historical whole-transaction/source-custody proofs, integer causal requotes and eight alarm checks are retained; new decision-history checks prohibit future outcomes. Fast all-closed cases are explained by K=0 entry placement; delayed cases have failed guards.

## Next falsification test

Investigate entry information describing failed recovery versus sustained new demand: sequential outside recovery transactions and residual sellable inventory, rather than optimizing the rolling window until it happens to win. Earlier3-second invalidation is a loss-reduction candidate, not a profitable strategy. Completion/migration execution remains independently incomplete.

## What I would investigate if data and tooling were unconstrained

Complete live shadow-intent stream for feedback calibration; archival funding/cohort inventory to distinguish coordinated sell supply; full failed-router simulation with original account/compute limits.

## Required result card

## confirmed_scratch3, positive10, portfolio, breakers False

```text
engine + revision: repaired approved day_general extensions; git35d8981; working code/data hashes CHECKS.json
data: October3–6UTC,2026;1800creation-selected launches,600earlier+1200later; sampled opportunity stream, not complete live activity
frozen before data: no; retrospective development after inspecting these periods
looks:26prior logged development looks +2feedback policies; baseline and confirmed3s recipes fixed, no gate threshold tuning
candidate: confirmed_scratch3/positive10/portfolio;breakersFalse;15SOL/0.50SOL/max2;0.25SOL cooldown probes
fast/central80/central85/slow zeroSOL: -0.717108 / -1.416811 / -1.419002 / -0.817431
markedSOL same order: -0.717108 / -1.416811 / -1.419002 / -0.817431
stress tail -0.505616; historical0.002916legfee -1.523935;scheduled n/a(all urgent)
central85 attempts/closed/failed/unresolved:57/42/15/0;zero-1.419002;marked-1.419002;closed-only-1.411427
settled drawdown1.611847;cash drawdown2.115391;largestwinner0.171696;netwithoutlargest-1.590698
opportunities230;gate rejection{"warmup": 60, "nonpositive_shadow": 113};funding skips{};daily{"2026-10-03": -0.194738467, "2026-10-04": -0.103657616, "2026-10-05": -1.158927131, "2026-10-06": 0.038321476}
PF0.34926648489172474;WR0.23809523809523808;eightalarms reviewed;causalprefix/ledger checks CHECKS.json
verdict:negative-central,retrospective
changesverdict:entry information beyond recent strategy PnL, complete opportunity stream and frozen14–21-day evaluation; authenticate migration execution before S5 claims
```

