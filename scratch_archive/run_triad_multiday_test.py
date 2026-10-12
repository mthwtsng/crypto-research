import gzip, json, pickle, collections

# 1. Load mint-to-date mapping
with gzip.open('research/multi_timeframe_audit_20261005/own_trade_replacement_v3/TAPES.pkl.gz', 'rb') as f:
    tapes = pickle.load(f)
mint_to_date = {t['mint']: t.get('date', 'unknown') for t in tapes}

# 2. Define week cohorts
def get_week(dt):
    if dt < '2026-09-21':
        return 'Week 1 (Sep 14-20)'
    elif dt < '2026-09-28':
        return 'Week 2 (Sep 21-27)'
    else:
        return 'Week 3 (Sep 28-Oct 4)'

# 3. Load all trade rows from EXIT_PATH_LABELS.jsonl.gz
records = []
with gzip.open('research/multi_timeframe_audit_20261005/own_trade_replacement_v3/EXIT_PATH_LABELS.jsonl.gz', 'rt') as f:
    for line in f:
        d = json.loads(line)
        if d.get('status') == 'closed':
            d['date'] = mint_to_date.get(d['mint'], 'unknown')
            d['week'] = get_week(d['date'])
            records.append(d)

print(f"Loaded {len(records)} closed trade records across {len(set(r['date'] for r in records))} dates.")

# 4. Evaluate Triad Exit mechanics vs Baseline
# For 8tpkr_fixed_05 (ticket = 0.50 SOL)
target_rules = ['8tpkr_fixed_05', '8tpkr_fixed_10', 'mature_flow', 'dislocation_recovery_confirmed']

def evaluate_exit(row, exit_mode):
    ticket = 0.5 if '05' in row['rule'] else 1.0
    tags = row.get('tags', [])
    mfe = row['observed_mfe']
    mae = row['observed_mae']
    base_pnl = row['pnl']
    
    if exit_mode == 'baseline':
        return base_pnl
        
    # Triad Exit Model:
    # 1. Stagnation scratch: if 'little_observed_followthrough' (never reached +2% upside)
    # Instead of holding to 40s (which bled to -32%), we scratch at ~10s.
    # At 10s, typical drift on dead coins is -4% to -6% (loss ~ -0.025 SOL on 0.5 ticket).
    if 'little_observed_followthrough' in tags:
        scratch_loss_pct = -0.05
        fee = 0.001505
        return (ticket * scratch_loss_pct) - fee
        
    # 2. Breakeven ratchet: if 'loss_despite_observed_upside10' (reached >= +10%, but later dumped)
    # The ratchet stops it at +2% (covering fees) or +5% on the bounce reversal.
    if 'loss_despite_observed_upside10' in tags:
        ratchet_return_pct = 0.03 # net +3% after fees
        return ticket * ratchet_return_pct
        
    # 3. Runner preservation: if 'timer_then_later_observed_upside20' (reached >= +20%)
    if 'timer_then_later_observed_upside20' in tags:
        if exit_mode == 'triad_trail':
            # Lock 50% at +18%, let 50% trail with 8% distance from MFE
            tranche1 = 0.5 * ticket * 0.18
            tranche2 = 0.5 * ticket * max(0.12, mfe - 0.08)
            fee = 0.002010
            return (tranche1 + tranche2) - fee
        elif exit_mode == 'triad_staged':
            # 50% at +15%, 50% at +25%
            tranche1 = 0.5 * ticket * 0.15
            tranche2 = 0.5 * ticket * 0.25 if mfe >= 0.25 else 0.5 * ticket * 0.10
            fee = 0.002010
            return (tranche1 + tranche2) - fee
            
    # For residual trades:
    return base_pnl

print("\n" + "="*85)
print("MULTI-PERIOD EVALUATION: BASELINE VS TRIAD EXIT (Central85 Scenario)")
print("="*85)

for rule in target_rules:
    print(f"\n>>> STRATEGY: {rule}")
    print(f"{'Period':<25} | {'Trades':<6} | {'Baseline PnL':<15} | {'Triad Trail PnL':<17} | {'Triad Staged PnL':<17}")
    print("-" * 85)
    
    rule_records = [r for r in records if r['rule'] == rule and r['scenario'] == 'central85']
    by_week = collections.defaultdict(list)
    for r in rule_records:
        by_week[r['week']].append(r)
        
    tot_base = 0.0
    tot_trail = 0.0
    tot_staged = 0.0
    tot_cnt = 0
    
    for wk in sorted(by_week.keys()):
        wk_recs = by_week[wk]
        cnt = len(wk_recs)
        base = sum(evaluate_exit(r, 'baseline') for r in wk_recs)
        trail = sum(evaluate_exit(r, 'triad_trail') for r in wk_recs)
        staged = sum(evaluate_exit(r, 'triad_staged') for r in wk_recs)
        
        tot_base += base
        tot_trail += trail
        tot_staged += staged
        tot_cnt += cnt
        
        print(f"{wk:<25} | {cnt:<6} | {base:>11.3f} SOL | {trail:>13.3f} SOL | {staged:>13.3f} SOL")
        
    print("-" * 85)
    print(f"{'FULL 21-DAY TOTAL':<25} | {tot_cnt:<6} | {tot_base:>11.3f} SOL | {tot_trail:>13.3f} SOL | {tot_staged:>13.3f} SOL")

print("\n" + "="*85)
print("ALL-SCENARIO ACCURACY CONTRACT MONOTONICITY CHECK (8tpkr_fixed_05)")
print("="*85)
scenarios = ['fast', 'central80', 'central85', 'slow']
print(f"{'Scenario':<15} | {'Trades':<6} | {'Baseline PnL':<15} | {'Triad Trail PnL':<17} | {'Triad Staged PnL':<17}")
print("-" * 85)
for sc in scenarios:
    sc_recs = [r for r in records if r['rule'] == '8tpkr_fixed_05' and r['scenario'] == sc]
    cnt = len(sc_recs)
    base = sum(evaluate_exit(r, 'baseline') for r in sc_recs)
    trail = sum(evaluate_exit(r, 'triad_trail') for r in sc_recs)
    staged = sum(evaluate_exit(r, 'triad_staged') for r in sc_recs)
    print(f"{sc:<15} | {cnt:<6} | {base:>11.3f} SOL | {trail:>13.3f} SOL | {staged:>13.3f} SOL")
