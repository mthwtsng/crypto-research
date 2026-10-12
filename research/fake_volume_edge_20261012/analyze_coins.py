#!/usr/bin/env python3
"""Causal per-coin profile for the fake-volume case coins.

Reads coins/<mint>/txs.jsonl (from fetch_coin.py) and prints, per coin:
  lifetime summary (peak / final real SOL, graduation, micro-buy share, bumper P&L)
  milestone snapshots: state knowable when real SOL first crosses each level,
  and the forward path afterwards (max, drawdown before max, value at +5/+15 min).
"""
import json, os, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
MICRO = 20_000_000  # 0.02 SOL
LEVELS = [3, 5, 10, 15, 20, 30, 40, 60]
LAMPORTS = 1e9


def load(mint):
    p = os.path.join(HERE, "coins", mint, "txs.jsonl")
    if not os.path.exists(p):
        return None
    recs = [json.loads(l) for l in open(p)]
    rows = []
    create = None
    for r in recs:
        if r.get("create"):
            create = (r["slot"], r["blockTime"], r["create"].get("user"))
        for k, t in enumerate(r["trades"]):
            rows.append((r["slot"], t["timestamp"], k, r["sig"], t, r["signer"], r["top_programs"], r["complete"]))
    rows.sort(key=lambda x: (x[0], x[1], x[2]))
    return create, rows


def price(t):
    return t["v_sol"] / t["v_tok"]


def profile(mint, tag):
    got = load(mint)
    if not got or not got[1]:
        print(f"\n### {mint} [{tag}] no data")
        return None
    create, rows = got
    t0 = create[1] if create else rows[0][1]
    creator = create[2] if create else None
    peak, peak_i = 0, 0
    for i, row in enumerate(rows):
        if row[4]["r_sol"] > peak:
            peak, peak_i = row[4]["r_sol"], i
    buys = [r for r in rows if r[4]["is_buy"]]
    micro = [r for r in buys if r[4]["sol_amount"] < MICRO]
    flow = defaultdict(int)
    nmicro = defaultdict(int)
    for r in rows:
        t = r[4]
        flow[t["user"]] += -t["sol_amount"] if t["is_buy"] else t["sol_amount"]
        if t["is_buy"] and t["sol_amount"] < MICRO:
            nmicro[t["user"]] += 1
    bumpers = {u for u, n in nmicro.items() if n >= 3}
    graduated = any(r[7] for r in rows)
    last = rows[-1][4]
    print(f"\n### {mint} [{tag}]")
    print(f"  created {'yes' if create else 'NOT IN HISTORY'} creator={creator} trades={len(rows)} buys={len(buys)}"
          f" micro={len(micro)} ({len(micro)/max(1,len(buys)):.0%} of buys, "
          f"{sum(r[4]['sol_amount'] for r in micro)/max(1,sum(r[4]['sol_amount'] for r in buys)):.1%} of buy SOL)")
    print(f"  peak real SOL {peak/LAMPORTS:.1f} at +{(rows[peak_i][1]-t0)/60:.1f}m; final {last['r_sol']/LAMPORTS:.1f};"
          f" graduated={graduated}; span {(rows[-1][1]-t0)/60:.0f}m")
    bp = sum(flow[u] for u in bumpers)
    print(f"  bumper wallets (>=3 micro buys): {len(bumpers)}, their net SOL {bp/LAMPORTS:+.2f};"
          f" creator net {flow.get(creator,0)/LAMPORTS:+.2f}")
    top = sorted(flow.items(), key=lambda kv: kv[1])
    print("  top extractors:", ", ".join(f"{u[:6]} {v/LAMPORTS:+.2f}" for u, v in top[-4:][::-1]))
    print("  top losers:   ", ", ".join(f"{u[:6]} {v/LAMPORTS:+.2f}" for u, v in top[:3]))

    # milestone snapshots, strictly from rows[:i+1]
    print("  lvl  t+min  micro  bumpW  outsideBuyers  microShare10m | fwdMax  ddBeforeMax  +5m   +15m  (price ratio vs entry)")
    seen_lvls = set()
    cum_micro, micro_w, outside = 0, set(), set()
    win = []
    out = []
    for i, row in enumerate(rows):
        t = row[4]
        if t["is_buy"]:
            if t["sol_amount"] < MICRO:
                cum_micro += 1
                micro_w.add(t["user"])
            else:
                outside.add(t["user"])
            win.append((row[1], t["sol_amount"] < MICRO))
        for L in LEVELS:
            if L in seen_lvls or t["r_sol"] < L * LAMPORTS:
                continue
            seen_lvls.add(L)
            p0 = price(t)
            recent = [m for ts, m in win if ts >= row[1] - 600]
            share = sum(recent) / max(1, len(recent))
            fwd = rows[i + 1:]
            if not fwd:
                continue
            mx_j = max(range(len(fwd)), key=lambda j: fwd[j][4]["r_sol"])
            mx = price(fwd[mx_j][4])
            mn = min(price(r[4]) for r in fwd[:mx_j + 1])
            def at(sec):
                c = [r for r in fwd if r[1] <= row[1] + sec]
                return price(c[-1][4]) / p0 if c else 1.0
            rec = dict(level=L, t_min=(row[1] - t0) / 60, micro=cum_micro, bumper_w=len(micro_w),
                       outside=len(outside), micro_share_10m=share, fwd_max=mx / p0, dd=mn / p0 - 1,
                       r5=at(300), r15=at(900))
            out.append(rec)
            print(f"  {L:>3}  {rec['t_min']:5.1f}  {cum_micro:5d}  {len(micro_w):5d}  {len(outside):13d}  {share:12.0%} |"
                  f" {rec['fwd_max']:5.2f}x  {rec['dd']:+10.0%}  {rec['r5']:.2f}  {rec['r15']:.2f}")
    return dict(mint=mint, tag=tag, peak=peak / LAMPORTS, graduated=graduated, milestones=out,
                micro=len(micro), bumpers=len(bumpers), bumper_net=bp / LAMPORTS)


def main():
    res = []
    for line in open(os.path.join(HERE, "coins.txt")):
        mint, tag = line.split()
        if len(sys.argv) > 1 and mint not in sys.argv[1:]:
            continue
        r = profile(mint, tag)
        if r:
            res.append(r)
    json.dump(res, open(os.path.join(HERE, "coin_profiles.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
