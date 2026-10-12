#!/usr/bin/env python3
"""Copy-trade test: signal = a tracked bot's opening buy tx; exit signal = its closing sell tx.
Our buy and our sell are both placed after the signal tx per contract placement
(fast / central p=0.80 / slow). 0.5 SOL, integer quotes, fees and own impact.
Any coin with a tracked trip is included (signal-defined selection, not outcome-defined);
tapes are live-feed, not all from creation, so this is a diagnostic.
"""
import gzip, os, pickle, statistics as st
from collections import defaultdict
import study as S

HERE = os.path.dirname(os.path.abspath(__file__))
RELAY = "ARu4n5mF"
BOTS = ["ssssswdk", "sssssDdM", "BWBd3hj2", "BUkpShoE", "omegoMAe", "2gnL2LdN", "2FdJD3EV", "ESEGGqQ5",
        "77wS9zZH", "AHeEPb1i", "haqqiUUX"]


def place(G, gi, mode):
    fast, same_mix, nxt1, slow = S.entry_states(G, gi)
    if mode == "fast":
        return [(fast, 1.0)]
    if mode == "slow":
        return [(slow, 1.0)]
    return [(ei, w * 0.8) for ei, w in same_mix] + [(nxt1, 0.2)]


def main():
    trips = pickle.load(open(os.path.join(HERE, "bot_trips.pkl"), "rb"))
    T = pickle.load(gzip.open(os.path.join(HERE, "TAPES.pkl.gz")))
    by_mint = defaultdict(list)
    for t in trips:
        if t["wallet"][:8] in BOTS:
            by_mint[t["mint"]].append(t)
    res = defaultdict(lambda: defaultdict(list))
    for mint, ts in by_mint.items():
        rows = T["mints"][mint]["rows"]
        G = S.groups(rows)
        gidx = {}
        n = 0
        for gi, g in enumerate(G):
            for _ in g:
                gidx[n] = gi
                n += 1
        for t in ts:
            gi0, gi1 = gidx[t["i0"]], gidx[t["i1"]]
            if gi1 <= gi0:
                continue
            for mode in ("fast", "c80", "slow"):
                val = 0.0
                for ei, w in place(G, gi0, mode):
                    er = G[ei][-1]
                    held = S.buy_tokens(er[S.VSOL], er[S.VTOK], er[S.FEE])
                    if ei >= gi1:  # we land after their exit already fired: sell right behind it
                        pass
                    for xi, w2 in place(G, max(gi1, ei), mode):
                        xr = G[xi][-1]
                        val += w * w2 * (S.sell_value(xr[S.VSOL], xr[S.VTOK], held, xr[S.FEE]) / S.BUDGET - 1)
                res[t["wallet"][:8]][mode].append(val)
            res[t["wallet"][:8]]["name"] = t["name"][:24]
            res[t["wallet"][:8]]["hold"].append((t["t1"] - t["t0"]) / 1000)
    print(f"{'bot':24} {'n':>5} {'hold med':>8} | mean return per copy: {'fast':>7} {'central80':>9} {'slow':>7} | win c80")
    for b in BOTS:
        r = res.get(b)
        if not r:
            continue
        c = r["c80"]
        print(f"{r['name']:24} {len(c):5d} {st.median(r['hold']):7.1f}s | {st.mean(r['fast']):+21.2%} {st.mean(c):+9.2%}"
              f" {st.mean(r['slow']):+7.2%} | {sum(x > 0 for x in c) / len(c):3.0%}")
        short = [(f, x) for f, x, h in zip(r["fast"], c, r["hold"]) if h <= 5]
        if short:
            print(f"{'   holds <=5s':24} {len(short):5d} {'':8} | {st.mean(a for a, _ in short):+21.2%} {st.mean(b_ for _, b_ in short):+9.2%}")


if __name__ == "__main__":
    main()
