# Wallet overlap and prior-collapse witnesses

The strongest historical receipt witness is a 20-wallet slice of Cvy’s eventual first buyers: 17 of those wallets had bought GWRj before Cvy’s first observed curve event, and that launch had already crossed the reserve-collapse screen. Two other screened launches before Cvy also carried 15/20 and 13/20 of the same retrospectively selected cohort. A separate, parent-supplied RPC investigation adds a more specific cross-case witness: four wallets that later traded Cvy were sellers in a tightly timed sell wave on prior AMM pool 77AXS. These are outcome-selected, retrospective associations. They do not establish common ownership, fraud, or a population-validated detector.

## Scope and frozen data

The target receipt copy is `ghost_observations.jsonl` under this report directory, frozen with its `MANIFEST.json`. It contains 1,615 target signatures and 1,783 successful supported-SOL curve events, with 392 distinct event users, 383 distinct buy users (382 noncreator buyers). The first successful target curve event was at 2026-10-11 23:13:18 UTC; the supplied approximate entry second is 23:18:17 UTC. The target creator is `FcNHxPSqQ1ChyWmwW8C4zzXuUvQR3b7zBNBxk84VPmSv`.

I scanned exactly the first 600,237,762 bytes of `data/ghost_observations.jsonl`, SHA-256 `f9ba7efb63da607eab9ed6a7b5760fe02596bbe777f405e528be2891d4520c5c`. The temporal-cutoff pass independently re-read and verified that same prefix. It contained 104,155 unique signatures, 80,834 successful supported-SOL curve events and 2,004 other mints; 1,073 had observed noncreator buyers over the whole prefix. The source grew by 719,429 bytes during the original scan, and that appended tail was excluded. The frozen observation window begins at 23:09:15 UTC, so it does not cover the earlier 77AXS sell wave described below.

Receipt rows were deduplicated by transaction signature; the prefix had no duplicate signature rows or conflicting payloads, and all 1,615 frozen target signatures were present. The repository decoder excludes failed transactions and requires successful Pump invocation ancestry. Other-mint buyer sets count distinct `event.user` addresses on successful supported-SOL buys where `user != creator`. A target participant must have an outside buy on the other mint to count as overlap.

The three cohorts are intentionally separate:

- `all_target_participants`: all 392 target event users, including creator and sell-only users.
- `first20_outside_buyers`: first 20 distinct noncreator target buyers ordered by slot, transaction index and event index.
- `top20_repeat_outside_buyers`: 20 noncreator buyers ranked by distinct target buy signatures, then sell signatures and first-buy order; each has at least two distinct buy signatures. This is a repeat-activity proxy, not a wash-trading label.

Full wallet membership sets, per-wallet target buy/sell signature counts, and signature examples are in [`overlap_analysis.json`](overlap_analysis.json). Candidate-level membership sets and examples are in [`overlap_rug_candidates.json`](overlap_rug_candidates.json) and [`overlap_temporal_cutoffs.json`](overlap_temporal_cutoffs.json).

## Outcome-first cutoff results

For exploratory screening, I marked a mint when its observed real-SOL curve reserve reached at least 10 SOL, later had an observed reserve at or below 1 SOL, and no observed event had `rtokens_raw == 0`. The last condition excludes observed curve completion/migration. This is a reserve-history screen only; a low reserve does not prove fraud, irrecoverability, or manipulation.

Cutoff views include only events whose one-second `event_timestamp` is strictly earlier than the cutoff. Same-second events are excluded because they cannot be ordered against Cvy’s event at this timestamp resolution. There were 17 other mints with an outside buy in Cvy’s first-event second and 11 in the approximate-entry second; they are not included in the strict-before counts.

| View | Other mints with prior outside buyers | Mints meeting reserve screen by cutoff | Screened mints with ≥5 first-20 cohort wallets | Screened mints with any repeat-20 overlap |
|---|---:|---:|---:|---:|
| Before Cvy’s first observed event, 23:13:18Z | 209 | 9 | 3 | 3 |
| Before approximate entry, 23:18:17Z | 394 | 20 | 3 | 3 |

Three already-collapsed launches dominate first-20 overlap before Cvy’s first observed event:

| Other mint | Reserve at pre-Cvy cutoff (peak → last SOL) | First-20 wallets shared | Jaccard | Share of other launch buyers | Target cohort coverage |
|---|---:|---:|---:|---:|---:|
| `GWRjTLqFatZEgfLgN8AcLL3o3dtPgTqX7y71NBD9pump` | 28.959 → 0.130 | 17/20 | 0.378 | 40.5% | 85% |
| `mtSCzFPH2fED9NPh9DEh44uDPUjNUdG6y3se4Rcpump` | 21.212 → 0.000000049 | 15/20 | 0.469 | 55.6% | 75% |
| `F88iUaKH5dcaW9UdUZMQ6aqoCNi6DEV1kaQxwbBzpump` | 18.679 → 0.0368 | 13/20 | 0.433 | 56.5% | 65% |

All three still met the reserve screen by approximate entry. GWRj had 44 outside buyers by then and closed its observed curve-reserve history at 0.012403 SOL at 23:17:19Z (signature `2FUQT5DHoSS297dnX4gFojkRc6qcupf8PWSfMrpnEPttuYNd7NkBZDRNPr1942fGffcJegvCEwzZJcq2uof7nG6b`); its peak-to-last virtual reserve ratio change was −74.09%. `mtSCz...` had 28 outside buyers and a last observed real reserve of 0.001601 SOL at 23:15:07Z (signature `2r8D5s2mU5bRapmSqzJgboCLHvLdEsELDExBPbbVFMRGQnc4GGWzUGBVWtLvGS78e27d3irgSruUX7zMUX2fzbQg`). `F88i...` had 23 outside buyers and a last observed real reserve of 0.000000024 SOL at 23:15:02Z (signature `27kbf6a8oCBdTzc9SV8pj5D2HMEuMzUbxA4AGw1C7xawZgFjgz3pG865GbFMsRTVTsx9hsU47eLmYe6RsehFqj7W`). None of these three had an observed zero real-token reserve in the screened interval.

The four wallets in Cvy’s top repeat-20 cohort—`B9ksmPhuhj43BBWXJxm1SUXDbVZRthmvf8FZMpYhVhoH`, `CMcKT7wshBUjRrPy6uH4bdTRkmxFLngQh2kTXrrzRVdC`, `Hy4ZuryDVXuytB3TGXmAdcqHQeF7WMQD4dZLdAipyVFt` and `7dGV2auDmovmUbb27KBW1QNN52aLXd4ZZbafG9nyr5VT`—bought all three launches. Each launch therefore had 4/20 repeat-cohort wallets, though just four wallets alone are weak evidence. The same `sha256:5cfade80be404b9365373e7abb69535bc1d9052f1ec31f9b2a6617764817d26c` route fingerprint appears on their GWRj receipts. That coarse fingerprint occurs across 308 observed mints, 3,705 signatures and 1,804 buy wallets in this prefix; it is a common transaction-shape match, not an identity link.

For concrete signature examples, those four wallets’ GWRj buys were `2Ch6DrnUSaBS4hrQFJftGgnhC9t29fmjn1BMwcpZMYixSkoJzqLHEJTrCEk745FQ22egyrERxcG9NL4dxmcrbm5r` (7dGV, 23:12:02Z), `5gyWykH7YXwdU6XarWUAT2J6JcL92HvfVWbq1n2AAa61ybWJNXyswqAqDCiBmGTrk93ubxkdrsa2n12aA3YbMCHv` (Hy4, 23:12:02Z), `3QdBumZ58CWfGnKdCagZDrBCkDc6Sc2KV1rGzbpeRpYzNrGc6HDCrpwEe589wWSbyDD1m7BiRRY8h1PfSmnGrMNx` (B9, 23:12:04Z), and `39zurKxo1wjWqyUjL5wCseJjqGKf2GWLqZsEU2umeKMVNxjJ6YbHtEqEx3VRQDDbfsZkA2qpkkT95PRjLB5R3Wf` (CMc, 23:12:04Z). Their first Cvy buys followed at 23:13:20Z; signatures are respectively `3CcdHJTNfhKkoHGMWJRFhwecu6CEpuMJQaYHCvtM7gx1HwXJQrwU455BLLSXoYdd9jpPHcyihEtS9aSG7nfotxid`, `41YanpQhfxHUxJXC1nwMMiQFQmGqmrTdJbGEsL7aUesHoeyM6HbFXbpTEfvrfY96iABPeKeHHj527gNLHavFEaqv`, `4BeNLPxBv3ZWzBCZRWLCvVeiEiyM3im8scoEJgQVfx4MZAuyKpZA1zMoWePneyoR76PvWQTuYkfEVFKbdi1nzF1N`, and `33hqdKmSM2cdpeNAwoVxXEna54Vq1ieyZpc3TrJ2icaVx2gPNajfQZajoShpyakredYmbTexuGJPxRd1NQezcaTV`. The receipt profiles show 7–15 target buy signatures and 9–11 sell signatures for these four wallets.

One small ordered fragment also recurs: `3Dpb2MpKNB3WxDUmWMo1gxmQjRReJpdtWnNzvisYhTMW` precedes `7dGV...` in the first 20 on GWRj, `mtSCz...` and `F88i...`, and in Cvy’s first-20 order. This is a two-wallet fragment within a broad launch cohort; it does not establish shared control. Ordered-pair counts and all example signatures are retained in `overlap_analysis.json`.

## Separate parent-supplied prior AMM evidence

A distinct four-wallet set selected from Cvy’s later activity—`CGbLazQt5HXNPawzFct36WeFwj8dL4vGUd8KRHSJ1iCX`, `98MLcc4UVzeLaDWckcBUCMcwS5CgSeqAjC4g2JNQ714c`, `mMpEUcCgvHmdXvkrawYszRZpXTVfp1E2rDCc4vtGfdw`, and `53MN5hAAGHu8Q8HM8ZCaenWYsBma4qTHD9Lp6ETKdLrL`—also appears in the parent’s prior-pool sell witnesses for `77AXSFnjgfgsT261R8wkPSwSe94BgheBS9hbLiQVpump`, pool `Bt8gmEqPWojBQqVsF4BuBNYKwTCX7JQevWb81Cyof4Yk`. The witness artifact records `Sell` instructions at 23:06:10–11Z: `5YNwTQNU5W183ozEZKwkczdACAsWmmbRpqenaRe4CeJxZvFMWAdMRmddMjtbumUicRvUPDwByXX54tNEVsUrC5rv` (98ML), `42PQJQ99EpBSh321uG466BamwACmwJ1eVQ8pgWByP8ypTwE8iZmaTPvz27Ceydb5xhVoejD2bjKF4gc4G79pvMcQ` (CGbLaz), `3Mt7JQs7Mit9gmt7q8ewmTNwzvwmpkE8jL8eeYV96Y1ooMtshNKvZicX6MTA2F9VQHde3bAhyvTfTGLwyWJHqqkk` (53MN), and `ftSkM4GJrLjvkAJ1MjhkxhdgVhR3R5etYiE7i82mtY4VEh8wiNaxFsBFppRZ8eidhHFq8qfsRiNG5Xzi47ixW8q` (mMp).

The parent separately reports authenticated SOL quote reserves of 100.659488463 SOL at 23:05:51Z and 3.8124 SOL at 23:06:11Z. I did not query RPC or independently verify those balances; the sell signatures/logs above are read from [`prior_77AXS_pool_sell_witnesses.json`](prior_77AXS_pool_sell_witnesses.json). Each wallet later bought Cvy: first-buy examples are `4FYv66DmercgQjkKf9sGxYukR7Pq6RRkSDLtXVEgVPudkt5T16opKEpi5sUpJJkaM8GpxYS6Ae2LriQkczTsgEcD` (CGbLaz), `31jk9TrTTf6YumgKPVSxZbAPYN4DWebf9hwH3nF3DWjoLLWp5bn8JQhEbFTyqf9AZL7TkhaCNJn7teAtRfMYb8u6` (98ML), `4tfTjdGZaZf7UcntkArUmuEhP4JJwGZ7knE3Xxe6JaShVmvQ6p7n2JPz4h6AHkTVTqYpz13NDCH7RWSuci2K5FqC` (mMp), and `5cY5eChqJvSgLWQZxCwEfgZxXWZx5bq2GAWSztW1BzXH9qgK3dmnmvPZvHvkMZsM6UZJXYrjmzDe3G2XchKN5171` (53MN). Those Cvy buys were at 23:15:26, 23:15:31, 23:15:36 and 23:15:49Z respectively, after Cvy’s first observed event.

This prior activity is temporally before Cvy, but the four-wallet group was identified by looking back from later Cvy participation. It is therefore a strong targeted historical lead, not evidence that a bot could have selected it at Cvy entry without first querying these histories. The parent also reports six high-volume target accounts funded through six distinct intermediates and six distinct ancestors around 23:06:35Z; no common root owner is established. The frozen curve-receipt stream starts after that window and does not contain SOL funding transfers. Related files are `rpc_funding_ancestry_links.json`, `rpc_funding_ancestry_signatures.json` and `rpc_funding_ancestry_transactions.json`.

## Limits and reading

- Cohort membership comes from Cvy’s completed receipt history. Any apparent predictive value is outcome-selected; it is not a population test or a causal entry rule.
- The first observed event is not authenticated mint creation. Collection gaps can omit earlier launch history.
- A low observed curve reserve is not a fraud verdict and does not rule out recovery or post-migration trading. `vsol_raw / vtokens_raw` is a reserve ratio, not a finite-size execution price.
- Route fingerprints describe broad transaction shape. Fee payer fields identify transaction payers, not funding provenance or common ownership. In the target receipts, 816 buy events had the event user as fee payer and 76 had a different payer; neither result establishes coordination.
- No RPC was called in this analysis, and no SOL funding graph, ownership proof, detector validation, replay, or PnL analysis was performed.
