# Entry-only patterns before exit refinement

Retrospective October 3–4, 600 creation-selected launches. 76 unchanged signals; no sell recipe used in these trajectories. A favorable quote/peak is an opportunity diagnostic, not realized profit. Horizon states use all complete groups strictly before the deadline; equal-second intrablock timing is not inferred. Failed attempts and incomplete horizons remain explicit.

| Setup | Attempts / fills | Executable +5% by 10s | By 20s | By 60s | Spot +5% by 20s | Median executable return at 20s |
|---|---|---|---|---|---|---|
| s1_dev_absorption | 11 / 9 | 4/9 | 4/9 | 5/9 | 4/9 | -13.4% |
| s2_survival_shelf | 12 / 11 | 3/11 | 4/11 | 8/11 | 6/11 | -3.5% |
| s3_deadman | 19 / 15 | 6/15 | 6/15 | 6/15 | 7/15 | -23.5% |
| s4_upper_ath | 27 / 16 | 9/16 | 11/16 | 12/16 | 13/16 | +3.0% |
| s5_carryover | 7 / 6 | 1/4 | 2/4 | 1/2 | 2/4 | -2.0% |

Interpretation:
- Dev absorption: fewer than half the fills offer +5% within its short exit window; selection/recovery quality needs testing, not just a higher target.
- Survival shelf: follow-through is slower—8/11 reach executable +5% by60s. Existing staged exits already show positive pilot cash; preserve this control.
- Dead-man: only6/15 offer +5% by10s; losing fills continue falling. Test recovery confirmation separately from earlier stagnation exits.
- Upper ATH:11/16 reach executable +5% by20s and12/16 by60s, versus its7–12s timeout and early8% stop. This is the clearest exit-gap candidate, though fees and failed guards still matter.
- Carryover: whole-transaction completion changes censor many paths. Early known quote trajectory can be measured; postmigration profitability cannot be concluded from this sample.

The denominator is known filled trajectories at each horizon. Censored fills cannot be counted as either failed opportunities or successful opportunities. ENTRY_SUMMARY.json includes all four placement cases, spot versus executable moves and every horizon. ENTRY_EXIT_GAPS.json links each fill to causal pre-entry features and baseline exit behavior.
