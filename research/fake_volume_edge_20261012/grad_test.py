#!/usr/bin/env python3
"""Hold-to-graduation diagnostic for late-curve entries (migration-carryover lead).

From-creation coins only. Entry after the signal tx with contract placement
(fast / central p=0.80 / slow), 0.5 SOL, fees, own impact.
Exit: stop at -STOP (checked after each tx, reactive fill with the same placement),
else hold until the curve completes and mark at the completion state (no PumpSwap
continuation: this is the curve-only mark the contract calls graduated-unresolved),
else a CAP timer (no reactive penalty). Coverage end before any exit -> censored.
"""
import gzip, os, pickle, sys
import study as S
import bot_study as B

HERE = os.path.dirname(os.path.abspath(__file__))
RELAY = "ARu4n5mFdZogZAravu7CcizaojWnS6oqka37gdLT5SZn"
CAP = 3_600_000


def place(G, gi, mode):
    fast, same_mix, nxt1, slow = S.entry_states(G, gi)
    if mode == "fast":
        return [(fast, 1.0)]
    if mode == "slow":
        return [(slow, 1.0)]
    return [(ei, w * 0.8) for ei, w in same_mix] + [(nxt1, 0.2)]


def path(G, ei, t0, end, stop, mode):
    er = G[ei][-1]
    held = S.buy_tokens(er[S.VSOL], er[S.VTOK], er[S.FEE])
    for j in range(ei + 1, len(G)):
        r = G[j][-1]
        if r[S.MS] > t0 + CAP:
            p = G[j - 1][-1]
            return S.sell_value(p[S.VSOL], p[S.VTOK], held, p[S.FEE]) / S.BUDGET - 1, "cap"
        if r[S.RSOL] >= S.GRAD_RSOL:
            return S.sell_value(r[S.VSOL], r[S.VTOK], held, r[S.FEE]) / S.BUDGET - 1, "grad"
        v = S.sell_value(r[S.VSOL], r[S.VTOK], held, r[S.FEE]) / S.BUDGET - 1
        if v <= -stop:
            tot = 0.0
            for x, w in place(G, j, mode):
                xr = G[x][-1]
                tot += w * (S.sell_value(xr[S.VSOL], xr[S.VTOK], held, xr[S.FEE]) / S.BUDGET - 1)
            return tot, "stop"
    if t0 + CAP <= end:
        p = G[-1][-1]
        return S.sell_value(p[S.VSOL], p[S.VTOK], held, p[S.FEE]) / S.BUDGET - 1, "cap"
    return None, "censored"


def run():
    W = set(B.tracked())
    T = pickle.load(gzip.open(os.path.join(HERE, "TAPES.pkl.gz")))
    sig = {}
    for mint, d in T["mints"].items():
        if d["create_slot"] is None:
            continue
        end = S.seg_end(T["coverage"], d["create_ms"])
        if end is None:
            continue
        rows = [r for r in d["rows"] if r[S.SLOT] >= d["create_slot"]]
        if len(rows) < 60:
            continue
        G = S.groups(rows)
        f = S.Feat()
        nbuys = 0
        micro_cnt = {}
        recent_bot = []
        fired = set()
        for gi, g in enumerate(G):
            prev = f.ath
            f.update(g)
            for r in g:
                if r[S.BUY]:
                    nbuys += 1
                    if r[S.SOLA] < S.MICRO:
                        micro_cnt[r[S.USER]] = micro_cnt.get(r[S.USER], 0) + 1
            r = g[-1]
            if r[S.MS] > end:
                break
            repeat_micro = sum(1 for v in micro_cnt.values() if v >= 3)
            bots = [x for x in g if x[S.BUY] and x[S.USER] in W and x[S.USER] != RELAY]
            recent_bot = [(s, w) for s, w in recent_bot if s >= r[S.SLOT] - 5]
            consensus = bool(bots) and any(w != bots[0][S.USER] for _, w in recent_bot)
            recent_bot += [(x[S.SLOT], x[S.USER]) for x in bots]
            cands = []
            for lvl in (45, 55):
                if prev < lvl * S.L <= r[S.RSOL] and nbuys >= 60:
                    cands.append((f"cross{lvl}_active", True))
                    cands.append((f"cross{lvl}_bumped30", f.cum_micro >= 30))
                    cands.append((f"cross{lvl}_repeatMicroW>=3", repeat_micro >= 3))
                    cands.append((f"cross{lvl}_noRepeatMicroW", repeat_micro == 0))
            if consensus and 35 * S.L <= r[S.RSOL] <= 65 * S.L:
                cands.append(("botConsensus_35-65", True))
                cands.append(("botConsensus_35-65_bumped30", f.cum_micro >= 30))
            for name, ok in cands:
                if ok and name not in fired:
                    fired.add(name)
                    sig.setdefault(name, []).append((mint, G, gi, end))
    return sig


def main():
    sig = run()
    for stop in (0.15, 0.25, 0.40):
        print(f"\n== stop -{stop:.0%}, else hold to curve completion (completion-state mark), else {CAP//60000} min cap")
        print(f"{'signal':30} {'n':>4} {'cens':>4} | {'fast':>7} {'central80':>9} {'slow':>7} | {'grad':>5} {'stop':>5} {'cap':>5} | {'win c80':>7} {'sum SOL c80':>11}")
        for name in sorted(sig):
            res = {"fast": [], "c80": [], "slow": []}
            kinds = {"grad": 0, "stop": 0, "cap": 0}
            cens = 0
            for mint, G, gi, end in sig[name]:
                t0 = G[gi][-1][S.MS]
                vals = {}
                ok = True
                for mode in ("fast", "c80", "slow"):
                    tot = 0.0
                    for ei, w in place(G, gi, mode):
                        v, k = path(G, ei, t0, end, stop, mode)
                        if v is None:
                            ok = False
                            break
                        tot += w * v
                        if mode == "c80" and w == max(w2 for _, w2 in place(G, gi, mode)):
                            kind = k
                    if not ok:
                        break
                    vals[mode] = tot
                if not ok:
                    cens += 1
                    continue
                kinds[kind] += 1
                for m in vals:
                    res[m].append(vals[m])
            n = len(res["c80"])
            if not n:
                continue
            m = {k: sum(v) / n for k, v in res.items()}
            print(f"{name:30} {n:4d} {cens:4d} | {m['fast']:+7.1%} {m['c80']:+9.1%} {m['slow']:+7.1%} |"
                  f" {kinds['grad']:5d} {kinds['stop']:5d} {kinds['cap']:5d} | {sum(v > 0 for v in res['c80'])/n:7.0%}"
                  f" {sum(res['c80']) * 0.5:+11.2f}")


if __name__ == "__main__":
    main()
