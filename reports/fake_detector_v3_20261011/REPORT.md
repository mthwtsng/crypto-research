# Fake-coin detector replacement — relationships and retained supply

User-authorized replacement, October 11, 2026. This implements buyer relationships, current retained supply, and expiring re-evaluation. Demand replacement/selling pressure is excluded from fake classification as requested. Strategy entries/exits and bankroll limits are unchanged by this work.

## Resulting admission behavior

The old poverty/count-majority/single-low-SOL, block-0/early-volume and raw unlinked top-N concentration fake-coin vetoes are removed. The S2 strategy's own canonical concentration predicate remains an entry definition, separate from fake screening. Low SOL and transaction fingerprints remain recorded diagnostics, not independent reasons to block. Failed Pump-network activity is collected in a separate metadata log; it cannot create successful trade volume or update curve reserves. Failed activity is not assigned to a mint from untrusted failed logs.

The new detector blocks only a corroborated group: at least 3 current holder wallets share verified successful direct funding from a source whose complete bounded launch funding window shows no more than 8 outbound wallet destinations, and the group retains at least 20% of actual mint supply in the current sampled accounts. Corroboration requires that funder paying for at least 3 distinct buyer receipts, the same multi-buyer set recurring across at least 2 receipts, or the same funded buyers recurring across observed launches. These are association and coordinated-inventory risk facts, not proof of fraud or identical ownership. A shared exchange/service/sponsor or an unverified, truncated source profile cannot establish narrow funding scope.

Thresholds are configurable with `FAKE_MIN_CLUSTER_WALLETS` (floor 3) and `FAKE_MIN_RETAINED_SUPPLY_BPS` (default 2000). They are initial risk heuristics, not empirically calibrated bot probabilities or profitability claims. Common funding alone, static wallet balances, order sizes, program routes, and regular chart/timing alone cannot hard-block.

Current owner amounts are grouped across the largest 20 token accounts and normalized against authenticated `getTokenSupply` raw units. This is a retained-supply lower bound in a bounded current-owner sample, not complete transfer/escrow custody or a top-20-unique-wallet census. Unknown owner/supply state skips entry. Reliable custody with partial relationship coverage yields `watch`, which permits entry and logs the coverage gaps. `clear` means no qualifying group in the covered scope, not a safe coin.

## Freshness and bounded collection

Holder state expires after 30 seconds. Clear/watch snapshots re-screen at 10 seconds; blocked groups re-screen at 5 seconds; unknown retries remain 2 seconds/5 seconds when rate limited. A blocked mint is no longer excluded from rescreening. Refreshed holdings can clear a rejection after the group sells down. Old checkpoint permanent flags are cleared while paper custody/cash are preserved and new admission waits for fresh evidence. The existing user-authorized tracked-wallet whitelist exception remains; bypassed verdicts are labeled explicitly.

Funding probes cover at most 8 holder wallets, 10 address signatures and 2 transaction receipts per wallet, with concurrency 4 and a shared approximately 2.9-second funding-evidence deadline. They inspect successful parsed System transfers and preserve actual signature, slot and block-time provenance; account-creation funding is diagnostic and does not satisfy the pure engine's transfer edge. Shared sources on at least 3 sampled wallets receive at most 2 source-profile scans, each bounded to 16 signatures. A profile is complete only if signature enumeration reaches the declared start (or exhausts the address history) and every relevant successful transaction is available and parsed. Outer and inner System instructions are included. Missing data, truncation or timeout remains explicit partial coverage.

The source window is 5 minutes before launch through 30 seconds after launch, clipped to evidence availability; no future window is claimed. Source-profile provenance must match that window and be no more than 30 seconds old. Source cache expiry is 20 seconds. Completed recipient funding intervals are cached for 60 seconds only when their actual time bounds cover the next request. Relationship evidence has a 10-minute horizon. Launch attribution requires an observed creation receipt; missing launch data cannot fabricate narrow-source evidence.

Successful receipt logs now include fee payer, signers, ordered resolved program IDs and a diagnostic transaction fingerprint. Per-mint receipt rings are bounded to 256 records/10 minutes and 4096 mints. Successful buyer/mint history is capped at 100,000 records/10 minutes; exact recurring addresses provide positive co-buy evidence, while incomplete overall history remains labeled partial. Neither network work nor RPC waits occur inside entry/exit quote evaluation.

New audit paths: `data/ghost_fake_detector.jsonl` and `data/ghost_failed_activity.jsonl` (environment overrides supported). Summaries expose effective policy, coverage, current statuses and active unexpired blocks. Dashboard `/api/shielded` uses current V3 blocks; historical records remain available on disk. Risk-log write failure cannot authorize a later identical unlogged verdict. Admission is checked before pending paper buys land; existing funded-position exits remain independent of admission.

## Validation and activation

The full detector binary test suite passed 244 tests, including current custody/supply RPC mocks, source fanout/truncation/timeouts, graph corroboration, cross-launch buyers with separate fee payment, stale/future evidence, sell-down recovery, receipt failure isolation, old JSON/checkpoint compatibility, cancellation/cash conservation and risk-log retry. Dashboard current/expired block and older-runner compatibility checks passed; Python syntax, shell syntax and diff checks passed. The offline release build succeeded (53.70s). A read-only Alchemy smoke check completed in 0.568s with 18 sampled wallet owners, actual raw supply 999959094186865, a complete holder snapshot and explicitly partial funding coverage (three-wallet smoke budget). This confirms RPC parsing and partial-coverage reporting, not detection accuracy. Build and final artifact hashes are recorded in MANIFEST.json; host activation is not inferred from source edits or tests.

No host `curve_detector` process was visible in this workspace during implementation. Source/build completion does not prove that the user's running shadow process has restarted. Use the existing `bash scripts/run_shadow_detector.sh` launcher on the host to load this version; it preserves checkpoint custody. Do not run a second collector against the same live output files.

Primary reference for failed-receipt semantics: [Solana transactions](https://solana.com/docs/core/transactions). Current versioned RPC support uses integer `maxSupportedTransactionVersion: 1`, per [Solana versioned transactions](https://solana.com/docs/core/transactions/versioned-transactions). RPC metadata fields are described in [Solana JSON structures](https://solana.com/docs/rpc/json-structures).

What I would investigate if data and tooling were unconstrained: complete token transfers/escrow and historical group custody; broad source/service/exchange labels; deeper multi-hop funder graphs; persistent deployer/buyer cohorts across days; prospectively labeled manipulation versus ordinary coordinated traders. None are assumed present in this implementation.

## Result card

```text
engine + source revision: Rust relationships_retained_supply_v3; HEAD and exact worktree/binary hashes in MANIFEST.json.
data: synthetic correctness fixtures and bounded read-only RPC smoke if recorded; earlier inspected log sample is development context, not validation.
rules frozen before data?: new user-authorized implementation; initial 3-wallet/20%-retained thresholds are heuristic.
look count: one detector design, correctness revisions; no optimized profit variant or selected winning threshold.
placement/stress: fast/central80/central85/slow and fee sensitivities not run; no replay/PnL claim.
attempts/closed/failed/unresolved: not a funded strategy experiment; no orders submitted by this work.
PnL/drawdown/largest winner: not calculated.
bug alarms: funded-replay alarms not applicable; atomic successful receipt handling, failed-state isolation, evidence timestamps/windows, freshness, custody/cash and no-unlogged-admission regression checks pass.
verdict: undetermined, retrospective for detection/performance; implementation correctness checks pass.
what changes verdict: authenticated host activation, prospective logged groups with fuller relationship/custody coverage, labeled false-positive/false-negative review and later frozen evaluation before effectiveness/profitability claims.
```
