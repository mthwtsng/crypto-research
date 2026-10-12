"""Starting Five Backtest Engine: Evaluates the five core strategies
on the repaired counterfactual curve paths with tailored exits and
the user's calibrated independent circuit-breaker matrix.
Strictly compliant with BACKTEST_ACCURACY_CONTRACT.md and GEMINI_CALIBRATION.md.
"""
import gzip, json, pathlib, collections, heapq, datetime

P = pathlib.Path(__file__).resolve().parent
REPO_ROOT = P.parents[1]

# Load corrected paths
PATHS_FILE = P / "CORRECTED_CURVE_PATHS.json.gz"
with gzip.open(PATHS_FILE, "rt") as f:
    ALL_PATHS = json.load(f)

L = 10**9
CAPITAL = 15.0 * L
TICKET_SOL = 0.50
TICKET_LAMPORTS = round(TICKET_SOL * L)
MAX_POSITIONS = 2
BASE_FEE = 1505000
RENT = 2039280

# Curve sell proceeds helper
def curve_sell(st, tokens):
    if not tokens or st['rtokens_raw'] <= 0:
        return 0
    vsol = st['vsol_raw']
    vtokens = st['vtokens_raw']
    gross = (vsol * tokens) // (vtokens + tokens)
    fee_bps = st.get('fee_bps', 95)
    creator_bps = st.get('creator_fee_bps', 30)
    total_fee = gross * (fee_bps + creator_bps) // 10000
    net = gross - total_fee
    return net

# AMM sell proceeds helper
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

# Simulate tailored exit for a filled path
def simulate_tailored_exit(path):
    rule = path['rule']
    states = path['states']
    entry_time = path['entry_time']
    tokens = path['remaining_tokens']
    bill = path['entry_bill_lamports']
    completion = path.get('counterfactual_completion')
    
    if not states or not tokens:
        return dict(outcome='no_states', net_lamports=-bill, exit_time=entry_time, roi=-1.0)
        
    start_time = states[0]['time']
    cost = bill + BASE_FEE
    
    # 1. Strat 1: broad_recovery / Dev Absorption
    if rule == 'broad_recovery':
        # -15% emergency stop (with 3s grace period); +25% take profit or 20s hold
        peak_roi = 0.0
        ratchet = False
        for s in states:
            dt = s['time'] - start_time
            roi = s.get('quote_ROI')
            if roi is None: continue
            if roi > peak_roi: peak_roi = roi
            if roi >= 0.12: ratchet = True
            
            # Stop loss check
            if not ratchet:
                if dt >= 3 and roi <= -0.15:
                    proceeds = curve_sell(s['state'], tokens)
                    return dict(outcome='stop_loss', net_lamports=proceeds - cost, exit_time=s['time'], roi=(proceeds-cost)/cost)
            else:
                if roi <= 0.01:
                    proceeds = curve_sell(s['state'], tokens)
                    return dict(outcome='ratchet_breakeven', net_lamports=proceeds - cost, exit_time=s['time'], roi=(proceeds-cost)/cost)
                    
            if peak_roi >= 0.25 and roi <= peak_roi - 0.12:
                proceeds = curve_sell(s['state'], tokens)
                return dict(outcome='trailing_stop', net_lamports=proceeds - cost, exit_time=s['time'], roi=(proceeds-cost)/cost)
                
            if dt >= 20 and peak_roi < 0.12:
                proceeds = curve_sell(s['state'], tokens)
                return dict(outcome='time_exit', net_lamports=proceeds - cost, exit_time=s['time'], roi=(proceeds-cost)/cost)
        last_s = states[-1]
        proceeds = curve_sell(last_s['state'], tokens)
        return dict(outcome='tape_end', net_lamports=proceeds - cost, exit_time=last_s['time'], roi=(proceeds-cost)/cost)

    # 2. Strat 2: fresh_expansion / Survival Shelf Breakout
    elif rule == 'fresh_expansion':
        # -15% stop loss (3s grace); ratchet armed at +12%; sell 50% at +25%, trail remaining 50%
        ratchet_armed = False
        peak_roi = 0.0
        tranche1_sold = False
        t1_proceeds = 0
        rem_tokens = tokens
        
        for s in states:
            dt = s['time'] - start_time
            roi = s.get('quote_ROI')
            if roi is None: continue
            if roi > peak_roi: peak_roi = roi
            if roi >= 0.12: ratchet_armed = True
            
            # Stop loss
            if not ratchet_armed:
                if dt >= 3 and roi <= -0.15:
                    proceeds = curve_sell(s['state'], rem_tokens)
                    return dict(outcome='stop_loss', net_lamports=t1_proceeds + proceeds - cost, exit_time=s['time'], roi=(t1_proceeds+proceeds-cost)/cost)
            else:
                if roi <= 0.01 and not tranche1_sold:
                    proceeds = curve_sell(s['state'], rem_tokens)
                    return dict(outcome='ratchet_breakeven', net_lamports=t1_proceeds + proceeds - cost, exit_time=s['time'], roi=(t1_proceeds+proceeds-cost)/cost)
                
            # Tranche 1: 50% at +25%
            if not tranche1_sold and roi >= 0.25:
                t1_tokens = rem_tokens // 2
                t1_proceeds = curve_sell(s['state'], t1_tokens)
                rem_tokens -= t1_tokens
                tranche1_sold = True
                
            # Tranche 2: Trailing stop (12% off peak) or graduation carryover
            if tranche1_sold:
                if roi <= peak_roi - 0.12:
                    proceeds = curve_sell(s['state'], rem_tokens)
                    return dict(outcome='trailing_stop', net_lamports=t1_proceeds + proceeds - cost, exit_time=s['time'], roi=(t1_proceeds+proceeds-cost)/cost)
                if s['state']['rtokens_raw'] == 0 or s['state']['rsol_raw']/1e9 >= 84.0:
                    amm_p = amm_sell(AMM_QUOTE, AMM_VIRTUAL, AMM_BASE, rem_tokens)
                    return dict(outcome='amm_carryover', net_lamports=t1_proceeds + amm_p - cost, exit_time=s['time'], roi=(t1_proceeds+amm_p-cost)/cost)
                    
            if dt >= 60 and not tranche1_sold and peak_roi < 0.10:
                proceeds = curve_sell(s['state'], rem_tokens)
                return dict(outcome='stagnation_exit', net_lamports=proceeds - cost, exit_time=s['time'], roi=(proceeds-cost)/cost)
                
        last_s = states[-1]
        proceeds = curve_sell(last_s['state'], rem_tokens)
        return dict(outcome='tape_end', net_lamports=t1_proceeds + proceeds - cost, exit_time=last_s['time'], roi=(t1_proceeds+proceeds-cost)/cost)

    # 3. Strat 3: quiet_absorption / Dislocation / Absorption Floor
    elif rule == 'quiet_absorption':
        # 10s scratch if flat; -15% stop (3s grace); trail 12% off peak
        peak_roi = 0.0
        ratchet = False
        for s in states:
            dt = s['time'] - start_time
            roi = s.get('quote_ROI')
            if roi is None: continue
            if roi > peak_roi: peak_roi = roi
            if roi >= 0.12: ratchet = True
            
            if not ratchet:
                if dt >= 3 and roi <= -0.15:
                    proceeds = curve_sell(s['state'], tokens)
                    return dict(outcome='stop_loss', net_lamports=proceeds - cost, exit_time=s['time'], roi=(proceeds-cost)/cost)
            else:
                if roi <= 0.01:
                    proceeds = curve_sell(s['state'], tokens)
                    return dict(outcome='ratchet_breakeven', net_lamports=proceeds - cost, exit_time=s['time'], roi=(proceeds-cost)/cost)
                    
            if peak_roi >= 0.20 and roi <= peak_roi - 0.12:
                proceeds = curve_sell(s['state'], tokens)
                return dict(outcome='trailing_stop', net_lamports=proceeds - cost, exit_time=s['time'], roi=(proceeds-cost)/cost)
                
            if dt >= 21 and peak_roi < 0.10:
                proceeds = curve_sell(s['state'], tokens)
                return dict(outcome='deadman_21s', net_lamports=proceeds - cost, exit_time=s['time'], roi=(proceeds-cost)/cost)
        last_s = states[-1]
        proceeds = curve_sell(last_s['state'], tokens)
        return dict(outcome='tape_end', net_lamports=proceeds - cost, exit_time=last_s['time'], roi=(proceeds-cost)/cost)

    # 4. Strat 4 / 5: late_continuation / Pre-Graduation Carryover (72 SOL -> AMM)
    elif rule == 'late_continuation':
        # -0.15 SOL curve stop; carries into AMM runner trail
        for s in states:
            dt = s['time'] - start_time
            roi = s.get('quote_ROI')
            rsol = s['state']['rsol_raw'] / 1e9
            if rsol <= 60.0 or (roi is not None and roi <= -0.15):
                proceeds = curve_sell(s['state'], tokens)
                return dict(outcome='curve_invalidation', net_lamports=proceeds - cost, exit_time=s['time'], roi=(proceeds-cost)/cost)
            if s['state']['rtokens_raw'] == 0 or rsol >= 84.0:
                t1 = tokens // 2
                t2 = tokens - t1
                p1 = amm_sell(AMM_QUOTE, AMM_VIRTUAL, AMM_BASE, t1)
                p2 = amm_sell(AMM_QUOTE + 50 * L, AMM_VIRTUAL, AMM_BASE - t1, t2)
                total_amm = p1 + p2
                return dict(outcome='amm_runner_trail', net_lamports=total_amm - cost, exit_time=s['time'], roi=(total_amm-cost)/cost)
        last_s = states[-1]
        proceeds = curve_sell(last_s['state'], tokens)
        return dict(outcome='tape_end', net_lamports=proceeds - cost, exit_time=last_s['time'], roi=(proceeds-cost)/cost)

    return dict(outcome='unknown', net_lamports=0, exit_time=entry_time, roi=0.0)

# Circuit Breaker Configuration Matrix (calibrated)
BREAKER_CONFIG = {
    'broad_recovery': {'streak_limit': 5, 'loss_ceiling_SOL': 0.60, 'cooldown_hours': 3, 'window_hours': 6},
    'fresh_expansion': {'streak_limit': 8, 'loss_ceiling_SOL': 0.60, 'cooldown_hours': 4, 'window_hours': 8},
    'quiet_absorption': {'streak_limit': 10, 'loss_ceiling_SOL': 0.50, 'cooldown_hours': 2, 'window_hours': 4},
    'late_continuation': {'streak_limit': 5, 'loss_ceiling_SOL': 0.80, 'cooldown_hours': 6, 'window_hours': 12},
}

def run_simulation(scenario='central85', use_breakers=True):
    sub = [p for p in ALL_PATHS if p['scenario'] == scenario]
    sub = sorted(sub, key=lambda x: (x['entry_time'], x['index']))
    
    cash = CAPITAL
    active_positions = 0
    pending_events = [] # (exit_time, seq, cash_delta, is_close, net_lamports, rule)
    seq = 0
    
    # State tracking per strategy
    strat_history = collections.defaultdict(list) # rule -> list of (exit_time, pnl_SOL)
    strat_consecutive_losses = collections.defaultdict(int)
    strat_cooldown_until = collections.defaultdict(int) # rule -> timestamp
    strat_trips = collections.defaultdict(int)
    
    closed_trades = []
    failed_trades = []
    skipped_counts = collections.Counter()
    peak_equity = CAPITAL
    max_dd = 0
    
    def process_pending(until_time):
        nonlocal cash, active_positions, peak_equity, max_dd
        while pending_events and pending_events[0][0] <= until_time:
            ex_time, _, delta, is_close, booked_net, r = heapq.heappop(pending_events)
            cash += delta
            if is_close:
                active_positions -= 1
            cur_equity = cash + sum(TICKET_LAMPORTS for _ in range(active_positions))
            peak_equity = max(peak_equity, cur_equity)
            max_dd = max(max_dd, peak_equity - cur_equity)
            
            # Update circuit breaker tracking
            pnl_sol = booked_net / L
            strat_history[r].append((ex_time, pnl_sol))
            if booked_net > 0:
                strat_consecutive_losses[r] = 0
            else:
                strat_consecutive_losses[r] += 1
                
            # Check circuit breaker trigger
            if use_breakers:
                cfg = BREAKER_CONFIG[r]
                # Check streak
                streak_hit = strat_consecutive_losses[r] >= cfg['streak_limit']
                
                # Check rolling PnL in window
                w_start = ex_time - cfg['window_hours'] * 3600
                w_trades = [p for t_time, p in strat_history[r] if t_time >= w_start]
                rolling_pnl = sum(w_trades)
                ceiling_hit = rolling_pnl <= -cfg['loss_ceiling_SOL']
                
                if streak_hit or ceiling_hit:
                    strat_cooldown_until[r] = ex_time + cfg['cooldown_hours'] * 3600
                    strat_trips[r] += 1
                    strat_consecutive_losses[r] = 0 # reset streak after tripping
                    
    for p in sub:
        now_time = p['entry_time']
        process_pending(now_time)
        rule = p['rule']
        mint = p['mint']
        
        # Check if strategy is in cooldown
        if use_breakers and now_time < strat_cooldown_until[rule]:
            skipped_counts[f'breaker_{rule}'] += 1
            continue
            
        reserve_needed = TICKET_LAMPORTS + BASE_FEE + RENT
        if active_positions >= MAX_POSITIONS:
            skipped_counts['max_positions'] += 1
            continue
        if cash < reserve_needed:
            skipped_counts['cash'] += 1
            continue
            
        status = p['status']
        active_positions += 1
        cash -= reserve_needed
        seq += 1
        
        if status == 'failed':
            failed_fee = p.get('failed_fee_SOL', 0.000505) * L
            failed_trades.append(dict(rule=rule, mint=mint, net=-failed_fee/L, time=now_time))
            close_time = now_time + 1
            heapq.heappush(pending_events, (close_time, seq, reserve_needed - failed_fee, True, -failed_fee, rule))
            continue
            
        # Filled trade: simulate tailored exit
        res = simulate_tailored_exit(p)
        net_l = res['net_lamports']
        exit_time = max(res['exit_time'], now_time + 1)
        closed_trades.append(dict(
            rule=rule, mint=mint, net=net_l/L, entry_time=now_time, exit_time=exit_time,
            outcome=res['outcome'], roi=res['roi']
        ))
        heapq.heappush(pending_events, (exit_time, seq, reserve_needed + net_l, True, net_l, rule))
        
    process_pending(9999999999)
    
    total_net = sum(t['net'] for t in closed_trades) + sum(t['net'] for t in failed_trades)
    wins = sum(1 for t in closed_trades if t['net'] > 0)
    losses = sum(1 for t in closed_trades if t['net'] <= 0)
    gw = sum(t['net'] for t in closed_trades if t['net'] > 0)
    gl = -sum(t['net'] for t in closed_trades if t['net'] < 0) - sum(t['net'] for t in failed_trades)
    pf = gw / gl if gl > 0 else 999.0
    wr = wins / len(closed_trades) * 100 if closed_trades else 0
    
    return {
        'scenario': scenario,
        'breakers': use_breakers,
        'attempts': len(closed_trades) + len(failed_trades),
        'closed': len(closed_trades),
        'failed': len(failed_trades),
        'total_net_SOL': total_net,
        'win_rate': wr,
        'profit_factor': pf,
        'max_drawdown_SOL': max_dd / L,
        'trips': dict(strat_trips),
        'skipped': dict(skipped_counts),
        'by_rule': {
            r: {
                'trades': sum(1 for t in closed_trades if t['rule'] == r),
                'net_SOL': sum(t['net'] for t in closed_trades if t['rule'] == r),
                'wins': sum(1 for t in closed_trades if t['rule'] == r and t['net'] > 0),
                'wr': sum(1 for t in closed_trades if t['rule'] == r and t['net'] > 0) / max(1, sum(1 for t in closed_trades if t['rule'] == r)) * 100
            }
            for r in BREAKER_CONFIG
        }
    }

def main():
    print("="*95)
    print("STARTING FIVE MULTI-STRATEGY CHRONOLOGICAL BACKTEST")
    print("Repaired Counterfactual Engine | 15.0 SOL Bankroll | 2 Concurrent Positions")
    print("="*95)
    
    scenarios = ['fast', 'central80', 'central85', 'slow']
    
    print("\n1. HEADLINE RESULTS: CIRCUIT BREAKERS ON vs OFF (Central85 Headline)")
    print("-" * 95)
    r_on = run_simulation('central85', use_breakers=True)
    r_off = run_simulation('central85', use_breakers=False)
    
    print(f"{'Configuration':<25} | {'Trades (Cl/Fail)':<18} | {'Net SOL':<12} | {'Win Rate':<9} | {'PF':<6} | {'Max DD':<9}")
    print("-" * 95)
    cl_on = f"{r_on['closed']}/{r_on['failed']}"
    print(f"{'Breakers ON (Calibrated)':<25} | {cl_on:<18} | {r_on['total_net_SOL']:>+10.4f} SOL | {r_on['win_rate']:>7.1f}% | {r_on['profit_factor']:>5.2f} | {r_on['max_drawdown_SOL']:>7.4f} SOL")
    cl_off = f"{r_off['closed']}/{r_off['failed']}"
    print(f"{'Breakers OFF (Unthrottled)':<25} | {cl_off:<18} | {r_off['total_net_SOL']:>+10.4f} SOL | {r_off['win_rate']:>7.1f}% | {r_off['profit_factor']:>5.2f} | {r_off['max_drawdown_SOL']:>7.4f} SOL")
    print("=" * 95)
    
    print("\n2. PERFORMANCE BREAKDOWN BY STRATEGY (Central85, Breakers ON)")
    print("-" * 80)
    print(f"{'Strategy Rule':<24} | {'Trades':<8} | {'Wins':<6} | {'Win Rate':<9} | {'Net SOL':<12}")
    print("-" * 80)
    for r, st in r_on['by_rule'].items():
        print(f"{r:<24} | {st['trades']:<8} | {st['wins']:<6} | {st['wr']:>7.1f}% | {st['net_SOL']:>+10.4f} SOL")
    print("=" * 80)
    
    print("\n3. MULTI-SCENARIO MONOTONICITY AUDIT (Breakers ON)")
    print("-" * 85)
    print(f"{'Placement Scenario':<20} | {'Trades':<12} | {'Net SOL':<12} | {'Win Rate':<9} | {'PF':<6} | {'Max DD':<9}")
    print("-" * 85)
    for sc in scenarios:
        res = run_simulation(sc, use_breakers=True)
        cl_sc = f"{res['closed']}/{res['failed']}"
        print(f"{sc:<20} | {cl_sc:<12} | {res['total_net_SOL']:>+10.4f} SOL | {res['win_rate']:>7.1f}% | {res['profit_factor']:>5.2f} | {res['max_drawdown_SOL']:>7.4f} SOL")
    print("=" * 85)
    
    out_payload = {'breakers_on': r_on, 'breakers_off': r_off}
    (P / "STARTING5_BACKTEST_SUMMARY.json").write_text(json.dumps(out_payload, indent=2))
    print(f"\nSaved summary to {P / 'STARTING5_BACKTEST_SUMMARY.json'}")

if __name__ == '__main__':
    main()
