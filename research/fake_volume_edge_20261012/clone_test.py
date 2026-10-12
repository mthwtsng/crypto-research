#!/usr/bin/env python3
"""Directional test of a rule cloned from the tracked scalpers' entry fingerprint.

Entry (evaluated after each complete transaction, from-creation coins only, one open
attempt per coin at a time, 60 s cooldown after exit):
  real SOL 12-35, price 10-30% below the 60 s high, >= MIN_BUYERS distinct buyers in
  the last 10 s, >= MIN_MICRO micro buys in the last 30 s.
Exit diagnostic (first passage, evaluated after every transaction): take +TP, stop -SL,
or time cap; marks are executable round-trip values incl. fees and own impact. The exit
itself lands at the triggering transaction's state (fast-bracket exit), so this is an
optimistic exit model: an opportunity diagnostic, not executable PnL.
"""
import gzip, os, pickle, sys
import study as S
import bot_study as B

HERE = os.path.dirname(os.path.abspath(__file__))
TP, SL, CAP = 0.10, 0.07, 30_000


def first_passage(G, ei, t_entry):
    er = G[ei][-1]
    held = S.buy_tokens(er[S.VSOL], er[S.VTOK], er[S.FEE])
    last = er
    for j in range(ei + 1, len(G)):
        r = G[j][-1]
        if r[S.MS] > t_entry + CAP:
            break
        last = r
        v = S.sell_value(r[S.VSOL], r[S.VTOK], held, r[S.FEE]) / S.BUDGET - 1
        if v >= TP or v <= -SL or r[S.RSOL] >= S.GRAD_RSOL:
            return v, j
    return S.sell_value(last[S.VSOL], last[S.VTOK], held, last[S.FEE]) / S.BUDGET - 1, None


def run(min_buyers, min_micro):
    T = pickle.load(gzip.open(os.path.join(HERE, "TAPES.pkl.gz")))
    res = []
    for mint, d in T["mints"].items():
        if d["create_slot"] is None:
            continue
        end = S.seg_end(T["coverage"], d["create_ms"])
        if end is None:
            continue
        rows = [r for r in d["rows"] if r[S.SLOT] >= d["create_slot"]]
        if len(rows) < 50:
            continue
        G = S.groups(rows)
        starts = []
        n = 0
        for g in G:
            starts.append(n)
            n += len(g)
        busy_until = 0
        for gi, g in enumerate(G):
            r = g[-1]
            if r[S.MS] > end - CAP:
                break
            if r[S.MS] < busy_until or not (12 * S.L <= r[S.RSOL] <= 35 * S.L):
                continue
            i = starts[gi] + len(g)
            if i >= len(rows):
                break
            c = B.ctx_before(rows, i, r[S.MS] + 1, -1)
            if not (-0.30 <= c["dd60"] <= -0.10 and c["buyers10"] >= min_buyers and c["micro30"] >= min_micro):
                continue
            fast, same_mix, nxt1, slow = S.entry_states(G, gi)
            out = {"fast": first_passage(G, fast, r[S.MS])[0], "slow": first_passage(G, slow, r[S.MS])[0]}
            same = sum(first_passage(G, ei, r[S.MS])[0] * w for ei, w in same_mix)
            nx = first_passage(G, nxt1, r[S.MS])[0]
            out["c80"] = 0.80 * same + 0.20 * nx
            out["c85"] = 0.85 * same + 0.15 * nx
            res.append(out)
            busy_until = r[S.MS] + CAP + 60_000
    return res


if __name__ == "__main__":
    print(f"exit diagnostic: +{TP:.0%} / -{SL:.0%} / {CAP//1000}s cap, 0.5 SOL, fees+impact; values are mean round-trip return")
    for mb, mm in ((6, 0), (6, 3), (8, 6), (10, 6), (12, 12)):
        R = run(mb, mm)
        if not R:
            continue
        def m(k):
            return sum(x[k] for x in R) / len(R)
        win = sum(x["c80"] > 0 for x in R) / len(R)
        print(f"buyers10>={mb:2d} micro30>={mm:2d}: n={len(R):5d} central80 {m('c80'):+6.2%}  fast {m('fast'):+6.2%}"
              f"  c85 {m('c85'):+6.2%}  slow {m('slow'):+6.2%}  win(c80) {win:3.0%}", flush=True)
