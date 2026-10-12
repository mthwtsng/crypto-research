# Bumper Coins & Real-Coin Bot Whitelisting Audit

**Date:** October 12, 2026  
**Calibration Standard:** `research/BACKTEST_ACCURACY_CONTRACT.md`  
**Single Source of Truth:** `research/MASTER_STRATEGY_REGISTRY.md`  

## 1. Summary of Changes

1. **33 Verified Real-Coin Edge Bots Added to Whitelist**:
   - Ingested into `tracked_wallets.txt`.
   - Included multi-coin real fleet bots (e.g., `ssssswdk4...` [45 real coins], `ARu4n5m...` [41 coins], `omegoMAe1...` [40 coins]) and top scalpers from the `5BeeHr` runner (`DtyfdfF6...` [+5.12 SOL], `7uvyEZDo...` [+4.81 SOL], etc.).
   - Mechanism: Matches on incoming buys invoke `curve.mark_whitelisted()`, clearing fake-coin shield vetoes (`is_botted_cabal = false`, `anti_bundle_reason = None`).

2. **Volume-Bumper Tracking & Strategy Adaptation**:
   - Built native bumper tracking in Rust engine (`CurveState.micro_buys_count`, `CurveState.last_bump_slot`, `CurveState.is_bumped`).
   - Relaxed S4 Upper ATH triggers on bumped coins: `min_buyers` lowered from 15 to 8, and `min_buy` requirement lowered from 0.45 SOL to 0.25 SOL.
   - Built **Bump Inactivity Scratch**: If `is_bumped` is active and no bump occurs for $\ge 25$ slots (~10 seconds) while ROI is $< +3.0\%$, the position is defensively scratched before cabal dump.

## 2. Empirical Backtest Results (1,902 Tokens Audited)

Run via `python3 research/analyze_bumped_strategy_cohort.py`:

| Setup Cohort | Trades | Win Rate | Net PnL | Profit Factor | Avg Trade PnL |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Bump-Aware (Active Bumper Cohort)** | **35** | **62.9%** (22W / 13L) | **+1.1530 SOL** | **3.40** | **+0.0329 SOL** |
| **Bump-Aware (Organic Cohort)** | 37 | 29.7% (11W / 26L) | -1.3660 SOL | 0.47 | -0.0369 SOL |
| **Baseline Canonical Mode (All Tokens)** | 69 | 43.5% (30W / 39L) | -0.4629 SOL | 0.87 | -0.0067 SOL |

## 3. Deployment Files
- Engine: `src/bot/curve_detector.rs`, `src/bin/curve_detector.rs`
- Binary: `target/release/curve_detector` (Release build verified, 341 tests pass)
- Whitelist: `tracked_wallets.txt` (162 unique whitelisted addresses)
- Backtest Engine: `research/analyze_bumped_strategy_cohort.py`
