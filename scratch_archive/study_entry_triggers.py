import urllib.request
import json
import base64
import struct
import time

RPC = "https://mainnet.helius-rpc.com/?api-key=1ce358dd-cb6b-4354-9073-2147d7f35d58"

# Load KOL wallets
kol_wallets = {}
try:
    with open("kol_wallets.txt") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                parts = line.split("#")
                addr = parts[0].strip()
                name = parts[1].strip() if len(parts) > 1 else "KOL"
                kol_wallets[addr] = name
except Exception:
    pass

# Load the 22 tracked bots
tracked_bots = {
    "C4JRuZx3nAFGqJ8ZcYuwWhRGxL4N9ZwpsErjfhGqxxAf": "broke bot lol",
    "97jv9pjCf5D7VUZEyj6XnXBC5JF23Vsagc3bvSF6GRmL": "Cbot7",
    "nya666pQkP3PzWxi7JngU3rRMHuc7zbLK8c8wxQ4qpT": "russianbot",
    "85YwZaQa8SATizDxCwZ8z5EpdpLvy5Ub9zp1a3TkaHrL": "snipebot",
    "niggerd597QYedtvjQDVHZTCCGyJrwHNm2i49dkm5zS": "nbot",
    "AURAEDwoBtWnqkzUfGQ2CVF53BFU5NoTCt5MeL4C1wPu": "bot12",
    "4BHBSZA96XCaepYLvmteV6wLqKTqJPyfkME941X5PqHP": "bot",
    "8TPkrBcRayR3EJzaxXb87XGmJs9k1U8tdc7wX3GJgw1z": "1 sol bot",
    "4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3": "Snippebot",
    "8dtx2tr4TuJsYpri2suggFu1pg3DVjFLBBVmhtDy1MEF": "Bottom Bidder",
    "J3gZFpvsCsmA5zwqXgUpyqNLBoGGcJzmnfRwbHFR6KfU": "bottty",
    "bcnzSs3F6F3MG7utvEQHpd8A53nRBM8ZM4TfEs2Zmcp": "bottimus",
    "EaaCfVxVboPx1wht6Xvqcmq6LVhDW5ouyCBMiu2tafBG": "asdasd",
    "7ovu7sqYQGcHwUnLfVfwjCx5VGBCiJmBrsrBv2ab1Ltx": "bot",
    "BuekUk3YMmm7Agnb4ni1qMCmShVpeBTdQZYNyihyzr7u": "insane bot",
    "5DC3tMyFSXeujJn9KWnh1MkM8QCgXXm2tDEGpjhcwFck": "bot",
    "Fhbh1DTUDKt6qu9zVg8Q5VgnZa1WWWbxBxG6pCoJoggA": "boooooot",
    "9QbcuwBLEDXKgJLx6rJKMnYfeXmTovBPzUmkAu9s4a19": "cbot14",
    "2gnL2LdN2mSyk6Y7oBrNinZoEi11F2SdhiHCYF1R3vGY": "Botty",
    "72MUPELEkUU5riN8ZPdfVssXWC6L8EViZ9FybHEmqT6J": "1sol bot",
    "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq": "bot",
    "94iQuYjVgTwGXxtM7ywfpzfLvx3gN4oQRuc9osRE2pEm": "Bot"
}

def rpc(method, params):
    try:
        req = urllib.request.Request(RPC, headers={"Content-Type": "application/json"}, data=json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params}).encode())
        res = json.loads(urllib.request.urlopen(req).read().decode())
        return res.get("result")
    except Exception as e:
        return None

def analyze_token_trigger(mint, buyer_bot_addr, buy_sig):
    print(f"\n==========================================================================")
    print(f"ANALYZING ENTRY TRIGGER ON TOKEN: {mint}")
    print(f"Buyer bot: {tracked_bots.get(buyer_bot_addr, buyer_bot_addr)}")
    print(f"Buy Tx: {buy_sig}")
    print(f"==========================================================================")
    
    # Get all signatures on the token
    sigs = rpc("getSignaturesForAddress", [mint, {"limit": 100}])
    if not sigs:
        print("Could not fetch signatures.")
        return
    
    sigs.reverse() # chronological order (oldest to newest)
    
    # Locate creation and bot buy index
    creation_time = sigs[0].get("blockTime")
    bot_idx = -1
    for i, s in enumerate(sigs):
        if s["signature"] == buy_sig:
            bot_idx = i
            break
    
    if bot_idx == -1:
        # maybe signature wasn't in the top 100 or matching
        for i, s in enumerate(sigs):
            if buyer_bot_addr in str(s):
                bot_idx = i
                break
    
    print(f"Total token transactions to date: {len(sigs)}")
    print(f"Bot buy position in sequence: tx #{bot_idx + 1} of {len(sigs)}")
    if bot_idx >= 0:
        bot_time = sigs[bot_idx].get("blockTime")
        age_seconds = bot_time - creation_time if (bot_time and creation_time) else "unknown"
        print(f"Token age at bot buy: {age_seconds} seconds")
    
    # Now inspect the 5 transactions immediately BEFORE the bot buy
    start_idx = max(0, bot_idx - 6)
    window = sigs[start_idx : bot_idx + 1]
    
    print(f"\n--- SEQUENCE OF TRANSACTIONS BEFORE & AT BOT BUY ---")
    reserves_history = []
    
    for idx_in_window, s_meta in enumerate(window):
        sig = s_meta["signature"]
        tx = rpc("getTransaction", [sig, {"encoding":"jsonParsed", "maxSupportedTransactionVersion":0}])
        if not tx: continue
        meta = tx.get("meta", {})
        tx_msg = tx.get("transaction", {}).get("message", {})
        accs = [a.get("pubkey") if isinstance(a, dict) else a for a in tx_msg.get("accountKeys", [])]
        fee_payer = accs[0] if accs else "unknown"
        
        # Identity check
        tag = ""
        if fee_payer in tracked_bots:
            tag = f"[TRACKED BOT: {tracked_bots[fee_payer]}]"
        elif fee_payer in kol_wallets:
            tag = f"[KOL: {kol_wallets[fee_payer]}]"
        elif fee_payer == buyer_bot_addr:
            tag = "[TARGET BOT ENTRY]"
        
        # Check action & reserves from log
        action = "OTHER"
        sol_amt = 0.0
        rsol = None
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
        
        reserves_history.append(rsol)
        is_target = "===> " if sig == buy_sig else "     "
        print(f"{is_target}tx #{start_idx + idx_in_window + 1} | {action:4} {sol_amt:7.3f} SOL | Curve: {str(rsol):8} SOL | User: {fee_payer[:8]}... {tag}")

# Lets analyze Botty buy on BnPfnjQFVZpPgwSuNLJj1mJ3XRUSAzBufYWFafropump
analyze_token_trigger(
    mint="BnPfnjQFVZpPgwSuNLJj1mJ3XRUSAzBufYWFafropump",
    buyer_bot_addr="2gnL2LdN2mSyk6Y7oBrNinZoEi11F2SdhiHCYF1R3vGY",
    buy_sig="2BHs4qi9fRtQG53tPjzYY86Wao7bAKqryfVFsBGfLDwyoBeTo4Z4KK3oqZtwJohKEJMZzRx47Dtv65f5xMYZ7K42"
)
