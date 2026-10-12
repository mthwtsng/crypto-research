#!/usr/bin/env python3
"""Migration-carryover diagnostic: late-curve entries carried into PumpSwap.

Curve leg: from-creation live tapes, contract entry placement (fast / central p=0.80 /
slow), 0.5 SOL, fees, own impact. Pre-graduation stop with reactive placement.
AMM leg: source-reported pool reserves per transaction from amm/tapes/<mint>.json.gz
(unauthenticated: the strict custody replay rejects current pools). Sell quote
(quote + virtual) * n / (base + n) less the group's fee rates. Our sell lands after the
trigger group per the same placement mixture applied to pool groups.
Graduated coins without an AMM tape are reported as graduated-unresolved with the
curve completion mark.
"""
import gzip, json, os, pickle, sys
from collections import defaultdict
import study as S
import bot_study as B

HERE = os.path.dirname(os.path.abspath(__file__))
AMM = os.path.join(HERE, "amm", "tapes")
CAP = 3_600_000
K_MIX = S.K_MIX


def amm_tape(mint, cache={}):
    if mint not in cache:
        p = os.path.join(AMM, mint + ".json.gz")
        cache[mint] = json.load(gzip.open(p, "rt"))["groups"] if os.path.exists(p) else None
    return cache[mint]


def amm_value(g, n):
    fee = sum(g["rates"] or (2, 93, 30))
    q = g["quote"] + g["virtual"]
    out = q * n // (g["base"] + n)
    return out * (10_000 - fee) // 10_000


def amm_place(A, gi, mode):
    slot = A[gi]["slot"]
    same = [j for j in range(gi + 1, len(A)) if A[j]["slot"] == slot]
    after = same[-1] if same else gi
    nxt = [j for j in range(after + 1, len(A)) if A[j]["slot"] == A[after + 1]["slot"]] if after + 1 < len(A) else []

    def same_k(k):
        return same[min(k, len(same)) - 1] if k and same else gi

    def next_after(n):
        return nxt[min(n, len(nxt)) - 1] if nxt else after

    if mode == "fast":
        return [(same_k(1), 1.0)]
    if mode == "slow":
        return [(next_after(2), 1.0)]
    return [(same_k(k), w * 0.8) for k, w in K_MIX] + [(next_after(1), 0.2)]


def amm_exit(A, n, policy, mode):
    """Return SOL out (lamports) for n tokens carried into the pool, per exit policy."""
    def sell_at(gi, amount):
        return sum(w * amm_value(A[j], amount) for j, w in amm_place(A, gi, mode))
    t_open = A[0]["time"]
    if policy == "open":
        return sell_at(0, n)
    if policy == "s5":
        half = n // 2
        out = sell_at(0, half)
        rest = n - half
        peak = 0
        for gi, g in enumerate(A):
            v = amm_value(g, rest)
            peak = max(peak, v)
            if v <= peak * 0.92:
                return out + sell_at(gi, rest)
            if g["time"] > t_open + 30:
                return out + sell_at(max(0, gi - 1), rest)
        return out + sell_at(len(A) - 1, rest)
    if policy.startswith("hold"):
        secs = int(policy[4:])
        for gi, g in enumerate(A):
            if g["time"] >= t_open + secs:
                return amm_value(A[max(0, gi - 1)], n)  # timer: no reactive penalty
        return amm_value(A[-1], n)
    if policy == "trail20":
        peak = 0
        for gi, g in enumerate(A):
            v = amm_value(g, n)
            peak = max(peak, v)
            if v <= peak * 0.80:
                return sell_at(gi, n)
            if g["time"] > t_open + 900:
                return amm_value(A[max(0, gi - 1)], n)
        return amm_value(A[-1], n)
    raise ValueError(policy)


def place(G, gi, mode):
    fast, same_mix, nxt1, slow = S.entry_states(G, gi)
    if mode == "fast":
        return [(fast, 1.0)]
    if mode == "slow":
        return [(slow, 1.0)]
    return [(ei, w * 0.8) for ei, w in same_mix] + [(nxt1, 0.2)]


def curve_leg(G, ei, t0, end, stop_fn, mode):
    """-> (kind, value_or_tokens). kind in stop/cap/grad/censored."""
    er = G[ei][-1]
    held = S.buy_tokens(er[S.VSOL], er[S.VTOK], er[S.FEE])
    for j in range(ei + 1, len(G)):
        r = G[j][-1]
        if r[S.MS] > t0 + CAP:
            p = G[j - 1][-1]
            return "cap", S.sell_value(p[S.VSOL], p[S.VTOK], held, p[S.FEE]), held
        if r[S.RSOL] >= S.GRAD_RSOL:
            return "grad", S.sell_value(r[S.VSOL], r[S.VTOK], held, r[S.FEE]), held
        if stop_fn(r, held):
            v = sum(w * S.sell_value(G[x][-1][S.VSOL], G[x][-1][S.VTOK], held, G[x][-1][S.FEE]) for x, w in place(G, j, mode))
            return "stop", v, held
    if t0 + CAP <= end:
        p = G[-1][-1]
        return "cap", S.sell_value(p[S.VSOL], p[S.VTOK], held, p[S.FEE]), held
    return "censored", None, held


POLICIES = ("open", "s5", "hold60", "hold300", "trail20")


def evaluate(mint, G, gi, end, stop_fn):
    t0 = G[gi][-1][S.MS]
    A = amm_tape(mint)
    out = {}
    for mode in ("fast", "c80", "slow"):
        acc = {p: 0.0 for p in POLICIES}
        kinds = defaultdict(float)
        for ei, w in place(G, gi, mode):
            kind, v, held = curve_leg(G, ei, t0, end, stop_fn, mode)
            if kind == "censored":
                return None
            kinds[kind] += w
            for p in POLICIES:
                if kind == "grad" and A:
                    val = amm_exit(A, held, p, mode)
                    kinds["amm"] += w / len(POLICIES)
                else:
                    val = v
                acc[p] += w * (val / S.BUDGET - 1)
        out[mode] = acc
        out[mode + "_kinds"] = dict(kinds)
    out["has_amm"] = A is not None
    return out


def signals():
    W = set(B.tracked())
    T = pickle.load(gzip.open(os.path.join(HERE, "TAPES.pkl.gz")))
    sig = defaultdict(list)
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
        bal = defaultdict(int)
        creator = d["creator"]
        slot_flow = []  # (slot, net outside lamports)
        fired = set()
        for gi, g in enumerate(G):
            prev = f.ath
            prev_rsol = G[gi - 1][-1][S.RSOL] if gi else 0
            f.update(g)
            net = 0
            for r in g:
                bal[r[S.USER]] += r[S.TOK] if r[S.BUY] else -r[S.TOK]
                if r[S.BUY]:
                    nbuys += 1
                if r[S.USER] != creator:
                    net += r[S.SOLA] if r[S.BUY] else -r[S.SOLA]
            r = g[-1]
            if slot_flow and slot_flow[-1][0] == r[S.SLOT]:
                slot_flow[-1] = (r[S.SLOT], slot_flow[-1][1] + net)
            else:
                slot_flow.append((r[S.SLOT], net))
            if r[S.MS] > end:
                break
            stop25 = lambda x, held, er=None: False
            if "s5" not in fired and prev_rsol < 72 * S.L <= r[S.RSOL] < S.GRAD_RSOL:
                holders = sum(1 for v in bal.values() if v > 0)
                flow = sum(v for s, v in slot_flow if s >= r[S.SLOT] - 4)
                if holders >= 100 and flow > 0:
                    fired.add("s5")
                    sig["S5_registry_cross72"].append((mint, G, gi, end, "s5stop"))
            for lvl in (45, 55):
                if prev < lvl * S.L <= r[S.RSOL] and nbuys >= 60:
                    for name, ok in ((f"cross{lvl}_active", True), (f"cross{lvl}_bumped30", f.cum_micro >= 30),
                                     (f"cross{lvl}_notBumped<10", f.cum_micro < 10)):
                        if ok and name not in fired:
                            fired.add(name)
                            sig[name].append((mint, G, gi, end, "pct25"))
    return sig


def stop_for(kind, G, gi):
    if kind == "s5stop":
        return lambda r, held: r[S.RSOL] <= 60 * S.L
    er = G[gi][-1]
    def pct(r, held):
        return S.sell_value(r[S.VSOL], r[S.VTOK], held, r[S.FEE]) / S.BUDGET - 1 <= -0.25
    return pct


def main():
    sig = signals()
    mints = sorted({m for v in sig.values() for m, *_ in v})
    json.dump(mints, open(os.path.join(HERE, "carry_mints.json"), "w"))
    print("AMM exit policies: open=all at pool opening; s5=half at opening + 8% trail, 30 s timeout;"
          " hold60/hold300 timers; trail20=20% trail, 15 min cap. Curve stop: S5 60 SOL, others -25%.")
    print("Mean round-trip return per attempt, 0.5 SOL. AMM marks unauthenticated (source pool reserves).\n")
    for name in sorted(sig):
        rows = []
        missing = 0
        for mint, G, gi, end, sk in sig[name]:
            e = evaluate(mint, G, gi, end, stop_for(sk, G, gi))
            if e is None:
                continue
            rows.append(e)
        if not rows:
            continue
        grads = sum(1 for e in rows if e["c80_kinds"].get("grad", 0) > 0.5)
        noamm = sum(1 for e in rows if e["c80_kinds"].get("grad", 0) > 0.5 and not e["has_amm"])
        print(f"== {name}: n={len(rows)}, graduated (central) {grads}, graduated without AMM tape {noamm}")
        print(f"   {'policy':8} {'fast':>7} {'central80':>9} {'slow':>7} {'win c80':>7} {'sum SOL c80':>11}")
        for p in POLICIES:
            m = {mode: sum(e[mode][p] for e in rows) / len(rows) for mode in ("fast", "c80", "slow")}
            win = sum(e["c80"][p] > 0 for e in rows) / len(rows)
            print(f"   {p:8} {m['fast']:+7.1%} {m['c80']:+9.1%} {m['slow']:+7.1%} {win:7.0%} {sum(e['c80'][p] for e in rows) * 0.5:+11.2f}")


if __name__ == "__main__":
    main()
