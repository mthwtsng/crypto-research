# 22-wallet receipt-authenticated entry patterns

This is a descriptive prefix study of **348 frozen target buys** across **18 wallets** and **310 mints**. It reports observable reserve, order-flow and preceding-wallet states; it does not estimate profitability, backtest a copy policy, or prove that a later wallet copied an earlier one.

Sample limit: up to **24 distinct mints per wallet** (fixed-hash selection, independent of outcome). Finalized RPC cutoff: slot 455910302 at blockTime 1791778325 (2026-10-12T04:12:05Z).

## Coverage and authentication

- Successful SOL-quoted Pump trades are decoded with the strict IDL-discriminator and successful invocation-ancestry decoder; target identity is `TradeEvent.user`, kept separate from fee payer.
- Authenticated creation was found in **193** prefixes and missing in **155**. A two-page cap means missing genesis is incomplete history, not evidence of a newly created token.
- Prefixes used official IDL instruction-to-curve mapping for **140** entries and mint-address fallback for **208**; fallback histories can be less complete if the mint address did not index curve trades.
- Entry pre/post reserves are reconstructed from the exact authenticated event SOL/token inputs. The independent last-prior-event continuity check matched real SOL, virtual SOL and virtual-token reserves in **342/344** checked prefixes.
- Same-prefix controls produced **1980 target-control matches** over **1980 unique control signatures**. Matches are not independent observations; controls are selected by the stated prior-time/reserve window.
- Same-second transactions are never ordered by blockTime: all prefix decisions use `(slot, transactionIndex)`. Same-slot rows lacking either index are excluded from the strictly prior set and counted as ambiguous.

## Per-wallet clues

Median reserve and flow values summarize only selected, covered prefixes; drawdown is against the highest authenticated pre-entry marginal-reserve price visible in that prefix. These are descriptive state ratios, not executable price returns.

| Wallet | Selected | Genesis found | Median pre real SOL | Median buy SOL | Median observed drawdown | Median outside net SOL, last 5 slots | Median unique buyers, last 5 slots | Two-buyer recoveries |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| broke bot lol | 13 | 9/13 | 14.18 | 0.99 | 0.0% | 4.49 | 2.0 | 2/13 |
| Cbot7 | 24 | 13/24 | 8.39 | 0.45 | -2.4% | 3.34 | 5.0 | 3/24 |
| russianbot | 24 | 18/24 | 8.44 | 0.09 | -7.1% | 1.93 | 4.0 | 4/24 |
| snipebot | 24 | 20/24 | 10.52 | 1.98 | 0.0% | 4.28 | 4.0 | 6/24 |
| nbot | 4 | 2/4 | 20.04 | 3.36 | -6.3% | 4.84 | 4.5 | 1/4 |
| bot12 | 20 | 4/20 | 22.95 | 1.47 | -3.7% | 3.61 | 3.0 | 3/20 |
| bot | 4 | 2/4 | 11.97 | 5.68 | -0.9% | 0.18 | 3.0 | 0/4 |
| 1 sol bot | 24 | 2/24 | 20.67 | 0.49 | -19.5% | -1.23 | 4.0 | 2/24 |
| Snippebot | 17 | 17/17 | 2.80 | 2.07 | 0.0% | 0.79 | 1.0 | 0/17 |
| Bottom Bidder | 24 | 15/24 | 8.47 | 0.56 | -10.5% | 1.10 | 2.0 | 0/24 |
| bottty | 24 | 13/24 | 9.04 | 0.99 | -19.0% | 0.35 | 3.0 | 1/24 |
| bottimus | 0 | 0/0 | — | — | — | — | — | 0/0 |
| asdasd | 24 | 8/24 | 8.68 | 0.99 | -21.4% | 0.98 | 2.5 | 1/24 |
| bot | 0 | 0/0 | — | — | — | — | — | 0/0 |
| insane bot | 0 | 0/0 | — | — | — | — | — | 0/0 |
| bot | 24 | 22/24 | 8.99 | 1.98 | 0.0% | 3.31 | 5.0 | 5/24 |
| boooooot | 2 | 1/2 | 24.20 | 2.72 | -21.4% | 0.59 | 2.0 | 0/2 |
| cbot14 | 24 | 5/24 | 13.38 | 0.92 | -16.3% | -0.95 | 4.5 | 2/24 |
| Botty | 24 | 17/24 | 9.67 | 0.88 | -23.9% | 0.86 | 2.5 | 6/24 |
| 1sol bot | 24 | 10/24 | 7.13 | 0.99 | -18.7% | -0.80 | 5.5 | 1/24 |
| bot | 24 | 15/24 | 3.12 | 0.74 | -13.0% | -1.22 | 0.5 | 1/24 |
| Bot | 0 | 0/0 | — | — | — | — | — | 0/0 |

## Same-prefix target/control feature comparison

Controls are prior, non-target and noncreator single-event buys from the same queried prefix, within 32 slots and within ±20% of the target's pre-entry real-SOL reserve. Their features are measured causally before each control using the same slot-based windows; no control outcome profitability is calculated.

| Sample | Observations | Median outside net SOL, last 5 slots | Median unique outside buyers, last 5 slots | Median observed drawdown | Current KOL buyers in last 5 slots | Current Tracked16 buyers in last 5 slots | Prior atomic group sides (buy / sell / mixed / none) |
|---|---:|---:|---:|---:|---:|---:|---|
| Target entries | 348 | 1.38 | 3.0 | -9.9% | 34/348 | 7/348 | 263 / 81 / 0 / 4 |
| Matched controls | 1980 | 0.76 | 5.0 | -10.4% | 288/1980 | 86/1980 | 1479 / 488 / 0 / 13 |

This comparison is descriptive and sample-conditioned; control assignments from one mint can overlap across target entries. Current roster membership is exploratory and does not prove historical knowledge.

## Payer/signer-linked receipt observations

These are successful authenticated Pump events in target-wallet transactions where the target was fee payer or signer but a different `TradeEvent.user` executed the trade. They are recorded separately from target entry candidates and do not establish common ownership or copying.

| Target label | Target payer txs | Target signer txs | Other-user trade events | Distinct other event users |
|---|---:|---:|---:|---:|
| bottimus | 133 | 133 | 133 | 12 |
| cbot14 | 130 | 134 | 6 | 2 |

### Bcnz payer-linked child-user entry prefixes

The parent payer/signer transaction window contains **66** authenticated SOL Pump buy events across **63 mints** and **12 child event users**. An outcome-blind hash selected **24 distinct-mint entries**, each with its own causal pre-entry prefix; they are not counted as bcnz's own `TradeEvent.user` buys.
In the selected linked sample, the parent is a transaction signer in **24/24**, the authenticated child event user is a signer in **24/24**, and the parent appears as parsed nonce authority in **24/24**. These are transaction-structure associations, not ownership evidence.

| Authenticated child event user | Selected prefixes | Genesis found |
|---|---:|---:|
| 82s2hm9RFxesfpSLsLg8kwxKz5XWn1Xorf2GyFQey8Xy | 4 | 2/4 |
| H1as9cJbd6Uhu7Lv5drRCFKg7nbPnNk3ymeYkJt1dZzQ | 4 | 4/4 |
| 7Ut1gh36seBkUiYuPx3rNQbuLE7QLT53YJRo3wsGAZRZ | 3 | 3/3 |
| 9a6x28w1qWLxJGs1FMi5MLMDzhgnWnm38SYzkKbrc7kR | 3 | 2/3 |
| EK2jmNwVtnv8cHuQKELbMKF8Y7t75aJ9jduayvpCbC6W | 3 | 2/3 |
| GApPtVhB94qhwJ2KCDiSv69pZoaqs9znUMnjWEgCd3LW | 2 | 2/2 |
| Had6pusVmdPaXzoWCEAQJQ4dMttPx7YCvii1Udd4nnPT | 2 | 1/2 |
| 3fdJGPWsoE1dhQNp1H1kwgYn6HFexSoWFAet7SCbTmTn | 1 | 1/1 |
| DhMmikTXrfk1bn87XSd9AiMYVNFpFMuDJG593eS4kuvZ | 1 | 1/1 |
| J2BA2Nkf9XYVpCUVJio7aaL4vCzxthzGYhFTxsAsDaUy | 1 | 1/1 |

## Separate succeeded-history extension

A separate outcome-blind extension adds **83 entries** across **5 wallets** from succeeded-only 21-day histories. It fills each wallet only up to the overall 24-distinct-mint cap, excluding mints already in the recent250 sample. These are separate from the primary recent-receipt cohort, and source histories are page-capped.

| Wallet | Extension entries | Authenticated distinct buy mints in fetched history | Genesis found | History rows | 10-page cap reached |
|---|---:|---:|---:|---:|---|
| nbot | 20 | 46 | 10/20 | 962 | yes |
| bot | 15 | 15 | 1/15 | 1337 | yes |
| insane bot | 2 | 2 | 1/2 | 10000 | yes |
| boooooot | 22 | 64 | 8/22 | 10000 | yes |
| Bot | 24 | 36 | 2/24 | 4863 | yes |

The succeeded-only extension excludes failed transactions by request design. Capped pages bound the age and token diversity observed, so its counts do not represent wallet lifetime activity.

## Entry mechanics and copy clues

The JSON preserves each entry's immediate prior atomic curve transaction group, exact SOL input, pre/post real-SOL reserves, marginal spot ratio, observed peak drawdown, last 1/5/20-slot outside flows, distinct buyer/seller counts, current KOL/Tracked16 roster presence and prior target-wallet participation at lags 0/1/2/5/20. The two-buyer recovery flag requires two distinct noncreator wallets to make separate >=0.05 SOL SOL-quoted buys within two slots after the latest outside sell and before the target entry. It is a diagnostic only.
Current KOL/Tracked16 addresses present in a target transaction's account keys are recorded as account references only; a reference does not establish a trade, signal, copy or ownership relationship. Entries whose authenticated `TradeEvent.user` equals the `CreateEvent` creator are flagged so deployer buys can be separated from follower behavior.

A repeated predecessor, co-occurring wallet or positive lead-lag count is only an association. Public receipts do not reveal private observation time, intent, funding relationship, shared signals, or whether a follower independently reached the same decision. The current `kol_wallets.txt` and `tracked_wallets.txt` snapshots are exploratory labels, not proof they were historically known; observed token buyers are receipt-authenticated addresses, not verified independent people.

The matched controls are non-target, noncreator single-event Pump buy transactions from the same observed prefix, strictly before the selected entry, within 32 slots and at pre-entry real-SOL reserve within +/-20%. Each matching state is counted; repeated use across entry matches is disclosed and does not increase the number of unique opportunities.

## Result card

- Engine: strict `research/day_general_20261004/helpers/decoder.py`; no replay engine invoked.
- Data: frozen 22-address recent-receipt set; up to two finalized Alchemy `getTransactionsForAddress` pages of 500 per selected mint/curve, query cutoff no later than entry blockTime and frozen blockTime.
- Selection: sha256(`wallet + NUL + signature`), one deterministically chosen transaction per mint, then up to 24 distinct mints per wallet; no outcomes used.
- Central placement, PnL, and profitability verdict: not applicable; no hypothetical entries/exits are simulated.
- Known coverage risks: wallet source histories are capped at 250 receipts; each token prefix at 1,000 receipts; history may begin after creation; blockTime has one-second precision; transactionIndex is needed for same-slot order.
- Status: exploratory descriptive evidence only; no copy edge or private wallet rule established.

## What I would investigate if data and tooling were unconstrained

Collect wallet decision/intent, received-signal, signing, send, route, failure and landing timestamps; complete creation-through-migration histories for every selected and matched-control mint; and pre-entry funding/acquisition relationships with account-owner custody. Freeze a small entry family on a development window, then measure fee-inclusive finite-size post-signal opportunity and actual migration continuation on untouched 2–3 week data with the approved central placement model.
