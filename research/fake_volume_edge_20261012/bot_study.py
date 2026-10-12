#!/usr/bin/env python3
"""Reverse-engineer tracked wallets' scalps from the live tapes.

Round trip = per (wallet, mint) from first buy at flat position until the token
position returns to <= 1% of its peak. SOL amounts are TradeEvent sol_amount
(excludes Pump fees, priority fees and tips), so PnL here is gross.

For each round trip we record the tape context strictly before the opening buy and
around the exit, plus the slot gap to the trade it most plausibly reacted to.
"""
import gzip, os, pickle, re, statistics as st
from collections import defaultdict, deque

HERE = os.path.dirname(os.path.abspath(__file__))
BOT_REPO = os.environ.get("CRYPTO_BOT_REPO", os.path.expanduser("~/code/Crypto"))
L = 1e9
MICRO = 20_000_000
SLOT, IDX, K, MS, SIG, USER, BUY, SOLA, TOK, RSOL, VSOL, VTOK, FEE, JUP, PAYER = range(15)


def tracked():
    out = {}
    for line in open(os.path.join(BOT_REPO, "tracked_wallets.txt")):
        body, _, comment = line.partition("#")
        for w in re.split(r"[,\s]+", body.strip()):
            if 32 <= len(w) <= 44:
                out[w] = comment.strip()
    return out


def price(r):
    return r[VSOL] / r[VTOK]


def ctx_before(rows, i, now, slot):
    """Tape context from trades strictly before rows[i]."""
    c = dict(micro10=0, micro30=0, buys10=0, buyers10=set(), net10=0.0, bigsell_prev=False,
             bigbuy_prev=False, same_slot_prior=0, chg5=0.0, dd60=0.0)
    p_now = price(rows[i - 1]) if i else price(rows[i])
    hi60 = p_now
    p5 = p_now
    for j in range(i - 1, -1, -1):
        r = rows[j]
        age = now - r[MS]
        if age > 60_000:
            break
        hi60 = max(hi60, price(r))
        if age <= 5_000:
            p5 = price(rows[j - 1]) if j else price(r)
        if r[SLOT] == slot:
            c["same_slot_prior"] += 1
        if r[BUY]:
            if r[SOLA] < MICRO:
                if age <= 10_000:
                    c["micro10"] += 1
                if age <= 30_000:
                    c["micro30"] += 1
            if age <= 10_000:
                c["buys10"] += 1
                c["buyers10"].add(r[USER])
        if age <= 10_000:
            c["net10"] += (r[SOLA] if r[BUY] else -r[SOLA]) / L
    if i:
        prev = rows[i - 1]
        c["bigsell_prev"] = (not prev[BUY]) and prev[SOLA] >= 0.5 * L
        c["bigbuy_prev"] = prev[BUY] and prev[SOLA] >= 0.5 * L
        c["prev_slot_gap"] = rows[i][SLOT] - prev[SLOT]
        c["prev_size"] = prev[SOLA] / L * (1 if prev[BUY] else -1)
    c["buyers10"] = len(c["buyers10"])
    c["chg5"] = p_now / p5 - 1
    c["dd60"] = p_now / hi60 - 1
    return c


def main():
    W = tracked()
    T = pickle.load(gzip.open(os.path.join(HERE, "TAPES.pkl.gz")))
    trips = []
    for mint, d in T["mints"].items():
        rows = d["rows"]
        if not any(r[USER] in W for r in rows):
            continue
        pos = {}
        for i, r in enumerate(rows):
            u = r[USER]
            if u not in W:
                continue
            p = pos.get(u)
            if r[BUY]:
                if p is None:
                    p = pos[u] = dict(wallet=u, name=W[u], mint=mint, i0=i, t0=r[MS], slot0=r[SLOT], p0=price(r),
                                      rsol0=r[RSOL] / L, tok=0, peak=0, sol_in=0, sol_out=0, nbuys=0, nsells=0,
                                      ctx=ctx_before(rows, i, r[MS], r[SLOT]), jup=r[JUP], payer=r[PAYER])
                p["tok"] += r[TOK]
                p["peak"] = max(p["peak"], p["tok"])
                p["sol_in"] += r[SOLA]
                p["nbuys"] += 1
            elif p is not None:
                p["tok"] -= r[TOK]
                p["sol_out"] += r[SOLA]
                p["nsells"] += 1
                if p["tok"] <= p["peak"] * 0.01:
                    p.update(t1=r[MS], slot1=r[SLOT], p1=price(rows[i - 1]) if i else price(r), i1=i)
                    # what happened between entry and exit
                    seg = rows[p["i0"] + 1:i]
                    p["n_between"] = len(seg)
                    p["peak_between"] = max([price(x) for x in seg], default=p["p0"]) / p["p0"] - 1
                    p["exit_after_bigsell"] = bool(seg) and (not seg[-1][BUY]) and seg[-1][SOLA] >= 0.5 * L
                    p["exit_after_bigbuy"] = bool(seg) and seg[-1][BUY] and seg[-1][SOLA] >= 0.5 * L
                    p["exit_ctx"] = ctx_before(rows, i, r[MS], r[SLOT])
                    trips.append(p)
                    del pos[u]
    pickle.dump(trips, open(os.path.join(HERE, "bot_trips.pkl"), "wb"))
    print(f"closed round trips by tracked wallets: {len(trips)} across {len({t['mint'] for t in trips})} mints, "
          f"{len({t['wallet'] for t in trips})} wallets")


if __name__ == "__main__":
    main()
