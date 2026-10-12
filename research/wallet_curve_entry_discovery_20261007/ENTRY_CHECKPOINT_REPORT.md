# Entry-first checkpoint — October 7

Four hypotheses frozen after reviewing40authenticated wallet trajectories. Tested120signals on600previously inspected creation-sampled launches,0.50SOL modeled buys. Four entry looks; zero exit looks. No realized profit estimate yet.

| Entry hypothesis | Central85 attempts | Guard failures | +30s mean quote return (covered n) | +180s mean quote return (covered n) |
|---|---:|---:|---:|---:|
| broad_recovery | 40 | 7 | -5.7% (33) | +10.2% (32) |
| fresh_expansion | 46 | 3 | -4.0% (43) | +14.0% (41) |
| quiet_absorption | 27 | 5 | -5.8% (22) | +16.0% (21) |
| late_continuation | 7 | 0 | -1.5% (4) | unavailable |

These are finite-position immediate liquidation quotes after own-impact curve repricing, not delivered exit returns, funded profits or oracle sell results. Horizon coverage differs; means omit censored horizons and can be dominated by runners. Do not rank entries by these incomplete means. All seven late-continuation paths encounter the base engine’s counterparty-liquidity boundary before180s; authentic completion and AMM continuation must be recovered and modeled before assessing them. Graduation is not treated as a loss or forced exit.

Actual continuation recovery is underway for every eligible mint, including nongraduating launches, with source curve history through1,800s after the latest signal and actual pool history through at least600s after migration. This corrects the previous study’s invented opening reserves and demand surge.

Completion requirements outstanding: matched opportunity controls on the performance cohort; no-intervention parity and counterparty guard/custody verification; curve-completion transition with actual migration accounting; independent post-migration quotes and delivery; larger temporal coverage; separate sell recipes and funded shared portfolio at15SOL/two positions; fee/placement stress and bug alarms.

Result card:
```text
engine: approved day_general helpers/replay.py; initial diagnostic extension only
data:600previously inspected creation-sampled launches;40wallet histories for discovery
rules frozen before performance run: yes; hypotheses developed on historical wallet samples
looks:4entry definitions;0exit recipes
placement: fast/central80/central85/slow entry traces saved; no funded exit PnL yet
stress: not yet evaluated
attempts:120signals ×4placements;480traces;0run exceptions
unresolved exposure: no funded orders; missing continuation remains explicitly censored
drawdown/largest winner: not applicable to entry-only quote diagnostics
bug alarms: profitability audit pending; prefix and causality tests recorded separately
verdict: undetermined, retrospective
next: authenticate and replay migration; then develop and compare exits per entry family
```
