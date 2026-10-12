# Second entry/exit-gap cycle

All October5–6 data are inspected retrospective development. These tests do not establish forward-confirmed edge. Entry-free diagnostics preceded these sell outcomes. All original five strategy families and every migration carryover remain in the shared portfolio; excluding S5 is separately labelled diagnostic.

## Entry quality before sell tests

| Entry / strategy | Attempts / fills | Net +5% by20s | By60s | Median net at20s |
|---|---|---|---|---|
| baseline / s2_survival_shelf | 37/32 | 9/32 | 13/32 | -9.6% |
| baseline / s4_upper_ath | 62/41 | 18/41 | 25/41 | -8.3% |
| broad_demand / s2_survival_shelf | 17/17 | 6/17 | 7/17 | -8.2% |
| broad_demand / s4_upper_ath | 34/27 | 12/27 | 13/26 | -11.8% |
| first_time_demand / s2_survival_shelf | 16/16 | 6/16 | 7/16 | -9.5% |
| first_time_demand / s4_upper_ath | 34/27 | 12/27 | 13/26 | -11.8% |

Known filled horizons are denominators, not all submitted attempts; failures and censoring are explicit in ENTRY_SUMMARY.json. Peaks are diagnostic liquidation quotes, not delivered sell fills. Broad demand requires >=3 distinct outside wallets with >=0.05SOL aggregate buys each, largest wallet <=50% of all outside buy volume, outside sell/buy <=50%, in current plus preceding3slots. First-time demand additionally requires >=2 such buyers with no observed earlier purchase. All original shelf/ATH conditions must still hold after the complete qualifying transaction. First qualifying gated signals can occur after the original baseline signal. Addresses are not authenticated independent humans.

## Funded results

| Recipe | S2 standalone SOL | S3 standalone zero / marked SOL | S4 standalone SOL | Four-strategy diagnostic, breakers off / on SOL |
|---|---:|---|---:|---|
| baseline | -1.7832 | -2.5930 / -1.9950 | -0.0530 | -3.9663 / -3.5077 |
| broad_demand | -1.1981 | -2.5930 / -1.9950 | +0.8414 | -2.9765 / -3.0447 |
| first_time_demand | -1.1284 | -2.5930 / -1.9950 | +0.8414 | -2.9068 / -2.9795 |
| confirmed_control | -1.7832 | -0.8446 / -0.8446 | -0.0530 | -2.7224 / -2.2157 |
| confirmed_full5 | -1.7832 | -0.7840 / -0.7840 | -0.0530 | -2.6619 / -2.1551 |
| confirmed_full10 | -1.7832 | -0.7634 / -0.7634 | -0.0530 | -2.6413 / -2.1345 |
| confirmed_scratch3 | -1.7832 | -0.2700 / -0.2700 | -0.0530 | -2.1479 / -1.6411 |

Tables headline Central85. Individual accounts are alternatives and cannot be added. Cards show Central80, fast/slow, tail and historical-fee sensitivity, attempts, failures, unresolved, drawdown, largest winner and daily net. Confirmed controls use the first >=0.05SOL outside recovery buy within2slots, reserves8–18SOL; entry quote/guard is recomputed at confirmation. Full5/full10 sell the entire remaining position on executable net +5%/+10% and preserve original10/21s timers. Scratch3 uses original confirmed exit logic with stagnation checked at3s instead of10s. Every sale lands causally after trigger/intervening whole transactions; target hit does not guarantee threshold fill.

The added broad/fresh demand proxies do not repair the shelf entries’ weak forward trajectory. Confirmed bounce exits are evaluated by total losses and relinquished winners, not percentage of coins that briefly rise. LOSS_ATTRIBUTION.json isolates actual exit reasons and worst fills. No parameter or live strategy is enabled by this study.

## Cross-window interpretation

| Demand gate / strategy | October3–4 Central85 | October5–6 Central85 |
|---|---:|---:|
| broad_demand / s2_survival_shelf | +0.3297 | -1.1981 |
| broad_demand / s4_upper_ath | -0.1942 | +0.8414 |

Both windows are development. The ATH gate’s later +0.8414SOL depends on a +0.8559SOL largest winner; without it net is−0.0146SOL. It loses−0.1942SOL on the earlier window. Shelf gate remains positive on the earlier small sample but negative later. First-time gate changes only one later shelf entry and no ATH decisions, so it supplies little independent evidence. These gates do not establish a repeatable improvement.

Confirmed bounce loss attribution: at full+5%, ten target exits earn0.4717SOL while eight10-second scratches lose1.2516SOL; at full+10%, eight target exits earn0.6858SOL while ten scratches lose1.4452SOL. Earlier3-second invalidation preserves runner gains0.9738SOL but eleven scratches still lose1.1877SOL. Eight failed entry fees cost0.0040SOL in every confirmed recipe. The main loss is failed-recovery price deterioration, not the failed-entry fee budget.

## Reproduction and next work

Run next_mechanisms.py, then cycle_sell.py, then cycle_report.py from the parent study directory. SPEC.json and SELL_SPEC.json disclose all new looks. Default signals match the original180;101gated decisions pass prefix invariance. Source reconstruction proof and15focused regressions are in the parent study. CHECKS.json rechecks eight alarms, token conservation and chronological funded accounting.

Next mechanism should address demand/supply identity or causal regime abstention rather than more nearby threshold searches; unresolved completion/router execution remains a separate evidence gap.

## What I would investigate if data and tooling were unconstrained

Prior resolved shadow-trade feedback, with explicit warmup and independent evaluation; funding/holding cohort identities; replay of complete failed router instructions against archival account states. These are hypotheses requiring data/tests, not enabled filters.

## Required result cards

See CANDIDATE_RESULT_CARDS.md for every full portfolio, diagnostic and family, with breakers on/off.

## confirmed_full5, portfolio, breakers True

```text
engine/revision: repaired approved day_general extensions; working hashes CHECKS.json; base git35d8981
data: October5–6UTC;1200fixed-hash creation-selected launches; histories begin at creation;180baseline signals
frozen before data: no; retrospective development on inspected later-window data; neutral entry diagnostics before new sell outcomes
looks:18prior new recipes +2entry mechanisms +3exit mechanisms +3portfolio assemblies=26new looks, plus2original endpoint recipes
candidate:confirmed_full5;scope:portfolio;breakers:True;15SOL/0.50SOL/max2;0.25SOL cooldown probes
fast/central80/central85/slow all-attempt zeroSOL:-2.387639/-2.449551/-2.445837/-2.451396
markedSOL same order:-1.257299/-1.297046/-1.316910/-1.300899
stress tail:-2.320112;historical0.002916legfee:-2.524183;scheduled sensitivity:n/a(allurgent)
attempts/closed/failed/unresolved:39/28/9/2;zero:-2.445837;marked:-1.316910;closed-only:-1.434204
settledDD:1.438749;cashDD:2.445837;largestwinner:0.112820;netwithoutlargest:-2.558658
daily settled net:{"2026-10-05": -1.438748853};skipped:{"strategy_pause": 6, "concurrency": 118};PF:0.11791253559837926;WR:0.10714285714285714
bugalarms:8checked;ledgerregenerated;creation/prefixparity;speedmatchingandfastallclosedexplanationsCHECKS.json
verdict:undetermined,retrospective
changesverdict:causal mechanism surviving frozen later14–21-day data and complete changed migration execution
```

