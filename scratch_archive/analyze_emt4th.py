import os
import json
import time
import base64
import struct
import urllib.request
import threading
from collections import defaultdict

MINT = "EmT4thNMrQ4aJviLjcTdPhs4nsjuNAQ5jb6jwYUKpump"
BONDING_CURVE = "2qhouGdizQ8PTDkAt6U5L4GPRKP1PdNsMLBucQz5mWDm"
TRACKED_WALLETS_PATH = "/home/mthwt/code/Crypto/tracked_wallets.txt"
CACHE_DIR = "/home/mthwt/code/Crypto/scratch/emt4th_cache"

RPC_PROVIDERS = [
    ("shyft", "https://rpc.shyft.to?api_key=owfc3zuSXH37YG0U"),
    ("solami", "https://rpc.solami.dev/sol?api_key=sk_7hPGeJuMS_ASwhlvlxKBn_6N5hm8I4bKSP8xyaRFSXI"),
    ("alchemy", "https://solana-mainnet.g.alchemy.com/v2/8jufMAGFyazXvclfVdzH_e-TxbvZHvqG")
]

TRADE_DISC = bytes([189, 219, 127, 211, 78, 230, 97, 238])
CREATE_DISC = bytes([27, 114, 169, 77, 222, 235, 99, 118])

ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58encode(b: bytes) -> str:
    n = int.from_bytes(b, "big")
    chars = []
    while n > 0:
        n, r = divmod(n, 58)
        chars.append(ALPHABET[r])
    res = "".join(reversed(chars))
    pad = 0
    for byte in b:
        if byte == 0: pad += 1
        else: break
    return "1" * pad + res

def load_tracked_wallets():
    tracked = {}
    if not os.path.exists(TRACKED_WALLETS_PATH):
        return tracked
    with open(TRACKED_WALLETS_PATH, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("#")
            addr = parts[0].strip()
            label = parts[1].strip() if len(parts) > 1 else "Unknown Tracked"
            if addr:
                tracked[addr] = label
    return tracked

# Resilient RPC client with round-robin provider pool and throttling
PROVIDER_LOCK = threading.Lock()
NEXT_CALL = {p[0]: 0.0 for p in RPC_PROVIDERS}
PROVIDER_IDX = 0

def rpc_call(method, params, max_retries=5):
    global PROVIDER_IDX
    for attempt in range(max_retries):
        for _ in range(len(RPC_PROVIDERS)):
            with PROVIDER_LOCK:
                p_name, p_url = RPC_PROVIDERS[PROVIDER_IDX % len(RPC_PROVIDERS)]
                PROVIDER_IDX += 1
                now = time.monotonic()
                delay = max(0.0, NEXT_CALL[p_name] - now)
                NEXT_CALL[p_name] = now + delay + 0.15 # 150ms pacing per provider
            if delay > 0:
                time.sleep(delay)
            
            payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode("utf-8")
            req = urllib.request.Request(p_url, headers={"Content-Type": "application/json"}, data=payload)
            try:
                resp = urllib.request.urlopen(req, timeout=15)
                data = json.loads(resp.read().decode("utf-8"))
                if "error" in data:
                    err_msg = str(data["error"])
                    if "429" in err_msg or "rate" in err_msg.lower():
                        continue
                    raise RuntimeError(data["error"])
                return data.get("result")
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    time.sleep(0.5 + attempt * 0.5)
                    continue
                # other errors
                time.sleep(0.2)
                continue
            except Exception as e:
                time.sleep(0.2)
                continue
        time.sleep(0.5 + attempt)
    raise RuntimeError(f"All RPC providers failed after {max_retries} retries for {method}")

def get_bonding_curve_state():
    info = rpc_call("getAccountInfo", [BONDING_CURVE, {"encoding": "base64"}])
    val = info.get("value")
    lamports = val.get("lamports", 0)
    data = base64.b64decode(val.get("data")[0])
    v_tokens, v_sol, r_tokens, r_sol, total_supply = struct.unpack("<QQQQQ", data[8:48])
    complete = data[48] != 0
    return {
        "lamports": lamports,
        "v_tokens": v_tokens,
        "v_sol": v_sol,
        "r_tokens": r_tokens,
        "r_sol": r_sol,
        "total_supply": total_supply,
        "complete": complete,
        "curve_progress_pct": (r_sol / 85_000_000_000) * 100
    }

def fetch_tx(sig):
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(CACHE_DIR, f"{sig}.json")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r") as f:
                data = json.load(f)
                if data:
                    return data
        except Exception:
            pass
    try:
        tx = rpc_call("getTransaction", [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1}])
        if tx:
            with open(cache_path, "w") as f:
                json.dump(tx, f)
        return tx
    except Exception as e:
        print(f"Failed to fetch {sig}: {e}")
        return None

def decode_events_from_tx(tx):
    if not tx or not tx.get("meta"):
        return []
    meta = tx["meta"]
    if meta.get("err"):
        return []
    
    logs = meta.get("logMessages", [])
    events = []
    
    msg = tx.get("transaction", {}).get("message", {})
    account_keys = msg.get("accountKeys", [])
    fee_payer = None
    if account_keys:
        first = account_keys[0]
        fee_payer = first.get("pubkey") if isinstance(first, dict) else first
    
    for log in logs:
        if log.startswith("Program data: "):
            b64_str = log[len("Program data: "):]
            try:
                raw = base64.b64decode(b64_str)
                if raw[:8] == TRADE_DISC:
                    mint = b58encode(raw[8:40])
                    sol_raw = struct.unpack('<Q', raw[40:48])[0]
                    tokens_raw = struct.unpack('<Q', raw[48:56])[0]
                    is_buy = raw[56] != 0
                    user = b58encode(raw[57:89])
                    timestamp = struct.unpack('<q', raw[89:97])[0]
                    vsol_raw = struct.unpack('<Q', raw[97:105])[0]
                    vtokens_raw = struct.unpack('<Q', raw[105:113])[0]
                    rsol_raw = struct.unpack('<Q', raw[113:121])[0]
                    rtokens_raw = struct.unpack('<Q', raw[121:129])[0]
                    
                    events.append({
                        "slot": tx.get("slot"),
                        "blockTime": tx.get("blockTime"),
                        "fee_payer": fee_payer,
                        "user": user,
                        "mint": mint,
                        "is_buy": is_buy,
                        "sol": sol_raw / 1e9,
                        "tokens": tokens_raw / 1e6,
                        "price": (sol_raw / 1e9) / (tokens_raw / 1e6) if tokens_raw > 0 else 0,
                        "vsol": vsol_raw / 1e9,
                        "vtokens": vtokens_raw / 1e6,
                        "rsol": rsol_raw / 1e9,
                        "rtokens": rtokens_raw / 1e6,
                    })
            except Exception:
                pass
    return events

def run():
    print("================================================================================")
    print("           SOLANA ON-CHAIN ORDERFLOW AUDIT: EmT4th... (TOKEN REPORT)             ")
    print("================================================================================")
    
    tracked = load_tracked_wallets()
    print(f"Loaded {len(tracked)} tracked wallets from tracked_wallets.txt\n")
    
    # 1. Bonding Curve State
    print("--- STEP 1: CURRENT BONDING CURVE METRICS ---")
    curve_st = get_bonding_curve_state()
    v_sol = curve_st["v_sol"] / 1e9
    v_tokens = curve_st["v_tokens"] / 1e6
    r_sol = curve_st["r_sol"] / 1e9
    r_tokens = curve_st["r_tokens"] / 1e6
    current_price = v_sol / v_tokens
    mcap_sol = current_price * 1_000_000_000
    
    print(f"Mint Address:           {MINT}")
    print(f"Bonding Curve Account:  {BONDING_CURVE}")
    print(f"Curve Status:           {'GRADUATED (Complete)' if curve_st['complete'] else 'ACTIVE ON BONDING CURVE (Incomplete)'}")
    print(f"Real SOL Reserves:      {r_sol:.4f} SOL")
    print(f"Virtual SOL Reserves:   {v_sol:.4f} SOL")
    print(f"Real Token Reserves:    {r_tokens:,.2f} tokens")
    print(f"Virtual Token Reserves: {v_tokens:,.2f} tokens")
    print(f"Bonding Progress:       {curve_st['curve_progress_pct']:.2f}% (relative to ~85.0 SOL graduation target)")
    print(f"Spot Price:             {current_price:.10f} SOL / token")
    print(f"Implied Market Cap:     {mcap_sol:.2f} SOL\n")
    
    # 2. Fetch all signatures
    print("--- STEP 2: RETRIEVING SIGNATURE HISTORY ---")
    all_sigs = []
    before = None
    for _ in range(4):
        opts = {"limit": 1000}
        if before: opts["before"] = before
        batch = rpc_call("getSignaturesForAddress", [MINT, opts])
        if not batch: break
        all_sigs.extend(batch)
        before = batch[-1]["signature"]
        if len(batch) < 1000: break
        
    print(f"Total On-Chain Signatures for Mint: {len(all_sigs)}")
    creation_info = all_sigs[-1]
    creation_slot = creation_info["slot"]
    creation_time = creation_info.get("blockTime")
    creation_str = time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(creation_time)) if creation_time else 'Unknown'
    
    latest_info = all_sigs[0]
    latest_slot = latest_info["slot"]
    latest_time = latest_info.get("blockTime")
    latest_str = time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(latest_time)) if latest_time else 'Unknown'
    
    print(f"Creation Slot:  {creation_slot} | Timestamp: {creation_str}")
    print(f"Latest Slot:    {latest_slot} | Timestamp: {latest_str}")
    lifespan_sec = (latest_time - creation_time) if (latest_time and creation_time) else 0
    print(f"Token Lifespan: {lifespan_sec / 3600:.2f} hours ({lifespan_sec} seconds)\n")
    
    # Analyze the creation transaction
    print("--- CREATION TRANSACTION INSPECTION ---")
    creation_tx = fetch_tx(creation_info["signature"])
    creator_wallet = None
    if creation_tx:
        msg = creation_tx.get("transaction", {}).get("message", {})
        keys = msg.get("accountKeys", [])
        if keys:
            creator_wallet = keys[0].get("pubkey") if isinstance(keys[0], dict) else keys[0]
    print(f"Creation Tx Signature: {creation_info['signature']}")
    print(f"Creator Wallet:        {creator_wallet}")
    if creator_wallet in tracked:
        print(f"*** CREATOR IS IN TRACKED WALLETS: {tracked[creator_wallet]} ***")
    else:
        print("Creator is untracked.")
        
    # Check creation buy
    creation_events = decode_events_from_tx(creation_tx)
    if creation_events:
        for cev in creation_events:
            print(f"Creator Initial Buy: {cev['sol']:.4f} SOL for {cev['tokens']:,.2f} tokens ({cev['tokens']/10_000_000:.2f}% of supply)")
    print()

    # 3. Transaction Fetching: All recovery phase transactions (from bottom dump onwards)
    recovery_sigs = [s for s in all_sigs if s["slot"] >= 455910400]
    print(f"--- STEP 3: FETCHING AND PARSING ENTIRE RECOVERY PHASE ({len(recovery_sigs)} TRANSACTIONS) ---")
    
    import concurrent.futures
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        recovery_txs = list(executor.map(fetch_tx, [s["signature"] for s in recovery_sigs]))
    t1 = time.time()
    print(f"Fetched {len(recovery_txs)} transactions in {t1-t0:.2f}s.\n")
    
    # Decode events
    all_events = []
    failed_tx_count = 0
    for s_info, tx in zip(recovery_sigs, recovery_txs):
        if not tx:
            continue
        if tx.get("meta", {}).get("err"):
            failed_tx_count += 1
            continue
        evs = decode_events_from_tx(tx)
        for ev in evs:
            ev["signature"] = s_info["signature"]
            all_events.append(ev)
            
    print(f"Recovery Phase Transaction Summary:")
    print(f"  Total Transactions Sampled: {len(recovery_sigs)}")
    print(f"  Failed Transactions:         {failed_tx_count}")
    print(f"  Decoded Trade Events:        {len(all_events)}")
    
    # Sort chronological (oldest to newest)
    all_events.sort(key=lambda x: (x["slot"], x["sol"]))
    
    # 4. Detailed Bot Behavior Analysis
    print("\n================================================================================")
    print("                    BOT ORDERFLOW & BEHAVIORAL PROFILING                        ")
    print("================================================================================")
    
    # Group by user wallet
    wallets_map = defaultdict(lambda: {"buys": [], "sells": []})
    for ev in all_events:
        if ev["is_buy"]:
            wallets_map[ev["user"]]["buys"].append(ev)
        else:
            wallets_map[ev["user"]]["sells"].append(ev)
            
    # Classify wallets
    bumpers = []
    scalpers = []
    regular_traders = []
    
    for user, data in wallets_map.items():
        buys = data["buys"]
        sells = data["sells"]
        buy_count = len(buys)
        sell_count = len(sells)
        total_buy_sol = sum(b["sol"] for b in buys)
        total_sell_sol = sum(s["sol"] for s in sells)
        
        # Bumper definition: micro-buys <= 0.02 SOL, high buy frequency, little/no sells
        micro_buys = [b for b in buys if b["sol"] <= 0.02]
        is_bumper = (buy_count >= 3 and len(micro_buys) / buy_count >= 0.75 and (total_buy_sol / buy_count) < 0.025)
        
        entry = {
            "user": user,
            "label": tracked.get(user, "Untracked"),
            "is_tracked": user in tracked,
            "buys": buys,
            "sells": sells,
            "buy_count": buy_count,
            "sell_count": sell_count,
            "total_buy_sol": total_buy_sol,
            "total_sell_sol": total_sell_sol,
            "avg_buy_sol": total_buy_sol / buy_count if buy_count > 0 else 0,
            "tokens_bought": sum(b["tokens"] for b in buys),
            "tokens_sold": sum(s["tokens"] for s in sells),
        }
        
        if is_bumper:
            bumpers.append(entry)
        elif sell_count > 0 and buy_count > 0:
            scalpers.append(entry)
        else:
            regular_traders.append(entry)
            
    # [A] BUMPER BOTS
    print("\n--- [A] HIGH-FREQUENCY MICRO-BUY BUMPER BOTS (<0.02 SOL) ---")
    if not bumpers:
        print(">> No high-frequency micro-buy bumper bots detected in this window.")
    else:
        print(f"Detected {len(bumpers)} active bumper bot wallet(s) generating artificial volume:")
        for b in sorted(bumpers, key=lambda x: x["buy_count"], reverse=True):
            slots = [x["slot"] for x in b["buys"]]
            slot_diffs = [slots[i] - slots[i-1] for i in range(1, len(slots))]
            avg_diff = sum(slot_diffs) / len(slot_diffs) if slot_diffs else 0
            min_diff = min(slot_diffs) if slot_diffs else 0
            max_diff = max(slot_diffs) if slot_diffs else 0
            
            print(f"Wallet:     {b['user']}")
            print(f"  Label:    {b['label']}")
            print(f"  Activity: {b['buy_count']} buys, {b['sell_count']} sells")
            print(f"  Volume:   {b['total_buy_sol']:.4f} SOL spent (avg {b['avg_buy_sol']:.5f} SOL per bump)")
            print(f"  Cadence:  Avg gap: {avg_diff:.1f} slots (~{avg_diff*0.4:.1f}s) | Min gap: {min_diff} slots | Max gap: {max_diff} slots")
            print(f"  Purpose:  DexScreener/Pump transaction count inflator & trending rank manipulation.")
            print()

    # [B] TRACKED WALLET CROSS-REFERENCE
    print("\n--- [B] TRACKED WALLETS CROSS-REFERENCE (FROM tracked_wallets.txt) ---")
    all_active = bumpers + scalpers + regular_traders
    active_tracked = [w for w in all_active if w["is_tracked"]]
    
    if not active_tracked:
        print(">> None of the 170+ wallets from tracked_wallets.txt were active in this recent sample.")
    else:
        print(f"Found {len(active_tracked)} tracked wallet(s) active on this coin:")
        for tw in sorted(active_tracked, key=lambda x: x["total_buy_sol"], reverse=True):
            print(f"  Wallet: {tw['user']}")
            print(f"    Name/Label:       {tw['label']}")
            print(f"    Buys:             {tw['buy_count']} ({tw['total_buy_sol']:.4f} SOL)")
            print(f"    Sells:            {tw['sell_count']} ({tw['total_sell_sol']:.4f} SOL)")
            net_tokens = tw["tokens_bought"] - tw["tokens_sold"]
            unreal = net_tokens * current_price
            pnl = (tw["total_sell_sol"] + unreal) - tw["total_buy_sol"]
            print(f"    Net PnL (Marked): {pnl:+.4f} SOL (Tokens remaining: {net_tokens:,.1f})")
            print()

    # [C] SCALPERS & FRONT-RUNNERS
    print("\n--- [C] ACTIVE SCALPERS & ARBITRAGE/MOMENTUM BOTS ---")
    # Wallets with both buys and sells, or rapid in-and-out
    scalpers.sort(key=lambda x: x["total_buy_sol"] + x["total_sell_sol"], reverse=True)
    print(f"{'Wallet':44} | {'Role/Label':22} | {'Buys':>4} | {'Buy SOL':>8} | {'Sells':>5} | {'Sell SOL':>8} | {'PnL SOL':>9} | {'Hold Time'}")
    print("-" * 125)
    for s in scalpers[:15]:
        net_tok = s["tokens_bought"] - s["tokens_sold"]
        unreal = max(0.0, net_tok) * current_price
        pnl = (s["total_sell_sol"] + unreal) - s["total_buy_sol"]
        
        # Calculate hold duration
        buy_times = [b["blockTime"] for b in s["buys"] if b["blockTime"]]
        sell_times = [x["blockTime"] for x in s["sells"] if x["blockTime"]]
        hold_str = "N/A"
        if buy_times and sell_times:
            avg_buy_t = sum(buy_times) / len(buy_times)
            avg_sell_t = sum(sell_times) / len(sell_times)
            duration_s = avg_sell_t - avg_buy_t
            if duration_s < 60:
                hold_str = f"{duration_s:.0f}s"
            else:
                hold_str = f"{duration_s/60:.1f}m"
                
        lbl = s["label"][:22]
        print(f"{s['user']:44} | {lbl:22} | {s['buy_count']:4d} | {s['total_buy_sol']:8.3f} | {s['sell_count']:5d} | {s['total_sell_sol']:8.3f} | {pnl:+9.4f} | {hold_str}")

    # [D] TOP ACCUMULATORS / HOLDING BUYERS
    print("\n--- [D] TOP UNCLOSED BUYERS (HOLDING/ACCUMULATING) ---")
    holding_buyers = [w for w in (regular_traders + bumpers) if w["buy_count"] > 0 and w["sell_count"] == 0]
    holding_buyers.sort(key=lambda x: x["total_buy_sol"], reverse=True)
    print(f"{'Wallet':44} | {'Role/Label':22} | {'Buys':>4} | {'Buy SOL':>8} | {'Tokens Held':>15} | {'Unreal SOL':>10} | {'Unreal PnL'}")
    print("-" * 125)
    for hb in holding_buyers[:15]:
        tokens = hb["tokens_bought"]
        unreal_val = tokens * current_price
        unreal_pnl = unreal_val - hb["total_buy_sol"]
        pnl_pct = (unreal_pnl / hb["total_buy_sol"] * 100) if hb["total_buy_sol"] > 0 else 0
        lbl = hb["label"][:22]
        print(f"{hb['user']:44} | {lbl:22} | {hb['buy_count']:4d} | {hb['total_buy_sol']:8.3f} | {tokens:15,.0f} | {unreal_val:10.4f} | {unreal_pnl:+8.4f} ({pnl_pct:+.1f}%)")

    # 5. Orderflow Structure & Volume Composition
    print("\n================================================================================")
    print("                    ORDERFLOW STRUCTURE & VOLUME ANATOMY                        ")
    print("================================================================================")
    all_buys = [e for e in all_events if e["is_buy"]]
    all_sells = [e for e in all_events if not e["is_buy"]]
    
    total_buy_sol = sum(e["sol"] for e in all_buys)
    total_sell_sol = sum(e["sol"] for e in all_sells)
    net_flow = total_buy_sol - total_sell_sol
    
    print(f"Total Trades in Sample:   {len(all_events)} ({len(all_buys)} buys, {len(all_sells)} sells)")
    print(f"Gross SOL Volume:         {total_buy_sol + total_sell_sol:.3f} SOL")
    print(f"Buy Volume:               {total_buy_sol:.3f} SOL ({(total_buy_sol/(total_buy_sol+total_sell_sol)*100 if total_buy_sol+total_sell_sol>0 else 0):.1f}%)")
    print(f"Sell Volume:              {total_sell_sol:.3f} SOL ({(total_sell_sol/(total_buy_sol+total_sell_sol)*100 if total_buy_sol+total_sell_sol>0 else 0):.1f}%)")
    print(f"Net Orderflow:            {net_flow:+.3f} SOL")
    
    # Bucket distribution of buys
    b_micro = [b for b in all_buys if b["sol"] < 0.05]
    b_small = [b for b in all_buys if 0.05 <= b["sol"] < 0.20]
    b_mid = [b for b in all_buys if 0.20 <= b["sol"] < 0.50]
    b_large = [b for b in all_buys if b["sol"] >= 0.50]
    
    print("\nBuy Size Distribution:")
    print(f"  < 0.05 SOL (Micro/Bumps):    {len(b_micro):3d} txs ({len(b_micro)/len(all_buys)*100:4.1f}%) | {sum(b['sol'] for b in b_micro):6.2f} SOL ({sum(b['sol'] for b in b_micro)/total_buy_sol*100:4.1f}% of buy vol)")
    print(f"  0.05 - 0.20 SOL (Small/Retail):{len(b_small):3d} txs ({len(b_small)/len(all_buys)*100:4.1f}%) | {sum(b['sol'] for b in b_small):6.2f} SOL ({sum(b['sol'] for b in b_small)/total_buy_sol*100:4.1f}% of buy vol)")
    print(f"  0.20 - 0.50 SOL (Medium/Bots): {len(b_mid):3d} txs ({len(b_mid)/len(all_buys)*100:4.1f}%) | {sum(b['sol'] for b in b_mid):6.2f} SOL ({sum(b['sol'] for b in b_mid)/total_buy_sol*100:4.1f}% of buy vol)")
    print(f"  >= 0.50 SOL (Large/Conviction):{len(b_large):3d} txs ({len(b_large)/len(all_buys)*100:4.1f}%) | {sum(b['sol'] for b in b_large):6.2f} SOL ({sum(b['sol'] for b in b_large)/total_buy_sol*100:4.1f}% of buy vol)")
    
    # Time span of the sample
    first_time = all_events[0]["blockTime"]
    last_time = all_events[-1]["blockTime"]
    dt = last_time - first_time if (first_time and last_time) else 1
    print(f"\nSample Time Span: {dt/60:.1f} minutes ({dt} seconds)")
    print(f"Average Trade Rate: {len(all_events)/(dt/60):.1f} trades / minute")
    print(f"Average Volume Rate: {(total_buy_sol+total_sell_sol)/(dt/60):.2f} SOL / minute")
    
if __name__ == "__main__":
    run()
