# Fourth coin: Htgwb / 7xJK

This is an outcome-selected forensic case: the mint was examined because its observed curve reserves rose sharply and later returned near the launch floor. That makes it a discovery example, not evidence that the same behavior is common or a validated detector. The supplied address `Htgwb58PvcZ9qqRu7UcMEn9JdV9vzdTdDLHW9f3ockDW` is identified in the frozen identity receipt as a Pump bonding-curve account. Its authenticated resolution transaction identifies mint `7xJKazFtFNEGUQB85KaFn5GDYGGFjUeNBTD8D1mQpump`. The receipt window’s first successful curve event at 23:50:00Z is only a creation proxy; the mint-resolution transaction at 00:00:47Z is not treated as the mint-creation transaction.

## Curve path and sell shocks

The frozen receipt has 1,223 rows and unique signatures, representing 1,363 successful supported-SOL curve event rows, 603 buys and 760 sells. It has zero parse errors, duplicate signature rows, or duplicate-signature payload conflicts. There are 315 participant wallets, including 313 outside buyers. The source receipt copy is 6,221,100 bytes with SHA-256 `48734d6017d88475412f749b858cd1e3f15a8267ad8812cbc298e0d8432013dd`; its manifest records a 1,027,809,516-byte source prefix.

Real SOL reserve began at 0.493827159 SOL at 23:50:00Z, peaked at 77.448648741 SOL at 23:56:54Z (slot 455840181; signature `quNQnuY2JQ21qkGcNd85wcMneBWn5btfidooDGaLvpJkGcjCo3teuPdj2Sv44MwgQGRxHQNhzqUrhQszhYzHmT8`), then reached 0.214681618 SOL at the last observed event, 00:00:47Z (slot 455841255; signature `2KE9LztZdZySp1Joyum31CqftU8BTkRNoTggTyDoVSTSbKpZGttf452r9PddntEG4uhuAMRUYc5mDneAquyJqxpP`). Peak-to-last real-reserve change is −99.7228%; the virtual reserve price ratio `vsol_raw / vtokens_raw` changed −92.0926%. The last event still has `rtokens_raw=785476121488783`; no receipt has `rtokens_raw==0`. So this is a near-floor reserve collapse in the observed window, not an observed curve completion or graduation.

The largest adjacent absolute reserve drop is 5.395021293 SOL (−7.1814% reserve; −10.0006% virtual-price ratio) between 23:56:55Z and 23:56:57Z, slots 455840187–455840195. The seller is `mMpEUcCgvHmdXvkrawYszRZpXTVfp1E2rDCc4vtGfdw`; before/after signatures are `2GcnCGgeqGZhXax2rdUm9aAQ6MfkyxrcRNz35UbEFRzF5szfXvNYjH8uQwJPb1uDJMwEy9eNZr1P8tspWNsqAbbf` and `5XUrQwMdziR8CxRLAk4kQrKWTtimSmF92UZU6PSVWvVnsAAZShwvjACBzDoWEQ6AwZAWpjik9NzCuV147kEg9VGX`. These are distinct signatures and slots, not one transaction. The largest percentage real-reserve drop is a separate low-reserve event: 0.399905364 SOL (−53.3878% reserve; −2.5842% virtual-price ratio) from 23:57:23Z to 23:57:26Z, slots 455840313–455840327, ending in seller `EcmJWzJ87efLY4ad22F99XSJGZr2YqrHDEvUiduLeGsE`’s signature `5m2pE7bXAzsTREGfbtsuYzgpzpzR5ddaSDJYxWnwVpnBkev3GvAXV8amzcFBAbcjzX4kR4yYbbYMneHfnYmKdK9m`.

Four wallets that root separately identified in the earlier 77AXS/Cvy sell wave also have a buy-then-sell sequence in this mint. In these frozen receipts, each sells at 23:56:57Z; abbreviated signature pairs below are exact in the JSON artifact.

| Wallet | Htgwb first buy | Htgwb sell | Htgwb example buy → sell signatures |
|---|---:|---:|---|
| `CGbLazQt5HXNPawzFct36WeFwj8dL4vGUd8KRHSJ1iCX` | 23:51:40Z | 23:56:57Z | `3YLz…T5ym` → `92cg…Jpd` |
| `98MLcc4UVzeLaDWckcBUCMcwS5CgSeqAjC4g2JNQ714c` | 23:51:45Z | 23:56:57Z | `2UPk…ndfh` → `3NDJ…Fq1` |
| `mMpEUcCgvHmdXvkrawYszRZpXTVfp1E2rDCc4vtGfdw` | 23:51:49Z | 23:56:57Z | `VWW3…Jcdj` → `5XUr…9VGX` |
| `53MN5hAAGHu8Q8HM8ZCaenWYsBma4qTHD9Lp6ETKdLrL` | 23:52:03Z | 23:56:57Z | `77e7…U8q` → `Q3Bs…Ft7` |

Root’s separately RPC-verified context adds a more specific cross-case witness: Cvy's `Dv4MuKsqjXZPMsep9ZDdXrRvNmCEFFGPoYidRMgJQsad` and Htgwb/7xJK's `CmxVhnMu3VSjK7aCLoVi31m5jRMHpgrQkNWDmjHGpQbf` each made one initial buy for exactly15.799270901SOL and360,271,445,579,211raw tokens (about36.027% of launch supply), then fully disposed of that inventory in67 and74 sell pieces, respectively. Root also reports the creators’ first gross buy as0.5SOL in both cases. The earlier parent shorthand `Cmx7xJK` referred to the same `CmxVhn...` wallet, not an additional address. Its74 decoded sell-event rows span30 signatures from23:50:46Z to23:50:57Z, so event rows must not be equated with unique transactions. Quote/amount equality follows from equal budgets and initial reserve state; it describes one repeatable seed recipe rather than independent proof of control.

## Prior-wallet overlap and timing

The overlap calculation uses only the three frozen comparison receipt copies in this report folder. Buyer sets are wallets with at least one buy event, excluding that case’s creator. To avoid same-second ambiguity, the strict-history lattice admits only prior-case events with `event_timestamp <` the later case’s first-observed-event second or paper-OPEN second. The later target’s final cohort membership remains retrospective even when its historical trades occurred before the cutoff.

| Prior case → Htgwb | Prior / Htgwb outside buyers | Shared buyers | Buyer-set Jaccard | Htgwb cohort with prior case history before first event / before paper OPEN |
|---|---:|---:|---:|---|
| Cvy | 382 / 313 | 219 | 46.01% | all participants 219/315 / 219/315; first 20 buyers 14/20 / 14/20; final repeat-top-20 20/20 / 20/20 |
| Cfiyy | 230 / 313 | 5 | 0.93% | all participants 5/315 / 5/315; first 20 buyers 1/20 / 1/20; final repeat-top-20 0/20 / 0/20 |
| Dg | 195 / 313 | 5 | 0.99% completed-set comparison only | Dg begins after Htgwb’s first event, so it is not pre-creation history for Htgwb |

Htgwb’s first observed event was 23:50:00Z and its paper OPEN was 23:55:00.293817991Z (the lattice uses the OPEN’s integer second, excluding same-second events). Cvy’s receipt history ends before both cutoffs, so its 219-wallet intersection is temporally prior. That count is a strong selected-case recurrence witness, but the 20/20 final repeat-wallet result is defined from the completed Htgwb receipt and was not known at entry. Root’s reciprocal strict-prior view finds 3 of Dg’s 200 final participants in Htgwb receipts before Dg’s first event, and 5 before Dg’s paper OPEN; Dg’s final-cohort membership is hindsight. For the prior 77AXS pool, root reports authenticated balances falling from 100.659 SOL to 3.8124 SOL between 23:05:51Z and 23:06:11Z, with the same four named wallets selling in the 23:06:10–11Z wave; see [prior 77AXS sell witnesses](prior_77AXS_pool_sell_witnesses.json).

The holder screen completed at 23:54:50.940Z. The local paper record opened at 23:55:00.294Z and closed at 23:56:57.927Z; both records say `actual_fill_established=false` and `placement_calibrated=false`. Nearby detector records are incomplete: an `unknown` verdict at 23:55:12.937Z cited missing mint supply, followed by `watch` at 23:55:16.181Z with receipt and cross-launch probes incomplete. This documents the paper/observer chronology, not a real fill or realized trade.

## Limits and artifacts

This target was selected after its observed outcome. Recurring wallets can be generic snipers, copy traders, or active curve participants; shared wallets do not prove common control or malicious intent. The local holder view is a bounded sample, not proof of ownership, and this analysis did not construct an RPC funding graph. Reserve snapshots are not executable prices, and near-floor reserves without `rtokens_raw==0` do not by themselves establish a rug. `received_at_ms − event_timestamp×1000` is only a descriptive observer-clock difference, not calibrated chain latency. The receipt’s first observed event can lag actual creation, and one-second timestamps leave same-second ordering unresolved.

The detailed event path, wallet profiles, full signatures, sell sequences, strict-prior lattice, and comparison wallet membership sets are in [fourth_analysis.json](fourth_analysis.json). Frozen inputs are indexed by [fourth_MANIFEST.json](fourth_MANIFEST.json); `fourth_ghost_observations.jsonl` is the target receipt copy.
