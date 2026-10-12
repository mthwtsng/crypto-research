# Ghost fill reconciliation

`scripts/reconcile_ghost_fills.py` audits Rust paper-trade intents and fills against read-only Solana RPC data. It uses the canonical transaction order returned by `getBlock`, retrieves `getTransaction` receipts for source and submitted signatures, keeps raw RPC response envelopes in a per-run cache, and writes linked reconciliation rows to `audit_append.jsonl`. It never edits the input logs.

Run it from the repository root:

```bash
python3 scripts/reconcile_ghost_fills.py \
  --intents data/ghost_trades.jsonl \
  --observations data/ghost_observations.jsonl \
  --output-dir reports/ghost_fill_reconciliation/run_20261010_review
```

The default RPC is the project Shyft endpoint. Set `--rpc-url`, `SOLANA_RPC_URL`, `SHYFT_RPC_URL`, or `ALCHEMY_RPC_URL` to select another supported Solana JSON-RPC endpoint. The endpoint is never copied into report output. The tool defaults to `finalized` commitment; use `--commitment confirmed` for provisional receipts. Requests use `maxSupportedTransactionVersion: 1` by default (`--max-transaction-version` overrides it) and can be bounded with `--next-slot-search-limit` and `--max-actual-slot-gap`.

The input can contain the Rust v2 `INTENT`, `FILL`, `FAIL`, and `CLOSE` rows. Records are linked by `intent_id`; source and own transaction signatures stay distinct. `source_transaction_index` and landing indexes are treated as logged claims and compared with the zero-based `getBlock` array position. The canonical position is authoritative. Captured observations are matched by signature and can supply decoded reserve events when RPC logs do not contain a decodable Pump event; estimates that rely on these captures are explicitly marked provisional and do not authenticate an actual receipt.

Rows from older `OPEN`/`CLOSE` logs that lack a source signature and slot remain unresolved. The tool does not infer their source transaction from a timestamp, mint, reserve level, or later close. It reports coverage counts and leaves the original historical fill rows unchanged.

For an actual submitted signature, a successful receipt's decoded trade event provides the observed token/curve-SOL amounts; `meta.fee` provides the network fee. The instruction's `min_output_raw` is recorded separately from actual received tokens. When complete intervening blocks and reserve transitions are available, the tool also requotes the finite intent amount immediately before the actual transaction to compare the boundary quote with the observed receipt.

When no own signature is present, output rows are explicitly `hypothetical_quote_only`. The quote uses integer curve reserves, fee-inclusive buy budgets or the recorded sell token quantity, protocol and creator fees, and the intent's own reserve impact. It does not state that a hypothetical order filled. Central80 and Central85 use a fixed SHA-256 seed derived from `intent_id` (or the stable row key), independent of chain outcome. They run separately at 80% and 85% same-slot probability. The same-slot group draw uses the historical 29/132, 20/132, 83/132 distribution from an older matched-copy audit, capped at two groups. The next-produced-slot branch uses one intervening curve group for the central cases and two for slow. Fast uses the source slot with at most one intervening curve group. These are contract sensitivities, not a measured current landing distribution. Hypothetical rows contain a curve-state boundary, not an asserted global block index or exact within-slot position.

Quotes use the repaired Pump curve adapter over the approved `day_general_20261004` integer quote helpers. This is a per-fill audit, not a profitability replay or a funded portfolio result. It does not recalculate strategy signals or exits, simulate later participant reactions to the intervention, or claim an executable PnL. A stop-triggering dump is applied as a whole transaction before the following quote; fills are never assigned to the stop threshold itself. Missing event coverage, reserve continuity, block order, or intent size remains unresolved.

Graduation is not a curve sell. If the curve has no real token reserves, the tool records `graduated_requires_authenticated_amm_continuation` and preserves the position as unresolved. This bounded tool decodes Pump curve trades only; migrated positions need separate authenticated PumpSwap/Raydium continuation coverage before they can be reconciled as exits. It does not fabricate migration timing, pool liquidity, or a graduation recovery value. The resulting report leaves settled PnL and marked PnL blank because it does not produce an account ledger.

Each run writes:

- `report.json`: coverage, receipt/quote statuses, placement assumptions and unresolved counts.
- `audit_append.jsonl`: one additive reconciliation record per input action.
- `rpc_cache/`: untouched raw JSON-RPC response envelopes, keyed by method and request parameters.

Run the focused unit checks without network access:

```bash
python3 -m unittest scripts.test_reconcile_ghost_fills -v
```
