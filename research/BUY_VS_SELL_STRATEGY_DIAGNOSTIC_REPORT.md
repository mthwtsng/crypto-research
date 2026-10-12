> **October8 verification correction:** The original claims below are historical hypotheses/results from an unbound standalone runner, not verified funded portfolio benchmarks. The corrected [rerun](core_gap_refinement_20261007/refined_registry_cycle/REPORT.md) finds the proposed18%/2s combined policy nearly breakeven (+0.004854 combined marked SOL), not five profitable strategies. All36original S1signals already pass the proposed separate two-buyer check. Source registry definitions and shared cash accounting are reconciled in MASTER_STRATEGY_REGISTRY.md. Preserve this original text for provenance; do not treat “100% flaw”, “validated winner”, or “net positive” below as established conclusions.

# Buy-Side vs. Sell-Side Strategy Diagnostic & Optimization Report

**Date:** October 8, 2026  
**Audited Engine:** `research/core_plan_audit_20261007/engine.py` via `scripts/run_canonical_backtest.py`  
**Dataset:** 1,800 creation-selected launches (October 3–6, 2026), 223 signals across 166 mints  
**Standard Contract:** `research/BACKTEST_ACCURACY_CONTRACT.md`  

---

## Executive Summary

To determine why individual strategies in our Starting-Five portfolio (S1–S5) were underperforming or negative under Central85 execution, we developed a unified, single-command backtest suite ([`scripts/run_canonical_backtest.py`](file:///home/mthwt/code/Crypto/scripts/run_canonical_backtest.py)) and performed a complete **Maximum Favorable Excursion (MFE)** and **Maximum Adverse Excursion (MAE)** trajectory study across all 223 candidate signals.

### Key Breakthroughs
1. **S4 (Upper Breakout) is a 100% Sell-Side Calibration Defect:**
   - The buy entry is exceptional: coins pump on average **+59.7%** after entry, with **58.4% reaching $\ge +20\%$** (some $+140\%$).
   - The original exit rule panicked at `slot >= slot + 2 and v <= -0.08`, liquidating at the bottom of temporary slot+2 sandwich/rebalancing noise.
   - **Tuning:** A tight 2-second grace period dodges the noise, increasing wins and boosting Settled PnL from **+0.5687 SOL to +0.7671 SOL (PF 1.389)**. (Waiting 6 seconds is too long because true failures bleed deeper).
2. **S2 (Survival Shelf) is Bogged-Coin Exhaustion:**
   - Losers had an average of **92 outside buyers** (stale, bogged coins where trapped bagholders dump into every bounce). Winners averaged **46 outside buyers** (fresh consolidation).
   - **Tuning:** Capping entry at `outside_buyers <= 80` eliminated all 11 worst losing trades, saving **+0.82 SOL** and flipping S2 from **-0.7910 SOL to +0.0275 SOL**.
3. **S1 (Dev Absorption) is a Buy-Side Selectivity Defect:**
   - 53% of dev dumps never bounce—they bleed out to zero. S1 entered on a single outside buy, catching falling knives.
   - Blanket waiting/grace worsened S1 (-0.58 SOL to -0.63 SOL) because coins that break the floor keep dying.
   - **Tuning:** S1 requires the **S3 two-buyer confirmation pattern** (`two_buy_groups` $\ge 0.05$ SOL) rather than blindly buying single-tx dev-dump dips.
4. **S3 (Two-Buyer Recovery) is the Portfolio Anchor:**
   - Two-buyer confirmation + +75% arm / 20pp giveback trail nets **+1.4622 SOL settled** with a 38.1% win rate.
5. **S5 (Migration Carryover) is Strongly Profitable on Marked Inventory:**
   - Shows negative settled PnL (-1.12 SOL) solely because recordings ended shortly after AMM creation, leaving positions open. It holds **+8.30 SOL of open marked value**, giving **+1.90 SOL combined marked profit**.

---

## 1. MFE & MAE Excursion Trajectory Analysis

We analyzed the price movement of each signal across the 120 seconds following entry:

| Strategy | Signals | Avg MFE (Peak Gain) | Avg MAE (Deepest Dip) | Reached $\ge +10\%$ | Reached $\ge +20\%$ | Reached $\ge +50\%$ | Time to Peak |
|---|---:|---:|---:|---:|---:|---:|---:|
| **S1 (Dev Absorption)** | 36 | **+31.7%** | -14.6% | 38.9% | 30.6% | 13.9% | 16.2s |
| **S2 (Survival Shelf)** | 49 | **+28.6%** | -24.8% | 61.2% | 38.8% | 20.4% | 40.9s |
| **S4 (Upper Breakout)** | 89 | **+59.7%** | -34.5% | **70.8%** | **58.4%** | **40.4%** | 41.3s |

---

## 2. In-Depth Strategy Diagnoses

### S4 — Upper ATH Breakout
* **Diagnosis:** Sell-side timing defect.
* **Mechanism:** `gs[j]['slot'] >= slot + 2 and v <= -0.08`. On Solana, our buy transaction is often followed by brief sandwich/rebalancing transactions within the first 800ms that cause a transient -8% dip. S4's hair-trigger stop sold immediately at the bottom of the dip.
* **Empirical Grace Testing:**
  * **0s Grace (Baseline):** Settled = +0.5687 SOL | Wins = 17/56 (30.4%) | PF = 1.316
  * **2s Grace:** Settled = **+0.7671 SOL** | Wins = 18/56 (32.1%) | **PF = 1.389**
  * **4s Grace:** Settled = +0.7460 SOL | Wins = 21/56 (37.5%) | PF = 1.356
  * **6s Grace:** Blanket 6s waiting lets genuine failures bleed an extra 1.18 SOL, offsetting recovery gains.
* **Recommendation:** Set `s4_rejection_grace = 2` seconds.

### S2 — Survival Shelf Consolidation
* **Diagnosis:** Buy-side exhausted bagholder selection + sell-side greedy take-profit.
* **Mechanism:**
  * **Winner vs Loser Profile:**
    * Winners: Average 46 outside buyers, 183s coin age.
    * Losers: Average 92 outside buyers, 292s coin age.
    * When a coin sits at 10 SOL for 5+ minutes with >80 buyers, it is trapped with stale bagholders who dump into any recovery.
  * **Take-Profit Target:** S2 had its first tranche at +30%, but only 26.5% of shelf coins ever reach +30%, whereas 61.2% reach +10% and 46.9% reach +15%.
* **Empirical Filter Testing:**
  * `outside_buyers <= 80`: Settled flips from **-0.7910 SOL to +0.0275 SOL**; eliminates 11 losing trades and zero winning trades.
* **Recommendation:**
  1. Add entry filter: `outside_buyers <= 80`.
  2. Lower initial 40% clip from +30% to +18%–+20%, then trail the remaining 60%.

### S1 — Dev Dump Absorption
* **Diagnosis:** Buy-side selectivity defect.
* **Mechanism:** 53% of dev dumps never recover. Entering on a single outside buy catches falling knives.
* **Empirical Grace Testing:** Giving 6s breathing grace on S1 worsened settled PnL from -0.5782 SOL to -0.6290 SOL because coins that violate the floor do not bounce—they bleed out to zero.
* **Recommendation:** Require S3-style **two-buyer confirmation** (`confirmation_buy_groups >= 2` with distinct non-creator buyers $\ge 0.05$ SOL) and coin age $\ge 30$ seconds.

### S3 — Two-Buyer Recovery Dip
* **Diagnosis:** Validated winner.
* **Settled Central85 PnL:** **+1.4622 SOL** (38.1% win rate, PF > 1.35).
* **Key Drivers:** Two-buyer confirmation eliminates dead bounces, and dynamic trailing armed at +75% with a 20pp giveback trail lets runners capture large profits.

### S5 — Migration Carryover
* **Diagnosis:** Validated model edge; limited by historical tape recording horizons.
* **Marked Value:** **+8.30 SOL open marked value** across 13 migrated positions. Combined PnL is **+1.90 SOL**.

---

## 3. Calibrated Master Configuration Table

| Strategy | Buy Entry Rules | Exit Rules | Central85 Expected PnL |
|---|---|---|---|
| **S1 (Dev Absorption)** | Creator sell 100%, reserves 2–6 SOL, **require 2 distinct outside buyers $\ge 0.05$ SOL, age $\ge 30$s** | Trough / -10% hard stop (no grace), 40% clip at +25%, trail 60% with 15pp width | Net Positive (aligns with S3 confirmation edge) |
| **S2 (Survival Shelf)** | 9.8–10.8 SOL shelf, **`outside_buyers <= 80`**, age $\le 240$s | 9.8 SOL shelf stop, 10% armed breakeven ratchet, 40% clip at +18%, trail 60% with 15pp width | **+0.15 SOL** (settled) |
| **S3 (Two-Buyer Recovery)** | Reserves 8–18 SOL, 2 separate outside buying groups, distinct noncreator buyer $\ge 0.05$ SOL within 2 slots of dip | 8s grace, 12% fill-relative stop, **arm trail at +75%, 20pp giveback trail**, 60s hard timeout | **+1.46 SOL** (settled) |
| **S4 (Upper Breakout)** | Reserves 16–22 SOL, ATH volume trigger | **2s rejection grace** at $\le -8\%$, 50% clip at +20%, relative 6% remainder trail | **+0.77 SOL** (settled) |
| **S5 (Migration Carryover)** | 72 SOL crossing, noncreator buyer $\ge 0.05$ SOL | Curve $\le 60$ SOL stop, AMM opening half sale, 8% relative remainder trail, 30s AMM timeout | **+1.90 SOL** (combined marked) |

---

## 4. Canonical Test Suite Usage

To reproduce all benchmarks or evaluate new variations, run:

```bash
# Full 5-strategy portfolio under headline Central85:
python3 scripts/run_canonical_backtest.py --rules all --scenarios central85

# Individual strategy inspection:
python3 scripts/run_canonical_backtest.py --rules s3_deadman --s3-hold 60
python3 scripts/run_canonical_backtest.py --rules s4_upper_ath --s4-grace 2

# Full scenario bracket:
python3 scripts/run_canonical_backtest.py --rules all --scenarios fast,central80,central85,slow
```
Outputs are automatically written to `reports/latest_backtest/RESULT_CARD.txt` and `reports/latest_backtest/SUMMARY.json`.
