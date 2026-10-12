# Backtest accuracy contract (shared by every agent)

Created: 2026-10-04. Applies to every backtest, replay, PnL table or edge claim in this repository. It turns [the RPC landing guide](RPC_LANDING_POSITION_GUIDE.md) into concrete pass/fail rules. Agent-specific calibration: [Gemini](GEMINI_CALIBRATION.md), [Codex](CODEX_CALIBRATION.md).

**Goal: report the most likely PnL, not the best case or the worst case.** A result is only useful if it would roughly match what the bot earns live. Bias in either direction wastes the user's time and money.

**Entry discovery precedes exit optimization — user instruction, October 4, 2026.** For new strategies and entry refinements, first follow the [entry-first workflow](EDGE_RESEARCH_GUIDE.md#13-default-loop): measure whether, how much and how soon coins rise after a causal signal and modeled entry, without inherited exits. Observation horizons and favorable excursions are diagnostics, not forced sell times or realized PnL. Do not reject an entry signal because an old exit loses money. Once promising entry behavior is found, develop exits to capture winners and limit losses, then apply this contract in full to profitability claims. The central placement requirement still applies when modeling entry; an initial directional study does not need a fictional funded exit ledger. Clearly label opportunity diagnostics versus executable profitability.

## 1. The user's execution model (user-reported, October 3–4)

- Buy: signal transaction lands on chain → our buy lands **50–70 ms later, at most 100 ms**. That interval already includes detection, build and send. Do not add more delay on top.
- About **80–85% of buys land in the same slot** as the signal.
- Reactive sells (stop, trailing stop, dump trigger, urgent timer) use the **same clock**: triggering transaction lands → our sell lands 50–70 ms later, at most 100 ms. Do not add a separate detection delay on top of 50–70 ms.
- A slot is about 400 ms. 50–70 ms is a small part of a slot, not "next slot" and not "end of slot".
- Sell-path latency is not yet measured; the above is the user's working assumption. Scheduled, non-urgent, zero-tip sells have **uncalibrated** delivery; treat them as a sensitivity.

## 2. Required fill mechanics

### Entry
1. Apply the **whole** signal transaction. We can never fill before or inside it.
2. Apply the curve transactions that land before our buy, per the placement scenario in section 3.
3. Quote our buy against that state with integer reserves, the recorded fee bps, a gross fee-inclusive budget and our own impact.
4. Enforce the min-output guard against the **signal-time** quote. A failed guard is a failed attempt and pays its network fee.
5. Apply our fill to the reserves, then replay later trades against the changed curve.

### Exit
1. A trigger is evaluated **after each complete transaction**, not once per slot.
2. Apply the whole triggering transaction. **If a sell blows through our stop or take-profit level, our fill is after that sell, never at the threshold price.**
3. Apply every transaction (sells and buys) that lands before our sell, per the placement scenario.
4. Quote our actual remaining tokens with fees and own impact. Update reserves after each partial sale before quoting the next.
5. Timers are anchored to **our buy's landing**, use real `blockTime`, and fire **even when no trade occurs**. Never wait for the next trade to start a timer exit.
6. If the curve completes (`real_token_reserves == 0`) before our sell lands, there is no curve sell. See section 5.
7. Never sell at the last state because the data file ends.

## 3. Placement scenarios: one central estimate plus two brackets

Every result table must show these three, with **central as the headline**:

| Scenario | Buy placement | Reactive sell placement | Role |
|---|---|---|---|
| **fast** | Same slot, at most 1 intervening curve group | Same slot as trigger, at most 1 intervening group | Optimistic bracket |
| **central** | Mixture below | Same mixture, anchored to the trigger | **Headline / best estimate** |
| **slow** | Next produced slot, after its first 2 curve groups | Next produced slot, after its first 2 groups | Pessimistic bracket |

`next_slot_tail` (after **every** trade in the next slot, about 400–800 ms) is a **stress test only**. It is far slower than the user's setup. Report it in a stress section, never as a co-equal headline column.

**Central mixture, until a reconciler of our real fills replaces it:**
- Run it twice, with same-slot probability `p = 0.80` and `p = 0.85`. Do not invent 0.825.
- Same-slot branch: intervening curve groups `K` follow the historical matched-copy audit (132 external-source copies, `SETUP_CONTEXT.md`): `K = 0` in 29/132, `K = 1` in 20/132, `K ≥ 2` in 83/132. For `K ≥ 2`, use 2 groups, or all remaining same-slot groups if fewer exist. Note that the audit is from an older configuration; label it accordingly.
- Next-slot branch: next produced slot, after its first curve group.
- Draw with a fixed seed **per intent**, independent of outcome. Or evaluate every branch deterministically and weight it. Never choose a branch using future price.

Scheduled/non-urgent sells: run 1-slot and 3-slot landing sensitivities and label them uncalibrated.

## 4. Approved and banned replay code

- **Approved base:** the `research/day_general_20261004` engine family (`helpers/replay.py`, `helpers/build.py`, `base_engine.py`, `clock.py`). It is correct on integer quotes, custody, timers and post-dump fills. Its known gaps are once-per-slot exit checks and end-of-next-slot sell landings. Fix those gaps to satisfy section 2 and section 3; do not work around them.
- **Banned for any PnL claim:** `scratch/harvest_and_test_live_coins.py` (`replay_trade`, tape builder), `scratch/audit_multi_day_mass_coins.py`, `scratch/honest_whole_coin_replay.py`, `scratch/tune_and_rescue_strategies.py`, `scratch/test_rescued_master_portfolio.py`, and anything importing them. Known defects: stale-price next-slot entries, timers that wait for trades, sells before same-slot dumps, end-of-file liquidation, curve sells after graduation, the newest-300-signature tape, and same-slot ordering by `blockTime`.
- Data: only tapes with complete history from creation, real block order (`getBlock` index or verified curve order) and outcome-independent coin selection. Never select coins by future volume, buyers, survival or "currently active".

## 5. Accounting

- Headline PnL = **all attempts**: closed + failed (with fees) + unresolved. Also show closed-only PnL, labelled as such.
- **Unresolved is not zero, and it is not profit.** Report three numbers: zero-recovery, executable mark at the last valid state, and count. For curve completion, collect PumpSwap continuation if feasible. Otherwise report "graduated-unresolved" separately with its completion-state mark. Graduation usually means the coin went *up*.
- Lead unresolved-account reporting with **settled closed-plus-failed PnL + open marked PnL = combined last-valid marked estimate**, and the unresolved count. Zero-recovery is a separate downside bound, never a realized loss. Record each mark's venue and timestamp; last-valid curve marks are not authenticated AMM fills or synchronized end-date wealth. Exclude unresolved trades from win/loss and feedback labels.
- Use one shared funded ledger (default 5 SOL, two positions), chronologically. Do not add up standalone strategy tables.
- Fees: buy/urgent sell 0.001505 SOL base case **and** 0.002916 SOL (measured historical entry average) sensitivity. Failed attempts: network fee only. Rent reserved and refunded on close.

## 6. Automatic bug alarms: stop and debug before reporting

If any of these appear, the replay is presumed broken until explained:

- A slower scenario beats a faster one for the same rule by more than noise.
- Zero failed guards in a delayed scenario across more than 30 attempts.
- An exit lands before its timer deadline, or a timer exit has no buy-landing anchor.
- Attempts == closed (no failed, no unresolved) across more than 50 attempts.
- Any fill at exactly the stop or take-profit price.
- Any curve sell after `real_token_reserves == 0`.
- PF above 3 or win rate above 70% on more than 50 trades.
- Profit concentrated in coins whose tape doesn't start at creation.

## 7. Selection honesty

- Any parameter chosen after seeing a period's results (hold length, thresholds, first-entry rule, age guard) is **development** on that period. Its numbers there cannot be called validation.
- Report the look count: how many variants were tried for the reported winner.
- Validation means frozen rules on **later, untouched** data. The user's horizon is 2–3 weeks. One day is "retrospective, unconfirmed", not "negative" and not "validated".

## 8. Verdict vocabulary: use exactly one per candidate

| Verdict | Meaning |
|---|---|
| `positive-central` | Central scenario all-attempt funded PnL > 0 and fast > 0; slow may be negative |
| `speed-dependent` | Fast > 0, central about 0 (inside the noise), slow < 0 |
| `negative-central` | Central scenario all-attempt funded PnL < 0 |
| `undetermined` | Too few trades, or unresolved exposure larger than the PnL |

Add `retrospective` or `forward-confirmed`. Banned words without frozen forward data: "validated", "definitively", "rescued", "robust", "production ready", "proven +EV", "will lose money".

## 9. Required result card (end of every report)

```text
engine + git revision:
data: dates, coins, selection rule, tape-from-creation check:
rules frozen before this data? (yes/no; which were tuned here):
look count:
placement: fast / central(p=0.80) / central(p=0.85) / slow  -> all-attempt funded PnL each
stress (next_slot_tail, 0.002916 fees, 3-slot scheduled sells):
attempts / closed / failed / unresolved (zero-recovery and marked):
max drawdown, largest winner, PnL without largest winner:
bug alarms checked (section 6): pass/fail each
verdict (section 8):
what would change the verdict:
```
