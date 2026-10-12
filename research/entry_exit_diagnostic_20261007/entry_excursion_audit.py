"""Entry Excursion Audit: Measures post-entry price trajectories and excursions
across multiple forward horizons (+5s, +10s, +20s, +30s, +60s, +120s, +180s, +300s, +600s),
evaluating MFE, MDE, and pump vs dip sequence to determine whether entries have predictive edge.
"""
import gzip, json, pathlib, statistics, collections

P = pathlib.Path(__file__).resolve().parent
REPO_ROOT = P.parents[1]
PATHS_FILE = REPO_ROOT / "research/wallet_curve_entry_discovery_20261007/CORRECTED_CURVE_PATHS.json.gz"

with gzip.open(PATHS_FILE, "rt") as f:
    ALL_PATHS = json.load(f)

HORIZONS = [5, 10, 20, 30, 60, 120, 180, 300, 600]

def analyze_path(path):
    states = path.get('states', [])
    if not states:
        return None
        
    start_time = states[0]['time']
    rois = [s.get('quote_ROI') for s in states]
    times = [s['time'] - start_time for s in states]
    
    # Filter valid rois
    valid = [(t, r) for t, r in zip(times, rois) if r is not None]
    if not valid:
        return None
        
    # Horizon returns
    horizon_returns = {}
    for h in HORIZONS:
        # Find closest state at or before h seconds
        h_rois = [r for t, r in valid if t <= h]
        if h_rois:
            horizon_returns[h] = h_rois[-1]
        else:
            horizon_returns[h] = valid[0][1]
            
    # MFE / MDE
    all_r = [r for t, r in valid]
    mfe = max(all_r)
    mde = min(all_r)
    
    mfe_idx = all_r.index(mfe)
    mde_idx = all_r.index(mde)
    time_to_mfe = valid[mfe_idx][0]
    time_to_mde = valid[mde_idx][0]
    
    # Early MDE (within first 3 seconds)
    early_rois = [r for t, r in valid if t <= 3]
    early_mde = min(early_rois) if early_rois else valid[0][1]
    
    # Sequence diagnostic: Did it dip -10% before or after reaching +15% / +20%?
    first_dip_10 = next((t for t, r in valid if r <= -0.10), None)
    first_pump_15 = next((t for t, r in valid if r >= 0.15), None)
    first_pump_20 = next((t for t, r in valid if r >= 0.20), None)
    
    sequence_category = "never_pumped_never_dipped"
    if first_pump_15 is not None and (first_dip_10 is None or first_pump_15 < first_dip_10):
        sequence_category = "clean_winner_pumped_first"
    elif first_dip_10 is not None and first_pump_20 is not None and first_pump_20 > first_dip_10:
        sequence_category = "dipped_then_exploded_shakeout"
    elif first_dip_10 is not None and first_pump_15 is None:
        sequence_category = "true_loss_dumped_without_pump"
    elif first_pump_15 is None and first_dip_10 is None:
        sequence_category = "flat_chop"
        
    # Graduation check
    graduated = any(s['state']['rtokens_raw'] == 0 or s['state']['rsol_raw']/1e9 >= 84.0 for s in states)
    
    return {
        'rule': path['rule'],
        'scenario': path['scenario'],
        'mint': path['mint'],
        'entry_time': path['entry_time'],
        'reserve_SOL': path.get('reserve_SOL', 0),
        'breadth': path.get('breadth', 0),
        'recent_buyers': path.get('recent_buyers', 0),
        'drawdown': path.get('drawdown', 0),
        'horizon_returns': horizon_returns,
        'mfe': mfe,
        'mde': mde,
        'time_to_mfe': time_to_mfe,
        'time_to_mde': time_to_mde,
        'early_mde': early_mde,
        'sequence': sequence_category,
        'graduated': graduated
    }

def run_audit():
    print("="*95)
    print("PHASE 1: SYSTEMATIC ENTRY EXCURSION & MOMENTUM DIAGNOSTIC")
    print("Dataset: 480 counterfactual paths across 600 uncurated launches (Oct 3-4, 2026)")
    print("="*95)
    
    for scenario in ['central85', 'fast', 'slow']:
        sub_paths = [p for p in ALL_PATHS if p['scenario'] == scenario and p['status'] == 'filled']
        analyzed = [analyze_path(p) for p in sub_paths]
        analyzed = [a for a in analyzed if a is not None]
        
        print(f"\n--- SCENARIO: {scenario.upper()} (Filled Trades: {len(analyzed)}) ---")
        
        by_rule = collections.defaultdict(list)
        for a in analyzed:
            by_rule[a['rule']].append(a)
            
        print(f"{'Strategy Rule':<20} | {'Trades':<6} | {'Avg MFE':<9} | {'Avg MDE':<9} | {'>=+10%':<7} | {'>=+20%':<7} | {'>=+50%':<7} | {'Graduated':<9}")
        print("-" * 90)
        
        for rule, items in by_rule.items():
            n = len(items)
            avg_mfe = statistics.mean([i['mfe'] for i in items])
            avg_mde = statistics.mean([i['mde'] for i in items])
            pct_10 = sum(1 for i in items if i['mfe'] >= 0.10) / n * 100
            pct_20 = sum(1 for i in items if i['mfe'] >= 0.20) / n * 100
            pct_50 = sum(1 for i in items if i['mfe'] >= 0.50) / n * 100
            grads = sum(1 for i in items if i['graduated'])
            grad_pct = grads / n * 100
            
            print(f"{rule:<20} | {n:<6} | {avg_mfe*100:>+7.1f}% | {avg_mde*100:>+7.1f}% | {pct_10:>5.1f}% | {pct_20:>5.1f}% | {pct_50:>5.1f}% | {grads:>2} ({grad_pct:4.1f}%)")
            
        # Detailed sequence analysis for central85
        if scenario == 'central85':
            print("\n" + "="*95)
            print("SEQUENCE TIMING AUDIT: WHY DID ENTRIES WIN OR LOSE? (Central85)")
            print("="*95)
            print(f"{'Strategy Rule':<20} | {'Clean Winner (Pumped 1st)':<26} | {'Shakeout (Dipped then Surged)':<30} | {'True Loss (Dumped)':<20}")
            print("-" * 100)
            for rule, items in by_rule.items():
                n = len(items)
                seq_counts = collections.Counter(i['sequence'] for i in items)
                c_clean = seq_counts['clean_winner_pumped_first']
                c_shake = seq_counts['dipped_then_exploded_shakeout']
                c_loss = seq_counts['true_loss_dumped_without_pump']
                print(f"{rule:<20} | {c_clean:>2} ({c_clean/n*100:4.1f}%)                  | {c_shake:>2} ({c_shake/n*100:4.1f}%)                       | {c_loss:>2} ({c_loss/n*100:4.1f}%)")
            print("=" * 100)
            
            print("\nFORWARD HORIZON RETURN TRAJECTORY (% Mean Return at Fixed Horizons)")
            print("-" * 100)
            print(f"{'Strategy Rule':<20} | {'+5s':<8} | {'+10s':<8} | {'+20s':<8} | {'+30s':<8} | {'+60s':<8} | {'+120s':<8} | {'+180s':<8} | {'+300s':<8}")
            print("-" * 100)
            for rule, items in by_rule.items():
                row_str = f"{rule:<20}"
                for h in [5, 10, 20, 30, 60, 120, 180, 300]:
                    mean_h = statistics.mean([i['horizon_returns'].get(h, 0) for i in items])
                    row_str += f" | {mean_h*100:>+6.1f}%"
                print(row_str)
            print("=" * 100)
            
            # Save payload
            (P / "ENTRY_EXCURSION_SUMMARY.json").write_text(json.dumps({
                'scenario': scenario,
                'rules': {
                    r: {
                        'n': len(items),
                        'avg_mfe': statistics.mean([i['mfe'] for i in items]),
                        'avg_mde': statistics.mean([i['mde'] for i in items]),
                        'time_to_mfe': statistics.mean([i['time_to_mfe'] for i in items]),
                        'time_to_mde': statistics.mean([i['time_to_mde'] for i in items]),
                        'pct_reach_10': sum(1 for i in items if i['mfe'] >= 0.10) / len(items) * 100,
                        'pct_reach_20': sum(1 for i in items if i['mfe'] >= 0.20) / len(items) * 100,
                        'pct_reach_50': sum(1 for i in items if i['mfe'] >= 0.50) / len(items) * 100,
                        'sequence_distribution': dict(collections.Counter(i['sequence'] for i in items)),
                        'horizon_means': {
                            h: statistics.mean([i['horizon_returns'].get(h, 0) for i in items])
                            for h in HORIZONS
                        }
                    }
                    for r, items in by_rule.items()
                }
            }, indent=2))

if __name__ == '__main__':
    run_audit()
