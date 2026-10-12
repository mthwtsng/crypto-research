#!/usr/bin/env python3
"""Build an ordered trade tape from txs.jsonl.

Within a slot, trades are ordered by reserve continuity (each trade's pre-state
must equal the previous trade's post-state on v_tok). getTransaction does not
give a block index, so tx_index is null; `ord` is the continuity-derived order.
"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))

def load_tracked():
    m = {}
    for line in open(os.path.join(ROOT, "tracked_wallets.txt")):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        addr, _, label = line.partition("#")
        addr = addr.strip()
        if addr:
            m[addr] = label.strip() or "unlabeled"
    return m

def pre_vtok(t):
    return t["v_tok"] + t["token_amount"] if t["is_buy"] else t["v_tok"] - t["token_amount"]

def main():
    tracked = load_tracked()
    R = [json.loads(l) for l in open(os.path.join(HERE, "txs.jsonl"))]
    rows = []
    for r in R:
        for k, t in enumerate(r["trades"]):
            rows.append({"slot": r["slot"], "tx_index": None, "blockTime": r["blockTime"], "signature": r["sig"],
                         "ev_in_tx": k, "user": t["user"], "signer": r["signer"], "is_buy": t["is_buy"],
                         "sol": t["sol_amount"] / 1e9, "tokens": t["token_amount"] / 1e6,
                         "r_sol": t["r_sol"] / 1e9, "v_sol": t["v_sol"] / 1e9, "v_tokens": t["v_tok"] / 1e6,
                         "_vtok": t["v_tok"], "_pre": pre_vtok(t), "fee": t.get("fee", 0) / 1e9,
                         "creator_fee": t.get("creator_fee", 0) / 1e9,
                         "programs": r["top_programs"], "tracked_label": tracked.get(t["user"]),
                         "user_sol_delta": r["sol_deltas"].get(t["user"], None),
                         "tx_fee": r["fee"] / 1e9})
    by_slot = {}
    for x in rows:
        by_slot.setdefault(x["slot"], []).append(x)
    ordered, last, breaks = [], None, 0
    for s in sorted(by_slot):
        pool = by_slot[s]
        while pool:
            nxt = [x for x in pool if x["_pre"] == last] if last is not None else []
            if not nxt:
                # fall back: the trade whose pre-state is not any other pool trade's post-state
                posts = {x["_vtok"] for x in pool}
                nxt = [x for x in pool if x["_pre"] not in posts] or pool
                if last is not None:
                    breaks += 1
            x = nxt[0]
            pool.remove(x)
            ordered.append(x)
            last = x["_vtok"]
    for i, x in enumerate(ordered):
        x["ord"] = i
    with open(os.path.join(HERE, "tape.jsonl"), "w") as f:
        for x in ordered:
            out = {k: x[k] for k in ("slot", "tx_index", "ord", "blockTime", "signature", "user", "signer", "is_buy", "sol",
                                     "tokens", "r_sol", "v_sol", "v_tokens", "fee", "creator_fee", "programs",
                                     "user_sol_delta", "tx_fee", "tracked_label")}
            out["user_sol_delta"] = None if out["user_sol_delta"] is None else out["user_sol_delta"] / 1e9
            f.write(json.dumps(out) + "\n")
    print("trades", len(ordered), "continuity breaks", breaks)

if __name__ == "__main__":
    main()
