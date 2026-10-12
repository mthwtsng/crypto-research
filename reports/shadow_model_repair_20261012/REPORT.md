# Shadow calculation and pre-entry tracking repair

October 12 UTC / October 11 local, 2026. Source repair and isolated feed audit; no strategy profitability claim or live orders.

## Findings and changes

The disputed DNkU6n loss was not trustworthy. The earlier [receipt-backed audit](../shadow_DNkU6n_audit_20261012/REPORT.md) found a capped partial sell recorded as a full close, deleting the remaining inventory. It also found authentic receipts replacing the paper position's own reserve impact. Chart spot movement cannot establish executable liquidation PnL, but neither defect can be accepted as position accounting.

The new `persistent_curve_v4` model keeps observed reserves and paper reserves separate. Setup features read authentic observed state. A paper buy or sell updates a persistent simulated reserve/custody ledger; later complete transaction groups are repriced using recorded instruction arguments, fee rounding and owner balances. Before repricing, the original no-intervention branch must reproduce the actual receipt exactly. Unsupported instructions, custody mismatches, changed completion or missing history suspend executable quotes and preserve tokens. Counterparty limit/liquidity failures revert the simulated group atomically while retaining its separately verified historical branch.

Pre-entry tracking now requires creation metadata, actual raw supply/decimals, ordered continuous receipt history and supported fees. Market capitalization uses virtual-reserve spot multiplied by actual supply; real SOL liquidity is a separate quantity. Transaction groups drive crossing/confirmation features once per group. Unknown metadata, old/out-of-order receipts, transfer gaps and stream gaps prevent setup admission, including whitelisted entries. Undecodable trade receipts are scoped to affected mints wherever possible. Restarted inventory is retained but needs history backfill before further counterfactual execution; automatic gap repair is not implemented.

Unresolved receipts have an explicit tracking audit row with affected mints, truncation and unscoped-success flags. Unlocalizable potential changes suspend coverage with a distinct receipt-gap reason; they are not mislabeled stream disconnects. This is deliberate exclusion of unknown data, not proof that every current coin can be reconstructed. The feed probe can demonstrate ingestion, metadata and price availability; it cannot certify complete coverage for every coin.

The scoping audit caught a truncated routed transaction that previously suspended the whole feed. An independently fetched RPC receipt confirmed four touched mint scopes, including its Pump coin. The decoder now preserves token-balance mint scopes even when logs truncate or instruction layouts are unknown. The regression tests both absent scopes and metadata fallback; the raw receipt is preserved in `feed_probe_scoping_audit/truncated_receipt_rpc.json`.

USD capitalization uses a timestamped, freshness-checked SOL/USD quote with CoinGecko and Coinbase fallback. Explicit environment overrides remain labeled static assumptions; missing/stale quotes no longer silently assume $145. Reference APIs: [CoinGecko Simple Price](https://docs.coingecko.com/reference/simple-price) and [Coinbase Exchange product ticker](https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-ticker).

Full liquidation requires a quote for every requested token. Unknown executable marks remain null; pending manual exits retain custody and the request. Dashboard/summary separate settled PnL, open marked PnL, combined marked estimate and unresolved inventory. Combined marked equity is unknown when any open mark is unknown. Historical trades lack v4 provenance and are visibly labeled unreconciled; original history is preserved, not retrospectively recomputed.

## Limits

The counterfactual curve model has receipt-parity and custody regressions, including the authentic DNkU6n entry/exit fixtures; this does not calibrate order delivery or prove hypothetical returns. Changed migration boundaries remain unresolved with custody preserved. Existing authenticated AMM snapshot quotes retain their separate model and are not a full replay of historical AMM counterparties. Pump-subscription transfer coverage is not a census of all wallet transfers; observed custody-only changes and later owner-balance mismatches quarantine affected coins. Coins first seen after creation are excluded until coverage is repaired.

The isolated probe uses all paper strategies disabled, separate audit/checkpoint paths and no capital. It does not restart or alter the user's running shadow session. The normal runner rebuilds the repaired source on its next launch. Existing stats, including DNkU6n, remain historical and unreconciled.

## Validation

Final `cargo test --bin curve_detector`: **300 passed, zero failed**. The optimized offline release build succeeded. Shared quote/scheduler standalone tests: **13 passed**. Current dashboard JavaScript syntax and null-value/provenance/render fixtures passed; launcher syntax and `git diff --check` passed. Earlier integrated runs encountered failures while separate fake-coin code was changing in the shared workspace; the final full-suite run passes. Source hashes and feed counts are recorded in `CHECKS.json`, adjacent test/build logs and `feed_probe_final/CHECKS.json`.

Final 30-second release probe: **1,526 decoded observations, 10 creations, 1,489 supported trade instruction events**. Fresh timestamped CoinGecko SOL/USD was available. One supported coin retained complete pre-entry tracking at the checkpoint; unsupported/custody/history gaps were explicitly excluded. Five truncated receipts were localized to mint scopes, with **zero feed-wide receipt suspensions**. No paper entries, positions or closed trades occurred; the timeout exit code 124 is intentional. This verifies the corrected scoping on live input, not exhaustive feed coverage or profitable strategy behavior.

## Result card — model audit, not a backtest

- Engine + revision: Rust shadow `persistent_curve_v4`; HEAD `9dcff3f509b40d78d51921509ca09e79a2eafe63`, dirty shared workspace; source hashes in CHECKS.json. Approved strategy backtest engine was not run.
- Data: disputed receipt fixtures and isolated current Pump feed; no complete historical portfolio tape certified. Probe starts cold and excludes coins missing creation.
- Rules frozen before data: no strategy thresholds changed by this repair; accounting changes developed after the anomaly.
- Look count: one disputed position; no strategy search.
- Fast / central(p=.80) / central(p=.85) / slow all-attempt funded PnL: not run; no return estimate.
- Stress: not run; paper receive-clock placement and AMM delivery remain uncalibrated.
- Attempts / closed / failed / unresolved: probe disables entries; original disputed historical outcome unresolved pending approved replay. No fabricated recovered mark or settled zero-recovery loss.
- Drawdown / largest winner / exclusion: not a portfolio study.
- Bug alarms: source regressions cover retained custody, exact full-size liquidity, historical receipt parity, whole-group limits, delayed intent/cash delivery and unknown migration. Scenario/profit-factor/sample-selection alarms are not evaluated by these tests.
- Verdict: **undetermined, retrospective** for corrected historical PnL.
- What would change the verdict: complete authenticated ordered history and approved funded replay with calibrated placement, all-attempt fees/guards and migration continuation.
