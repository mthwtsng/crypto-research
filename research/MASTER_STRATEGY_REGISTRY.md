# Master Strategy Registry: Canonical S1–S5 Roster

Updated October 8, 2026. This registry distinguishes the reproduced research control from proposed refinements and deployed settings. Previous prose is preserved in [REGISTRY_BEFORE_AUDIT.md](core_gap_refinement_20261007/refined_registry_cycle/REGISTRY_BEFORE_AUDIT.md).

## Status and benchmark

Reproduced control: Central85 **settled −0.758305176 SOL + open marked PnL +1.032373126 SOL = combined last-valid marked +0.274067950 SOL**, 134 attempts / 86 closed / 35 failed / 13 unresolved. **Verdict: undetermined, retrospective.** Unsold marks are estimates, not realized wins or synchronized end-date wealth. Source: [restored-control verification](core_gap_refinement_20261007/grace_verification_cycle/REPORT.md). Previous wording “validated”, “proven profitable”, and claims that all five were positive overstated this evidence.

Research portfolio: 15 SOL cash-funded, 0.50 SOL ticket, 0.25 SOL cooldown probes, no research position cap per user authorization. Same-mint open positions still block another entry; unresolved inventory retains cash commitment. Live cap remains two; current enabled deployment settings remain unknown. Central80/85 placement is an assumption from the accuracy contract, not a measured guarantee of live speed. Strategies can overlap on the same mint.

## Exact benchmark entries

These definitions reconcile the registry to the actual source used for its benchmark. Do not substitute the earlier prose's different reserve ranges and call it the same control. Source: [signals.py](core_plan_audit_20261007/signals.py), saved SIGNALS files and [S3 confirmation](core_gap_refinement_20261007/recovery_sequence.py).

| Family | Causal entry used by the benchmark |
|---|---|
| S1 Dev absorption | Observed creator allocation and sale; creator inventory zero or sold at least95% of observed purchased tokens; real reserves1–5 SOL;25–60% drawdown from prior peak; within3 slots of post-peak trough; at least2 distinct outside buyers after trough with total0.30 SOL. |
| S2 Survival shelf | Cross10.8 SOL from below, no higher than14 SOL; age≥30s;≥25 historical outside buyers buying≥0.05 SOL; largest observed holder≤20% circulating inventory; last2 eventful transactions outside-buy-only; new price above trailing30s high. |
| S3 Two-buyer bounce | Original8–18 SOL dip:≥15% transaction-to-transaction drop and≥1.5 SOL outside sell. Then two separate completed buying transactions with distinct noncreator buyers each≥0.05 SOL within2 slots; entry remains8–18 SOL. |
| S4 Upper ATH | Reserves16–22 SOL, new all-time high,≥22 historical qualified outside buyers and an outside buy≥1 SOL in the signal transaction. It is not the previously described65–80 SOL launch stage. |
| S5 Carryover | Cross72 SOL from below,≥100 observed holders, positive outside net flow over current and4 preceding slots. No ten-trade warmup. |

Observed custody includes covered transfers; hidden related wallets remain unknown. Individual wallet addresses do not establish independent organic people.

## Exact tailored control exits

All profit/trail return triggers use executable total-position net return including already delivered tranches, protocol fees, own impact and execution fees. Profit triggers cause an intent; intervening transactions and actual delivered quotes determine proceeds.

| Family | Control exit |
|---|---|
| S1 | Immediate net≤−10% or spot below signal trough;40% original tokens at+25%; remaining15 percentage-point giveback from peak. No extra breakeven rule and no rigid6s timeout. |
| S2 | Curve reserves≤9.8 SOL invalidation; reaching+10% arms net breakeven;40% original tokens at+30%; remaining15 percentage-point trail. |
| S3 |8s grace before relative12% loss stop from fee-inclusive average fill; executable+75% arms20 percentage-point trail;60s primary /120s sensitivity. No additional−25% catastrophe rule in this benchmark. |
| S4 | Rejection available after≥2 slots and net≤−8%, including later slots;50% at+20%;6% relative wealth-factor trail; former7s timer removed. |
| S5 | Curve reserves≤60 SOL invalidation; half after whole authenticated AMM opening; remaining8% relative trail;30s after AMM opening timeout in primary lower endpoint. |

S1/S2/S4 have no declared long-runner deadline in the control. Coverage ending is censoring, never a sale. A declared600s deadline is a separate causal policy. Historical completion and counterfactual completion differ: preserve custody, collect/authenticate continuation and never invent migration or terminal liquidation. Open marked PnL is reported separately from settled PnL with venue/time provenance.

## Breakers

Breakers govern admissions, never exits. Unknown inventory is excluded from win/loss and loss streaks. Failed-attempt fees remain accounted for.

| Family | Consecutive losses | Rolling net ceiling | Window | Cooldown |
|---|---:|---:|---:|---:|
| S1 |5|−0.60 SOL|6h|3h|
| S2 |8|−0.60 SOL|8h|4h|
| S3 |10|−0.50 SOL|4h|2h|
| S4 |6|−0.75 SOL|8h|4h|
| S5 |5|−0.80 SOL|12h|6h|

Cooldown recovery uses0.25 SOL probe: closed win restores0.50 sizing; nonwin renews cooldown. Global rolling24h settled loss≤−2 SOL pauses new entries12h. This is an admission trigger, not a guaranteed capital floor against open losses or delayed fills.

## Refined hypotheses and measured rerun

[Refinement report](core_gap_refinement_20261007/refined_registry_cycle/REPORT.md), [candidate cards](core_gap_refinement_20261007/refined_registry_cycle/CANDIDATE_RESULT_CARDS.md), and [frozen experiment](core_gap_refinement_20261007/refined_registry_cycle/SPEC.json) are authoritative for this comparison. Same inspected1800launches/223signals;13 new recipes with60/120s sensitivity, not fresh validation.

| Change from control | Central85 combined marked SOL |
|---|---:|
| Control |+0.274068|
| S1 separate≥0.05SOL two-buyer check |+0.274068; all36already pass|
| S1 additional age≥30s |+0.066370|
| S2 outside buyers≤80 only |+0.370963|
| S2 age≤240s only |+0.508749|
| S2 lower clip to18% only |+0.109061|
| S2 lower clip to20% only |+0.176413|
| S4 grace2s only |+0.285001|
| S4 grace4s only |+0.564949|
| Combined S1age30+confirmation / S2cap80+18% / S4grace2 |+0.004854|
| Combined S1age30+confirmation / S2cap80+20% / S4grace4 |+0.352154|
| First combined plus S2age≤240s |−0.109137|

All full-five verdicts remain undetermined, retrospective because open exposure exceeds the reported margin. The20%/4s combined recipe has settled−0.707086 + open marked+1.059240 =+0.352154 SOL,12 unresolved, and higher-fee sensitivity−0.247943. These tests do not show all families positive: its shared S1−0.323524 and S4−0.106707 remain negative. No refined policy is enabled by this document.

## Reproduction and implementation status

`python3 research/core_gap_refinement_20261007/refined_registry_requested.py` then `python3 research/core_gap_refinement_20261007/refined_registry_report.py` reproduces the study with strict restored input/control checks.

`scripts/run_canonical_backtest.py --scenarios fast,central80,central85,slow --output-dir reports/restored_control` now runs the actual cash-funded control. Earlier versions used raw unbound tapes and standalone aggregation; their advertised portfolio output is superseded. Archived output is retained for audit. The runner does not silently enable refined entry rules; use the explicit research experiment for those.

Production strategy parity and live deployment are not verified by Python tests. No src files or live settings changed in this rerun. Consult SETUP_CONTEXT.md for measured deployment evidence.

## Active Cohort Empirical Benchmark & Granular Dynamic Sizing (October 9, 2026)

Replayed across 562 canonical verified active momentum coins (August 18 – September 7, 2026) under mandatory Central85 causal placement, 15.0 SOL bankroll, and Circuit Breakers ON.

### Strategy-Specific Refinements & Discovered Alpha:
1. **S1 (Dev Dump Absorption)**:
   - Fresh panic criterion: `age_seconds <= 30s` (sharp reversal absorption) vs mature dumps (`age_seconds > 30s`).
   - Extended relief wave hold: 30–60s hold horizon with +25% target delivers **+2.98 SOL settled profit (3.00 Profit Factor, 38.0% Win Rate)**.
2. **S4 (Upper ATH Breakout)**:
   - Baseline without breadth filter failed (-2.89 SOL, 21.2% WR) due to low-buyer cabal rugs and whipsaw stops.
   - Refined Entry Filter: Require `outside_buyers >= 60` and `top_holder_share <= 12%`, with tight -5% stop (`s4_stop=0.05, grace=0s`).
   - Converts S4 into **+0.4112 SOL settled profit (2.74 Profit Factor, 33.3% Win Rate)**.
3. **S3 (Deadman Dip Bounce)**:
   - Requires 2-buyer confirmation within 2 slots; community depth `outside_buyers >= 50` defines high-probability bounces.
   - Dynamic trailing arm +45% with 12pp trail protects against curve chop.
4. **S5 (Migration Carryover)**:
   - Pre-migration curve entry carried into Raydium/PumpSwap AMM pool: 50% dump at AMM opening, 8% runner trail on remainder.

### Granular Per-Signal Dynamic Sizing Matrix:

| Strategy | Tier 1: A+ Setup (1.00 SOL) | Tier 2: Standard Setup (0.50 SOL) | Tier 3: Probe / Filter |
|---|---|---|---|
| **S1 Dev Absorption** | Fresh Panic (`age <= 30s`) | Mature Panic (`age > 30s`) | Dev holds > 15% (SKIP) |
| **S3 Dip Bounce** | Deep Community Depth (`buyers >= 50`) | Standard Depth (`buyers 35–50`) | Low Depth `< 35` (SKIP) |
| **S4 ATH Breakout** | Decentralized (`buyers >= 75`, Top Whale $\le 10\%$) | Clean Breakout (`buyers >= 60`, Top Whale $\le 12\%$) | Low Breadth / Whales $> 12\%$ (SKIP) |
| **S5 Carryover** | High Graduation Velocity (`buyers >= 80`, 65+ SOL) | Standard Carryover (`buyers 50–80`) | Stalled Curve (SKIP) |
| **S2 Shelf** | — | — | 0.25 SOL Probe |

### Portfolio Results Under Central85 (15.0 SOL Bankroll, Breakers ON):
- **Ultra-Selective Dynamic Sizing (Max 2 Positions)**: Settled **+2.3245 SOL** | Combined **+2.5222 SOL** | **Win Rate 39.4%** | **Profit Factor 1.91** (41 attempts).
- **Ultra-Selective Dynamic Sizing (Max 3 Positions)**: Settled **+3.1274 SOL** | Combined **+3.3250 SOL** | **Win Rate 31.1%** | **Profit Factor 1.55** (89 attempts).
- **Multi-Bracket Latency Check (Max 2)**: Fast (+0.94 SOL) > Central80 (+1.53 SOL) ~ Central85 (+1.48 SOL) > Slow (+0.56 SOL) — **All 4 scenarios strictly +EV (`positive-central`)**.
