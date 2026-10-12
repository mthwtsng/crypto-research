# Backtest accuracy review — October 11, 2026

## Finding

The latest saved replay is credible as a **one-day simulation under its stated assumptions**, not as a forecast of live strategy PnL. In the sampled, locally screened population, the current-entry/current-exit Central85 result is **−1.238466812 SOL** (18 funded attempts, 16 closes, two failed guards, no unresolved inventory). The report’s wider verdict is correctly **undetermined, retrospective**: only 16 filled attempts resolve the tested package, and the full current holder screen admits zero historical setups. This result says nothing conclusive about the fully screened population.

The much larger positive October 9 active-cohort claims in the master registry are **not reproducible or supported by the artifacts now in this checkout**. Do not use the +2.98 SOL S1, +0.4112 SOL S4, or +2.3245/+3.1274 SOL dynamic-sizing figures as current empirical benchmarks until their original replay, data selection, funded outputs, and engine version are recovered and audited. The extant cohort is explicitly outcome-filtered and incomplete; I cannot establish that the old run used a banned engine, so this is an evidence/provenance failure rather than a finding that it did.

## Artifact audit

| Artifact | Assessment |
|---|---|
| `reports/day_sample_20261011/` | Best current accuracy evidence. Its fixed-hash sample came from a complete 47,335-creation census (240 mints, 10 per hour), with continuation and source-parity distinctions retained. The saved funded rows reproduce the report’s central values. The current/local Central85 row is −1.238466812 SOL; canonical/local is −0.942708969 SOL; same current entries with canonical exits are −0.878071532 SOL. The matched-exit comparison is development on this sample, not validation. The local screen omits historical holder-balance gating; the full gate is unevaluable, not a zero-PnL test. Seven authentic pool histories were collected, four joined to replayable continuations, and V3 completion with a synthetic pool leg remains explicit coverage debt. |
| `research/day_general_20261004/` | A useful earlier fixed-rule transfer study with source repair, atomic replay checks, and honest sampling limits. Its `same_slot_one` and `next_slot_tail` numbers predate the current Central80/85 mixture and should not be read as present Central85 estimates. It reports one sampled day and explicitly warns against extrapolation. |
| `research/MASTER_STRATEGY_REGISTRY.md` Oct 9 active-cohort section | Positive figures are unsupported in the current checkout. It cites `reports/ACTIVE_COHORT_MOMENTUM_REPLAY_REPORT.md`, which is absent. `research/active_momentum_cohort_20261009/` is a collection directory marked `collecting`, 562/2,000, with an Aug 18–Sep 30 window; the manifest says `complete: false` and `selection: outcome-filtered active research cohort`. This does not match the registry’s claimed Aug 18–Sep 7 period and cannot establish general-launch expectancy. |
| Active-cohort runner candidates | `run_unified_cohort_replay.py` imports `strategy_validation_batch2/engine_frozen.py`, but that directory is absent; its `PROVENANCE.json` does not freeze replay-engine hashes or results. `scripts/run_active_coins_benchmark.py` expects `ACTIVE_COINS_MANIFEST.json`, bound tapes and prepare audits under the 21-day collection path, plus writes an output JSON that is also absent. `scripts/test_all_concurrency_and_strats.py` points at the separate 1,800-coin Oct 3–6 benchmark, not the claimed 562-coin August cohort. None supplies the missing Oct 9 result card or proves which engine produced it. |

## Method and controls

For the Oct 11 sample, the runtime path imports the repaired `research/core_plan_audit_20261007/engine.py` and ledger, with a report-local V3 extension. The replay source hash in the report matches the file on disk; the report also records source hashes, 1,264 replay rows with no errors, and 44 focused tests. I did not rerun those tests or any PnL sweep. I inspected the placement helper and parsed the saved `FUNDED_RESULTS.json`; its canonical/local, current/local, and matched/local central totals and attempt counts match the report.

The Central80/85 logic uses an outcome-independent deterministic hash per intent, the contract’s 80%/85% same-slot probabilities, and the saved historical same-slot group split (29/132 at zero intervening groups, 20/132 at one, 83/132 at two or more). The next-slot branch lands after its first eventful transaction group; reactive exits use the same placement rule from the trigger. This is structurally aligned with the accuracy contract. The headline is still an assumption-driven estimate: the same-slot rate is user-reported, and the 132-copy group distribution is from an older execution configuration, not measured on today’s strategy intents or sells. Scheduled-sell delivery remains uncalibrated.

The report checks integer finite-size quotes, fees, counterparty repricing, custody, timers, failed guards, migration continuation, and shared 15 SOL cash accounting. Research concurrency is uncapped under the current authorization; this does not change the live cap. It explicitly uses canonical all-family/global breakers rather than the deployed shadow map, which currently contains only S4. Thus it is not a replay of the running shadow binary. The same-day shadow log is separate paper evidence: its quoted fills and placement are not calibrated actual fills.

Accuracy alarms are accounted for rather than hidden. The Oct 11 report found 40 timer legs not early, 1,412 exit legs not before their triggers, no curve sale after completion, and no exact-threshold fills. The slower-than-fast alarm did fire in secondary comparisons; paired guard failures and changed admission/breaker paths explain those cases. The primary current/local bracket is ordered fast > Central80 > Central85 > slow. The current/local high-fee result is −1.253761793 SOL; next-slot-tail stress is −1.308369435 SOL. These checks support internal replay consistency, not the live landing model.

The older Oct 3–4 general-launch report remains useful as a warning against optimistic placement: its mature-breakout result is positive only in `same_slot_one` and negative in `next_slot_tail`, while the synthetic `same_slot_one` assumption is explicitly not equivalent to the user’s same-slot percentage. It is not a current Central result. Likewise, the registry’s earlier restored-control +0.274067950 SOL is a combined marked estimate from a different sample, with settled −0.758305176 SOL and 13 unresolved positions; it must not be combined with the Oct 11 sample or described as realized profit.

## Recommended next work

1. Keep the Oct 11 result labeled `undetermined, retrospective`; freeze its exact screens and exits before collecting an untouched 14–21 day creation-selected evaluation. Preserve the same all-family risk policy and show local-screen and fully screened eligibility separately.
2. Recover decision-time holder balances and their provenance. Until then, report the local-gate replay as a diagnostic and do not infer results for fully screened/non-rug coins.
3. Calibrate buy, urgent-sell, and scheduled-sell placement independently from intent-to-signature-to-block-position records. Replace the old 132-copy distribution only after later, comparable observations exist; keep Central80 and Central85 sensitivities meanwhile.
4. Repair and freeze migration/V3 continuation coverage, including changed-path completion and custody, before extending conclusions to carryover setups.
5. Mark the Oct 9 active-cohort claims as **unverified / not a current benchmark** until the exact sample manifest, replay engine and code hash, central result rows, look count, alarms, and funded result card are restored. Retain the conditional active-market hypothesis, but do not let an outcome-filtered cohort stand in for a launch-universe estimate.

## Result card

```text
engine + revision: Oct 11 report uses the approved day_general family plus repaired core_plan engine; saved core_plan engine SHA256 bb844aaf9b8c8fad050bc69b35b379b325cdd31a1f5a91482d93f420108a8976. No new replay run.
data: Oct 10 06:00–Oct 11 06:00 UTC; 240 fixed-hash mints from 47,335-creation census, 10/hour; continuation to Oct 11 07:34; outcome-independent sample, retrospective day.
rules frozen before this data?: no relative to event dates; code/source frozen before replay. The matched-exit row was added after inspecting the sample.
look count: three entry/exit packages; seven entry/exit/screen comparison cells, plus declared placement/fee/timer sensitivities.
placement: current/local fast −1.045396720 / Central80 −1.238073788 / Central85 −1.238466812 / slow −1.357544916 SOL.
stress: next_slot_tail −1.308369435; Central85 at 0.002916 SOL delivered fees −1.253761793; scheduled +1/+3 slots both −1.238466812 (no changed outcomes; this does not calibrate delivery).
Central85 current/local: settled −1.238466812 + open marked 0 = combined −1.238466812 SOL; zero-recovery bound −1.238466812; 18 attempts / 16 closed / 2 failed / 0 unresolved.
drawdown / largest winner / without largest: 1.334006749 / +0.095539937 / −1.334006749 SOL.
bug alarms: timer-before-deadline pass (40); sell-before-trigger pass (1,412); post-completion curve sell pass; exact-threshold fill pass; delayed >30-attempt comparisons had failed guards; slower-outperforms-faster triggered in secondary comparisons and explained. The primary current/local bracket has fast least negative and slow most negative; >50-trade alarms not applicable.
verdict: undetermined, retrospective. The resolved local-screen subset is negative; full current screens have zero historical eligible setups and the sample is one day.
what would change it: later untouched 14–21 day results, causal holder-history coverage, calibrated execution cohorts, and complete migration/V3 custody continuation.
```

Audit scope: read-only review of saved code, reports, manifests, hashes and funded summaries. No replay, new PnL sweep, source/config/registry/log edit, order, or runtime action was performed.
