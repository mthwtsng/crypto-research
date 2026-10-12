import os
import sys
import json
import time
import datetime
import struct
import base64
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

SHYFT_RPC = "https://rpc.shyft.to?api_key=owfc3zuSXH37YG0U"
ALCHEMY_RPC = "https://solana-mainnet.g.alchemy.com/v2/8jufMAGFyazXvclfVdzH_e-TxbvZHvqG"

MINT = "MiLFgCEjhTLnzVnv9PznbQ41Qgna3PXW9CgFRHKpump"
CURVE_ADDR = "DnVwC3wrntqra5jXqi7DCBHCBxQB5qeh6656KGLDaqYr"
PUMP_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"

TRACKED_WALLETS_PATH = "/home/mthwt/code/Crypto/tracked_wallets.txt"
KOL_WALLETS_PATH = "/home/mthwt/code/Crypto/kol_wallets.txt"

def load_wallets(path):
    d = {}
    if not os.path.exists(path):
        return d
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("#")
            addr = parts[0].strip()
            label = parts[1].strip() if len(parts) > 1 else ""
            if addr:
                d[addr] = label
    return d

def rpc_call(method, params, rpc=SHYFT_RPC, retries=3):
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    for attempt in range(retries):
        try:
            r = requests.post(rpc, json=payload, timeout=10)
            if r.status_code == 200:
                res = r.json()
                if "result" in res:
                    return res["result"]
            time.sleep(0.2 * (attempt + 1))
        except Exception:
            time.sleep(0.3 * (attempt + 1))
    # fallback to Alchemy if Shyft fails
    if rpc == SHYFT_RPC:
        return rpc_call(method, params, rpc=ALCHEMY_RPC, retries=2)
    return None

def get_curve_state():
    info = rpc_call("getAccountInfo", [CURVE_ADDR, {"encoding": "base64"}])
    if not info or not info.get("value"):
        return None
    val = info["value"]
    raw = base64.b64decode(val["data"][0])
    v_tokens, v_sol, r_tokens, r_sol, supply = struct.unpack("<QQQQQ", raw[8:48])
    complete = raw[48] != 0
    return {
        "lamports": val["lamports"],
        "virtual_token_reserves": v_tokens,
        "virtual_sol_reserves": v_sol,
        "real_token_reserves": r_tokens,
        "real_sol_reserves": r_sol,
        "token_total_supply": supply,
        "complete": complete,
        "real_sol_sol": r_sol / 1e9,
        "virtual_sol_sol": v_sol / 1e9,
        "price_sol_per_token": (v_sol / 1e9) / (v_tokens / 1e6) if v_tokens > 0 else 0,
        "market_cap_sol": ((v_sol / 1e9) / (v_tokens / 1e6)) * 1_000_000_000 if v_tokens > 0 else 0
    }

def fetch_tx(sig):
    tx = rpc_call("getTransaction", [sig, {"maxSupportedTransactionVersion": 1, "encoding": "jsonParsed"}])
    return sig, tx

def parse_transaction(sig, tx):
    if not tx:
        return None
    slot = tx.get("slot")
    block_time = tx.get("blockTime")
    meta = tx.get("meta", {})
    if meta.get("err") is not None:
        return None
    
    logs = meta.get("logMessages", [])
    trade_type = "UNKNOWN"
    for l in logs:
        if "Instruction: Buy" in l or "Instruction: BuyV2" in l:
            trade_type = "BUY"
            break
        elif "Instruction: Sell" in l or "Instruction: SellV2" in l:
            trade_type = "SELL"
            break
        elif "Instruction: Create" in l or "Instruction: CreateV2" in l:
            trade_type = "CREATE"
            break
            
    if trade_type == "UNKNOWN":
        return None
        
    msg = tx.get("transaction", {}).get("message", {})
    account_keys = msg.get("accountKeys", [])
    
    pre_bal = meta.get("preBalances", [])
    post_bal = meta.get("postBalances", [])
    curve_idx = None
    for i, a in enumerate(account_keys):
        pk = a["pubkey"] if isinstance(a, dict) else a
        if pk == CURVE_ADDR:
            curve_idx = i
            break
            
    sol_delta = 0
    if curve_idx is not None and curve_idx < len(pre_bal) and curve_idx < len(post_bal):
        sol_delta = (post_bal[curve_idx] - pre_bal[curve_idx]) / 1e9
        
    pre_tb = {b["accountIndex"]: int(b["uiTokenAmount"]["amount"]) for b in meta.get("preTokenBalances", []) if b.get("mint") == MINT}
    post_tb = {b["accountIndex"]: int(b["uiTokenAmount"]["amount"]) for b in meta.get("postTokenBalances", []) if b.get("mint") == MINT}
    
    trader_wallet = None
    token_delta = 0
    for idx in set(pre_tb.keys()).union(post_tb.keys()):
        diff = post_tb.get(idx, 0) - pre_tb.get(idx, 0)
        owner = None
        for b in meta.get("postTokenBalances", []) + meta.get("preTokenBalances", []):
            if b.get("accountIndex") == idx:
                owner = b.get("owner")
                break
        if owner and owner != CURVE_ADDR:
            trader_wallet = owner
            token_delta = diff / 1e6
            break
            
    signers = [a["pubkey"] if isinstance(a, dict) else a for a in account_keys if (isinstance(a, dict) and a.get("signer"))]
    fee_payer = signers[0] if signers else "unknown"
    if not trader_wallet:
        trader_wallet = fee_payer

    return {
        "signature": sig,
        "slot": slot,
        "block_time": block_time,
        "trade_type": trade_type,
        "trader_wallet": trader_wallet,
        "fee_payer": fee_payer,
        "sol_amount": abs(sol_delta),
        "sol_delta": sol_delta,
        "tokens": abs(token_delta),
        "token_delta": token_delta,
        "fee": meta.get("fee", 0) / 1e9
    }

def run_pipeline():
    print("Step 1: Checking current curve state...")
    curve = get_curve_state()
    if curve:
        print(f"  Real SOL: {curve['real_sol_sol']:.4f} SOL")
        print(f"  Virtual SOL: {curve['virtual_sol_sol']:.4f} SOL")
        print(f"  Bonding progress: {(curve['real_sol_sol'] / 85.0)*100:.1f}%")
        print(f"  Market cap: {curve['market_cap_sol']:.2f} SOL")
        print(f"  Graduated: {curve['complete']}")

    print("\nStep 2: Parsing latest 300 transactions...")
    with open("/home/mthwt/code/Crypto/scratch/latest_300_sigs.json") as f:
        recent_sigs = json.load(f)

    parsed_recent = []
    with ThreadPoolExecutor(max_workers=15) as executor:
        futures = {executor.submit(fetch_tx, s["signature"]): s for s in recent_sigs}
        for fut in as_completed(futures):
            sig, tx = fut.result()
            parsed = parse_transaction(sig, tx)
            if parsed:
                parsed_recent.append(parsed)

    parsed_recent.sort(key=lambda x: (x["slot"], x["signature"]))
    print(f"Parsed {len(parsed_recent)} successful trades from latest 300 sigs.")

    with open("/home/mthwt/code/Crypto/scratch/latest_parsed_txs.json", "w") as f:
        json.dump(parsed_recent, f, indent=2)

    # Step 3: Combine datasets
    all_trades = {}
    for path in [
        "/home/mthwt/code/Crypto/scratch/first_100_parsed.json",
        "/home/mthwt/code/Crypto/scratch/parsed_txs_milfgc.json",
        "/home/mthwt/code/Crypto/scratch/latest_parsed_txs.json"
    ]:
        if os.path.exists(path):
            with open(path) as f:
                trades = json.load(f)
                for t in trades:
                    all_trades[t["signature"]] = t

    trade_list = sorted(all_trades.values(), key=lambda x: (x["slot"], x["signature"]))
    print(f"\nTotal unique trades in combined analysis dataset: {len(trade_list)}")
    print(f"Slot span: {trade_list[0]['slot']} to {trade_list[-1]['slot']} (elapsed: {trade_list[-1]['slot'] - trade_list[0]['slot']} slots)")

    # Step 4: Load tracked wallets & KOLs
    tracked = load_wallets(TRACKED_WALLETS_PATH)
    kol = load_wallets(KOL_WALLETS_PATH)

    # Step 5: Bumper Bot Analysis
    buys = [t for t in trade_list if t["trade_type"] == "BUY"]
    sells = [t for t in trade_list if t["trade_type"] == "SELL"]
    creates = [t for t in trade_list if t["trade_type"] == "CREATE"]

    micro_buys = [t for t in buys if t["sol_amount"] < 0.02]
    micro_buys_001 = [t for t in buys if t["sol_amount"] < 0.01]
    micro_buys_005 = [t for t in buys if t["sol_amount"] < 0.005]

    print("\n--- BUMPER BOT ORDERFLOW QUANTIFICATION ---")
    print(f"Total Buys Analyzed: {len(buys)}")
    print(f"Micro-buys (< 0.02 SOL): {len(micro_buys)} ({len(micro_buys)/len(buys)*100:.1f}% of all buys)")
    print(f"Micro-buys (< 0.01 SOL): {len(micro_buys_001)} ({len(micro_buys_001)/len(buys)*100:.1f}% of all buys)")
    print(f"Micro-buys (< 0.005 SOL): {len(micro_buys_005)} ({len(micro_buys_005)/len(buys)*100:.1f}% of all buys)")
    
    micro_sol_volume = sum(t["sol_amount"] for t in micro_buys)
    total_buy_sol = sum(t["sol_amount"] for t in buys)
    print(f"Micro-buy SOL Volume: {micro_sol_volume:.4f} SOL ({micro_sol_volume/total_buy_sol*100:.2f}% of total buy SOL volume {total_buy_sol:.2f} SOL)")

    # Bumper wallets
    bumper_wallets = Counter(t["trader_wallet"] for t in micro_buys)
    print(f"\nUnique wallets executing micro-buys: {len(bumper_wallets)}")
    print("Top 10 micro-buyer wallets:")
    for w, count in bumper_wallets.most_common(10):
        w_micro = [t for t in micro_buys if t["trader_wallet"] == w]
        w_all_buys = [t for t in buys if t["trader_wallet"] == w]
        w_all_sells = [t for t in sells if t["trader_wallet"] == w]
        w_sol_in = sum(t["sol_amount"] for t in w_all_buys)
        w_sol_out = sum(t["sol_amount"] for t in w_all_sells)
        print(f"  {w}: {count} micro-buys (total buys: {len(w_all_buys)}, total sells: {len(w_all_sells)}), In: {w_sol_in:.4f} SOL, Out: {w_sol_out:.4f} SOL")

    # Slot spacing between micro-buys
    if len(micro_buys) > 1:
        micro_buys_sorted = sorted(micro_buys, key=lambda x: x["slot"])
        slot_diffs = [micro_buys_sorted[i]["slot"] - micro_buys_sorted[i-1]["slot"] for i in range(1, len(micro_buys_sorted))]
        avg_slot_gap = sum(slot_diffs) / len(slot_diffs)
        med_slot_gap = sorted(slot_diffs)[len(slot_diffs)//2]
        print(f"\nBumper cadence: Avg slot gap = {avg_slot_gap:.1f} slots (~{avg_slot_gap*0.4:.1f}s), Median slot gap = {med_slot_gap} slots (~{med_slot_gap*0.4:.1f}s)")
        print(f"Cadence <= 2 slots: {sum(1 for d in slot_diffs if d <= 2)} / {len(slot_diffs)} ({sum(1 for d in slot_diffs if d <= 2)/len(slot_diffs)*100:.1f}%)")
        print(f"Cadence <= 5 slots: {sum(1 for d in slot_diffs if d <= 5)} / {len(slot_diffs)} ({sum(1 for d in slot_diffs if d <= 5)/len(slot_diffs)*100:.1f}%)")

    # Step 6: Tracked Wallets & KOL Cross-Reference
    print("\n--- TRACKED WALLETS & KOL CROSS-REFERENCE ---")
    all_traders = set(t["trader_wallet"] for t in trade_list)
    fee_payers = set(t["fee_payer"] for t in trade_list)

    matched_tracked = all_traders.intersection(tracked.keys())
    matched_kol = all_traders.intersection(kol.keys())
    matched_fp_tracked = fee_payers.intersection(tracked.keys())
    matched_fp_kol = fee_payers.intersection(kol.keys())

    print(f"Tracked wallets participating as traders: {len(matched_tracked)}")
    for w in matched_tracked:
        print(f"  [TRACKED TRADER] {w} -> {tracked[w]}")
    for w in matched_fp_tracked:
        if w not in matched_tracked:
            print(f"  [TRACKED FEE PAYER] {w} -> {tracked[w]}")

    print(f"KOL wallets participating: {len(matched_kol)}")
    for w in matched_kol:
        print(f"  [KOL TRADER] {w} -> {kol[w]}")

    # Step 7: Bot Performance & PnL Accounting
    print("\n--- TRADER / BOT PERFORMANCE & PNL (TOP PARTICIPANTS) ---")
    curr_price = curve["price_sol_per_token"] if curve else 0

    wallet_stats = {}
    for w in all_traders:
        w_buys = [t for t in buys if t["trader_wallet"] == w]
        w_sells = [t for t in sells if t["trader_wallet"] == w]
        
        sol_in = sum(t["sol_amount"] for t in w_buys)
        tokens_in = sum(t["tokens"] for t in w_buys)
        sol_out = sum(t["sol_amount"] for t in w_sells)
        tokens_out = sum(t["tokens"] for t in w_sells)
        
        token_inventory = max(0, tokens_in - tokens_out)
        unrealized_sol = token_inventory * curr_price
        realized_pnl = sol_out - (sol_in * (tokens_out / tokens_in)) if tokens_in > 0 and tokens_out > 0 else (sol_out - sol_in if tokens_out >= tokens_in > 0 else 0)
        net_pnl = (sol_out + unrealized_sol) - sol_in

        # duration
        all_w_trades = sorted(w_buys + w_sells, key=lambda x: x["slot"])
        hold_slots = all_w_trades[-1]["slot"] - all_w_trades[0]["slot"] if len(all_w_trades) > 1 else 0
        hold_seconds = all_w_trades[-1]["block_time"] - all_w_trades[0]["block_time"] if len(all_w_trades) > 1 and all_w_trades[-1]["block_time"] and all_w_trades[0]["block_time"] else 0

        # Archetype tagging
        tag = "Organic"
        if w in tracked:
            tag = f"Tracked ({tracked[w]})"
        elif len(w_buys) >= 2 and all(t["sol_amount"] < 0.02 for t in w_buys) and len(w_sells) == 0:
            tag = "Bumper Bot"
        elif len(w_buys) >= 1 and len(w_sells) >= 1 and hold_slots <= 150:
            tag = "Scalper Bot"
        elif sol_in > 1.0 and len(w_buys) >= 1:
            tag = "Whale / Momentum"
        elif len(w_buys) >= 3:
            tag = "Active Trader"

        wallet_stats[w] = {
            "tag": tag,
            "buys": len(w_buys),
            "sells": len(w_sells),
            "sol_in": sol_in,
            "tokens_in": tokens_in,
            "sol_out": sol_out,
            "tokens_out": tokens_out,
            "token_inventory": token_inventory,
            "unrealized_sol": unrealized_sol,
            "realized_pnl": realized_pnl,
            "net_pnl": net_pnl,
            "hold_slots": hold_slots,
            "hold_seconds": hold_seconds,
            "avg_buy_price": (sol_in / tokens_in) if tokens_in > 0 else 0,
            "avg_sell_price": (sol_out / tokens_out) if tokens_out > 0 else 0,
        }

    # Print Tracked bot breakdown
    print("\n--- DETAILED BREAKDOWN OF TRACKED BOTS ---")
    for w in matched_tracked:
        st = wallet_stats[w]
        print(f"Bot: {w}")
        print(f"  Label: {tracked[w]}")
        print(f"  Buys: {st['buys']} (Total {st['sol_in']:.4f} SOL, {st['tokens_in']:,.0f} tokens)")
        print(f"  Sells: {st['sells']} (Total {st['sol_out']:.4f} SOL, {st['tokens_out']:,.0f} tokens)")
        print(f"  Remaining inventory: {st['token_inventory']:,.0f} tokens ({st['unrealized_sol']:.4f} SOL marked)")
        print(f"  Net PnL (Realized + Unrealized): {st['net_pnl']:+.4f} SOL")
        print(f"  Avg Entry Price: {st['avg_buy_price']*1e6:.6f} SOL/M tokens")
        print(f"  Avg Exit Price:  {st['avg_sell_price']*1e6:.6f} SOL/M tokens")
        print(f"  Holding Duration: {st['hold_slots']} slots (~{st['hold_seconds']}s)")

    # Print Top 15 Wallets by Total Volume
    print("\n--- TOP 15 WALLETS BY VOLUME IN SAMPLE ---")
    sorted_by_vol = sorted(wallet_stats.items(), key=lambda x: x[1]["sol_in"] + x[1]["sol_out"], reverse=True)
    for w, st in sorted_by_vol[:15]:
        print(f"Wallet: {w[:16]}... | Tag: {st['tag'][:25]:25s} | Buys: {st['buys']:2d} ({st['sol_in']:6.2f} SOL) | Sells: {st['sells']:2d} ({st['sol_out']:6.2f} SOL) | Net PnL: {st['net_pnl']:+6.3f} SOL | Hold: {st['hold_slots']:4d} slots (~{st['hold_seconds']:3d}s)")

    # Step 8: Top Profitable Bots vs Top Losing Bots
    print("\n--- TOP 5 PROFITABLE TRADERS / BOTS IN SAMPLE ---")
    sorted_by_pnl = sorted(wallet_stats.items(), key=lambda x: x[1]["net_pnl"], reverse=True)
    for w, st in sorted_by_pnl[:5]:
        print(f"  {w} ({st['tag']}): Net PnL {st['net_pnl']:+.4f} SOL | In: {st['sol_in']:.3f} SOL, Out: {st['sol_out']:.3f} SOL, Inv: {st['unrealized_sol']:.3f} SOL")

    print("\n--- TOP 5 LOSING TRADERS / BOTS IN SAMPLE ---")
    for w, st in sorted_by_pnl[-5:]:
        print(f"  {w} ({st['tag']}): Net PnL {st['net_pnl']:+.4f} SOL | In: {st['sol_in']:.3f} SOL, Out: {st['sol_out']:.3f} SOL, Inv: {st['unrealized_sol']:.3f} SOL")

if __name__ == "__main__":
    run_pipeline()
