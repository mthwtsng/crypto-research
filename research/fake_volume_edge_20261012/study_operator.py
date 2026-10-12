#!/usr/bin/env python3
"""Bumper-operator track record as a causal feature.

A coin's bumper wallets = wallets with >= 3 micro buys (< 0.02 SOL) in it, counted only
up to the decision time. For each bumper wallet we know, causally, which earlier coins it
bumped and whether those coins had graduated (real SOL >= 84) before the decision time.
Evaluated at the first crossing of each level, same placement/marking as study.py.
"""
import bisect, gzip, os, pickle
from collections import defaultdict
import study as S

HERE = os.path.dirname(os.path.abspath(__file__))
LEVELS = (20, 35, 45, 55)


def main():
    T = pickle.load(gzip.open(os.path.join(HERE, "TAPES.pkl.gz")))
    cov = T["coverage"]
    # pass 1: per mint, per wallet, time of 3rd micro buy; graduation time
    bump_at = defaultdict(list)  # wallet -> [(ms_qualified, mint)]
    grad_ms = {}
    for mint, d in T["mints"].items():
        cnt = defaultdict(int)
        for r in d["rows"]:
            if r[S.BUY] and r[S.SOLA] < S.MICRO:
                cnt[r[S.USER]] += 1
                if cnt[r[S.USER]] == 3:
                    bump_at[r[S.USER]].append((r[S.MS], mint))
            if r[S.RSOL] >= S.GRAD_RSOL and mint not in grad_ms:
                grad_ms[mint] = r[S.MS]
    for v in bump_at.values():
        v.sort()
    multi = sum(1 for v in bump_at.values() if len(v) >= 2)
    print(f"bumper wallets {len(bump_at)}, active in >=2 coins: {multi}")

    out = []
    for mint, d in T["mints"].items():
        if d["create_slot"] is None or not d["rows"]:
            continue
        end = S.seg_end(cov, d["create_ms"])
        if end is None:
            continue
        rows = [r for r in d["rows"] if r[S.SLOT] >= d["create_slot"]]
        G = S.groups(rows)
        f = S.Feat()
        cnt = defaultdict(int)
        bumpers = set()
        nbuys = 0
        done = set()
        for gi, g in enumerate(G):
            prev = f.ath
            f.update(g)
            for r in g:
                if r[S.BUY]:
                    nbuys += 1
                    if r[S.SOLA] < S.MICRO:
                        cnt[r[S.USER]] += 1
                        if cnt[r[S.USER]] >= 3:
                            bumpers.add(r[S.USER])
            r = g[-1]
            now = r[S.MS]
            if now > end:
                break
            for lvl in LEVELS:
                if lvl in done or not (prev < lvl * S.L <= r[S.RSOL]):
                    continue
                done.add(lvl)
                prior, prior_grad = set(), set()
                for w in bumpers:
                    lst = bump_at[w]
                    for ms, m in lst[:bisect.bisect_left(lst, (now, ""))]:
                        if m == mint:
                            continue
                        prior.add(m)
                        if grad_ms.get(m, 1 << 62) < now:
                            prior_grad.add(m)
                e = S.evaluate(mint, G, gi, end, f)
                e.update(level=lvl, nbuys=nbuys, n_bumpers=len(bumpers), prior=len(prior),
                         prior_grad=len(prior_grad), ms=now)
                out.append(e)
    pickle.dump(out, open(os.path.join(HERE, "study_operator.pkl"), "wb"))

    from study_late import stats
    for lvl in LEVELS:
        E = [e for e in out if e["level"] == lvl and e["nbuys"] >= 60]
        print(f"\n== first crossing {lvl} SOL, active coins (>=60 buys), n={len(E)}")
        stats([e for e in E if e["n_bumpers"] == 0], "no bumper wallets")
        stats([e for e in E if e["n_bumpers"] > 0 and e["prior"] == 0], "bumpers, all fresh (no prior coins)")
        stats([e for e in E if e["prior"] > 0 and e["prior_grad"] == 0], "bumpers reused, 0 prior grads")
        stats([e for e in E if e["prior_grad"] >= 1], "bumpers with >=1 prior grad")
        stats([e for e in E if e["prior_grad"] >= 3], "bumpers with >=3 prior grads")
        stats([e for e in E if e["prior"] >= 5 and e["prior_grad"] / e["prior"] >= 0.2], "prior>=5 & grad rate>=20%")


if __name__ == "__main__":
    main()
