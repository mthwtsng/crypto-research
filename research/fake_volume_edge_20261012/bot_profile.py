#!/usr/bin/env python3
"""Entry/exit fingerprint of the top tracked scalpers vs a same-coin baseline."""
import gzip, os, pickle, random, statistics as st
from collections import defaultdict
import bot_study as B

HERE = os.path.dirname(os.path.abspath(__file__))
FEE = 0.0125
TXFEE = 0.001  # per side, priority + base (assumption; tips unknown)
RELAY = {"ARu4n5mFdZogZAravu7CcizaojWnS6oqka37gdLT5SZn"}
BOTS = ["ssssswdk", "sssssDdM", "BWBd3hj2", "BUkpShoE", "omegoMAe", "2gnL2LdN", "2FdJD3EV", "ESEGGqQ5",
        "77wS9zZH", "AHeEPb1i", "haqqiUUX"]


def net(t):
    return (t["sol_out"] * (1 - FEE) - t["sol_in"] * (1 + FEE)) / 1e9 - TXFEE * (t["nbuys"] + t["nsells"])


def q(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * len(xs)))] if xs else float("nan")


def fmt_ctx(C, label, n):
    def med(k):
        return st.median(c[k] for c in C)
    def share(fn):
        return sum(1 for c in C if fn(c)) / len(C)
    print(f"  {label:22} n={n:5d} rsol={st.median(c['_rsol'] for c in C):5.1f} micro10={med('micro10'):3.0f}"
          f" micro30={med('micro30'):3.0f} buys10={med('buys10'):3.0f} buyers10={med('buyers10'):3.0f}"
          f" net10={med('net10'):+5.2f} chg5={med('chg5'):+5.1%} dd60={med('dd60'):+5.1%}"
          f" prevBigBuy={share(lambda c: c['bigbuy_prev']):3.0%} prevBigSell={share(lambda c: c['bigsell_prev']):3.0%}"
          f" sameSlotAsPrev={share(lambda c: c.get('prev_slot_gap', 9) == 0):3.0%}")


def main():
    trips = pickle.load(open(os.path.join(HERE, "bot_trips.pkl"), "rb"))
    trips = [t for t in trips if t["wallet"] not in RELAY]
    T = pickle.load(gzip.open(os.path.join(HERE, "TAPES.pkl.gz")))
    M = T["mints"]
    rng = random.Random(3)
    # baseline: random non-tracked buys in the same mints the bots traded
    W = B.tracked()
    mints = list({t["mint"] for t in trips})
    base = []
    for m in rng.sample(mints, min(1500, len(mints))):
        rows = M[m]["rows"]
        idx = [i for i, r in enumerate(rows) if r[B.BUY] and r[B.USER] not in W and r[B.SOLA] >= B.MICRO]
        for i in rng.sample(idx, min(5, len(idx))):
            c = B.ctx_before(rows, i, rows[i][B.MS], rows[i][B.SLOT])
            c["_rsol"] = rows[i][B.RSOL] / 1e9
            base.append(c)
    print("== entry context (median / share). baseline = random non-tracked, non-micro buys in the same coins")
    fmt_ctx(base, "BASELINE", len(base))
    by = defaultdict(list)
    for t in trips:
        t["ctx"]["_rsol"] = t["rsol0"]
        by[t["wallet"][:8]].append(t)
    for b in BOTS:
        ts = by[b]
        if not ts:
            continue
        name = ts[0]["name"][:22]
        fmt_ctx([t["ctx"] for t in ts], name, len(ts))
        wins = [t for t in ts if net(t) > 0]
        loss = [t for t in ts if net(t) <= 0]
        fmt_ctx([t["ctx"] for t in wins], "   winners", len(wins))
        fmt_ctx([t["ctx"] for t in loss], "   losers", len(loss))

    print("\n== trip shape: net PnL after 1.25%/side Pump fee + 0.001 SOL/tx, hold, exit")
    print(f"  {'bot':22} {'trips':>5} {'net SOL':>8} {'net/trip':>8} {'win':>4} {'hold p25/50/75 s':>17} {'buys/sells':>10}"
          f" {'exitROI med win/loss':>20} {'peakBefExit':>11} {'exit after big buy':>18} {'big sell':>8}")
    for b in BOTS:
        ts = by[b]
        if not ts:
            continue
        ns = [net(t) for t in ts]
        hold = [(t["t1"] - t["t0"]) / 1000 for t in ts]
        roi = [net(t) / (t["sol_in"] / 1e9) for t in ts]
        print(f"  {ts[0]['name'][:22]:22} {len(ts):5d} {sum(ns):+8.2f} {sum(ns)/len(ts):+8.4f} {sum(x>0 for x in ns)/len(ns):4.0%}"
              f" {q(hold,.25):5.1f}/{q(hold,.5):5.1f}/{q(hold,.75):5.1f}"
              f" {st.mean(t['nbuys'] for t in ts):4.1f}/{st.mean(t['nsells'] for t in ts):4.1f}"
              f" {st.median([r for r in roi if r>0] or [0]):+9.1%}/{st.median([r for r in roi if r<=0] or [0]):+8.1%}"
              f" {st.median(t['peak_between'] for t in ts):+10.1%}"
              f" {sum(t['exit_after_bigbuy'] for t in ts)/len(ts):18.0%} {sum(t['exit_after_bigsell'] for t in ts)/len(ts):8.0%}")

    print("\n== does fake activity attract them? share of bot entries by micro-buys in prior 30 s, and net/trip")
    allb = [t for b in BOTS for t in by[b]]
    for lo, hi in ((0, 1), (1, 3), (3, 6), (6, 12), (12, 999)):
        sub = [t for t in allb if lo <= t["ctx"]["micro30"] < hi]
        bs = [c for c in base if lo <= c["micro30"] < hi]
        if sub:
            print(f"  micro30 {lo:>2}-{hi:<3}: bot entries {len(sub)/len(allb):4.0%} vs baseline buys {len(bs)/len(base):4.0%}"
                  f" | bot net/trip {st.mean(net(t) for t in sub):+.4f} win {sum(net(t)>0 for t in sub)/len(sub):3.0%} n={len(sub)}")


if __name__ == "__main__":
    main()
