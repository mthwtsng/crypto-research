> Implementation update, October12 UTC: the user subsequently authorized a replacement. A narrow repeated custody/funding recipe lane is now implemented and tested; see [V4 implementation](../fabrication_detector_v4_20261012/IMPLEMENTATION.md). The original forensic mapping below records the pre-implementation evidence and remains a coverage/false-positive warning. It does not mean all six examples now hard-block.

# Mapping the examples to the fake-coin watcher

## Answer

Four examples show two recurring operational structures. The fifth, GKGn, confirms another near-floor collapse and a creator-funder association with Cfiyy/DgT6, but does not share their observed pre-entry wallets or established four-position relay template. **There is no demonstrated universal fingerprint across all five, and these selected cases cannot establish a zero-false-positive filter.** The useful next version is a persistent inventory/relationship watcher with corroborated risk decisions, rather than a single chart, size, volume or holder-percentage veto.

## Concrete evidence mapping

| Evidence family | Observed examples | Observable input needed | What it supports |
|---|---|---|---|
| Repeated early acquisition → wallet relay → selling | Cfiyy andDgT6: four whole-inventory relays match exact earlier buys; identical allocation recipe totals710.19million tokens | Successful compiled/parsed token instructions, account-key resolution, pre/post token owners and raw amounts, corresponding buy receipts, current recipient holdings | Connect current inventory to the original acquiring wallets. A repeated recipe becomes more specific with creator/holder funding links and earlier collapse history. |
| Recurring inventory/seller cohort across near-floor collapses | Prior77AXS → Cvy →7xJK; repeated large holders/sellers;219 recurring Cvy addresses on7xJK | Historical AMM andcurve trade/ownership records, collapse provenance, current custody/holdings, transfers that rotate wallet keys | Prior extraction participation plus current meaningful linked inventory is a risk signal. A seller list alone cannot distinguish common control from independent panic/copy traders. |
| Repeated large-seed and sell-slicing recipe | Cvy and7xJK each15.799270901SOL→360.271445579211million tokens, then67/74 sell slices | Creator/genesis state, whole-receipt trades, buy/sell inventory sequence | Supports a repeatable automated template. Identical output is mechanically determined by the same input/state and is not a second independent corroborator. |
| Broad recurring address cohort |112 of152 pre-entry DgT6 users previously appear onCfiyy; first20 andrepeat20 overlaps forCvy/7xJK | Durable timestamped buyer histories beyond10minutes, including AMM participation and restarts | Finds repeated groups; does not prove coordinated ownership. Compare with ordinary snipers/market makers/services. |
| Creator dump and synchronized later liquidation | GKGn: creator sells265.758million observed tokens; later31-wallet sell burst empties recovered34SOL curve | Creator acquisitions, current/custody history and later ordered transactions | Labels a collapse for study. This is not enough to certify fabricated volume before entry; ordinary creator selling is not a universal fake veto. |

## Proposed decision boundary

Use **independent evidence together**, with each fact's time and coverage preserved:

1. A verified current inventory/funding/custody relationship that is specific to the launch group. Exclude protocol vaults; distinguish transfer lineage from beneficial ownership; classify shared exchanges, service fee payers and generic funding separately.
2. Repeated behavior of that linked group across prior launches, such as the same early inventory relay or acquisition/sale template, combined with authenticated earlier near-floor extraction outcomes. Use only outcomes already observed before this coin's decision.
3. Current meaningful exposure or repeated cluster-led trading, measured from actual mint supply and successful receipts. Report retained inventory separately from gross turnover and already-disposed inventory.

Their conjunction is a **candidate high-confidence block lane**, not an established fraud certificate. The current20% retained-supply heuristic can remain a benchmark while new custody links are measured;71%/36% observed initial allocations are examples, not newly optimized thresholds. A current group with no verified relationship or no available prior behavior remains review/unknown evidence. Do not silently hard-block every recurring buyer, every transfer, every large seed, or every high-degree funder.

There must also be a separate fabricated-volume hypothesis: matched linked-wallet trading cycles and repeated turnover with verified custody/funding. Successful buys followed by sales are not themselves wash trading. Current ring evidence contains no complete transfer-aware cycle ledger, so this hypothesis is not yet measured rigorously.

## Why today's watcher missed these

- Exact-wallet history expires after10minutes; Cfiyy→DgT6 repetition was13–17minutes apart, whileCvy→7xJK was later still. AMM prior extraction/transfer history is also incomplete.
- The block rule requires a single narrow direct funder near launch. Verified fee/funding seeds here can predate launch by roughly20minutes to two hours, pass through relays, or use several recurring sources.
- It does not trace successful SPL custody transfers from early buyers into the holders it screens. The four receiving wallets can start as sellers with no buy receipt under their own identity.
- Funding completion can mean eight selected probes succeeded, while19 holders exist. Cross-launch completeness remainsfalse and a256-item receipt ring saturates.
- Partial evidence returnsWatch, which currently permits entry. All five user examples entered the paper ledger: fourS5 and oneS1, no whitelist exception or confirmed bot signature.

These are missing information/representation and admission-policy gaps. Raising buyer counts or lowering a volume threshold does not repair them.

## Implementable collection and validation order

First persist successful transaction-level custody edges and older relationship history, with event and receive timestamps, source signatures, account-owner attribution, raw mint/supply units and coverage. The current receipt record lacks the necessary full token-instruction/owner graph; obtain it from transaction/meta stream fields where available, with bounded asynchronous RPC enrichment as a fallback. Keep System funding, SPL/WSOL funding, token-inventory relays and protocol-vault swap legs distinct. Refresh current balances independently of historical relationship facts.

Then emit auditable observe-only evidence for both operational structures. Freeze decisions at each entry candidate; require prefix invariance, no future-current-rug labels, and no inferred ownership from absence of data. Separate behavioral risk from missing-coverage Watch so neither becomes an automatic safety certificate or an indiscriminate blacklist. Preserve the currently authorized tracked-wallet exception as a separately labeled policy; these five misses did not use it.

Compare candidates with ordinary launches using the same liquidity, age, platform/mode and observed history coverage, including legitimate bot-heavy coins, large seed buys, transfer/privacy workflows and funding services. Measure missed labeled cases, false-block candidates, abstentions and decision-time coverage. Freeze a candidate before later untouched14–21day evaluation. Any profitability test must use the approved replay and exact controls; none was performed here.

## What is and is not ready

Ready now: a documented casebook, authenticated transfer/funding witnesses, recurring cohort memberships, concrete collector gaps and a detector evidence specification.

Not established: fraud intent, which fraction of volume is self-dealing, all-five coverage by one rule, normal-coin false-block rates or improved trade profitability. No source/admission change was made from this selected sample. A strict precision policy will miss some unverified cases; a rule broad enough to reject all near-floor outcomes can reject ordinary failed launches too.
