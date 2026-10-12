# Crypto-Research: Strategy Lab & Backtesting Environment

This repository hosts the quantitative research lab, offline backtesting harnesses, historical market replay tapes, and audit reports for the Solana trading system.

## Repository Structure

- `research/`: Experimental strategy cohorts, orderflow studies, bumper analysis, and historical edge discovery folders.
  - Core specifications: `MASTER_STRATEGY_REGISTRY.md`, `BACKTEST_ACCURACY_CONTRACT.md`, `EDGE_RESEARCH_GUIDE.md`, etc.
- `reports/`: Audit reports, historical session analyses, and PnL evidence cards.
- `scripts/`: Offline simulation engines, parameter grid searches, and replay scripts:
  - `run_canonical_backtest.py`
  - `run_combined_portfolio_replay.py`
  - `benchmark_s5_across_scenarios.py`
  - `download_s5_amm_pools.py`
  - `filter_active_coins.py`
- `data_archive/`: Historical session tapes and raw JSONL observation dumps (16+ GB).
- `scratch_archive/`: One-off forensic scripts, cache files, and diagnostic tools.
- `SETUP_CONTEXT_FULL_HISTORY.md`: Comprehensive historical record of all prior deployment and engineering sessions.

## Governance & Standards

All strategy models in this lab adhere to the **Backtest Accuracy Contract** (`research/BACKTEST_ACCURACY_CONTRACT.md`) and benchmark against the canonical S1–S5 strategies defined in `research/MASTER_STRATEGY_REGISTRY.md`.
