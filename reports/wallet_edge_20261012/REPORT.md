# What the 22 bot wallets actually buy

The largest observed differences from our S1–S5 implementation are **entry stage, participant selection, execution cost, and repeated opportunities on the same coin**. These wallets do not share one reserve threshold, one momentum rule, or one exit style. Some are creation-stage scalpers, some buy mature pullbacks, and some have explicit named-wallet inputs to on-chain execution programs. This study identifies those distinctions; it does not recover their private source code or establish a profitable replacement for our bot.

You report that every wallet is profitable over lifetime, weekly and monthly views. That is recorded as your observation, not contradicted by a short losing slice. The new receipt accounting is deliberately narrower than lifetime PnL: transferred/inherited/unclassified inventory, open marks and associated-wallet activity remain separate. In particular, Bottimus requires controller/child accounting.

The study collected **190,762 full wallet-history receipt rows**, with a separate succeeded-only supplement for spam-heavy wallets, and examined **455 outcome-blind selected buy prefixes on 393 unique mints across all 22 requested addresses**. The finalized cutoff is **2026-10-12 04:12:05 UTC**. Most wallet histories hit a 10-page cap and span different intervals; this is not a complete common 21-day performance study. All 455 buys now have a separately authenticated creation anchor. Only 234 of their saved local prefixes contain creation: recovering an old creation receipt establishes age and creator, but does not repair the missing intervening price/custody history.

## The differences that matter most

**Our entries often address a later opportunity.** The frozen master paper ledger was joined to actual source buys on the same mint, choosing the closest source buy separately per wallet within 300 seconds. Russianbot bought before our paper signal in 118 of 130 shared-mint comparisons, a median approximately 32.5 seconds earlier, and had already completed its matched source cycle in 83. Cbot7 had already sold in 37 of 53 comparisons; its median buy was approximately 21 seconds earlier. These are comparisons with paper signal anchors, not real user fills or a replay of alternative entry profits. They nevertheless establish a large stage mismatch that a few milliseconds of sender improvement cannot explain. Some source sales were losses; “already sold” is not synonymous with “missed guaranteed profit.” See [the signature-level comparison](shadow_overlap.json).

**There are two distinct early-flow profiles.** Cbot7 bought immediately after another authenticated buy in 24/24 selected entries; its median coin age was 9.5 seconds, real SOL reserve 8.39, and preceding five-slot net flow +3.34 SOL. Russianbot used much smaller curve inputs (median 0.094 SOL), median coin age 3 seconds and reserve 8.44 SOL, with shallow observed pullbacks. Snippebot is more clearly a creation-stage trader: 16/17 sampled entries were in the authenticated creation slot, all 17 in the same blockTime second as creation, median pre-buy reserves 2.80 SOL and typical curve input 2.07 SOL. Its recovered completed holds have median three seconds. Snipebot and 5DC3 also have very early entries and one-second median completed holds. These source trades are execution-sensitive candidates; their observed profit cannot be transferred to a 40–50 ms implementation without modeling whole-transaction landing, failures, impact and costs. Same-slot RPC order does not reveal millisecond decision time.

**Mature pullbacks are a different family.** 8TPkr’s sampled coin age median was 123 seconds, reserve 20.67 SOL and local observed drawdown 19.5%; half its selected buys immediately followed a sell. Its preceding five-slot net flow median was negative. This is unlike a universal positive-momentum filter or an 8–18 SOL-only bounce recipe. Bottom Bidder’s age median was 104.5 seconds and local drawdown 10.5%, but 23/24 sampled buys immediately followed another buy: the observable clue is renewed demand after a pullback. Botty, bottty, asdasd and 72MU show other sell-response/recovery variants. The exact supply-risk and wallet-quality selectors behind them remain unknown.

**Several bots repeatedly trade a coin.** In the recovered clean completed-cycle subset, 8TPkr had 4,228 cycles on 2,045 mints: 2,183 cycles, or 51.6%, were subsequent completed cycles on a mint already traded in that capture. Corresponding shares were 40.5% for bottty, 40.9% for asdasd and 45.0% for Botty. Current source `src/bin/curve_detector.rs` permanently rejects a mint after a recorded close. That removes a substantial class of opportunities these wallets use. It does not prove the lock should simply be removed: our earlier repeated-dip losses remain relevant, and a later entry needs a new independently qualifying setup. The numbers are capture-bounded re-entries, not averaging down; the three former wallets have no multi-buy clean cycles in this reconstructed subset.

**KOL following is material for some wallets and weak as a universal explanation.** The strongest case is 7ovu: 15/15 selected successful buy receipts include positive pre-buy token balances for named KOL/tracked-wallet owners on the traded mint, alongside named-account inputs to its custom execution program. The observed holders include Cupsey, tru, Cented, theo, Sebastian and the roster’s “Tracked guy.” Eight of fifteen buys also had a known KOL buy in the prior two slots. This strongly supports investigating a holdings-dependent wallet-following mechanism, while the custom program’s exact predicate remains undecoded. See [the owner/token-account evidence](held_leaders.json).

For nbot and Fhbh, 12/24 sampled buys each had a known KOL buy within two prior slots. Fhbh also passes named wallets to custom programs. Those are substantial following clues, with independent reaction to the same market event still a competing explanation. Buek passes many named wallets into its custom program, but only two successful SOL-buy prefixes were recovered; its private trigger is unresolved. For the 348 primary entries, known-KOL prior-five-slot presence is only 34/348 (9.8%) versus 288/1,980 (14.5%) for the matched controls. Cbot7 and Russianbot each have zero such recent-KOL matches in their 24-entry samples. This does not exclude delayed, private or unlisted-wallet following. Among the 22 supplied bots, immediate two-slot pair associations generally explain only a small fraction of buys and frequently occur in both directions. See [roster lead–lag diagnostics](bot_lead_lag.json).

**Bottimus is a controller with twelve authenticated trading signers.** Repeated co-signing, direct funding and a successful sweep program bind the execution roles. The current sampled entries are older recoveries: median age 479.5 seconds, reserve 6.69 SOL, local drawdown 20.4%, and every selected linked buy immediately follows another buy. The group’s recovered completed holds have median 50 seconds and include partial exits and authentic Pump-to-PumpSwap carryovers. One manually traced source sequence held for 4,941 seconds through several curve sales and an authenticated final AMM sale. This is evidence of real migration continuity, not a graduation multiplier. Twelve signing addresses do not prove twelve different strategies or common beneficial ownership. The [group review](bottimus_accounting_review.md) preserves 248 positive observed owner/mint inventories and 2,937 unclassified token-changing receipts; zero active clean cycles does not mean zero holdings.

**Migration contributes unevenly and can matter much more than its trade count.** In the reconstructed closed source-cycle cash subset, C4J has 21 Pump-entry/PumpSwap-exit cycles with +6.7816 SOL cash, versus +0.4051 SOL from its other 394 closes; captured failed-payer network fees are a separate 1.0592 SOL. 8TPkr has 93 such carryovers with +26.6016 SOL cash, versus +69.6037 from its other 4,135 closes. Successful-leg payments are embedded in these actual cash changes, while open/inherited/unclassified custody and recoverable rent/refunds outside those legs are separate. These are source-cash partitions, not full-wallet marked PnL or profits available to our copier. They show why forcing every pre-migration position closed at graduation can discard a meaningful part of the source behavior. See [the exact partition](migration_cycle_cash.json).

## Full wallet profiles

These are medians, not recovered private thresholds. Buy-state quantities come from each fixed-hash selected entry sample; closed-hold medians come separately from the broader recovered clean source cycles. Curve SOL input excludes protocol/creator fees, network costs and account funding. Drawdown is from the highest price visible in the covered prior prefix, not a claimed lifetime ATH where earlier history is missing. Coin age comes from authenticated creation, with whole-second blockTime precision. Sparse samples and the different recent/succeeded-only/controller-linked origins are explicit in [the summary JSON](ANALYSIS_SUMMARY.json).

| Wallet / address prefix | Buys sampled | Median age (s) | Pre-buy real SOL | Curve SOL input | Observed prefix drawdown | Prior 5-slot net SOL | Completed hold (s) | Clue |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| broke bot lol | 13 | 6.0 | 14.18 | 0.988 | 0.0% | 4.49 | 61.0 | Momentum/near observed highs; recent size differs from longer capture. |
| Cbot7 | 24 | 9.5 | 8.39 | 0.454 | -2.4% | 3.34 | 11.0 | Renewed buy flow: immediately after a buy in 24/24 sampled entries. |
| russianbot | 24 | 3.0 | 8.44 | 0.094 | -7.1% | 1.93 | 10.0 | Small tickets, early flow and shallow pullbacks; brief source holds. |
| snipebot | 24 | 1.0 | 10.52 | 1.975 | 0.0% | 4.28 | 1.0 | Early momentum scalp; one-second median completed hold. |
| nbot | 24 | 23.5 | 16.26 | 3.556 | -7.7% | 4.38 | 9.0 | KOL-following candidate: recent KOL buy within two slots in 12/24. |
| bot12 | 20 | 169.5 | 22.95 | 1.471 | -3.7% | 3.61 | 25.0 | Later-stage demand/momentum; wide actual entry reserve distribution. |
| bot / 4BHBSZA | 4 | 3.0 | 11.97 | 5.679 | -0.9% | 0.18 | 5.0 | Large tickets and extra custody/signers; only four prefix samples. |
| 1 sol bot | 24 | 123.0 | 20.67 | 0.494 | -19.5% | -1.23 | 35.0 | Mature pullbacks, often after sells; frequent separate re-entries. |
| Snippebot | 17 | 0.0 | 2.80 | 2.070 | 0.0% | 0.79 | 3.0 | Creation-slot entry in 16/17; short holds and frequent partial exits. |
| Bottom Bidder | 24 | 104.5 | 8.47 | 0.563 | -10.5% | 1.10 | 14.0 | Mature pullback followed by renewed buying; 23/24 immediately followed a buy. |
| bottty | 24 | 25.0 | 9.04 | 0.988 | -19.0% | 0.35 | 5.0 | Pullback/sell-response scalps; frequent re-entries. |
| bottimus | 24 | 479.5 | 6.69 | 0.988 | -20.4% | 2.36 | 50.0 | Controller funds 12 trading signers; older recovery entries and partial exits. |
| asdasd | 24 | 40.5 | 8.68 | 0.988 | -21.4% | 0.98 | 6.0 | Pullback/sell-response scalps; frequent re-entries. |
| bot / 7ovu7sq | 15 | 33.0 | 25.09 | 4.444 | 0.0% | 5.65 | — | Strong wallet-following clue: named holder present in 15/15 buy receipts. |
| insane bot | 2 | 92.5 | 14.19 | 3.457 | -1.7% | 7.37 | — | KOL account references in custom program; only two successful buy prefixes. |
| bot / 5DC3tMy | 24 | 1.0 | 8.99 | 1.975 | 0.0% | 3.31 | 1.0 | Very early momentum scalp; one-second median completed hold. |
| boooooot | 24 | 109.0 | 14.42 | 3.951 | -14.9% | 2.29 | 14.0 | KOL-following candidate: recent KOL buy within two slots in 12/24. |
| cbot14 | 24 | 7.5 | 13.38 | 0.921 | -16.3% | -0.95 | 7.0 | Early sell-pressure/recovery entries; some adds and partial exits. |
| Botty | 24 | 56.0 | 9.67 | 0.884 | -23.9% | 0.86 | 8.0 | Recovery buyers at substantial observed drawdown; variable tickets and re-entries. |
| 1sol bot | 24 | 17.5 | 7.13 | 0.988 | -18.7% | -0.80 | 26.0 | Sell-response pullbacks; near-constant gross one-SOL sizing. |
| bot / haqqiUU | 24 | 7.0 | 3.12 | 0.741 | -13.0% | -1.22 | 25.0 | Low-reserve sell-response; observed adds and staged sales. |
| Bot / 94iQuYj | 24 | 6.0 | 23.12 | 0.988 | -14.5% | -2.78 | 1.0 | Rapid sell-response/custom execution; sparse recovered full cycles. |

## What the controls do and do not establish

The primary 348 target entries have median preceding five-slot outside net flow +1.38 SOL versus +0.76 for 1,980 same-prefix, prior-time, reserve-matched control buys. Target median recent unique buyers is three versus five for controls, and local drawdown medians are similar (−9.9% versus −10.4%). A larger generic buyer-count floor or drawdown threshold is therefore not established as the shared explanation. These comparisons are descriptive, use sampled profitable-wallet opportunities, and do not measure forward executable returns. “Outside” means noncreator address when creator is known; addresses are not proof of unrelated humans or organic volume.

## Why our current recipes can miss their opportunity

The measured differences justify four bounded research comparisons, without changing live settings:

1. Keep distinct early-flow, mature recovery and wallet-holdings families. Compare their causal entry opportunities against exact canonical and current S1–S5 definitions before choosing exits. A reserve crossing alone does not encode who bought, who still holds, or whether demand returned after selling.
2. Compare source-compatible ticket/fee economics with our fixed 0.50 SOL recipe. Russianbot’s much smaller sizing changes own impact; copying its price pattern at a larger ticket changes the experiment. Do not scale source PnL linearly or reduce the authorized sender floors merely because a source wallet pays less.
3. Test later fresh setups on previously closed coins against the permanent re-entry control. Preserve failed and deteriorating repeat attempts; source re-entry frequency alone cannot choose a profitable retry rule.
4. Compare exit timing within each family. Eleven-/ten-second median source holds for Cbot7/Russianbot, five-/six-second holds for bottty/asdasd, and one-second fast scalps differ from the current S3 grace behavior and broad runner exits. These medians are observations, not exact timers or a recommendation to force every trade out at the median.

The prior [current-strategy audit](../current_strategy_audit_20261011/REPORT.md) separately documents weak bounce entries, stale S2/S4 reclaim conditions, differences from canonical grace/invalidation/trailing rules, and historical shadow calculation defects. The current source’s S1 trough window is 35 slots and the permanent mint re-entry exclusion is present. Source capability and a dated audit do not establish the exact externally running binary/config. Historical paper PnL cannot by itself determine whether the problem is entries, exits, accounting or execution; this report uses source receipt states and paper anchors without promoting the known-defective paper-profit epochs.

## Execution costs

See [the separate exact-receipt cost audit](execution_costs.md). Costs are sampled per successful leg, with captured payer-failed fees reported separately. Protocol/creator trading fees are distinct from network fees and external payments. Provider-recipient identification is a minimum attribution, not proof of route or complete cost; unexplained non-protocol residuals stay unclassified.

The paired receipt calculation includes network fees plus observed non-protocol cash outflow after adjusting recoverable token-account rent. Unattributed payments are included as outflow but are not labeled tips; positive unexplained inflows stay separate. Hash-selected source medians are:

| Source | Sampled buys / sells | Buy overhead (SOL) | Sell overhead (SOL) |
|---|---:|---:|---:|
| Cbot7 | 114 / 86 | 0.000119596 | 0.000119596 |
| Russianbot | 102 / 98 | 0.000159886 | 0.000132443 |
| Bottom Bidder | 104 / 96 | 0.001938499 | 0.002030358 |

These subtotals exclude the separately recorded protocol/creator trading fees. Cbot7’s 200 exact hash-selected receipts have network-plus-published-recipient transfers of 0.000119596 SOL per leg. In the independently traced Russianbot buy, the network fee is 0.000059886 SOL and a distinct outer payment is 0.000100000, totaling 0.000159886 SOL before trading fees. Bottom Bidder’s traced leg totals 0.001938037 SOL, and the paired observed-overhead sample median is about 0.001942. Thus low execution cost is an observed advantage for some sources, not the shared explanation for all bots. Our 0.001505 SOL base and 0.002916 sensitivity are modeling/policy references, not measured present user fills. At a 0.095 SOL ticket, the base reference alone is roughly 1.6% per leg, so small-ticket scalps need their own cost/impact analysis.

## Evidence, limits and reproducibility

All work is read-only chain research plus report/script creation. No trading strategies, risk settings, bankroll, deployed runner or external messages were changed by this work. Existing concurrent workspace edits were preserved. GPT-6 Luna at xhigh/max handled bounded collection and reviews; GPT-6.1 Luna was unavailable, and root reviewed the method and interpretation.

Reproduce core collection with `python3 reports/wallet_edge_20261012/collect.py`, then `accounting.py`, `bottimus_accounting.py`, `entry_patterns.py --limit 24 --include-history-supplement`, `creation_anchors.py`, `held_leaders.py`, `shadow_overlap.py`, `bot_lead_lag.py`, `execution_costs.py`, and `summarize.py` in that folder. Existing manifests preserve the original cutoff and caches; separate succeeded-only extensions exclude failed fees. The source/client hashes are in [PROVENANCE.json](PROVENANCE.json); raw page request/hash/coverage details are in [collection.json](collection.json). The exact copied-entry strategy and its future returns remain untested. A complete monthly all-wallet cost/custody reconciliation is not claimed.

What I would investigate with unconstrained data: decoded custom-program predicates and full failed/no-op intent histories; past-only profitability of recurring anonymous predecessor wallets; live intent/arrival/send/landing clocks; complete creation-to-migration price, fee, custody and holder graphs; contemporaneous opportunities the bot rejected. Each would help distinguish copying, identity selection, common signals and execution advantage. Freeze any candidate before evaluating its later untouched 14–21-day outcomes.

## Required result card

```text
engine: authenticated Pump IDL/success-ancestry decoder + authenticated PumpSwap events; observed-source study, no hypothetical replay
revision: 9dcff3f509b40d78d51921509ca09e79a2eafe63; exact source/artifact hashes in PROVENANCE.json
data: requested Sep21–Oct12 UTC, cutoff Oct12 04:12:05; 190,762 history rows, six complete requested histories / sixteen capped; separate 27,162 succeeded-only supplement rows overlap the history cohort
entries: 348 recent250 + 83 sparse-wallet succeeded-history extensions + 24 controller-linked entries = 455, on393unique mints; all455 creation anchors authenticated
continuous creation-containing prefixes:234/455; recovering age does not recover the intervening tape
rules frozen before data: deterministic outcome-independent entry hash sampling; user selected wallet universe for historical profitability; exploratory features, no private rule frozen
look count: nine diagnostic factor families; no parameter/PnL optimization winner
placement fast / central80 / central85 / slow: N/A, no counterfactual fills or funded strategy PnL claimed
stress fees / scheduled sells / next-slot-tail: N/A; actual-source costs reported separately, user-placement transfer untested
attempts / closed / failed / unresolved: receipt activity and custody diagnostics, not a strategy-intent ledger; unknown marks and open custody retained
settled / open marked / combined portfolio PnL: not reconstructed for all wallets; unknown inventory is not a realized loss
max drawdown / largest-winner concentration: no hypothetical portfolio calculated
bug alarms: no replay timing/guard/threshold/after-graduation fills; raw receipt detail/order/window/hash checks pass; mixed custody excluded; prefix reserve discrepancies explicitly retained
verdict: undetermined, retrospective, for any inferred/copied trading strategy; measured source behavioral differences reported directly
what changes verdict: frozen causal rule + full opportunity/control coverage + integer fee/impact/custody central-placement replay + later untouched14–21day confirmation
```
