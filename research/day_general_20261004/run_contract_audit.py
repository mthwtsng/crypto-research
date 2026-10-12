"""Run full accuracy contract audit across 600-coin day dataset.

Follows BACKTEST_ACCURACY_CONTRACT.md, GEMINI_CALIBRATION.md, and CODEX_CALIBRATION.md.
"""
import collections, concurrent.futures, datetime, gzip, hashlib, json, pathlib, pickle, statistics, sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.append(str(HERE))
sys.path.append(str(HERE / 'helpers'))

import contract_engine as CE
import screen as S
import clock as W
import collect as N

# Plug in RPC cache from collect
W.rpc = N.rpc

def run_audit():
    print("=" * 70)
    print("STARTING BACKTEST ACCURACY CONTRACT AUDIT")
    print(f"Timestamp: {datetime.datetime.now(datetime.timezone.utc).isoformat()}")
    print("=" * 70)

    # 1. Load tapes
    tapes_path = HERE / 'TAPES.pkl.gz'
    tapes = pickle.load(gzip.open(tapes_path, 'rb'))
    print(f"Loaded {len(tapes)} tapes from {tapes_path.name}")

    # Cache clock times from tapes
    for t in tapes:
        for g in t['groups']:
            W.TIMES[g['slot']] = g['block_time']
    print(f"Pre-cached {len(W.TIMES)} clock slots")

    # 2. Detect signals on normal-SOL tapes
    triggered_coins = []
    signals_count = 0
    signals_by_rule = collections.Counter()
    all_signals = [] # list of (tape, sig)

    for t in tapes:
        if not t['normal']:
            continue
        sigs = S.detect(t)
        if sigs:
            triggered_coins.append(t)
            signals_count += len(sigs)
            for s in sigs:
                signals_by_rule[s['rule']] += 1
                all_signals.append((t, s))

    print(f"Triggered coins: {len(triggered_coins)} of {sum(t['normal'] for t in tapes)} normal tapes")
    print(f"Total signals detected: {signals_count}")
    for rule, c in signals_by_rule.items():
        print(f"  {rule:15s}: {c} signals")

    # 3. Placement branches to evaluate for each signal:
    # 'same_0', 'same_1', 'same_2', 'next_1', 'slow', 'stress'
    # Note: 'fast' is identical to 'same_1'
    BRANCHES = ['same_0', 'same_1', 'same_2', 'next_1', 'slow', 'stress']

    # We evaluate both modes: 'full_timer' and 'staged_ladder'
    MODES = ['full_timer', 'staged_ladder']

    # We evaluate:
    # A. Baseline holds: velocity 10s, liquidity 10s, dislocation 8s, mature_fresh 45s
    # B. Development candidate: velocity 4s (look count = 3: 10s, 4s, 3s)
    # C. Development candidate: mature_fresh 25s (look count = 2: 45s, 25s)

    HOLD_CONFIGS = {
        'baseline': CE.BASELINE_HOLDS,
        'dev_v4': CE.DEVELOPMENT_HOLDS,
        'dev_v4_m25': CE.DEVELOPMENT_HOLDS_25S,
    }

    print("\nSimulating trade outcomes across all branches, modes, and hold configs...")

    # Build simulation jobs
    # To be extremely efficient and avoid redundant re-runs:
    # Key: (mint, sig_slot, sig_rule, hold_config, mode, fee_regime, sched_delay, branch)
    raw_results = {}

    total_jobs = len(all_signals) * len(HOLD_CONFIGS) * len(MODES) * len(BRANCHES)
    print(f"Total branch evaluations: {total_jobs}")

    # Run simulations
    done = 0
    for t, sig in all_signals:
        for h_name, holds in HOLD_CONFIGS.items():
            for mode in MODES:
                for br in BRANCHES:
                    res = CE.simulate_trade(
                        t=t,
                        sig=sig,
                        branch=br,
                        mode=mode,
                        holds=holds,
                        fees=CE.FEES_BASE,
                        scheduled_delay=1,
                    )
                    raw_results[(t['mint'], sig['slot'], sig['rule'], h_name, mode, 'base', 1, br)] = res
                    done += 1
                    if done % 1000 == 0:
                        print(f"  Evaluated {done}/{total_jobs} runs...", flush=True)

    print(f"Completed {done} base-fee evaluations.")

    # Also run sensitivity jobs for central and stress scenarios:
    # 1. Historical entry average fee (0.002916 SOL)
    # 2. 3-slot scheduled sell delay
    sensitivity_results = {}
    for t, sig in all_signals:
        for br in BRANCHES:
            for mode in MODES:
                # Fee sensitivity
                r_fee = CE.simulate_trade(
                    t=t,
                    sig=sig,
                    branch=br,
                    mode=mode,
                    holds=CE.BASELINE_HOLDS,
                    fees=CE.FEES_HISTORICAL,
                    scheduled_delay=1,
                )
                sensitivity_results[(t['mint'], sig['slot'], sig['rule'], 'baseline', mode, 'historical_fee', 1, br)] = r_fee

                # Delay sensitivity
                r_delay = CE.simulate_trade(
                    t=t,
                    sig=sig,
                    branch=br,
                    mode=mode,
                    holds=CE.BASELINE_HOLDS,
                    fees=CE.FEES_BASE,
                    scheduled_delay=3,
                )
                sensitivity_results[(t['mint'], sig['slot'], sig['rule'], 'baseline', mode, 'delay_3', 3, br)] = r_delay

    print(f"Completed {len(sensitivity_results)} sensitivity evaluations.")

    # 4. Synthesize Contract Scenarios per intent
    # Contract Section 3:
    # - fast: branch 'same_1'
    # - slow: branch 'slow'
    # - stress: branch 'stress'
    # - central_p80: deterministic fixed-seed per intent draw (p=0.80) AND weighted expectation
    # - central_p85: deterministic fixed-seed per intent draw (p=0.85) AND weighted expectation

    def get_central_draw(mint, slot, rule, p):
        """Deterministic seed per intent draw per contract section 3."""
        key_str = f"{mint}:{slot}:{rule}"
        h_val = int(hashlib.sha256(key_str.encode()).hexdigest(), 16) / (2**256)
        if h_val < p:
            # Same slot branch
            h2 = h_val / p
            if h2 < 29.0 / 132.0:
                return 'same_0'
            elif h2 < (29.0 + 20.0) / 132.0:
                return 'same_1'
            else:
                return 'same_2'
        else:
            return 'next_1'

    # Build scenario trade rows for each scenario
    SCENARIOS = ['fast', 'central_p80', 'central_p85', 'slow', 'stress']

    scenario_trade_sets = collections.defaultdict(list)

    for (t, sig) in all_signals:
        for h_name in HOLD_CONFIGS:
            for mode in MODES:
                # 1. Fast
                rf = raw_results[(t['mint'], sig['slot'], sig['rule'], h_name, mode, 'base', 1, 'same_1')]
                scenario_trade_sets[(h_name, mode, 'base', 1, 'fast')].append(rf)

                # 2. Slow
                rs = raw_results[(t['mint'], sig['slot'], sig['rule'], h_name, mode, 'base', 1, 'slow')]
                scenario_trade_sets[(h_name, mode, 'base', 1, 'slow')].append(rs)

                # 3. Stress
                rx = raw_results[(t['mint'], sig['slot'], sig['rule'], h_name, mode, 'base', 1, 'stress')]
                scenario_trade_sets[(h_name, mode, 'base', 1, 'stress')].append(rx)

                # 4. Central p=0.80 draw
                br_80 = get_central_draw(t['mint'], sig['slot'], sig['rule'], 0.80)
                r_c80 = raw_results[(t['mint'], sig['slot'], sig['rule'], h_name, mode, 'base', 1, br_80)]
                scenario_trade_sets[(h_name, mode, 'base', 1, 'central_p80')].append(r_c80)

                # 5. Central p=0.85 draw
                br_85 = get_central_draw(t['mint'], sig['slot'], sig['rule'], 0.85)
                r_c85 = raw_results[(t['mint'], sig['slot'], sig['rule'], h_name, mode, 'base', 1, br_85)]
                scenario_trade_sets[(h_name, mode, 'base', 1, 'central_p85')].append(r_c85)

    # Also build sensitivity scenario sets for baseline
    for (t, sig) in all_signals:
        for mode in MODES:
            # Historical fee
            rf_h = sensitivity_results[(t['mint'], sig['slot'], sig['rule'], 'baseline', mode, 'historical_fee', 1, 'same_1')]
            rs_h = sensitivity_results[(t['mint'], sig['slot'], sig['rule'], 'baseline', mode, 'historical_fee', 1, 'slow')]
            rx_h = sensitivity_results[(t['mint'], sig['slot'], sig['rule'], 'baseline', mode, 'historical_fee', 1, 'stress')]
            br_80 = get_central_draw(t['mint'], sig['slot'], sig['rule'], 0.80)
            br_85 = get_central_draw(t['mint'], sig['slot'], sig['rule'], 0.85)
            rc80_h = sensitivity_results[(t['mint'], sig['slot'], sig['rule'], 'baseline', mode, 'historical_fee', 1, br_80)]
            rc85_h = sensitivity_results[(t['mint'], sig['slot'], sig['rule'], 'baseline', mode, 'historical_fee', 1, br_85)]

            scenario_trade_sets[('baseline', mode, 'historical_fee', 1, 'fast')].append(rf_h)
            scenario_trade_sets[('baseline', mode, 'historical_fee', 1, 'slow')].append(rs_h)
            scenario_trade_sets[('baseline', mode, 'historical_fee', 1, 'stress')].append(rx_h)
            scenario_trade_sets[('baseline', mode, 'historical_fee', 1, 'central_p80')].append(rc80_h)
            scenario_trade_sets[('baseline', mode, 'historical_fee', 1, 'central_p85')].append(rc85_h)

            # Delay 3 sensitivity
            rf_d = sensitivity_results[(t['mint'], sig['slot'], sig['rule'], 'baseline', mode, 'delay_3', 3, 'same_1')]
            rs_d = sensitivity_results[(t['mint'], sig['slot'], sig['rule'], 'baseline', mode, 'delay_3', 3, 'slow')]
            rx_d = sensitivity_results[(t['mint'], sig['slot'], sig['rule'], 'baseline', mode, 'delay_3', 3, 'stress')]
            rc80_d = sensitivity_results[(t['mint'], sig['slot'], sig['rule'], 'baseline', mode, 'delay_3', 3, br_80)]
            rc85_d = sensitivity_results[(t['mint'], sig['slot'], sig['rule'], 'baseline', mode, 'delay_3', 3, br_85)]

            scenario_trade_sets[('baseline', mode, 'delay_3', 3, 'fast')].append(rf_d)
            scenario_trade_sets[('baseline', mode, 'delay_3', 3, 'slow')].append(rs_d)
            scenario_trade_sets[('baseline', mode, 'delay_3', 3, 'stress')].append(rx_d)
            scenario_trade_sets[('baseline', mode, 'delay_3', 3, 'central_p80')].append(rc80_d)
            scenario_trade_sets[('baseline', mode, 'delay_3', 3, 'central_p85')].append(rc85_d)

    print("\nScenario trade sets compiled successfully.")

    # 5. Summarize Standalone Strategies
    # For each rule, scenario, mode, hold_config
    summary_table = []
    for (h_name, mode, fee_name, delay, sc), rows in sorted(scenario_trade_sets.items()):
        by_rule = collections.defaultdict(list)
        for r in rows:
            by_rule[r['rule']].append(r)

        for rule, r_rows in sorted(by_rule.items()):
            attempts = len(r_rows)
            closed = [r for r in r_rows if r['status'] == 'closed']
            failed = [r for r in r_rows if r['status'] == 'failed']
            unresolved = [r for r in r_rows if r['status'] == 'unresolved']

            closed_wins = [r['pnl'] for r in closed if r['pnl'] > 0]
            closed_losses = [r['pnl'] for r in closed if r['pnl'] <= 0]
            closed_pnl = sum(r['pnl'] for r in closed)
            all_attempt_pnl = sum(r['pnl'] for r in r_rows if r.get('pnl') is not None)
            all_attempt_marked = sum(r['marked_pnl'] for r in r_rows if r.get('marked_pnl') is not None)

            pf = sum(closed_wins) / abs(sum(closed_losses)) if sum(closed_losses) else 999.0
            win_rate = (len(closed_wins) / len(closed) * 100.0) if closed else 0.0

            # Funded standalone ledger
            f_ledger = CE.continuous_ledger(r_rows, capital=5.0, position_limit=2)

            summary_table.append(dict(
                hold_config=h_name,
                rule=rule,
                mode=mode,
                fee_name=fee_name,
                delay=delay,
                scenario=sc,
                attempts=attempts,
                closed_count=len(closed),
                failed_count=len(failed),
                unresolved_count=len(unresolved),
                closed_pnl=closed_pnl,
                all_attempt_pnl=all_attempt_pnl,
                all_attempt_marked=all_attempt_marked,
                profit_factor=pf,
                win_rate=win_rate,
                funded_net_zero=f_ledger['all_attempt_funded_net_pnl'],
                funded_net_marked=f_ledger['all_attempt_marked_net_pnl'],
                max_drawdown=f_ledger['max_settled_drawdown'],
                largest_winner=max([r['pnl'] for r in closed], default=0.0),
                pnl_without_largest=closed_pnl - max([r['pnl'] for r in closed], default=0.0),
            ))

    # 6. Continuous Shared Funded Portfolios
    # Router 1: 'all_three' (Dislocation > Velocity > Mature)
    # Router 2: 'core_positive' (Dislocation > Mature; excludes negative-EV velocity and liquidity)
    ROUTERS = {
        'all_three': {'dislocation': 0, 'velocity': 1, 'mature_fresh': 2},
        'core_positive': {'dislocation': 0, 'mature_fresh': 1},
    }
    portfolio_results = []

    for (h_name, mode, fee_name, delay, sc), rows in sorted(scenario_trade_sets.items()):
        for r_name, priority in ROUTERS.items():
            first_per_mint = {}
            for r in rows:
                if r['rule'] not in priority:
                    continue
                key = (r['decision_slot'], priority[r['rule']])
                if r['mint'] not in first_per_mint or key < first_per_mint[r['mint']][0]:
                    first_per_mint[r['mint']] = (key, r)

            union_trades = [v[1] for v in first_per_mint.values()]
            p_ledger = CE.continuous_ledger(union_trades, capital=5.0, position_limit=2)

            closed_union = [r for r in union_trades if r['status'] == 'closed']
            largest_w = max([r['pnl'] for r in closed_union], default=0.0)

            portfolio_results.append(dict(
                router=r_name,
                hold_config=h_name,
                mode=mode,
                fee_name=fee_name,
                delay=delay,
                scenario=sc,
                total_signals=len(union_trades),
                admitted=p_ledger['admitted'],
                closed=p_ledger['statuses'].get('closed', 0),
                failed=p_ledger['failed_count'],
                unresolved=p_ledger['unresolved_count'],
                funded_net_zero=p_ledger['all_attempt_funded_net_pnl'],
                funded_net_marked=p_ledger['all_attempt_marked_net_pnl'],
                closed_only_pnl=p_ledger['closed_only_net_pnl'],
                max_drawdown=p_ledger['max_settled_drawdown'],
                ending_cash=p_ledger['ending_cash_zero_recovery'],
                largest_winner=largest_w,
                pnl_without_largest=p_ledger['all_attempt_funded_net_pnl'] - largest_w,
            ))

    # Save outputs
    out_data = {
        'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'dataset': 'day_general_20261004 (600 launches, Oct 3-4, 2026)',
        'screening': 'Frozen natural-volume screen (57 triggered coins, 177 signals)',
        'summary_standalone': summary_table,
        'portfolio_results': portfolio_results,
    }

    out_file = HERE / 'CONTRACT_AUDIT_RESULTS.json'
    out_file.write_text(json.dumps(out_data, indent=2))
    print(f"\nSaved contract audit results to {out_file.name}")

    return out_data

if __name__ == '__main__':
    run_audit()
