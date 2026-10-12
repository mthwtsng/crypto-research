# Frozen custody-recovery evidence

Read-only input package for the recovery runner. It preserves the two target shadow positions and receipt tape without editing runtime state, strategy code, or executables. No PnL or cash-reset claim is made.

## Frozen checkpoint and tape

- `input_checkpoint_targets.json` preserves the failure-time target curves, both shadow ledgers (`observed`, `state`, historical/simulated balances, group counts and error strings), position/fill anchors, intents, and source anchors. Source checkpoint: `data/ghost_runtime_state.json`, VM `ghost-v2-20261012T041817`, saved at `1791779101008` ms, 4,850,189 bytes, SHA-256 `ac3eaf4b43f559bcb65d9810a6a8ee2c00b6be331e85ddbe63740490b887f7cc`.
- `input_checkpoint_current_targets.json` and `input_checkpoint_current_manifest.json` preserve the later current target curves and their receipt cutoffs. Current checkpoint source SHA-256 `a8a6c980d5fbaf33546614fd705c1721de2698c389133a10c6f0294393eb4314`, saved at `1791779675900` ms, VM unchanged. The live file continued to advance during this audit; these are the exact captured target cuts, not a claim that the source file stopped changing. The current target curve objects had no `shadow_curve`; use the failure-time snapshot above for the frozen shadow ledgers.
- `input_target_receipt_tape.json` contains 664 compact target-mint observations: 492 Gxv rows through `[455916417,38]` and 172 DNo rows through `[455914288,331]`. Each row preserves signature, slot/index, receipt time, target events, target token balances, program IDs, custody/coverage flags, source file line order, and a hash/count for omitted raw logs. The captured source prefix SHA-256 is `8db20262e191163704820d89c845be2d89becf324083575ec4ec9dc0d4d85661`; the source appended during capture, but all target observations through the checkpoint cutoffs were present in that prefix.

## Gxv4V2j7…pump: earliest post-anchor counterparty baseline

The frozen shadow has `groups_replayed=9`. Its observed reserve tuple exactly matches receipt `3g5KehCP…` at slot 455912382, transaction index 82, received at `1791778776320` ms: `(rsol=21090748318, rtokens=350155366006770, vsol=51090748318, vtokens=630055366006770)`. This is the last accepted source observation before the shadow error.

The first target-mint receipt after that anchor is `3jTQsqDM…` at slot 455912401, index 375, received at `1791778780468` ms. It is a finalized, successful Pump Sell v1 by Eh4V, with complete sell limits and `7,137,155,407,498` tokens. The curve-owner AXim prebalance is `557,055,366,006,770`, exactly equal to its last local postbalance at the anchor. Both AXim and Eh4V keys are absent from the frozen historical and simulated balance maps; Eh4V has no earlier local postbalance in the target observation tape. The first receipt’s postbalance moves those tokens to the curve owner.

Shyft `getTransaction` for `3jTQsqDM…` identifies Eh4V’s token account as `HuuRBuHZyDVdM5huaJbuwvcy3DXeyqQDG5N4zpR3raPY`. Its `getSignaturesForAddress` history before the sell returns one prior signature, `4wtno3QET…`, at slot 455911963/index 1228. That successful transaction is a Pump `BuyExactSolIn`; its postbalance is exactly `7,137,155,407,498` for Eh4V. The account’s latest prior transaction is 419 slots before the paperfill anchor, and there is no token-account transaction between that anchor and `3jTQsqDM…`. The prior buy is absent from `ghost_observations.jsonl`; the first local Gxv target observation in the captured file is at slot 455912039. This supports a pre-existing, unchanged actor balance at the paperfill boundary, rather than an intervening gift or transfer. The first post-anchor sell’s observed prebalance can seed the missing actor equally in both ledgers.

The earliest later Gxv observation whose custody-missing list includes the Gxv mint is `2hnSCUGqy…`, slot 455912523/index 215. Its local parser marks token-balance coverage known but custody operations incomplete. The raw finalized transaction shows a top-level `Aveaiu…` RouteSwap with a successful nested Pump `BuyExactQuoteInV2`; it is a separate later routed-invocation coverage case, not the first missing actor baseline at `3jTQsqDM…`.

## DNoBMr…pump: explicit first custody failure

The frozen DNo shadow has `groups_replayed=2`; its observed reserve tuple matches `5dndaJso…` at slot 455912607/index 38. A finalized full-block response for that slot orders `5dndaJso…` at block transaction position 38 before `4pHSdnk…` at position 284.

The shadow error names `4pHSdnk…`. Its Pump Sell v1 instruction is complete: the base58 instruction data decodes to 24 bytes, and the local parser reports `limits_complete=true`, `token_amount_raw=18074490387359`, `min_quote_output_raw=829435491`, and no unsupported reason. The missing custody change is a separate top-level Token-2022 `TransferChecked` before the Pump Sell: 18,074,490,387,359 tokens move from old token account `4WZLhW1M6ddiCpqN3GhDFjXW2CVfuVQcr7Qw1C4dVwu` (pre owner E7hh) into newly created account `3Fdi31gc4qTA31eiBznVt876AA3jmejxBXuUjoaARuBH` (owner/signer GvwY). Pump then sells from the new account, which is closed afterward. The prior accepted receipt `3BV4…` created E7hh’s exact 18,074,490,387,359-token balance; that amount matches both frozen historical and simulated maps and the first-failure transaction’s E7hh prebalance. This is an unsupported account-transfer/custody path, not an incomplete Pump Sell argument decode.

## RPC evidence files

All Shyft request metadata omits endpoint and credentials. Raw response bodies and body hashes are saved for the primary proof transactions and block query:

- `input_rpc_g_first_post_anchor.json` — exact `getTransaction` response for `3jTQsqDM…`, body SHA-256 `f03f1fe63856a4b1ab05a3644e08af8435d387949e866e38b1e7c46d2134769e`.
- `input_rpc_g_first_actor_ata_history.json` — exact ATA `getSignaturesForAddress` response (limit 15), SHA-256 `d4b9a439d41d41af4c5a216ed32ba930eb2a45b369beb56c6dba6792cd10c14d`.
- `input_rpc_g_first_actor_last_prior.json` — exact `getTransaction` response for `4wtno3QET…`, SHA-256 `9cf5ce0ffbb2b28094db39dffade252a038564c6a32562ef44695c86342b1589`.
- `input_rpc_g_first_custody_gap.json` — exact `getTransaction` response for later routed signature `2hnSCUGqy…`, SHA-256 `c93ceffb641be787066b9335cef19267c74e0b531b0e4ea2fb9c414657beaa59`.
- `input_rpc_d_first_failure_raw.json` — exact `getTransaction` response for first DNo failure `4pHSdnk…`, SHA-256 `6107719418874a3f8f0c6cd248772176be4bacf0568b2c2e1a4769f160021c75`.
- `input_rpc_dno_same_slot_block.json` — exact finalized `getBlock` response for slot 455912607, SHA-256 `92fd9630f714df6eb246f383c08af25ff9c062a14898fbbf8645268b99c2d858`.
- `input_rpc_first_failure.json`, `input_rpc_gro_buy.json`, and `input_rpc_gro_signatures.json` retain the initial structured first-failure and entry-anchor probes. The first-failure raw response is also preserved separately above.

