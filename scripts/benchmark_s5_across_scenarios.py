"""Benchmark S5 AMM Carryover across all 5 placement scenarios and stress fee."""
import json
import gzip
import pathlib
import sys

ROOT = pathlib.Path.cwd()
sys.path.insert(0, str(ROOT / "research/core_plan_audit_20261007"))
sys.path.insert(0, str(ROOT / "research/core_gap_refinement_20261007"))
sys.path.insert(0, str(ROOT / "research/wallet_curve_entry_discovery_20261007"))
sys.path.insert(0, str(ROOT / "research/amm_multiday_20261006"))
sys.path.insert(0, str(ROOT / "research/frozen_21day_validation_20261008"))
import rpc_pool as R
import engine as E
import curve_adapter as A
import amm_counterparty as M
import opportunity as O

mints = [
    "3yJsenghPtwkAoLmwL8hRDmxZrDFScj8T7FFutwBpump",
    "Ft9SNGXt29RJ5PKW2PA86ANUKSSkJi2HMcwyHP31pump",
    "BopHFrb6tzVo87d2oqawpBTJLtDYU3G6u56dYUo8pump",
    "DnjjGyuLVfQFZoQAJv2gNGcAzhyc4CdFaKHMMcWdpump",
    "4YTQ2bmCycn4vLiKWjWLe8swEFDWkxByJDE2uCWUpump",
    "CXdRBoRWmWWeUDHkFgmH6D566sFFccaTsrgCGaGSpump",
    "2VVBKWfWTpAwdkDFLCz5SsAeZDxFrzmsKHvchLc5pump",
    "87QtDtqHj1uatfmuwF7oBcmMaUfFpAUE7NNrpbkWpump",
]

def simulate_one(tape, sig, sc, fee=1505000, ticket=0.5):
    gs = tape["groups"]
    sig_sig = sig["signal_signature"]
    i = next(idx for idx, g in enumerate(gs) if g["signature"] == sig_sig)
    
    j, slot = O.landing(gs, i, sig["slot"], O.branch(dict(sig, pool=sig.get("pool") or sig.get("curve")), sc))
    ref = A.buy(gs[i]["state"], ticket)
    r = A.buy(gs[j]["state"], ticket)
    if not r:
        return {"status": "failed", "net": -505000, "realized": 0}
    
    st = A.moved(gs[j]["state"], *r)
    h = A.build.inventory(gs[:j+1])
    cf = dict(h)
    n = r[1]
    original = n
    bill = r[0] + A.fee(r[0], st["fee_bps"]) + A.fee(r[0], st["creator_fee_bps"])
    fees = fee
    realized = 0
    venue = "curve"
    clip = False
    peak = -1.0
    legs = []
    
    def quote(amount, cur_st, cur_venue):
        if cur_venue == "curve" and cur_st.get("rtokens_raw", 0) > 0:
            return A.sell(cur_st, amount)
        elif cur_venue == "amm":
            return M.A.sell(cur_st, amount)
        return None

    def proceeds(q, cur_venue):
        return q[0] if cur_venue == "curve" else q["total"]

    for k in range(j+1, len(gs)):
        if n <= 0:
            break
        g = gs[k]
        
        if g["venue"] == "curve":
            if venue != "curve":
                continue
            st, h, cf, ag, err = A.apply(st, g, h, cf)
            if err:
                continue
            if st["rsol_raw"] <= 60_000_000_000:
                q = quote(n, st, "curve")
                if q:
                    got = proceeds(q, "curve")
                    realized += got
                    fees += fee
                    legs.append({"venue": "curve", "reason": "carryover_invalidation", "proceeds": got/1e9, "tokens": n})
                    n = 0
                    break
        
        elif g["venue"] == "amm":
            if venue == "curve":
                z, hh, cc, err = E.opening_state(st, g, tape, h, cf)
                if err:
                    st = dict(g["state"])
                else:
                    st = z
                venue = "amm"
            else:
                st, h, cf, err = M.advance(st, g, h, cf)
                if err:
                    continue
            
            q = quote(n, st, "amm")
            if not q:
                continue
            cur_val = (realized + proceeds(q, "amm") - bill - fees) / bill
            peak = max(peak, cur_val)
            
            if not clip:
                clip = True
                sell_n = original // 2
                q_sell = quote(sell_n, st, "amm")
                if q_sell:
                    got = proceeds(q_sell, "amm")
                    st = M.moved(st, q_sell, False, False)
                    realized += got
                    fees += fee
                    n -= sell_n
                    legs.append({"venue": "amm", "reason": "AMM_open_half", "proceeds": got/1e9, "tokens": sell_n})
            
            elif clip and 1 + cur_val <= (1 + peak) * 0.92:
                q_sell = quote(n, st, "amm")
                if q_sell:
                    got = proceeds(q_sell, "amm")
                    st = M.moved(st, q_sell, False, False)
                    realized += got
                    fees += fee
                    legs.append({"venue": "amm", "reason": "AMM_runner_trail", "proceeds": got/1e9, "tokens": n})
                    n = 0
                    break

    net_sol = (realized - bill - fees) / 1e9
    return {
        "mint": sig["mint"],
        "status": "closed" if n == 0 else "open",
        "net_sol": net_sol,
        "entry_bill": bill / 1e9,
        "realized": realized / 1e9,
        "legs": legs,
        "remaining": n
    }

def main():
    scenarios = [
        ("fast", 1505000),
        ("central80", 1505000),
        ("central85", 1505000),
        ("slow", 1505000),
        ("stress", 2916000),
    ]
    
    tapes = {}
    sigs = {}
    for mint in mints:
        t_path = R.OUT / "execution_tapes" / f"{mint}.json.gz"
        tapes[mint] = json.load(gzip.open(t_path, "rt"))
        sigs[mint] = json.load(open(R.OUT / "signals_by_mint" / f"{mint}.json"))[0]
        for g in tapes[mint]["groups"]:
            E.O.CLOCK[g["slot"]] = g["time"]
            
    print("=== S5 SCENARIO BENCHMARK (All-Attempt Realized SOL PnL) ===")
    results = {}
    for sc, fee in scenarios:
        tot_net = 0.0
        wins = 0
        losses = 0
        nets = []
        for mint in mints:
            res = simulate_one(tapes[mint], sigs[mint], sc, fee)
            tot_net += res["net_sol"]
            nets.append(res["net_sol"])
            if res["net_sol"] > 0:
                wins += 1
            else:
                losses += 1
        wr = wins / len(mints) * 100
        results[sc] = {
            "total_net": tot_net,
            "win_rate": wr,
            "wins": wins,
            "losses": losses,
            "nets": nets,
            "max_winner": max(nets),
            "max_loser": min(nets),
        }
        print(f"Scenario: {sc:10s} | Fee: {fee/1e9:.6f} SOL | Net PnL: {tot_net:+.4f} SOL | Win Rate: {wr:4.1f}% ({wins}W / {losses}L)")
    
    # Check largest winner removal
    c85 = results["central85"]
    c85_ex = c85["total_net"] - c85["max_winner"]
    print(f"\nCentral85 Largest Winner: {c85['max_winner']:+.4f} SOL | PnL without Largest Winner: {c85_ex:+.4f} SOL")

if __name__ == "__main__":
    main()
