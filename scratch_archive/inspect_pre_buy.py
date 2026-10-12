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
    "8TPkrBcRayR3EJzaxXb87XGmJs9k1U8tdc7wX3GJgw1z": "1 sol bot",
    "bcnzSs3F6F3MG7utvEQHpd8A53nRBM8ZM4TfEs2Zmcp": "bottimus",
}

mint = "BnPfnjQFVZpPgwSuNLJj1mJ3XRUSAzBufYWFafropump"
buy_sig = "2BHs4qi9fRtQG53tPjzYY86Wao7bAKqryfVFsBGfLDwyoBeTo4Z4KK3oqZtwJohKEJMZzRx47Dtv65f5xMYZ7K42"

def rpc(method, params):
    for attempt in range(3):
        try:
            req = urllib.request.Request(RPC, headers={"Content-Type": "application/json"}, data=json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params}).encode())
            res = json.loads(urllib.request.urlopen(req).read().decode())
            if "result" in res:
                return res["result"]
            time.sleep(0.5)
        except Exception:
            time.sleep(0.5)
    return None

# Fetch sigs before buy_sig
res = rpc("getSignaturesForAddress", [mint, {"before": buy_sig, "limit": 10}])
if not res:
    print("Could not fetch signatures.")
    exit(1)

res.reverse()
res.append({"signature": buy_sig})

print(f"{'SLOT':10} | {'TIME':10} | {'ACTION':4} | {'SOL':7} | {'CURVE RSOL':10} | {'SIGNER':44} | {'IDENTITY'}")
print("-" * 115)

for s in res:
    sig = s["signature"]
    tx = rpc("getTransaction", [sig, {"encoding":"jsonParsed", "maxSupportedTransactionVersion":0}])
    if not tx:
        print(f"Failed to fetch tx: {sig[:20]}")
        continue
    meta = tx.get("meta", {})
    slot = tx.get("slot", 0)
    bt = tx.get("blockTime", 0)
    tx_msg = tx.get("transaction", {}).get("message", {})
    accs = [a.get("pubkey") if isinstance(a, dict) else a for a in tx_msg.get("accountKeys", [])]
    signer = accs[0] if accs else "unknown"
    
    identity = ""
    if signer in kol:
        identity = f"*** KOL: {kol[signer]} ***"
    elif signer in tracked:
        identity = f"[TRACKED BOT: {tracked[signer]}]"
    
    # decode event
    action = "OTHER"
    sol_amt = 0.0
    rsol = 0.0
    for l in meta.get("logMessages", []):
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
    
    marker = "===> " if sig == buy_sig else "     "
    print(f"{marker}{slot} | {bt} | {action:4} | {sol_amt:7.3f} | {rsol:10.3f} | {signer:44} | {identity}")
    time.sleep(0.1)
