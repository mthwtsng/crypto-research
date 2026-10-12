"""Exit Optimization Audit: Systematically benchmarks and tunes exit policies
to resolve the shakeout problem and capture the 63% of coins running >= +20%.
Evaluates grace periods, stop loss depths, breakeven ratchets, trailing stops,
and migration carryovers under BACKTEST_ACCURACY_CONTRACT.md.
"""
import gzip, json, pathlib, statistics, collections

P = pathlib.Path(__file__).resolve().parent
REPO_ROOT = P.parents[1]

PATHS_FILE = REPO_ROOT / "research/wallet_curve_entry_discovery_20261007/CORRECTED_CURVE_PATHS.json.gz"
with gzip.open(PATHS_FILE, "rt") as f:
    ALL_PATHS = json.load(f)

# AMM constants
L = 10**9
AMM_BASE = 206_900_000_000_000
AMM_QUOTE = 67_405_853_768
AMM_VIRTUAL = 17_584_505_288

def amm_sell(quote_res, virtual_res, base_res, tokens_in):
    k = (quote_res + virtual_res) * base_res
    new_base = base_res + tokens_in
    new_quote_virtual = k // new_base
    gross_quote = (quote_res + virtual_res) - new_quote_virtual
    fee = gross_quote * 55 // 10000
    net_proceeds = gross_quote - fee
    return net_proceeds

def curve_sell(st, tokens):
    if not tokens or st['rtokens_raw'] <= 0:
        return 0
    vsol = st['vsol_raw']
    vtokens = st['vtokens_raw']
    gross = (vsol * tokens) // (vtokens + tokens)
    fee_bps = st.get('fee_bps', 95)
    creator_bps = st.get('creator_fee_bps', 30)
    total_fee = gross * (fee_bps + creator_bps) // 10000
    return gross - total_fee

def evaluate_exit(path, grace_sec, stop_loss, ratchet_arm, trail_width, carryover_amm=True):
    states = path.get('states', [])
    if not states:
        return None
    start_time = states[0]['time']
    tokens = path['remaining_tokens']
    bill = path['entry_bill_lamports']
    cost = bill + 1505000
    
    peak_roi = 0.0
    ratchet_active = False
    tranche1_sold = False
    t1_proceeds = 0
    rem_tokens = tokens
    exit_outcome = 'tape_end'
    exit_time = states[-1]['time']
    final_proceeds = 0
    
    for s in states:
        dt = s['time'] - start_time
        roi = s.get('quote_ROI')
        if roi is None: continue
        if roi > peak_roi: peak_roi = roi
        
        # Arm ratchet
        if roi >= ratchet_arm:
            ratchet_active = True
            
        # 1. Stop loss check
        if not ratchet_active:
            # Enforce grace period
            if dt >= grace_sec and roi <= stop_loss:
                proceeds = curve_sell(s['state'], rem_tokens)
                return {
                    'outcome': 'stop_loss',
                    'net_lamports': t1_proceeds + proceeds - cost,
                    'roi': (t1_proceeds + proceeds - cost) / cost,
                    'dt': dt
                }
        else: # Ratchet active: stop moves to breakeven (+1% buffer)
            if roi <= 0.01 and not tranche1_sold:
                proceeds = curve_sell(s['state'], rem_tokens)
                return {
                    'outcome': 'ratchet_breakeven',
                    'net_lamports': t1_proceeds + proceeds - cost,
                    'roi': (t1_proceeds + proceeds - cost) / cost,
                    'dt': dt
                }
                
        # 2. Tranche 1 Take Profit: Sell 50% at +25%
        if not tranche1_sold and roi >= 0.25:
            t1_tokens = rem_tokens // 2
            t1_proceeds = curve_sell(s['state'], t1_tokens)
            rem_tokens -= t1_tokens
            tranche1_sold = True
            
        # 3. Tranche 2 Trailing Stop or Graduation
        if tranche1_sold:
            if roi <= peak_roi - trail_width:
                proceeds = curve_sell(s['state'], rem_tokens)
                return {
                    'outcome': 'trailing_stop',
                    'net_lamports': t1_proceeds + proceeds - cost,
                    'roi': (t1_proceeds + proceeds - cost) / cost,
                    'dt': dt
                }
            # Graduation into AMM
            if carryover_amm and (s['state']['rtokens_raw'] == 0 or s['state']['rsol_raw']/1e9 >= 84.0):
                amm_p = amm_sell(AMM_QUOTE + 30 * L, AMM_VIRTUAL, AMM_BASE, rem_tokens)
                return {
                    'outcome': 'amm_carryover',
                    'net_lamports': t1_proceeds + amm_p - cost,
                    'roi': (t1_proceeds + amm_p - cost) / cost,
                    'dt': dt
                }
                
        # 4. Long stagnation exit: 120s with zero progress
        if dt >= 120 and peak_roi < 0.10:
            proceeds = curve_sell(s['state'], rem_tokens)
            return {
                'outcome': 'stagnation_120s',
                'net_lamports': proceeds - cost,
                'roi': (proceeds - cost) / cost,
                'dt': dt
            }
            
    last_s = states[-1]
    final_proceeds = curve_sell(last_s['state'], rem_tokens)
    return {
        'outcome': 'tape_end',
        'net_lamports': t1_proceeds + final_proceeds - cost,
        'roi': (t1_proceeds + final_proceeds - cost) / cost,
        'dt': states[-1]['time'] - start_time
    }

def main():
    print("="*95)
    print("PHASE 3: EXIT OPTIMIZATION AUDIT (SOLVING THE SHAKEOUT PROBLEM)")
    print("Dataset: 105 filled central85 paths across 600 launches")
    print("="*95)
    
    sub = [p for p in ALL_PATHS if p['scenario'] == 'central85' and p['status'] == 'filled']
    
    # Grid search across exit parameters
    grace_options = [0, 2, 4, 6]
    sl_options = [-0.10, -0.12, -0.15, -0.18, -0.20]
    ratchet_options = [0.10, 0.12, 0.15]
    trail_options = [0.10, 0.12, 0.15]
    
    recipes = []
    
    # 1. Baseline legacy (0s grace, -10% SL, no ratchet, fixed 25% TP)
    recipes.append({
        'name': 'Legacy Control (Rigid -10% SL, 0s Grace)',
        'grace': 0, 'sl': -0.10, 'ratchet': 0.99, 'trail': 0.08
    })
    
    # 2. Breathing stop variants
    for g in [2, 4, 6]:
        for sl in [-0.12, -0.15, -0.18]:
            for r in [0.12, 0.15]:
                for tr in [0.12, 0.15]:
                    name = f"Grace {g}s | SL {int(sl*100)}% | Ratchet +{int(r*100)}% | Trail {int(tr*100)}%"
                    recipes.append({
                        'name': name,
                        'grace': g, 'sl': sl, 'ratchet': r, 'trail': tr
                    })
                    
    results = []
    for rec in recipes:
        trades = [evaluate_exit(p, rec['grace'], rec['sl'], rec['ratchet'], rec['trail']) for p in sub]
        trades = [t for t in trades if t is not None]
        
        wins = sum(1 for t in trades if t['net_lamports'] > 0)
        n = len(trades)
        wr = wins / n * 100
        tot_net = sum(t['net_lamports'] for t in trades) / L
        gw = sum(t['net_lamports'] for t in trades if t['net_lamports'] > 0) / L
        gl = -sum(t['net_lamports'] for t in trades if t['net_lamports'] < 0) / L
        pf = gw / gl if gl > 0 else 999.0
        
        # Shakeout recoveries: trades that experienced < -10% drawdown but ended positive
        shakeouts_saved = sum(1 for p, t in zip(sub, trades) if min([s.get('quote_ROI', 0) for s in p['states'] if s.get('quote_ROI') is not None] or [0]) <= -0.10 and t['net_lamports'] > 0)
        
        results.append({
            'name': rec['name'],
            'win_rate': wr,
            'net_SOL': tot_net,
            'pf': pf,
            'wins': wins,
            'losses': n - wins,
            'shakeouts_saved': shakeouts_saved,
            'grace': rec['grace'],
            'sl': rec['sl'],
            'ratchet': rec['ratchet'],
            'trail': rec['trail']
        })
        
    # Sort by Net SOL
    results_sorted = sorted(results, key=lambda x: x['net_SOL'], reverse=True)
    
    print(f"\nTOP 10 EXIT ARCHITECTURES RANKED BY NET SOL (Central85, 0.50 SOL Ticket)")
    print("-" * 105)
    print(f"{'Exit Policy':<50} | {'Win Rate':<9} | {'Net SOL':<12} | {'PF':<6} | {'W / L':<9} | {'Shakeouts Saved':<16}")
    print("-" * 105)
    
    for r in results_sorted[:10]:
        wl = f"{r['wins']}/{r['losses']}"
        print(f"{r['name']:<50} | {r['win_rate']:>7.1f}% | {r['net_SOL']:>+10.4f} SOL | {r['pf']:>5.2f} | {wl:<9} | {r['shakeouts_saved']:>2} saved")
    print("-" * 105)
    
    # Print the legacy baseline for comparison
    legacy = next(r for r in results if 'Legacy' in r['name'])
    wl_leg = f"{legacy['wins']}/{legacy['losses']}"
    print(f"{legacy['name']:<50} | {legacy['win_rate']:>7.1f}% | {legacy['net_SOL']:>+10.4f} SOL | {legacy['pf']:>5.2f} | {wl_leg:<9} | {legacy['shakeouts_saved']:>2} saved")
    print("=" * 105)
    
    (P / "EXIT_OPTIMIZATION_RESULTS.json").write_text(json.dumps(results_sorted, indent=2))

if __name__ == '__main__':
    main()
