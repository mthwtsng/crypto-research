# Master Structural Edge Catalog (Non-Speed-Dependent Alpha)

**Living Registry of Discovered On-Chain Edges**  
**Core Directive:** Strictly eliminate all sub-30ms speed-fragile strategies. Maintain a modular, orthogonal collection of structural edges that execute comfortably within realistic 50–75ms landing latency and Yellowstone gRPC ingress.

---

## 1. The Strategy Triage Filter: Speed vs. Structure

To avoid the trap of latency wars against co-located Jito bundlers in Frankfurt or Amsterdam, every discovered edge is evaluated against the **Execution Latency Tolerance Gate**:

1. **Sub-30ms Fragility (PRUNED & ARCHIVED):**
   - Genesis Block 0 Sniping (`4yFA`, `8Rvt`, `89oox`)
   - Microsecond atomic sandwiching
   - Unconfirmed sub-second velocity chasing
   *Verdict:* Discarded. Being 1 position late results in negative expected value (-EV).

2. **Structural Robustness (QUALIFIED & KEPT):**
   - Execution window $\ge 50\text{–}100\text{ ms}$ up to multi-second shelves.
   - Operates on state changes, balance clearances, and consolidation floors rather than raw transaction race order.

---

## 2. Active Structural Edge Collection

Each edge operates independently in our modular engine without overwriting or interfering with others:

### Edge 1: Post-Dev Liquidation Absorption Floor (The Cleansed Floor)
* **Exemplars:** `9LXWa7V3` (+63.0 SOL/day), `3VUNtVtj` (+69.2 SOL/day), `9Sq7tiVyc` (+48.0 SOL, PF 88.7)
* **Execution Window:** **5 to 30 seconds (Multi-slot consolidation)**
* **Speed Sensitivity:** **Zero.** The bottom forms over dozens of slots after the developer sells off. 50–75ms has zero negative impact.
* **Structural Thesis:** 95% of Pump.fun tokens die because the creator dumps their dev allocation. Once the creator has dumped 100%, **the token cannot be creator-rugged anymore**. If organic buyers step in to absorb the crash, the risk-reward is heavily asymmetric.
* **Exact Mechanics:**
  - **Dev State:** `dev_sold_fraction >= 0.90` (or `creator_token_balance == 0`).
  - **Drawdown:** Curve price down `25% to 55%` from local high.
  - **Absorption Gate:** $\ge 2$ distinct non-creator buyers purchase $\ge 0.30\text{ SOL}$ within 3 slots of the trough (confirming community interest/CTO).
  - **Hold & Exit:** 10s stagnation scratch; +15% take-profit or 30s timer.

---

### Edge 2: Mature Survival Shelf Breakout (10.8 to 20 SOL Expansion)
* **Exemplars:** `8TPkr` (+120.4 SOL across 21 days), `9keCU8mg` (+26.4 SOL/day, median age 111s), `72NWWbch` (+17.9 SOL/day, median age 143s)
* **Execution Window:** **1 to 5 seconds (Calm consolidation expansion)**
* **Speed Sensitivity:** **Low.** Executes on mature curves with deep liquidity pools where individual trades move price only 0.5%–1.5%.
* **Structural Thesis:** 40% of tokens cross 10.8 SOL reserve (33% of the curve). Tokens that reach 10.8 SOL with $\ge 25$ unique buyers and decentralized holder distribution have an **83.3% probability of reaching 15.0 SOL** and **17.7% probability of graduating to AMM**.
* **Exact Mechanics:**
  - **Reserve & Age:** `reserve_sol >= 10.4 && reserve_sol <= 20.0`, `age_seconds >= 30`.
  - **Decentralization Gate:** $\ge 20$ unique non-dev buyers; top holder owns $\le 20\%$ of supply.
  - **Trigger:** Breaking out to a new local high with $\ge 2$ consecutive outside buy clips.
  - **Hold & Exit:** Arm Breakeven Ratchet at $+10\%$; 50% TP at $+20\%$, trail remaining 50% with an 8% trailing stop.

---

### Edge 3: Pre-Graduation to AMM Carryover (Bonding Curve Entry, AMM Exit)
* **Exemplars:** `BUkpShoE` (+205.0 SOL, 376 migration-carried cycles), `HvJi28GX` (+42.2 SOL/day), `88887QrR` (+28.9 SOL/day), `9999huSC` (+22.1 SOL/day)
* **Execution Window:** **Multi-second / multi-block (Curve entry + migration freeze + AMM sell)**
* **Speed Sensitivity:** **Zero on the curve buy; standard 50–70ms on the AMM sell.**
* **Core Mandate (User instruction, Oct 7, 2026):** For ALL pre-migration curve strategies, do NOT artificially terminate or force-close trades when a coin hits 84 SOL graduation. Never treat graduated tokens as unresolvable model failures. Model custody continuity through the ~30s migration freeze, and execute the sell into the post-migration AMM pool liquidity (where DexScreener visibility and initial AMM volume create high liquidity surges).
* **Structural Thesis:** Entering on the curve before or during late graduation (or riding a breakout runner through graduation) allows holding inventory that benefits from the post-migration AMM liquidity wave without paying AMM entry slippage.
* **Exact Mechanics:**
  - **Curve Entry:** Validated curve entry (e.g., `9keCU` strict absorption, mature breakout, or late 72+ SOL expansion).
  - **The Graduation Hold:** When reserve reaches 84 SOL, bonding curve locks. Hold through the ~30s migration freeze.
  - **The AMM Exit:** As soon as pool liquidity is initialized on PumpSwap/Raydium, execute the sell via `pumpswap.rs` into the initial AMM liquidity wave.
  - **The Invalidation Stop:** If curve drops below invalidation floor before graduating, cut immediately.

---

### Edge 4: 21-Second Dead-Man Dislocation Scalp
* **Exemplars:** `BDW8Bjoe` (+30.2 SOL/day, 41.3% exits clustered at 21–22s), `J3gZFpvs` (+14.8 SOL/day, 20.7% exits at 30s)
* **Execution Window:** **1 to 3 seconds**
* **Speed Sensitivity:** **Low.** Operates on severe wick dislocations caused by outside whale dumps on established curves.
* **Structural Thesis:** When a non-dev whale dumps $\ge 1.5\text{ SOL}$ on an active curve, price overshoots downwards due to AMM curve slippage. Organic buyers step in to arbitrage the discount. If momentum does not materialize within 21 seconds, the dead-man switch cuts the position to prevent holding dead weight.
* **Exact Mechanics:**
  - **Entry Trigger:** An outside whale sell of $\ge 1.5\text{ SOL}$ causes $\ge 15\%$ immediate dislocation on a curve with $\ge 8\text{ SOL}$ reserve.
  - **Exit Rule 1 (Stagnation Scratch):** Exit at $t=10\text{s}$ if spot $\le +2\%$.
  - **Exit Rule 2 (Hard Dead-Man Switch):** Exit 100% at $t=21\text{s}$ if position has not expanded into a runner ($< +15\%$).
  - **Exit Rule 3 (Full Single Fill):** Execute 100% in a single transaction to eliminate multi-tranche fee drag.

---

## 3. The Pruned / Archived Graveyard (Sub-30ms Fragility)

| Discarded Strategy | Exemplar Bots | Why It Was Pruned |
|---|---|---|
| **Genesis Block 0 Sniping** | `4yFAz7dp`, `8RvtT818`, `89ooxuy4`, `AMDEmVoc` | Requires sub-millisecond Jito bundles in slot 0. When landing 50–75ms late, you buy after 5 other snipers and get dumped on in slot 2. Guaranteed -EV under network latency. |
| **Unconfirmed 4s Velocity Chasing** | Early `nya666` | Chasing green volume within the first 4–8 seconds without checking dev balances walks directly into unexhausted developer rugs. |
| **KOL / Social Wallet Copying** | Call channels, Twitter KOLs | 50–75ms copy delay means buying after followers have already spiked the price, serving as exit liquidity for the caller. |

---

## 4. Bankroll & Capacity Blueprint (15.0 SOL Bankroll)

- **Bankroll:** 15.0 SOL max.
- **Ticket Size:** 0.50 SOL (max 0.75 SOL on Edge 3).
- **Max Concurrent Positions:** 2 positions (1.0 SOL locked, 14.0 SOL liquid buffer).
- **Exit Style:** 100% Single-Fill Exit (saves 0.004–0.006 SOL in priority fees and tips per round-trip).
