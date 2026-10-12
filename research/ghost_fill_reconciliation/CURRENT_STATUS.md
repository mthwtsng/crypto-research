# Ghost execution audit status — October 9 local / October 10 UTC, 2026

## Subsequent integration and handoff

The fill repair is now integrated into the source and a release build. See [integration notes](INTEGRATION_NOTES.md). Twenty-one Rust fill/accounting tests, nine receipt tests and fourteen Python reconciliation tests pass. The final isolated live probe under `reports/ghost_fill_ready_live_20261010_023956/` captured four buy fills, four final sell fills and one failed sell guard, with completed sell records correctly labeled FILL. Its JSON verification records the cash-ledger comparison and source provenance. The preceding probe additionally exercised a partial sale and automatic post-exit RPC audits.

The previously running host test was not stopped or replaced. To load the rebuilt runner, stop that test and run `bash scripts/run_shadow_detector.sh` from the repository root. The script builds current source, preserves the previous inventory summary, and starts a separately identified zero-capital run. Paper fills remain provisional estimates and migrated-AMM exits remain pending authenticated route coverage. Concurrent strategy edits are separate from this execution repair.

The following findings describe the earlier source snapshot and are retained as audit history.

The reported paper fills are not validated executable fills. Thin curve liquidity magnifies the effect: a stop threshold triggers an order, but the triggering transaction and competing orders ahead of that order determine the later sell quote. Market capitalization does not establish executable pool depth.

## Current source recheck

The concurrently updated core runner still reads instruction limits as executed amounts (`src/bin/curve_detector.rs`, decoder at line 69), including exact-SOL minimum tokens, regular-buy maximum SOL and sell minimum SOL. Pending entries are now wired, but landing runs before the current trade is applied (lines 1039–1042) and counts decoded events rather than complete atomic transactions. Partial and final sells still execute synchronously against the trigger state (`src/bot/curve_detector.rs`, lines 668 and 689); they do not wait for and reprice at a later exit boundary. Fees remain fixed 1% with floor rounding, and migration exits still use the curve rather than authenticated AMM continuation. Line anchors describe the source inspected during this session, not a pinned deployment.

The release binary changed during the session. That timestamp does not establish a running deployment. Another writer subsequently archived the 40-record legacy log, and a new local summary updated at 00:41:27 UTC with uptime 90 seconds and zero open/closed trades. This establishes fresh telemetry after a reset, not active binary provenance or correct fill behavior. Do not claim these isolated repair components are enabled.

## Evidence and repair scope

The [frozen receipt audit](../../reports/ghost_verification_20261010_002243/REPORT.md) includes a successful source buy whose 0.500000000 SOL instruction cap differs from its actual 0.490196077 SOL curve amount. It is not an authenticated match to an individual paper signal.

The final legacy reconciliation run at `reports/ghost_fill_reconciliation/legacy_20261010_final/report.json` inspected a preserved snapshot of 40 action records: all 40 lack source signature/slot anchors and remain unresolved; zero exact receipts or hypothetical boundary quotes were established. Existing records were preserved. An unsubmitted ghost order cannot have an exact on-chain fill receipt; its placement is an explicitly labeled estimate.

Separate repair components are implemented and offline: successful receipt decoding (9 focused tests), integer curve quotes and delayed intent scheduling (12 focused tests), and per-fill reconciliation (14 focused tests), with 100 buy and 100 sell parity cases against the approved Python adapter. See [integration requirements](INTEGRATION_NOTES.md). They have not been wired into a running process, and component checks do not establish portfolio PnL or strategy profitability.
