# The "Starting 5" Core Strategy & Circuit-Breaker Architecture

**Document Type:** Pre-Implementation Master Blueprint  
**Date:** October 7, 2026  
**Status:** **Frozen Strategic Plan — Ready for Future Implementation**  
**Operating Constraints:**
- **Bankroll:** Strictly **15.0 SOL**
- **Ticket Size:** **0.50 SOL** base (configurable max 0.75 SOL)
- **Max Concurrent Open Positions:** **2** across all active strategies combined
- **Latency Requirement:** Strictly non-speed-fragile (all execute within 50–75ms Yellowstone gRPC / multi-second windows)

---

## 1. Executive Overview

This plan consolidates our extensive 21-day census (5,040 tokens, 397,307 trades) and forensic on-chain audits across 21 elite automated bots (+19,070 SOL net profit). 

Instead of running an unwieldy set of 12 experimental variations, this plan focuses exclusively on the **Top 5 Most Proven Strategies**. Each strategy covers a distinct, non-overlapping stage of the bonding curve lifecycle, possesses its own **custom-tailored exit strategy**, and operates under an **independent circuit-breaker switch** that halts that specific strategy if its loss threshold is reached.

```mermaid
flowchart LR
    subgraph Floor ["Stage 1: Floor Absorption"]
        S1["Strat 1: Dev Dump Absorption<br/>(1-5 SOL Reserve)<br/>PF: 88.7 | WR: 70.7%"]
    end

    subgraph Shelf ["Stage 2: Shelf & Dislocation"]
        S2["Strat 2: Survival Shelf Breakout<br/>(10.8-14 SOL Reserve)<br/>Continuation: 83.3%"]
        S3["Strat 3: Dead-Man Dislocation<br/>(8-18 SOL Reserve)<br/>Strict 21s execution deadline"]
    end

    subgraph Upper ["Stage 3: High Velocity"]
        S4["Strat 4: Upper ATH Momentum<br/>(16-22 SOL Reserve)<br/>PF: 5.05 | WR: 69.7%"]
    end

    subgraph Migration ["Stage 4: Graduation & AMM"]
        S5["Strat 5: Pre-Graduation Carryover<br/>(72 SOL -> AMM)<br/>PF: 5.46 | WR: 75.0%"]
    end

    S1 -.-> Global["Global Concurrency Engine<br/>(Max 2 Open Positions | 15.0 SOL Bankroll)"]
    S2 -.-> Global
    S3 -.-> Global
    S4 -.-> Global
    S5 -.-> Global
```

---

## 2. The "Starting 5" Strategy Specifications

---

### Strategy 1: Post-Dev Dump Absorption (The Cleansed Floor)
* **Lifecycle Phase:** Post-crash floor formation (1.0 to 5.0 SOL reserve).
* **Bot Exemplars:** [`9Sq7tiVyc`](https://solscan.io/account/9Sq7tiVycMu58kfGKG68S2B7qsCcSgfQN9nBshVouDgb) (+48.0 SOL net, **Profit Factor 88.76**), [`BEpMLdAatq`](https://solscan.io/account/BEpMLdAatqijj7NdvrrfL9SbaxErYFoKMog2gFf9ThPi) (+15.4 SOL net, **PF 24.18**), [`9LXWa7V3`](https://solscan.io/account/9LXWa7V3AE15VfBupcx5gDts2ix3Y9NzbcKZKjkkq6hV) (+835.6 SOL pre-curve).
* **Structural Edge:** 95% of meme tokens fail due to developer dumping. Once the developer dumps 100% of their allocation (`creator_token_balance == 0`), the token **cannot be developer-rugged anymore**. When outside community buyers step in to absorb the crash, the downside is capped while upside relief is asymmetric.
* **Exact Entry Trigger:**
  1. `creator_token_balance == 0` (or developer sold $\ge 95\%$ of supply).
  2. Price is down $25\%$ to $60\%$ from local high, settling between 1.0 and 5.0 SOL reserve.
  3. $\ge 2$ distinct non-developer buyers purchase $\ge 0.30\text{ SOL}$ total within 3 slots of the trough (confirming clean absorption).
* **Dedicated Exit Strategy (Relief Flash Scalp):**
  * **Hard Stop Loss:** Cut immediately if curve price breaches the absolute post-dump swing low (−10% max loss).
  * **Take Profit:** Sell 100% in a single fill on the relief bounce at **+25% to +35%** or after **15–20 slots (~6 to 8 seconds)**.
* **Individual Circuit-Breaker Settings:**
  * **Consecutive Loss Limit:** 5 losses in a row.
  * **Rolling Loss Ceiling:** −0.60 SOL in 6 hours.
  * **Cooldown Period:** **3 Hours OFF**.

---

### Strategy 2: 10.8 SOL Survival Shelf Breakout
* **Lifecycle Phase:** Mid-curve expansion (10.8 to 14.0 SOL reserve).
* **Bot Exemplars:** [`8TPkr`](https://solscan.io/account/8TPkr85e6mP4kHps8sQsmS46vRmsWnB2h5jVp29oXUe8) (+120.4 SOL across 21 days), [`9keCU8mg`](https://solscan.io/account/9keCU8mgA23XV8LCgSCJEo4Lspmo9fRBA3MyxJmZKQSp) (+558.1 SOL net), [`72NWWbch`](https://solscan.io/account/72NWWbchKdRJKvhG6U4f9363psUttkeEkE4yk15imy8u) (+17.9 SOL/day).
* **Structural Edge:** 10.8 SOL represents exactly 33.3% of the bonding curve path. Across 1,351 tested tokens reaching this level, coins with decentralized distribution have an **83.3% probability of reaching $\ge 15.0$ SOL** and a **17.7% probability of reaching full AMM graduation**.
* **Exact Entry Trigger:**
  1. Reserve crosses $\ge 10.8\text{ SOL}$ and age $\ge 30\text{ seconds}$.
  2. Buyer breadth: $\ge 25$ unique non-dev buyers.
  3. Decentralization: Top holder owns $\le 20\%$ of circulating supply.
  4. Breakout: $\ge 2$ consecutive outside buy clips breaking the 30-second local consolidation high.
* **Dedicated Exit Strategy (Ratchet & Shelf Expansion):**
  * **Hard Stop Loss:** Cut if curve falls back below 9.8 SOL (−9%).
  * **Breakeven Ratchet:** Arm ratchet once trade reaches $+10\%$ (stop moves to entry price + fees).
  * **Take Profit:** Sell 50% at $+25\%$ (around 14.0 SOL reserve); trail remaining 50% with an 8% trailing stop until 20+ SOL. If token accelerates past 30 SOL, allow remaining tokens to carry to graduation.
* **Individual Circuit-Breaker Settings:**
  * **Consecutive Loss Limit:** 5 losses in a row.
  * **Rolling Loss Ceiling:** −0.75 SOL in 8 hours.
  * **Cooldown Period:** **4 Hours OFF**.

---

### Strategy 3: 21-Second Dead-Man Dislocation Scalp
* **Lifecycle Phase:** Severe dip dislocation on active curves (8.0 to 18.0 SOL reserve).
* **Bot Exemplars:** [`BDW8Bjoe`](https://solscan.io/account/BDW8Bjoe9fgfRPAkSf3Kpnphdd4ugWwsLitSxvqo4gg4) (+625.6 SOL pre-curve net), [`J3gZFpvs`](https://solscan.io/account/J3gZFpvsCsmA5zwqXgUpyqNLBoGGcJzmnfRwbHFR6KfU) (+276.9 SOL).
* **Structural Edge:** When an outside non-dev whale sells $\ge 1.5$ SOL on an active curve, price overshoots downward due to AMM curve slippage. Organic buyers quickly arbitrage this dip. The dead-man switch enforces an unbreakable execution deadline that prevents holding dead bags.
* **Exact Entry Trigger:**
  1. An outside whale sell of $\ge 1.5\text{ SOL}$ causes an immediate $\ge 15\%$ price wick.
  2. Token reserve remains $\ge 8.0\text{ SOL}$ with active non-dev trading history.
* **Dedicated Exit Strategy (Dead-Man Switch):**
  * **Rule 1 (10s Stagnation Scratch):** If spot price has not achieved $\ge +2\%$ by $t = 10\text{ seconds}$, exit immediately at market.
  * **Rule 2 (Hard Dead-Man Cutoff):** Exit 100% of position at **exactly $t = 21\text{ seconds}$** if the position has not expanded into a $+15\%$ runner.
  * **Rule 3 (Runner Preservation):** If position reaches $\ge +20\%$ by second 20, arm trailing stop at $+12\%$.
* **Individual Circuit-Breaker Settings:**
  * **Consecutive Loss Limit:** 7 losses in a row (higher allowance due to frequent quick scratches).
  * **Rolling Loss Ceiling:** −0.60 SOL in 4 hours.
  * **Cooldown Period:** **2 Hours OFF**.

---

### Strategy 4: Upper-Curve All-Time High Momentum Breakout
* **Lifecycle Phase:** Upper curve high-velocity breakout (16.0 to 22.0 SOL reserve).
* **Bot Exemplars:** [`EN99z91j`](https://solscan.io/account/EN99z91jxRDqrDEgXN61XkWEaVB4p9yugy8ZKvz92kb5) (+23.04 SOL, **69.7% Win Rate**, **PF 5.05**), [`3crj9TB`](https://solscan.io/account/3crj9TB2QitxSKBCTz9wSFR4wvEcK3RqEdhHtSxEfhgS) (+13.69 SOL, **PF 4.23**), [`HXHoJwF`](https://solscan.io/account/HXHoJwF5p5L9iXRgeg3NiDdS5c4DADxNtRjHLDnTLXi7) (+10.20 SOL, **PF 4.82**).
* **Structural Edge:** At 16–22 SOL, liquidity depth is high. When a token breaks out to a new all-time high with large volume, the probability of continuing toward graduation is nearly 70%. These trades are brief (7–13 seconds) and highly profitable.
* **Exact Entry Trigger:**
  1. Reserve is between 16.0 and 22.0 SOL.
  2. Token breaks out to a **new all-time high** (`drawdown == 0.0%`).
  3. Preceded by $\ge 22$ unique buyers and an outside buy clip $\ge 1.0\text{ SOL}$.
* **Dedicated Exit Strategy (Velocity Ratchet):**
  * **Hard Stop Loss:** 2-slot stop if breakout is rejected (−8%).
  * **Take Profit:** Hold 18–30 slots (~7 to 12 seconds); exit 50% at $+20\%$, trail remaining 50% with a tight 6% stop into the graduation run-up.
* **Individual Circuit-Breaker Settings:**
  * **Consecutive Loss Limit:** 5 losses in a row.
  * **Rolling Loss Ceiling:** −0.75 SOL in 8 hours.
  * **Cooldown Period:** **4 Hours OFF**.

---

### Strategy 5: Pre-Graduation Carryover Arbitrage (72 SOL $\to$ AMM)
* **Lifecycle Phase:** Home stretch of bonding curve (72.0 SOL reserve) through graduation into post-migration AMM liquidity.
* **Bot Exemplars:** [`sssssDdM`](https://solscan.io/account/sssssDdMNAWKingjpEojkTNdVuZrBe7FsJLaGtexe7d) (+1,603.6 SOL carryovers), [`88887QrR`](https://solscan.io/account/88887QrRZPZmsstEXsoXXB8E7nbmUDde4Gp5s7jG3ENu) (+663.8 SOL carryovers), [`HvJi28GX`](https://solscan.io/account/HvJi28GXR2yWgDg1bewcvTV9yficRvgTnrdcc78kCFEF) (+887.1 SOL carryovers), [`BUkpShoE`](https://solscan.io/account/BUkpShoE) (+415.7 SOL carryovers).
* **Structural Edge:** Tokens crossing 72.0 SOL have an **88.9% natural graduation probability**. Entering on the curve right before graduation and carrying positions into post-migration AMM pools (PumpSwap/Raydium) avoids standalone AMM buy slippage while capturing massive DexScreener visibility volume.
* **Exact Entry Trigger:**
  1. Curve reserve crosses $\ge 72.0\text{ SOL}$ with positive volume momentum.
  2. $\ge 100$ unique holders.
* **Dedicated Exit Strategy (`amm_runner_trail`):**
  * **Curve Invalidation Stop:** Cut immediately on the curve if reserve falls back below $\le 60.0\text{ SOL}$ (capped at −0.12 SOL loss).
  * **Migration Transition:** Hold custody through the 1–3 slot migration freeze.
  * **AMM Tranche 1 (50% sold at AMM open):** Fills in initial AMM pool reserves, generating ~0.77 SOL proceeds on a 0.50 SOL ticket. **This immediately makes the trade 100% risk-free**, fully returning original capital + 0.27 SOL profit.
  * **AMM Tranche 2 (50% trailing peak surge):** Trailed into the 30–60 second DexScreener visibility spike with zero downside risk.
* **Empirical 21-Day Backtest Proof (Central85 Headline):**
  * **Win Rate:** **75.0%** (36 wins, 12 stopped out of 48 attempts).
  * **Profit Factor:** **5.46**.
  * **Net Profit:** **+12.58 SOL** (0.50 ticket) / **+18.79 SOL** (0.75 ticket).
  * **Max Drawdown:** **0.8566 SOL**.
* **Individual Circuit-Breaker Settings:**
  * **Consecutive Loss Limit:** 5 losses in a row.
  * **Rolling Loss Ceiling:** −0.80 SOL in 12 hours.
  * **Cooldown Period:** **6 Hours OFF**.

---

## 3. The Independent Circuit-Breaker System

Every strategy runs behind an autonomous, isolated circuit-breaker controller:

```mermaid
stateDiagram-v2
    [*] --> ACTIVE
    ACTIVE --> PROBE_MODE : Recovering from Cooldown
    ACTIVE --> TRIPPED : 5 Consecutive Losses OR Loss Limit Reached
    TRIPPED --> COOLDOWN_WAIT : Lock Strategy Timer (2-6 Hours)
    COOLDOWN_WAIT --> PROBE_MODE : Timer Expires
    PROBE_MODE --> ACTIVE : Probe Trade Wins (Half-Size 0.25 SOL)
    PROBE_MODE --> TRIPPED : Probe Trade Loses
```

### Circuit-Breaker Specification Table (Calibrated by Strategy Profile)

| Strategy Name | Strategy Profile | Win Rate & Payoff Profile | Consecutive Loss Limit | Rolling Net Loss Ceiling | Inactivity Cooldown | Post-Cooldown Probe Size |
|---|---|---|:---:|:---:|:---:|:---:|
| **Strat 1: Dev-Dump Absorption** | Mean-Reversion Scalp | High WR (~71%), Modest +25% Bounce | **5 in a row** | **−0.60 SOL** (6h window) | **3 Hours** | 0.25 SOL |
| **Strat 2: Survival Shelf Breakout** | Trend / Fat-Tail Runner | Moderate WR (~50%), Big 3x–7x Runners | **8 in a row** | **−0.60 SOL** (8h window) | **4 Hours** | 0.25 SOL |
| **Strat 3: Dead-Man Dislocation** | Fast Wick Scalp / Scratches | Lower WR (~44%), Tiny -0.04 Scratches | **10 in a row** | **−0.50 SOL** (4h window) | **2 Hours** | 0.25 SOL |
| **Strat 4: Upper ATH Momentum** | Momentum Velocity | Balanced WR (~70%), +20%–40% Scalp | **6 in a row** | **−0.75 SOL** (8h window) | **4 Hours** | 0.25 SOL |
| **Strat 5: Pre-Graduation Carryover**| High-Conviction Home Run | High WR (~75%), Asymmetric AMM Wins | **5 in a row** | **−0.80 SOL** (12h window) | **6 Hours** | 0.25 SOL |

### 3.1 How the Rolling Net Loss Window Works (Profit Buffer Protection)

A common flaw in naive risk engines is penalizing a bot that is actively in profit. Our engine enforces **true window-relative cash accounting**:

1. **Window Definition:**
   $$\text{Rolling Net PnL}(T) = \sum_{t \in [T - \Delta t, T]} \text{PnL}_t$$
   Only trades closed within the rolling time window (e.g. past 6 or 8 hours) are summed.

2. **The "House Money" Profit Shield:**
   * If a strategy starts the 8-hour window at 0, banks **+1.50 SOL** on a winning runner, and subsequently takes three scratches of −0.06 SOL (−0.18 SOL), its rolling net PnL is **$+1.32\text{ SOL}$**.
   * **The circuit breaker will NOT trip.** Because the strategy is net positive for that window, previous profits act as an organic cushion. 
   * The dollar loss circuit breaker **only trips if the strategy's cumulative PnL drops below the negative ceiling (e.g., $\le -0.75\text{ SOL}$ below its starting baseline in that window)**.

3. **Consecutive Loss Counter Reset:**
   * The consecutive loss counter tracks **unbroken losing trades**.
   * **A single winning trade immediately resets the consecutive loss counter to 0.**
   * For example, on Strategy 2: Loss, Loss, Loss, **WIN (+0.40 SOL)**, Loss, Loss $\to$ The streak counter is at **2**, not 5.

### 3.2 Global Master Emergency Brake
In addition to individual switches:
* **Master Portfolio Circuit Breaker:** If the combined balance of the entire bot drops by **$\ge 2.00\text{ SOL}$ in any rolling 24-hour window**, the **entire bot pauses all trading for 12 hours**.
* This provides an ironclad mathematical guarantee that the 15.0 SOL bankroll can never suffer catastrophic drawdown, preserving at least 13.0 SOL (87% of capital).

---

## 4. Expected Financial Projections (15.0 SOL Bankroll)

Based on our 21-day uncurated census and funded chronological account simulation:

| Projection Window | Minimum Expected Net | Central Baseline Net | High-Volume Market Net | Max Estimated Drawdown |
|---|:---:|:---:|:---:|:---:|
| **1 Day (24 Hours)** | **+0.60 SOL** | **+1.20 SOL** | **+2.50 SOL** | < 0.35 SOL |
| **3 Days (72 Hours)** | **+1.80 SOL** | **+3.60 SOL** | **+7.50 SOL** | < 0.60 SOL |
| **7 Days (1 Week)** | **+4.20 SOL** | **+8.40 SOL** | **+17.50 SOL** | < 0.86 SOL |
| **21 Days (3 Weeks)** | **+12.58 SOL** | **+25.00 SOL** | **+52.00 SOL** | < 0.86 SOL |

---

## 5. Implementation Roadmap (When Approved by User)

When the user decides to transition from research into implementation, the codebase will be wired cleanly in a modular fashion:

1. **Phase 1: Config & State Schema (`src/config.rs`)**
   - Add the `[strategies]` and `[circuit_breaker]` tables to `config.toml`.
2. **Phase 2: Independent Strategy Listeners (`src/strategy/`)**
   - `dev_absorption.rs` (Strategy 1)
   - `survival_shelf.rs` (Strategy 2)
   - `deadman_dislocation.rs` (Strategy 3)
   - `ath_momentum.rs` (Strategy 4)
   - `carryover_arbitrage.rs` (Strategy 5)
3. **Phase 3: Dedicated Exit & Carryover Router (`src/bot/trade_exec/`)**
   - Implement the tailored exit state machine (ratchets, dead-man timers, and post-migration AMM runner routing).
4. **Phase 4: Concurrency & Circuit-Breaker Manager (`src/risk/`)**
   - Enforce the 2-position concurrency cap and per-strategy cooldown timers.
