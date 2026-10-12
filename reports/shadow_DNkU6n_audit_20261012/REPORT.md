# DNkU6n shadow accounting audit — October 12 UTC / October 11 local, 2026

The reported **−84.4827% is not an authenticated full-position loss**. The shadow code sold only 17.7835% of the requested inventory, deleted the other 82.2165%, and classified the position as fully closed. The arithmetic reconciles only under that invented zero-recovery write-off. No corrected realized PnL is established here.

## Evidence

Mint: `DNkU6n6ZP1knEuGWFdYKqSqAHqQ4vx72WB47o8Pipump`, VM `ghost-v2-20261011T231014`, position `ghost-v2-20261011T231014-1791762554604-293`.

Frozen source rows: `ghost_trades.json` and `ghost_intents.json`. OPEN: October 11 23:49:14.704 UTC. CLOSE: 23:49:41.456 UTC. Entry signal slot 455838080/index 707; exit trigger slot 455838208/index 493. Both anchor signatures were retrieved independently through Shyft finalized `getTransaction`; both succeeded and their complete Program-data log payload lists match the stored observations exactly (`receipt_checks.json`). Entry transaction version 1 required `maxSupportedTransactionVersion=1`. Alchemy requests failed with HTTP errors. Source transaction index was not independently authenticated with full blocks in this audit.

Entry wallet budget 0.500000000 SOL = 0.493827159 curve input + 0.004691359 protocol fee + 0.001481482 creator fee. Separate execution fee 0.001505000 SOL gives cost 0.501505000 SOL. Paper tokens: 16,112,887.222808 (raw 16,112,887,222,808). Entry size and fee arithmetic reconcile.

At the exit trigger, authentic virtual reserves are 30.080329005 SOL and 1,070,134,573.807784 tokens; real SOL is 0.080329005. The strict full-size quote requests 0.446197543 SOL gross, exceeding observed real liquidity. The cap instead quotes only 2,865,428.220102 tokens, net 0.079324891 SOL; after execution fee, 0.077819891 SOL. The fill audit explicitly deletes the other 13,247,459.002706 tokens and records `filled_full_close`. The CLOSE then records −0.423685109 SOL / −84.4827%. This is a custody/accounting defect, not evidence the entire bag sold for that amount.

There is only one explicit written-off short sell FILL in the inspected intent log. A broader defect applies to all curve positions: each incoming authenticated receipt overwrites all paper-adjusted reserves (`CurveState::apply_onchain_trade`). This erases the hypothetical buy's liquidity/token effects; the next quotes combine paper custody with observed reserves from a world where our buy never happened. Correct counterfactual performance requires sequential counterparties replayed with instruction semantics, guards, fees and migration continuity, not a constant reserve offset.

Observed virtual-reserve spot moves from 0.000000030169881388 SOL/token at the entry signal to 0.000000028108921757 at the exit trigger: **−6.8312%**. This is a receipt-derived spot diagnostic, not corrected executable PnL. Paper buy moves spot +3.19437%; the dashboard's old +42.4405% `buy_impact_pct` actually measured real-reserve growth. The user reports chart capitalization about $4.4k to $3k; the DexScreener browser tool could not access this page, so those chart values are not independently verified. Authentic receipts establish the reserves/spot independently. [Pump documentation](https://github.com/pump-fun/pump-public-docs/blob/main/docs/PUMP_PROGRAM_README.md) describes the synthetic-reserve curve and equal SOL changes to real and virtual reserves; market capitalization and real liquidity are distinct.

## Source repair and scope

`src/bot/curve_detector.rs` now uses strict requested-size quotes for liquidation marks, exit estimates and exit fills. An insufficient-liquidity mark is unknown; a pending liquidation intent retains custody with no invented ROI, output, fee or fill. It retries as AwaitingData until a full quote becomes available or custody enters migration. Full-size failure no longer creates an undeclared partial order, deletes inventory or increments closed-trade losses/breakers. Existing full executable exits and explicit tranche exits retain their ordinary behavior. Buy/sell impact fields now calculate spot price movement from virtual reserves.

Regressions cover the exact DNkU6n entry/exit fixture, cap-versus-full quote quantities, original inventory retention, unchanged reserves/proceeds/no extra fees while pending, normal recovery/full-close, and actual spot impact. `cargo test --bin curve_detector`: **245 passed, 0 failed** (`tests.log`). Reviewed independently by GPT-6 Luna xhigh, with root accounting review.

This is a protective source repair. It does **not** implement persistent counterfactual curve replay or establish corrected historical PnL. Running release process was not rebuilt/restarted; original runtime history/statistics were preserved. Source loads through the runner's normal rebuild/restart workflow. The broader reserve-reset problem remains and affects both exits and return triggers; historical performance should not be treated as calibrated execution evidence.

A further existing dashboard issue: `calculate_total_equity` substitutes entry cost for unknown marks. Although null per-position proceeds/ROI and unresolved counts exist, that aggregate is a cost-basis placeholder, not executable marked equity. This audit does not report it as marked wealth or fabricate recovered history.

## Result card — accounting diagnostic, not a strategy replay

- Engine + revision: inspected current Rust shadow source; HEAD `9dcff3f509b40d78d51921509ca09e79a2eafe63`, dirty workspace; exact before/after source SHA256 in `source_provenance.json`.
- Data: selected disputed October 11 trade; 207 stored mint observations, frozen entry/exit rows and two independently fetched successful finalized RPC receipts. No complete creation-to-exit block-ordered counterfactual tape certified.
- Rules frozen before data: existing shadow behavior; this accounting repair is developed after inspecting the anomaly. Strategy parameters unchanged.
- Look count: one disputed position; one accounting repair, no strategy search.
- Placement fast / central80 / central85 / slow: not run; no funded counterfactual PnL claim. Existing receive-clock quotes uncalibrated.
- Stress: not run; not a replay study.
- Attempts / closed / failed / unresolved: original disputed row says one full close; actual logged quoted quantity covers only part of custody. Corrected historical outcome unresolved pending proper replay. No fabricated mark or zero-recovery settled loss.
- Max drawdown / largest winner / largest-winner exclusion: not a portfolio study.
- Bug alarms: custody conservation **failed in original**, fixed in source regression; insufficient full liquidity previously hidden by cap/write-off. Replay-specific timing/scenario/guard/completion/profit-factor alarms not evaluated by this diagnostic. Both anchor transactions independently succeed and match stored payloads.
- Verdict: **undetermined, retrospective** for corrected executable PnL.
- What would change verdict: authenticated ordered tape plus approved counterfactual replay preserving intervention, supported fees/limits, exit placement and actual custody through migration when applicable.

If data/tooling were unconstrained: bind every shadow position to a persistent counterfactual curve ledger and capture the instruction limits/atomic groups needed for sequential repricing, then reconcile estimated delivery with actual buy/sell placement cohorts.
