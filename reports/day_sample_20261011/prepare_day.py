#!/usr/bin/env python3
"""Prepare the frozen 2026-10-11 sample for the approved causal replay.

This driver reuses the frozen day_general receipt builder, curve limit binder,
account-level receipt grouping, migration decoder, AMM preparation/custody
helpers and parity adapters. It never changes the frozen selection or source
helpers. RPC responses are served/cached by the sibling collect_day.py module.
"""
from __future__ import annotations

import collections
import copy
import gzip
import hashlib
import importlib.util
import json
import pathlib
import pickle
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

OUT = pathlib.Path(__file__).resolve().parent
ROOT = OUT.parents[1]
HELPERS = ROOT / "research/day_general_20261004/helpers"
DAY = ROOT / "research/day_general_20261004"
OLD = ROOT / "research/wallet_curve_entry_discovery_20261007"
AMM = ROOT / "research/amm_multiday_20261006"
sys.path[:0] = [str(HELPERS), str(DAY), str(OLD), str(AMM), "/tmp/amm_research_deps"]


def module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot_load:{path}")
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


COLLECT = module("day_sample_collect_day", OUT / "collect_day.py")
P = sys.modules["prepare"]
BUILD = sys.modules["build"]
DECODER = sys.modules["decoder"]
BIND = module("day_sample_bind_curve_limits", OLD / "bind_curve_limits.py")
MERGE = module("day_sample_merge_curve_receipts", OLD / "merge_curve_receipts.py")
CURVE_ADAPTER = sys.modules["curve_adapter"]
CURVE_V3 = module("day_sample_curve_v3_extension", OUT / "curve_v3_extension.py")
CURVE_V3.install()
if CURVE_V3.A is not CURVE_ADAPTER:
    raise RuntimeError("v3_extension_installed_on_different_curve_adapter_module")
REPAIR = module("day_sample_repair_helpers", DAY / "repair_helpers.py")
MIGRATE = module("day_sample_migration_collect", AMM / "collect.py")
MIGRATE.MIG = {d: i for d, i in MIGRATE.MIG.items() if i["name"] in ("migrate", "migrate_v2")}
AMM_PREP = module("day_sample_amm_prepare", AMM / "prepare.py")
AMM_CUSTODY = module("day_sample_repair_amm_custody", OLD / "repair_amm_custody.py")
AMM_NORMALIZE = module("day_sample_normalize_amm_virtual", OLD / "normalize_amm_virtual.py")
AMM_PARITY = module("day_sample_verify_amm_counterparty", OLD / "verify_amm_counterparty.py")
MIGRATION_AUDIT = module("day_sample_audit_migration_custody", OLD / "audit_migration_custody.py")

FREEZE = json.loads((OUT / "FREEZE.json").read_text())
CAPTURE_END = int(FREEZE["capture_end"])
SOL_MINTS = {None, "11111111111111111111111111111111", MIGRATE.WSOL}
RAW_CURVES = OUT / "raw_curves"
CURVE_CONT = OUT / "continuation_curves"
POOL_CONT = OUT / "continuation_pools"
REPAIR.HERE = OUT / "custody"
REPAIR.HERE.mkdir(parents=True, exist_ok=True)


def save_gz(path: pathlib.Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".partial")
    with gzip.open(tmp, "wt", compresslevel=1) as f:
        json.dump(value, f, separators=(",", ":"))
    tmp.replace(path)


def save_json(path: pathlib.Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".partial")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)


def read_gz(path: pathlib.Path):
    with gzip.open(path, "rt") as f:
        return json.load(f)


def all_raw_transactions(tape):
    path = RAW_CURVES / (tape["mint"] + ".json.gz")
    raw = read_gz(path)
    return raw, path


def curve_history(tape):
    """Fetch full curve receipt history from creation through frozen capture end."""
    mint = tape["mint"]
    out = CURVE_CONT / (mint + ".json.gz")
    if out.exists():
        cached = read_gz(out)
        if cached.get("through_time") == CAPTURE_END and cached.get("complete"):
            return cached
    raw, _ = all_raw_transactions(tape)
    address = tape["curve"]
    try:
        rows, pages = COLLECT.history(address, tape["creation_time"] - 2, CAPTURE_END + 1)
        by = {x["transaction"]["signatures"][0]: x for x in rows}
        # Keep the collector's authenticated ordered rows. Include the original
        # frozen receipt if a provider range edge omitted it, then force an
        # explicit creation signature check in the audit.
        for x in raw["transactions"]:
            sig = x["transaction"]["signatures"][0]
            if sig not in by and x.get("blockTime", 0) <= CAPTURE_END:
                by[sig] = x
        rows = sorted(by.values(), key=lambda x: (x["slot"], x["transactionIndex"]))
        creation_sig = tape.get("creation_metadata", {}).get("signature")
        if not creation_sig:
            creation_sig = next((x["transaction"]["signatures"][0] for x in raw["transactions"]
                                 if any(c["mint"] == mint for c in P.decoder.creations(x))), None)
        has_creation = creation_sig in by if creation_sig else any(
            c["mint"] == mint for x in rows for c in P.decoder.creations(x))
        if not has_creation:
            raise ValueError("creation_signature_missing_from_continuation")
        result = dict(mint=mint, curve=address, complete=True, through_time=CAPTURE_END,
                      pages=pages, transactions=rows, creation_signature=creation_sig,
                      creation_present=True, source="collect_day.history; finalized full transaction receipts")
    except Exception as e:
        # Preserve the selected mint and its original finite receipts. A failed
        # continuation is explicit coverage debt, not an outcome exclusion.
        rows = raw["transactions"]
        result = dict(mint=mint, curve=address, complete=False,
                      through_time=raw.get("requested_end_time"), requested_through=CAPTURE_END,
                      error=repr(e), transactions=rows,
                      source="frozen raw curve history only; continuation unresolved")
    save_gz(out, result)
    return result


def curve_migrations(tape, history):
    rows = []
    parse_errors = []
    for tx in history["transactions"]:
        try:
            rows.extend(m for m in MIGRATE.migrations(tx) if m["mint"] == tape["mint"])
        except Exception as e:
            parse_errors.append(dict(signature=tx["transaction"]["signatures"][0], error=repr(e)))
    # Preserve exact transaction ordering and repeated retries. The caller
    # authenticates a tradable pool from its CreatePool receipt, not a retry.
    rows.sort(key=lambda m: (m["slot"], m["index"], m["signature"]))
    return rows, parse_errors


def pool_history(tape, migration):
    mint = tape["mint"]
    out = POOL_CONT / (mint + ".json.gz")
    if out.exists():
        z = read_gz(out)
        if z.get("complete") and z.get("through_time") == CAPTURE_END:
            return z
    if migration["quote_mint"] != MIGRATE.WSOL:
        raise ValueError("unsupported_migration_quote:" + str(migration["quote_mint"]))
    rows, pages = COLLECT.history(migration["pool"], migration["time"] - 2, CAPTURE_END + 1)
    sigs = {x["transaction"]["signatures"][0] for x in rows}
    if migration["signature"] not in sigs:
        # Repeated migrate instruction signatures need not be the pool genesis.
        # Pool preparation below verifies the actual CreatePoolEvent instead.
        pass
    coverage = dict(pool=migration["pool"], mint=mint, complete=True,
                    transactions=len(rows), pages=pages, through_time=CAPTURE_END,
                    migration=migration, source="collect_day.history; finalized full transaction receipts")
    result = dict(coverage=coverage, transactions=rows, complete=True, through_time=CAPTURE_END)
    save_gz(out, result)
    return result


def reward_adaptable(tape):
    c = tape.get("creation_metadata", {})
    return (c.get("is_holder_reward") is True and not c.get("is_mayhem_mode", False)
            and c.get("quote_mint") in SOL_MINTS)


def bind_events(tape, transactions):
    by = {x["transaction"]["signatures"][0]: x for x in transactions}
    audits = []
    errors = []
    for g in tape["groups"]:
        if not g["events"]:
            continue
        tx = by.get(g["signature"])
        if tx is None:
            errors.append(dict(signature=g["signature"], error="source_transaction_not_loaded"))
            continue
        try:
            params = BIND.bind(tx, tape["mint"])
            if len(params) != len(g["events"]):
                errors.append(dict(signature=g["signature"], events=len(g["events"]), instructions=len(params),
                                   error="curve_instruction_event_count"))
                continue
            for e, b in zip(g["events"], params):
                if e["buy"] != b["name"].startswith("buy"):
                    raise ValueError("side_bind")
                decoder_name = e.get("ix_name")
                e.update(b["fields"])
                # Decoder event logs use a generic alias in several Pump
                # versions. Keep it, while dispatching on the exact original
                # transaction instruction authenticated by account/data binding.
                e["decoder_ix_name"] = decoder_name
                e["ix_name"] = b["name"]
                e["instruction_name"] = b["name"]
                e["bound_instruction_name"] = b["name"]
            audits.append(dict(signature=g["signature"], trades=len(params)))
        except Exception as e:
            errors.append(dict(signature=g["signature"], error=repr(e)))
    return audits, errors


def make_curve_tape(mint, source):
    d = dict(mint=mint, transactions=source["transactions"], requested_end_time=CAPTURE_END)
    return P.make(d)


def patch_repair_runtime():
    REPAIR.rpc = COLLECT.rpc
    REPAIR.save = COLLECT.save
    # The helper's historical rule stops at the first authenticated completion;
    # post-completion migrations and transfers are audited separately.
    old_gap = REPAIR.gap

    def curve_prefix_gap(t):
        gs = t["groups"]
        end = next((i + 1 for i, g in enumerate(gs)
                    if g.get("state", {}).get("rtokens_raw") == 0), len(gs))
        return old_gap(dict(t, groups=gs[:end]))

    REPAIR.gap = curve_prefix_gap
    return old_gap


def repair_curve_gap(tape, source, raw_path, eligible):
    mint = tape["mint"]
    input_path = OUT / "custody_inputs" / (mint + ".json.gz")
    save_gz(input_path, dict(mint=mint, transactions=source["transactions"], requested_end_time=CAPTURE_END))
    base_t, base_a = make_curve_tape(mint, source)
    if not base_t:
        return source, dict(mint=mint, status="source_tape_missing", detail=base_a)
    initial = REPAIR.gap(base_t)
    if not initial:
        return source, dict(mint=mint, status="no_wallet_level_gap", groups=len(base_t["groups"]))
    if not eligible:
        return source, dict(mint=mint, status="unsupported_rule_excluded_from_repair",
                            initial_signature=initial[0]["signature"], owner=initial[1])
    # The repair helper's historical normal flag excludes holder-reward coins.
    # Enable its unchanged account-history repair only for the explicit SOL
    # holder-reward adaptation; final inclusion still requires full source parity.
    original_make = REPAIR.make
    if reward_adaptable(tape):
        def reward_make(d):
            z, a = original_make(d)
            if z is not None:
                z["normal"] = True
            return z, a
        REPAIR.make = reward_make
    try:
        audit = REPAIR.one(input_path)
    finally:
        REPAIR.make = original_make
    repaired = REPAIR.HERE / "custody_extended" / input_path.name
    if repaired.exists():
        data = read_gz(repaired)
        result = dict(mint=mint, status=audit.get("status"), passes=audit.get("passes", []),
                      source_transactions=len(data["transactions"]), initial_signature=initial[0]["signature"],
                      remaining_gap=None)
        final_t, _ = make_curve_tape(mint, data)
        bad = REPAIR.gap(final_t) if final_t else None
        if bad:
            result["remaining_gap"] = dict(signature=bad[0]["signature"], owner=bad[1])
        else:
            result["status"] = "wallet_level_custody_repaired"
        return data, result
    return source, dict(mint=mint, status=audit.get("status", "repair_no_output"),
                        passes=audit.get("passes", []), issue=audit.get("issue"),
                        initial_signature=initial[0]["signature"], owner=initial[1])


def account_and_curve_parity(mint, tape, source):
    """Bind instructions, retain wallet signal groups, group by token account, verify prefix."""
    tx_by = {x["transaction"]["signatures"][0]: x for x in source["transactions"]}
    bind_audit, bind_errors = bind_events(tape, source["transactions"])
    # Wallet-level groups are needed for canonical strategy holders/buyer counts.
    signal_groups = copy.deepcopy(tape["groups"])
    account_groups = []
    account_errors = []
    owners = {}
    for g in tape["groups"]:
        tx = tx_by.get(g["signature"])
        if tx is None:
            account_errors.append(dict(signature=g["signature"], error="source_transaction_not_loaded"))
            continue
        try:
            ag = MERGE.account_group(g, tx, mint)
            owners.update(ag.get("account_owners", {}))
            account_groups.append(ag)
        except Exception as e:
            account_errors.append(dict(signature=g["signature"], error=repr(e)))
    complete_index = next((i for i, g in enumerate(account_groups)
                           if g.get("state", {}).get("rtokens_raw") == 0), None)
    prefix_end = complete_index + 1 if complete_index is not None else len(account_groups)
    first = next((e for g in account_groups[:prefix_end] for e in g.get("events", [])), None)
    parity = dict(pass_all=False, groups_checked=0, total_groups=prefix_end, errors=[])
    if first is None:
        parity["status"] = "no_trades"
        parity["errors"].append(dict(reason="no_curve_trade_events"))
    else:
        d = 1 if first["buy"] else -1
        st = dict(vsol_raw=first["vsol_raw"] - d * first["sol_raw"],
                  vtokens_raw=first["vtokens_raw"] + d * first["tokens_raw"],
                  rsol_raw=first["rsol_raw"] - d * first["sol_raw"],
                  rtokens_raw=first["real_token_reserves"] + d * first["tokens_raw"],
                  fee_bps=first["fee_bps"], creator_fee_bps=first["creator_fee_bps"])
        h, cf = {}, {}
        for g in account_groups[:prefix_end]:
            z, hh, cc, adj, err = CURVE_ADAPTER.apply(st, g, h, cf)
            expected = g["state"]
            keys = ("vsol_raw", "vtokens_raw", "rsol_raw", "rtokens_raw")
            if err or adj.get("counterfactual_revert") or any(z[k] != expected[k] for k in keys) or hh != cc:
                reason = err or adj.get("counterfactual_revert") or "state_or_account_custody_mismatch"
                parity["status"] = "coverage_required" if reason in (
                    "v3_completion_pool_leg_coverage_required",
                    "v3_counterfactual_completion_pool_leg_coverage_required") else "fail"
                parity["errors"].append(dict(signature=g["signature"],
                                             reason=reason,
                                             actual={k: z.get(k) for k in keys}, expected={k: expected.get(k) for k in keys}))
                break
            st, h, cf = z, hh, cc
            parity["groups_checked"] += 1
        parity["status"] = "pass" if parity["groups_checked"] == prefix_end and not parity["errors"] else parity.get("status", "fail")
        parity["pass_all"] = parity["status"] == "pass"
    # Independently check the recorded source holdings by account without the
    # counterfactual engine. A negative balance invalidates the prefix.
    inventory_error = None
    inventory = collections.Counter()
    for i, g in enumerate(account_groups[:prefix_end]):
        try:
            for op in BUILD.ops(g):
                if op["kind"] == "trade":
                    e, account = op["event"], op["owner"]
                    inventory[account] += e["tokens_raw"] if e["buy"] else -e["tokens_raw"]
                elif op["kind"] == "transfer":
                    inventory[op["from_owner"]] -= op["raw"]
                    inventory[op["to_owner"]] += op["raw"]
                    if inventory[op["from_owner"]] < 0:
                        raise ValueError("negative_token_account_inventory")
                else:
                    raise ValueError("unknown_custody_op")
            if min(inventory.values(), default=0) < 0:
                raise ValueError("negative_token_account_inventory")
        except Exception as e:
            inventory_error = dict(index=i, signature=g["signature"], error=repr(e))
            break
    t = dict(tape)
    t.update(groups=account_groups, signal_groups=signal_groups, inventory_key="token_account",
             account_owners=owners, source_status="prepared", end_time=CAPTURE_END)
    audit = dict(mint=mint, raw_groups=len(tape["groups"]), account_groups=len(account_groups),
                 completed=complete_index is not None, completion_index=complete_index,
                 curve_prefix_groups=prefix_end, instruction_bindings=len(bind_audit),
                 instruction_errors=bind_errors, account_group_errors=account_errors,
                 source_parity=parity, inventory_error=inventory_error,
                 account_mapping_verified=not account_errors and not inventory_error,
                 signal_group_semantics="wallet owner and original wallet transfers retained",
                 replay_group_semantics="receipt-bound token-account custody")
    return t, audit


def apply_amm_custody(tape, history):
    by = {x["transaction"]["signatures"][0]: x for x in history["transactions"]}
    errors = []
    for g in tape["groups"]:
        if not g.get("custody_error") and g["signature"] != tape["groups"][0]["signature"]:
            continue
        tx = by.get(g["signature"])
        if tx is None:
            errors.append(dict(signature=g["signature"], error="pool_receipt_missing"))
            continue
        try:
            g["raw_events"] = AMM_CUSTODY.B.A.events(tx)
            ops, err = AMM_CUSTODY.custody(tx, tape["migration"], g["trades"], g)
            g["custody_ops"], g["custody_error"] = ops, err
            g.pop("raw_events", None)
            if err:
                errors.append(dict(signature=g["signature"], error=err))
        except Exception as e:
            g.pop("raw_events", None)
            g["custody_error"] = repr(e)
            errors.append(dict(signature=g["signature"], error=repr(e)))
    return errors


def prepare_pool(mint, pool_source):
    path = POOL_CONT / (mint + ".json.gz")
    tape, audit = AMM_PREP.prepare(path)
    # The full pool receipt history ends at the frozen capture boundary.
    tape["coverage"]["through_time"] = CAPTURE_END
    tape["coverage"]["decision_end"] = CAPTURE_END
    tape["end_time"] = CAPTURE_END
    custody_errors = apply_amm_custody(tape, pool_source)
    return tape, dict(prepare=audit, custody_errors=custody_errors)


def migration_audit_for(tape):
    p = OUT / "normalized_amm_tapes" / (tape["mint"] + ".json.gz")
    return MIGRATION_AUDIT.audit(p)


def main():
    if not pathlib.Path("/tmp/amm_research_deps/ijson").exists():
        raise RuntimeError("approved_ijson_dependency_missing:/tmp/amm_research_deps")
    original = pickle.load(gzip.open(OUT / "TAPES.pkl.gz", "rb"))
    if len(original) != int(json.loads((OUT / "COLLECTION_COMPLETE.json").read_text())["selected"]):
        raise RuntimeError("frozen_sample_count_mismatch")
    creation = json.loads((OUT / "CREATION_SAMPLE.json").read_text())
    chosen = {x["mint"]: x for x in creation["chosen"]}
    source_by_mint = {}
    manifest = {t["mint"]: dict(mint=t["mint"], selected=True, original_groups=len(t["groups"]),
                                original_normal=t["normal"], holder_reward=reward_adaptable(t),
                                continuation="pending", custody="pending", migration="pending",
                                source_parity="pending", replay_status="pending") for t in original}

    print("CURVE_CONTINUATIONS", len(original), "through", CAPTURE_END, flush=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futs = {pool.submit(curve_history, t): t for t in original}
        for f in as_completed(futs):
            t = futs[f]
            try:
                z = f.result()
                source_by_mint[t["mint"]] = z
                manifest[t["mint"]]["continuation"] = "complete" if z["complete"] else "incomplete"
                if z.get("error"):
                    manifest[t["mint"]]["continuation_error"] = z["error"]
            except Exception as e:
                manifest[t["mint"]]["continuation"] = "error"
                manifest[t["mint"]]["continuation_error"] = repr(e)
            if len(source_by_mint) % 20 == 0:
                save_json(OUT / "PREPARATION_PROGRESS.json", dict(stage="curve_continuations", done=len(source_by_mint),
                                                                  total=len(original), audit=manifest))
                print("CURVE_HISTORY", len(source_by_mint), "/", len(original), flush=True)
    save_json(OUT / "CURVE_CONTINUATION_AUDIT.json", manifest)

    # Locate authentic migrations and pool receipt histories. No survival,
    # volume, or future-return criterion changes membership.
    migration_rows = {}
    pool_sources = {}
    pool_jobs = {}
    for t in original:
        m = manifest[t["mint"]]
        src = source_by_mint.get(t["mint"])
        if not src:
            m["migration"] = "unresolved_curve_history"
            continue
        rows, parse_errors = curve_migrations(t, src)
        m["migration_calls"] = rows
        m["migration_parse_errors"] = parse_errors
        if parse_errors:
            m["migration_parse_status"] = "partial"
        if not rows:
            m["migration"] = "no_authenticated_migrate_instruction_through_capture_end" if src["complete"] else "not_observed_in_incomplete_history"
            continue
        migration_rows[t["mint"]] = rows
        pools = {r["pool"] for r in rows}
        if len(pools) != 1:
            m["migration"] = "ambiguous_multiple_pools"
            m["migration_pools"] = sorted(pools)
            continue
        pool = rows[0]["pool"]
        candidates = [r for r in rows if r["pool"] == pool and r["quote_mint"] == MIGRATE.WSOL]
        if not candidates:
            m["migration"] = "unsupported_quote_or_route"
            m["migration_pools"] = sorted(pools)
            continue
        # The pool's authenticated CreatePoolEvent, verified below, sets the
        # actual opening position. Earlier migrate calls are kept as provenance.
        pool_jobs[t["mint"]] = (t, candidates[0], src)
        m["migration"] = "pool_receipts_pending"

    print("POOL_HISTORIES", len(pool_jobs), "through", CAPTURE_END, flush=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futs = {pool.submit(pool_history, *job[:2]): mint for mint, job in pool_jobs.items()}
        for f in as_completed(futs):
            mint = futs[f]
            try:
                z = f.result()
                pool_sources[mint] = z
                manifest[mint]["migration"] = "pool_history_complete"
                manifest[mint]["pool"] = z["coverage"]["pool"]
                print("POOL_HISTORY", mint[:9], z["coverage"]["transactions"], flush=True)
            except Exception as e:
                manifest[mint]["migration"] = "pool_history_error"
                manifest[mint]["migration_error"] = repr(e)
                print("POOL_HISTORY_ERROR", mint[:9], repr(e), flush=True)
    save_json(OUT / "MIGRATION_COLLECTION_AUDIT.json", manifest)

    # Prepare all curve histories in the original sample, then repair gaps and
    # bind the source Pump instructions to their original limits.
    old_gap = patch_repair_runtime()
    curve_tapes = {}
    for i, t in enumerate(original, 1):
        mint = t["mint"]
        src = source_by_mint.get(mint)
        if src is None:
            raw, _ = all_raw_transactions(t)
            src = dict(mint=mint, transactions=raw["transactions"], complete=False,
                       through_time=raw.get("requested_end_time"), error="continuation_missing")
            source_by_mint[mint] = src
        pure = reward_adaptable(t)
        manifest[mint]["holder_reward_adaptation_candidate"] = pure
        eligible_repair = bool(t["normal"] or pure)
        # Prepare once to identify actual, causal custody gaps. Repair helpers
        # add only authenticated account-address receipts through capture_end.
        pt, pa = make_curve_tape(mint, src)
        custody_audit = dict(mint=mint, status="initial_prepare_failed" if not pt else "pending",
                             initial_custody_gap=pa.get("custody_gap") if isinstance(pa, dict) else None)
        if pt and REPAIR.gap(pt):
            raw_path = RAW_CURVES / (mint + ".json.gz")
            src, custody_audit = repair_curve_gap(t, src, raw_path, eligible_repair)
            source_by_mint[mint] = src
            pt, pa = make_curve_tape(mint, src)
        if pt is None:
            manifest[mint]["custody"] = "curve_prepare_failed"
            manifest[mint]["curve_prepare_error"] = pa
            continue
        manifest[mint]["custody"] = custody_audit.get("status", "no_wallet_level_gap")
        manifest[mint]["custody_audit"] = custody_audit
        manifest[mint]["curve_groups_after_repair"] = len(pt["groups"])
        # For holder-reward SOL coins, run the same existing integer replay
        # only as an explicit parity-gated adaptation.
        if pure:
            pt["normal"] = True
            pt["normalization"] = "holder_reward_SOL_enabled_only_if_bound_source_parity_passes"
        merged, ca = account_and_curve_parity(mint, pt, src)
        ca["holder_reward_adaptation_candidate"] = pure
        source_ok = ca["source_parity"]["pass_all"] and not ca["instruction_errors"] and not ca["account_group_errors"] and not ca["inventory_error"]
        if pure and not source_ok:
            merged["normal"] = False
            merged["normalization"] = "holder_reward_SOL_parity_failed; unsupported"
        elif pure:
            merged["normal"] = True
            merged["normalization"] = "holder_reward_SOL_source_parity_pass"
        ca["replay_eligible"] = bool((t["normal"] or (pure and source_ok)) and source_ok)
        if ca["source_parity"].get("status") == "no_trades":
            manifest[mint]["source_parity"] = "no_trades"
        elif ca["source_parity"].get("status") == "coverage_required":
            manifest[mint]["source_parity"] = "coverage_required"
        else:
            manifest[mint]["source_parity"] = "pass" if source_ok else "fail"
        manifest[mint]["source_parity_audit"] = ca
        if ca["source_parity"].get("status") == "no_trades":
            manifest[mint]["replay_status"] = "no_curve_trades_observed"
        elif ca["source_parity"].get("status") == "coverage_required":
            manifest[mint]["replay_status"] = "v3_terminal_pool_leg_coverage_required"
        else:
            manifest[mint]["replay_status"] = "curve_source_ready" if ca["replay_eligible"] else "unsupported_or_unresolved_source_parity"
        curve_tapes[mint] = merged
        save_gz(OUT / "merged_account_tapes" / (mint + ".json.gz"), merged)
        if i % 10 == 0 or i == len(original):
            save_json(OUT / "PREPARATION_PROGRESS.json", dict(stage="curve_account_binding_parity", done=i,
                                                              total=len(original), audit=manifest))
            print("CURVE_PREPARED", i, "/", len(original), "account_groups", len(merged["groups"]),
                  "parity", source_ok, flush=True)

    # Build authentic migrated AMM histories, repair custody, normalize virtual
    # reserves, and prove whole-history source parity before combining venues.
    amm_tapes = {}
    amm_prepare_audits = {}
    for mint, (t, migration, _) in pool_jobs.items():
        if mint not in pool_sources or mint not in curve_tapes:
            continue
        try:
            at, aa = prepare_pool(mint, pool_sources[mint])
            # Retain the actual migrate call list; the pool opening is later
            # anchored to the transaction with the authenticated CreatePoolEvent.
            at["migration_calls"] = migration_rows.get(mint, [])
            save_gz(OUT / "repaired_amm_tapes" / (mint + ".json.gz"), at)
            amm_tapes[mint] = at
            amm_prepare_audits[mint] = aa
            manifest[mint]["amm_groups"] = len(at["groups"])
            manifest[mint]["amm_prepare_errors"] = aa.get("prepare", {}).get("errors", [])
            manifest[mint]["amm_custody_errors"] = aa["custody_errors"]
            manifest[mint]["migration"] = "amm_prepared"
        except Exception as e:
            manifest[mint]["migration"] = "amm_prepare_error"
            manifest[mint]["amm_prepare_error"] = repr(e)
            print("AMM_PREPARE_ERROR", mint[:9], repr(e), flush=True)
    save_json(OUT / "AMM_PREPARE_AUDIT.json", amm_prepare_audits)

    # Use the approved existing normalizer and parity checker with this day's
    # bounded inputs by redirecting their in-memory output root only.
    AMM_NORMALIZE.P = OUT
    AMM_PARITY.P = OUT
    MIGRATION_AUDIT.P = OUT
    AMM_NORMALIZE.main()
    AMM_PARITY.main()
    amm_norm = {}
    amm_parity_rows = {}
    amm_parity_path = OUT / "AMM_COUNTERPARTY_PARITY.json"
    if amm_parity_path.exists():
        amm_parity_rows = {x["mint"]: x for x in json.loads(amm_parity_path.read_text()).get("audits", [])}
    for mint, at in amm_tapes.items():
        nf = OUT / "normalized_amm_tapes" / (mint + ".json.gz")
        if nf.exists():
            amm_norm[mint] = read_gz(nf)
        else:
            manifest[mint]["migration"] = "amm_normalization_missing"
    save_json(OUT / "AMM_PARITY_AUDIT.json", amm_parity_rows)

    # Authenticate migration custody against the curve completion and actual
    # pool opening. This keeps post-migration liquidity/custody continuous.
    migration_audits = {}
    for mint in amm_norm:
        try:
            audit = migration_audit_for(amm_norm[mint])
            migration_audits[mint] = audit
            manifest[mint]["migration_custody_audit"] = audit
            if audit.get("pass_all"):
                # The auditor may correct a later idempotent migrate retry to
                # the actual pool-creation position in the normalized tape.
                amm_norm[mint] = read_gz(OUT / "normalized_amm_tapes" / (mint + ".json.gz"))
                manifest[mint]["migration"] = "migration_custody_pass"
            else:
                manifest[mint]["migration"] = "migration_custody_unresolved"
        except Exception as e:
            migration_audits[mint] = dict(mint=mint, pass_all=False, error=repr(e))
            manifest[mint]["migration"] = "migration_audit_error"
            manifest[mint]["migration_audit_error"] = repr(e)
    save_json(OUT / "MIGRATION_CUSTODY_AUDIT.json", migration_audits)

    # Compose one chronology per selected mint. The curve side ends at actual
    # real-token exhaustion; migration custody is handled by the authenticated
    # pool opening group, avoiding double-counting migration transfers.
    prepared = []
    for original_t in original:
        mint = original_t["mint"]
        t = curve_tapes.get(mint)
        if t is None:
            t = dict(original_t, groups=[], signal_groups=[], inventory_key="token_account",
                     end_time=CAPTURE_END, preparation_status="curve_source_unresolved",
                     source_error=manifest[mint].get("curve_prepare_error"))
        source_groups = t.get("groups", [])
        completion = next((i for i, g in enumerate(source_groups)
                          if g.get("state", {}).get("rtokens_raw") == 0), None)
        if completion is not None:
            source_groups = source_groups[:completion + 1]
        combined = [dict(g, venue="curve", trades=g.get("events", []),
                         time=g.get("block_time", g.get("time")), block_time=g.get("block_time", g.get("time")),
                         source_status="succeeded") for g in source_groups]
        migration_ok = False
        if mint in amm_norm:
            observed_pool_t = amm_norm[mint]
            observed_amm_groups = [dict(g, venue="amm", block_time=g["time"], time=g["time"])
                                   for g in observed_pool_t["groups"]]
            t["observed_amm_groups"] = observed_amm_groups
            t["observed_migration"] = observed_pool_t["migration"]
            t["observed_pool"] = observed_pool_t["pool"]
            t["observed_amm_coverage"] = observed_pool_t["coverage"]
            a = migration_audits.get(mint, {})
            p = amm_parity_rows.get(mint, {})
            custody_clear = all(not g.get("custody_error") for g in observed_pool_t.get("groups", []))
            migration_ok = bool(a.get("pass_all") and p.get("pass_all") and custody_clear and completion is not None
                                and not amm_prepare_audits.get(mint, {}).get("prepare", {}).get("errors")
                                and manifest[mint].get("source_parity") == "pass")
            if migration_ok:
                pool_t = observed_pool_t
                genesis_pos = (pool_t["groups"][0]["slot"], pool_t["groups"][0]["index"])
                # Curve groups with an ordered position after pool genesis are
                # not curve-market activity; preserve only the completed curve.
                combined.extend(observed_amm_groups)
                t["migration"] = pool_t["migration"]
                t["migration_quote_difference"] = a["measured_migration_quote_difference_lamports"]
                t["pool"] = pool_t["pool"]
                t["amm_coverage"] = pool_t["coverage"]
                t["migration_custody_pass"] = True
                manifest[mint]["replay_status"] = "curve_and_migration_AMM_source_ready"
            else:
                manifest[mint]["migration"] = "observed_but_not_replayable"
                manifest[mint]["migration_source_ready"] = False
        combined.sort(key=lambda g: (g["slot"], g["index"]))
        t["groups"] = combined
        t["signal_groups"] = t.get("signal_groups", [])
        t["inventory_key"] = "token_account"
        t["end_time"] = CAPTURE_END
        t["selected"] = True
        t["preparation_status"] = manifest[mint]["replay_status"]
        t["preparation_audit_key"] = mint
        t["coverage"] = dict(requested_end_time=CAPTURE_END,
                             curve_history_complete=bool(source_by_mint.get(mint, {}).get("complete")),
                             curve_last_observed=max((g.get("block_time", 0) for g in source_groups), default=None),
                             migration_observed=bool(migration_rows.get(mint)),
                             migration_source_ready=migration_ok,
                             capture_end=CAPTURE_END)
        # Basic chronology/data-schema guarantees consumed by the canonical engine.
        if any(g.get("time") is None or g.get("block_time") is None for g in combined):
            manifest[mint]["schema_error"] = "missing_group_time"
            t["preparation_status"] = "unsupported_missing_group_time"
        if any((a["slot"], a["index"]) > (b["slot"], b["index"])
               for a, b in zip(combined, combined[1:])):
            manifest[mint]["schema_error"] = "group_order_not_monotonic"
            t["preparation_status"] = "unsupported_group_order"
        prepared.append(t)
    with gzip.open(OUT / "PREPARED_TAPES.pkl.gz", "wb", compresslevel=1) as f:
        pickle.dump(prepared, f, protocol=pickle.HIGHEST_PROTOCOL)

    counts = collections.Counter(t["preparation_status"] for t in prepared)
    parity_counts = collections.Counter(m.get("source_parity", "pending") for m in manifest.values())
    summary = dict(selected=len(original), prepared=len(prepared), selected_mints=[t["mint"] for t in original],
                   status_counts=dict(counts), source_ready=sum(bool(manifest[t["mint"]].get("source_parity") == "pass") for t in original),
                   source_parity_status_counts=dict(parity_counts),
                   no_curve_trade_activity=parity_counts.get("no_trades", 0),
                   source_coverage_required=parity_counts.get("coverage_required", 0),
                   source_parity_failures=parity_counts.get("fail", 0),
                   migrations_observed=sum(bool(migration_rows.get(t["mint"])) for t in original),
                   migrations_source_ready=sum(t.get("migration_custody_pass", False) for t in prepared),
                   curve_continuations_complete=sum(bool(source_by_mint.get(t["mint"], {}).get("complete")) for t in original),
                   holder_reward_adaptations=dict(total=sum(reward_adaptable(t) for t in original),
                                                 parity_pass=sum(bool(manifest[t["mint"]].get("holder_reward_adaptation_candidate") and
                                                                     manifest[t["mint"]].get("source_parity") == "pass") for t in original)),
                   capture_end=CAPTURE_END,
                   scope="all 240 creation-hash selections retained; unsupported/unresolved entries remain explicit; no outcome-based exclusions")
    save_json(OUT / "PREPARATION_AUDIT.json", dict(summary=summary, mints=manifest,
                                                  migration_audits=migration_audits,
                                                  amm_prepare_audits=amm_prepare_audits,
                                                  amm_parity=amm_parity_rows))
    print("PREPARED", json.dumps(summary, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
