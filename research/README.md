# Research Directory Index & Navigation Guide

This directory houses the quantitative research, on-chain reverse-engineering, backtesting engines, and strategy playbooks for the project.

---

## 1. Core Operating Standards & Living Guides (Mandatory Reading)

These documents govern all research, execution modeling, and strategy decisions across the project:

| Document | Purpose & Scope |
|---|---|
| [`BACKTEST_ACCURACY_CONTRACT.md`](BACKTEST_ACCURACY_CONTRACT.md) | **Mandatory backtest standard.** Defines Central80/85 scenarios, approved replay engines, all-attempt fee accounting, and bug alarms. |
| [`EDGE_RESEARCH_GUIDE.md`](EDGE_RESEARCH_GUIDE.md) | **Living edge research reference.** Outlines the 13-step research loop, entry-first/exit-second design, and counterfactual validation. |
| [`RPC_LANDING_POSITION_GUIDE.md`](RPC_LANDING_POSITION_GUIDE.md) | **On-chain execution mechanics.** Explains how buy/sell transactions land, slot boundaries, and realistic fill pricing. |
| [`SELL_DISCOVERY_GUIDE.md`](SELL_DISCOVERY_GUIDE.md) | **Universal exit discovery.** Trajectory-derived exit rules: 10s stagnation scratch, +10% breakeven ratchet, and runner preservation. |
| [`STRUCTURAL_NON_SPEED_EDGES.md`](STRUCTURAL_NON_SPEED_EDGES.md) | **Living structural edge catalog.** Curated collection of non-speed-dependent edges (>50–100ms tolerance); strictly filters out sub-30ms racing. |
| [`MASTER_STRUCTURAL_EDGE_PLAYBOOK.md`](MASTER_STRUCTURAL_EDGE_PLAYBOOK.md) | **Structural alpha architecture.** The 10.8 SOL bonding curve survival shelf and rule-based bot deconstructions. |
| [`HISTORICAL_RESEARCH_ARCHIVE_SUMMARY.md`](HISTORICAL_RESEARCH_ARCHIVE_SUMMARY.md) | **Historical research timeline.** Synthesizes all completed research phases from October 1 through October 6. |
| [`CODEX_CALIBRATION.md`](CODEX_CALIBRATION.md) & [`GEMINI_CALIBRATION.md`](GEMINI_CALIBRATION.md) | **Agent calibrations.** Known historical failure modes and audit rules to maintain impartiality. |

---

## 2. Active & Recent Strategy Research (October 6–7, 2026)

| Study Directory | Focus & Key Artifacts | Current Status / Verdict |
|---|---|---|
| [`amm_multiday_20261006/`](amm_multiday_20261006/) | **Multi-Day AMM Strategy Backtest:** Evaluating migration-transition strategies and direct PumpSwap pool trades. | **Active / Under Replay** |
| [`amm_strategy_discovery_20261006/`](amm_strategy_discovery_20261006/) | **Direct AMM Pool Discovery:** Examines 30 completed direct-PumpSwap cycles (`2CQ`, `3VUN`, `9LX`) and migration age distribution. Report: [`REPORT.md`](amm_strategy_discovery_20261006/REPORT.md). | **Completed Discovery** |
| [`automated_wallet_expansion_20261006/`](automated_wallet_expansion_20261006/) | **21-Bot Automated Expansion Census:** Identifies 21 candidate bots earning $\ge 10\text{ SOL/day}$ (17 pure curve, 4 AMM carryovers). Report: [`REPORT.md`](automated_wallet_expansion_20261006/REPORT.md), Roster: [`STAGE_FOCUS_WALLETS.txt`](automated_wallet_expansion_20261006/STAGE_FOCUS_WALLETS.txt). | **Completed Census** |
| [`automated_wallet_discovery_20261006/`](automated_wallet_discovery_20261006/) | **11-Bot Automated Shortlist:** Initial discovery of systematic rule-based on-chain bots. Report: [`REPORT.md`](automated_wallet_discovery_20261006/REPORT.md). | **Completed Precursor** |
| [`wallet_selector_clues_20261006/`](wallet_selector_clues_20261006/) | **Bot Selector & Exit Fingerprints:** Forensic analysis of `BDW` (24% drawdown pullback, 21s timed exit) vs `sssss` (renewed buying). Report: [`REPORT.md`](wallet_selector_clues_20261006/REPORT.md). | **Completed Synthesis** |
| [`bot_edge_gap_20261006/`](bot_edge_gap_20261006/) | **Entry-Gap & Mature Sequence Study:** Tested fresh-breadth sequence filters across 5,040 September/October launches. Report: [`REPORT.md`](bot_edge_gap_20261006/REPORT.md). | **Completed Retrospective** |

---

## 3. Completed Historical Research Milestones (October 4–5, 2026)

| Study Directory | Description & Key Findings |
|---|---|
| [`multi_timeframe_audit_20261005/`](multi_timeframe_audit_20261005/) | **21-Day Multi-Period Audit (5,040 Launches):** Benchmarked 11 strategy variants across 21 calendar days (Sept 14 – Oct 4). Established that 24/7 unguided execution is -EV due to dry off-peak hours. |
| [`wallet_8tpkr_20261005/`](wallet_8tpkr_20261005/) | **Decompilation of Benchmark Bot `8TPkr`:** Forensic audit of 22,242 receipts (+120.4 SOL lifetime cash). Identified 38s median holds and strict 8.5–25 SOL curve corridors. |
| [`refined_8tpkr_10sol/`](refined_8tpkr_10sol/) | **10 SOL Bankroll Adaptation:** Porting 8TPkr mechanics to small-ticket execution. |
| [`day_general_20261004/`](day_general_20261004/) | **October 4 Canonical Day Benchmark:** Evaluated 600 uncurated launches under the approved canonical replay engine. |
| [`bot_discovery_onchain/`](bot_discovery_onchain/) | **Initial On-Chain Mining:** Census across 26,787 candidate addresses. |

---

## 4. Historical Archive (`archive/`)

* [`archive/historical_oct02_oct04/`](archive/historical_oct02_oct04/): Houses early exploration reports (BWAM snipes, early unified specs) and scratch JSON result logs from October 2 through October 4.
* Legacy compressed bundles: `data/legacy_research.tar.gz` and `data/archive_research_20261003.tar.gz`.
