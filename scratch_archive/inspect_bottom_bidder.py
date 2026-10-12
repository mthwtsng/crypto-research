import urllib.request
import json
import base64
import struct
import time

RPC = "https://mainnet.helius-rpc.com/?api-key=1ce358dd-cb6b-4354-9073-2147d7f35d58"

# Load KOL and tracked bots
kol = {}
with open("kol_wallets.txt") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#"):
            parts = line.split("#")
            kol[parts[0].strip()] = parts[1].strip() if len(parts) > 1 else "KOL"

tracked = {
    "2gnL2LdN2mSyk6Y7oBrNinZoEi11F2SdhiHCYF1R3vGY": "Botty",
    "72MUPELEkUU5riN8ZPdfVssXWC6L8EViZ9FybHEmqT6J": "1sol bot",
    "nya666pQkP3PzWxi7JngU3rRMHuc7zbLK8c8wxQ4qpT": "russianbot",
    "4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3": "Snippebot",
    "8dtx2tr4TuJsYpri2suggFu1pg3DVjFLBBVmhtDy1MEF": "Bottom Bidder",
}

def rpc(method, params):
    try:
        req = urllib.request.Request(RPC, headers={"Content-Type": "application/json"}, data=json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params}).encode())
        res = json.loads(urllib.request.urlopen(req).read().decode())
        return res.get("result")
    except Exception:
        return None

# Find the buy signature for Bottom Bidder on 7g4zMAo1...
sigs = rpc("getSignaturesForAddress", ["8dtx2tr4TuJsYpri2suggFu1pg3DVjFLBBVmhtDy1MEF", {"limit": 20}])
target_sig = None
for s in sigs:
    if s["signature"].startswith("2Frq5jXq"):
        target_sig = s["signature"]
        break

print(f"Target Bottom Bidder Buy Sig: {target_sig}")
tx = rpc("getTransaction", [target_sig, {"encoding":"jsonParsed", "maxSupportedTransactionVersion":0}])
meta = tx["meta"]
slot = tx["slot"]
mint = None
for b in meta["postTokenBalances"]:
    if b["owner"] == "8dtx2tr4TuJsYpri2suggFu1pg3DVjFLBBVmhtDy1MEF":
        mint = b["mint"]
        break
print(f"Mint: {mint}, Slot: {slot}")

# Now get transactions before this on the mint
pre_sigs = rpc("getSignaturesForAddress", [mint, {"before": target_sig, "limit": 6}])
pre_sigs.reverse()
pre_sigs.append({"signature": target_sig})

print(f"\n{'SLOT':10} | {'ACTION':4} | {'SOL':7} | {'CURVE RSOL':10} | {'SIGNER':44} | {'IDENTITY'}")
print("-" * 110)

for s in pre_sigs:
    sig = s["signature"]
    t = rpc("getTransaction", [sig, {"encoding":"jsonParsed", "maxSupportedTransactionVersion":0}])
    if not t: continue
    m = t.get("meta", {})
    t_slot = t.get("slot", 0)
    tx_msg = t.get("transaction", {}).get("message", {})
    accs = [a.get("pubkey") if isinstance(a, dict) else a for a in tx_msg.get("accountKeys", [])]
    signer = accs[0] if accs else "unknown"
    
    identity = ""
    if signer in kol:
        identity = f"*** KOL: {kol[signer]} ***"
    elif signer in tracked:
        identity = f"[TRACKED BOT: {tracked[signer]}]"
    
    action = "OTHER"
    sol_amt = 0.0
    rsol = 0.0
    for l in m.get("logMessages", []):
        if "Program data:" in l:
            try:
                b64 = l.split("Program data: ")[1].strip()
                raw = base64.b64decode(b64)
                d = raw[8:]
                sol_raw, tokens_raw, is_buy = struct.unpack("<QQ?", d[32:32+17])
                ts, vsol, vtokens, rsol_raw, rtokens = struct.unpack("<qQQQQ", d[32+17+32:32+17+32+40])
                rsol = rsol_raw / 1e9
                sol_amt = sol_raw / 1e9
                action = "BUY" if is_buy else "SELL"
            except Exception:
                pass
    
    marker = "===> " if sig == target_sig else "     "
    print(f"{marker}{t_slot} | {action:4} | {sol_amt:7.3f} | {rsol:10.3f} | {signer:44} | {identity}")
    time.sleep(0.1)
