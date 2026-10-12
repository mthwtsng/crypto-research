# Frozen day sample and current shadow assessment

**Verdict: undetermined, retrospective.** The current entry/exit replay with reconstructable bundle/concentration/scan gates produced **Central85 settled −1.238466812 SOL + open marked 0 = combined −1.238466812 SOL**, with 18 funded attempts, 16 closes, two failed guards and zero unresolved positions. This is a diagnostic of partially screened setups. The complete current screen could not be evaluated at useful scale: its causal historical holder-balance evidence admitted **zero current setups**, so this does not establish profitability for fully screened coins or answer whether genuinely non-rug coins have an edge.

The [latest frozen shadow snapshot](../shadow_new_profit_20261011/refresh_final/REPORT.md), **October 11, 16:34:14 UTC**, records **39 paper closes, 16 wins/23 losses, settled −0.218531123 SOL, no open inventory**. The earlier +0.643900894 SOL at 07:34 was real recorded paper profit, followed by a 0.862432017 SOL giveback. Latest S2 (+0.257892420) and S5 (+0.236999661) contributions are encouraging but small; S4 (−0.347693735) and S3 (−0.285183079) outweigh them. Recorded quotes and assumed placement remain uncalibrated against actual fills.

## Selection and historical screens

Creation window: **October 10 06:00–October 11 06:00 UTC**, with continuation captured through **October 11 07:34 UTC**. A complete census of **47,335 creations** supplied ten fixed-hash-selected SOL launches per hour: **240 selected mints**, including 33 holder-reward curves, excluding unsupported Mayhem. The seed and selection were frozen before collecting sample outcomes, not before the historical day occurred. No future volume, survival, price or migration criterion selected the coins. All selected mints remain in the manifest, including no-activity and coverage-debt cases.

Three screening scopes were retained rather than silently substituting missing historical evidence:

| Scope | Canonical eligible signals | Current eligible signals | Interpretation |
|---|---:|---:|---|
| Gates off | 43 | 34 | Secondary mechanical diagnostic |
| Local bundle/concentration/scan gates | 22 | 24 | Main partially screened diagnostic; holder SOL-balance gate unavailable |
| Full current gates with causal holder history | 1 | 0 | Too sparse to evaluate the requested fully screened population |

Saved holder history supplies only **11 timestamped rows for seven selected mints**. Historical screens use raw balances and the current 0.3 SOL / supply-concentration definitions, not the obsolete metadata description. No current RPC balance is substituted for a past balance; unavailable evidence stays unknown. A clear verdict lasts 30 seconds; the 40-second in-flight extension requires explicit historical evidence, absent here. Historical KOL whitelist evidence is also unavailable and never assumed.

As requested, rapid-pump-then-collapse labels are **hindsight diagnostics only**. Four of 240 launches fit that observed label; none of the 18 admitted current/local Central85 attempts did. No outcome was excluded with that label. Its absence does not establish organic trading or eliminate slower drains, linked holders or other manipulation.

## Funded replay comparison

All rows use a shared **15 SOL cash-funded ledger**, 0.50 SOL normal tickets, 0.25 SOL cooldown probes, no research position cap, and canonical all-family/global breakers held fixed. This holds risk controls constant; the saved deployed shadow breaker map contains only S4 and is not reproduced as the comparison's risk policy. Canonical entries/exits use the master registry. Current entries/exits use the frozen source audit. Normal fees are 0.001505 SOL per delivered buy/urgent sell; failed attempts pay 0.000505 SOL.

**Central80/85 are the headline placement estimates**. Intent seeds are fixed independently of outcomes. Both reactive buys and sells land after complete transactions, using the contract's same-slot mixture and historical intervening-group distribution. Fast is an optimistic bracket; slow is a pessimistic bracket. Scheduled-sell delivery is separately uncalibrated.

| Local-screen package | Fast SOL | **Central80 SOL** | **Central85 SOL** | Slow SOL |
|---|---:|---:|---:|---:|
| Canonical entries and exits | −1.013244023 | **−0.947499699** | **−0.942708969** | −0.913498567 |
| Current entries and exits | −1.045396720 | **−1.238073788** | **−1.238466812** | −1.357544916 |
| Current entries, canonical exit recipe | −0.852891601 | **−0.877678508** | **−0.878071532** | −1.051152205 |

These local-screen rows have zero unresolved inventory, so settled and combined marked PnL coincide. Canonical Central85 has 22 attempts, 17 closes and five guard failures. Current and matched-exit Central85 each have 18 attempts, 16 closes and two guard failures; current admission skips are two previously closed mints and four strategy pauses. Counts describe the shared funded portfolio, not the sum of independent strategy simulations.

The matched-exit row preserves current entry intents, the current 90% min-output guard and closed-mint policy. Canonical baseline uses its canonical guard. The matched row changes the exit recipe, including its canonical return denominator; it is not a bitwise isolation of one S4 threshold. It was added after inspecting results and is **development on this sample**, not independent confirmation.

| Sensitivity | Canonical/local SOL | Current/local SOL | Matched exits SOL |
|---|---:|---:|---:|
| Next-slot-tail stress | −0.810570485 | −1.308369435 | −0.943639079 |
| Central85, 0.002916 SOL delivered fees | −1.035148042 | −1.253761793 | −0.920282471 |
| Central85, scheduled sells +1 produced slot | −0.942708969 | −1.238466812 | Not separately run |
| Central85, scheduled sells +3 produced slots | −0.942708969 | −1.238466812 | Not separately run |

Scheduled sensitivities do not change these admissions/outcomes; that does not calibrate live scheduled delivery. Tail stress is not a headline estimate. Full raw off-screen results are retained in `FUNDED_RESULTS.json`; one current/off slow position remains open with settled −1.209583856 SOL, positive inventory value but lifecycle marked PnL −0.339568212 SOL, combined −1.549152068 SOL. Its last-valid mark provenance is retained in the raw funded row; it is not counted as a closed loss or assigned zero recovery as expected PnL.

## Entries versus exits

**Entry selection is the larger observed problem.** Current/local Central85 has one winning fill and 15 losing fills. **Twelve of those 15 losers never recorded a positive executable post-fill return**; the highest executable peak among losing fills was only about +5.40%. Moving a take-profit target cannot recover upside that was not observed. These peaks include executable fees and impact; an ideal hindsight peak remains an opportunity diagnostic rather than a deliverable sale.

| Family contribution, shared Central85 ledger | Current SOL | Same current entries, canonical exits SOL |
|---|---:|---:|
| S1 | −0.309984078 | −0.309984078 |
| S2 | −0.009883350 | −0.009883350 |
| S3 | −0.155738415 | −0.133538281 |
| S4 | −0.624596382 | −0.286401236 |
| S5 | −0.138264587 | −0.138264587 |

**Exits also add avoidable damage in this diagnostic.** The canonical exit recipe improves the matched portfolio by **0.360395280 SOL**, comprising S4 +0.338195146 and S3 +0.022200134, while remaining below zero. Current S4's delayed rejection permits more downside than the canonical early rejection. This supports testing earlier structural invalidation; it does not establish that the canonical recipe is optimal or sufficient.

Current S2/S4 reclaim waits for an ≥8% dip and then buys back at the original breakout level within 180 seconds. It is therefore buying recovered price, rather than filling at the discount. The current rule lacks a fresh-demand requirement at reclaim and a cap on overshoot. The next entry experiments should compare fresh independent demand, absorption at the shelf, and bounded reclaim price against the exact control, with failed reclaims retained. No threshold was tuned here and no improved entry was declared profitable.

S5 deserves a separate migration-aware experiment rather than general stop tightening. In the earlier shadow batch, two small S5 losers opened the AMM at approximately +19.8%/+24.9% lifecycle return but never reached the current half-sale threshold of **opening return +50 percentage points**. An earlier partial could protect gains but also surrender runner upside; it must be replayed with changed custody, subsequent volume and the profitable carried winner retained. This sample does not confirm that improvement.

## Coverage, engine fidelity and checks

All 240 continuation collections are complete through capture end. Preparation classifies **205 source-parity passes, 30 no-trade tapes, four source/custody failures and one completing-V3 coverage-required tape**. The prepared `curve_history_complete` count of 219 is not network coverage: custody repair dropped the metadata field on 18 passing tapes, while three other false flags belong to unresolved source histories. Collection files and `CURVE_CONTINUATION_AUDIT.json` establish collection completeness; source parity separately establishes replayability.

All seven authentic migrated pool histories were collected and passed AMM counterparty parity. Five migrations pass custody audit; four combined curve/AMM continuations are replay-ready. Remaining negative inventory/binding gaps and one V3 synthetic completion leg remain explicit coverage debt. Eligible pre-entry prefixes were checked; `UNMODELED_SIGNALS.json` is empty. No selected eligible signal was silently deleted to improve PnL. The migrated DYtVme S5 setup exits causally by its pre-migration invalidation at 1791630571, before historical migration at 1791630602, rather than being force-closed at graduation.

The approved `research/day_general_20261004` family and repaired `research/core_plan_audit_20261007/engine.py` supply integer quotes, complete-transaction order, changed reserves, independent timers, funded accounting and custody. Report-local extensions reproduce current exits and non-completing V3 trade variants. A source-completing V3 requires its authentic synthetic pool leg and is explicitly coverage-required, not fabricated as a curve fill or guard failure. This distinction follows the official [V3 trade documentation](https://github.com/pump-fun/pump-public-docs/blob/main/docs/instructions/TRADE_V3.md) and [synthetic migration documentation](https://github.com/pump-fun/pump-public-docs/blob/main/docs/SYNTHETIC_MIGRATION.md).

**44 meaningful tests passed**: current exits 27, signals 11, V3 3 and ledger/timing 3. The original approved engine remains unchanged; source and adapter hashes are saved. Raw main replay contains 1,264 evaluated results and zero errors; matched-exit replay also has zero errors.

Bug alarms were reviewed: 40 timer legs never land early; 1,412 exit legs never precede their trigger; no curve sale after completion and no exact-threshold fill were found. Delayed >30-attempt comparisons have failed guards. >50-trade closure/PF/win-rate alarms do not apply to these funded samples. Slower-outperforms-faster **did trigger in secondary comparisons**: inspected pairs show delays rejecting losing buys, changed admitted portfolios/breakers, and different landed prices. For example, canonical/off 88sTb loses −0.087479821 SOL fast but fails its slow guard for −0.000505 SOL. This explains the alarm without suggesting slower execution is preferable. The primary current/local bracket is fast > central > slow.

Potential understatement checks: central placement is used rather than tail stress; missing migration inventory is retained with marks/debt rather than zeroed; profitable partial/runner legs remain in funded accounting. None reverses the reported local Central85 result. Potential overstatement also remains: optimistic fast placement/low fees and uncalibrated inclusion assumptions.

Fidelity limits that matter: current S2/S5 detection retains one-shot baseline candidates; millisecond receipt time is approximated by whole-second chain time; current S5 opening anchor is the authentic whole opening transaction rather than its first delayed RPC snapshot; unquotable live retry is retained unresolved offline. Risk controls differ from the deployed S4-only map. These prevent calling this an exact replay of the running binary. No strategy, filter, live cap or runtime was changed.

Solami MCP history calls were blocked by automatic tool approval under the session's `never` approval policy. Authorized direct Solami history was unavailable for this collection; the complete receipt census/history used the project's authorized Alchemy fallback. No credentials are included in artifacts.

## Result card

```text
engine + git revision: approved day_general family + core_plan_audit engine, original engine SHA bb844aaf9b8c8fad050bc69b35b379b325cdd31a1f5a91482d93f420108a8976; HEAD 9dcff3f509b40d78d51921509ca09e79a2eafe63. Report-local adapters/hashes: FINAL_CODE_HASHES.json.
data: Oct10 06:00–Oct11 06:00 UTC creations, continuation to Oct11 07:34; 240/47,335 fixed creation-hash selection, 10/hour; all creation histories retained; source/continuation coverage distinctions above.
rules frozen before this data?: no. Canonical/source definitions frozen before evaluation, after historical day; no thresholds tuned. Matched-exit diagnostic added after inspection.
look count: 3 entry/exit packages; original 2 packages × 3 screen scopes plus 1 matched local scope = 7 comparison cells. Execution/fee sensitivities disclosed; no best-threshold search.
placement fast / central80 / central85 / slow, all-attempt funded SOL:
  current/local: −1.045396720 / −1.238073788 / −1.238466812 / −1.357544916.
  canonical/local: −1.013244023 / −0.947499699 / −0.942708969 / −0.913498567.
  matched/local: −0.852891601 / −0.877678508 / −0.878071532 / −1.051152205.
stress current/local: tail −1.308369435; high-fee Central85 −1.253761793; scheduled +1/+3 slots both −1.238466812. Other packages in table.
Central85 attempts / closed / failed / unresolved:
  current/local 18 / 16 / 2 / 0; canonical/local 22 / 17 / 5 / 0; matched/local 18 / 16 / 2 / 0.
  full current screens: 0 eligible/admitted, not a zero-PnL profitability result. Full canonical: 1 close, Central85 −0.053736895 SOL.
settled + open marked = combined current/local: −1.238466812 + 0 = −1.238466812 SOL; no unavailable marks. Zero-recovery bound equals settled for these closed local portfolios.
max settled drawdown current/local: 1.334006749 SOL; largest winner +0.095539937; without largest −1.334006749 SOL. Canonical/local DD 0.942708969; largest +0.058418744; without largest −1.001127713 SOL.
bug alarms: all pass/applicability reviewed; slower-better triggered, paired guard/admission/price differences inspected and explained in BUG_ALARMS.json. No early timer/trigger, exact-threshold or completed-curve sell defects found.
verdict, all candidate packages: undetermined, retrospective (small day sample; full-screen population untested). Resolved local-screen central numbers are below zero; no general claim about all non-rug coins or future profitability.
what would change verdict: broad causal historical holder-screen evidence, remaining migration/V3 custody coverage, reconciled actual fill placement, and frozen controls/entry and exit experiments on later untouched 14–21 days.
```
