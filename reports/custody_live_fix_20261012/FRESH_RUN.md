# Fresh paper run — October 12 UTC / October 11 local

User canceled recovery of old paper positions and authorized a fresh live paper test. User confirmed the old host bot was stopped. Old runtime files were moved to `data/archive/paper_reset_20261012T050629`; this is an abandoned experiment, not a liquidation, realized loss, or on-chain transfer. Strategy settings and fake-casebook seed were retained.

Source repair reconstructs ordered account-level transfers and Pump swaps, distinguishes the bonding-curve token vault from wallet holdings, mirrors own paper reserve changes into the simulated vault, and preserves transaction-guard failures. Signed delegated transfers require equal authorization paths and equal source-account quantities. Unsupported authorization mutations remain quarantined. Observed owner holdings apply touched-account deltas, preserving untouched accounts.

Final offline detector suite: **337 passed, 0 failed**. Source diff whitespace checks passed. The new-account close-authority exception passes the frozen ordinary-router receipt, with negative owner/authority regressions remaining quarantined.

User subsequently requested **build only**, with live launch and monitoring performed by the user. The queued launcher was canceled before live startup. Release build status is recorded below. No historical recovery, backtest result, profitability claim, or real order is implied.

Release build succeeded: `cargo build --offline --release --bin curve_detector`, optimized release, 1m09s. Binary SHA-256: `8a102a3693f30963756ed3284454d18fa84357445b41f29f703a3691172e94f3`. Existing warnings remain; zero build errors.
