# Frozen 21-day test — collection in progress

User authorized the primary configuration on October8local/October9UTC: allfivefamilies; S1unchanged, S2age≤240s and outsidebuyers≤80 retaining40%clipat30%, S3two-group recovery75%arm20pptrail60s, S4four-second grace/half20%/6%relative trail, S5authenticated AMMcarryover. Original reproduced control is the second frozen policy. No parameter selection from this new collection is allowed.

Historical window: August18–September7UTC,21completedays,20fixed-hash ordinary launches per each of504hours, target10080coins. Known prior1840mints excluded. Earlier broad user-reported studies usedAugust14–17 andSeptember14–October4; missing deleted artifacts mean genuinely untouched history cannot be certified. Label historical transfer, not forward-confirmed. Actual later21days after freeze are needed for forward confirmation.

15SOLshared cash ledger,0.50SOLtickets,0.25cooldownprobes, no research positioncap; live cap/settings unchanged. Target500closedoverall and100perfamily are collection planning targets, not statistical proof. Do not extrapolate+0.80SOL from summed component improvements.

All threeRPCs passgetSlot. Alchemy supplies complete ordered historical-address receipts; Shyft's alternate address API returns no rows in a period containing many Alchemy-authenticated creations and is not accepted as historical coverage. Solami's history probe timed out; standard SolanaRPC fallback remains available. Provider telemetry: RPC_HEALTH.json and RPC_EVENTS.jsonl. Cache and finite retries retain failures explicitly.

Collection/resume:
`python3 research/frozen_21day_validation_20261008/collect_validation.py`

Preparation/AMM/replay pipeline (waits for complete collection):
`python3 research/frozen_21day_validation_20261008/run_after_collection.py`

Independent report after replay:
`python3 research/frozen_21day_validation_20261008/report_validation.py`

MonitorPROGRESS.json/COLLECTION.log and PREPARE_PROGRESS.json/CONTINUATION_PROGRESS.json/PIPELINE.log. PIPELINE_STOP.json is an explicit coverage failure requiring repair, never a silently dropped coin. PnLmustnotbereporteduntilREPORT_COMPLETE.json. Frozen input/source hashes: FREEZE.json; prior-use audit: PRIOR_USE_AUDIT.json. First5sampledcurves passed128source whole-transaction parity checks; this is an ingestion smokecheck, not a profit estimate.


User-authorized cap amendment: test2(control),5,10,15anduncapped on both frozen strategy policies using identical replay traces/placement seeds. Bankroll stays15SOL; unresolved positions retain capital and count against each finite cap. CAP_AMENDMENT.json records authorization before any new replay results, original freeze preserved. Report adds admissions/capacity skips/cash skips/peak occupancy/drawdown and marked/settled decomposition for every cap. No live cap change.
