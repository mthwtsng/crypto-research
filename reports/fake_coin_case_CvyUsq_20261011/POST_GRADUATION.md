# Cvy post-graduation AMM trace

## Finding

The observed collapse was real and severe at the pool level. During a 581 ms interval at 23:30:45.557–23:30:46.138 UTC, the spendable WSOL quote vault fell from 80.8343 SOL to 2.8808 SOL (96.44%), while the token vault rose from 180.39 million to 875.35 million Cvy. The PumpSwap virtual quote reserve stayed at 17.3702 SOL during those samples. That is consistent with a near-floor collapse, but it does not independently verify the reported $63k-to-$4k market-cap values: this trace has no historical SOL/USD conversion, and virtual quote is not spendable vault liquidity.

The largest local spendable-quote reserve sample was 90.7733 SOL at 23:30:29.105 UTC. In the frozen local snapshot window through 23:38:21.633 UTC, the trough was 1.6040 SOL at 23:34:07.859 UTC and the last sample was 1.6108 SOL. That is a 98.23% peak-to-trough and 98.22% peak-to-last reserve decline. A separate finalized account read at 23:45:39.423 UTC (slot 455837059) measured 1.294647602 SOL in the quote vault; it is later and distinct from the frozen local snapshot series.

The immediate collapse is explained by a broad sell wave in the observed transaction slice, rather than a detected LP-withdrawal event. The 122 successful transactions with both pool-vault balance changes in slots 455832951–455832959 comprise 120 token sells from 120 distinct token owners/signers and two buys. Sellers moved 707.788 million tokens into the pool and received 80.05925 SOL gross; buys returned 0.48884 SOL and removed 20.959 million tokens. Net quote-vault depletion was 79.57040 SOL, from 82.7230 to 3.1526 SOL across the slice (96.19%). No withdrawal instruction was observed in these slots. This is evidence of a severe sell-driven reserve collapse, not by itself evidence of fraud, coordination, or creator intent.

Most observed AMM sellers had previously held Cvy on the bonding curve: 115 of 120 seller owners appear in the target’s curve-wallet ledger; 99 had positive net token balances at curve completion; and 43 sold an amount exactly matching that positive pre-graduation net balance. The Cvy creator was not among the burst sellers or their signers in this slice. Those observations do not establish who controlled or coordinated the wallets.

## Reserve and price-proxy observations

The local PumpSwap snapshot stores actual quote-vault reserves and virtual quote reserves separately. A formula proxy, `(actual quote + virtual quote) / base reserve × token supply`, fell from 524.95 SOL at the first rapid-collapse sample to 22.31 SOL at the last sample. This is a SOL-denominated pool-implied proxy, not a USD valuation. The actual quote reserve fell 96.44% over the same 581 ms, while virtual quote was unchanged. Across the frozen peak/trough pair, virtual quote changed by only −0.21% even as actual quote fell from 90.7733 to 1.6040 SOL.

| Observation | UTC | Actual quote vault | Virtual quote | Base tokens in pool |
|---|---:|---:|---:|---:|
| Pool opening sample | 23:24:34.883 | 74.0753 SOL | 17.5845 SOL | 191.845m |
| Actual quote peak | 23:30:29.105 | 90.7733 SOL | 17.3949 SOL | 163.700m |
| Rapid decline start | 23:30:45.557 | 80.8343 SOL | 17.3702 SOL | 180.388m |
| Next sampled state | 23:30:45.776 | 54.0518 SOL | 17.3702 SOL | 248.133m |
| Rapid decline end | 23:30:46.138 | 2.8808 SOL | 17.3702 SOL | 875.348m |
| Frozen-window trough | 23:34:07.859 | 1.6040 SOL | 17.3584 SOL | 934.862m |
| Frozen-window last sample | 23:38:21.633 | 1.6108 SOL | 17.3583 SOL | 934.534m |
| Separate finalized vault read | 23:45:39.423 | 1.2946 SOL | not fetched | 939.002m |

The reported dollar market-cap path is therefore qualitatively consistent with the observed reserve/price collapse, but its exact endpoints are unverified here. A current finalized token supply read was 964,252,793.000417 tokens.

## Transaction evidence

Pool signatures were retrieved in two pages of 1,000 and 899 entries, covering the observed opening through the 23:45:26 UTC refresh: 1,899 unique signatures, of which 1,213 succeeded and 686 failed. Transaction bodies were selected for the opening, the reserve-peak/trough interval, and all successful pool activity after the trough, within the 400-body limit. Of 331 selected successful transactions, 329 bodies were returned. Two requests remained rate-limited (HTTP 429), at 23:30:46 UTC, slot 455832960, and 23:31:25 UTC, slot 455833137. All 122 successful transactions in the rapid-collapse slice were present; neither unresolved body is in that slice. Failed transactions were not fetched because they do not change confirmed pool reserves.

The first five sell witnesses in slot 455832954 alone reduced the quote vault from 80.8343 to 54.0518 SOL. Each seller was a distinct owner and transaction signer:

| Seller owner | Quote out | Tokens sold | Transaction |
|---|---:|---:|---|
| `3E5C4bw4MmAXZK9f8D5PFqGJrxqauCUFtfvQ7jD6oha2` | 4.035819 SOL | 7.747m | [`2KCcFPFV…QreLMEV`](https://solscan.io/tx/2KCcFPFVQN8iSAcJVF2BAcbik818Lhf5b9oD9yA9cYAY3s6CrLaP5K8eqFfeRos9iyuuiCVSc91xdVxn2QreLMEV) |
| `mMpEUcCgvHmdXvkrawYszRZpXTVfp1E2rDCc4vtGfdw` | 5.733421 SOL | 12.223m | [`3xBdC6tE…o3T6AZu`](https://solscan.io/tx/3xBdC6tEMQSM94gcjbSLMmSKownz53Haisk7yUypZYXnBSYdDiqMus63WGhnYiwyDTn9qBd5MKQMHSKAo3gT6AZu) |
| `53MN5hAAGHu8Q8HM8ZCaenWYsBma4qTHD9Lp6ETKdLrL` | 6.760975 SOL | 16.622m | [`3KfCcakp…HRW2pJzs`](https://solscan.io/tx/3KfCcakpCyMBuo9gZDEpWKR6fxuPp33a6fYVQoKPw41sh56TDStroeY3oVF3LZQSubCJW87myuQoo9X9HRW2pJzs) |
| `CGbLazQt5HXNPawzFct36WeFwj8dL4vGUd8KRHSJ1iCX` | 6.162394 SOL | 17.711m | [`5t5kJ5Yx…ktujov7ZE`](https://solscan.io/tx/5t5kJ5YxnSTm3qx8Y1A8U6yWzWmG4BH1NHw9venv3dFn3mf4A3oqyBW5ggCLJt5dghyTvCucU1esWZnktujov7ZE) |
| `98MLcc4UVzeLaDWckcBUCMcwS5CgSeqAjC4g2JNQ714c` | 4.089860 SOL | 13.442m | [`51XWDoQe…KXsipjb`](https://solscan.io/tx/51XWDoQefBZXGiD72PatkgdsekcQvZeubwRrnHq2y5gibSLsTDAHX7LDsqfmsvTZVSzsf7ibZWnPpxY3yKXsipjb) |

These five sells total 26.7825 SOL, about one third of the collapse-slice gross sell proceeds. The wider burst involved 120 observed sellers, so the reserve loss was not attributable to a single observed seller. Wallet addresses are not proof of distinct people.

## Earlier pool overlap and other observed collapses

A bounded witness sample for an earlier pool, `Bt8gmEqPWojBQqVsF4BuBNYKwTCX7JQevWb81Cyof4Yk` / `77AXSFnjgfgsT261R8wkPSwSe94BgheBS9hbLiQVpump`, contains successful sells by four wallets that later sold Cvy: `98MLcc…`, `CGbLaz…`, `53MN5h…`, and `mMpEUc…`. The witness times are 23:06:10–23:06:11 UTC, before Cvy creation at 23:13:18 UTC. Selected pre/post quote-vault balances include 77.3855→68.6357 SOL for `98MLcc…`, 50.4799→42.0227 SOL for `CGbLaz…`, 22.9681→22.1370 SOL for `53MN5h…`, and 10.9385→10.1967 SOL for `mMpEUc…`. This is a bounded sample of prior-pool transactions, not a complete prior-pool tape or proof of common control or coordination.

An outcome-selected scan of the local authenticated/post-exit snapshot file found three other pools whose sampled actual quote reserve fell at least 90% from its observed peak to its last sample:

| Pool / mint | Peak sample | Last sample | Peak → last actual quote reserve | Decline | Samples |
|---|---|---|---:|---:|---:|
| `B5BroH6…QyC6qx` / `p9CMs7…pump` | 22:09:23.745 | 22:22:06.582 | 135.8441 → 11.3470 SOL | 91.65% | 465 |
| `C91wG1…P2jbT` / `7rhg1p…pump` | 23:35:02.119 | 23:50:46.461 | 65.4956 → 6.1430 SOL | 90.62% | 304 |
| `3g4Mfs…MzNJQ` / `Cfiyy9…pump` | 23:39:01.967 | 23:54:15.454 | 78.5799 → 4.5630 SOL | 94.19% | 234 |

These are descriptive outcomes selected because the reserve had already collapsed. They are not a random cohort, causal comparison, predictive filter, or strategy backtest. The snapshot file is not a complete transaction tape for these pools. The third pool’s last row is a local `POST_EXIT_AMM_SNAPSHOT`; no independent RPC verification is included in this cross-pool screen.

## Limits and artifacts

The trace establishes actual quote-vault depletion and authentic sell transactions around the collapse. It does not establish fraudulent intent, common control among sellers, creator benefit, or the exact USD market-cap path. No liquidity-withdraw instruction was found in the observed collapse slice; withdrawals outside that slice are not ruled out. Transaction-body coverage is focused rather than complete for all 1,213 successful signatures, and local snapshot sampling is sparse.

Reproduction and evidence files in this directory:

- `amm_collect.py` — bounded RPC collector; endpoint values are read from `AGENTS.md` and are not written into the report.
- `amm_pool_signatures.json`, `amm_tx_selection.json`, `amm_pool_transactions.json` — signature coverage, selection, and parsed transaction bodies.
- `amm_current_pool_state.json` — separate finalized vault/supply state read.
- `amm_analysis.py`, `amm_analysis.json` — local deterministic summary and reserve/seller calculations.
- `amm_other_deep_declines.json` — outcome-selected cross-pool snapshot summaries.
- `prior_77AXS_pool_sell_witnesses.json` — bounded earlier-pool witness set.
