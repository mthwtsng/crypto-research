# Repeated custody fabrication detector V4

User authorized replacing the old fake-coin admission logic after providing Gazk (October 11 local / October 12 UTC, 2026). This is a narrow structural risk heuristic, not a fraud certificate, zero-false-positive guarantee, or profitability result.

## New block boundary

Every condition must belong to one current/prior launch comparison:

- A fresh, complete bounded holder-owner snapshot with actual mint supply; incomplete, inconsistent, future or stale holder baselines remain Unknown and skip entries.
- At least four successful, authenticated, pairwise-disjoint buyer→recipient token relays. Each matches an exact raw token purchase in a strictly earlier chain slot; the initial relayed inventory covers at least 50% of actual supply. Protocol PDA/vault swap legs are excluded.
- The current relay recipients still hold at least 20% of actual supply in the observed holder sample. Already-sold tokens are not counted.
- A different earlier launch has the matching normalized relay-allocation recipe (within one basis point per allocation), and an already observed >=90% real reserve drain from a >=20 SOL peak. Curve and authenticated AMM reserve peaks are kept separate. Graduation is not a zero-reserve rug.
- At least two distinct current/prior recipient pairs repeat a material direct System funding amount (>=0.01 SOL) from matching exact sources; two different funding sources are required. Funding must precede each launch by at most 24 hours and precede its relay on chain. Known service/exchange/sponsor sources are excluded. Shared funders, fee payers, wallet reuse, timing, chart shape and volume alone never qualify.

These round thresholds are initial guardrails. The selected casebook does not establish their precision or optimality. Stronger independent ownership/custody evidence could support additional lanes later; the present detector does not guess them.

## Replaced and retained behavior

V3's narrow launch-proximate funder plus payer/cohort veto is removed. The old ten-minute receipt and wallet-history rings are removed from the runner. The holder collector remains a current balance/supply source, with its old DTO fields retained for compatibility; they cannot independently block. Watch continues to permit entry with explicit partial coverage. The existing tracked-wallet exception is preserved and logged. Canonical strategy entry predicates, sizing, cash, inventory and exits are not changed by this replacement.

History persists inside the custody runtime checkpoint for seven days, bounded to 4,096 mints and bounded per-mint evidence. Truncation counters are durable. Two asynchronous RPC workers collect early parsed token transfer and direct funding receipts independently of strategy evaluation. Their scans are bounded and can miss buried receipts, same-slot ordering, rotated wallets and older activity. Failed or unavailable receipts cannot manufacture positive evidence. Outcome polling includes learned recipes that were never bought.

The optional `GHOST_FAKE_HISTORY_BOOTSTRAP_PATH` imports reviewed receipt-backed history, never a mint blacklist. `scripts/import_fake_coin_casebook.py` verifies transfer ownership/deltas, original buyer matching, material System funding witnesses and authentic quote-vault outcome metadata. The generated seed contains eight verified relays across Cfiyy/DgT6, eight verified material funding edges, and one prior deep-drain outcome (Cfiyy). Import-time availability is explicit: the seed cannot retroactively justify a block on either historical entry. The launcher uses the seed only when the file exists; the current generated file is `data/fake_coin_history_seed.json`.

## Casebook coverage

Cfiyy→DgT6 supplies the corroborated relay/funding recipe. Cvy, 7xJK and the latest [Gazk pool](../fake_coin_case_CvyUsq_20261011/SIXTH_COIN.md) show a recurring synchronized-trading cohort; their beneficial custody/funding relationship is not sufficiently proven for this hard-block lane. GKGn has a different extraction sequence and a creator-funder association. None of those facts alone qualifies them for a V4 hard block. Cold-start or incomplete relationship coverage will miss some fabricated coins. Blocking all six just because they later declined would leak outcomes and broaden false blocks.

## Verification and runtime

`cargo test --offline --bin curve_detector`: **299 passed, zero failed**, including strict-rule negative controls, the actual Cfiyy transfer RPC fixture, caught failed inner invocations, research-availability cutoff and checkpoint continuity. `cargo build --offline --release --bin curve_detector`: passed (existing repository warnings remain). Launcher shell syntax and dashboard/importer Python syntax passed. `git diff --check` passed. Source implementation and the rebuilt local release binary are separate from activation of the external running shadow process. No live transaction, runtime restart or strategy profitability comparison was performed by this work.

## What I would investigate if data and tooling were unconstrained

Collect complete funded-owner and token-custody graphs for the recurring Cvy/Gazk group, including their earlier AMM exits and wallet rotation paths. Compare frozen entry-time features with ordinary bot-heavy launches, transfer/privacy workflows and service-funded accounts; measure false blocks and missed labeled coins on later untouched dates before claiming broad coverage or improved profitability.
