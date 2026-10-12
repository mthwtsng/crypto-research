"""Starting Five Diagnostic Replay: Evaluates the Starting 5 strategies
incorporating the Phase 1 & 2 diagnostic insights:
1. Developer Gate (Entry Filter): Eliminate developer-dump trap tokens.
2. Breathing Stop Architecture (Exit Fix): 8s grace, -30% emergency stop, 
   120s patience timer, +20% breakeven ratchet, and 15% trailing stop / AMM carryover.
3. Chronological 15.0 SOL Bankroll Replay with 2 Concurrent Position Limit
4. Calibrated Strategy-Dependent Circuit Breakers (5-10 streak, rolling buffer cushion).

Compliant with BACKTEST_ACCURACY_CONTRACT.md and GEMINI_CALIBRATION.md.
"""
import gzip, json, pathlib, collections, heapq

P = pathlib.Path(__file__).resolve().parent
REPO_ROOT = P.parents[1]

# Load corrected paths
PATHS_FILE = REPO_ROOT / "research/wallet_curve_entry_discovery_20261007/CORRECTED_CURVE_PATHS.json.gz"
with gzip.open(PATHS_FILE, "rt") as f:
    ALL_PATHS = json.load(f)

# Load tapes for developer gate
TAPES_DIR = REPO_ROOT / "research/wallet_curve_entry_discovery_20261007/bound_curve_tapes"
tape_by_mint = {}
for tf in TAPES_DIR.glob("*.json.gz"):
    with gzip.open(tf, "rt") as f:
        t = json.load(f)
        tape_by_mint[t["mint"]] = t

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

def check_developer_gate(path):
    mint = path['mint']
    t = tape_by_mint.get(mint)
    if not t:
        return True # Default allow if tape missing
    creator = t.get('creator')
    if not creator:
        return True
    entry_time = path['entry_time']
    c_bought = 0
    c_sold = 0
    c_max = 0
    for g in t.get('groups', []):
        if g['block_time'] > entry_time:
            break
        for e in g.get('events', []):
            if e.get('user') == creator:
                if e.get('buy', False):
                    c_bought += e.get('tokens_raw', 0)
                    c_max = max(c_max, c_bought - c_sold)
                else:
                    c_sold += e.get('tokens_raw', 0)
    held = c_bought - c_sold
    # Dev gate: Allow if dev never bought (fair launch), or dev held <= 15% of max
    creator_dumped = c_max == 0 or (held <= 0.15 * c_max)
    return creator_dumped

def simulate_breathing_exit(path, grace_sec=8, stop_loss=-0.30, ratchet_arm=0.20, trail_width=0.15):
    states = path.get('states', [])
    entry_time = path['entry_time']
    tokens = path.get('remaining_tokens', 0)
    bill = path.get('entry_bill_lamports', 0)
    
    if not states or not tokens:
        return dict(outcome='no_states', net_lamports=-bill, exit_time=entry_time, roi=-1.0)
        
    start_time = states[0]['time']
    cost = bill + BASE_FEE
    
    peak_roi = 0.0
    ratchet_active = False
    tranche1_sold = False
    t1_proceeds = 0
    rem_tokens = tokens
    
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
            if dt >= grace_sec and roi <= stop_loss:
                proceeds = curve_sell(s['state'], rem_tokens)
                return dict(outcome='stop_loss', net_lamports=t1_proceeds + proceeds - cost, exit_time=s['time'], roi=(t1_proceeds+proceeds-cost)/cost)
        else:
            # Ratchet active: breakeven stop (+1% buffer)
            if roi <= 0.01 and not tranche1_sold:
                proceeds = curve_sell(s['state'], rem_tokens)
                return dict(outcome='ratchet_breakeven', net_lamports=t1_proceeds + proceeds - cost, exit_time=s['time'], roi=(t1_proceeds+proceeds-cost)/cost)
                
        # 2. Tranche 1 Take Profit: Sell 50% at +25%
        if not tranche1_sold and roi >= 0.25:
            t1_tokens = rem_tokens // 2
            t1_proceeds = curve_sell(s['state'], t1_tokens)
            rem_tokens -= t1_tokens
            tranche1_sold = True
            
        # 3. Tranche 2 Trailing Stop or Graduation Carryover
        if tranche1_sold:
            if roi <= peak_roi - trail_width:
                proceeds = curve_sell(s['state'], rem_tokens)
                return dict(outcome='trailing_stop', net_lamports=t1_proceeds + proceeds - cost, exit_time=s['time'], roi=(t1_proceeds+proceeds-cost)/cost)
            # Graduation into AMM
            if s['state']['rtokens_raw'] == 0 or s['state']['rsol_raw']/1e9 >= 84.0:
                amm_p = amm_sell(AMM_QUOTE + 30 * L, AMM_VIRTUAL, AMM_BASE, rem_tokens)
                return dict(outcome='amm_carryover', net_lamports=t1_proceeds + amm_p - cost, exit_time=s['time'], roi=(t1_proceeds+amm_p-cost)/cost)
                
        # 4. Trajectory-aligned patience timer: 120s hold if flat
        if dt >= 120 and peak_roi < 0.10:
            proceeds = curve_sell(s['state'], rem_tokens)
            return dict(outcome='stagnation_120s', net_lamports=proceeds - cost, exit_time=s['time'], roi=(proceeds-cost)/cost)
            
    last_s = states[-1]
    final_proceeds = curve_sell(last_s['state'], rem_tokens)
    return dict(outcome='tape_end', net_lamports=t1_proceeds + final_proceeds - cost, exit_time=last_s['time'], roi=(t1_proceeds+final_proceeds-cost)/cost)

# Calibrated circuit breaker matrix
BREAKER_CONFIG = {
    'broad_recovery': {'streak_limit': 6, 'loss_ceiling_SOL': 0.80, 'cooldown_hours': 3, 'window_hours': 6},
    'fresh_expansion': {'streak_limit': 8, 'loss_ceiling_SOL': 0.80, 'cooldown_hours': 4, 'window_hours': 8},
    'quiet_absorption': {'streak_limit': 10, 'loss_ceiling_SOL': 0.60, 'cooldown_hours': 2, 'window_hours': 4},
    'late_continuation': {'streak_limit': 5, 'loss_ceiling_SOL': 0.80, 'cooldown_hours': 6, 'window_hours': 12},
}

def run_simulation(scenario='central85', use_dev_gate=True, use_breakers=True, grace_sec=8, stop_loss=-0.30):
    sub = [p for p in ALL_PATHS if p['scenario'] == scenario]
    sub = sorted(sub, key=lambda x: (x['entry_time'], x['index']))
    
    cash = CAPITAL
    active_positions = 0
    pending_events = [] # (exit_time, seq, cash_delta, is_close, net_lamports, rule)
    seq = 0
    
    strat_history = collections.defaultdict(list)
    strat_consecutive_losses = collections.defaultdict(int)
    strat_cooldown_until = collections.defaultdict(int)
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
            
            pnl_sol = booked_net / L
            strat_history[r].append((ex_time, pnl_sol))
            if booked_net > 0:
                strat_consecutive_losses[r] = 0
            else:
                strat_consecutive_losses[r] += 1
                
            if use_breakers:
                cfg = BREAKER_CONFIG[r]
                streak_hit = strat_consecutive_losses[r] >= cfg['streak_limit']
                w_start = ex_time - cfg['window_hours'] * 3600
                w_trades = [p for t_time, p in strat_history[r] if t_time >= w_start]
                rolling_pnl = sum(w_trades)
                ceiling_hit = rolling_pnl <= -cfg['loss_ceiling_SOL']
                
                if streak_hit or ceiling_hit:
                    strat_cooldown_until[r] = ex_time + cfg['cooldown_hours'] * 3600
                    strat_trips[r] += 1
                    strat_consecutive_losses[r] = 0
                    
    for p in sub:
        now_time = p['entry_time']
        process_pending(now_time)
        rule = p['rule']
        mint = p['mint']
        
        # 1. Dev Gate check
        if use_dev_gate and not check_developer_gate(p):
            skipped_counts['dev_gate'] += 1
            continue
            
        # 2. Breaker check
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
            
        # Filled trade
        res = simulate_breathing_exit(p, grace_sec=grace_sec, stop_loss=stop_loss)
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
        'dev_gate': use_dev_gate,
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
    print("DIAGNOSTIC UPGRADED STARTING FIVE PORTFOLIO REPLAY")
    print("Developer Gate + Breathing Exits | 15.0 SOL Bankroll | 2 Concurrent Positions")
    print("="*95)
    
    print("\n1. COMPARISON: LEGACY VS DIAGNOSTIC FIXES (Central85 Headline)")
    print("-" * 105)
    print(f"{'Configuration':<42} | {'Trades':<12} | {'Net SOL':<12} | {'Win Rate':<9} | {'PF':<6} | {'Max DD':<9}")
    print("-" * 105)
    
    # Baseline Legacy (No Dev Gate, 3s grace, -15% stop)
    leg = run_simulation('central85', use_dev_gate=False, use_breakers=True, grace_sec=3, stop_loss=-0.15)
    cl_leg = f"{leg['closed']}/{leg['failed']}"
    print(f"{'Legacy Control (No Dev Gate, -15% SL)':<42} | {cl_leg:<12} | {leg['total_net_SOL']:>+10.4f} SOL | {leg['win_rate']:>7.1f}% | {leg['profit_factor']:>5.2f} | {leg['max_drawdown_SOL']:>7.4f} SOL")
    
    # Dev Gate Only (with Legacy Exit)
    dev_only = run_simulation('central85', use_dev_gate=True, use_breakers=True, grace_sec=3, stop_loss=-0.15)
    cl_dev = f"{dev_only['closed']}/{dev_only['failed']}"
    print(f"{'Dev Gate Only (Legacy -15% SL)':<42} | {cl_dev:<12} | {dev_only['total_net_SOL']:>+10.4f} SOL | {dev_only['win_rate']:>7.1f}% | {dev_only['profit_factor']:>5.2f} | {dev_only['max_drawdown_SOL']:>7.4f} SOL")
    
    # Breathing Exit Only (No Dev Gate)
    exit_only = run_simulation('central85', use_dev_gate=False, use_breakers=True, grace_sec=8, stop_loss=-0.30)
    cl_exit = f"{exit_only['closed']}/{exit_only['failed']}"
    print(f"{'Exit Fix Only (Breathing Stop, No Dev Gate)':<42} | {cl_exit:<12} | {exit_only['total_net_SOL']:>+10.4f} SOL | {exit_only['win_rate']:>7.1f}% | {exit_only['profit_factor']:>5.2f} | {exit_only['max_drawdown_SOL']:>7.4f} SOL")
    
    # Full Combined Solution (Dev Gate + Breathing Exit)
    full_on = run_simulation('central85', use_dev_gate=True, use_breakers=True, grace_sec=8, stop_loss=-0.30)
    cl_full_on = f"{full_on['closed']}/{full_on['failed']}"
    print(f"{'Full Fix (Dev Gate + Breathing Stop, Breakers ON)':<42} | {cl_full_on:<12} | {full_on['total_net_SOL']:>+10.4f} SOL | {full_on['win_rate']:>7.1f}% | {full_on['profit_factor']:>5.2f} | {full_on['max_drawdown_SOL']:>7.4f} SOL")
    
    # Full Combined Solution (Breakers OFF)
    full_off = run_simulation('central85', use_dev_gate=True, use_breakers=False, grace_sec=8, stop_loss=-0.30)
    cl_full_off = f"{full_off['closed']}/{full_off['failed']}"
    print(f"{'Full Fix (Dev Gate + Breathing Stop, Breakers OFF)':<42} | {cl_full_off:<12} | {full_off['total_net_SOL']:>+10.4f} SOL | {full_off['win_rate']:>7.1f}% | {full_off['profit_factor']:>5.2f} | {full_off['max_drawdown_SOL']:>7.4f} SOL")
    print("=" * 105)
    
    print("\n2. PERFORMANCE BREAKDOWN BY STRATEGY (Full Fix, Central85, Breakers ON)")
    print("-" * 80)
    print(f"{'Strategy Rule':<24} | {'Trades':<8} | {'Wins':<6} | {'Win Rate':<9} | {'Net SOL':<12}")
    print("-" * 80)
    for r, st in full_on['by_rule'].items():
        print(f"{r:<24} | {st['trades']:<8} | {st['wins']:<6} | {st['wr']:>7.1f}% | {st['net_SOL']:>+10.4f} SOL")
    print("=" * 80)
    
    print("\n3. MULTI-SCENARIO MONOTONICITY AUDIT (Full Fix, Breakers ON)")
    print("-" * 85)
    print(f"{'Placement Scenario':<20} | {'Trades':<12} | {'Net SOL':<12} | {'Win Rate':<9} | {'PF':<6} | {'Max DD':<9}")
    print("-" * 85)
    for sc in ['fast', 'central80', 'central85', 'slow']:
        res = run_simulation(sc, use_dev_gate=True, use_breakers=True, grace_sec=8, stop_loss=-0.30)
        cl_sc = f"{res['closed']}/{res['failed']}"
        print(f"{sc:<20} | {cl_sc:<12} | {res['total_net_SOL']:>+10.4f} SOL | {res['win_rate']:>7.1f}% | {res['profit_factor']:>5.2f} | {res['max_drawdown_SOL']:>7.4f} SOL")
    print("=" * 85)
    
    (P / "STARTING5_DIAGNOSTIC_REPLAY_SUMMARY.json").write_text(json.dumps({
        'legacy': leg, 'dev_only': dev_only, 'exit_only': exit_only, 'full_on': full_on, 'full_off': full_off
    }, indent=2))
    print(f"\nSaved summary to {P / 'STARTING5_DIAGNOSTIC_REPLAY_SUMMARY.json'}")

if __name__ == '__main__':
    main()
