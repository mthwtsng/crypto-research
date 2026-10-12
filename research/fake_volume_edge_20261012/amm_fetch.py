#!/usr/bin/env python3
"""Authenticated PumpSwap continuation tapes for every graduated from-creation coin.

Selection is outcome-independent at the entry level: every coin in the live universe
whose curve completed gets its first hour of pool history, regardless of any signal.
Uses the frozen-validation migration decoder, history fetcher and AMM tape preparer,
redirected to write into this folder. Pool states are the source-reported reserves per
transaction; the strict whole-source custody replay (`pool()`) is NOT applied because it
rejects current pools (virtual_prestate_gap, likely buyback/boost changes), so these
marks are unauthenticated.
Usage: amm_fetch.py [mint ...] | --from mints.json   (default: all graduated coins)
"""
import gzip, importlib.util, json, os, pickle, sys, traceback
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
FROZEN = os.path.join(ROOT, "research/frozen_21day_validation_20261008")
sys.path.insert(0, FROZEN)
import pathlib
# rpc_pool reads RPC endpoints from <repo>/AGENTS.md, which lives in the bot repo.
BOT_AGENTS = pathlib.Path(os.environ.get("CRYPTO_BOT_REPO", os.path.expanduser("~/code/Crypto"))) / "AGENTS.md"
_read_text = pathlib.Path.read_text
pathlib.Path.read_text = lambda self, *a, **k: _read_text(
    BOT_AGENTS if self.name == "AGENTS.md" and not self.exists() else self, *a, **k)
import rpc_pool as R
pathlib.Path.read_text = _read_text
OUT = pathlib.Path(HERE) / "amm"
R.OUT = OUT
OUT.mkdir(exist_ok=True)
import run_after_collection as RAC
RAC.P = OUT
import collect_validation as C
sys.path.insert(0, HERE)
import study as S

spec = importlib.util.spec_from_file_location("pda", os.path.join(ROOT, "reports/coin_EH4cP8_20261012/fetch.py"))
PDA = importlib.util.module_from_spec(spec)
spec.loader.exec_module(PDA)
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"


def graduated():
    T = pickle.load(gzip.open(os.path.join(HERE, "TAPES.pkl.gz")))
    out = {}
    for mint, d in T["mints"].items():
        if d["create_slot"] is None or S.seg_end(T["coverage"], d["create_ms"]) is None:
            continue
        for r in d["rows"]:
            if r[9] >= 84 * 10**9:
                out[mint] = r[3] // 1000
                break
    return out


def one(mint, t_complete):
    dest = OUT / "summary" / (mint + ".json")
    if dest.exists():
        return json.load(open(dest))
    curve, _ = PDA.find_pda([b"bonding-curve", PDA.b58d(mint)], PUMP)
    try:
        rows = C.history(curve, t_complete - 120, t_complete + 900, "succeeded")
        migs = [m for tx in rows for m in RAC.MC.migrations(tx) if m["mint"] == mint]
        if not migs:
            res = dict(mint=mint, status="no_migration_found", curve_rows=len(rows))
        else:
            m = migs[0]
            raw = OUT / "continuation_pools" / (m["pool"] + ".json.gz")
            if not raw.exists():
                txs = C.history(m["pool"], m["time"], m["time"] + 3600, "succeeded")
                R.save(raw, dict(coverage=dict(pool=m["pool"], complete=True, through_time=m["time"] + 3600, migration=m),
                                 transactions=txs))
            tape, audit = RAC.AP.prepare(raw)
            groups = [dict(slot=g["slot"], index=g["index"], time=g["time"], base=g["state"]["base"],
                           quote=g["state"]["quote"], virtual=g["state"].get("virtual", 0),
                           rates=(g["trades"][0]["rates"] if g["trades"] else None), n_trades=len(g["trades"]))
                      for g in tape["groups"]]
            R.save(OUT / "tapes" / (mint + ".json.gz"), dict(migration=m, groups=groups,
                                                             audit_errors=len(audit.get("errors", []))))
            res = dict(mint=mint, status="ok", pool=m["pool"], migration=m, groups=len(groups),
                       audit_errors=len(audit.get("errors", [])))
    except Exception as e:
        res = dict(mint=mint, status="error", error=str(e)[:400], trace=traceback.format_exc()[-800:])
    R.save(dest, res)
    return res


def main():
    G = graduated()
    if sys.argv[1:2] == ["--from"]:
        mints = [m for m in json.load(open(sys.argv[2])) if m in G]
    else:
        mints = sys.argv[1:] or sorted(G)
    print(f"graduated from-creation coins: {len(G)}; fetching {len(mints)}", flush=True)
    done = 0
    with ThreadPoolExecutor(4) as ex:
        for res in ex.map(lambda m: one(m, G[m]), mints):
            done += 1
            print(done, res["mint"][:8], res["status"], res.get("groups", ""), res.get("error", "")[:160], flush=True)


if __name__ == "__main__":
    main()
