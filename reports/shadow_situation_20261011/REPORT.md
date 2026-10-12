# Current shadow situation — October 11, 2026

**Verdict: undetermined, retrospective.** The live feed provides forward observations, but repeated changes, restart carryovers, short samples and uncalibrated simulated placement prevent forward confirmation of the current strategy package. There is evidence of weak entries and surrendered upside; neither all entries nor all exits can be blamed uniformly.

This is an observational log/source audit, not a backtest, a new exit simulation, or actual wallet performance. No running script, strategy, filter, breaker or position was changed. Root reviewed two GPT-6 Luna xhigh read-only audits; the preferred GPT-6.1 Luna was unavailable.

## Frozen account snapshot

Summary timestamp **2026-10-11 07:19:47.547958580 UTC** (00:19:47 Vancouver), session `ghost-v2-20261011T064058`:

- Nine closed paper trades: **−0.158217252 SOL**; failed-buy fees: zero.
- One open S5 position, original cost 0.501505 SOL, delivered paper tranche proceeds 0.431522214 SOL, remaining executable paper mark 0.469657937 SOL. Lifecycle open marked PnL: **+0.399675151 SOL**.
- Closed settled outcomes + open lifecycle marked outcome = **+0.241457899 SOL**, or total marked paper equity **15.241457899 SOL**. Cash alone is 14.771799962 SOL; committed inventory is not a realized loss.
- One open position, zero unavailable marks in this snapshot. The open position is not a closed win. Zero remaining-token recovery would give combined lifecycle PnL −0.228200038 SOL; that is a downside bound, not the expected result.
- The mark is an authenticated PumpSwap RPC snapshot/finite-size paper quote for `5sh1QmnDdXLYvPPdocMwKZSBNRGRbtzjFMt3Rs9ZQfeT`, pool `BSTmsq1M4zr6VQZGBV8fWQHWr28QvktgeDSTTdSKnWW8`. The summary is the accounting anchor. The separately copied runtime has a later pool observation at 07:19:51.878 UTC / slot 455566359; do not combine that later price with earlier summary values. Neither represents an on-chain sale.

For this decomposition, realized tranches remain inside the open position's lifecycle result to match the runner's closed-position settled subtotal. Cash already contains their delivered paper proceeds; they are counted once.

| Family | Closed | Wins | Closed paper PnL, SOL | Current evidence |
|---|---:|---:|---:|---|
| S1 | 2 | 0 | −0.095814177 | Floor invalidation/stop, negligible recorded positive excursion |
| S2 | 0 | 0 | 0 | No admitted current-session fills; pending watches are censored |
| S3 | 1 | 0 | −0.099977489 | −18% stop after 18-second grace |
| S4 | 6 | 3 | +0.037574414 | Three rejection stops, three profitable trails |
| S5 | 0 | 0 | 0 | One retained, partially sold AMM position with positive mark |

S4's largest closed winner is +0.159941328 SOL: the current closed S4 subtotal without it is −0.122366914 SOL. Runner concentration is a diagnostic, not automatic rejection. No verified whole-account marked drawdown series was reconstructed.

## Entry versus exit diagnosis

The frozen current trade file contains 42 opens, 41 closes and five failed-buy guards across multiple session IDs, from October 11 00:24 to 07:17 UTC for recorded closes. **Do not sum these as one continuous funded portfolio or one frozen configuration.** Three closes cross session IDs; one S5 position was retained for over four hours and stopped only after a later restart. Missing earlier receipt paths and intent epochs prevent full reconstruction.

Resolved-row descriptive counts: S1 0 wins/9 closes; S2 1/4; S3 1/3; S4 6/19; S5 3/6. These include mixed rules and carryovers and are not current-policy profitability estimates.

**S1: entry/setup economics are the stronger concern.** Seven of nine closes have recorded peak net ROI at zero, and none reaches +10% recorded peak net ROI. The immediate floor/loss exit is generally reacting to a failed bounce, not throwing away an already demonstrated large profitable move. Test whether post-developer-sale buying is genuinely new absorption, how much selling remains, and whether finite-size round-trip economics leave enough upside. Smaller separately quoted research tickets are an experiment, not a linear scaling promise. Do not mistake the logged `buy_impact_pct` for price impact: it measures percentage growth in real SOL reserves.

**S2: evidence is sparse.** Three of four pooled closes have zero recorded positive peak. Current-session S2 has no fills. A surviving reserve level and historical buyer count do not establish fresh demand at the entry; inactivity can also reflect screens or reclaim gating. No causal matched breakout/reclaim profitability comparison exists in the variant log.

**S3: two purchases do not yet establish a durable bounce.** The current losing trade reached no recorded positive net peak and stopped after about 18 seconds. One other pooled loss reached +10.6%, while one win reached +43.3%. There are only three pooled closes, so neither a shorter grace nor more patience is established as better. Compare a causal second demand wave/higher low with the exact two-transaction control before optimizing exits.

**S4: both failed entries and exit opportunity are visible.** All three current rejection-stop losers had recorded peak executable ROI at zero. However, within the following minute `siBF3bcDKAH9...` and `FoZcuF5qFuKM...` rebounded about +25% and +98% in observed curve spot versus the last pre-exit spot; `AgpQqukiTNoT...` fell about another 46%. All three current profitable exits also had higher subsequent observed spots, about +17%, +62% and +29% within a minute. This is evidence to compare selection and runner management, not proof that removing stops or holding would profit. These percentages exclude finite sale quotes, counterfactual impact and a delivered alternative exit.

**S5: continued migration execution is the correct direction, with policy still unproven.** Six post-exit AMM watches show mixed paths: one later peaks ~179% above exit spot and ends ~69% below it; another peaks ~145% above and ends ~43% above. Universal immediate liquidation and universal long holds both leave failure modes. Preserve migration custody and compare exits against post-open demand and liquidity, with downside and surrendered upside both measured. The current positive open mark is useful evidence, not a completed winning trade.

## What the reclaim entry actually does

Current variant records explicitly say `live_entry_mode=reclaim`. A breakout arms a watch; price must fall at least 8%, then a buying transaction must return to the **original breakout level** within 180 seconds. This is a confirmation filter, not an 8%-cheaper fill. It also misses runners that never dip.

Across logged reclaims, median S4 entry overshoot is 0.82% above the original level and maximum is 30.43%. Current examples:

- `AgpQqukiTNoT...`: 48.85-second wait, 8.6% dip, reclaim signal 6.5% above the original level; lost.
- `siBF3bcDKAH9...`: 169.16-second wait after a 40.8% collapse; reclaimed and subsequently lost while held, then rebounded after exit.
- `CMyMb6Ttpyge...`: 1.98-second wait after a 14.3% dip; won, then continued after exit.

The reclaim branch rechecks holder-screen readiness, capital and exclusions, but does not freshly require the original buyer/flow conditions, retained reserve band, a new meaningful-buyer sequence or a maximum overshoot. It reuses the original signal. **Highest-priority entry hypothesis:** distinguish quick absorption of a retest from an old collapsed coin making one large reclaim purchase. A price/size guard is useful only if it improves later finite-size opportunity without excluding the continuing winners. No new threshold was selected here.

## Current source is a revised strategy package

At git revision in `PROVENANCE.json`, important differences from the registry's exact reproduced control include:

- S1 trough entry window: 35 slots versus three.
- S2 breakeven arming: +20% versus +10%; S2/S4 use the reclaim wrapper.
- S3: >=35 qualified buyers added; 18s/−18% stop versus 8s/−12%; +20%/10pp trail versus +75%/20pp.
- S4: >=35 buyers and >=0.95 SOL signal buy versus >=22 and >=1 SOL; delayed rejection at >=25 slots/−18% only if peak is below +10%, plus −22% severe dump stop, versus >=2 slots/−8%. Half at +20% and 6% relative total-wealth trail remain.
- S5: >=50 unique nondeveloper buyers added; no opening sale; half at +50 percentage points above first observed AMM ROI; after 60s an 18% relative trail; 600s AMM timeout; −35% versus first AMM value or −45% lifecycle stop. A separate 600s curve-stagnation exit is also present. The control sells half after authenticated opening, then uses an 8% relative trail/30s timeout.

The S5 first AMM anchor is the first obtained valid snapshot, not proof of the pool's whole opening transaction. Historical positive selected-active-coin cohort results and the registry's earlier undetermined canonical result do not validate this changed package in today's full live universe.

## Evidence and implementation gaps to repair first

1. **Breaker map:** the frozen runtime contains only `UpperAthBreakout` despite `circuit_breakers_enabled=true`. Restore replaces the initialized map with saved entries; missing families bypass cooldown gating. The shadow source also lacks the registry's global rolling loss pause and 0.25 SOL cooldown-probe recovery. This affects opportunity admission and risk; it is not proof of poor entry alpha. Launcher defaults are not evidence of effective restored settings.
2. **Wrong policy metadata:** summary/writer describe 1-SOL holder-count screening, while current holder-screen code/evidence use <0.3 SOL supply concentration, >=50% low-SOL supply, >=8 of top ten, or a >=7% single low-SOL holding. The newest setup history records the latter revisions. This is stale telemetry, not a request to reinstate older policy.
3. **Configuration identity:** VM ID survives checkpoint restore/restarts. Source/build/config hashes, effective cap and entry mode are absent from summary. Uptime and archive snapshots show multiple process intervals under the same ID. Freeze and label complete configuration epochs.
4. **Paper placement:** 70ms starts from provider receipt, not measured source-chain landing. The account has no central80/85 mixture, on-chain fills or higher-fee sensitivity. AMM polling is sequential RPC plus 200ms loop sleep; intent-ready time is not guaranteed delivery. Snapshot pricing retains own-sale adjustments but does not replay every external transaction under changed custody.
5. **Log integrity/coverage:** current intents include a byte-identical duplicate S4 partial-fill row; an S5 migrated paper partial is labeled `event=FAIL` although its status is a filled partial and cash is credited. Earlier trade epochs lack corresponding intent epochs. Missing source paths cannot support retrospective entry/exit reconstruction. Undecoded receipts are not automatically all missing Pump swaps; a denominator/reason audit is required.
6. **Marks:** when a mark is unavailable, account equity can fall back to cost; read the unresolved count and mark source before interpreting equity. The earlier agent snapshot briefly had an unavailable S5 mark; the selected later snapshot has a valid mark. A later price is not interchangeable with the earlier accounting timestamp.

Atomic whole-transaction processing is required by Solana's actual transaction semantics ([official documentation](https://solana.com/docs/core/transactions)). Current source applies all decoded instructions before evaluating triggers. This is a useful repair, not complete counterfactual replay validation.

## Recommended research order

First establish truthful per-epoch configuration, complete breaker inventory, fill-event semantics, receipt coverage and mark provenance. Keep the running experiment intact until a specific change is authorized.

Then freeze a small comparison: (1) canonical breakout, (2) current reclaim, (3) reclaim with causal refreshed absorption and bounded chasing. Record all eligible, skipped, failed and nonreclaiming signals; keep the same 15 SOL funded policy. Examine full post-fill trajectories without inherited exits first. A lower observed price alone is not a better executable entry.

For exits, compare the current S4 remainder trail with a demand-conditioned runner exit; evaluate rescued loser opportunity, extra downside on dead coins and surrendered winner upside. Keep S5 carryover and compare the current post-open grace/trail to the exact registry control using complete AMM transaction history. Do not stretch all stops or shorten all timers from these examples.

Keep S1/S2/S3 at research/probe priority until fresh entry evidence is stronger; test independently quoted smaller S1 tickets if investigating liquidity economics. Dynamic sizing should follow demonstrated opportunity, not amplify this uncertain sample. Freeze candidates and evaluate later untouched 14–21-day data with actual placement calibration, all attempted fees and migration continuity. This audit selected no profitable variant and ran no parameter sweep.

If data/tooling were unconstrained, investigate authenticated funding/retained-supply links, buyer recurrence and seller release, actual inclusion telemetry, and complete cross-venue transaction-level post-entry paths. Each requires data beyond the current aggregate screens and snapshot stream.

## Result card

```text
engine + git revision: observational shadow v3/source audit; git in PROVENANCE.json; no approved-engine replay run
data: frozen Oct11 07:19:47 UTC summary; 42 opens/41 closes/5 guards across mixed sessions;
      ongoing receipt file selectively inspected for current mints; creation-complete tape check not established
rules frozen before this data?: no single verified unchanged epoch; current defaults/registry differ
look count: one observational audit; zero new strategy/exit variants replayed; prior tuning count unknown
placement: fast / central80 / central85 / slow: not run; no central profitability estimate
stress: higher 0.002916 fees / next_slot_tail / 3-slot scheduled sells: not run
current attempts / closed / failed / unresolved: 10 / 9 / 0 / 1 open (valid mark, unavailable marks 0)
current accounting: closed settled -0.158217252; open lifecycle marked +0.399675151;
                    combined +0.241457899; zero remaining-token recovery bound -0.228200038 SOL
max drawdown: not reconstructed; largest current closed winner +0.159941328;
              closed subtotal without it -0.318158580 SOL (open inventory still separate)
bug alarms: speed inversion N/A; delayed-guard counts 5 pooled/0 current, central N/A;
            exact timer anchoring not comprehensively rechecked; pooled attempts != closes;
            delivered stops differ from thresholds; curve-after-completion not comprehensively rechecked;
            no >70% WR/>3 PF current alarm; creation coverage not established
verdict: undetermined, retrospective (forward observations are not a forward-confirmed policy)
what would change it: frozen later 14–21-day all-attempt funded central replay/fill reconciliation,
                      reliable full migration coverage, reconciled configuration and costs
```

Evidence files are immutable copies for this report; live `data/` continues changing. Source hashes are recorded, but the active host process/build/environment was not independently visible from this workspace. Full observations/intents/AMM snapshots remain in `/tmp/shadow_diagnosis_20261011/` for this session; those temporary files are not promised permanent artifacts.
