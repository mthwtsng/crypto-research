# RPC provider documentation audit

**Date:** 2026-10-09  
**Scope:** Official Alchemy and Shyft Solana documentation, the active cohort's RPC configuration, and the already-recorded capability probes. No new RPC probes were run. The six-worker collector was left untouched.

## Findings

### 1. Full-history page size differs between docs and measured backend behavior

`collect_cohort.py` requests `getTransactionsForAddress` with `transactionDetails="full"` and `limit=1000` in both `history()` and the first-page creation lookup. Alchemy documentation says **up to 1,000 signatures, or up to 100 full transactions per request**. The observed backend behavior contradicts that stated full-mode ceiling: the root's cache audit identified five existing Alchemy full-mode pages requested at `limit=1000` that each returned 1,000 entries. I independently opened the two supplied cache receipts (`f0c0de…5195c2.json.gz` and `7b821d…d04b7f.json.gz`): both have provider `alchemy`, `transactionDetails="full"`, requested limit 1,000, 1,000 `result.data` rows, a next pagination token, and entries containing both `transaction` and `meta` objects.

This is measured behavior for the cached requests; Alchemy's public reference does not promise that 1,000 full results are supported across plans or future backend versions. Preserve the working `limit=1000` and continue exhausting each `paginationToken`; do not lower it to 100 based only on the docs. The full-history request's other material settings align with documented options: `sortOrder="asc"`, finalized commitment, JSON-parsed bodies, and optional `filters.blockTime` bounds. It does not filter status, which preserves failed receipts needed by this collector. The current evidence does not establish that page size is a collection bottleneck. At the documented fixed 100-CU price per call, lowering the page size from 1,000 to 100 would require roughly ten times as many calls for the same receipts, without a measured speed benefit.

Alchemy's `getBlock` method costs 40 CUs per call. Its `getTransactionsForAddress` method costs 100 CUs per call. These are method costs, not per returned transaction. The account's throughput is measured in CUs per second and shared across its apps; current docs specify a 10-second rolling window. The published base throughput is 300 CUs/s on Free and 10,000 CUs/s on Pay-as-you-go, with Enterprise custom. At those limits, a stream consisting only of full-history calls would fit about 3 calls/s on Free or 100 calls/s on Pay-as-you-go; a stream consisting only of `getBlock` calls would fit about 7.5 or 250 calls/s, respectively. Actual capacity is lower when the account makes other calls, and the active API-key plan is unknown. The pool's 10 request/s Alchemy target is not a plan-aware CUs/s limit, so it can exceed Free throughput while appearing below the local request ceiling.

### 2. Vote exclusion does not explain these block-list mismatches

The existing capability report records:

- August slot 441666345: Alchemy returned 1,869 signatures; Solami returned 1,175, all of which were an Alchemy subsequence (694 Alchemy-only).
- September slot 447527916: Alchemy returned 1,643; Solami returned 975 (865 shared, 778 Alchemy-only, 57 Solami-only), so even the ordering/subsequence check failed.
- Shyft returned RPC error `-32009` for both probes.

Alchemy's documented Vote-program exclusion is specifically for **`getSignaturesForAddress` when the queried address is the high-volume Vote program**. Its support article recommends `getBlock` with `transactionDetails="signatures"` or `"full"` to obtain vote transaction data. Alchemy's `getBlock` docs do not list a vote filter, and Shyft's full-block example itself contains an instruction involving the Vote program. The `getTransactionsForAddress` reference lists filters for slot, block time, signature, status, and token-account activity, but no vote filter. Therefore the documented Vote-program address-index exception is not evidence that Alchemy's block response filters votes, nor does it explain the observed provider count differences. The probe saved counts and comparison statistics rather than the two providers' signature arrays, so the mismatching entries cannot be classified as vote transactions from these artifacts.

### 3. Shyft historical availability is not established for this window

Shyft documents a standard `getBlock` method and the full/signatures transaction-detail options, but its current transaction-API documentation says transaction history is limited to the past 3–4 days for both RPCs and APIs. Its `getFirstAvailableBlock` method reports the lowest confirmed block not purged from the node ledger; that is the documented availability check. Shyft's dedicated-node page separately says transaction history can be enabled on request for 1–2 days. None of these pages promises archived August–September history for the shared RPC endpoint. Those dates were 9–52 days old at collection time, so Shyft should not be treated as a historical fallback for this window absent a separate archive guarantee.

The recorded Shyft `-32009` is a JSON-RPC error, not a recorded HTTP 429/rate-limit response. The capability artifact omits the provider's error message, so it cannot distinguish a skipped slot from missing historical storage or another provider-specific failure. Do not classify it as throttling or as proof that a slot had no block. The docs' `getFirstAvailableBlock`/`minimumLedgerSlot` checks can establish the node's stated retained floor, but cannot repair an individual gap by themselves.

### 4. Secondary routing should remain disabled under the recorded evidence

The current `rpc_pool.py` makes full `getBlock` calls Alchemy-only. For signatures-only `getBlock`, it routes to a secondary only after that provider's signatures exactly match Alchemy's ordered list for the relevant month. `getTransactionsForAddress` also remains Alchemy-only because pagination-token continuity and complete-history compatibility have not been proven for another provider. The existing probes fail those conditions: Shyft is unavailable on both samples, and Solami is not exactly equal on either. Those guards protect transaction-index parity and coverage; changing them to use a lower-count response would silently lose block positions or receipts.

### 5. Batch support is not documented for this Solana path

Alchemy's batch-request article is titled and scoped to Ethereum, Polygon, Optimism, and Arbitrum; its examples are EVM methods. It says HTTP batches can contain up to 1,000 calls in general, advises small batches for reliability, and warns that some enhanced APIs do not support batches. Alchemy's Solana HTTP reference documents individual request objects and does not establish batch support for Solana `getBlock` or `getTransactionsForAddress`. Shyft's cited RPC pages also document individual requests, not JSON-RPC batch behavior. Treat batching for these Solana methods as **unverified**, especially for the enhanced history call. Batching, where supported, would reduce HTTP round trips but not the documented CUs: Alchemy's CU-cost table says a batch is billed as the method cost multiplied by the number of calls. It is not a remedy for the full-page-size mismatch or an account throughput cap.

## Concrete follow-ups for the collector owner

1. Preserve `limit=1000` for the current measured Alchemy backend behavior, along with the pagination token loop, ascending order, finalized commitment, and all-status history. Track the docs/backend discrepancy; only reconsider the limit if a measured request fails to return the expected page or the provider confirms a changed limit.
2. Keep the current exact-signature-order rule for secondary block routing. Do not interpret the count difference as vote filtering without signature-level evidence.
3. Before attempting Shyft historical routing, record `getFirstAvailableBlock` (and, if useful, `minimumLedgerSlot`) plus a single known finalized block inside the target range. A successful recent `getBlock` alone does not establish old-range archive coverage.
4. Read the actual Alchemy account throughput tier and aggregate usage before changing the local 10 RPS target. Compare rate control in CUs/s, including 100-CU full-history pages and 40-CU block checks.
5. Do not add JSON-RPC batching based on the EVM-only Alchemy page. If pursued later, verify one small, isolated Solana standard-method batch and one enhanced-method batch separately, check every response ID/error, and retain the existing durable receipt/parity checks.

## Official documentation

- [Alchemy `getTransactionsForAddress`](https://www.alchemy.com/docs/chains/solana/solana-api-endpoints/get-transactions-for-address) — 100 CUs; 1,000-signature / 100-full-transaction page ceiling; filters and pagination.
- [Alchemy `getBlock`](https://www.alchemy.com/docs/chains/solana/solana-api-endpoints/get-block) — 40 CUs; standard block request and response.
- [Alchemy Vote-program indexing note](https://support.alchemy.com/articles/7476139689-why-does-getsignaturesforaddress-return-an-empty-array-for-the-solana-vote-program) — exclusion applies to `getSignaturesForAddress` on high-volume Vote addresses; recommends block lookup.
- [Alchemy CU costs](https://www.alchemy.com/docs/reference/compute-unit-costs) and [compute units / throughput](https://www.alchemy.com/docs/reference/compute-units) — per-method CU values and throughput interpretation.
- [Alchemy pricing plans](https://www.alchemy.com/docs/reference/pricing-plans) and [throughput / 429 behavior](https://www.alchemy.com/docs/reference/throughput) — Free/PAYG base throughput, account-level aggregation, rolling window, and throttling behavior.
- [Alchemy batch requests](https://www.alchemy.com/docs/reference/batch-requests) — EVM-scoped examples, generic batch constraints, and reliability caveat.
- [Solana `getBlock` reference](https://solana.com/docs/rpc/http/getblock) — canonical method parameters and result shape.
- [Shyft `getBlock`](https://docs.shyft.to/solana/rpc-calls/http/getblock) — supported detail modes and request configuration.
- [Shyft `getFirstAvailableBlock`](https://docs.shyft.to/solana/rpc-calls/http/getfirstavailableblock) — lowest confirmed block retained by node.
- [Shyft transaction APIs](https://docs.shyft.to/solana-apis/transactions/transaction-apis) — states transaction history is limited to 3–4 days for RPCs and APIs.
- [Shyft RPC & gRPC plan limits](https://shyft.to/solana-rpc-grpc-pricing) — published RPC request-per-second plan limits.
- [Shyft dedicated Solana nodes](https://shyft.to/solana-dedicated-grpc-nodes) — transaction history can be enabled by request, documented as 1–2 days.

## Local evidence reviewed

`research/active_momentum_cohort_20261009/RPC_CAPABILITIES.json`, `rpc_pool.py`, and `collect_cohort.py`. The report is limited to documentation and existing probe artifacts; it is not a new live capability test.
