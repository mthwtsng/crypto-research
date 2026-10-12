#!/usr/bin/env python3
"""Forensic analysis of the EH4cP8 tape. Writes analysis.json and prints a digest."""
import json, os, collections, datetime, statistics

HERE = os.path.dirname(os.path.abspath(__file__))
T = [json.loads(l) for l in open(os.path.join(HERE, "tape.jsonl"))]
SIGS = json.load(open(os.path.join(HERE, "signatures.json")))["signatures"]
TXS = {json.loads(l)["sig"]: json.loads(l) for l in open(os.path.join(HERE, "txs.jsonl"))}

CREATE_SLOT, CREATE_BT = 451744435, 1790712411
DEV = "D9gQ6RhKEpnobPBUdWY5bPQt2p3zGk3iVz6ChpUi2ArA"       # create-tx signer / CreateEvent.user
CREATOR_FEE = "4bjXcMSRTEE2gFo4J6ovc9NMGrHPiMcZN1RdJ42ePP2e"  # CreateEvent.creator (fee recipient)
REVIVAL_SLOT = 455876702
MAINRUN_SLOT = 455925991
COMPLETE_SLOT = 455947247
JUP = "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"
MICRO = 0.02

def utc(bt):
    return datetime.datetime.fromtimestamp(bt, datetime.UTC).strftime("%Y-%m-%d %H:%M:%S")

def phase_of(t):
    if t["slot"] < REVIVAL_SLOT:
        return "launch"
    return "mainrun" if t["slot"] >= MAINRUN_SLOT else "revival_pre"

out = {}

# ---------- 1. timeline ----------
def milestones(rows, levels=(5, 10, 15, 20, 30, 50, 70, 84)):
    ms, peak = {}, None
    for t in rows:
        for L in levels:
            if L not in ms and t["r_sol"] >= L:
                ms[L] = {"ord": t["ord"], "slot": t["slot"], "utc": utc(t["blockTime"])}
        if peak is None or t["r_sol"] > peak["r_sol"]:
            peak = {"r_sol": round(t["r_sol"], 4), "ord": t["ord"], "slot": t["slot"], "utc": utc(t["blockTime"])}
    return ms, peak

def counts(rows):
    b = [t for t in rows if t["is_buy"]]
    s = [t for t in rows if not t["is_buy"]]
    return {"trades": len(rows), "buys": len(b), "sells": len(s), "unique_buyers": len({t["user"] for t in b}),
            "unique_traders": len({t["user"] for t in rows}), "buy_sol": round(sum(t["sol"] for t in b), 3),
            "sell_sol": round(sum(t["sol"] for t in s), 3)}

def failed_between(a, b):
    return sum(1 for s in SIGS if s["err"] is not None and a <= s["slot"] < b)

launch = [t for t in T if t["slot"] < REVIVAL_SLOT]
revival = [t for t in T if t["slot"] >= REVIVAL_SLOT]
mainrun = [t for t in T if t["slot"] >= MAINRUN_SLOT]
tl = {}
for name, rows, a, b in (("launch", launch, CREATE_SLOT, REVIVAL_SLOT), ("revival_all", revival, REVIVAL_SLOT, 10**12),
                         ("mainrun", mainrun, MAINRUN_SLOT, 10**12)):
    ms, peak = milestones(rows)
    tl[name] = {"counts": counts(rows), "milestones": ms, "peak": peak, "failed_txs": failed_between(a, b),
                "first": utc(rows[0]["blockTime"]), "last": utc(rows[-1]["blockTime"]),
                "end_r_sol": round(rows[-1]["r_sol"], 4)}
tl["total_failed"] = sum(1 for s in SIGS if s["err"] is not None)
tl["total_sigs"] = len(SIGS)
tl["launch_window_failed_first_400_slots"] = failed_between(CREATE_SLOT, CREATE_SLOT + 400)
# dormant
dorm = [t for t in launch if t["blockTime"] > CREATE_BT + 3600]
tl["dormant_trades_after_first_hour"] = len(dorm)
tl["pre_revival_r_sol"] = round(launch[-1]["r_sol"], 4)
out["timeline"] = tl

# r_sol path (per-minute close, revival) for the report
path = collections.OrderedDict()
for t in revival:
    path[utc(t["blockTime"])[11:16]] = round(t["r_sol"], 2)
out["revival_r_sol_by_minute"] = path
lpath = collections.OrderedDict()
for t in launch[:1300]:
    lpath[utc(t["blockTime"])[11:16]] = round(t["r_sol"], 2)
out["launch_r_sol_by_minute"] = lpath

# ---------- helpers for pre-entry state ----------
def state_before(idx):
    """Curve facts using only trades strictly before T[idx]."""
    t0 = T[idx]
    prior = T[:idx]
    ph_start = 0 if t0["slot"] < REVIVAL_SLOT else next(i for i, t in enumerate(T) if t["slot"] >= REVIVAL_SLOT)
    ph_prior = T[ph_start:idx]
    last = prior[-1] if prior else None
    def win(sec):
        w = [t for t in ph_prior if t0["blockTime"] - sec <= t["blockTime"] <= t0["blockTime"]]
        b = [t for t in w if t["is_buy"]]
        s = [t for t in w if not t["is_buy"]]
        return {"buys": len(b), "sells": len(s), "net_sol": round(sum(t["sol"] for t in b) - sum(t["sol"] for t in s), 3),
                "unique_buyers": len({t["user"] for t in b}), "micro_buys": sum(1 for t in b if t["sol"] < MICRO)}
    ath_all = max((t["r_sol"] for t in prior), default=0)
    ath_phase_before_last = max((t["r_sol"] for t in ph_prior[:-1]), default=0)
    dev_tokens = sum((t["tokens"] if t["is_buy"] else -t["tokens"]) for t in prior if t["user"] == DEV)
    dev_sold = any((not t["is_buy"]) and t["user"] == DEV for t in prior)
    return {"r_sol_before": round(last["r_sol"], 4) if last else 0,
            "last_trade_is_new_phase_ath": bool(last and ph_prior and last["r_sol"] >= ath_phase_before_last),
            "phase_ath_before": round(max((t["r_sol"] for t in ph_prior), default=0), 3),
            "all_time_ath_before": round(ath_all, 3),
            "w30": win(30), "w60": win(60),
            "unique_buyers_phase_so_far": len({t["user"] for t in ph_prior if t["is_buy"]}),
            "largest_prior_buy_phase": round(max((t["sol"] for t in ph_prior if t["is_buy"]), default=0), 4),
            "micro_buys_phase_so_far": sum(1 for t in ph_prior if t["is_buy"] and t["sol"] < MICRO),
            "dev_tokens_held_M": round(dev_tokens / 1e6, 3), "dev_has_sold": dev_sold,
            "secs_since_phase_start": t0["blockTime"] - T[ph_start]["blockTime"]}

# ---------- 2. tracked bots ----------
tracked = collections.OrderedDict()
for i, t in enumerate(T):
    if t["tracked_label"]:
        tracked.setdefault(t["user"], []).append(i)
bots = []
for u, idxs in tracked.items():
    rows = [T[i] for i in idxs]
    b = [t for t in rows if t["is_buy"]]
    s = [t for t in rows if not t["is_buy"]]
    tok_net = sum(t["tokens"] for t in b) - sum(t["tokens"] for t in s)
    receipts = [t["user_sol_delta"] for t in rows if t["user_sol_delta"] is not None]
    # dedupe receipts per signature (multi-event tx)
    seen, rec_sum = set(), 0.0
    for t in rows:
        if t["signature"] not in seen and t["user_sol_delta"] is not None:
            seen.add(t["signature"]); rec_sum += t["user_sol_delta"]
    first_buy_i = next((i for i in idxs if T[i]["is_buy"]), None)
    bots.append({
        "user": u, "label": rows[0]["tracked_label"], "phases": sorted({phase_of(t) for t in rows}),
        "n_buys": len(b), "n_sells": len(s), "sol_in_curve": round(sum(t["sol"] for t in b), 4),
        "sol_out_curve": round(sum(t["sol"] for t in s), 4),
        "curve_pnl_excl_fees": round(sum(t["sol"] for t in s) - sum(t["sol"] for t in b), 4),
        "receipt_net_sol": round(rec_sum, 4), "tokens_left_M": round(tok_net / 1e6, 3),
        "first_buy": None if first_buy_i is None else {"ord": T[first_buy_i]["ord"], "utc": utc(T[first_buy_i]["blockTime"]),
                     "slot": T[first_buy_i]["slot"], "sol": round(T[first_buy_i]["sol"], 4),
                     "r_sol_after": round(T[first_buy_i]["r_sol"], 3),
                     "secs_since_create": T[first_buy_i]["blockTime"] - CREATE_BT, "phase": phase_of(T[first_buy_i]),
                     "state_before": state_before(first_buy_i)},
        "last_trade": {"ord": rows[-1]["ord"], "utc": utc(rows[-1]["blockTime"]), "r_sol": round(rows[-1]["r_sol"], 3)},
        "entry_r_sol_range": [round(min(t["r_sol"] for t in b), 2), round(max(t["r_sol"] for t in b), 2)] if b else None,
        "exit_r_sol_range": [round(min(t["r_sol"] for t in s), 2), round(max(t["r_sol"] for t in s), 2)] if s else None,
        "median_hold_s": None, "routers": collections.Counter(p for t in rows for p in t["programs"]).most_common(3),
        "trades": [{"ord": t["ord"], "slot": t["slot"], "utc": utc(t["blockTime"]), "side": "B" if t["is_buy"] else "S",
                    "sol": round(t["sol"], 4), "r_sol": round(t["r_sol"], 3), "receipt": t["user_sol_delta"]} for t in rows]})
    # FIFO-ish hold: pair each buy with the next sell
    holds, q = [], []
    for t in rows:
        if t["is_buy"]:
            q.append(t["blockTime"])
        elif q:
            holds.append(t["blockTime"] - q.pop(0))
    bots[-1]["median_hold_s"] = statistics.median(holds) if holds else None
    bots[-1]["n_holds"] = len(holds)
out["tracked_bots"] = bots

# first tracked buy per phase + clusters
def first_tracked_buy(pred):
    for i, t in enumerate(T):
        if t["tracked_label"] and t["is_buy"] and pred(t):
            return i
fi = {}
for name, pred in (("launch_any", lambda t: t["slot"] < REVIVAL_SLOT),
                   ("launch_non_dev", lambda t: t["slot"] < REVIVAL_SLOT and t["user"] != DEV),
                   ("revival", lambda t: t["slot"] >= REVIVAL_SLOT),
                   ("mainrun", lambda t: t["slot"] >= MAINRUN_SLOT)):
    i = first_tracked_buy(pred)
    fi[name] = {"ord": T[i]["ord"], "label": T[i]["tracked_label"], "utc": utc(T[i]["blockTime"]), "slot": T[i]["slot"],
                "sol": round(T[i]["sol"], 4), "state_before": state_before(i)}
out["first_tracked_buy"] = fi

# clusters: tracked first-buys (per wallet, per phase) within 3 slots
firsts = []
for u, idxs in tracked.items():
    for ph in ("launch", "revival_pre", "mainrun"):
        i = next((i for i in idxs if T[i]["is_buy"] and phase_of(T[i]) == ph), None)
        if i is not None:
            firsts.append((T[i]["slot"], T[i]["tracked_label"], ph, round(T[i]["r_sol"], 2)))
firsts.sort()
clusters, cur = [], []
for f in firsts:
    if cur and f[0] - cur[-1][0] <= 3:
        cur.append(f)
    else:
        if len(cur) > 1:
            clusters.append(cur)
        cur = [f]
if len(cur) > 1:
    clusters.append(cur)
out["tracked_first_buys"] = firsts
out["tracked_entry_clusters_le3slots"] = clusters
# all tracked buys same-slot co-occurrence
slot_tr = collections.defaultdict(set)
for t in T:
    if t["tracked_label"] and t["is_buy"]:
        slot_tr[t["slot"]].add(t["tracked_label"])
out["slots_with_2plus_tracked_buyers"] = sum(1 for v in slot_tr.values() if len(v) >= 2)

# ---------- 3. fake volume ----------
def micro_stats(rows):
    m = [t for t in rows if t["is_buy"] and t["sol"] < MICRO]
    w = collections.Counter(t["user"] for t in m)
    gaps = [b["slot"] - a["slot"] for a, b in zip(m, m[1:])]
    return {"micro_buys": len(m), "wallets": len(w), "top_wallets": [(u, c) for u, c in w.most_common(8)],
            "median_slot_gap": statistics.median(gaps) if gaps else None,
            "first": utc(m[0]["blockTime"]) if m else None, "first_r_sol": round(m[0]["r_sol"], 2) if m else None,
            "sol_total": round(sum(t["sol"] for t in m), 4),
            "share_of_buys": round(len(m) / max(1, sum(1 for t in rows if t["is_buy"])), 3)}
out["micro"] = {"launch": micro_stats(launch), "revival_all": micro_stats(revival), "mainrun": micro_stats(mainrun)}

# micro timeline relative to r_sol: per-minute counts in revival
mt = collections.OrderedDict()
for t in revival:
    k = utc(t["blockTime"])[11:16]
    x = mt.setdefault(k, {"buys": 0, "micro": 0, "sells": 0, "tracked_buys": 0, "r_close": 0, "vol": 0.0})
    if t["is_buy"]:
        x["buys"] += 1
        x["micro"] += t["sol"] < MICRO
        x["tracked_buys"] += bool(t["tracked_label"])
    else:
        x["sells"] += 1
    x["vol"] = round(x["vol"] + t["sol"], 3)
    x["r_close"] = round(t["r_sol"], 2)
out["revival_minute_table"] = mt

# round trips: same wallet buy then sell within 10 slots
rt = []
last_buy = {}
for t in T:
    u = t["user"]
    if t["is_buy"]:
        last_buy[u] = t
    elif u in last_buy and t["slot"] - last_buy[u]["slot"] <= 10:
        b = last_buy.pop(u)
        rt.append({"user": u, "buy_ord": b["ord"], "sell_ord": t["ord"], "slots": t["slot"] - b["slot"],
                   "buy_sol": b["sol"], "sell_sol": t["sol"], "net": t["sol"] - b["sol"],
                   "same_tx": b["signature"] == t["signature"], "phase": phase_of(t), "tracked": t["tracked_label"]})
def rt_summary(ph):
    r = [x for x in rt if x["phase"] == ph]
    flat = [x for x in r if abs(x["net"]) <= 0.05 * x["buy_sol"]]
    w = collections.Counter(x["user"] for x in r)
    return {"round_trips_le10_slots": len(r), "near_flat_within_5pct": len(flat), "same_tx": sum(x["same_tx"] for x in r),
            "wallets": len(w), "gross_sol_both_legs": round(sum(x["buy_sol"] + x["sell_sol"] for x in r), 2),
            "tracked_round_trips": sum(1 for x in r if x["tracked"]),
            "top_wallets": w.most_common(8)}
out["round_trips"] = {ph: rt_summary(ph) for ph in ("launch", "revival_pre", "mainrun")}
gross = {ph: sum(t["sol"] for t in T if phase_of(t) == ph) for ph in ("launch", "revival_pre", "mainrun")}
out["gross_volume"] = {k: round(v, 2) for k, v in gross.items()}

# repeat-amount cohort: wallets that bought the identical lamport amount >= 3 times
amt = collections.defaultdict(collections.Counter)
for t in revival:
    if t["is_buy"]:
        amt[t["user"]][round(t["sol"], 6)] += 1
cohort = {u: c.most_common(1)[0] for u, c in amt.items() if c.most_common(1)[0][1] >= 3}
out["repeat_amount_wallets_revival"] = {u: {"amount": a, "times": n, "label": next((t["tracked_label"] for t in revival if t["user"] == u), None)}
                                         for u, (a, n) in sorted(cohort.items(), key=lambda kv: -kv[1][1])}

# routers / aggregators
prog_counter = collections.Counter()
for t in T:
    for p in set(t["programs"]):
        prog_counter[p] += 1
out["top_level_programs"] = prog_counter.most_common(25)
jup = [t for t in T if JUP in t["programs"]]
out["jupiter"] = {"trades": len(jup), "buys": sum(t["is_buy"] for t in jup), "wallets": len({t["user"] for t in jup}),
                  "micro_buys": sum(1 for t in jup if t["is_buy"] and t["sol"] < MICRO),
                  "by_phase": collections.Counter(phase_of(t) for t in jup),
                  "signer_ne_user": sum(1 for t in jup if t["signer"] != t["user"])}
sne = [t for t in T if t["signer"] != t["user"]]
out["signer_ne_user"] = {"trades": len(sne), "by_phase": collections.Counter(phase_of(t) for t in sne),
                         "top_signers": collections.Counter(t["signer"] for t in sne).most_common(6),
                         "micro_buys": sum(1 for t in sne if t["is_buy"] and t["sol"] < MICRO)}

# ---------- 4. creator / launch snipers ----------
dev_rows = [t for t in T if t["user"] in (DEV, CREATOR_FEE)]
out["dev_trades"] = [{"ord": t["ord"], "user": t["user"][:6], "utc": utc(t["blockTime"]), "side": "B" if t["is_buy"] else "S",
                      "sol": round(t["sol"], 4), "tokens_M": round(t["tokens"] / 1e6, 3), "r_sol": round(t["r_sol"], 3),
                      "receipt": t["user_sol_delta"]} for t in dev_rows]
first_slot = [t for t in launch if t["slot"] <= CREATE_SLOT + 2]
out["launch_snipe"] = {"trades_in_create_slot_plus2": len(first_slot), "buyers": len({t["user"] for t in first_slot if t["is_buy"]}),
                       "sol": round(sum(t["sol"] for t in first_slot if t["is_buy"]), 3),
                       "r_sol_after": round(first_slot[-1]["r_sol"], 3) if first_slot else None}
# biggest dumps (single sells) per phase and what followed
def dumps(rows, n=6):
    s = sorted([t for t in rows if not t["is_buy"]], key=lambda t: -t["sol"])[:n]
    res = []
    for d in s:
        after = [t for t in T if d["ord"] < t["ord"] <= d["ord"] + 30]
        res.append({"ord": d["ord"], "utc": utc(d["blockTime"]), "user": d["user"][:6], "sol": round(d["sol"], 3),
                    "r_sol_after": round(d["r_sol"], 2), "label": d["tracked_label"],
                    "tracked_buys_next30": [(t["tracked_label"], round(t["sol"], 3)) for t in after if t["tracked_label"] and t["is_buy"]],
                    "r_sol_30_later": round(after[-1]["r_sol"], 2) if after else None})
    return res
out["dumps"] = {"launch": dumps(launch), "revival": dumps(revival, 10)}

# early launch buyers (first 60 trades) and their exits
eb = collections.OrderedDict()
for t in launch[:60]:
    if t["is_buy"]:
        eb.setdefault(t["user"], 0)
for u in eb:
    rows = [t for t in launch if t["user"] == u]
    eb[u] = {"buy": round(sum(t["sol"] for t in rows if t["is_buy"]), 3), "sell": round(sum(t["sol"] for t in rows if not t["is_buy"]), 3),
             "label": rows[0]["tracked_label"]}
out["launch_early_buyers"] = eb

# revival cohort wallets first 45 trades: did they come back in mainrun?
early_rev = list(dict.fromkeys(t["user"] for t in revival[:45]))
out["revival_early_wallets"] = {u: {"n_trades_revival": sum(1 for t in revival if t["user"] == u),
                                    "net_curve_sol": round(sum((t["sol"] if not t["is_buy"] else -t["sol"]) for t in revival if t["user"] == u), 3),
                                    "label": next((t["tracked_label"] for t in revival if t["user"] == u), None),
                                    "traded_launch": any(t["user"] == u for t in launch)} for u in early_rev}

json.dump(out, open(os.path.join(HERE, "analysis.json"), "w"), indent=1, default=str)
print("ok")
