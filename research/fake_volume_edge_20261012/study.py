#!/usr/bin/env python3
"""Entry-first causal study: does micro-buy (bumper) activity predict forward returns?

Universe: every mint in TAPES.pkl.gz whose creation was captured inside a coverage
segment (outcome-independent). Features are updated after each complete transaction
using only rows already seen. One entry per (signal, mint): the first trigger.

Entry placement (BACKTEST_ACCURACY_CONTRACT section 3), applied after the whole signal tx:
  fast    same slot, at most 1 further curve group
  central p * same-slot mixture (K=0 29/132, K=1 20/132, K>=2 -> 2 groups; 83/132)
          + (1-p) * next produced slot after its first group;  p in {0.80, 0.85}
  slow    next produced slot after its first 2 groups
Buy: 0.5 SOL gross, integer constant-product quote, recorded fee bps.
Mark: round-trip sell of our tokens at the observed state shifted by our own holding
(paper offset model), fees included. Graduated curves are marked at completion state.
Outputs are opportunity diagnostics (fixed horizons, max favourable excursion),
not executable PnL.
"""
import gzip, os, pickle, sys
from collections import defaultdict, deque

HERE = os.path.dirname(os.path.abspath(__file__))
L = 1_000_000_000
MICRO = 20_000_000
OUTSIDE_MIN = 50_000_000
BUDGET = 500_000_000
HORIZONS = [300_000, 900_000, 1_800_000, 3_600_000]
GRAD_RSOL = 84 * L
FP_LEVELS = (0.2, 0.3, 0.5)
K_MIX = [(0, 29 / 132), (1, 20 / 132), (2, 83 / 132)]

# row: (slot, idx, k, ms, sig, user, is_buy, sol, tok, rsol, vsol, vtok, fee_bps, jup, payer_is_user)
SLOT, IDX, K, MS, SIG, USER, BUY, SOLA, TOK, RSOL, VSOL, VTOK, FEE = range(13)


def buy_tokens(vsol, vtok, fee_bps):
    net = BUDGET * 10_000 // (10_000 + fee_bps)
    return vtok * net // (vsol + net)


def sell_value(vsol, vtok, held, fee_bps):
    # observed reserves shifted along the invariant as if our tokens were still in the curve
    vtok_adj = vtok - held
    if vtok_adj <= 0:
        return 0
    vsol_adj = vsol * vtok // vtok_adj
    gross = vsol_adj * held // (vtok_adj + held)
    return gross * 10_000 // (10_000 + fee_bps)


def groups(rows):
    out, cur = [], []
    for r in rows:
        if cur and r[SIG] != cur[-1][SIG]:
            out.append(cur)
            cur = []
        cur.append(r)
    if cur:
        out.append(cur)
    return out


def entry_states(G, gi):
    """Entry state (last row applied before our buy) per placement branch."""
    slot = G[gi][0][SLOT]
    same = [j for j in range(gi + 1, len(G)) if G[j][0][SLOT] == slot]
    after_same = same[-1] if same else gi
    nxt = after_same + 1
    nxt_ok = nxt < len(G) and G[nxt][0][SLOT] == slot + 1
    nxt_groups = [j for j in range(nxt, len(G)) if G[j][0][SLOT] == slot + 1] if nxt_ok else []

    def same_k(k):
        return same[min(k, len(same)) - 1] if k and same else gi

    def next_after(n):
        return nxt_groups[min(n, len(nxt_groups)) - 1] if nxt_groups else after_same

    fast = same_k(1)
    slow = next_after(2)
    same_mix = [(same_k(k), w) for k, w in K_MIX]
    nxt1 = next_after(1)
    return fast, same_mix, nxt1, slow


class Feat:
    __slots__ = ("cum_micro", "micro_w", "recent", "ath", "outside_w")

    def __init__(self):
        self.cum_micro = 0
        self.micro_w = set()
        self.recent = deque()
        self.ath = 0
        self.outside_w = set()

    def update(self, g):
        for r in g:
            if r[BUY]:
                m = r[SOLA] < MICRO
                if m:
                    self.cum_micro += 1
                    self.micro_w.add(r[USER])
                elif r[SOLA] >= OUTSIDE_MIN:
                    self.outside_w.add(r[USER])
                self.recent.append((r[MS], r[SOLA], r[USER], m))
        now = g[-1][MS]
        while self.recent and self.recent[0][0] < now - 300_000:
            self.recent.popleft()
        self.ath = max(self.ath, g[-1][RSOL])

    def window(self, now, ms):
        micro = 0
        outs = set()
        for t, s, u, m in self.recent:
            if t < now - ms:
                continue
            if m:
                micro += 1
            elif s >= OUTSIDE_MIN and u not in self.micro_w:
                outs.add(u)
        return micro, len(outs)


def make_signals():
    S = {}
    for lvl in (10, 20, 30, 45):
        for tag, cond in (("all", lambda f: True),
                          ("bumped30", lambda f: f.cum_micro >= 30),
                          ("bumped60", lambda f: f.cum_micro >= 60),
                          ("nobump<10", lambda f: f.cum_micro < 10)):
            def fn(f, r, now, prev_ath, lvl=lvl, cond=cond):
                return prev_ath < lvl * L <= r[RSOL] and cond(f)
            S[f"cross{lvl}_{tag}"] = fn

    def ath_break(f, r, now, prev_ath, need_micro, lo=15):
        if not (lo * L <= r[RSOL] <= 70 * L and r[RSOL] > prev_ath and prev_ath >= lo * L):
            return False
        micro5, _ = f.window(now, 300_000)
        _, outs2 = f.window(now, 120_000)
        if outs2 < 5:
            return False
        if need_micro is None:
            return True
        return micro5 >= 5 if need_micro else micro5 == 0
    S["athbreak_outside5_any"] = lambda f, r, now, pa: ath_break(f, r, now, pa, None)
    S["athbreak_outside5_activebump"] = lambda f, r, now, pa: ath_break(f, r, now, pa, True)
    S["athbreak_outside5_nobump"] = lambda f, r, now, pa: ath_break(f, r, now, pa, False)
    return S


def seg_end(coverage, ms):
    for a, b in coverage:
        if a <= ms <= b:
            return b
    return None


def run():
    T = pickle.load(gzip.open(os.path.join(HERE, "TAPES.pkl.gz")))
    cov = T["coverage"]
    S = make_signals()
    res = defaultdict(list)
    n_mints = 0
    for mint, d in T["mints"].items():
        if d["create_slot"] is None or not d["rows"]:
            continue
        end = seg_end(cov, d["create_ms"])
        if end is None:
            continue
        rows = [r for r in d["rows"] if r[SLOT] >= d["create_slot"]]
        if not rows:
            continue
        n_mints += 1
        G = groups(rows)
        f = Feat()
        fired = set()
        for gi, g in enumerate(G):
            prev_ath = f.ath
            f.update(g)
            r = g[-1]
            now = r[MS]
            if now > end:
                break
            for name, fn in S.items():
                if name in fired or not fn(f, r, now, prev_ath):
                    continue
                fired.add(name)
                res[name].append(evaluate(mint, G, gi, end, f))
    return n_mints, res


def evaluate(mint, G, gi, end, f):
    sig_row = G[gi][-1]
    fast, same_mix, nxt1, slow = entry_states(G, gi)
    t_entry = sig_row[MS]

    def path_from(ei):
        er = G[ei][-1]
        held = buy_tokens(er[VSOL], er[VTOK], er[FEE])
        out = {}
        mfe = 0
        hi = 0
        last = er
        grad = False
        hz = list(HORIZONS)
        fp = {}
        for j in range(ei + 1, len(G)):
            r = G[j][-1]
            while hz and r[MS] > t_entry + hz[0]:
                out[hz[0]] = sell_value(last[VSOL], last[VTOK], held, last[FEE]) / BUDGET - 1
                hz.pop(0)
            if not hz:
                break
            last = r
            v = sell_value(r[VSOL], r[VTOK], held, r[FEE]) / BUDGET - 1
            mfe = max(mfe, v)
            for x in FP_LEVELS:
                if x not in fp and (v >= x or v <= -x):
                    fp[x] = 1 if v >= x else -1
            if r[RSOL] >= GRAD_RSOL:
                grad = True
                break
        out["fp"] = fp
        for h in hz:
            if grad or t_entry + h <= end:
                out[h] = sell_value(last[VSOL], last[VTOK], held, last[FEE]) / BUDGET - 1
            else:
                out[h] = None  # censored by coverage end
        return out, mfe, grad

    branches = {}
    for name, ei in (("fast", fast), ("slow", slow), ("nxt1", nxt1)):
        branches[name] = path_from(ei)
    same = [(path_from(ei), w) for ei, w in same_mix]
    return dict(mint=mint, rsol=sig_row[RSOL] / L, cum_micro=f.cum_micro, fast=branches["fast"],
                slow=branches["slow"], nxt1=branches["nxt1"], same=same)


def mix(e, p, h):
    vals = [(b[0][h], w * p) for b, w in e["same"]] + [(e["nxt1"][0][h], 1 - p)]
    if any(v is None for v, _ in vals):
        return None
    return sum(v * w for v, w in vals)


def summarize(n_mints, res):
    print(f"universe: {n_mints} mints with creation captured inside coverage\n")
    hdr = f"{'signal':32} {'n':>5} {'grad':>5} | {'15m central80':>13} {'fast':>7} {'c85':>7} {'slow':>7} | {'5m':>7} {'30m':>7} {'60m':>7} | {'win15':>5} {'MFE med':>7} {'P(MFE>30%)':>10}"
    print(hdr)
    for name in sorted(res):
        E = res[name]
        def mean(xs):
            xs = [x for x in xs if x is not None]
            return (sum(xs) / len(xs), len(xs)) if xs else (float("nan"), 0)
        c15, n15 = mean([mix(e, 0.80, 900_000) for e in E])
        f15, _ = mean([e["fast"][0][900_000] for e in E])
        c85, _ = mean([mix(e, 0.85, 900_000) for e in E])
        s15, _ = mean([e["slow"][0][900_000] for e in E])
        c5, _ = mean([mix(e, 0.80, 300_000) for e in E])
        c30, _ = mean([mix(e, 0.80, 1_800_000) for e in E])
        c60, _ = mean([mix(e, 0.80, 3_600_000) for e in E])
        v15 = [mix(e, 0.80, 900_000) for e in E]
        v15 = [v for v in v15 if v is not None]
        win = sum(v > 0 for v in v15) / max(1, len(v15))
        mfes = sorted(e["fast"][1] * 0 + sum(b[1] * w for b, w in e["same"]) * 0.8 + e["nxt1"][1] * 0.2 for e in E)
        med = mfes[len(mfes) // 2] if mfes else float("nan")
        p30 = sum(m > 0.30 for m in mfes) / max(1, len(mfes))
        grad = sum(e["fast"][2] for e in E)
        print(f"{name:32} {len(E):5d} {grad:5d} | {c15:+13.1%} {f15:+7.1%} {c85:+7.1%} {s15:+7.1%} | {c5:+7.1%} {c30:+7.1%} {c60:+7.1%} | {win:5.0%} {med:+7.1%} {p30:10.0%}")


if __name__ == "__main__":
    n, res = run()
    pickle.dump(res, open(os.path.join(HERE, "study_results.pkl"), "wb"))
    summarize(n, res)
