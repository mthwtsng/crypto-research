# Edge Discovery & Research Guide

Living reference for discovering, testing, rejecting and validating Solana deployer-, buyer-, launch-, execution- and market-structure edges in this repository. Updated: 2026-10-04.

This file expands the search space. It does not define it. Every factor, mechanism, example and number below is non-exhaustive and is not a recommended default. Research here does not authorize live trading, custody changes or production enablement.

---

## 0. Mission

Find repeatable, causal, executable sources of expected value that survive realistic timing, fills, fees, tips, failed transactions, finite liquidity, capital limits, regime change, later unseen data and competition from other bots.

A valuable result may be a new entry or exit mechanism, an abstention rule, a better wallet/deployer selection method, a prediction of failure, a secondary-entry strategy instead of a genesis race, an execution advantage, a graph or regime signal, or evidence that the current strategy family is structurally weak. "No edge found" is a valid result.

**Be rigid about evidence, flexible about hypotheses.** Causality, chronology, execution realism, accounting, reproducibility and validation are fixed (Part 2). Variables, entities, horizons, mechanisms and strategy shapes are open. Existing rules are baselines and history, not boundaries. Finding a useful missing factor is worth more than testing another neighboring threshold.

---

## 1. Operating protocol

### 1.1 Before any exploration

1. **Read prior work.** Read the reports in Part 10. Establish what was actually tried, what failed and where. Older narrative claims can conflict with audited code; check the latest applicable reports and code. Existing Python tests do not prove Rust strategy parity.
2. **Inventory data.** List what the pipeline can actually observe, and mark every hypothesis you consider as one of:
   - **feasible now**
   - **needs new data** (name it, say when it becomes causally available)
   - **not possible**

   Never fabricate or assume access to funding graphs, transaction fingerprints, leader/slot data, SOL volatility, off-chain feeds or similar if the pipeline lacks them.
3. **Seal a holdout.** Before any exploration, fix a final holdout window and do not look at it until a candidate is frozen. Retrospective replay of previously inspected history is still retrospective, however chronologically it is run.
4. **Keep a look log.** Record every hypothesis, feature set, label, split and configuration tried, including failures and neighbors. Many correlated simulations are not independent observations. Report the count of looks next to any "winner".
5. **Check sample size.** Per-deployer samples are often small. State a rough minimum sample before using clustering, graph or ML methods, and say when a result is too thin to support them.

### 1.2 Read raw data first

Before writing any feature, read 30-50 actual launches as full trajectories: the biggest winners, the biggest losers, and the surprising ones (see Part 4). Write down what you notice in plain language. Unseen edges usually show up here, not in a feature list. Only then define features.

### 1.3 Default loop

**User-directed entry-first workflow (October 4, 2026):** When discovering a new strategy or refining its entry signal, first test whether the coin rises after the signal and a realistically modeled entry. Do not attach an inherited timer, take-profit ladder, trailing stop or loss stop to this initial test. Do not accept or reject an entry signal based on PnL from an old exit strategy.

1. **Discover the entry effect.** Preserve the full forward trajectory for every eligible signal, including declines, flat paths, failed entries and incomplete coverage. Predeclare observation horizons and measure the probability, size and timing of subsequent rises, maximum favorable/adverse excursion, and whether the rise occurs before a major decline. Compare with simple matched controls. Describe both signal-time price movement and movement after modeled landing; they answer different questions. These observation horizons are measurement windows, not mandatory sell timers.
2. **Confirm the signal separately.** Test the frozen entry conditions on later data before choosing exits from those outcomes. A future peak or trough is an analysis label only, never information available to the entry decision. A selected favorable excursion is potential opportunity, not executable profit or an oracle exit.
3. **Develop exits for the demonstrated opportunity.** Once promising entry behavior exists, design and compare exits to capture its upside, preserve runners, reduce losing-position damage and manage risk. Exit logic should fit the observed opportunity rather than inherit an unrelated strategy's hold time or ladder. Report loser savings and surrendered winner upside explicitly.
4. **Calculate full profitability.** Apply the execution, cost, unresolved-position and funded-ledger requirements below to the resulting entry/exit policy. A signal can predict rises without producing profitable fills; distinguish those findings instead of letting an unsuitable exit obscure the entry effect.

Initial entry-discovery reports must lead with post-signal/post-entry behavior, not an old exit's profit table. Existing exits may be retained as separately labeled controls in the later exit-development phase. Explicit exit-only investigations may start from an already established entry signal.

**Cross-venue migration carryover directive (User instruction, October 7, 2026):**
When evaluating pre-migration bonding-curve strategies, do not artificially truncate positions, force-close at the 84 SOL curve graduation boundary, or discard graduated runs as unresolvable model failures. Model custody continuity through the migration freeze and execute exits into post-migration AMM pool liquidity (where initial DexScreener visibility and AMM liquidity surges occur). The primary goal is pre-migration entries whose exits carry over into migrated coins. Standalone AMM buy entries are secondary and research-only. All strategies must eliminate sub-30ms speed fragility, sizing at 0.50 SOL tickets within a 15.0 SOL bankroll (max 2 open positions).

**Observe, find anomalies, generate competing explanations, formalize a mechanism, compare against simple controls, stress, validate on later data, retain failures.**

Not: pick a rule family, sweep thresholds, choose a winner.

- **Observe** trajectories, participant sequences, developer behavior, cross-launch context, buyer recurrence, execution conditions. Goal: find structure.
- **Find anomalies** that violate the current mental model (Part 4).
- **Generate at least two competing explanations** per anomaly and design tests that distinguish them. Example: five recurring early wallets could be skilled independent buyers, one coordinated entity, copiers of a hidden wallet, reacting to an off-chain signal, incidental to a launch type that is itself predictive, or momentum creators for later demand.
- **Formalize** only a supported mechanism: unit of analysis, observable features, availability time, entry, exit, sizing, abstention, capital assumptions, expected source of profit.
- **Compare** against controls (Part 7), **stress** (Part 6), **validate** on frozen later data.
- If a candidate fails, record exactly where, why and which assumption failed, and whether the mechanism or only one implementation is rejected.

### 1.4 Suggested agent roles

A single agent that invents and validates its own ideas tends to rationalize. Where possible, separate:

- **Proposer:** generates hypotheses from the data schema and raw examples.
- **Red team:** attacks them (alternative explanations, leakage, controls that explain the result).
- **Harness runner:** runs the evidence process in Part 2 and reports without advocacy.

### 1.5 Ask the right question

Ask about mechanisms, not thresholds. A threshold is usually the final representation of an edge, not the edge.

| Threshold framing | Mechanism framing |
|---|---|
| Does outside volume > 5 SOL work? | Does rapidly broadening demand create persistent follow-through that overcomes early seller pressure? |
| Does dev sell-down > 85% work? | When does removal of developer inventory reduce supply risk, and what shows outside demand absorbed it? |
| Does buyer count >= 5 work? | Does broad participation differ from concentrated bot activity in a way that predicts executable continuation? |

---

## 2. Immutable evidence constraints

Hypotheses may be creative. Evidence may not be.

### 2.1 Causality

Decisions may use only information observable at decision time. Distinguish: instruction order, transaction completion, slot order, block timestamp, synthetic event time, provider receipt time, local decode time, decision time, submission time, landing time, confirmed execution time.

- Evaluate signals only after complete atomic transactions. Respect instruction order, source availability, finality and partial-day cutoffs.
- Verify prefix invariance: future events must not change an earlier decision. Declare a rule for same-time ordering.
- Never use eventual troughs, peaks, buyer counts, sell-down, migration, outcomes, later wallet classification or later market context in a decision, unless the experiment is explicitly labeled exploratory/retrospective.

### 2.2 Executability

Spot price is not realized PnL. Every candidate must eventually use: finite-size entry and exit quotes with own impact and sequential counterparty repricing, protocol/creator fees, network fees, priority fees and tips, setup/rent, failed submitted legs, retries, inclusion delay, slippage, adverse movement during delay, and unresolved positions. State uncertainty about counterparties' limits and reactions. Disclose omitted costs and assumed refunds.

### 2.3 Chronological accounting

One funded ledger: available cash, reserved cash, pending entries, open positions, pending exits, realized proceeds, fees, failed orders, unresolved inventory, capital displaced by competing opportunities.

- No instant capital reuse; use chronological proceeds.
- Shadow PnL never increases funded cash. Count a shadow outcome only after its exit or failure is observable.
- Do not scale small-ticket profit linearly, and do not enlarge tickets to make a backtest look profitable. Fixed fees hurt small tickets; large tickets change impact and eligibility.
- Report pending/unresolved liabilities, executable marks and conservative zero-recovery bounds separately from realized PnL.

### 2.4 Validation

A relationship is not an edge until it survives later data. Separate exploratory, rule-development, selection, later-evaluation and untouched-confirmation history. Freeze feature definitions, rules, code, source revision, timing assumptions, fees and selection logic before evaluating later periods. Select on earlier dates, evaluate on later dates without retuning, and prevent trades spanning a boundary from leaking into training.

- **Minimum horizon:** the user requires a 2-3 week minimum evaluation horizon where applicable. Distinguish covered calendar time, active dates, sample size and genuinely fresh time. A few hours or one day cannot satisfy it.
- Exploratory outputs (ML, clustering, forward-label analysis) generate hypotheses only. Training performance is not strategy evidence.

### 2.5 Source and coverage

- Authenticate creations; census the full eligible opportunity set where feasible. If sampling, declare outcome-independent sampling and coverage limits.
- Preserve raw inputs, source revisions and hashes. Repaired data can change shadow histories and capital allocation; compare unchanged rules before and after repair.
- Report missing/unsupported launches, missing transactions, incomplete genesis, unsupported modes, provider outages, truncated days and migration gaps separately from quiet launches, rejected signals and failed orders. Never treat missing data as "no sell", "no buyer" or a profitable unresolved exit.
- Source tape must extend beyond entry, hold, sell delay and any recovery/migration logic. Truncated coverage is not proof of a successful exit.

---

## 3. Where edge might live

Search across all of these. Do not assume earliest entry is best.

| Category | Question |
|---|---|
| Selection | Which deployers, launches, buyers, clusters, seed/mode cohorts or regimes deserve attention at all? Often more important than entry timing. |
| Information | Can we see or represent something earlier or better than competitors (sequencing, wallet history, lineage, funding, fingerprints, regime data)? |
| Behavioral | Are participants predictable (developer selling habits, buyer re-entry, sniper groups, size changes, response to wins/losses, strategy drift)? |
| Microstructure | Do curve shape, reserves, impact, fees, modes, migration mechanics or repeated bot orders create predictable states? |
| Timing | Genesis, just after genesis, after first outside buyers, after first seller, after developer sale, after bot-wave exhaustion, after first recovery, before/after migration, after a quiet period. |
| Execution | Provider race, routing, leader proximity, fee/tip policy, send fanout, exit latency, failure recovery. Measure separately from signal edge. |
| Exit | Demand exhaustion, developer re-entry, early sell-cascade detection, liquidity-aware or dynamic holds, partial exits, competitor-exit detection, post-migration continuation. Do not be entry-obsessed. |
| Abstention | Knowing when not to trade: poor executable liquidity, crowding, toxic concentration, imminent dev sell, weak follow-through, bad regime, capital contention. |
| Capital allocation | Weak prediction can still pay if capital is deployed selectively: confidence sizing, exposure caps, opportunity-cost-aware admission, regime risk, current vs initial equity. |
| Negative prediction | Predict failure: dump within N seconds, no meaningful buyer, dev sale before absorption, churn spike, unexitable liquidity. Avoiding losers may be easier than finding runners. |

### Units of analysis

"One launch" is not always the right unit. Consider: transaction (instruction order, roles, fees, signer structure), event (first outside buy, dev sell, burst, silence, recovery, migration), launch, deployer (history, cadence, sale habits, mode changes), buyer (prior participation, holding time, win/loss history), wallet cluster/graph (shared funders, co-occurrence, synchronized trading), and market regime. A discovery may only appear after changing level.

### Orthogonality

After several variants of one mechanism fail, move to a materially different hypothesis before widening the parameter search. "Materially different" means a change in unit of analysis, data source, causal mechanism, modeled participant, entry stage, holding horizon, exit logic, capital logic, competitive assumption, source of profit, or regime representation. Examples: genesis momentum, post-dev-sale absorption, buyer-cluster following, secondary-entry continuation, imminent-dump prediction, deployer regime change, cross-launch rotation, bot-behavior inference, liquidity-state prediction, execution-only edge.

---

## 4. Observation universe and anomaly search

Collect broadly before turning anything into a filter. Treat all concentration and independence measures as proxies; outside addresses are not proven independent or organic, and curve-observed developer holdings may miss transfers or off-curve custody. Label unavailable observations and proxies.

| Area | Collect |
|---|---|
| Deployer | Authenticated creator (vs. a reference sniper), launch history, cadence, seed/mode patterns, past sale behavior, run/migration rate, funding sources, behavior change over time |
| Launch setup | Quote currency, venue, reward/normal mode, seed, gross developer spend, reserves, token allocation, creator fees, creation instruction ordering |
| Demand amount | Gross outside buy SOL, net flow, seed-normalized demand, rate per unit time, post-sale demand |
| Demand shape | Inter-arrival times, acceleration, bursts, buy-size distribution, streaks, repeated waves, quiet periods, time since last meaningful buy. Is 5 SOL in 100 ms equivalent to 5 SOL over 4 s? Usually not. |
| Buyer breadth | Unique and meaningful buyers, repeats, largest/top-3/top-5 share, entropy, independent transaction groups |
| Buyer quality/history | Wallet age, prior early entries, hold times, co-occurrence, size consistency, win/loss persistence. Use only history available before the current launch. |
| Selling pressure | Outside sell SOL, developer sells, sell/buy ratio, acceleration, seller concentration, sell bursts; separate churn, developer supply, sniper exits and broad demand failure |
| Developer behavior | First sale time, count and size, inventory sold/remaining, staged vs single, rebuys, transfers, timing vs demand and price, reaction to strong/weak demand |
| Price path | Return from anchor, speed, realized volatility, drawdown and run-up so far, higher/lower highs, pump-dip-recovery, flat-then-burst, reversals. Only peaks/troughs already observed. |
| Curve/liquidity | Reserves, progress, marginal impact for candidate sizes, SOL needed to move price X%, exit depth, migration proximity. A signal may work only at sizes the liquidity cannot support. |
| Cross-launch | Gap since previous launch, its outcome and trapped capital, overlap, buyer rotation, cadence change, cannibalization |
| Market regime | Launch rate, aggregate volume, migration rate, success rate, congestion, priority-fee environment, active sniper count, time of day |
| Execution environment | Receipt vs decision times, inclusion delay, fees/tips, failures, competing orders |

### Anomalies worth chasing

Low early volume then a large run; huge early volume then collapse; developer dump then continuation; developer retention then collapse; few buyers but sustained growth; many buyers but no continuation; the same buyer cluster before many successes; abrupt deployer behavior change; strong continuation in a quiet market; a bullish signal turning bearish in one regime; a launch ignored by common snipers that later succeeds; a heavily botted launch that still fails. Do not discard outliers; ask what mechanism explains them.

### Snapshots and forward labels (exploratory only)

Build causal snapshots at several ages (e.g. creation complete, 100 ms, 250 ms, 500 ms, 1 s, 2 s, 3 s, 5 s, 10 s, 15 s) and events (first outside buy, second meaningful buyer, first sell, first dev sell, first burst, first dip, first recovery, silence, migration threshold). Record only what is known at that point.

Forward labels (executable return after N seconds, adverse excursion, probability of +X before -Y, exit-liquidity persistence, dev-sale probability, migration) are for hypothesis generation only and never live features. Control the snapshot/label/feature multiplicity with the look log.

### Representations

- **Relative features:** percentile vs the deployer's own history, vs trailing eligible launches, and normalized by seed, reserves, liquidity, developer inventory, elapsed age or ticket size. A factor may be weak in raw units and strong in relative ones.
- **Sequences:** buy-buy-sell-buy, dev sell then pause then broad burst, concentrated early buys then broad later buys, burst-silence-burst, sell cascade then stabilization, leader arrival then cluster arrival. Aggregates may hide order. Production rules must stay interpretable and causal.

---

## 5. Competitors, graphs and fingerprints

Other bots are part of the market; treat recurring automated traders as research subjects.

**Competitors.** Track wallets that repeatedly arrive early, co-occur, size similarly, exit similarly or trade the same deployers. Ask which deployers/seeds/modes they trade or ignore, whether they follow another wallet, wait for confirmation, stop after losses, use fixed tickets or an allowlist. Infer rules only as competing explanations. Another bot's action can be information, but test whether copying survives your added delay and impact. Their predictable exits (fixed time, fixed profit, dev sale, silence, migration) may matter more than their entries. Crowding may be a positive signal, negative signal or regime-dependent; do not assume.

**Graph/relationships.** Deployer-funder, deployer-prior wallets, buyer-buyer, buyer-funder, seller-buyer, wallet-fingerprint. Measure co-occurrence (time-decayed), common funding, synchronized trades, role recurrence, cluster persistence, known-vs-new cluster presence. Use "linked", "associated", "co-occurring" or "behaviorally similar", not "same owner", without evidence. Are "five buyers" really five signals or one strategy?

**Fingerprints.** Instruction ordering, program combos, compute-unit limit/price, priority fee, tip structure, account ordering, transaction size, lookup-table use. Can they identify strategy families, predict weak exits, or flag a deployer strategy change? Use only what is visible by decision time.

---

## 6. Execution and stress

Replay the whole logic under each scenario. Recompute quotes, signals, routing and admissions; never subtract a flat penalty from an unchanged winner list.

Stress dimensions: receive/decode/decision/send/landing delay, whole-block timing, buy and sell slippage or adverse fills, failed-send rate, priority fee and tip, weaker demand, stronger seller pressure, developer selling, truncated liquidity, larger and smaller tickets, provider outage/gaps, migration path. Treat measured detect-to-land telemetry separately from synthetic latency.

---

## 7. Controls and tests of the claim

Every candidate faces simple baselines: no trade; all eligible launches; fixed-time entry; fixed-size entry; strongest existing fixed rule (currently the repaired BWAM normal-12 control); random subset with matched number of trades, matched exposure or matched capital at risk; matched entry age; matched entry price. For routers also compare each setting alone, an ungated launch router, a market-gated router and the inherited router. Report whether a gate helps selection or merely trades less.

Falsification questions for every candidate:

- What similar launches did not work, and what worked without the "important" factor?
- Is the factor merely a proxy for price already moving?
- Does a random matched subset do as well?
- What happens with a slightly worse fill, 100-300 ms worse execution, a larger ticket, without the largest winner, without the strongest day, in a later regime?
- Does shared capital mean an added order displaces a better trade?
- What would make us abandon the hypothesis?

Add ablations for each condition (added silence, inventory or exit conditions can remove the trades behind a profit claim), bounded interactions with a plausible mechanism (deadline x churn, recent flow x landing cap, demand speed x churn, dev sell x post-sale demand), and neighbor tests. Avoid brute-force combinatorics.

---

## 8. Definitions every experiment must make explicit

- **Seed:** curve input vs gross developer budget including protocol/creator fees; state tolerance (0.15 vs 0.35 SOL matters).
- **Outside buying:** buys by addresses other than the deploying wallet; state how associated wallets are treated.
- **Net flow:** subtract outside sells only, all sells, or developer sells separately.
- **Recent flow:** lookback and its unit (seconds, slots, transaction groups); same-time ordering.
- **Churn:** outside sell SOL / outside buy SOL; define the zero-buy case.
- **Buyer count:** unique addresses meeting an individual purchase floor (e.g. 0.02 vs 0.05 SOL), not transactions; define repeats and dust.
- **Concentration:** largest/top-N share, denominator, window.
- **Developer sell-down:** tokens sold / initial seed tokens with rebuys accounted for; distinct from SOL recovered / seed SOL.
- **Post-sale absorption:** demand strictly after the observed sale; cumulative demand from genesis is a separate hypothesis.
- **Anchor price:** typically spot after the complete creation transaction, not the developer's average price or pre-seed spot; state if it is an executable quote instead.
- **Trough/recovery:** a trough already observed by decision time.
- **Clock:** which of the clocks in 2.1 is used.

Keep seed sizes and holder/reward modes separate when measuring conditional results. Registry prose, saved parameters and executed rules have diverged before; preserve differences rather than silently standardizing them.

---

## 9. Parameter menu (previously explored, not recommendations)

Use as a reference for what has been tried and to keep distinctions, not as a default search grid.

**Entry/eligibility:** wallet/cohort and mode; seeds around 2/3/4/5/6/10/12 SOL; fixed 1-2 s observations; first-crossing deadlines roughly 2-8 s (exploratory to 15 s); outside-volume floors 0.5-15 SOL; one to five meaningful buyers; largest-buyer ceilings 0.35/0.50/0.70; churn ceilings 0.20-0.60; developer sale forbidden/required/unrestricted; remaining-inventory thresholds (e.g. 15% remaining); post-sale demand and deadline; price cap vs anchor; separate landing guard (e.g. 1.10-1.30x anchor; failed submitted guards still pay fees); one attempt per mint and precedence if several patterns qualify.

**Exit:** max hold from actual modeled entry (2-12 s examples; longer needs coverage); full vs partial exits (a generic multi-minute bot ladder is a different strategy); take-profit on executable net profit vs spot target; peak drawdown distance and monitoring window; breakeven arming; trailing arming/distance/grace; silence timeout and reset behavior; developer-sale or emergency triggers (spot triggers do not guarantee realized sale price); sell delay, failures, dust, partial fills, unresolved positions. For every trigger define the reference value, observation clock, delay, finite-size quote, failure/retry behavior and unresolved handling.

**Sizing/capital:** fixed vs independently quoted tickets (0.04-3 SOL across studies); signal tiers with a zero/skip tier (check each tier has enough observations); allocated balances 2/5/10 SOL; principal vs current equity; conservative/balanced/aggressive profiles; reserves, exposure caps, daily risk budget; pending and unresolved positions counted in reservations.

**Routing:** outcome counts 5/8/10/12/20; lookbacks 30 min/2 h/24 h; mean/median gates, return floors, consecutive-loss vetoes, daily loss stops, warmup and cold-start rules. These are heuristics, not calibrated probabilities. Up to two or three interpretable settings plus skip; switching cannot manufacture profitable components. Distinguish current-launch state from trailing market state. Freeze candidate selection, overlap precedence, cadence, lookback, reset rules and ticket economics. Keep shadow observations for skipped signals. Avoid routers that merely pick whatever recently won unless the selection survives later validation.

**Entry mechanisms to keep as baselines:** complete-creation entry (never assume second/third-buyer landing), fixed-age observation, first threshold crossing, early momentum, demand burst, developer-sale entry, strict post-sale absorption, dip with returning buyers, post-sale recovery, secondary momentum, explicit abstention.

---

## 10. Prior results (read before proposing)

Preserve as accumulated evidence, not universal truths.

- Volume alone and blind sizing did not establish BWAM profitability; high aggregate activity can coexist with low retained demand per launch.
- Saved parameters, registry prose and executed rules have diverged; preserve buyer-floor, seed-tolerance, flow-definition, reward-mode and exit differences.
- A cumulative absorption rule can pass using buying entirely before a developer sale. Test strict post-sale demand separately.
- Added silence, inventory or exit conditions can remove the trades behind a historical profit claim.
- A router positive in aggregate can depend on one day or a few winners; past-day selection and live-like trailing selection can differ.
- The latest BWAM three-family experiment rejected its nine bounded new configurations; the qualified router enabled no settings, and its diagnostic routers lost and harmed the fixed control when combined. This rejects those recipes, not every BWAM scenario.
- The repaired fixed normal-12 candidate retains conditional historical support in some capital profiles, with drawdown and concentration limitations. It is a research control, not proof of deployable edge.
- BWAM normal-5 and normal-12 launches are important cohorts, but do not assume they exhaust BWAM opportunities or transfer to another deployer.
- A failed bounded search rejects the tested recipes, not every strategy for that deployer.

### Repository references

- [Latest BWAM collaboration results](bwam_superharness/REPORT.md) and [independent accounting/risk review](bwam_superharness/INDEPENDENT_ACCOUNTING_RISK_REVIEW.md)
- [Exact BWAM canonical rules](bwam_superharness/CANONICAL_RULES.json)
- [BWAM early-flow and exit study](../data/research/bwam_angles/REPORT.md), [dynamic pattern/sizing](../data/research/bwam_angles/DYNAMIC_REPORT.md), [deeper routing](../data/research/bwam_angles/DEEPER_REPORT.md)
- [Multi-wallet signal sizing](../data/research/tier_sizing/REPORT.md)
- [Deployer launch moments](../data/research/deployer_momentum/REPORT.md) and [demand bursts](../data/research/deployer_bursts/REPORT.md)
- [Independent rule/implementation discrepancy audit](../data/research/independent_audit/REPORT.md) (older optimistic claims must be read with later reviews and corrected-source results)
- [Research data overview](../data/research/README.md)

---

## 11. Anti-patterns

- Endless neighboring grid search without a new mechanism.
- Winner mining: searching a huge space and reporting only the best configuration.
- Outcome leakage; spot-price fantasy (peaks that could not be liquidated at size).
- Parameter storytelling after a configuration happens to win.
- One-day or one-winner edges promoted without acknowledging concentration (do not auto-reject a runner strategy or require every day to profit; investigate dependence).
- "More filters = better"; confusing less trading with better selection.
- Scaling small-ticket results linearly.
- Treating repeated bot wallets as independent humans.
- Assuming earliest is best, or that the current unit of analysis is right.
- Letting this file's idea lists become a checklist to work through in order.

---

## 12. Research queue and "wrong framing" checks

Maintain a queue: priority, hypothesis, category, novelty, required data, feasibility (now / new data / impossible), current evidence, next test, status. Rank by plausibility, expected value if true, novelty, cost of testing and ability to falsify, never by backtest optimism. Prefer a falsification test over another neighboring sweep.

Each cycle, aim for a diverse mix: a refinement of an existing mechanism, an orthogonal family, an anomaly-derived idea, an adversarial/competitor idea, a negative-prediction or abstention idea, and a "wrong framing" idea. This is a diversity goal, not a quota; do not force weak ideas.

Periodically ask whether the framing is wrong. Maybe early buyers or funders predict more than deployers; exit timing matters more than selection; genesis is structurally too competitive; the opportunity starts after sniper exits; exit liquidity is easier to predict than price; failure is easier to predict than success; cross-launch dynamics beat isolated launch state; only a narrow deployer subset is worth modeling; event sequences beat thresholds. Record these challenges even when rejected.

Useful prompts: What are we aggregating that should stay sequential? What should be normalized? Are counts hiding identity, totals hiding timing, averages hiding concentration? Can we make money by entering later, exiting earlier, trading fewer launches, or avoiding the highest-contention ones? Which variables change sharply before successes or failures?

### Unconstrained ideas

Every report ends with a short section: **"What I would investigate if data and tooling were unconstrained."** List ideas that cannot be tested yet, with the data each needs. Ideas recorded here are not signals until tested.

---

## 13. Hypothesis template

- **Idea / mechanism:** why should expected value exist (behavioral, structural, informational, competitive, execution)?
- **Unit of analysis and cohort:** wallets, seeds, modes, venues, dates.
- **Observables and availability:** exact features and when each becomes knowable.
- **Feasibility:** feasible now / needs new data / not possible.
- **Competing explanations:** at least two where reasonable.
- **First diagnostic:** the descriptive test to run before any rule.
- **Entry / exit / routing / sizing:** only after evidence supports formalizing; bounded search.
- **Controls and predeclared selection criteria.**
- **Dev / later test / untouched confirmation dates.**
- **Execution stresses and capital assumptions.**
- **What would reject or weaken it.**
- **Results (including negative), limitations, artifact links.**
- **Next step.**

---

## 14. Result card for every promoted candidate

1. Mechanism and unit of analysis; wallet/cohort and exclusions.
2. Exact feature definitions, entry/exit/router/sizing payload, units and all defaults.
3. Source interval, cutoff, active/complete dates, opportunity counts, gaps, exclusions.
4. Train/selection/evaluation dates; retrospective vs untouched; freeze time and code/source/config/model hashes; look-log count.
5. Balance, ticket, funded policy, execution clock, delays, fees, full stress matrix.
6. Attempts; closed/failed/pending/unresolved counts; admitted vs skipped opportunities; failure reasons.
7. All-attempt net SOL, daily PnL, net per attempt, profit factor, win/loss distribution, drawdown, exposure, capital feasibility.
8. Largest-winner and strongest-day dependence, deployer and regime dependence; day-grouped uncertainty with a note on what resampling does and does not establish.
9. Controls, ablations, neighbor tests, interactions, matched-exposure or shared-capital tests.
10. Failure modes.
11. Status: diagnostic, rejected, retrospective candidate, prospectively supported under stated assumptions, or production-research ready under stated assumptions. State missing evidence and the exact next falsification test.
12. Reproduction commands, independent review, durable checkpoint.

### Failure memory

Failed research is an asset. For each failure record mechanism, exact configuration, cohort, dates, why it was tested, and how it failed (weak signal, late entry, poor exits, fees, impact, capital contention, regime drift, data error, source or implementation mismatch). State the exact scope of rejection, not "this idea doesn't work."
