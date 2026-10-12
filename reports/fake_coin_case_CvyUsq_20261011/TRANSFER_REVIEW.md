# Initial inventory relay across Cfiyy and DgT6

This is the strongest structural match in the two later user examples. Successful parsed `TransferChecked` instructions show four early buyers forwarding their entire observed purchases to a different four-wallet set within the first few seconds. The **four raw amounts are identical across both launches**. Source and destination token-account owners are authenticated by transaction pre/post token balances; each source has an exact earlier curve-buy match in the frozen receipts.

| Raw token amount (six decimals) | Cfiyy buy wallet → receiving wallet | DgT6 buy wallet → receiving wallet |
|---:|---|---|
|352,243,820,712,452|`95Sp1Fr...` → `3rroAW...`|`FySVY5...` → `BbiQH6...`|
|182,270,662,645,082|`ExZV17...` → `GV1Pw...`|`ikPSWAPS...` → `7pVSN...`|
|106,467,965,872,131|`5QTUm8...` → `DhrDvy...`|`DDPvEh...` → `B1fvn...`|
|69,207,549,760,218|`9ka2hX...` → `4VXsn...`|`2XUT95...` → `BMxDP...`|

Sum: **710,189,998,989,883 raw units =710.189998989883 million tokens**, about71.019% of the nominal one-billion-token launch supply. This is gross early inventory acquired and relayed, not current retained inventory. Both entry holder screens report a one-billion-token actual supply; subsequent burns/changes require their own denominators.

Cfiyy's relay transactions occurred around23:35:23UTC after its23:35:20 first creation receipt. DgT6's corresponding transactions occurred around23:51:44UTC after its23:51:42 creation receipt. The acquiring and receiving wallet sets differ between launches, while their direct funding graphs repeatedly use the same three sources. This ties the repeated token-allocation template to an observed funding family.

Concrete transfer examples:

- Cfiyy352.243820712452million: `5m1DPPKwZGt2MJ6dT4VtHTTCdcBAcuC5o3ZEnfbcdpTD4C7NPBw9gPv5nyNdxiSAq1RU51pwAh5fEoR6nSmC5rt7`.
- DgT6same amount: `ghAZYFuFmXQC5MxNkeXmK3bNZhRMVD1A4jfh1BscvVHiw5u115bee7Gxy8cWquUPmhF2thTnQTBE7ZAYUXq9Lma`.
- Cfiyy69.207549760218million: `3vwDQWXa4qgiJGUzg9pU8Nu4W469wcJ6w6AWZ13353E1SkQ7qtTCm1tPkFDs1RyXz9Zm4CKnZqqnhLw3cikmpz6q`.
- DgT6same amount: `4r8HZCCTsXJQmjyfCsJ1D4uNzFfXgyc2ktM175TkEWEgn42YWCBbGGaoWDsfvib8yMXEHTjmfLMmQhbmGygW65PA`.

Full addresses, owning accounts, amounts, signatures, slots and exact earlier-buy joins are in `early_inventory_transfers.json`; raw bodies are in `second_rpc_transactions.json` and `third_rpc_funding_transactions.json`. Only the eight source-owner records with an exact earlier curve-buy match form this table. Other transfer records involving `9Pnw...` and `DNfd...` include protocol-vault legs of normal swaps and must not be interpreted as an additional central wallet distributing investor tokens.

The receiving wallets begin their captured swap activity by selling, rather than by buying their initial inventory. A detector that links only event buyers and direct SOL funders can therefore fail to connect these retained holders to the early acquisition cluster. The case calls for token-transfer custody continuity: acquiring wallet → receiving holder → subsequent seller, with funding and launch history alongside it.

The observations establish a repeated acquisition/relay template and funding associations. Matching token output can follow mechanically from matching buy budgets and initial curve states, so amount equality must not be counted as independent proof alongside those same inputs. The authenticated transfer path, recurring funding family and later observed behavior add different evidence. These records do not identify a single beneficial owner or quantify self-dealing volume. A service/platform or automated trading arrangement is a competing explanation to investigate through funder provenance and comparison with ordinary launches. No detector threshold or trading rule was changed.
