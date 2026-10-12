#!/usr/bin/env python3
"""Follow-up: late-curve level crossings split by causal bumper intensity, with
confounder controls (buys so far, distinct buyers so far) and a time split."""
import gzip, os, pickle, random
from collections import defaultdict
import study as S

HERE = os.path.dirname(os.path.abspath(__file__))


def run():
    T = pickle.load(gzip.open(os.path.join(HERE, "TAPES.pkl.gz")))
    cov = T["coverage"]
    mid = sorted(d["create_ms"] for d in T["mints"].values() if d["create_ms"])[len(T["mints"]) // 3]
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
        nbuys, buyers = 0, set()
        done = set()
        for gi, g in enumerate(G):
            prev = f.ath
            f.update(g)
            for r in g:
                if r[S.BUY]:
                    nbuys += 1
                    buyers.add(r[S.USER])
            r = g[-1]
            if r[S.MS] > end:
                break
            for lvl in (35, 45, 55):
                if lvl in done or not (prev < lvl * S.L <= r[S.RSOL]):
                    continue
                done.add(lvl)
                e = S.evaluate(mint, G, gi, end, f)
                micro5, outs2 = f.window(r[S.MS], 300_000)
                e.update(level=lvl, nbuys=nbuys, nbuyers=len(buyers), micro_w=len(f.micro_w),
                         micro5=micro5, age_min=(r[S.MS] - d["create_ms"]) / 60000,
                         half="early" if d["create_ms"] < mid else "late")
                out.append(e)
    return out


def stats(E, label):
    v = [S.mix(e, 0.80, 900_000) for e in E]
    v = [x for x in v if x is not None]
    v60 = [S.mix(e, 0.80, 3_600_000) for e in E]
    v60 = [x for x in v60 if x is not None]
    mfe = [sum(b[1] * w for b, w in e["same"]) * 0.8 + e["nxt1"][1] * 0.2 for e in E]
    grad = sum(e["fast"][2] for e in E)
    if not E:
        return
    # bootstrap CI on graduation rate
    rng = random.Random(7)
    bs = sorted(sum(rng.choice(E)["fast"][2] for _ in E) / len(E) for _ in range(500))
    def up_first(e, x):
        br = [(b[0]["fp"].get(x, 0), w * 0.8) for b, w in e["same"]] + [(e["nxt1"][0]["fp"].get(x, 0), 0.2)]
        return sum(w for s, w in br if s == 1), sum(w for s, w in br if s == -1)
    fps = []
    for x in (0.2, 0.3, 0.5):
        u = [up_first(e, x) for e in E]
        fps.append(f"{sum(a for a, _ in u)/len(E):3.0%}/{sum(b for _, b in u)/len(E):3.0%}")
    print(f"  {label:34} n={len(E):4d} grad={grad/len(E):5.0%} [{bs[12]:.0%},{bs[487]:.0%}]"
          f" 15m={sum(v)/max(1,len(v)):+6.1%} 60m={sum(v60)/max(1,len(v60)):+6.1%}"
          f" MFE>30%={sum(m>0.3 for m in mfe)/len(E):4.0%}  up/down first ±20,30,50%: {' '.join(fps)}")


def main():
    out = run()
    pickle.dump(out, open(os.path.join(HERE, "study_late.pkl"), "wb"))
    for lvl in (35, 45, 55):
        E = [e for e in out if e["level"] == lvl]
        print(f"\n== first crossing {lvl} SOL  (n={len(E)})")
        q = sorted(e["nbuys"] for e in E)
        t1, t2 = q[len(q) // 3], q[2 * len(q) // 3]
        for name, fn in (("micro<10", lambda e: e["cum_micro"] < 10),
                         ("micro10-29", lambda e: 10 <= e["cum_micro"] < 30),
                         ("micro30+", lambda e: e["cum_micro"] >= 30),
                         ("microW>=10", lambda e: e["micro_w"] >= 10),
                         ("active bump (>=5 micro in 5m)", lambda e: e["micro5"] >= 5)):
            stats([e for e in E if fn(e)], name)
        act = [e for e in E if e["nbuys"] >= 60]
        print(f"  -- active coins only (>=60 buys so far, n={len(act)}), by micro share of buys:")
        stats([e for e in act if e["cum_micro"] / e["nbuys"] < 0.15], "micro share <15%")
        stats([e for e in act if 0.15 <= e["cum_micro"] / e["nbuys"] < 0.30], "micro share 15-30%")
        stats([e for e in act if e["cum_micro"] / e["nbuys"] >= 0.30], "micro share >=30%")
        stats([e for e in act if e["micro5"] >= 5], "active bump now")
        stats([e for e in act if e["micro5"] == 0], "no bump in last 5m")
        stats([e for e in E if e["nbuys"] < 60], "few-buy coins (<60 buys)")
        print("  -- time split, active coins:")
        for h in ("early", "late"):
            stats([e for e in act if e["half"] == h], f"{h} / all active")
            stats([e for e in act if e["half"] == h and e["micro5"] >= 5], f"{h} / active bump now")


if __name__ == "__main__":
    main()
