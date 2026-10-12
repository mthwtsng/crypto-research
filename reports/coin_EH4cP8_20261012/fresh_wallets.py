#!/usr/bin/env python3
"""Sampled wallet-age / funding-parent check for suspicious and early wallets.

For each wallet: getSignaturesForAddress(limit 1000). If < 1000 returned, the
oldest is the wallet's first-ever tx; fetch it and find the largest SOL sender.
"""
import json, os, sys, datetime
from fetch import rpc

HERE = os.path.dirname(os.path.abspath(__file__))
COIN_CREATE_BT = 1790712411
REVIVAL_BT = 1791770979

WALLETS = {
    # micro-bumpers / lockstep clusters
    "6FZ1RasKHCPa9DnNYzg2v6ppDBhMigPM9X3L5fUY8kab": "micro bumper 0.000978 x124 (term router)",
    "UuAvcGQZWmo9ATGx2wzLi7tYX9DbGV3V3xb6nNxGyvH": "ignition-slot buyer, same router as 6FZ1Ra",
    "64Eo13uodbdMyrXqsUK9Hmazj5v2vHcURtDMS9R3z2UL": "FLASHX lockstep triad",
    "GT16BVecjpFvDJPnctZM499aDYNEsL2iAu83oeoBjghr": "FLASHX lockstep triad",
    "moeypiG1S8jepY2hCtP5RC6iCcpHvdgkagNPKiFWxN6": "FLASHX lockstep triad",
    "HzjDm1fiMha9UguXGWKKSdRdu6H9s5k6fWBQtKPhH5ni": "micro bumper 0.009877 x26",
    "3JQvkiF2GKfca3ggMPRwTHmzvnj6emReuSFwSrBBonp5": "late micro bumper via FHpcNSe6 relay",
    "4qzJLi17Sh9SgKvUPXDL2WMuiJpNJGB1Pd9cjJgN83Ei": "micro bumper GMGN",
    "H8URrcUAopozaDLYAZVUGYj83DzSRgWoRH1tnfGiAAAm": "launch micro bumper/churner x48",
    # revival leaders / first-wave
    "DGma4Uxm9JS6yLNdgYaxsZhwk2nxrRGMfMt5buXbiFCm": "revival first buyer (leader)",
    "FjpP8RjP99ozeqPvTidadjKgh9gDGbZEQLE7SLkByobq": "revival wave-1",
    "CNBuuRcP2vFSoS6pmBN1wQYan9UPJ8CXPyJyLTNWHpj": "revival wave-1",
    "8eftoRDpRcjkrT6VZ1HPSB1mJfE9SdgkNKqid58F5XKi": "revival wave-1 (0.083 repeat)",
    "6Qt8a3Y6B4nekSRQ1p2e5yqP5bSCbE6HzUTdWwdfYXmR": "revival wave-1",
    "3QJ1Dze6YxH1g3YNzzrzcvbFS9spaTxjiJZGqRCmFMD2": "main-run first buyer 05:09:08",
    "GGBJfS": None,  # resolved below
    "CHCLtC": None,
}

def full(prefix):
    for l in open(os.path.join(HERE, "tape.jsonl")):
        u = json.loads(l)["user"]
        if u.startswith(prefix):
            return u

def utc(bt):
    return datetime.datetime.fromtimestamp(bt, datetime.UTC).strftime("%Y-%m-%d %H:%M:%S") if bt else None

def funder(sig, wallet):
    tx = rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
    if not tx:
        return None
    msg = tx["transaction"]["message"]
    keys = list(msg["accountKeys"])
    la = tx["meta"].get("loadedAddresses") or {}
    keys += la.get("writable", []) + la.get("readonly", [])
    d = [post - pre for pre, post in zip(tx["meta"]["preBalances"], tx["meta"]["postBalances"])]
    gain = d[keys.index(wallet)] / 1e9 if wallet in keys else None
    snd = min(range(len(d)), key=lambda i: d[i])
    return {"first_tx_signer": keys[0], "largest_sender": keys[snd], "sender_delta": d[snd] / 1e9, "wallet_gain": gain}

def main():
    res = {}
    for w, note in list(WALLETS.items()):
        if note is None:
            fw = full(w)
            note = {"GGBJfS": "2.963 SOL ignition-slot buyer, then laddered sells", "CHCLtC": "main-run 3rd buyer (FLASHX)"}[w]
            w = fw
        sigs = rpc("getSignaturesForAddress", [w, {"limit": 1000}])
        r = {"note": note, "n_sigs_le1000": len(sigs), "newest": utc(sigs[0]["blockTime"]) if sigs else None,
             "oldest_seen": utc(sigs[-1]["blockTime"]) if sigs else None, "history_complete": len(sigs) < 1000}
        if sigs and len(sigs) < 1000:
            r["first_tx_hours_before_revival"] = round((REVIVAL_BT - sigs[-1]["blockTime"]) / 3600, 2)
            try:
                r["funding"] = funder(sigs[-1]["signature"], w)
            except Exception as e:
                r["funding"] = str(e)
        res[w] = r
        print(w[:6], json.dumps(r), flush=True)
    json.dump(res, open(os.path.join(HERE, "fresh_wallets.json"), "w"), indent=1)

if __name__ == "__main__":
    main()
