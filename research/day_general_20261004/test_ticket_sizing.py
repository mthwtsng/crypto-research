"""Empirical test of 1-2 SOL ticket sizing and dynamic sizing on accuracy contract engine."""
import collections, datetime, gzip, hashlib, json, pathlib, pickle, sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.append(str(HERE))
sys.path.append(str(HERE / 'helpers'))

import contract_engine as CE
import screen as S
import clock as W
import collect as N

W.rpc = N.rpc

def run_sizing_test():
    # 1. Load tapes and pre-cache times
    tapes = pickle.load(gzip.open(HERE / 'TAPES.pkl.gz', 'rb'))
    for t in tapes:
        for g in t['groups']:
            W.TIMES[g['slot']] = g['block_time']

    # 2. Extract signals on normal tapes
    all_signals = []
    for t in tapes:
        if not t['normal']:
            continue
        sigs = S.detect(t)
        for s in sigs:
            if s['rule'] in ('dislocation', 'mature_fresh'): # Core Positive strategies only
                all_signals.append((t, s))

    print(f"Total eligible signals for Core Positive strategies: {len(all_signals)}")

    # Define sizing models:
    # 1. 'fixed_0.75': baseline (0.75 SOL ticket)
    # 2. 'fixed_1.0': 1.0 SOL ticket
    # 3. 'fixed_1.5': 1.5 SOL ticket
    # 4. 'fixed_2.0': 2.0 SOL ticket
    # 5. 'dynamic_1_to_2': 1.0 SOL default, 2.0 SOL on high conviction:
    #    - Dislocation: drop >= 2.5 SOL and (drop / pre_reserve) >= 0.20
    #    - Mature Breakout: outside >= 50 and reserve >= 14.0 SOL
    SIZING_MODES = ['fixed_0.75', 'fixed_1.0', 'fixed_1.5', 'fixed_2.0', 'dynamic_1_to_2']

    def get_ticket(sig, sizing_mode):
        if sizing_mode == 'fixed_0.75':
            return 0.75
        elif sizing_mode == 'fixed_1.0':
            return 1.0
        elif sizing_mode == 'fixed_1.5':
            return 1.5
        elif sizing_mode == 'fixed_2.0':
            return 2.0
        elif sizing_mode == 'dynamic_1_to_2':
            if sig['rule'] == 'dislocation':
                if sig.get('drop', 0) >= 2.5 and (sig.get('drop', 0) / sig.get('pre_reserve', 1.0)) >= 0.20:
                    return 2.0
                return 1.0
            elif sig['rule'] == 'mature_fresh':
                if sig.get('outside', 0) >= 50 and sig.get('reserve', 0) >= 14.0:
                    return 2.0
                return 1.0
        raise ValueError(f"Unknown sizing mode: {sizing_mode}")

    BRANCHES = ['same_0', 'same_1', 'same_2', 'next_1', 'slow', 'stress']

    # Pre-simulate trades across sizing modes and branches
    # Key: (mint, sig_slot, sig_rule, sizing_mode, branch)
    results = {}
    print("Simulating trades across sizing modes...")
    total = len(all_signals) * len(SIZING_MODES) * len(BRANCHES)
    done = 0

    for t, sig in all_signals:
        for sm in SIZING_MODES:
            tk = get_ticket(sig, sm)
            sig_mod = dict(sig, ticket=tk)
            for br in BRANCHES:
                res = CE.simulate_trade(
                    t=t,
                    sig=sig_mod,
                    branch=br,
                    mode='staged_ladder',
                    holds=CE.BASELINE_HOLDS,
                    fees=CE.FEES_BASE,
                    scheduled_delay=1,
                )
                res['sizing_mode'] = sm
                results[(t['mint'], sig['slot'], sig['rule'], sm, br)] = res
                done += 1
                if done % 1000 == 0:
                    print(f"  {done}/{total} simulated...", flush=True)

    print(f"Completed {done} simulations.")

    # Synthesize Contract Scenarios per intent
    def get_central_draw(mint, slot, rule, p):
        key_str = f"{mint}:{slot}:{rule}"
        h_val = int(hashlib.sha256(key_str.encode()).hexdigest(), 16) / (2**256)
        if h_val < p:
            h2 = h_val / p
            if h2 < 29.0 / 132.0:
                return 'same_0'
            elif h2 < 49.0 / 132.0:
                return 'same_1'
            else:
                return 'same_2'
        else:
            return 'next_1'

    SCENARIOS = ['fast', 'central_p85', 'central_p80', 'slow', 'stress']

    scenario_sets = collections.defaultdict(list)

    for t, sig in all_signals:
        for sm in SIZING_MODES:
            # fast
            scenario_sets[(sm, 'fast')].append(results[(t['mint'], sig['slot'], sig['rule'], sm, 'same_1')])
            # slow
            scenario_sets[(sm, 'slow')].append(results[(t['mint'], sig['slot'], sig['rule'], sm, 'slow')])
            # stress
            scenario_sets[(sm, 'stress')].append(results[(t['mint'], sig['slot'], sig['rule'], sm, 'stress')])
            # central p85
            br_85 = get_central_draw(t['mint'], sig['slot'], sig['rule'], 0.85)
            scenario_sets[(sm, 'central_p85')].append(results[(t['mint'], sig['slot'], sig['rule'], sm, br_85)])
            # central p80
            br_80 = get_central_draw(t['mint'], sig['slot'], sig['rule'], 0.80)
            scenario_sets[(sm, 'central_p80')].append(results[(t['mint'], sig['slot'], sig['rule'], sm, br_80)])

    # Evaluate Portfolios under:
    # A. Capital = 5.0 SOL (position limit 2)
    # B. Capital = 10.0 SOL (position limit 2)
    CAPITALS = [5.0, 10.0]
    priority = {'dislocation': 0, 'mature_fresh': 1}

    out_records = []

    for sm in SIZING_MODES:
        for sc in SCENARIOS:
            rows = scenario_sets[(sm, sc)]
            # First eligible per mint
            first_per_mint = {}
            for r in rows:
                key = (r['decision_slot'], priority[r['rule']])
                if r['mint'] not in first_per_mint or key < first_per_mint[r['mint']][0]:
                    first_per_mint[r['mint']] = (key, r)

            union_trades = [v[1] for v in first_per_mint.values()]

            for cap in CAPITALS:
                ledger = CE.continuous_ledger(union_trades, capital=cap, position_limit=2)
                closed_u = [r for r in union_trades if r['status'] == 'closed']
                largest_w = max([r['pnl'] for r in closed_u], default=0.0)

                out_records.append(dict(
                    sizing_mode=sm,
                    scenario=sc,
                    capital=cap,
                    admitted=ledger['admitted'],
                    closed=ledger['statuses'].get('closed', 0),
                    failed=ledger['failed_count'],
                    unresolved=ledger['unresolved_count'],
                    cash_skips=ledger['cash_skips'],
                    position_skips=ledger['position_skips'],
                    funded_net_pnl=ledger['all_attempt_funded_net_pnl'],
                    return_pct=100.0 * ledger['all_attempt_funded_net_pnl'] / cap,
                    max_drawdown=ledger['max_settled_drawdown'],
                    largest_winner=largest_w,
                    pnl_without_largest=ledger['all_attempt_funded_net_pnl'] - largest_w,
                ))

    # Save to JSON
    out_path = HERE / 'SIZING_EXPERIMENT_RESULTS.json'
    out_path.write_text(json.dumps(out_records, indent=2))
    print(f"Saved sizing experiment results to {out_path.name}")

if __name__ == '__main__':
    run_sizing_test()
