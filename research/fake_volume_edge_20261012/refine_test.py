#!/usr/bin/env python3
"""Directional tests of the refinements proposed from tracked-bot behaviour.

Signals (evaluated after each complete transaction):
  consensus  a tracked wallet buys while a *different* tracked wallet bought this mint
             within the previous 5 slots; real SOL 10-60 (any coin in the tapes)
  catalyst   a non-tracked buy >= 0.40 SOL leaves real SOL in 14-38, price within 2% of
             the 60 s high, >= 3 micro buys in the prior 30 s (from-creation coins only)
One attempt per mint at a time, 60 s cooldown after the exit window.
Entry placement per contract (fast / central p=0.80 / slow); 0.5 SOL, fees, own impact.
Exit diagnostics: first passage +10%/-7% capped at 30 s; fixed 30 s / 120 s marks;
'bot sell' = sell placed after the first tracked-wallet sell following our entry (cap 300 s).
Exit fills use the same placement as entry. Opportunity diagnostics, not executable PnL.
"""
import gzip, os, pickle, sys
import study as S
import bot_study as B

HERE = os.path.dirname(os.path.abspath(__file__))
RELAY = "ARu4n5mFdZogZAravu7CcizaojWnS6oqka37gdLT5SZn"
NOFEE = "--nofee" in sys.argv


def val(r, held):
    fee = 0 if NOFEE else r[S.FEE]
    return S.sell_value(r[S.VSOL], r[S.VTOK], held, fee) / S.BUDGET - 1


def held_at(r):
    return S.buy_tokens(r[S.VSOL], r[S.VTOK], 0 if NOFEE else r[S.FEE])


def exits(G, ei, t0, W, mode):
    """Return dict of exit values for one entry branch; exit landings use `mode` placement."""
    held = held_at(G[ei][-1])
    out = {}
    trig = {}
    for j in range(ei + 1, len(G)):
        r = G[j][-1]
        dt = r[S.MS] - t0
        if "tp" not in trig:
            v = val(r, held)
            if v >= 0.10 or v <= -0.07 or dt > 30_000:
                trig["tp"] = j if dt <= 30_000 else j - 1
        if "h30" not in trig and dt > 30_000:
            trig["h30"] = j - 1
        if "h120" not in trig and dt > 120_000:
            trig["h120"] = j - 1
        if "bot" not in trig:
            if any((not x[S.BUY]) and x[S.USER] in W and x[S.USER] != RELAY for x in G[j]) or dt > 300_000:
                trig["bot"] = j if dt <= 300_000 else j - 1
        if len(trig) == 4 or r[S.RSOL] >= S.GRAD_RSOL:
            break
    last = len(G) - 1
    for k in ("tp", "h30", "h120", "bot"):
        j = max(ei, trig.get(k, last))
        if k in ("h30", "h120"):
            out[k] = val(G[j][-1], held)  # timers: no reactive placement penalty
        else:
            out[k] = sum(w * val(G[x][-1], held) for x, w in place(G, j, mode))
    return out


def place(G, gi, mode):
    fast, same_mix, nxt1, slow = S.entry_states(G, gi)
    if mode == "fast":
        return [(fast, 1.0)]
    if mode == "slow":
        return [(slow, 1.0)]
    return [(ei, w * 0.8) for ei, w in same_mix] + [(nxt1, 0.2)]


def evaluate(G, gi, W):
    t0 = G[gi][-1][S.MS]
    res = {}
    for mode in ("fast", "c80", "slow"):
        acc = {}
        for ei, w in place(G, gi, mode):
            for k, v in exits(G, ei, t0, W, mode).items():
                acc[k] = acc.get(k, 0) + w * v
        res[mode] = acc
    return res


def run():
    W = set(B.tracked())
    T = pickle.load(gzip.open(os.path.join(HERE, "TAPES.pkl.gz")))
    out = {"consensus": [], "catalyst": [], "single_bot": []}
    for mint, d in T["mints"].items():
        rows = d["rows"]
        has_bot = any(r[S.USER] in W for r in rows)
        from_creation = d["create_slot"] is not None and S.seg_end(T["coverage"], d["create_ms"]) is not None
        if not has_bot and not from_creation:
            continue
        if from_creation:
            rows = [r for r in rows if r[S.SLOT] >= d["create_slot"]]
        if len(rows) < 30:
            continue
        G = S.groups(rows)
        starts, n = [], 0
        for g in G:
            starts.append(n)
            n += len(g)
        busy = {"consensus": 0, "catalyst": 0, "single_bot": 0}
        recent_bot = []  # (slot, wallet)
        for gi, g in enumerate(G):
            r = g[-1]
            now = r[S.MS]
            bot_buys = [x for x in g if x[S.BUY] and x[S.USER] in W and x[S.USER] != RELAY]
            recent_bot = [(s, w) for s, w in recent_bot if s >= r[S.SLOT] - 5]
            if bot_buys and 10 * S.L <= r[S.RSOL] <= 60 * S.L:
                u = bot_buys[0][S.USER]
                if now >= busy["single_bot"]:
                    out["single_bot"].append(evaluate(G, gi, W))
                    busy["single_bot"] = now + 90_000
                if any(w != u for _, w in recent_bot) and now >= busy["consensus"]:
                    out["consensus"].append(evaluate(G, gi, W))
                    busy["consensus"] = now + 90_000
            for x in bot_buys:
                recent_bot.append((x[S.SLOT], x[S.USER]))
            if from_creation and now >= busy["catalyst"] and 14 * S.L <= r[S.RSOL] <= 38 * S.L:
                cat = [x for x in g if x[S.BUY] and x[S.USER] not in W and x[S.SOLA] >= 0.4 * S.L]
                if cat:
                    i = starts[gi] + len(g)
                    if i < len(rows):
                        c = B.ctx_before(rows, i, now + 1, -1)
                        if c["dd60"] >= -0.02 and c["micro30"] >= 3:
                            out["catalyst"].append(evaluate(G, gi, W))
                            busy["catalyst"] = now + 90_000
    return out


if __name__ == "__main__":
    out = run()
    print(f"{'(no Pump fees: reconciliation only)' if NOFEE else 'fees + own impact included'}; mean round-trip return per attempt")
    print(f"{'signal':11} {'n':>5} | {'exit':5} {'fast':>7} {'central80':>9} {'slow':>7} {'win c80':>7}")
    for name, R in out.items():
        if not R:
            continue
        for k in ("tp", "h30", "h120", "bot"):
            m = {mode: sum(x[mode][k] for x in R) / len(R) for mode in ("fast", "c80", "slow")}
            win = sum(x["c80"][k] > 0 for x in R) / len(R)
            print(f"{name:11} {len(R):5d} | {k:5} {m['fast']:+7.2%} {m['c80']:+9.2%} {m['slow']:+7.2%} {win:7.0%}")
