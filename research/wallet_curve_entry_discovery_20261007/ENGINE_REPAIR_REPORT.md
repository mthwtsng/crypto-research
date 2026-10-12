# Replay repairs before the Starting Five backtest

**Subsequent work:** the Starting Five pilot has now been run in
[core_plan_audit_20261007/REPORT.md](../core_plan_audit_20261007/REPORT.md).
This repair report records the earlier checkpoint; its counterfactual router
limitations still apply.

October 7, 2026. User directed engine repair before strategy evaluation. No production files, live orders or execution settings changed. The five-strategy backtest has not been run.

The historical curve and AMM paths now reconcile at individual token-account level. Counterfactual router execution is still incomplete, so this is a source-reconstruction milestone rather than a profitability result.

## Repairs and measured checks

| Issue | Change | Evidence |
|---|---|---|
| Missing landed-failed orders | Recovered all statuses, retained failed receipts locally, merged canonical slot/transaction-index order | 79,976 receipts recovered; 79,970 occur at/after creation. Six earlier failed attempts cannot be affected by a subsequent own buy. |
| Wallet totals hid token-account movements | Bound trades to their actual token accounts and preserved transfers between accounts owned by the same wallet | All 54 curves pass account-level source replay: 41,344 complete successful groups. |
| Temporary AMM output accounts disappeared from pre/post arrays | Infer mint membership from authenticated swap accounts and token-program transfer connections; retain unchecked transfers | All 19 previously flagged AMM custody mismatches repaired. |
| Post-trade virtual reserves were stale or overwritten | Apply retained deferred fees to real and virtual reserves; preserve counterfactual virtual differences across later swaps | All nine source paths pass 202,868 complete post-opening AMM groups. |
| Exact-input fee rounding lost a lamport | Preserve quote fee components calculated before the net-input adjustment | Receipt regression checks the Ad3gZohC one-lamport discrepancy. |
| Migration metadata pointed to repeat calls | Anchor to authenticated pool creation and atomic vault deposits, not the last successful migrate instruction | Four anchors corrected; all nine migration custody audits pass. Actual integer-second freezes are 0–1 seconds in this sample, superseding the earlier 0–12-second estimate. |

Six regression tests pass: deferred-fee reserve identity, integer fee rounding, persistence of own virtual-reserve impact, closed temporary-account transfers, rejection of routed quote-only fills, and whole-transaction rollback after a later guard failure.

Artifacts: `MERGED_ACCOUNT_PARITY.json`, `AMM_CUSTODY_REPAIR.json`, `AMM_VIRTUAL_NORMALIZATION.json`, `AMM_COUNTERPARTY_PARITY.json`, `MIGRATION_CUSTODY_AUDIT.json`, `REPLAY_REPAIR_TESTS.txt`.

## What the failed-order discovery establishes

The 79,976 receipts are landed-failed transactions, not pending orders. The original quote-only diagnostics found orders whose amounts and limits could exhaust remaining counterfactual curve supply. Those were not executed fills. The two distinct apparent completion-saving orders in Ad3gZohC and H5mBRtgR ran through Jupiter and another router. Router guards, post-swap transfers, funding and changed instruction behavior still require verification.

`failed_order_checks.py` and `FAILED_ORDER_EXECUTION_SCOPE.json` now distinguish router uncertainty, missing schemas, remaining failed Pump guards and quote-compatible direct orders. **No failed transaction is promoted to a successful fill merely because its quote passes.** Unknown cases remain explicit exposure/path uncertainty. They are neither assumed winners nor treated as established strategy losses.

## Remaining requirements before profitability claims

1. Execute or authenticate complete router transactions, including instructions after the historical failure, cash funding, account existence and compute constraints. Preserve failure effects atomically.
2. Merge their feasible counterfactual outcomes chronologically; retain account inventory and actual source fee configurations. A changed completion must not force an unchanged historical migration time or opening state.
3. Support instruction-version-3 curve/pool crossing and historical fee-tier changes where they occur; flag specific missing configurations.
4. Connect the five frozen entry/exit state machines to the repaired adapters, including independent timers, delayed reactive fills, partial inventory and retained custody during migration.
5. Test one chronological 15 SOL, 0.50 SOL, two-position portfolio with the latest user breaker matrix, breakers on/off, both exit endpoints, central80/85 headlines, placement/fee stresses and unresolved marks. Older strategy percentages and synthetic funded carryover tables do not satisfy this requirement.

The earlier 600-coin signal census found 9/12/19/27/7 signals for the five plan families. This was a causal definition/coverage check, not a strategy or exit backtest. The full 21-day source tape cited by the plan is absent at its referenced path; its summary results cannot substitute for raw replay data.

## What I would investigate if data and tooling were unconstrained

Archived validator bank states and complete router program/account snapshots would permit instruction-level transaction reexecution, rather than inferring unseen post-failure behavior. Actual sender intent logs would independently calibrate failed sends, expiries, fee policy and buy/sell placement; historical successful-match statistics cannot supply those missing outcomes.

```text
engine + revision: approved day_general extensions; exact file hashes in CHECKPOINT_VERIFICATION.json
data: existing 600 creation-sampled Oct 3–4 launches; 54 eligible curves and nine authentic AMM continuations
frozen before data: no; retrospective engine repair and source audit
look count: four earlier entry hypotheses; five plan definitions enumerated; zero new exit recipes evaluated
placement: source parity only in this repair report; fast/central80/central85/slow funded PnL not computed
stress: not run
attempts / closed / failed / unresolved: strategy funded accounting not yet computed
drawdown / largest winner / exclusion: not computed
bug alarms: source chronology/completion/atomicity checks and six regressions pass; strategy exit/PF/funded alarms pending
verdict: undetermined, retrospective
what changes verdict: complete counterfactual execution coverage, causal sell replay and shared funded portfolio results
```
