# Detecting coordinated volume before a liquidity collapse

Scope: research observer design and the accompanying frozen diagnostic, not an enabled trading filter. User request: ladder-like bot buying that pumps and abruptly rugs. Current holder screening is a risk proxy; it does not establish common wallet ownership or authentic demand.

## What to measure before an entry

Measure at the actual S2/S4 setup and update while a reclaim watch is armed, using completed transactions and only data received by that time. Preserve windows separately rather than mixing launch concentration with later community buying.

| Evidence | Causal measurements available now | What it can tell us |
|---|---|---|
| Demand retained | Gross outside buys, sells, net flow, real reserve change, wallet hold/sell sequences | Whether volume accumulates capital or mostly turns it over. A one-way bot pump can still retain capital until its exit; low churn cannot prove safety. |
| Effective breadth | Qualified addresses, repeat-wallet volume, top-N buying shares, supply retained by recent buyer cohorts | Whether a high transaction/address count represents concentrated economic exposure. Addresses are not independently funded people. |
| Ladder structure | Repeated purchase sizes, order-size distribution, slot burst concentration, recurrence of buyer groups | Whether buying looks unusually regimented. Legitimate automated orders can share sizes/routes; regularity alone cannot veto a coin. Feed receipt intervals cannot establish exact on-chain timing. |
| Sell pressure | Who sells, recently retained supply entering sells, buy replacement after seller waves, reserve loss | Whether the holders supporting the rise are unloading and fresh buying replaces them. This can become observable only after the initial sell, so it is not a guarantee of pre-rug prediction. |
| Snapshot changes | Offending holder custody changes, updated concentration and screen freshness | Whether a prior risk still exists. 5UC38's early >=7% low-SOL holder sold below the threshold and then out, but the permanent block did not reconsider it. |

An observer should emit the raw evidence and reasons for suspicion. It should keep `unknown`, `suspected coordinated`, `concentration risk`, and `observed liquidity failure` distinct. Avoid an opaque bot probability or a permanent fake label from one snapshot. No arbitrary combination of these features is established as predictive by the current short sample.

## The largest missing information

A bot group can spread buys across fresh wallets, varying sizes and timing enough to appear broad. The present logs do not supply authentic common-funding links, complete transfers/escrow inventory, or independently established wallet owners. The next data collection should bind buyer signers and fee payers to transaction fingerprints, funding parents where covered, cross-launch buyer-group recurrence, and retained token custody. Common funding and matching fingerprints are association evidence, not ownership proof. Public-route use alone is too common to identify a coordinated group.

The current `<0.3 SOL` holder balance rule asks how much SOL remains after a trade. That does not by itself show whether the wallet is a bot, where its funds came from or whether it is coordinating with other buyers.

## How to assess the observer

Use the creation-observed cohort and first source-valid S2/S4 setup as independent prespecified views. The included diagnostic computes prior-10s features and subsequent curve-path labels, with censored recent or graduated paths separated. These future outcomes are labels only; the alert may use no future values. Preserve a genuine later, untouched stream period before selecting any thresholds. Evaluate both caught collapses and rejected runners, especially 5UC38; report admitted vs skipped setups and funding implications through the approved engine before claiming a profitability benefit.

The supplied script and CSV files are descriptive extraction artifacts. They do not classify all bots or authorize a live veto. Main implementation priority from this audit is revisiting stale holder verdicts while collecting enough group/retained-inventory evidence for a narrower coordinated-volume detector.
