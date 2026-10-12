#!/usr/bin/env python3
"""Bumped-Coin Strategy Cohort Backtest & Comparative Audit.

Complies strictly with:
- research/BACKTEST_ACCURACY_CONTRACT.md
- research/MASTER_STRATEGY_REGISTRY.md

Compares performance on Active Volume-Bumped Coins (>= 15 micro-buys < 0.02 SOL)
vs Organic Non-Bumped Coins across authenticated observation history.
"""

import json
import glob
from collections import defaultdict, Counter

def load_and_classify_mints():
    files = [
        'data/ghost_observations.jsonl',
        'data/archive/ghost_observations_before_ghost-v2-20261012T054024.jsonl',
        'data/archive/ghost_observations_before_ghost-v2-20261012T053309.jsonl'
    ]
    
    mint_trades = defaultdict(list)
    mint_micro_buys = Counter()
    mint_peaks = defaultdict(float)
    mint_creators = {}

    for f in files:
        try:
            with open(f) as fp:
                for line in fp:
                    try:
                        d = json.loads(line)
                        for ev in d.get('events', []):
                            m = ev.get('mint')
                            u = ev.get('user')
                            if not m or not u:
                                continue
                            sol = ev.get('sol_raw', 0) / 1e9
                            rsol = ev.get('rsol_raw', 0) / 1e9
                            is_buy = ev.get('is_buy', False)
                            slot = d.get('slot', 0)
                            ts = ev.get('event_timestamp', 0)

                            if rsol > mint_peaks[m]:
                                mint_peaks[m] = rsol
                            
                            is_creator = mint_creators.get(m) == u
                            if not is_creator and is_buy and sol < 0.02:
                                mint_micro_buys[m] += 1

                            mint_trades[m].append({
                                'slot': slot,
                                'ts': ts,
                                'user': u,
                                'is_buy': is_buy,
                                'sol': sol,
                                'rsol': rsol,
                                'sig': d.get('signature')
                            })
                    except:
                        pass
        except:
            pass

    return mint_trades, mint_micro_buys, mint_peaks

def simulate_s4_trades(mint_trades, mint_micro_buys, mode='bump_aware'):
    """
    mode:
      'baseline': fixed 15 buyers, 0.45 SOL min buy, 15s stagnation scratch
      'bump_aware': 8 buyers, 0.25 SOL min buy on bumped coins + bump inactivity scratch
    """
    results = []

    for mint, trades in mint_trades.items():
        if len(trades) < 10:
            continue
        trades.sort(key=lambda x: (x['slot'], x['ts']))
        
        is_bumped = mint_micro_buys[mint] >= 15
        
        # Track curve state progression
        outside_buyers = set()
        peak_reserve = 0.0
        position = None
        last_bump_slot = 0
        micro_buys_seen = 0

        for i, t in enumerate(trades):
            slot = t['slot']
            sol = t['sol']
            rsol = t['rsol']
            is_buy = t['is_buy']
            user = t['user']

            if is_buy and sol < 0.02:
                micro_buys_seen += 1
                last_bump_slot = slot

            if is_buy and sol >= 0.05:
                outside_buyers.add(user)

            # Check S4 Entry
            if position is None:
                if mode == 'bump_aware':
                    min_buyers = 8 if (is_bumped or micro_buys_seen >= 10) else 15
                    min_buy = 0.25 if (is_bumped or micro_buys_seen >= 10) else 0.45
                else:
                    min_buyers = 15
                    min_buy = 0.45

                if 10.5 <= rsol <= 22.0 and rsol >= peak_reserve and len(outside_buyers) >= min_buyers:
                    if is_buy and sol >= min_buy:
                        # Entry triggered! Apply 70ms landing (simulate 1 slot later or immediate reserve)
                        entry_idx = min(i + 1, len(trades) - 1)
                        entry_rsol = trades[entry_idx]['rsol']
                        position = {
                            'mint': mint,
                            'is_bumped': is_bumped,
                            'entry_slot': slot,
                            'entry_rsol': entry_rsol,
                            'entry_cost_sol': 0.5015,
                            'peak_roi': 0.0,
                            'tranche1_sold': False,
                            'entry_idx': entry_idx
                        }

            # Check S4 Exit if position open
            elif position is not None and i > position['entry_idx']:
                entry_rsol = position['entry_rsol']
                current_roi = (rsol - entry_rsol) / entry_rsol if entry_rsol > 0 else 0.0
                if current_roi > position['peak_roi']:
                    position['peak_roi'] = current_roi

                elapsed_slots = slot - position['entry_slot']

                # Exit Rule 1: Stagnation Scratch (15s = ~37 slots, peak < +5%)
                if not position['tranche1_sold'] and elapsed_slots >= 37 and position['peak_roi'] < 0.05:
                    net_pnl = 0.50 * current_roi - 0.0015
                    results.append({
                        'mint': mint,
                        'is_bumped': is_bumped,
                        'roi': current_roi,
                        'pnl_sol': net_pnl,
                        'reason': '15s Stagnation Scratch'
                    })
                    position = None
                    break

                # Exit Rule 2 (Bump-Aware only): Bump Inactivity Scratch (no bump for > 25 slots, ROI < +3%)
                if mode == 'bump_aware' and position['is_bumped'] and not position['tranche1_sold']:
                    if slot >= last_bump_slot + 25 and current_roi < 0.03:
                        net_pnl = 0.50 * current_roi - 0.0015
                        results.append({
                            'mint': mint,
                            'is_bumped': is_bumped,
                            'roi': current_roi,
                            'pnl_sol': net_pnl,
                            'reason': 'Bump Inactivity Scratch'
                        })
                        position = None
                        break

                # Exit Rule 3: Rejection Stop (>= 15 slots, ROI <= -10%)
                if elapsed_slots >= 15 and current_roi <= -0.10:
                    net_pnl = 0.50 * current_roi - 0.0015
                    results.append({
                        'mint': mint,
                        'is_bumped': is_bumped,
                        'roi': current_roi,
                        'pnl_sol': net_pnl,
                        'reason': 'Rejection Stop (-10%)'
                    })
                    position = None
                    break

                # Exit Rule 4: Scale out 50% at +15%, trail remainder at -6%
                if not position['tranche1_sold'] and current_roi >= 0.15:
                    position['tranche1_sold'] = True

                if position['tranche1_sold'] and current_roi <= position['peak_roi'] - 0.06:
                    net_pnl = 0.50 * current_roi - 0.0015
                    results.append({
                        'mint': mint,
                        'is_bumped': is_bumped,
                        'roi': current_roi,
                        'pnl_sol': net_pnl,
                        'reason': f"Trailing Stop (Peak: +{position['peak_roi']*100:.1f}%)"
                    })
                    position = None
                    break

            if rsol > peak_reserve:
                peak_reserve = rsol

    return results

def compute_metrics(trades, label):
    if not trades:
        return f"{label}: No trades executed."
    n = len(trades)
    wins = [t for t in trades if t['pnl_sol'] > 0]
    losses = [t for t in trades if t['pnl_sol'] <= 0]
    wr = len(wins) / n * 100
    net_pnl = sum(t['pnl_sol'] for t in trades)
    tot_gain = sum(t['pnl_sol'] for t in wins)
    tot_loss = abs(sum(t['pnl_sol'] for t in losses))
    pf = (tot_gain / tot_loss) if tot_loss > 0 else float('inf')

    return (
        f"--- {label} ({n} Trades) ---\n"
        f"  Win Rate:      {wr:.1f}% ({len(wins)}W / {len(losses)}L)\n"
        f"  Net PnL:       {net_pnl:+.4f} SOL\n"
        f"  Profit Factor: {pf:.2f}\n"
        f"  Avg Trade PnL: {net_pnl/n:+.4f} SOL\n"
    )

def main():
    print("Loading authenticated historical observation data...")
    mint_trades, mint_micro_buys, mint_peaks = load_and_classify_mints()
    bumped_count = sum(1 for m, c in mint_micro_buys.items() if c >= 15)
    print(f"Total tokens analyzed: {len(mint_trades)} (Bumped: {bumped_count}, Organic: {len(mint_trades)-bumped_count})")

    # Run simulations
    baseline_trades = simulate_s4_trades(mint_trades, mint_micro_buys, mode='baseline')
    bump_aware_trades = simulate_s4_trades(mint_trades, mint_micro_buys, mode='bump_aware')

    print("\n" + "="*70)
    print("BACKTEST ACCURACY AUDIT: BASELINE CANONICAL VS BUMP-AWARE S4")
    print("="*70)
    
    print("\n[1. BASELINE CANONICAL MODE - ALL TOKENS]")
    print(compute_metrics(baseline_trades, "Baseline Overall"))

    print("\n[2. BUMP-AWARE MODE - COHORT BREAKDOWN]")
    bumped_trades = [t for t in bump_aware_trades if t['is_bumped']]
    organic_trades = [t for t in bump_aware_trades if not t['is_bumped']]
    print(compute_metrics(bumped_trades, "Bump-Aware (Active Bumper Cohort)"))
    print(compute_metrics(organic_trades, "Bump-Aware (Organic Cohort)"))
    print(compute_metrics(bump_aware_trades, "Bump-Aware (Overall Portfolio)"))

if __name__ == '__main__':
    main()
