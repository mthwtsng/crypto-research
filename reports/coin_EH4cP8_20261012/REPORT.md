# EH4cP8…pump ("Dogcoin"): why tracked bots piled in

Scope: complete Pump bonding-curve history plus sampled post-migration PumpSwap activity. Data was collected Oct 12 2026 (UTC) and all times below are UTC. **Measured** means read directly from decoded on-chain data. **Inferred** means interpretation.

Coverage: the curve PDA `8Qw6LJzHCweFYBFnXaGVraDQfJTQ34KN4eEpvPekMNtX` has 14,346 signatures, 5,103 successful and 9,243 failed. All 5,103 successful txs were fetched and 4,797 Pump TradeEvents were decoded. Trades within a slot were ordered by reserve continuity, with **0 continuity breaks** across the whole tape. getTransaction does not give a block index, so `tx_index` is null; `ord` is the continuity order. Failed txs are counted from signature `err`, with 23 sampled.

Caveat: Shyft's `getSignaturesForAddress` silently stopped at Oct 10 and missed the original launch. Solami returned the full history. Treat Shyft history paging as incomplete for older coins.

Scripts: `fetch.py`, `build_tape.py`, `analyze.py`, `fresh_wallets.py`, `post_migration.py`.
Outputs: `tape.jsonl`, `analysis.json`, `fresh_wallets.json`, `post_migration.json`.

## 1. Timeline (measured)

This coin has two lives: a launch that died, and a revival 12 days later that graduated.

| Phase | Window (UTC) | Trades (buys/sells) | Unique buyers | Failed txs | r_sol path |
|---|---|---|---|---|---|
| Launch | Sep 29 20:06:51 → ~21:00 | 1,302 (655/647) | 382 | 8,395 (8,019 in first 400 slots) | 9.2 → 45.60 peak at 20:07:38 (+47 s) → 5.8 by +10 min → 2.2 by +30 min |
| Dormant | Sep 30 → Oct 10 | 16 dust trades | – | – | 1.35 → **0.039** |
| Revival probes | Oct 12 02:09:39 → 02:47 | 45 | ~16 | 3 | three waves to 3.0 / 4.6 / 3.2, each fully sold back within 2–5 min |
| Main run | Oct 12 05:09:08 → 06:26:16 | 3,450 (2,169/1,281) | 839 | 845 | see below |

- **Creation:** slot 451,744,435 at 2026-09-29 20:06:51. Name/symbol "Dogcoin", URI `m.rapidlaunch.io`. The create-tx signer and CreateEvent.user is `D9gQ6RhK…`, **which is your tracked wallet "washey"**. CreateEvent.creator (the fee recipient) is `4bjXcMSR…`.
- **Main-run milestones:**

  | r_sol | Time |
  |---|---|
  | 5 SOL | 05:09:31 |
  | 10 and 15 SOL | 05:10:57, crossed by one 6.91 SOL buy |
  | 20 SOL | 05:11:00 |
  | 30 SOL | 05:14:10 |
  | 50 SOL | 05:55:20 |
  | 70 SOL | 06:20:09 |
  | 84 SOL | 06:26:11 |
  | Complete | slot 455,947,247 at 06:26:16 (r_sol 85.005) |

  The run was choppy. The running all-time high stepped 22.96 → 37.86 (05:16) → 52.85 (05:57) → 85. There were drawdowns to about 15.6 (05:52) and 29.0 (06:02).
- **Migration:** MigrateV2 executed at slot 455,947,249, two slots after completion. The PumpSwap pool is `3S7fiSZpCRKfevwqmXaK5twHAQxGsPvV3gWcskkx6h48`, seeded with 67.45 SOL and 206.79M tokens at 0.326 SOL/Mtok. Within 16 minutes it had 2,807 signatures (411 failed). Sampled price: 0.378 at 06:26:32, 0.243 at 06:29, 0.159 at 06:33, 0.162 at 06:37. That is roughly −50% from the migration price within about 10 minutes.

## 2. Tracked bots (measured)

27 tracked wallets traded this coin: 614 trades in total.
- Launch: 7.1% of SOL volume.
- Revival: **19% of SOL volume** (551 of 3,495 trades).
- 49 slots contained buys from 2 or more tracked wallets.
- Summed curve PnL is +14.72 SOL before fees. Summed fee-payer receipts on the curve are +8.89 SOL; these exclude `ARu4n5`, whose SOL is paid by other fee payers, and `sssssw`'s post-migration exit.

Column definitions: B/S counts buys/sells; "in/out" is curve SOL; "rcpt" is the wallet's lamport delta (net of fees and tips); r is r_sol.

| Label (wallet) | Phase | First buy (UTC) and r before → after | B/S | in → out SOL | Curve PnL / rcpt | Median hold | Entry r range → exit r range |
|---|---|---|---|---|---|---|---|
| washey (D9gQ6R) **= dev** | launch | create tx, 0 → 2.96 | 1/3 | 2.96 → 5.98 | +3.02 / +2.83 | 3 s | dumped at 8–17.6 |
| Jijo (4BdKax) | launch | 20:07:12, 8.0 | 2/1 | 1.44 → 1.06 | −0.37 / −0.45 | 731 s | 9–20 → 3.7 |
| Fleet Bot 39 (sssssD) | launch + revival | 20:07:16, 29.1 | 27/27 | 27.62 → 32.33 | +4.71 / +3.95 | 60 s | 2.8–57 → 1.0–75 |
| snipebot (85YwZa) | launch | 20:07:26, 21.8 | 1/3 | 2.67 → 3.32 | +0.65 / +0.57 | 1 s | 24.5 → 26–32 |
| Real Coin Bot 23 (77wS9z) | both | 20:07:30, 30.6 | 2/2 | 0.30 → 0.26 | −0.04 / −0.05 | 140 s | |
| blue (8Ltv5r) | launch | 20:07:32, 33.2 | 1/2 | 1.22 → 0.95 | −0.27 / −0.35 | 29 s | |
| Real Coin Bot 17 (2zMj6w) | both | 20:07:32, 35.7 (ATH) | 5/5 | 0.54 → 0.54 | −0.01 / −0.03 | 15 s | |
| Real Coin Bot 21 (DiJF3L) | both | 20:07:32, 35.8 (ATH) | 6/6 | 0.30 → 0.30 | 0 / −0.01 | 15 s | |
| Real Coin Bot 41 (ARu4n5)* | both | 20:07:53, 32.9 | 43/43 | 16.63 → 18.27 | +1.64 / n/a* | 202 s | 1.0–84.1 |
| Real Coin Bot 18 (88887Q) | launch | 20:08:24, 12.5 | 1/1 | 1.05 → 1.53 | +0.48 / +0.45 | 9 s | |
| Fleet Bot 45 (sssssw) | revival | 02:09:40, 2.41 → 3.20 | 83/43 | 27.26 → 29.00 (+2.00 AMM) | +1.74 / +1.02 curve, **+3.02 incl. AMM** | 650 s | 3.1–80 |
| Real Coin Bot 17 (67Ptgd) | main | 05:09:27, 2.58 | 3/3 | 0.15 → 0.15 | 0 | 13 s | |
| Scalp Bot 40 (omegoM) | main | 05:09:49, 5.68 | 40/40 | 24.48 → 26.31 | +1.83 / +1.19 | 29 s | 6.0–78.8 → 5.0–82.6 |
| Real Coin Bot 23 (2FdJD3) | main | 05:09:50, 5.74 | 5/5 | 2.05 → 2.13 | +0.08 / +0.02 | 12 s | |
| Real Coin Bot 15 (AHeEPb) | main | 05:12:00, 13.6 | 1/2 | 2.96 → 3.40 | +0.44 / +0.32 | 2 s | |
| Real Coin Bot 30 (5veTCy) | main | 05:12:00, 17.0 | 34/34 | 0.067 → 0.070 | ~0 | 11.5 s | **all buys 0.002 SOL (micro)** |
| Real Coin Bot 33 (8jmHwe) | main | 05:12:09, 20.4 | 29/29 | 4.30 → 4.55 | +0.25 / +0.12 | 8 s | 0.148 tickets |
| Real Coin Bot 19 (ocBBRK) | main | 05:13:17, 18.9 | 3/3 | 0.74 → 0.77 | +0.03 / +0.01 | 12 s | |
| Real Coin Bot 22 (5pHk81) | main | 05:13:47, 21.2 | 1/1 | 0.05 → 0.09 | +0.04 / +0.03 | 91 s | |
| chiensewarlord (JAj2wK) | main | 05:14:52, 33.4 | 3/2 | 5.38 → 3.89 | **−1.49 / −1.79** | 625 s | 27.7–37.9 → 18.9–23 |
| Real Coin Bot 15 (8vjxLy) | main | 05:15:28, 35.1 | 1/1 | 0.03 → 0.02 | −0.01 | 23 s | |
| MiLFgC Early Scalper (HANcjm) | main | 05:18:47, 29.0 | 1/1 | 0.64 → 0.55 | −0.09 / −0.11 | 156 s | |
| Real Coin Bot 16 (6SFc4b) | main | 05:21:35, 24.5 | 15/15 | 11.65 → 13.03 | +1.38 / +1.05 | 55 s | 23.7–76.4 |
| Real Coin Bot 18 (4FpuSL) | main | 05:25:39, 25.0 | 2/2 | 0.16 → 0.17 | +0.01 | 37 s | |
| Real Coin Bot 28 (BWBd3h) | main | 05:25:41, 27.6 | 7/7 | 9.41 → 9.84 | +0.42 / +0.16 | 14 s | |
| insane bot (BuekUk) | main | 05:27:59, 15.5 | 2/12 | 7.90 → 8.16 | +0.25 / −0.05 | 3 s | |
| bot (haqqiU) | main | 06:20:52, 76.7 | 1/1 | 0.10 → 0.10 | ~0 | 11 s | |

\* `ARu4n5` trades were paid by **26 different fee payers**, including relay signers `CaVvP8`, `AgmLJB`/DFlow and `FHpcNSe6`. Its own SOL balance never changed in any trade. It ended the curve holding 20.36M tokens; its last buy was 0.86 SOL at r_sol 84.08. Its token balance is now 0, but the post-migration exit was not located in its first 120 post-migration signatures, so treat it as **unresolved**. Marked at pool prices, those tokens were worth about 6.6 SOL at 0.326 SOL/Mtok and about 3.3 SOL at 0.16 (venue: PumpSwap pool, 06:26–06:37). It is probably a shared relayer/custody account, not a single self-funded bot.

**Curve state right before the first tracked buy (only trades before that buy):**

- **Revival (Fleet Bots sssssD and sssssw, slot 455,876,704, 1 s into the revival):** r_sol 2.41, a new phase high. The 6 prior buys were all buys, totalling +2.37 SOL net, from 6 unique buyers. Zero micro-buys. Largest prior buy 0.988 SOL. All-time high was 45.6 from the old launch. The dev held 0 tokens; he sold everything on launch day.
- **Main run, first cluster (05:09:49–05:09:50: sssssw, omegoM, 2FdJD3 within 3 slots):** r_sol 5.68, **not** at the phase high of 8.53. In the prior 30 s: 12 buys / 11 sells, +4.08 SOL net, 12 unique buyers, **0 micro-buys**. Largest prior buy 2.963 SOL (GGBJfS at 05:09:31).
- **Main run, Real-Coin-Bot swarm (05:12:00–05:13:47: AHeEPb, 5veTCy, 8jmHwe, ocBBRK, 5pHk81):** r_sol 13.6–21.2, below the 22.96 high. In the prior 60 s: 31–46 buys, net flow −3 to +1 SOL, **8–16 micro-buys**. This swarm came right after the 6.91 SOL whale buy and the FLASHX buying burst (Section 3). 54–67 micro-buys had already occurred since 05:09.
- **Clusters (first buy per wallet within ≤3 slots):**
  - Launch: 2zMj6w, DiJF3L and blue, all in slot 451,744,584 at r ≈ 35.
  - Revival: sssssD and sssssw in the same slot.
  - Main run: sssssw, omegoM and 2FdJD3 at 05:09:49; AHeEPb and 5veTCy at 05:12:00 / slot +1; 2zMj6w and DiJF3L at 33 SOL at 05:14:10, the same pair as at launch.
- Tracked buys by r_sol bucket in the main run: 0–10 SOL: 7; 10–20: 54; **20–30: 95**; 30–40: 66; 40–50: 29; 50+: 34. Most tracked buying happened in the 20–40 SOL chop, not at the ignition.

## 3. Fake-volume analysis, in time order (measured, with inference flagged)

**Micro-buys (< 0.02 SOL).**
- Main run: 542 micro-buys from 143 wallets. That is 25% of buy count but only 3.2 SOL (0.4% of the 767 SOL bought). 15 wallets made 5 or more each, together 356 micro-buys.
- Launch: 159 micro-buys from 66 wallets. The top wallet, H8URrc, made 48 of them and also did 22 round trips at seconds 15–148 after creation.

Main-run bump sequence:
1. **05:09:08–05:09:31 ignition, with no micro-buys at all.** 3QJ1Dz buys 0.49 SOL via GMGN; CHCLtC buys 0.98. Then one slot (455,926,096) carries 6FZ1Ra 0.62 and UuAvcG 0.84 (both through Axiom `term9YPb` terminal-proxy), GGBJfS 2.96, plus two more buyers: r_sol 2.6 → 7.35. GGBJfS then laddered out (≈ break-even).
2. **The first tracked main-run buys came before any bumping:** 67Ptgd at 05:09:27, and the sssssw/omegoM/2FdJD3 cluster at 05:09:49–05:10:21.
3. **05:10:15–05:10:55: bumping during a stall.** Axiom pair 6FZ1Ra (0.000978 SOL buys) and UuAvcG (0.0006 SOL buys) fired about 36 micro-buys while r_sol sat flat at about 5.3. That is roughly one per 1–2 slots.
4. **05:10:56–05:11:03: the move.** A second Axiom pair, FczAVr and DVMkhi, bought 1.4667 SOL each in the same slot. Then 2H6Dwr bought **6.91 SOL** (8.8 → 15.7) and started laddering sells within 1 s; it finished +2.1 SOL on the curve. FLASHX buyers piled in, including BDRubJ with 5 identical 0.4298 SOL buys and 5iRNtt with 4.89 SOL, taking r_sol to 22.8 by 05:11:00.
5. **05:12–05:13: the largest tracked-entry minutes** (13 and 11 tracked buys), after the bump plus whale.
6. **Later bumping bursts:**
   - 6FZ1Ra kept bumping (05:16–05:45, 127 micro-buys total). It is net +0.73 SOL on the curve.
   - 05:22: 18 micro-buys while sells nearly stopped.
   - **06:01:59–06:02:04, a dispersal triad:** moeypi, GT16BV and 64Eo13 each bought about 1.6 SOL at 06:00:48 at r ≈ 46–50. Each then fired 21 micro-buys in the same 5 seconds (63 total) **while price fell 50.8 → 29** through 1.5–5.6 SOL dumps from other wallets. All three sold at 06:02:08 and lost about 1.7 SOL combined. Tracked bots bought into this dip: Scalp 0.63, RCB16 0.81, RCB 1.24, Fleet45 ×3.
   - 06:20–06:26: 3JQvki, after a 3.52 SOL buy at r 32.6, sprayed 44 micro-buys plus repeated 0.044 buys through the `FHpcNSe6` relay during the final push to graduation.
7. **Tracked wallet 5veTCy ("Real Coin Bot 30") is itself a micro bumper:** 34 buys of exactly 0.001975 SOL, each with a matching sell, about 0 PnL.

**Round trips (same wallet buys then sells within 10 slots).**

| Phase | Round trips | Wallets | Within ±5% (near-flat) | Gross SOL (both legs) | Share of phase volume |
|---|---|---|---|---|---|
| Launch | 59 | 30 | 12 | 71.5 | ≈ 13% |
| Main run | 23 | 18 | 5 | 49.9 | **3.4%** of 1,450 |

- No same-transaction (atomic) buy+sell was found.
- 9 of the main-run round trips were by tracked bots.
- **Conclusion:** round-trip churn was minor in SOL terms.

**Fresh / dispersal wallets (sample of 22).**
- **Only one fresh cluster was confirmed.** Parent `moeypi…` (1,000+ txs since Oct 11 23:19) funded `GT16BV…` with 8.16 SOL in that wallet's first-ever tx at **05:04:23, about 5 minutes before the main-run ignition**. It also funded `64Eo13…` (first tx 00:50, 0.75 SOL). The three traded in lockstep: same second, same router (FLASHX).
- `4qzJLi` (micro bumper via GMGN) was first funded on Oct 10 by `EMXJqH…`.
- Every other sampled wallet already had 1,000+ txs and was established before this coin: DGma4U, GGBJfS, 2H6Dwr, 6FZ1Ra, UuAvcG, FczAVr, DVMkhi, 3QJ1Dz, CHCLtC, 5iRNtt, BDRubJ, and the revival wave wallets.
- **Conclusion:** the ignition was done by high-frequency trading wallets, not freshly dispersed wallets.

**Aggregators and relays.**
- Jupiter (JUP6): 218 trades (199 in the main run) from 75 wallets, including 31 micro-buys. It played no material role.
- 529 trades had a fee payer different from the trader:
  - `FHpcNSe6` signed 242 trades for 79 users via program `6Vo3245…`, and also signed the periodic no-trade curve txs about every 15 minutes since Oct 1.
  - `AgmLJB` signed 174 trades via DFlow.
- Top routers by trade count: FLASHX 1,003; 6Vo3245 997; Axiom `term` 429; GMGN 341.
- Revival failed txs: 422 Axiom `term` nonce rejections (duplicate fan-out sends), 198 sells against uninitialised token accounts, and 51 Pump slippage errors (6042).

## 4. Creator and launch snipers (measured)

- **Dev / "washey" (D9gQ6R):**
  - Bought 2.963 SOL in the create tx.
  - Sold all 96.4M tokens in 3 sells within 5 s: 1.13 at r 8.2, 1.63 at 17.6, 3.23 at 14.0.
  - Result: **+2.83 SOL net**. The 3.23 SOL sell was the 2nd-largest launch dump.
  - Neither dev wallet traded again; they held 0 tokens through the revival.
- **Launch snipe:** 7 different buyers in the create slot +2 (10.19 SOL), with 8,019 failed txs in the first 400 slots. The failures were mostly sniper-program custom errors (Db8hf6 code 7 ×3,110; DhpyNW code 13; BevFQ2 code 3) and Pump slippage errors.
- **Tracked bots bought the dump absorption at launch:** snipebot and Fleet39 bought at 20:07:16–20:07:26 right after 2LSncY's 3.31 SOL sell and 3TZkRo's 2.58 SOL sell, and r_sol recovered to 32–34.
- **They did the same in the main run.** After each of the 10 largest main-run sells (7.87, 6.23, 5.56, 5.07, …), 1–5 tracked buys appeared within the next 30 trades, mainly from Fleet45, Scalp40, RCB28, RCB16 and RCB33. That is consistent with dip-absorption rules.

## 5. Why the tracked bots piled in

**Inferred, ranked by evidence:**

1. **A dead ex-runner suddenly woke up.** The coin had a 45.6 SOL launch high and had sat at 0.04 SOL for 12 days. At 02:09 a leader wallet, DGma4U (via GMGN), bought 1 SOL. In the **same slot**, followers FjpP8R, CNBuuR and 8eftoR bought; one slot later came 6Qt8a3, H1gcwL, and **tracked Fleet Bots sssssD and sssssw**. When DGma4U sold at 02:11:25 and again at 02:36:43, the same set sold in the same slot. This pattern repeated at 02:31 (inferred: copy-trading of DGma4U or a shared external trigger). The Fleet bots' revival entries look like copy or shared-signal entries, not curve-state entries.
2. **The main-run ignition was a burst of size from established HFT wallets.** 0.49 → 0.98 → a 4.7 SOL single slot (Axiom pair + 2.96) took r_sol from 2.6 to 7.4 in 23 s. Then a second Axiom pair plus a 6.9 SOL whale took it from 8.8 to 22.8 in 4 s, which pulled in a FLASHX crowd. Tracked scalpers (omegoM, Fleet45, RCB23) entered on the first burst; the Real-Coin-Bot swarm entered after the second.
3. **Bumping was present but secondary.** Micro-bumping began **44 s after ignition and after the first tracked cluster**. It ran during a stall (r ≈ 5.3) right before the whale, and recurred at stalls and dips (05:22, 05:43, 06:02, 06:20). It plausibly kept the coin at the top of "recent trade" feeds and inflated trade counts (25% of buys). It contributed only 0.4% of buy SOL. Real SOL flow (839 unique buyers, 767 SOL bought) carried the curve to graduation, so this was **not** a fake-volume-only pump. Explicit wash churn was small (3.4%), and the one fresh dispersal triad lost money.
4. **Continuous high activity and dip absorption.** The 20–40 SOL chop gave 1–2.5 SOL dumps followed by rebounds. Tracked bots repeatedly bought right after large sells (Section 4) and traded in and out with median holds of 8–60 s. That produced the "going crazy" trade counts: Fleet45 126 trades, ARu4n5 86, Scalp40 80, RCB30 68, RCB33 58, Fleet39 54.

**Observable in real time at entry (no hindsight):** the old all-time high of 45.6 versus the current r_sol of about 0.04, the 12-day dormancy and the revival-start timestamp; leader-wallet identity (DGma4U) and same-slot follower count; size of the ignition buys (≥ 2.9 SOL single buy, ≥ 4 SOL in one slot); net SOL flow over the last 30 s (+4 SOL) and unique buyers (≥ 12 in 30 s); the running micro-buy count and micro-buyer concentration (one or two wallets via the same router); size of the most recent sell (a dump) combined with the buy response in the next N trades; and the dev having already fully exited.

**Candidate causal entry features suggested by this coin:**
- `revival_flag`: previous all-time high ≥ 30 SOL, current r_sol < 1, dormancy over 24 h, followed by a ≥ 0.9 SOL buy.
- `ignition_burst`: SOL bought in the last 5 slots and the largest single buy (here 4.7 SOL in one slot; then 6.9 SOL in one buy).
- `leader_follow`: a known leader wallet bought, plus the count of same-slot followers.
- `flow_30s`: net SOL and unique buyers over the last 30 s, with the buy/sell ratio.
- `micro_concentration`: share of micro-buys from the top 1–2 wallets and whether those wallets share a router. High concentration means bumping (a warning sign, not support).
- `fresh_cluster`: buyers funded by a common parent within the last hour (here the moeypi triad, which bumped during a dump).
- `dump_absorption`: a sell of at least X SOL followed by K buys within N trades, with r_sol recovery measured before entry.
- `phase_ath_distance`: entries 5–40% below the running phase high did better than chasing new highs on this coin. This is a single-coin observation, not an edge claim.

Not established: the off-chain trigger for 02:09 or 05:09 (social posts, DexScreener, Telegram calls) cannot be seen on-chain. The motive for the triad's micro-spray is also unknown; it is consistent with bumping to mask a dip, but that is inferred. No backtest or PnL replay was run; the bot PnL figures above are realized on-chain receipts and curve amounts, not strategy estimates.
