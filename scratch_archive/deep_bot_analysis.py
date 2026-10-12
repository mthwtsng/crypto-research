import urllib.request
import json
import time

RPC = "https://mainnet.helius-rpc.com/?api-key=1ce358dd-cb6b-4354-9073-2147d7f35d58"

JITO_TIP_ACCOUNTS = {
    "96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5",
    "HFqU5x63VTxvQssQpnMgUBrt2zgQHqQauBfgzWnTXTX",
    "Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY",
    "ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49",
    "DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh",
    "ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt",
    "DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL",
    "3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT",
}

bots_to_study = [
    {"addr": "4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3", "name": "Snippebot (642 SOL)"},
    {"addr": "4BHBSZA96XCaepYLvmteV6wLqKTqJPyfkME941X5PqHP", "name": "bot (209 SOL)"},
    {"addr": "nya666pQkP3PzWxi7JngU3rRMHuc7zbLK8c8wxQ4qpT", "name": "russianbot (149 SOL)"},
    {"addr": "BuekUk3YMmm7Agnb4ni1qMCmShVpeBTdQZYNyihyzr7u", "name": "insane bot (76 SOL)"},
    {"addr": "8dtx2tr4TuJsYpri2suggFu1pg3DVjFLBBVmhtDy1MEF", "name": "Bottom Bidder (58 SOL)"},
    {"addr": "bcnzSs3F6F3MG7utvEQHpd8A53nRBM8ZM4TfEs2Zmcp", "name": "bottimus (43 SOL)"},
    {"addr": "72MUPELEkUU5riN8ZPdfVssXWC6L8EViZ9FybHEmqT6J", "name": "1sol bot (22 SOL)"},
    {"addr": "2gnL2LdN2mSyk6Y7oBrNinZoEi11F2SdhiHCYF1R3vGY", "name": "Botty (21 SOL)"},
    {"addr": "J3gZFpvsCsmA5zwqXgUpyqNLBoGGcJzmnfRwbHFR6KfU", "name": "bottty (15 SOL)"},
    {"addr": "8TPkrBcRayR3EJzaxXb87XGmJs9k1U8tdc7wX3GJgw1z", "name": "1 sol bot (14 SOL)"},
]

def rpc(method, params):
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode("utf-8")
    req = urllib.request.Request(RPC, headers={"Content-Type": "application/json"}, data=payload)
    resp = urllib.request.urlopen(req)
    return json.loads(resp.read().decode("utf-8")).get("result")

for bot in bots_to_study:
    addr = bot["addr"]
    name = bot["name"]
    print(f"\n=======================================================")
    print(f"ANALYZING: {name} | {addr}")
    print(f"=======================================================")
    
    sigs = rpc("getSignaturesForAddress", [addr, {"limit": 15}])
    if not sigs:
        print("  No signatures found.")
        continue
    
    successful_sigs = [s for s in sigs if s.get("err") is None]
    failed_sigs = [s for s in sigs if s.get("err") is not None]
    print(f"  Recent 15 tx: {len(successful_sigs)} success, {len(failed_sigs)} failed")
    
    # Analyze the transactions
    trades = []
    venues = set()
    jito_count = 0
    tips = []
    
    # Sample up to 8 recent transactions
    for s_meta in sigs[:8]:
        sig = s_meta["signature"]
        tx = rpc("getTransaction", [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}])
        if not tx:
            continue
        
        meta = tx.get("meta", {})
        tx_msg = tx.get("transaction", {}).get("message", {})
        accounts = [a.get("pubkey") if isinstance(a, dict) else a for a in tx_msg.get("accountKeys", [])]
        
        # Check Jito tips
        has_jito = any(acc in JITO_TIP_ACCOUNTS for acc in accounts)
        if has_jito:
            jito_count += 1
            # Check lamports transferred to Jito
            # postBalances vs preBalances
            pass
        
        fee_sol = meta.get("fee", 0) / 1e9
        
        # Check logs for programs and actions
        logs = meta.get("logMessages", [])
        is_pump = any("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P" in l for l in logs)
        is_raydium = any("675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8" in l or "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK" in l for l in logs)
        is_pumpswap = any("pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ" in l for l in logs)
        
        action = "OTHER"
        mint = None
        sol_change = 0.0
        
        # Pre vs post SOL balance for the bot wallet
        try:
            bot_idx = accounts.index(addr)
            pre_bal = meta.get("preBalances", [])[bot_idx] / 1e9
            post_bal = meta.get("postBalances", [])[bot_idx] / 1e9
            sol_change = post_bal - pre_bal
        except Exception:
            pass
        
        # Pre vs post token balances
        token_deltas = {}
        for pb in meta.get("preTokenBalances", []):
            if pb.get("owner") == addr:
                m = pb.get("mint")
                amt = float(pb.get("uiTokenAmount", {}).get("uiAmount") or 0)
                token_deltas[m] = token_deltas.get(m, 0.0) - amt
        for pb in meta.get("postTokenBalances", []):
            if pb.get("owner") == addr:
                m = pb.get("mint")
                amt = float(pb.get("uiTokenAmount", {}).get("uiAmount") or 0)
                token_deltas[m] = token_deltas.get(m, 0.0) + amt
        
        # Find traded mint
        traded_tokens = [m for m, delta in token_deltas.items() if abs(delta) > 0]
        if traded_tokens:
            mint = traded_tokens[0]
            token_delta = token_deltas[mint]
            if token_delta > 0:
                action = f"BUY (delta=+{token_delta:,.0f})"
            else:
                action = f"SELL (delta={token_delta:,.0f})"
        else:
            # Check logs
            for l in logs:
                if "Instruction: Buy" in l: action = "BUY"
                elif "Instruction: Sell" in l: action = "SELL"
        
        venue_str = "Pump.fun" if is_pump else ("Raydium" if is_raydium else "Other")
        venues.add(venue_str)
        
        err_str = "FAIL" if s_meta.get("err") else "OK"
        print(f"    [{err_str}] {s_meta.get('blockTime')} | {venue_str:8} | {action:25} | SOL change: {sol_change:+.4f} | Fee: {fee_sol:.5f} SOL | Sig: {sig[:12]}...")
    
    print(f"  Summary for {name}:")
    print(f"    Venues: {list(venues)}")
    print(f"    Jito Tip Bundle Usage: {jito_count}/8 inspected txs")
