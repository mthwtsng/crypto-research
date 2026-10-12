import urllib.request
import json
import base64
import struct
import time

RPC = "https://mainnet.helius-rpc.com/?api-key=1ce358dd-cb6b-4354-9073-2147d7f35d58"

def rpc(method, params):
    try:
        req = urllib.request.Request(RPC, headers={"Content-Type": "application/json"}, data=json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params}).encode())
        res = json.loads(urllib.request.urlopen(req).read().decode())
        return res.get("result")
    except Exception as e:
        return None

target_bots = [
    ("4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3", "Snippebot (642 SOL)"),
    ("nya666pQkP3PzWxi7JngU3rRMHuc7zbLK8c8wxQ4qpT", "russianbot (149 SOL)"),
    ("4BHBSZA96XCaepYLvmteV6wLqKTqJPyfkME941X5PqHP", "bot (209 SOL)"),
    ("72MUPELEkUU5riN8ZPdfVssXWC6L8EViZ9FybHEmqT6J", "1sol bot (22 SOL)"),
    ("2gnL2LdN2mSyk6Y7oBrNinZoEi11F2SdhiHCYF1R3vGY", "Botty (21 SOL)"),
    ("8dtx2tr4TuJsYpri2suggFu1pg3DVjFLBBVmhtDy1MEF", "Bottom Bidder (58 SOL)"),
    ("BuekUk3YMmm7Agnb4ni1qMCmShVpeBTdQZYNyihyzr7u", "insane bot (76 SOL)")
]

for addr, label in target_bots:
    print(f"\n==========================================")
    print(f"{label} ({addr})")
    print(f"==========================================")
    sigs = rpc("getSignaturesForAddress", [addr, {"limit": 30}])
    if not sigs:
        print("Could not get signatures")
        continue
    succ = [s for s in sigs if s.get("err") is None]
    fail = [s for s in sigs if s.get("err") is not None]
    print(f"Success: {len(succ)}, Fail: {len(fail)} (Fail rate: {len(fail)/len(sigs)*100:.1f}%)")
    
    # Analyze successful transactions
    for s in succ[:8]:
        sig = s["signature"]
        tx = rpc("getTransaction", [sig, {"encoding":"jsonParsed", "maxSupportedTransactionVersion":0}])
        if not tx: continue
        meta = tx.get("meta", {})
        fee = meta.get("fee", 0) / 1e9
        accs = [a.get("pubkey") if isinstance(a, dict) else a for a in tx.get("transaction", {}).get("message", {}).get("accountKeys", [])]
        try:
            idx = accs.index(addr)
            sol_chg = (meta.get("postBalances", [])[idx] - meta.get("preBalances", [])[idx]) / 1e9
        except Exception:
            sol_chg = 0.0
        
        # Check instructions
        action = "UNKNOWN"
        rsol = None
        for l in meta.get("logMessages", []):
            if "Instruction: Buy" in l: action = "BUY"
            elif "Instruction: Sell" in l: action = "SELL"
            if "Program data:" in l:
                try:
                    b64 = l.split("Program data: ")[1].strip()
                    raw = base64.b64decode(b64)
                    d = raw[8:]
                    sol_raw, tokens_raw, is_buy = struct.unpack("<QQ?", d[32:32+17])
                    ts, vsol, vtokens, rsol_raw, rtokens = struct.unpack("<qQQQQ", d[32+17+32:32+17+32+40])
                    rsol = rsol_raw / 1e9
                except Exception:
                    pass
        
        # Traded token
        post_tokens = meta.get("postTokenBalances", [])
        mints = set(b.get("mint") for b in post_tokens if b.get("owner") == addr)
        mint_str = list(mints)[0][:8] + "..." if mints else "N/A"
        rsol_str = f"curve={rsol:.2f} SOL" if rsol is not None else "curve=N/A"
        
        print(f"  {s.get('blockTime')} | {action:4} | {sol_chg:+8.4f} SOL | {rsol_str:16} | token: {mint_str} | sig: {sig[:16]}...")
    time.sleep(0.5)
