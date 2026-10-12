# Six unresolved custody witnesses

Frozen at `2026-10-12T04:11:04.545460+00:00` UTC. This is a receipt and decoder-policy audit of the six checkpoint positions; it makes no PnL, replay, or valuation claim.

## Finding

All six finalized `getTransaction` receipts succeeded. For every signature, Shyft JSON `meta.logMessages` exactly matches the stored decoded gRPC `raw_logs`; aggregated pre/post token amounts by `(owner, mint)` also match exactly, and RPC slot matches the stored slot. The receipts do not show missing or contradictory terminal balance/log data. They show three distinct causes behind the common unresolved label: ordered target-token custody transfers in router paths, one outside-Pump WSOL transfer plus a target self-transfer, and two Pump argument-layout/version cases.

| Mint | Receipt operation or decoder status | RPC/local parity |
|---|---|---|
| `3WzM1ZUm4xdrdsvvvseSXvLoMD57fRvBAwbjgcnhpump` | target TransferChecked 29958460988407 raw: `4f2eU3GrdgsvEJh2icQ2TcaPx84CDnpdGgg9FpdSUCRi` owner `9ikSKkTCz6QWQKnwKChpefNkw9tAyzvj7XeDeF6UX9Pe` → `AZh8tLs2xRN7AtCX1Ydy5C8Nw6rWvAiNA5CkYodtqqT2` owner `AEA5we6SM3WQ1S5VikLCUhpkcRrYZypqnQRvdLC9Kmgv`; transient destination consumed by Pump Sell then closed. | slot 455904267; logs equal; pre/post aggregates equal |
| `12De7WDKSxunPaDmFYuogrz4MVvWpP2E6z25tv8Jpump` | target self-transfer 1559880175332 raw from/to `AJ93oeEvcdZQWbH9Cs2npDPwgoF13LZ8kSzeZpkto9Np` (zero delta); outside-Pump WSOL transfer 992543 raw. | slot 455904305; logs equal; pre/post aggregates equal |
| `BroUJVHA18XxsNtBcAq17PFd176HLkrmUJxj2Y9Wpump` | direct Pump Sell; no outside-Pump target transfer; `18` argument bytes rejected by current Sell layout (16 only). | slot 455905240; logs equal; pre/post aggregates equal |
| `3dT6s4kz4QvaNr21jjLBYX4JJgKk63mRSEkreTHBpump` | DFlow target transfer outside Pump 2364197218502 raw: `4R7KBuFcBWEAz7TFL7stn9GnGZyLyLVnh9iSZniSRSEE` → `DWbXbXfBTDzBhRNGEoQwBweVqJvzvSCfpjmWaYL4WSo5` after Pump output; route also moves USDC/WSOL. | slot 455906000; logs equal; pre/post aggregates equal |
| `GRkCgRJ3hJQRDUAp8AdzG1memXkzWzyzMnuEtcHapump` | target TransferChecked 21088680739068 raw: `55mXegLCJLk1zkdSaZFHEAN4QrZ2i4k5z52sPduKoePr` owner `BPUhUcAtPp4bA2dAEJTJrzhbficSAch6Zc6tHWdXkrTc` → `C59Zz4tPmD6VUEUccXvEPA2q6yhAU7ysTazDZ3STdaxJ` owner `GCPws8xQALDTuccgrzRv2AmuqEUNbLNn1VNvqV9zQrzd`; transient destination consumed by Pump Sell then closed. | slot 455906305; logs equal; pre/post aggregates equal |
| `7DVAPYQ2ip5XwPq7Nf6CHndtZk7mBqjWx2AUve6kpump` | direct BuyExactQuoteInV3; no outside-Pump target transfer; `16` argument bytes accepted by current source, stored replay flag unsupported. | slot 455906435; logs equal; pre/post aggregates equal |

## Case interpretation

- `3Wz…` and `GRk…`: Before Sell, a top-level Token-2022 `TransferChecked` moves the full target amount into a newly created transient token account. The source token-account owner differs from the transient account owner/authority. Pump then consumes that amount and closes the transient account. This is an ordered custody path, not a same-owner ATA shuffle.

- `12De…`: The router’s target-mint `TransferChecked` uses the same source and destination account, so it has no target-balance effect. Separately, the receipt shows an outside-Pump WSOL transfer of 992,543 raw units from a temporary WSOL account to a destination account. The stored custody scope includes both target and WSOL; the target self-transfer is a no-op candidate for exclusion from custody-change accounting.

- `3dT…`: DFlow executes Pump BuyV3, receives target tokens into a temporary target token account, then transfers the same 2,364,197,218,502 raw units from that account to the final recipient outside the Pump invocation. USDC and WSOL route operations are present too.

- `Bro…`: The only target balance-changing transfer is inside the direct Pump Sell. Its Sell V1 instruction has 18 argument bytes. Current source accepts exactly 16 for Sell, so the current tree still rejects this receipt layout; this is decoder-layout coverage, not an observed external target movement.

- `7DVA…`: No target transfer occurs outside the direct Pump BuyExactQuoteInV3 invocation. It has 16 argument bytes, accepted by current source. The frozen local observation nevertheless records `limits_complete=false` and an unsupported-layout reason, so the saved row reflects another processing state. Active deployed decoder identity/activation was not verified.

## Method and artifact map

`raw_rpc_witnesses.json` holds the bounded six-signature Shyft `getTransaction` response pairs (`json` and `jsonParsed`) using finalized commitment and `maxSupportedTransactionVersion=1`. `index.json` contains only the matching six checkpoint and local observation rows, raw Pump argument bytes, owner/mint balance comparisons, and parsed token operations with instruction location, program, stack height, mint, source/destination owner and raw balances. No endpoint or credential is stored.

Created-and-closed accounts can be absent from terminal pre/post token-balance arrays. Their mint/owner and ordered transfer are therefore read from parsed transfer and account initialization/close instructions. A successful, internally consistent receipt does not by itself mean the local custody or decoder policy can account for every operation.

Counterfactual support must preserve token-account amount/authority checks and caller guards as well as net owner balances. A self-transfer having zero net token movement is not proof that its guard cannot fail after an intervention. Likewise, matching the observed terminal balances is not sufficient to permit arbitrary router paths. The retained paper state requires receipt-backed catch-up from its last accepted group; clearing the error field alone would skip that history.
