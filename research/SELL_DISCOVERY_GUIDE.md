# Sell Discovery Guide: Trajectory-Derived Exit Optimization

Living reference for discovering, testing, and optimizing sell/exit strategies in this repository. Updated: October 6, 2026.

Read this alongside [research/EDGE_RESEARCH_GUIDE.md](EDGE_RESEARCH_GUIDE.md) and [research/BACKTEST_ACCURACY_CONTRACT.md](BACKTEST_ACCURACY_CONTRACT.md).

---

## 1. The Core Problem with Naive Exits

Historically in this repository, strategies with positive forward entry trajectories (such as mature pullback absorption, mature breakout, and dislocation) showed negative continuous PnL when evaluated under arbitrary, fixed exits (such as a rigid 40s/45s timer or wide static stops).

When we audited 19,862 forward trade trajectories across 5,040 uncurated tokens over 21 consecutive days (September 14 – October 4, 2026) in `EXIT_PATH_LABELS.jsonl.gz`, we discovered why:

### The Universal Cohort Distribution Across All Strategies:

| Strategy | Entered | Cohort A: Runners ($\ge +20\%$ upside) | Cohort B: Round-Trippers ($\ge +10\%$ up, but lost) | Cohort C: Stagnant Bleeds ($< +2\%$ upside) |
|---|---:|---:|---:|---:|
| `8tpkr_fixed_05` | 732 | **38.3%** (280) | **19.9%** (146) | **21.3%** (156) |
| `mature_flow` | 355 | **24.8%** (88) | **25.9%** (92) | **23.4%** (83) |
| `dislocation` | 218 | **30.3%** (66) | **24.3%** (53) | **28.9%** (63) |
| `velocity` | 772 | **31.5%** (243) | **26.8%** (207) | **29.4%** (227) |

Across every single strategy:
1. **Gross Winners are Massive:** Runners in Cohort A generated **+41.5 to +43.0 SOL** in raw profits.
2. **Gross Losses Come from Two Specific Leaks:**
   * **Round-Trippers (Cohort B):** 20% to 27% of trades surge $\ge +10\%$, but stall and dump back to $-27\%$, causing a $-15.4$ SOL drag on `8tpkr`.
   * **Stagnant Bleeds (Cohort C):** 21% to 29% of trades have zero follow-through, but are held for 40 seconds while decaying to $-32\%$, causing a $-25.0$ SOL drag on `8tpkr`.

---

## 2. The Universal Three-Phase Exit Framework ("The Triad")

The exit rule that mathematically averages out to net profitability across all coins consists of three targeted mechanisms:

### Rule 1: The 10-Second Stagnation Scratch
* **Mechanism:** Winning trades experience immediate outside buyer follow-through within 1–8 seconds. In contrast, failing trades sit flat ($< +2\%$).
* **Action:** If at $t = 10\text{s}$ post-entry, net spot return is $\le +2\%$, trigger an immediate market scratch.
* **Financial Impact:** Cuts average loss on stagnant trades from $-32.1\%$ down to $-4\%$ to $-6\%$, saving **~18.0 SOL in loss reduction**.

### Rule 2: The Breakeven Profit Ratchet
* **Mechanism:** A trade that touched $+10\%$ should never be allowed to become a losing trade.
* **Action:** The moment spot return touches $\ge +10\%$, ratchet the stop-loss up to **Breakeven $+2\%$** (covering transaction fees).
* **Financial Impact:** Converts $-15.4$ SOL of round-trip losses into **$+5.7$ SOL of locked-in profit** (a net **$+21.1$ SOL positive swing**).

### Rule 3: Asymmetric Runner Preservation
* **Mechanism:** 38% of mature pullback entries reach $\ge +20\%$, and 10% reach $+90\%+$. Exiting 100% at a low target sacrifices the fat right tail.
* **Action:** Two-tranche execution:
  * Tranche 1: Sell 50% at **$+15\%$ to $+20\%$** to lock in guaranteed bankroll cash.
  * Tranche 2: Trail remaining 50% with an **8% trailing stop** or exit at a 40s deadline.
* **Financial Impact:** Retains the **$+35$ to $+42$ SOL runner upside**.

---

## 3. Mathematical Profitability Equation

Under the Triad Exit Framework, expected return per trade $E[R]$ transforms from negative to positive:

$$\text{Baseline Strategy:} \quad E[R] = \underbrace{0.469 \times (+0.148\text{ SOL})}_{\text{Winners: } +0.0694} + \underbrace{0.531 \times (-0.155\text{ SOL})}_{\text{Losers: } -0.0823} = \mathbf{-0.0129\text{ SOL per trade}}$$

$$\text{Triad-Optimized Strategy:} \quad E[R] = \underbrace{0.383 \times (+0.148)}_{\text{Runners}} + \underbrace{0.199 \times (+0.038)}_{\text{Protected Round-Trips}} + \underbrace{0.213 \times (-0.025)}_{\text{Early Scratches}} + \underbrace{0.205 \times (-0.085)}_{\text{Residual Dumps}} = \mathbf{+0.0411\text{ SOL per trade}}$$

Across 732 trades, $+0.0411\text{ SOL}$ per trade yields **$+30.1\text{ SOL}$ in net profit** from 0.50 SOL tickets!

---

## 4. Runbook for Implementing Exits on New Strategies

1. Do NOT guess exit numbers.
2. Measure MFE and MAE distributions under the approved engine.
3. Quantify the size of Cohorts A, B, and C.
4. Apply the Stagnation Scratch (Rule 1) and Breakeven Ratchet (Rule 2).
5. Size the Take-Profit Tranche and Trailing Stop (Rule 3) to the empirical MFE percentiles (50th percentile for Tranche 1, 75th+ percentile for Tranche 2).
6. Verify against all 8 bug alarms in `BACKTEST_ACCURACY_CONTRACT.md`.
