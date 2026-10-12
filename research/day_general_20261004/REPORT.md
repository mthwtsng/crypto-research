# Fixed-rule 24-hour general-launch transfer test

Window: **2026-10-03T06:59:02+00:00 to 2026-10-04T06:59:02+00:00**, October 2 23:59 to October 3 23:59 Vancouver. Retrospective wider-window transfer, not a completely later untouched day. The previous 400 source mints are excluded.

Complete census: 54,029 creations; 33,499 ordinary candidates after prior-source exclusion. Fixed 25 hash-selected launches per hourly stratum: 600 sampled; 600 prepared; 57 coins trigger the unchanged causally activity-screened recipes. No stopping at a favorable PnL or 40 coins, no future-volume/nonmigration/survival selection.

Sampling covers all 24 hourly strata, not every launch in the day. Sample profits and capital contention must not be scaled to the full creation population. Each tape covers the first 15 minutes plus 60 seconds reserved solely for exits. Late-life entries on older coins are outside scope. Natural-volume screening is the same decision-time proxy as the previous study, not a certification of independent ownership or genuine coins.

## Finding

Mature breakout is positive only under the fast modeled placement in this wider day: timer +0.643970 SOL, staged +0.982364 SOL. Next-slot tail is negative: timer −0.209545, staged −0.441603. Under fast placement the staged exit saves 1.110202 SOL on timer losers while surrendering 0.771809 SOL on winners, increasing net by 0.338394 SOL; this reverses the earlier two-hour exit comparison. With 5 SOL, mature timer maximum settled drawdown is 2.085275 SOL, staged 1.165703 SOL. Full timer has 16 wins and 17 losses. Across 18 signal-active hourly strata, timer has nine positive/nine negative hours; staged ten positive/eight negative. That is a possible speed-sensitive candidate, not a robust all-placement/live edge.

Higher historical-entry-mean buy/urgent fees preserve fast mature profit: timer +0.597420 SOL, staged +0.928761 SOL; next-slot outcomes remain negative. The synthetic same-slot-one scenario is not implied by an 80–90% same-slot rate: the number and sizes of intervening curve transactions and actual sell placement still need measurement.

The first-entry-only dip benchmark is negative (−0.159785 / −0.038823 SOL). Velocity and liquidity are also negative with timer exits. The combined first-entry router has timer −0.107371 / −0.644123 SOL; staged +0.153344 / −0.443679. This is one predeclared policy; no standalone profit summation or newly optimized router is claimed.

## Frozen first-entry-per-rule/mint funded benchmark

First attempted entry per rule/mint is frozen before this day replay. It avoids treating independent recurrent-dip replays as a continuous multiple-intervention simulation. Each arm has its own 5 SOL / two-position bankroll; profits cannot be added.

| Rule | Placement | Attempts / closes | Known intent net SOL | Funded net SOL | Settled drawdown SOL | Unknown intents |
|---|---|---:|---:|---:|---:|---:|
| dislocation | next_slot_tail | 21 / 13 | -0.038823 | -0.038823 | 0.238567 | 0 |
| dislocation | same_slot_one | 21 / 18 | -0.159785 | -0.159785 | 0.761359 | 0 |
| liquidity | next_slot_tail | 56 / 47 | -0.445477 | -0.445477 | 0.813314 | 0 |
| liquidity | same_slot_one | 56 / 52 | -1.229810 | -1.229810 | 1.644265 | 0 |
| mature_fresh | next_slot_tail | 35 / 26 | -0.209545 | -0.209545 | 1.942181 | 0 |
| mature_fresh | same_slot_one | 35 / 33 | +0.643970 | +0.643970 | 2.085275 | 0 |
| velocity | next_slot_tail | 52 / 40 | -0.856609 | -0.856609 | 1.116713 | 0 |
| velocity | same_slot_one | 52 / 47 | -0.097115 | -0.097115 | 0.601440 | 0 |

The ledger skips incomplete intents and explicitly records their count. If unknown intents exist, funded numbers are conditional known-outcome accounting, not a complete portfolio proof. Zero-recovery unresolved positions are distinguished from entirely unmodeled missing histories. See status counts in FIRST_ENTRY_LEDGER.json. Capital/position/duplicate skips are also retained.

## Fixed combined first-entry routing

| Placement | Exit | Funded net SOL | Unknown |
|---|---|---:|---:|
| same_slot_one | full_timer | -0.107371 | 0 |
| same_slot_one | staged_ladder | +0.153344 | 0 |
| next_slot_tail | full_timer | -0.644123 | 0 |
| next_slot_tail | staged_ladder | -0.443679 | 0 |

Router: first eligible dislocation/velocity/mature signal per mint, tie priority dislocation > velocity > mature. This is one fixed routing policy, not proof of current production parity.

## Runner contribution and exit tradeoff

- Mature next_slot_tail: 42.3% closed win rate, largest winner 0.810822 SOL; mean win 0.32420476572727275, mean loss -0.25141679906666664. Largest-winner dependence is diagnostic, not automatic rejection of a runner strategy.
- Mature same_slot_one: 48.5% closed win rate, largest winner 0.694571 SOL; mean win 0.288624724125, mean loss -0.23370678923529412. Largest-winner dependence is diagnostic, not automatic rejection of a runner strategy.
- Mature same_slot_one, matched staged exits: saves +1.110202 SOL on timer losers; surrenders +0.771809 SOL on timer winners; total staged change +0.338394 SOL. Winner/loser labels are evaluation-only, never causal routing inputs.
- Mature next_slot_tail, matched staged exits: saves +0.654708 SOL on timer losers; surrenders +0.886767 SOL on timer winners; total staged change -0.232059 SOL. Winner/loser labels are evaluation-only, never causal routing inputs.

HOURLY_RESULTS.json contains all 24 strata, including no-signal hours. These hourly subdivisions are correlated and do not replace multiple independent days. One day cannot satisfy the guide’s two-to-three-week confirmation horizon.

## Execution and data limits

Exact integer quotes, recorded protocol fee pairs, finite own impact, sequential counterparty repricing/custody, 97% token-output entry guard, quiet-period block-second timers, and modeled network costs are inherited unchanged. Buy and urgent exit cost 0.001505 SOL; failed guarded entries 0.000505 SOL; rent 0.003 reserved/refunded on closure. Mature scheduled exits are 0.000010 SOL / one slot same-slot, 0.000505 SOL / three slots next-slot; short timer and reactive exits urgent / one slot. The historical-entry-mean sensitivity uses 0.002915606 SOL for buy/urgent exits. Actual current sender/exit costs are not newly measured. Same-slot-one and next-slot-tail are synthetic placement sensitivities, not a calibrated 50–75ms distribution. Historical participant reactions to changed prices/limits remain unobserved.

Source custody repairs are applied to every affected sampled tape without PnL selection, up to 30 passes per affected mint; unresolved gaps are retained. Source collection exceptions are listed in PREPARE_AUDIT.json, not converted to no-signal launches. Historical source state and finalized order checks are in AUTHENTICATION.json. All arm outcomes and accounting failures are reported, including unsupported terminal/migration boundaries. Current Rust strategy parity, adaptive deployer memory, and organic ownership are not established.

## Verification

600 histories collected with zero collection failures; 708 primary and 1,062 sensitivity rows, no replay exceptions or missing/unresolved modeled intents. Ten regression checks pass and all funded ledgers reconcile. 47,170 historical state transitions checked; the single unsupported terminal capped-buy transition is at curve completion after every modeled trade on that mint has settled (FINAL_CHECKS.json). Thirty finalized block-order checks have zero missing/reversed signatures or provider errors. Custody repair resolved 40 of 61 source gaps fully; 21 partial gaps remain outside the actual modeled trade paths, not silently excluded by profit. These coverage facts do not establish how participants react to our hypothetical intervention.

## Reproduction and looks

All four rules x two placements x two exits are reported (16 primary cells); 24 declared cost/accounting sensitivity cells; 16 first-entry diagnostics; four fixed combined router cells. These are correlated views of one sampled day, not independent confirmations. No thresholds/tickets/holds optimized. See LOOK_LOG.md and CODE_FREEZE.json.

```bash
python3 research/day_general_20261004/collect.py
python3 research/day_general_20261004/repair_source.py
python3 research/day_general_20261004/evaluate.py
python3 research/day_general_20261004/sensitivity.py
python3 research/day_general_20261004/first_entries.py
python3 research/day_general_20261004/exit_tradeoffs.py
python3 research/day_general_20261004/authenticate.py
python3 research/day_general_20261004/checks.py
python3 research/day_general_20261004/day_report.py
```

## What I would investigate if data and tooling were unconstrained

Prospectively collect two-to-three weeks of the unchanged rules with actual source-receipt, submit, landing and exit telemetry; test realistic participant limit/reaction changes; resolve full funding/ownership graph and migration custody; build continuous repeat-entry counterfactuals and exact production-router parity. These require new data rather than inferred certainty.
