# Blocked coins and fake-volume detection audit

Frozen 2026-10-11 22:25:33.517 UTC; current VM `ghost-v2-20261011T220021`, candidate window 22:00:21–22:25:33. This is an observation and source-predicate audit, not a profit backtest. **Yes: a permanent holder-screen rejection excluded at least one coin with source-valid S2/S4/S5 opportunities and a later graduation.** It does not establish that every blocked runner was organic or profitable to trade.

## Strongest missed setup: 5UC38

Mint: `5UC38iV4AJexEXMAH1VZZT9r9DXz1yxdqFfUcWbJWMVB`.

| Event | UTC | Evidence |
|---|---|---|
| Observed creation | 22:07:25.222 | Creation mapping and successful receipt in the saved stream; creator seed 0.05 SOL. |
| Holder veto | 22:07:28.302 | Reserves about 9.66 SOL; 7 sampled known wallets; wallet `2MrkVnbfG63fnjEDrEX5ps5QjSbK49S69YbSeFczrbY9` held 12.0919% of supply and 0.181379 SOL, triggering the single low-SOL >=7% rule. Call duration 67ms. |
| S2 source predicate | 22:08:09.799 | 11.578786 SOL, 30 qualified outside buyers; source anti-bundle gate clear. |
| S4 source predicate | 22:08:24.396 | 17.055861 SOL, 47 qualified outside buyers; source anti-bundle gate clear. |
| Ownership change by S4 | 22:08:24.396 | The offending wallet had sold 8.8158% of supply, leaving 3.2762% observed custody. Trade-only top-3/5/10 shares were 8.76%/13.98%/23.45%, all below current source vetoes. Transfers are not reconstructed. |
| S4-style reclaim | 22:08:47.773 | Subsequent complete receipt returns above the S4 breakout level after an observed 18.6% dip; reserves 17.297436 SOL. The offending wallet's observed custody is now zero. This is a conditional reclaim opportunity, not a simulated funded fill; competing family precedence/own impact were not replayed. |
| S5 source predicate | Later in window | Crosses 72 SOL at 72.316841 SOL, 178 qualified buyers, anti-bundle clear. |
| Completion receipt | 22:16:56.019 | Real token reserves zero; real SOL about 85.005360. Completion is observed, not invented from a fixed 84 SOL threshold. |

No captured trade OPEN or variant arm exists for this mint. The RPC holder ban is sticky: a blocked report sets `is_botted_cabal=true`; scheduling explicitly excludes flagged mints; holder readiness excludes the flag; entry requires ready or whitelist. Therefore the original holder verdict survives the wallet's observed sale and later breadth growth. A tracked-wallet whitelist can clear it, but no such override produced an entry here. Sources: `src/bin/curve_detector.rs:422`, `:2053`, `:2106`, `:2137`; raw `5UC_holder_evidence.json`, complete candidate receipts, frozen slim observations and source helper.

## What the blocked list does and does not show

98 new shield records appear in the current time window: 77 on-chain flags and 21 RPC holder flags. Among 97 with subsequent captured curve observations, 39 reached at least 25 SOL reserves, 10 at least 50 and 6 at least 72. These are observed reserve-path counts, not returns or missed-profitable-trade counts. Ten shield-record mints also appear in the captured trade file; historical on-chain reasons are not necessarily active vetoes and whitelist overrides matter.

Exact checked-out Rust source predicates were evaluated after complete receipts before admission screens. The receive-order observer finds 217 candidate rows across 55 mints (47 with observed creation, 8 with unknown genesis). Repeated rows on different signatures are repeated opportunities, not independent setups. Source-valid candidates after an earlier logged holder ban, among creation-observed mints with no captured OPEN, occur on four mints: 5UC38 (S2/S4/S5), 9uHMv (S4), EzxoD6 (S5), GbkCmb (S5). These are opportunities, not four guaranteed trade wins. EzxoD6 reached about 78 SOL then 0.45; GbkCmb about 81.89 then 1.08; 9uHMv only 23.78 then 0.19. Removing the shield indiscriminately admits substantial collapse risk too.

The main entry-side gap is **a permanent label based on an early ownership snapshot, without reconsideration after supply disperses or the offending holder exits**. That is different from claiming the thresholds never detect risk. Current losses also show poor follow-through on admitted entries; blocker repair alone does not establish an edge.

## Screening bottleneck

1,787 holder results across 312 mints in the frozen session: 1,387 clear, 372 unknown, 28 blocked. Latest logged result per mint: 226 clear, 58 unknown, 28 blocked. Sixty initially unknown mints later cleared. 336 unknown results involved fewer than five resolvable system-owned wallet owners. Unknown skips entry while retrying; it is missing evidence, not a fake-coin label.

450 primary HTTP 429 responses used fallback; 102 fallback results remained unknown. Other primary errors do not trigger fallback. Screen call duration was about 78ms median/474ms p90; it excludes permit/pacing waits and the first request time when report timing restarts at fallback. These counts cannot alone establish how many qualifying entries were missed by delays.

## Better fake-volume detection direction

The user's target pattern is apparent ladder-like buying followed by an abrupt collapse. Low wallet SOL, total volume and raw address count cannot distinguish that reliably on their own. A useful observer should preserve: gross buys/sells and retained net demand; repeated-wallet share; effective buyer concentration; buy-size and slot concentration; ownership changes; and repeated wallet groups across launches. Genuine bot ownership/common funding requires additional evidence; many distinct addresses do not prove independence. Fine timing regularity requires a reliable clock rather than feed burst artifacts.

Current pattern diagnostic artifacts, when completed, are in `fake_volume_diagnostic/`. This study keeps flags separate from production admission. No threshold is promoted from this short inspected window, and no live filter/restart/order is authorized or performed by this report.

## Frozen fake-volume diagnostic findings

The observer now includes 27 first S2/S4 setup snapshots on creation-observed mints (some mints qualify for both families). Two snapshots are too recent for a full 120s horizon. Of the remaining 25, six have an observed >=90% running-peak real-curve-reserve drain within 120s. This is a curve liquidity-state diagnostic, not proof of common-owner bots or executable loss. Future drains are labels, never entry features. Graduation is censored where it ends observable curve coverage.

Prior-10s repeated-wallet buying and standardized order-size concentration do not clearly separate these six drain snapshots from the other nineteen. Median repeat-wallet volume share is zero in both groups; median modal order-size count share is 17.4% vs 20.0%. Median sell/buy churn is lower in the drain group (8.7% vs 43.1%), so high retained net buying alone would not identify these one-way pump paths. These small, conditional, retrospective groups cannot calibrate a classifier. Examples include `4ViCZ...` (80% of recent buy counts in one size bucket, later 99.3% real-reserve drain), while other drain cases have varied sizes. A regular-looking ladder is a reason to investigate, not an established veto.

The separate first-16-SOL creation-cohort view mainly identifies launch whale bursts rather than broad, late ladder volume. It is preserved as a separate descriptive view, not selected as a winning classifier. All feature windows use complete receipts available through the anchor; outcome states use each receipt's final state per mint. All-trade buy/sell churn and outside-address metrics are distinguished in definitions. See [diagnostic report](fake_volume_diagnostic/REPORT.md), scripts, CSVs and [detector specification](FAKE_VOLUME_DETECTOR.md).

The better detection direction is a changing, evidence-based risk assessment: group/funding associations, retained inventory, repeated buyer-group history and demand replacement after selling, with a fresh screen. Current logs do not establish those ownership links or complete transfers, so no all-bots detector or live veto is claimed here.

## Evidence limits and checks

The saved stream has 6,381 same-slot transaction-index inversions across 91,095 receipts and zero duplicate signatures. Receive order mirrors what the current source observer sees, but the full interleaved stream is not canonical block order. Root found zero same-mint/same-slot index inversions; the independent chain-order rerun reproduces all 217 candidate keys and snapshot fields exactly. Thus the cross-mint inversions do not change these per-coin candidate conclusions. The separate chain-order view is an ordering sensitivity, not a fabricated real-time availability claim. Creation observed does not prove a complete, gap-free transfer history. Checked-out source parity with the deployed binary/config is unverified.

The helper directly includes current Rust strategy source; no rewritten Python profit engine was used. It applies all events in a complete receipt, then evaluates each mint's last event. It leaves live state and signal_fired unchanged and records full receipts. Root independently checked the 5UC predicate and offender's observed custody changes. Two GPT-6 Luna workers supplied screening and source-predicate evidence; root reviewed the interpretation. Existing files and live state were preserved.

What I would investigate if data and tooling were unconstrained: common funding/fee-payer and recurring buyer cohorts; full token transfers/escrow; authenticated same-slot state ordering; actual order inclusion and exit liquidity during ladder breaks. These would allow distinguishing linked bot volume from independent automated trading and testing the missed setup under the approved funded replay.

## Result card

```text
engine: current Rust source predicate observer, no executable profit replay; source/helper hashes in MANIFEST.json.
data: 21:56:03 warmup, 22:00:21–22:25:33 current window; 91,095 saved complete receipts; all observed creations/opportunities, not future-winner selection.
rules frozen before data?: current source retrospectively inspected; no new strategy variant executed.
look count: source-candidate audit plus two prespecified feature-anchor views (first16SOL and firstS2/S4), spot-collapse / reserve-drain descriptive labels, receive/chain ordering check; no tuned admission classifier.
placement and stress: fast/central80/central85/slow not run; unavailable for hypothetical filled profit.
attempts/closed/failed/unresolved: not a funded experiment; source candidates only; no modeled cash or inventory.
PnL/drawdown/largest winner: not calculated; future peaks are opportunity diagnostics.
bug alarms: profit-replay alarms not applicable; atomicity, signature uniqueness and creation flags checked; receipt-order inversion detected and disclosed.
verdict: undetermined, retrospective.
what changes verdict: complete transfer/custody and reliable ordering, pinned deployed configuration, prospectively observed fake-risk flags, later evaluation and approved causal funded replay before a profitability claim.
```
