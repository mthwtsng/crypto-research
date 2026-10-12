#!/usr/bin/env python3
"""Compress live ghost observation logs into per-mint trade tapes.

Output: TAPES.pkl.gz = {
  "coverage": [(start_ms, end_ms), ...]   # per source file, received-time span
  "gaps": [(from_ms, to_ms), ...]         # stream silences > GAP_MS inside files
  "mints": {mint: {"creator", "create_slot", "create_ms", "rows": [...]}}
}
Row: (slot, tx_index, received_ms, signature, user, is_buy, sol_raw, tokens_raw,
      rsol_raw, vsol_raw, vtokens_raw, fee_bps_total, jupiter_routed, fee_payer_is_user)
"""
import glob, gzip, json, os, pickle, sys
from collections import defaultdict
from multiprocessing import Pool

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "TAPES.pkl.gz")
CHUNK = 192 * 1024 * 1024
GAP_MS = 3000
JUPITER = {"JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4", "JUP4Fb2cqiRUcaTHdrPC8h2gNsA2ETXiPDD33WcGuJB"}
SOL = "11111111111111111111111111111111"


def files():
    out = sorted(glob.glob(os.path.join(ROOT, "data/archive/ghost_observations_before_*.jsonl")))
    out.append(os.path.join(ROOT, "data/ghost_observations.jsonl"))
    return out


def chunks():
    for path in files():
        size = os.path.getsize(path)
        start = 0
        while start < size:
            yield (path, start, min(size, start + CHUNK))
            start += CHUNK


def work(job):
    path, start, end = job
    rows, creates, times = [], [], []
    with open(path, "rb") as fp:
        if start:
            fp.seek(start - 1)
            if fp.read(1) != b"\n":
                fp.readline()
        while fp.tell() < end:
            line = fp.readline()
            if not line:
                break
            try:
                d = json.loads(line)
            except Exception:
                continue
            ms = d.get("received_at_ms") or 0
            times.append(ms)
            slot = d.get("slot") or 0
            idx = d.get("transaction_index")
            sig = d.get("signature")
            for pair in d.get("creators") or []:
                creates.append((pair[0], pair[1], slot, idx if idx is not None else -1, ms))
            evs = d.get("events") or []
            if not evs:
                continue
            jup = any(p in JUPITER for p in (d.get("program_ids") or []))
            payer = d.get("fee_payer")
            for k, e in enumerate(evs):
                if e.get("quote_mint", SOL) != SOL or not e.get("supported_sol_quote", True):
                    continue
                rows.append((
                    e["mint"], slot, idx if idx is not None else -1, k, ms, sig, e["user"],
                    bool(e["is_buy"]), e["sol_raw"], e["tokens_raw"], e["rsol_raw"], e["vsol_raw"],
                    e["vtokens_raw"], (e.get("fee_bps") or 0) + (e.get("creator_fee_bps") or 0),
                    jup, payer == e["user"],
                ))
    times.sort()
    gaps = [(a, b) for a, b in zip(times, times[1:]) if b - a > GAP_MS]
    span = (times[0], times[-1]) if times else None
    return path, span, gaps, creates, rows


def main():
    jobs = list(chunks())
    print(f"{len(jobs)} chunks", flush=True)
    mints = defaultdict(lambda: {"creator": None, "create_slot": None, "create_ms": None, "rows": []})
    spans, gaps = defaultdict(list), []
    seen = set()
    with Pool(18) as pool:
        for n, (path, span, g, creates, rows) in enumerate(pool.imap_unordered(work, jobs), 1):
            if span:
                spans[path].append(span)
            gaps.extend(g)
            for mint, creator, slot, idx, ms in creates:
                m = mints[mint]
                if m["create_slot"] is None or slot < m["create_slot"]:
                    m.update(creator=creator, create_slot=slot, create_idx=idx, create_ms=ms)
            for r in rows:
                key = (r[5], r[3], r[0])
                if key in seen:
                    continue
                seen.add(key)
                mints[r[0]]["rows"].append(r[1:])
            if n % 10 == 0:
                print(f"{n}/{len(jobs)} chunks, {len(mints)} mints", flush=True)
    for m in mints.values():
        m["rows"].sort(key=lambda r: (r[0], r[1], r[2]))
    coverage = sorted((min(s[0] for s in v), max(s[1] for s in v)) for v in spans.values())
    with gzip.open(OUT, "wb", compresslevel=3) as fp:
        pickle.dump({"coverage": coverage, "gaps": sorted(gaps), "mints": dict(mints)}, fp, protocol=5)
    print("mints", len(mints), "with create", sum(m["create_slot"] is not None for m in mints.values()))
    print("rows", sum(len(m["rows"]) for m in mints.values()))
    print("coverage segments", coverage)
    print("gaps>3s inside files", len(gaps))


if __name__ == "__main__":
    main()
