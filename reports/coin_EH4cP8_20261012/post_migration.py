#!/usr/bin/env python3
"""Sample post-migration PumpSwap pool activity and tracked holders' carryover exits."""
import json, os, datetime
from concurrent.futures import ThreadPoolExecutor
from fetch import rpc, MINT

HERE = os.path.dirname(os.path.abspath(__file__))
POOL = "3S7fiSZpCRKfevwqmXaK5twHAQxGsPvV3gWcskkx6h48"
MIG_SLOT = 455947249
WSOL = "So11111111111111111111111111111111111111112"
HOLDERS = {"ARu4n5mFdZogZAravu7CcizaojWnS6oqka37gdLT5SZn": "Real Coin Bot (41 real coins)",
           "sssssw": "Fleet Bot (45 real coins, 1074 txns)"}

def utc(bt):
    return datetime.datetime.fromtimestamp(bt, datetime.UTC).strftime("%Y-%m-%d %H:%M:%S")

def gtx(sig):
    return rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])

def pool_state(tx):
    sol = tok = None
    for b in tx["meta"].get("postTokenBalances") or []:
        if b.get("owner") == POOL:
            if b["mint"] == WSOL:
                sol = float(b["uiTokenAmount"]["uiAmount"] or 0)
            elif b["mint"] == MINT:
                tok = float(b["uiTokenAmount"]["uiAmount"] or 0)
    return sol, tok

def main():
    for l in open(os.path.join(HERE, "tape.jsonl")):
        u = json.loads(l)["user"]
        if u.startswith("sssssw"):
            HOLDERS[u] = HOLDERS.pop("sssssw", HOLDERS.get(u)); break
    sigs, before = [], None
    while True:
        opts = {"limit": 1000}
        if before:
            opts["before"] = before
        page = rpc("getSignaturesForAddress", [POOL, opts])
        sigs += [s for s in page if s["slot"] >= MIG_SLOT]
        if len(page) < 1000 or page[-1]["slot"] < MIG_SLOT:
            break
        before = page[-1]["signature"]
    sigs.sort(key=lambda s: s["slot"])
    ok = [s for s in sigs if s["err"] is None]
    step = max(1, len(ok) // 120)
    sample = ok[::step][:150]
    with ThreadPoolExecutor(6) as ex:
        txs = list(ex.map(lambda s: (s, gtx(s["signature"])), sample))
    path = []
    for s, tx in txs:
        if not tx:
            continue
        sol, tok = pool_state(tx)
        if sol and tok:
            path.append({"slot": s["slot"], "utc": utc(s["blockTime"]), "pool_sol": round(sol, 3), "pool_tok_M": round(tok / 1e6, 3),
                         "price_sol_per_Mtok": round(sol / tok * 1e6, 6)})
    res = {"pool": POOL, "post_migration_sigs": len(sigs), "ok": len(ok), "failed": len(sigs) - len(ok),
           "first": utc(sigs[0]["blockTime"]) if sigs else None, "last": utc(sigs[-1]["blockTime"]) if sigs else None,
           "price_path_sampled": path}
    # tracked holders
    hold = {}
    for w, lab in HOLDERS.items():
        ws = rpc("getSignaturesForAddress", [w, {"limit": 1000}])
        after = sorted([s for s in ws if s["slot"] >= MIG_SLOT and s["err"] is None], key=lambda s: s["slot"])
        found = []
        for s in after[:120]:
            tx = gtx(s["signature"])
            if not tx:
                continue
            tb = {}
            for side in ("preTokenBalances", "postTokenBalances"):
                for b in tx["meta"].get(side) or []:
                    if b.get("mint") == MINT and b.get("owner") == w:
                        tb[side] = int(b["uiTokenAmount"]["amount"])
            dtok = tb.get("postTokenBalances", 0) - tb.get("preTokenBalances", 0)
            if dtok:
                msg = tx["transaction"]["message"]; keys = list(msg["accountKeys"])
                la = tx["meta"].get("loadedAddresses") or {}; keys += la.get("writable", []) + la.get("readonly", [])
                i = keys.index(w)
                dsol = (tx["meta"]["postBalances"][i] - tx["meta"]["preBalances"][i]) / 1e9
                sol, tok = pool_state(tx)
                found.append({"utc": utc(s["blockTime"]), "slot": s["slot"], "sig": s["signature"], "d_tokens_M": dtok / 1e12,
                              "wallet_sol_delta": dsol, "pool_sol_after": sol})
            if len(found) >= 6:
                break
        hold[w] = {"label": lab, "post_mig_sigs_seen": len(after), "mint_txs": found}
    res["tracked_holders_post_migration"] = hold
    json.dump(res, open(os.path.join(HERE, "post_migration.json"), "w"), indent=1)
    print(json.dumps({k: v for k, v in res.items() if k != "price_path_sampled"}, indent=1)[:4000])
    for p in path[::8]:
        print(p)

if __name__ == "__main__":
    main()
