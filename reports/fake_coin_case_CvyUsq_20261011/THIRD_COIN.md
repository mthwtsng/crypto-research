# Third case: DgT6h post-graduation pool

## Finding

The frozen observations show a fast, substantial sell shock, but this pool did not approach a near-zero quote reserve during the captured window. The largest adjacent sampled fall was from 66.3559 to 44.6679 SOL between 23:55:17.557 and 23:55:18.318 UTC: 32.68% over 761 ms of observer time. The next sample fell from 44.6679 to 33.6196 SOL over another 749 ms (24.73%). The sampled reserve later reached a low of 30.4640 SOL and recovered to 31.9126 SOL at the last frozen observation. The complete frozen series has 124 observations.

Actual WSOL in the quote vault is kept separate from PumpSwap’s virtual quote reserve. Virtual quote was about 17.36 SOL during the abrupt move, while the actual quote vault changed from 66.3559 to 44.6679 SOL. Using `(actual quote + virtual quote) / base reserve × token supply` gives a pool-implied proxy of about 394.86 to 216.74 SOL across that sampled interval. It is not a USD market-cap measurement; no historical SOL/USD source was used.

This is a sharp liquidity and price shock, not the terminal near-floor reserve collapse seen in the Cvy example. The user’s sub-0.5-second timing is not resolved by this capture. The two largest adjacent snapshot observations are 761 and 749 ms apart, and `blockTime` has only one-second granularity. Faster transactions may have occurred between observer samples, so these data neither prove nor rule out an on-chain sub-500-ms sell sequence.

## Pool reserve path

The pool is `7LAx8jrRB5zXgeH69RXs2FwXjmoXzTUXwfUU1fPrHbpc`, with base vault `CXa9yFKacD14aorShxWcL1x7MwGhBG18K6KtQN9nVWge` and WSOL quote vault `DLx6wfCAdH2t9WJ7oUcxYo4A1yFP6Lfh5DmGpbwKU57y`.

| Sample | UTC | Slot | Actual quote vault | Virtual quote | Base tokens in pool |
|---|---:|---:|---:|---:|---:|
| First frozen AMM observation | 23:54:28.696 | 455839514 | 71.7296 SOL | 17.5787 SOL | 196.905m |
| Sampled reserve peak | 23:54:55.341 | 455839633 | 79.4836 SOL | 17.3827 SOL | 181.935m |
| Before largest sampled fall | 23:55:17.557 | 455839733 | 66.3559 SOL | 17.3657 SOL | 210.977m |
| Stop-trigger snapshot | 23:55:18.318 | 455839737 | 44.6679 SOL | 17.3619 SOL | 284.774m |
| Next sampled state | 23:55:19.067 | 455839741 | 33.6196 SOL | 17.3579 SOL | 346.530m |
| Sampled trough | 23:55:30.542 | 455839795 | 30.4640 SOL | 17.3539 SOL | 369.435m |
| Last frozen observation | 23:56:13.559 | 455839990 | 31.9126 SOL | 17.3487 SOL | 358.618m |
| Separate finalized account read | 23:57:33.581 | 455840327 | 30.9311 SOL | not fetched | 364.140m |

From the sampled peak to trough, actual quote reserve declined 61.67%. The later finalized account read confirms the pool still held 30.9311 SOL; it is a separate point-in-time read, not a continuation of the frozen local snapshot stream. Total token supply at that read was 941,066,861.559732.

## Transaction evidence

A bounded `getSignaturesForAddress` scan queried two pages of 1,000 signatures each. It hit the two-page cap: 2,000 unique signatures, 119 successful and 1,881 failed. The oldest returned signature was at 23:55:17 UTC and the newest at 23:57:24 UTC, so this capture does not reach the pool’s first local observation at 23:54:28.696. All 119 successful signatures in the returned pages were selected for parsed transaction retrieval. The original capture returned 116 bodies; one targeted Alchemy retry recovered the body at slot 455839742, leaving 117 returned and two unresolved. One unresolved body is at slot 455839735 (23:55:17), inside the steep sampled-break second; the other is later at slot 455839810 (23:55:33). The pool signature and transaction artifacts retain exact signatures and errors.

Among recovered transactions with both pool-vault balance deltas and block times from 23:55:10–23:55:25 UTC, there were 47 sells from 45 token owners and eight buys. Those recovered sells sent 139.233m tokens to the pool and withdrew 28.2106 SOL; buys returned 2.1437 SOL. The net observed quote-vault change in this body subset was −26.0669 SOL. Each of the 47 observed selling-owner transaction occurrences was also signed by that owner. The largest individual recovered seller outputs were:

| Seller owner | Quote out | Transaction |
|---|---:|---|
| `EN8iDPcGucFT6NffNZD8n9XwfnnbQ5CDx6ekoC4yWyqE` | 4.948926 SOL | [view transaction](https://solscan.io/tx/nvVXCiAdRWM5jCE7rdAdKuasmNmagwYE8EvWktPsqbANTEkYqRgJ3t3MFfzCQJqf44bDHUFQpZ32oj98MLnBT3i) |
| `CGr5CYVv6tG3XQ2sWHzr7a5q55LR9GuAq2eoMzD64ctd` | 2.515613 SOL | [view transaction](https://solscan.io/tx/41QTQYnM7QjfjwTNT2oMnomZtUe1DoVy25vz49EihRrUybVqhmkuQHudNJWxj4rnVYbsMNHcCL7ezRF4kjZnUCBk) |
| `9p7aE9fXaEXijLjJYej5HZfJXAo6ZcFTrygngEq243vk` | 2.205634 SOL | [view transaction](https://solscan.io/tx/3cRaLpLpM9UMuxGYMZxQibG3suKsJLryZFMQ3BDezanz6RKNNHNAVUwaesWGbWeTrozEYKzA2ZxtJKWRuanp8Q8) |
| `5hfPL9MphVk8d9FZhD7rXfRywq6FggHQfRqaeFjiWi3n` | 2.002933 SOL | [view transaction](https://solscan.io/tx/3qYVbtChantR1GcKPzRCCfFgzHoakd6RgGzkK6DemDjGcP3GWVfSt7YmaZ8xzEozYaXWhMRYoNbATrQQAwLjZabn) |
| `5MfuZ6mGnQtrxNmpyXXvmynEoYb2g7gu6dcnUGRfgDoc` | 1.556503 SOL | [view transaction](https://solscan.io/tx/2BiYn7EJ3JKjN9bmYbX4b1rJj1hTSEkAc5GE5GkP8edC6D8B2WXtDRaiLwRKgPhuRR51iP91BkS3jFpDx32ugz5d) |

Because one body from the critical second remains unresolved, these figures describe recovered transactions, not a complete incident ledger.

No `Withdraw` instruction appeared in the 117 recovered parsed transaction bodies. A later transaction at 23:57:24 emitted `SweepProtocolFee` / `SweepCreatorFee` instructions and coincided with a 0.237423 SOL quote-vault decrease. That event is outside the rapid-break interval and is recorded separately from a liquidity-withdraw instruction. The observed reserve break is accompanied by many successful sell instructions; the available evidence does not show LP removal as its cause, although the two unresolved bodies limit that negative finding.

The 76 distinct sellers observed across the recovered selected transaction bodies had no exact-address match to the saved Cvy rapid-burst seller set, the four sellers repeated in the prior 77AXS pool witness sample, the Cvy top-repeat-four addresses, or the 14-address bounded Cfiyy funding-sample set. They also did not include the Dg role-wallet addresses flagged by the parent’s cross-case funding review (`B1f…`, `BMx…`, `7pVS…`, `Bbi…`, or creator `Fabbi…`). One other tracked Dg holder, `5MfuZ6…`, did sell in the incident and is discussed below. This is a bounded address comparison; lack of overlap does not establish unrelated control, and shared funding evidence does not establish control by itself.

### Frozen curve receipt comparison and cross-case funding context

The frozen local Dg curve file contains 308 receipt events from 200 distinct user addresses. Eighteen of the 45 AMM incident sellers appear in that set (40%). This is owner membership in the saved event file, not a complete token-transfer graph. The top three AMM sellers (`EN8i…`, `CGr5…`, `9p7a…`) have no owner receipt in that file. The bounded prior-history probe for `EN8i…` returned candidate signatures but its one parsed transaction request failed HTTP 429, so this capture did not establish how those tokens reached that wallet.

The fourth-largest seller, `5hfPL9…`, had one frozen curve buy for 6,716,005.817303 tokens and no recorded curve sell; its AMM sale was the same token quantity. The fifth-largest, `5MfuZ6…`, had six curve buys totaling 11,307,171.330753 tokens and no recorded curve sell; it sold 11,307,071.330753 tokens on AMM, 100 tokens below the frozen receipt total. `5MfuZ6…` is the sole AMM incident seller among the seven selected Dg funding/holder wallets in `third_rpc_manifest.json`. The first amount matches exactly and the second nearly exhausts the locally observed inventory, but neither establishes who controlled either wallet.

Separately, the parent’s bounded funding review records three funders linking selected Cfiyy and Dg wallets: `5tzFki…` sent 0.065732 SOL to Cfiyy wallet `GV1Pw…` and Dg wallet `B1f…` in the same transaction, and 0.117922 SOL to Cfiyy wallet `4VXsn…`; `BmFdp…` sent 0.057667 SOL to Cfiyy wallet `3rro…` and Dg wallet `Bbi…`, as well as a larger transfer to Cfiyy creator `Ams5…`; `iGdFc…` sent funds to Cfiyy wallet `DhrD…` and Dg creator `Fabbi…`, `BMx…`, and `7pVS…`. The saved selected-wallet transfer artifacts and shared-funder summary are bounded samples, not exhaustive funding graphs.

There is also an unusually specific token-amount correspondence in the saved transaction bodies: in Dg, a 352,243,820.712452-token transfer from early curve buyer `FySVY5…` to `Bbi…` and a 69,207,549.760218-token transfer from early curve buyer `2XUT95…` to `BMx…` are recorded in [two Dg transactions](https://solscan.io/tx/ghAZYFuFmXQC5MxNkeXmK3bNZhRMVD1A4jfh1BscvVHiw5u115bee7Gxy8cWquUPmhF2thTnQTBE7ZAYUXq9Lma) and [the second transfer](https://solscan.io/tx/4r8HZCCTsXJQmjyfCsJ1D4uNzFfXgyc2ktM175TkEWEgn42YWCBbGGaoWDsfvib8yMXEHTjmfLMmQhbmGygW65PA). The Cfiyy transaction bodies show exactly the same two quantities arriving at `3rro…` from `95Sp1…` and at `4VXsn…` from `9ka2h…` ([352.244m](https://solscan.io/tx/5m1DPPKwZGt2MJ6dT4VtHTTCdcBAcuC5o3ZEnfbcdpTD4C7NPBw9gPv5nyNdxiSAq1RU51pwAh5fEoR6nSmC5rt7), [69.208m](https://solscan.io/tx/3vwDQWXa4qgiJGUzg9pU8Nu4W469wcJ6w6AWZ13353E1SkQ7qtTCm1tPkFDs1RyXz9Zm4CKnZqqnhLw3cikmpz6q)). This exact transfer-volume pattern plus the common funders is a stronger cross-case lead than address overlap alone. Still, the named Dg role wallets are not sellers in the recovered Dg pool bodies, and these transfers do not establish common control or connect the top three sellers to those wallets. The token receipt file has only 308 events; sellers outside that file may have received inventory through transfers.

Audit files for the bounded funding comparison: `second_rpc_incoming_transfers.json`, `third_rpc_incoming_transfers.json`, `third_rpc_funding_transactions.json`, `second_rpc_transactions.json`, `shared_funder_links.json`, and `shared_funder_summary.json`.

## Shadow ledger timing is not an on-chain exit

The frozen paper ledger records an open at 23:53:45.390 UTC and an S5 AMM hard-stop trigger at 23:55:18.318, when the sampled quote vault held 44.6679 SOL. The intent was marked ready at 23:55:18.388, 70 ms after the trigger. A later event at 23:55:19.068 is labeled `paper_filled_migrated_full`, 750 ms after the trigger, but both the open and close have `actual_fill_established=false` and `our_signature=null`. The data therefore do not show an actual submitted or confirmed exit, and should not be read as realized proceeds or PnL. The next local AMM sample, at 23:55:19.067, observed quote reserve at 33.6196 SOL; this contextualizes the paper event but does not establish its executable fill.

## Limits and evidence files

This result tests the observed liquidity path. It does not establish that the chart was intentionally manipulated, identify a common operator, or prove a live order was extracted in under 0.5 seconds. The local snapshot timestamps are observer arrival times, the RPC signature history is capped and starts after pool opening, and two transaction bodies remain unresolved. No USD conversion, trade PnL, or profitability conclusion is made. The receipt comparison and selected funding transfers have bounded coverage; they are not a complete pre-AMM ownership graph.

Evidence created for this case:

- `third_amm_collect.py` — one bounded, read-only signature, parsed-transaction and finalized-vault capture.
- `third_amm_pool_signatures.json`, `third_amm_tx_selection.json`, `third_amm_pool_transactions.json`, `third_amm_current_pool_state.json`, `third_amm_targeted_followup.json` — RPC capture outputs, including the single bounded retry and prior-history lookup results.
- `third_amm_analyze.py`, `third_amm_analysis.json` — reproducible frozen-snapshot, transaction-balance and address-overlap summaries.
- `third_ghost_amm_evidence.jsonl` and `third_MANIFEST.json` — frozen input snapshot set and prefix manifest.
