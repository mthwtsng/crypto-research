# Observed execution costs for the 22-wallet sample

This is a receipt-based cost audit, not a trade replay, profitability result or edge claim. It uses finalized captured history through the shared freeze **2026-10-12 04:12:05 UTC**. Six histories reached their natural end before the 10-page cap; sixteen are explicitly truncated at that cap and cover different date ranges. The 200-receipt sample per wallet is selected by the smallest SHA-256 signature hashes among exact authenticated trades, independent of outcomes.

An authenticated row requires a successful official-IDL Pump trade event, `event.user` present as a transaction signer, a native-SOL quote, one changed owner-held mint, and exact equality between the event token amount(s) and the owner's pre/post token delta. The displayed Pump `fee` and `creator_fee` are protocol trade charges, separate from the transaction `meta.fee` and provider-recipient transfers. `buyback_fee` is a component of `fee`, not an additional charge.

Provider-recipient transfers are counted only when the enhanced receipt parses a System transfer from the trade owner to a matching account. The locally configured recipient map comes from [bot_types.rs](../../src/bot/bot_types.rs); route used cannot be proven from the destination alone. Published addresses were checked against [0slot's tip-account list](https://0slot.trade/docs.php), [Jito's tip-account documentation](https://docs.jito.wtf/lowlatencytxnsend/), and [Helius Sender's account list](https://www.helius.dev/blog/zero-slot). Other System outflows are excluded from tip totals. These are minimum observed transfer amounts, not a claim that every provider or account family has been identified.

## Per-wallet capture and sampled cost

`observed overhead` is calculated per receipt as the wallet-paid `meta.fee` plus any negative rent-adjusted residual against the Pump event's expected cash delta. Positive residuals are reported separately as unclassified net inflows and are not treated as costs or offsets. Negative residuals can include unrecognized recipients, so they are not assigned to tip providers. Configured and externally published recipient transfers are shown separately as attribution evidence. Medians of paired per-receipt overhead need not equal the sum of component medians.

| Wallet | History capture | Exact receipts | Sample | Median network fee (SOL) | Median published tip (SOL) | Median configured tip (SOL) | Median fee + adjusted residual outflow (SOL) | Median Pump fee / creator fee (SOL) | Payer-failed tx / fees (SOL) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| broke bot lol | complete / 2,856 rows | 401 | 200 | 1.1667e-05 | 0.0 | 0.0 | 0.002844255 | 0.004691359 / 0.001481482 | 842 / 1.059174675 |
| Cbot7 | truncated_page_cap / 10,000 rows | 9,317 | 200 | 9.596e-06 | 0.00011 | 0.00011 | 0.000119596 | 0.003341383 / 0.001055174 | 583 / 0.005594468 |
| russianbot | truncated_page_cap / 10,000 rows | 8,512 | 200 | 5.9886e-05 | 0.0 | 0.0001 | 0.000159886 | 0.000885089 / 0.0002795025 | 1,414 / 0.063465365 |
| snipebot | complete / 6,871 rows | 2,725 | 200 | 0.001005 | 0.0 | 0.0 | 0.002005 | 0.018765433 / 0.005925926 | 2,935 / 0.528907730 |
| nbot | truncated_page_cap / 10,000 rows | 57 | 57 | 2.5e-05 | 0.0 | 0.00011 | 0.000135 | 0.009324998 / 0.002944736 | 9,824 / 0.961028812 |
| bot12 | complete / 8,130 rows | 661 | 200 | 0.001005 | 0.0 | 0.0 | 0.010107614 | 0.010301761 / 0.003253188 | 4,961 / 34.436005402 |
| bot | truncated_page_cap / 10,000 rows | 1,909 | 200 | 0.000156148 | 0.0 | 0.0 | 0.005587821 | 0.0047862775 / 0.0015114565 | 1,819 / 9.344917682 |
| 1 sol bot | truncated_page_cap / 10,000 rows | 8,363 | 200 | 0.000105 | 0.0 | 0.0 | 0.000205 | 0.005611762 / 0.001772136 | 1,290 / 0.287419000 |
| Snippebot | truncated_page_cap / 10,000 rows | 1,467 | 200 | 0.000105 | 0.0 | 0.0 | 0.000205 | 0.010088055 / 0.003185702 | 7,926 / 14.588537536 |
| Bottom Bidder | truncated_page_cap / 10,000 rows | 9,051 | 200 | 0.00091216 | 0.0 | 0.00103 | 0.001941787 | 0.005437285 / 0.001717038 | 350 / 0.272505148 |
| bottty | truncated_page_cap / 10,000 rows | 8,598 | 200 | 0.000105 | 0.0 | 0.0 | 0.000205 | 0.009382717 / 0.002962963 | 1,214 / 0.327485000 |
| bottimus | truncated_page_cap / 10,000 rows | 0 | 0 | n/a | n/a | n/a | n/a | n/a / n/a | 526 / 0.962400049 |
| asdasd | truncated_page_cap / 10,000 rows | 8,664 | 200 | 0.000105 | 0.0 | 0.0 | 0.000205 | 0.009382717 / 0.002962963 | 1,166 / 0.315305000 |
| bot | truncated_page_cap / 10,000 rows | 7 | 7 | 3.5e-05 | 5e-05 | 5e-05 | 8.5e-05 | 0.009595718 / 0.003030227 | 9,971 / 0.069610535 |
| insane bot | truncated_page_cap / 10,000 rows | 0 | 0 | n/a | n/a | n/a | n/a | n/a / n/a | 9,182 / 0.380681642 |
| bot | complete / 7,009 rows | 2,861 | 200 | 0.001005 | 0.0 | 0.0 | 0.002005 | 0.018765433 / 0.005925926 | 3,120 / 0.420695365 |
| boooooot | truncated_page_cap / 10,000 rows | 104 | 104 | 0.000105 | 0.0 | 0.0 | 0.000205 | 0.007321276 / 0.0023119825 | 8,271 / 5.202037416 |
| cbot14 | complete / 1,882 rows | 831 | 200 | 0.001405 | 0.0 | 0.0 | 0.020805 | 0.0140855495 / 0.004448069 | 211 / 0.175201651 |
| Botty | truncated_page_cap / 10,000 rows | 8,492 | 200 | 0.000123888 | 0.0 | 0.0 | 0.000215 | 0.0095276675 / 0.0030087375 | 1,407 / 0.174310416 |
| 1sol bot | complete / 4,014 rows | 3,594 | 200 | 9e-05 | 0.001 | 0.001 | 0.00109 | 0.009382717 / 0.002962963 | 290 / 0.026100000 |
| bot | truncated_page_cap / 10,000 rows | 8,979 | 200 | 0.0001249755 | 0.0002 | 0.0002 | 0.000217022 | 0.004691359 / 0.001481482 | 721 / 0.066474615 |
| Bot | truncated_page_cap / 10,000 rows | 24 | 24 | 1.8996e-05 | 0.0 | 0.0 | 0.002668095 | 0.009382717 / 0.002962963 | 9,905 / 0.184103585 |

## Russianbot and Bottom Bidder

On the hash-selected exact-trade samples, Russianbot's median paired observed overhead was **0.000159886 SOL** (p95 0.001059886); **all 200/200** sampled receipts were at or below the 0.001505 SOL base reference. Only **111/200** residuals reconciled to a configured provider-recipient transfer; the rest remain unclassified but are included as outflows. Bottom Bidder's median was **0.001941787 SOL** (p95 0.002036432), with **168 of 200** receipts above that base. The overhead uses each receipt's own payer fee plus any negative rent-adjusted event-cash residual, so unknown net outflows contribute without being called tips; positive residuals are kept separate as unclassified inflows. Russianbot's reported ticket is 0.095 SOL: the study's 0.001505 / 0.002916 SOL reference costs would equal 1.58% / 3.07% of that ticket. These figures compare explicit user-supplied assumptions with observed per-leg costs; they do not estimate profitability. The captured wallet samples differ in coverage and routing, so this is descriptive rather than a controlled sender comparison.

| Wallet | Side | Sample n | Median network fee (SOL) | Median residual outflow (SOL) | Median paired overhead (SOL) | p95 paired overhead (SOL) |
|---|---|---:|---:|---:|---:|---:|
| russianbot | buy | 102 | 5.9886e-05 | 0.0001 | 0.000159886 | 0.001059886 |
| russianbot | sell | 98 | 3.2443e-05 | 0.0001 | 0.000132443 | 0.000132443 |
| Bottom Bidder | buy | 104 | 0.000908807 | 0.00103 | 0.001938499 | 0.001942869 |
| Bottom Bidder | sell | 96 | 0.001000965 | 0.00103 | 0.002030358 | 0.002037648 |

The source-checked examples below show why `meta.fee` alone and outbound transfers alone each miss part of execution cost. They are case checks, not added to the hash-selected samples:

| Wallet / signature prefix | Pump event SOL amount | Pump `fee` + `creator_fee` | Rent reserve change | `meta.fee` | Provider-recipient transfer | Adjusted residual | Observed overhead |
|---|---:|---:|---:|---:|---|---:|---:|
| russianbot / `6WbajoMNCCMP` | 0.121770265 | 0.001156818 + 0.000365311 | 0.001513840 | 0.000059886 | 0slot 0.000100000 | -0.000100000 | 0.000159886 |
| Cbot7 / `4fi1SbrMj7S4` | 0.140000000 | 0.001330000 + 0.000420000 | 0.001513840 | 0.000009596 | 0slot 0.000110000 | -0.000110000 | 0.000119596 |
| Bottom Bidder / `3azUGwM3ReSy` | 0.635533779 | 0.006037571 + 0.001906602 | 0.001513840 | 0.000908037 | Nozomi 0.001030000 | -0.001030000 | 0.001938037 |

Russianbot's checked 0slot destination matches the published 0slot address list. Cbot7's destination also appears there. Bottom Bidder's recipient is mapped to Nozomi by the project's configured account list; the provider route itself is not inferable from a successful transfer. Pump `fee` and `creator_fee` are event-level protocol charges and are distinct from `meta.fee` and the residual. No unclassified residual is labeled as a tip.

## Residual and payer failures

For each sampled exact trade, the script compares owner native-plus-WSOL balance change (adjusted for the change in rent held by that owner's token accounts) to the official Pump event cash amount. It adds back `meta.fee` when the trade owner paid it. A residual is considered reconciled only when it equals the negative of parsed configured-recipient transfers within one lamport. Negative residuals unmatched to configured recipients remain unexplained and contribute to the overhead proxy; positive residuals are shown separately as unclassified net inflows. Russianbot's paired cost is not the lower identified-recipient-only subtotal: only receipts with a matching configured account transfer receive that label. Full captured-history payer-failed fee sums are listed separately above, including failed receipts beyond the 200-trade samples.

bottimus (`bcnz...`) payer-linked child trades are stored separately in JSON. Child event-user token ownership is kept distinct from the payer's network fee/tip; they are not counted as direct bottimus-owned trade receipts.

## Limits

The enhanced API capture stopped at 10 history pages per wallet where that cap was reached. Consequently, failed-fee totals are complete only for each wallet's captured pages, and wallet medians are not aligned to a common interval. The SHA-256 sample is a reproducible descriptive sample, not a randomized population estimate. Provider recipient identity does not reveal the sender route; locally configured provider accounts beyond published lists are labeled as configured rather than independently verified. No hypothetical fill, PnL, or strategy edge is estimated.
