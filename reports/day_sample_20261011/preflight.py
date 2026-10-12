#!/usr/bin/env python3
"""Read-only preflight for the Oct 11 creation-sampled replay.

This deliberately does not import fresh_collect.py, fresh_pipeline.py,
recovery_sequence.py, or variants.py: those modules initialize paths and some
create directories at import time. The engine smoke check runs in an isolated
Python subprocess with bytecode writes disabled and makes no RPC calls.
"""
from __future__ import annotations

import ast
import json
import pathlib
import subprocess
import sys


ROOT = pathlib.Path(__file__).resolve().parents[2]
RESEARCH = ROOT / "research"
DAY = RESEARCH / "day_general_20261004"
CORE = RESEARCH / "core_plan_audit_20261007"
GAP = RESEARCH / "core_gap_refinement_20261007"
FRESH = GAP / "fresh_oct05_oct06"
OLD = RESEARCH / "wallet_curve_entry_discovery_20261007"


def exists(path: pathlib.Path) -> bool:
    return path.exists()


def import_smoke() -> dict:
    child = r'''import importlib.util, json, pathlib, sys
sys.dont_write_bytecode = True
root = pathlib.Path(sys.argv[1])
day = root / "research/day_general_20261004"
helpers = day / "helpers"
sys.path[:0] = [str(helpers), str(day)]

def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot make spec for {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

import replay, build, clock
base = load(day / "base_engine.py", "_oct11_base_engine_probe")
core = load(root / "research/core_plan_audit_20261007/engine.py", "_oct11_core_engine_probe")
ledger = load(root / "research/core_plan_audit_20261007/ledger.py", "_oct11_ledger_probe")
signals = load(root / "research/core_plan_audit_20261007/signals.py", "_oct11_signals_probe")
print(json.dumps({
    "base_modules": {"replay": hasattr(replay, "buy") and hasattr(replay, "sell"),
                     "build": hasattr(build, "inventory"),
                     "clock": hasattr(clock, "timer_slot"),
                     "base_engine": hasattr(base, "simulate") or hasattr(base, "replay")},
    "approved_replay_extension": {"engine_simulate": hasattr(core, "simulate"),
                                  "migration_opening": hasattr(core, "opening_state"),
                                  "ledger_funded": hasattr(ledger, "funded"),
                                  "canonical_detector": hasattr(signals, "detect")},
}, sort_keys=True))
'''
    result = subprocess.run(
        [sys.executable, "-B", "-c", child, str(ROOT)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    parsed = None
    if result.stdout.strip():
        try:
            parsed = json.loads(result.stdout.strip().splitlines()[-1])
        except json.JSONDecodeError:
            pass
    return {
        "returncode": result.returncode,
        "ok": result.returncode == 0 and parsed is not None,
        "probe": parsed,
        "stdout_tail": result.stdout[-1200:],
        "stderr_tail": result.stderr[-2400:],
    }


def function_lines(path: pathlib.Path, names: set[str]) -> dict[str, int]:
    tree = ast.parse(path.read_text())
    return {
        node.name: node.lineno
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names
    }


def main() -> None:
    collector = GAP / "fresh_collect.py"
    pipeline = GAP / "fresh_pipeline.py"
    old_continuation = OLD / "collect_continuations.py"
    old_custody = OLD / "repair_curve_custody.py"
    detector = CORE / "signals.py"
    recovery = GAP / "recovery_sequence.py"
    unified = GAP / "unified_requested.py"
    root_manifest = DAY / "CREATION_SAMPLE.json"
    day_freeze = DAY / "FREEZE.json"

    expected_old_helper = RESEARCH / "automated_wallet_expansion_20261006" / "collect_wallets.py"
    files = {
        "fresh_collect": collector,
        "fresh_pipeline": pipeline,
        "canonical_signals": detector,
        "recovery_sequence": recovery,
        "unified_requested": unified,
        "curve_continuation_collector": old_continuation,
        "curve_custody_repair": old_custody,
        "expected_collect_wallets_dependency": expected_old_helper,
        "temporary_amm_dependency_dir": pathlib.Path("/tmp/amm_research_deps"),
    }

    collection_spec = {}
    if collector.exists():
        source = collector.read_text()
        collection_spec = {
            "uses_provider_extension_getTransactionsForAddress": "getTransactionsForAddress" in source,
            "full_transaction_details": "transactionDetails='full'" in source or 'transactionDetails=\"full\"' in source,
            "requires_provider_transaction_index": "missing_provider_index" in source,
            "paginates": "paginationToken" in source,
            "frozen_hourly_sample": "range(48)" in source and "per_hour" in source,
        }

    pipeline_spec = {}
    if pipeline.exists():
        source = pipeline.read_text()
        pipeline_spec = {
            "custody_repair_before_signal_detection": source.find("repair_selection()") < source.find("continuations(signals)"),
            "collects_continuation_for_each_signal_mint": "for s in signals" in source and "submit(C.run,j)" in source,
            "token_account_custody_required_before_AMM_replay": "inventory_key']='token_account'" in source,
            "AMM_receipt_repairs_present": all(x in source for x in ("repair_amm_custody", "verify_amm_counterparty", "audit_migration_custody")),
            "old_import_side_effect_warning": "H.H.HERE.mkdir" in source,
        }

    recovery_spec = {}
    if recovery.exists():
        source = recovery.read_text()
        recovery_spec = {
            "has_two_buy_groups_mode": "two_buy_groups" in source,
            "distinct_new_buyer_gate": "buyers-first" in source,
            "two_slots_after_raw_dip": "s['slot']+2" in source,
            "rechecks_reserves_8_to_18": "8<=r<=18" in source,
        }
    unified_spec = {}
    if unified.exists():
        source = unified.read_text()
        unified_spec = {
            "replaces_raw_S3_signals": "[s for s in baseline if s['rule']!='s3_deadman']" in source,
            "uses_two_buy_groups": "selection[window]['two_buy_groups']" in source,
            "candidate_S3_receipt": "source='explicit user-requested unified comparison" in source,
        }

    prior_sample = None
    if root_manifest.exists():
        prior_sample = json.loads(root_manifest.read_text())
    prior_freeze = json.loads(day_freeze.read_text()) if day_freeze.exists() else None
    prior_result = {}
    if prior_sample is not None:
        prior_result["older_24h_sampled_mints"] = len(prior_sample.get("chosen", []))
        prior_result["older_24h_total_creations"] = prior_sample.get("total_creations")
        prior_result["older_24h_ordinary_native_SOL_creations"] = prior_sample.get("ordinary")
        prior_result["older_24h_census_complete"] = prior_sample.get("census_complete")
    if prior_freeze is not None:
        prior_result["older_capture_seconds"] = prior_freeze.get("capture_seconds")
        prior_result["older_max_source_tapes"] = prior_freeze.get("max_source_tapes")

    sample_files = [
        FRESH / "COMPLETE.json",
        FRESH / "SIGNAL_AUDIT.json",
        FRESH / "CONTINUATION_COMPLETE.json",
        FRESH / "PIPELINE_COMPLETE.json",
    ]
    old_sample_result = {}
    if all(p.exists() for p in sample_files):
        complete, signals, continuation, pipe = [json.loads(p.read_text()) for p in sample_files]
        old_sample_result = {
            "Oct5_6_selected_and_prepared": [complete.get("selected"), complete.get("tapes")],
            "Oct5_6_curve_tapes_with_initial_custody_gaps": len(complete.get("custody_gaps", [])),
            "Oct5_6_signal_mints": signals.get("mints"),
            "Oct5_6_signal_counts": signals.get("signals"),
            "Oct5_6_continuation_mints_and_errors": [continuation.get("total"), len(continuation.get("errors", []))],
            "Oct5_6_migration_status_counts": {
                status: sum(a.get("status") == status for a in continuation.get("audits", []))
                for status in sorted({a.get("status") for a in continuation.get("audits", [])})
            },
            "Oct5_6_bound_curve_tapes_and_pools": [pipe.get("bound_tapes"), pipe.get("pools")],
        }

    result = {
        "scope": "read-only; no network calls; no replay; no output besides stdout",
        "engine_import_smoke": import_smoke(),
        "expected_files": {name: {"path": str(path), "exists": exists(path)} for name, path in files.items()},
        "collection_contract": collection_spec,
        "current_pipeline_contract": pipeline_spec,
        "S3_signal_route": {
            "canonical_detector_functions": function_lines(detector, {"detect"}) if detector.exists() else {},
            "recovery_sequence_functions": function_lines(recovery, {"choose", "source", "prepare", "entries"}) if recovery.exists() else {},
            "recovery_sequence_logic": recovery_spec,
            "unified_driver_logic": unified_spec,
        },
        "older_sample_scale": prior_result,
        "older_reuse_scale": old_sample_result,
        "immediate_gaps": [
            "fresh_collect.py imports collect_wallets from the missing automated_wallet_expansion_20261006 directory",
            "collect_continuations.py and repair_curve_custody.py import the same missing RPC/cache helper, so fresh_pipeline.py is not importable as-is",
            "fresh_pipeline.py creates a directory at module import and must not be imported merely for preflight",
            "the old collector uses enhanced getTransactionsForAddress with full transactions and transactionIndex; Solami MCP's standard JSON-RPC tool does not document that provider extension",
            "the generic canonical runner reads saved earlier/later CONTROL_REPLAY inputs; new data must be passed by a new driver into engine.simulate and ledger.funded",
            "the old S3 raw dip detector must be followed by the frozen two_buy_groups confirmation path for the registry's confirmed S3 entry",
        ],
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
