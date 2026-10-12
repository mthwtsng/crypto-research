# Wallet-inspired curve entries and migration exits — October 7

User superseded standalone AMM entry research. Preserve existing artifacts; no production edits. Account: 15 SOL, base 0.50 SOL, maximum 0.75 SOL, two positions. Exclude sub-30ms-dependent signals.

Read the user attachment before continuing. Audited the source-stage accounting and carryover implementation. The carryover report is unsuitable for profitability claims: its engine adds invented 25/30 SOL AMM demand, substitutes a universal opening pool, invents migration at graduation slot+2, uses an 84 SOL threshold rather than completion, fails to reprice historical counterparties after our purchase, sells at tape end, and omits reactive stop delivery. Preserve that report as historical material; do not inherit its PnL or claimed guaranteed migration lift.

The stage buckets concern completed account cycles. Conditioning on eventual AMM exits selects eventual survivors; it does not prove that buying all similar curves works. Sampled wallet entries also include non-carryover cycles and require per-receipt venue confirmation. Negative curve-only cash with positive carryover cash is a reason to study runner preservation, not evidence to hold every position forever.

Initial measured clues from retained contexts: 88887 median reserve 7.86 SOL, age39s, drawdown29.7%, recent meaningful buyers5; 9999 median10.95 SOL, age14s, recent buyers7; sssss median13.65 SOL, age33.5s, recent buyers6. All three have zero sampled entries at68 SOL or above. Therefore a universal68–74 SOL entry rule is not demonstrated by these samples. Private rules remain unknown. Additional contexts missing for several expansion wallets must be recovered before inferring their entry rules.

Entry-first queue, hypotheses rather than recommendations:
1. Broad recovery after a mature drawdown: require newly observed distinct meaningful buyers after the sell, distinguish fresh from returning demand, compare to matched age/reserve/drawdown controls.
2. Sustained multi-wave expansion: measure buyer breadth and persistence across separate completed transactions; distinguish repeated concentrated buyers from fresh breadth. Test earlier curve entry while preserving eventual runners.
3. Late-curve continuation: compare completion proximity plus sustained demand to a bare reserve crossing. Authenticate completion/configuration; include every failed-to-migrate signal. Do not assume this is the wallets' primary entry.

Next required work: read 30–50 full source trajectories; join wallet entries to authentic curve receipts and actual migration pools; compare entries and same-coin non-entry opportunities using causal prefixes. Freeze a few entry definitions before post-entry diagnostics at10/30/60/180/600s, through migration, with central80/85 modeled buys and failed guards. Favorable excursions are opportunity labels, never executable profits.

Only after entries demonstrate opportunity, develop separate bounded sell sets per family: full liquidation control, staged realized-profit exits, runner trailing, and demand-failure exits. Replay actual AMM reserves and atomic swaps after authentic pool opening, with own impact, custody, fees, independent clocks and delayed sell fills. Preserve inventory during freeze. Missing coverage is a recoverable data need; graduation is not a terminal forced close. Fund the shared portfolio and publish all-attempt cash, marks, failed fees, concentration, drawdown and all eight bug alarms. Later untouched14–21days are still required for confirmation.

Status: source/implementation audit completed; entry discovery, authenticated continuation adapter and exit evaluation incomplete. No profitable new strategy established.

## Measured progress after the initial source audit

Recovered40fixedhash wallet histories, all authenticated curve buys and from-creation censuses, through600s after entry; no acquisition errors. Reviewed all40prior transaction sequences. Nearby earlier same-coin descriptive controls show median recent-buyer differences+5 for88887 and9999,0 forsssss,-0.5 for3VUN; samples6/5/9/10matched pairs respectively. These are hypotheses, not causal effects or independent wallet votes.

Frozen four entry hypotheses in `ENTRY_FREEZE.json`/`entry_signals.py`: broad recovery, fresh expansion, quiet absorption, late continuation. Initial600creation-sampled retrospective launch diagnostics yield40/46/27/7signals and480placement traces, no execution exceptions. Prefix-invariance tested at all120signals; three structural tests pass. Initial horizons are censored at the base replay’s completion/liquidity boundary; continuation is being collected before ranking opportunities or optimizing exits. No sell recipes tested yet. See `ENTRY_CHECKPOINT_REPORT.md`.

Authentic migration recovery includes every frozen eligible mint, not only eventual graduates. Creator fee-sharing reassignment (`migrate_bonding_curve_creator`) was found to share a migration-like name but is not pool graduation; the local collector now decodes only genuine `migrate`/`migrate_v2`. Retained historical files are unchanged.

First eight actual migrated opening states reconcile all source AMM swaps under the approved adapter with no parity errors as of this checkpoint. `ACTUAL_MIGRATION_OPENINGS.json` compares actual post-creation effective AMM spot with final curve spot: ratios approximately0.999756, not3.06. Classic curve completion is approximately85.00536SOL, not a universal84SOL trigger. Recorded integer-second freezes range0–12s. These are source state diagnostics, not executable profitability or exact within-slot timing. Remaining pipeline and continuation modeling are still incomplete.

Continuation acquisition and normalization now completed:54/54eligible mints recovered, zero acquisition errors;54curve tapes and9actual AMM pools prepared. All9AMM no-intervention source parity audits pass. Fixed a preparation watcher race that initially returned before the final four curve files were processed, then explicitly checked54/54coverage. `CHECKPOINT_VERIFICATION.json` records exact hashes, source custody gaps, tests, and the outstanding counterfactual transition requirement. Next substantive step is bridge accounting through real completion/migration, then entry controls and separate exit development. No profitability claim follows from source parity alone.

## October 7 resumed checks: custody, integer quotes and completion

Repaired all54eligible curve histories with112token-account recovery passes; no remaining curve custody gaps. Bound original instruction budgets and slippage limits to41,668trades. Corrected exact-input integer rounding and removed source-budget conversion through floating SOL. Independent event-local quote checks pass41,668trades; full no-intervention state/custody/limit replay passes41,344complete groups. These checks authenticate source reconstruction, not counterfactual profitability.

Corrected480entry paths across four scenarios have no execution exceptions. Central85 has33/40broad-recovery fills,43/46fresh-expansion fills,22/27quiet-absorption fills,7/7late-continuation fills. Failed guards remain attempts, not exclusions. No exits executed. Early fixed-horizon curve liquidation quotes do not yet reveal a consistently positive mean; see `CORRECTED_ENTRY_HORIZONS.json`. Censored graduates are retained separately and those quote means are not all-attempt realized returns.

Under fixed original public instructions, only two central85family/mint paths complete within the recovered curve prefix. Nineteen other filled family/mint paths on historically completing coins do not complete within that prefix after our intervention. This is a market-response/model-coverage issue, not nineteen established losses: original exact-output budgets/limits can revert and future private requotes are unknown. Do not force unchanged migration, discard these paths, or use a zero inventory valuation to rank entry families. Original landed-failed intents are being recovered for all54eligible curves to investigate missing public order coverage. Alchemy rejects `filters.status="failed"`; the collector now requests all landed statuses and filters locally with its original provider cursor. Session28972 runs this recovery; inspect `FAILED_INTENT_COLLECTION.log`/progress before restarting.

No version3 post-completion crossing occurred in the current480fixed-source paths. Such a crossing still requires the authenticated pool-to-be leg; the adapter must not silently treat it as a legacy partial fill. Nine AMM source reserve parity checks pass, but several AMM tapes flag unverified custody groups. Account-level curve-to-AMM continuity, historical fee-tier changes, displaced completion/requotes, ordinary-cohort matched entry controls and the shared funded exit study remain incomplete. All four candidates remain `undetermined, retrospective`.

Result card for this checkpoint:
```text
engine: approved day_general helper extension; exact file hashes in CHECKPOINT_VERIFICATION.json
data: 600 creation-sampled retrospective launches, 120 frozen signals, 54 eligible full curve histories, 9 authentic AMM pools
frozen before data: no; wallet-inspired retrospective development
look count: 4 entry families, 0 exit recipes
placement: fast / central80 / central85 / slow entry paths computed; funded PnL not computed
stress: not yet run
attempts: 120 per scenario; central85 105 fills / 15 failed guards; closes and funded unresolved accounting not yet evaluated
drawdown / largest winner / winner exclusion: not computed
bug alarms: delayed central guards present; no exit execution, so exit/PF/ledger alarms pending rather than passed
verdict: undetermined, retrospective
next evidence: complete real migration/custody continuity and public failed-order coverage, then causal entry controls and separate exit tests
```

Failed-order acquisition subsequently completed54/54curves with79,976landed-failed receipts and zero acquisition errors (`FAILED_INTENT_COMPLETE.json`); session28972 is finished. `FAILED_COMPLETION_ORDER_DIAGNOSTICS.json` finds public post-completion buy intents whose original limits are compatible with retained counterfactual curve quotes. Four central85family/mint paths have at least one quote capable of exhausting the remaining supply (Ad3gZohC fresh-expansion/late-continuation; H5mBRtgR fresh-expansion/broad-recovery). This is evidence that succeeded-only histories omit relevant public orders, not proof of execution: preceding failed intents, whole-transaction guards/custody, source funds and fee tiers still need replay. Neither the nineteen displaced paths nor these four candidate repairs establish a realized win/loss. Next step: merge landed-failed public intents in canonical order and validate whole-transaction feasibility before constructing the AMM bridge.
