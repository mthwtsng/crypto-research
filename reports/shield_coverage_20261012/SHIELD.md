# Current shadow shield and entry funnel

Frozen read-only audit: VM `ghost-v2-20261012T032117`, started 2026-10-12 03:21:17 UTC. The summary prefix was last updated at **03:44:57.339894590 UTC**; the bounded-prefix capture completed at 03:45:02 UTC. Detailed evidence, file sizes, prefix hashes, and source hashes are in [shield_funnel.json](shield_funnel.json). Counts below use that capture only; log events are VM-scoped and no later rows are joined into it.

## Shield verdict

The frozen VM records **zero hard BLOCKs**: `active_fake_coin_blocks=[]`, `total_shielded_coins=0`, and zero VM-scoped `FAKE_COIN_VERDICT` rows or mints with status Blocked. Verdict events were Unknown: 2,225 rows / 1,242 unique mints; Watch: 661 rows / 136 unique mints. Repeated rows and changing statuses mean these unique-mint totals can overlap across statuses. Recipe-scan and AMM-outcome events are separate event types and are excluded from verdict counts.

The source-reviewed policy skips admission for Unknown, permits Watch with partial-coverage logging, and hard-vetoes a current non-whitelisted Blocked verdict. The persisted run summary shows 72 current clear holder reports, 139 completed Unknown/expired screens, one in-flight screen, and zero blacklisted. Thus the available evidence does not show that the actual shield blocked any mint in this VM. A false-block rate cannot be estimated from a zero-block sample; no blocked-mint outcome cohort exists. Unknown skips may warrant coverage repair, but this evidence alone does not establish false blocks.

## Funnel and tracking coverage

The final signal-log prefix has 62 raw candidate rows across 26 unique mints. Of these, 24 rows / 14 mints had covered observed history and 38 rows / 14 mints were incomplete-history diagnostics; two mints appeared in both bases. The covered set includes 10 row instances / 9 mints with `holder_ready=true`. These are not confirmed entry-eligible opportunities: audit rows do not carry every remaining gate, and the run was in reclaim mode. Incomplete-history rows remain diagnostic even when holder-ready.

The log records 334 setup-tracking audits, 6 breakout signals, 5 reclaim-entry events, and 2 reclaim expirations. The checkpoint contains 7,764 unique curve mints: 478 complete, 6,905 with incomplete history, and 3,776 missing creation history. These checkpoint categories overlap. Its primary per-mint tracking-error counts are restart gap 3,225; creation history missing 1,610; ordered custody incomplete 581; reserve-transition gap/inconsistency 562; unscoped receipt gap 475; unrecognized successful trade 324; wallet custody differs 126; duplicate/out-of-order receipt quarantined 2.

The frozen trade log records 6 OPEN rows across 6 mints and 5 CLOSE rows across 5 mints at the cutoff, with 1 active position and 0 failed buy attempts. These are execution/funnel counts only; no PnL or edge conclusion is made. Source review indicates S2/S4 breakout signals in reclaim mode arm a watch and need at least an 8% pullback followed by a return to the level within 180 seconds. The setup audit does not record every admission gate, so the raw candidate count cannot be treated as missed buys or a complete opportunity denominator.

## Evidence limits

Summary and checkpoint identify the same VM. JSONL counts use the frozen byte prefixes and scoping rules recorded in the JSON artifact; intent/fill rows are scoped with the VM intent-ID prefix where their rows lack a top-level VM ID. Two unscoped log prefixes are retained only as bounded hashes and were not counted. Invalid JSON rows without a reliable VM identity are not attributed to this run.

The inspected Rust and launcher files describe the current worktree, not a verified running binary. The saved summary/checkpoint omit the effective `MAX_POSITIONS` setting, so its active cap is unknown (the launcher source default is not evidence of the live value). Circuit breakers are persisted as disabled. No RPC, replay, backtest, profitability, or strategy-edge analysis was performed.
