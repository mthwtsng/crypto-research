# RPC routing and acceleration review

Updated 2026-10-09 UTC. This review covers the read-only RPC layer used by the
active cohort collector for August 18–September 30, 2026. It does not establish
that the target rates are sustainable or that collection throughput improved by
a measured amount.

## Routing decisions

- Enhanced `getTransactionsForAddress` is Alchemy-only. Alchemy's historical
  pagination has been used for the complete address histories. Shyft's prior
  alternate probe returned an empty page, and Solami uses provider-specific
  cursors while historical time-filtered coverage has not been established.
  The collector therefore surfaces an Alchemy failure for retry; it does not
  let an empty alternate page mean history is exhausted or pass one provider's
  pagination token to another.
  The existing cache audit found 931 enhanced-history receipts, all tagged
  Alchemy. Cache reads for this method accept only Alchemy-tagged receipts;
  an unproven alternate page is ignored and replaced only after an Alchemy
  success.
- Historical `getBlock` probes ran Alchemy first for one finalized,
  signatures-only sample in each month, then tested Shyft and Solami at the
  same slot. A secondary is eligible for transaction-index verification only
  after its ordered signature array exactly matches Alchemy's at that month's
  sample.
  Neither secondary passed, so signatures-only historical block calls stay on
  Alchemy. Full transaction-detail blocks also stay on Alchemy because only
  signatures-only secondary behavior was probed.
- `getTransaction`, `getBlockTime`, and other non-enhanced methods are spread
  across providers by a stable cache-key hash. A valid
  `COHORT_RPC_PREFERRED_PROVIDER=alchemy|shyft|solami` setting moves that
  provider to the front where the method's routing policy permits it. Null
  `getTransaction` and `getBlock` results are unavailable receipts: the caller
  tries another provider when one is allowed by that method's route and never
  stores null as success. At present, historical block probes did not qualify
  a secondary.

## Historical block probe evidence

The full probe record, including sample slots, UTC block-time boundaries,
provider timings and signature comparison counts, is in
[`RPC_CAPABILITIES.json`](RPC_CAPABILITIES.json). Probes requested signatures
only and did not retrieve transaction bodies.

| Month sample | Alchemy | Shyft | Solami | Secondary eligible |
|---|---:|---|---:|---|
| August, slot 441666345 | 1,869 signatures, 0.450 s | RPC error `-32009` | 1,175 signatures, 5.295 s; missing 694 Alchemy signatures | No |
| September, slot 447527916 | 1,643 signatures, 0.438 s | RPC error `-32009` | 975 signatures, 1.586 s; 865 shared, 778 Alchemy-only, 57 Solami-only | No |

Solami's August list was an ordered subset, but its entries no longer occupied
their canonical block indexes. Its September response also differed in set and
order. Neither can verify `transactionIndex` by array offset. Shyft supplied no
usable signatures at either sample. The Alchemy timings are single-probe
observations, not sustained throughput benchmarks. The boundary probes used
Alchemy `getBlockTime` to map the UTC month split to slots 443282098 and
452119504.

## Concurrency, pacing and cache safety

Cache filenames retain the existing SHA-256 key over `[method, params]` and the
same `rpc/<key>.json.gz` location. A per-key `flock` spans the cache check,
provider request and atomic save, so separate worker processes share in-flight
work. A cached receipt records the successful provider for provenance; valid
Alchemy receipts and exactly parity-proven block receipts are reused without
replacement. Unproven alternate enhanced-history or block-signature receipts
are ignored. Old null block/transaction entries are discarded as unusable
coverage.

Provider requests use process-shared file locks for bounded in-flight slots and
start-time pacing. Configured ceilings are 10 requests/second for Alchemy and
5 requests/second for Shyft and Solami, with maximum simultaneous requests of
8, 4 and 4 respectively. A 429 halves that provider's shared rate scale and
applies exponential backoff; successful traffic slowly restores the rate.
These ceilings are controls, not observed provider entitlements. The probe did
not validate sustained rates. `RPC_EVENTS.jsonl` appends are locked across
processes and contain no endpoint credentials or response bodies.

## Validation and limits

`rpc_pool.py` compiles with Python 3. The live capability probe succeeded for
Alchemy in both months, got Shyft error `-32009` in both months, and received
incomplete Solami signature lists in both months. No secondary historical
block route is enabled by that evidence. Enhanced-address alternates remain
disabled pending a separate test of complete history, empty-page semantics and
provider-specific cursor behavior. Mocked cross-process checks confirmed that
two workers sharing one cache key issue one provider call, pacing is shared
across three worker processes, telemetry lines remain parseable, null receipts
are rejected, and provider provenance is retained. This work changes the
cohort RPC module and its own capability/review artifacts only; it does not
change strategy logic or run simulations.
