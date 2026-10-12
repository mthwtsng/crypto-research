# Proposed strategy-specific supply-risk filters

October 10, 2026. Requested plan only: no strategy, runner, entry floor, exit, or live deployment was changed. Thresholds below are candidate definitions or existing controls, not validated fraud classifications or profitable rules.

## Recommendation

Retain the concentrated low-SOL inventory checks as the initial shared risk control. Replace gross-early-buy standalone vetoes with strategy-specific evaluation of current retained supply and acquisition relationships. Add transfer/release inventory monitoring in the background; native SOL balance alone misses well-funded dump sellers. Evaluate each family before recording a family-specific admission veto. Never let an admission filter block exits.

The canonical registry remains the exact research benchmark. Also preserve a separate captured deployed-policy control, including its documented 0.95 SOL S4 threshold, 10% entry guard, $8k floor and existing screens. These are different controls. Do not silently replace either definition with this proposal.

## Evidence and competing explanations

- [Collapse study](../../reports/rug_pattern_research_20261010/REPORT.md): two normal-mode rapid collapses shared 21 sellers; two independently traced sellers received their subsequently sold tokens via escrow claims and had >2 SOL liquid balances. This supports investigating transferred sellable inventory; it does not authenticate all 21 paths or common ownership. Ordinary distribution and legitimate vesting remain competing explanations.
- [Missed-entry study](../../reports/missed_momentum_D1Lu_20261010/ROOT_REVIEW.md): early purchased quantity exceeded 20% and the initial largest buyer exceeded 7.5%. The coin subsequently ran, but one selected path is not proof that any veto should be removed; the old exact S4 also did not qualify.
- [Shadow audit](../../reports/shadow_gap_audit_20261010/REPORT.md): the $8k floor prevents a representative S1 test; screening availability can erase crossing signals; migration execution is incomplete; the current seven-close sample cannot calibrate family-specific thresholds.
- [Momentum study](../../reports/solami_live_entry_20261010/REPORT.md): buyer breadth/net buying can precede either continuation or decline. Do not replace supply checks with another unvalidated volume/breadth threshold.

## 1. Keep the low-SOL test precise

Keep the captured deployed control exactly as it ran, including its assumed supply denominator and largest-account sample. The proposed normalized control uses the same numerical thresholds, strictly <0.30 SOL and actual wallet-owner lamports, but authenticated mint supply/decimals:

1. At least 22% of total supply is held by sampled low-SOL owners; OR
2. At least three of the five largest sampled wallet owners are low-SOL and together hold at least 10% of total supply; OR
3. One low-SOL owner holds at least 7% of total supply.

Keep these three predicates for every enabled family in the first candidate. Actual-supply normalization can change decisions even with unchanged thresholds: compare it separately against the captured legacy denominator. Do not lower/raise their numerical thresholds while changing early-buy policy; that would confound attribution. A wallet with <0.30 SOL and a small position alone does not trigger them. These are supply-risk vetoes, not findings of fraud.

For normalized/new candidate decisions, use the mint's actual raw supply. Preserve the old one-billion assumption only when reproducing the captured legacy control; log both calculations to measure their divergence. Group token accounts by wallet owner. Explicitly label the present largest-20-token-account sample as incomplete; it is not a full top-20-wallet census. Exclude authenticated curve/pool inventory from wallet concentration, but do not silently treat excluded escrow/program accounts as safe or nonexistent: route their balances into a separate custody/claimable-inventory analysis.

Positive observed threshold crossings may justify a risk veto even with partial coverage; incomplete data cannot establish a pass. Unknown ownership, supply, balance, or transfer coverage stays unknown and causes a paper admission skip when that feature is required. Do not infer a low balance from an RPC failure. Update policy metadata and every decision with the actual thresholds.

Technical basis: a mint stores supply/decimals, and a wallet can own multiple accounts for one mint ([Solana token documentation](https://solana.com/docs/tokens)). Group confirmations and allocations by successful complete transaction, because all transaction instructions execute atomically ([Solana transaction documentation](https://solana.com/docs/core/transactions)).

## 2. Replace the gross-20% interpretation

Record two separate quantities from authenticated creation coverage:

- Gross early buying: sum executed token purchases from the creation transaction through creation slot +1 inclusive, and separately through creation slot +10 inclusive, matching the two present accumulators. Both require authenticated creation coverage; first-seen midlife is not creation. Preserve both control windows separately, rather than merge their counts. Rebuys can count the same inventory repeatedly; this is activity, not current ownership.
- Current retained inventory: authenticated present holdings of those buyers, with sales, rebuying and transfers accounted for. A sale can disperse inventory; a transfer can merely split the same allocation into more addresses. Buy/sell-only balances cannot certify dispersion.

Proposed first alternative: gross early buying >20% becomes a warning, rather than a standalone all-family veto. The current edited source limits its hard veto to age <=10 seconds and cap <$10k, while earlier source/logs show broader rejection; authenticate the deployed build and scope before freezing its control. This proposal also preserves warnings after that age/cap boundary. A confirmed acquisition-linked group retaining >=20% total supply is a candidate all-family supply veto. Retain the current single/top-N concentration and low-SOL predicates while evaluating this one change. Broad early participation is not itself an acquisition-linked group.

Acquisition linkage requires token/custody evidence beyond simultaneous buying: for example, a directly traced shared token-allocation source combined with synchronized acquisition/release. Direct common SOL funding plus synchronized trades is a supporting research feature, not proof of common ownership. Exchanges, shared relays, routers and Jupiter Lock infrastructure do not establish linkage by themselves. Exact linkage strength and the retained-20% cutoff need prospective false-rejection tests; the number is a starting risk threshold inherited from the existing heuristic, not empirically selected.

Do not implement this weaker gross-buy gate until retained ownership/transfer coverage exists for the affected cohort. Until then, compute the alternative in observe-only mode and retain the deployed policy for actual paper admissions. Unknown retained inventory is not a clear verdict. In particular, do not grant automatic immunity solely because age exceeds ten seconds or market cap exceeds $10k.

## 3. Per-family policy

| Family | Re-evaluation point | Candidate veto specific to the mechanism | Historical warning handling |
|---|---|---|---|
| S1 dev absorption | After the observed developer disposal, before admission | Canonical developer disposal must hold; veto material remaining developer/linked inventory or any shared current supply-risk predicate. Keep post-trough absorption exact. Transfers are not developer sales. | Earlier developer/launch concentration may clear only on authenticated sale/dispersion; keep ancestry so transfers to associated wallets do not look like disposal. |
| S2 shelf | At the exact qualifying shelf-crossing transaction | Preserve canonical largest-holder <=20% of circulating inventory, plus shared current supply-risk vetoes. This denominator differs from total supply. | An old busy launch alone does not veto a distributed current shelf. Log recent flow but add no new demand threshold in this first experiment. |
| S3 bounce | After the second separate qualifying buying transaction | Reject two confirmations from the same transaction; a known acquisition-linked confirming pair is a candidate veto. Assess the dump seller's remaining supply and shared predicates after the sale. | A completed whale sale can remove risk; a transfer cannot certify that. Do not ban because the seller used to be large. Unknown relationships are not proof of independence. |
| S4 ATH | At the breakout transaction, with evidence already cached | Shared current supply/concentration vetoes remain. A known linked/recycled buyer cluster must not be counted as independent support in a separate candidate. Keep exact baseline entry and exit definitions. | Rapid independent purchases alone do not veto. Preserve a record of historical warnings without declaring a coin safe because its cap rose. |
| S5 carryover | At the qualifying 72-SOL crossing and through migration observation | Shared current supply predicates; separately evaluate distributed/claimable inventory and known acquisition links regardless of wallet SOL. New execution claims require authenticated AMM opening/custody/exit coverage. | Launch history is context; current retained/claimable supply decides the risk. Do not force-close or value retained migration tokens at zero. |

No higher/lower family-specific low-SOL cutoff is selected from the seven-trade sample. The justified first distinction is which inventory state matters to each mechanism, not arbitrary new cutoffs. Strong current concentration does not become harmless because a strategy is bullish.

## 4. Add the missing layer in observe-only mode first

Proposed feature work, in priority order:

1. Current real supply, owner-grouped balances, acquisition and coverage timestamps. Feasible with read-only RPC; grouping all relevant accounts needs additional collection beyond the current top-account sample.
2. Transfers and escrow deposits/claims from creation, recording donor, recipient, quantities, original timing and remaining claimable quantity. Needs new subscriptions/history coverage and decoder work; the trade-only feed does not provide it.
3. Recurrent seller/allocation cohorts defined only from earlier observed coins, with creation-to-entry lead time. Existing retrospective overlap is development; later noncollapse prevalence must be measured.
4. Executable aggregate sell impact of retained/claimable inventory against current liquidity. Requires authentic venue quote math and sequential group sales; do not divide spot-marked notional by reserves and call it executable.
5. SOL/WSOL/token funding and volume recycling, with shared infrastructure excluded. Needs bounded history and explicit unknown status. Do not revive the failed latest-20-signatures lifetime-age inference.

The first non-dust candidate is a traced recurring seller/allocation group with significant retained or immediately claimable supply. Log quantity, current concentration, release state and predicted liquidation effect. No new numerical hard veto for that feature is enabled until control comparisons establish false rejections and useful pre-entry lead time. Already-claimed tokens are current inventory, not a hypothetical future unlock.

## 5. Scheduling and data policy

- Collect signal candidates regardless of whether the portfolio would admit them. Screening selection must not erase the eligible-signal denominator.
- Prefetch/cache supply and holder evidence outside the decision path; prioritize by enabled family and approaching entry window. Do not synchronously wait for RPC at a crossing, then pretend the buy occurred at the original signal.
- Preserve the current 30-second cached-screen TTL as a control; log intervening transfer/large-holder changes and invalidate known-changing evidence. Choosing a new TTL is another experiment.
- While a required screen is unknown, record a skip and retain follow-up observations. A later clear screen does not recreate the missed signal. Only a new causal qualifying setup can authorize a later attempt.
- The $8k preference and canonical S1 cannot both define one enabled experiment. Main paper control retains the configured floor; S1 needs a separately labeled low-reserve research lane and earlier screening if included. Do not silently loosen the user's floor.
- S5 remains observational with retained custody until authentic AMM exit coverage is repaired; no fabricated settled performance.
- Replace blanket mint classification with family decision records: pass / veto / unknown, exact predicates, denominator, evidence signatures/slots, cached-evidence age, policy/build version and affected families. Record every reason, not just the first. Exits run independently of admission filters.

## 6. Bounded validation plan

Predeclare four policies: canonical registry control; captured deployed control with its actual denominator/sample and authenticated early-veto scope; normalized control changing only supply calculation; one alternative to that normalized control with strategy-specific re-evaluation and gross-early warning instead of the independent gross-buy veto, only where ownership coverage supports it. Attribute normalization using deployed versus normalized, and early-policy effects using normalized versus alternative. Leave low-SOL thresholds, sizing and exits unchanged for that comparison. Predeclare linked-confirmation and transfer/release candidate definitions separately; do not bundle many improvements and report only the winning combination.

First inspect 30–50 complete trajectories across declined, continued and surprising cases, including rejected coins and matched admitted/noncollapse controls. Freeze a prospective candidate and the later untouched 14–21-day evaluation cutoff before seeing those outcomes. This plan's existing inspected cases are development only. Keep a look log, including feature additions, threshold changes and failed candidates.

For each family report eligible signals, veto/unknown/admission counts, collapse warning recall/lead time, rejection of observed noncollapse coins, coverage and setup opportunity after a realistically landed entry. Then compare delivered exits with the canonical controls using the approved day_general engine family, Central80/85 headline and fast/slow brackets, actual fees, guards, integer impact, 15 SOL cash funding, and authentic migration continuation. Keep settled, open marked and unknown inventory separate. Compare losers avoided and continuation surrendered; a filter that merely trades less is not demonstrated better selection. Use the user's flexible research ticket/concurrency authorizations consistently within separately frozen policies.

Planning target: 500 closes overall / roughly 100 per enabled family from the existing research plan, alongside the 2–3-week horizon; not a statistical guarantee. No promote/deploy decision is based on a few selected winners or known collapsed coins.

Acceptance requires faithful metadata, no hidden shifted entry clock, prefix causality, supply/custody reconciliation, meaningful pre-entry lead time, and later evidence that supports the intended trade-off. Unknown migration exposure keeps full profitability undetermined. A worsening opportunity/false-rejection trade-off rejects this candidate, not every possible supply-risk rule.

## Implementation order if this plan is adopted

1. Fix measurement/versioning and add per-family decision logging; restore missing registry risk controls and restart continuity separately from filter experiments.
2. Introduce a policy dispatcher around unchanged entry/exit controls, with a separately captured deployed-policy control.
3. Collect transfer-aware retained inventory; run the proposed alternative observe-only while current admissions continue.
4. Review full trajectories, freeze one eligible candidate, and run the prospective comparison.
5. Promote only the supported per-family change; retain all rejected/unknown cases and their evidence.

No live deployment or filter removal is part of this planning deliverable.

## What I would investigate if data and tooling were unconstrained

Complete token/SOL/WSOL custody graphs before each signal, cluster sell-impact against authentic curve/AMM liquidity, and repeated allocation/release patterns across independent later dates. These would test whether coordinated sellable supply predicts collapse beyond balance, gross early buying and matched launch-stage controls.

## Result card

- Engine/revision: planning document; no replay. Inspected source revision d00a042d5f30e16efc9ab147567ac7a7f461cef4 with concurrent modifications; running build identity unverified.
- Data: existing October 10 shadow/missed-entry/collapse/momentum reports, all previously inspected; no new cohort, orders or PnL calculations. Full creation/transfer coverage is not certified.
- Frozen rules: this is a proposed development plan, not enabled settings; later experiment freeze/holdout required.
- Look count: one planning synthesis; four predeclared control/candidate policies proposed, no parameter sweep or tested winner. Further feature proposals require a separate look log.
- Placement fast/central80/central85/slow and execution stresses: not run; no funded PnL claim.
- Attempts/closed/failed/unresolved/marks/drawdown/winner dependence: not calculated for this proposal; historical figures remain in their source reports.
- Bug alarms: replay alarms not applicable to a planning deliverable; no pass claim.
- Verdict: undetermined for the proposed filters; retrospective development rationale only.
- What changes verdict: sufficient ownership coverage, frozen later family-level comparison, opportunity/false-rejection evidence, and approved placement-aware funded execution including migration.
