#!/usr/bin/env python3
"""Usage: fetch_coin.py <mint>. Fetch the full bonding-curve history for one Pump.fun mint and decode TradeEvents.

Outputs (in this directory):
  signatures.json   all signatures on the curve PDA (with err)
  txs.jsonl         compact per-successful-tx records (decoded trades, programs, balance deltas)
  failed_sample.jsonl  a few fetched failed txs
"""
import base64, hashlib, json, os, sys, time, threading, random
from concurrent.futures import ThreadPoolExecutor
import requests

MINT = sys.argv[1]
HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "coins", MINT)
os.makedirs(HERE, exist_ok=True)
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
ENDPOINTS = [
    "https://rpc.shyft.to?api_key=owfc3zuSXH37YG0U",
    "https://rpc.solami.dev/sol?api_key=sk_7hPGeJuMS_ASwhlvlxKBn_6N5hm8I4bKSP8xyaRFSXI",
]
if os.environ.get("ONLY_EP"):
    ENDPOINTS = [ENDPOINTS[int(os.environ["ONLY_EP"])]]

# ---------------- base58 / PDA ----------------
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

def b58d(s):
    n = 0
    for c in s:
        n = n * 58 + B58.index(c)
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    pad = len(s) - len(s.lstrip("1"))
    return b"\x00" * pad + raw

def b58e(b):
    n = int.from_bytes(b, "big")
    out = ""
    while n:
        n, r = divmod(n, 58)
        out = B58[r] + out
    pad = len(b) - len(b.lstrip(b"\x00"))
    return "1" * pad + out

P = 2**255 - 19
D = (-121665 * pow(121666, P - 2, P)) % P

def on_curve(b):
    y = int.from_bytes(b, "little") & ((1 << 255) - 1)
    if y >= P:
        return False
    y2 = y * y % P
    u = (y2 - 1) % P
    v = (D * y2 + 1) % P
    x2 = u * pow(v, P - 2, P) % P
    if x2 == 0:
        return True
    return pow(x2, (P - 1) // 2, P) == 1

def find_pda(seeds, program):
    pid = b58d(program)
    for bump in range(255, -1, -1):
        h = hashlib.sha256(b"".join(seeds) + bytes([bump]) + pid + b"ProgramDerivedAddress").digest()
        if not on_curve(h):
            return b58e(h), bump
    raise RuntimeError("no pda")

# ---------------- RPC ----------------
_sem = [threading.Semaphore(4) for _ in ENDPOINTS]
_rr = [0]
_rr_lock = threading.Lock()
_sess = threading.local()

def sess():
    if not hasattr(_sess, "s"):
        _sess.s = requests.Session()
    return _sess.s

def rpc(method, params, tries=8):
    for attempt in range(tries):
        with _rr_lock:
            i = _rr[0] % len(ENDPOINTS)
            _rr[0] += 1
        with _sem[i]:
            try:
                r = sess().post(ENDPOINTS[i], json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=40)
                if r.status_code == 429 or r.status_code >= 500:
                    raise RuntimeError(f"http {r.status_code}")
                j = r.json()
                if "error" in j:
                    raise RuntimeError(str(j["error"])[:200])
                return j["result"]
            except Exception as e:
                last = e
        time.sleep(min(8, 0.4 * 2 ** attempt) + random.random() * 0.3)
    raise RuntimeError(f"{method} failed: {last}")

# ---------------- decoding ----------------
EVENT_CPI_TAG = bytes.fromhex("e445a52e51cb9a1d")
TRADE_DISC = hashlib.sha256(b"event:TradeEvent").digest()[:8]
CREATE_DISC = hashlib.sha256(b"event:CreateEvent").digest()[:8]
COMPLETE_DISC = hashlib.sha256(b"event:CompleteEvent").digest()[:8]

def u64(b, o):
    return int.from_bytes(b[o:o + 8], "little")

def decode_trade(b):
    # b starts at the TradeEvent discriminator
    o = 8
    ev = {"mint": b58e(b[o:o + 32])}; o += 32
    ev["sol_amount"] = u64(b, o); o += 8
    ev["token_amount"] = u64(b, o); o += 8
    ev["is_buy"] = b[o] == 1; o += 1
    ev["user"] = b58e(b[o:o + 32]); o += 32
    ev["timestamp"] = int.from_bytes(b[o:o + 8], "little", signed=True); o += 8
    ev["v_sol"] = u64(b, o); o += 8
    ev["v_tok"] = u64(b, o); o += 8
    ev["r_sol"] = u64(b, o); o += 8
    ev["r_tok"] = u64(b, o); o += 8
    try:
        ev["fee_recipient"] = b58e(b[o:o + 32]); o += 32
        ev["fee_bps"] = u64(b, o); o += 8
        ev["fee"] = u64(b, o); o += 8
        ev["creator"] = b58e(b[o:o + 32]); o += 32
        ev["creator_fee_bps"] = u64(b, o); o += 8
        ev["creator_fee"] = u64(b, o); o += 8
    except Exception:
        pass
    return ev

def decode_create(b):
    o = 8
    out = {}
    for k in ("name", "symbol", "uri"):
        n = int.from_bytes(b[o:o + 4], "little"); o += 4
        out[k] = b[o:o + n].decode("utf-8", "replace"); o += n
    for k in ("mint", "bonding_curve", "user"):
        out[k] = b58e(b[o:o + 32]); o += 32
    if len(b) >= o + 32:
        out["creator"] = b58e(b[o:o + 32])
    return out

def compact(sig, tx):
    meta = tx["meta"]
    msg = tx["transaction"]["message"]
    keys = list(msg["accountKeys"])
    la = meta.get("loadedAddresses") or {}
    keys += la.get("writable", []) + la.get("readonly", [])
    rec = {"sig": sig, "slot": tx["slot"], "blockTime": tx.get("blockTime"), "err": meta.get("err"),
           "fee": meta.get("fee"), "signer": keys[0], "trades": [], "create": None, "complete": False}
    progs = set()
    for ix in msg["instructions"]:
        progs.add(keys[ix["programIdIndex"]])
    top_progs = sorted(progs)
    events = []
    for grp in meta.get("innerInstructions") or []:
        for ix in grp["instructions"]:
            pid = keys[ix["programIdIndex"]]
            progs.add(pid)
            if pid != PUMP:
                continue
            try:
                d = b58d(ix["data"])
            except Exception:
                continue
            if d[:8] == EVENT_CPI_TAG:
                body = d[8:]
                if body[:8] == TRADE_DISC:
                    events.append(("trade", grp["index"], decode_trade(body)))
                elif body[:8] == CREATE_DISC:
                    rec["create"] = decode_create(body)
                elif body[:8] == COMPLETE_DISC:
                    rec["complete"] = True
    if not events:  # fallback: program data logs
        for line in meta.get("logMessages") or []:
            if line.startswith("Program data: "):
                try:
                    d = base64.b64decode(line[14:])
                except Exception:
                    continue
                if d[:8] == TRADE_DISC:
                    events.append(("trade", -1, decode_trade(d)))
                elif d[:8] == CREATE_DISC and rec["create"] is None:
                    rec["create"] = decode_create(d)
                elif d[:8] == COMPLETE_DISC:
                    rec["complete"] = True
    rec["trades"] = [e for _, _, e in events if e["mint"] == MINT]
    rec["top_programs"] = top_progs
    rec["programs"] = sorted(progs)
    # SOL deltas for trade users (net of everything in the tx incl. fees/tips)
    users = {t["user"] for t in rec["trades"]} | {keys[0]}
    deltas = {}
    for u in users:
        if u in keys:
            i = keys.index(u)
            deltas[u] = meta["postBalances"][i] - meta["preBalances"][i]
    rec["sol_deltas"] = deltas
    # token balance changes for the mint by owner
    tb = {}
    for side, arr in (("pre", meta.get("preTokenBalances") or []), ("post", meta.get("postTokenBalances") or [])):
        for x in arr:
            if x.get("mint") == MINT:
                o = x.get("owner")
                tb.setdefault(o, {"pre": 0, "post": 0})[side] += int(x["uiTokenAmount"]["amount"])
    rec["token_deltas"] = {o: v["post"] - v["pre"] for o, v in tb.items() if v["post"] != v["pre"]}
    rec["n_keys"] = len(keys)
    return rec

def get_tx(sig):
    return rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])

def main():
    curve, bump = find_pda([b"bonding-curve", b58d(MINT)], PUMP)
    print("curve", curve, bump, flush=True)
    sigp = os.path.join(HERE, "signatures.json")
    if os.path.exists(sigp):
        sigs = json.load(open(sigp))["signatures"]
    else:
        sigs, before = [], None
        while True:
            opts = {"limit": 1000, "commitment": "confirmed"}
            if before:
                opts["before"] = before
            page = rpc("getSignaturesForAddress", [curve, opts])
            sigs += page
            print("sigs", len(sigs), page[-1]["slot"] if page else None, flush=True)
            if len(page) < 1000:
                break
            before = page[-1]["signature"]
        json.dump({"curve": curve, "bump": bump, "signatures": sigs}, open(sigp, "w"))
    ok = [s["signature"] for s in sigs if s["err"] is None]
    bad = [s["signature"] for s in sigs if s["err"] is not None]
    print(f"total {len(sigs)} ok {len(ok)} failed {len(bad)}", flush=True)

    outp = os.path.join(HERE, "txs.jsonl")
    done = set()
    if os.path.exists(outp):
        for line in open(outp):
            done.add(json.loads(line)["sig"])
    todo = [s for s in ok if s not in done]
    lock = threading.Lock()
    fo = open(outp, "a")
    cnt = [0]

    def work(sig):
        try:
            tx = get_tx(sig)
        except Exception as e:
            print("ERR", sig, e, flush=True)
            return
        if tx is None:
            print("NULL", sig, flush=True)
            return
        rec = compact(sig, tx)
        with lock:
            fo.write(json.dumps(rec) + "\n")
            cnt[0] += 1
            if cnt[0] % 200 == 0:
                fo.flush()
                print("fetched", cnt[0], "/", len(todo), flush=True)

    with ThreadPoolExecutor(8) as ex:
        list(ex.map(work, todo))
    fo.close()

    fp = os.path.join(HERE, "failed_sample.jsonl")
    if not os.path.exists(fp) and bad:
        samp = random.Random(1).sample(bad, min(12, len(bad)))
        with open(fp, "w") as f:
            for s in samp:
                tx = get_tx(s)
                if tx:
                    rec = compact(s, tx)
                    rec["logs_tail"] = (tx["meta"].get("logMessages") or [])[-6:]
                    f.write(json.dumps(rec) + "\n")

if __name__ == "__main__":
    main()
