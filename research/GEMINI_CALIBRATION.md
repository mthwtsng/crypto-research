# Gemini calibration: you have been overestimating

Created: 2026-10-04 from an audit of recent research. Read with [the shared accuracy contract](BACKTEST_ACCURACY_CONTRACT.md), which you must follow.

Your recent results have consistently reported +EV. Independent replay shows most of that profit came from replay bugs and same-data tuning, not from the strategies. This file lists your specific failure modes so you can avoid them. It does not say the strategies are bad. Some may be positive. Report what the corrected engine says.

## What went wrong, with evidence

| Report / artifact | Problem |
|---|---|
| `STRATEGY_TUNING_AND_RESCUE_REPORT.md` | "next_slot" beat the faster rank1 (genesis +329 vs +6 SOL; post-dev +26.3 vs +1.8). Landing later cannot be systematically better. The cause was a next-slot buy quoted at the signal's own price. |
| `LIVE_FRESH_COINS_TEST_RESULTS.json`, `MULTI_DAY_MASS_COIN_AUDIT_RESULTS.json` | `scratch/harvest_and_test_live_coins.py`: zero possible guard failures, timers that waited for trades, sells filled before same-slot dumps, forced end-of-file sells marked `closed`, sells into graduated curves, newest-300-signature tapes, coins chosen by future activity. See `mass_claim_audit_20261004/REPORT.md`. |
| Oct 2–4 "+6.8 SOL" | Those three days summed to −1.61 SOL. +8.4 SOL came from older Aug–Sep data. |
| `mass_claim_audit_20261004/FULL_AUDIT_REPORT.md` | Correct engine, but 4 s velocity and 45 s mature holds were chosen on the same day they were scored, then called "definitive". Its +0.318 SOL portfolio is fast-scenario only, one day, with 0.88 SOL drawdown. |

## Rules for you specifically

1. **Never use the banned scratch replay code** (contract section 4) for any number you report. If you need a new strategy, add it to the approved engine.
2. **Headline the central scenario**, never the best one. Always show slow next to fast.
3. **If a slower or harsher scenario looks better, assume a bug.** Stop and find it before writing anything.
4. **Do not tune and score on the same data.** If you pick a hold, threshold or filter after seeing results, label the number "development" and give the look count.
5. **Include every attempt.** Failed guards with fees, and unresolved positions with zero-recovery bounds. No closed-only headline.
6. **No marketing language.** Banned: "breakthrough", "rescued", "definitively", "validated", "robust bedrock", "production ready", "transforms a loss into profit". Use the verdict table in contract section 8.
7. **Sanity-check magnitude.** PF above 3, win rate above 70%, or tens of SOL from 0.5 SOL tickets on short holds are almost always a bug. Investigate before reporting.
8. **Do not write unverified claims into `SETUP_CONTEXT.md`** or call anything enabled or deployed. Record results as retrospective under stated assumptions.
9. **Before finishing, red-team your own result**: name the three most likely ways it is overstated and check each one.

## Self-check before you submit

- [ ] Uses the approved engine; no banned imports.
- [ ] Central, fast and slow all reported; central is the headline.
- [ ] Slow ≤ central ≤ fast for each rule (or the exception is explained).
- [ ] All-attempt PnL, failed and unresolved counts shown.
- [ ] Parameters tuned here are labelled development, with look count.
- [ ] Bug alarms in contract section 6 checked.
- [ ] Contract section 9 result card filled.
