# Observed-price display repair

October 12 UTC, 2026. The active-position UI required `tracking_status === 'complete'`, while the current summary emitted `complete_from_creation`. It also used the paper-model valuation error to hide independently available observed market data. The actual active-position summary contained finite observed market cap and SOL/token spot values even though executable proceeds and execution spot were null.

The UI now accepts both tracking-status labels for observed data and displays the observed price/supply independently of paper-model valuation errors. Execution spot still requires a resolved valuation; unknown liquidation quotes, ROI, peak and unresolved status remain unchanged. Incomplete observed tracking still displays Unknown.

Validation: extracted dashboard JavaScript passes `node --check`. The actual seven-position summary at verification rendered through `renderSummary` with DOM stubs: observed market cap displayed numerically while execution spot remained Unknown, unknown marks remained visible and UNRESOLVED statuses were retained. Tracked-file whitespace check passed. No trading-engine source, runtime checkpoint, cash or position state was changed by this display repair. The external browser/host's loaded asset version was not verified.
