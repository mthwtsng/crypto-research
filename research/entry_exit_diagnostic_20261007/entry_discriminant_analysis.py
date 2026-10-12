"""Entry Discriminant Analysis: Analyzes the statistical differences
between True Losses (dumped to zero) and Winners (surged >= +20%)
to discover entry filters that filter out the losers before they are entered.
"""
import gzip, json, pathlib, statistics, collections

P = pathlib.Path(__file__).resolve().parent
REPO_ROOT = P.parents[1]

# Load excursion summary and paths
PATHS_FILE = REPO_ROOT / "research/wallet_curve_entry_discovery_20261007/CORRECTED_CURVE_PATHS.json.gz"
with gzip.open(PATHS_FILE, "rt") as f:
    ALL_PATHS = json.load(f)

# Load bound tapes to check creator
TAPES_DIR = REPO_ROOT / "research/wallet_curve_entry_discovery_20261007/bound_curve_tapes"
tape_by_mint = {}
for tf in TAPES_DIR.glob("*.json.gz"):
    with gzip.open(tf, "rt") as f:
        t = json.load(f)
        tape_by_mint[t["mint"]] = t

from entry_excursion_audit import analyze_path

def main():
    print("="*95)
    print("PHASE 2: ENTRY DISCRIMINANT ANALYSIS (WINNERS VS TRUE LOSSES)")
    print("Finding the exact entry filters to eliminate the 30-35% true losses")
    print("="*95)
    
    sub = [p for p in ALL_PATHS if p['scenario'] == 'central85' and p['status'] == 'filled']
    
    records = []
    for p in sub:
        a = analyze_path(p)
        if not a: continue
        
        # Check creator balance at entry
        t = tape_by_mint.get(p['mint'])
        creator_dumped = True
        creator_held_pct = 0.0
        if t:
            creator = t.get('creator')
            entry_time = p['entry_time']
            c_bought = 0
            c_sold = 0
            c_max = 0
            for g in t.get('groups', []):
                if g['block_time'] > entry_time: break
                for e in g.get('events', []):
                    if e.get('user') == creator:
                        if e.get('buy', False):
                            c_bought += e.get('tokens_raw', 0)
                            c_max = max(c_max, c_bought - c_sold)
                        else:
                            c_sold += e.get('tokens_raw', 0)
            held = c_bought - c_sold
            creator_held_pct = held / c_max if c_max > 0 else 0.0
            creator_dumped = c_max == 0 or (held <= 0.15 * c_max)
            
        is_winner = a['mfe'] >= 0.20
        is_true_loss = a['sequence'] == 'true_loss_dumped_without_pump'
        
        records.append({
            'rule': p['rule'],
            'mint': p['mint'],
            'is_winner': is_winner,
            'is_true_loss': is_true_loss,
            'mfe': a['mfe'],
            'mde': a['mde'],
            'reserve_SOL': p.get('reserve_SOL', 0),
            'age': p.get('age', 0),
            'breadth': p.get('breadth', 0),
            'recent_buyers': p.get('recent_buyers', 0),
            'fresh_buyers': p.get('fresh_buyers', 0),
            'drawdown': p.get('drawdown', 0),
            'dominance': p.get('dominance', 0),
            'creator_dumped': creator_dumped,
            'creator_held_pct': creator_held_pct
        })
        
    winners = [r for r in records if r['is_winner']]
    losers = [r for r in records if r['is_true_loss']]
    
    print(f"Total Analyzed: {len(records)} | Winners (MFE >= +20%): {len(winners)} ({len(winners)/len(records)*100:.1f}%) | True Losses: {len(losers)} ({len(losers)/len(records)*100:.1f}%)")
    print("-" * 95)
    
    features = [
        ('reserve_SOL', 'Reserve (SOL)'),
        ('age', 'Token Age (seconds)'),
        ('breadth', 'Unique Non-Dev Buyers'),
        ('recent_buyers', 'Recent 4s Buyers'),
        ('fresh_buyers', 'Fresh 4s Buyers'),
        ('drawdown', 'Drawdown %'),
        ('dominance', 'Volume Dominance %'),
        ('creator_held_pct', 'Creator Held %')
    ]
    
    print(f"{'Feature':<25} | {'Winners Mean':<14} | {'Winners Median':<14} | {'Losers Mean':<14} | {'Losers Median':<14} | {'Discriminant Power':<18}")
    print("-" * 105)
    
    for feat, label in features:
        w_vals = [r[feat] for r in winners]
        l_vals = [r[feat] for r in losers]
        
        w_mean = statistics.mean(w_vals) if w_vals else 0
        w_med = statistics.median(w_vals) if w_vals else 0
        l_mean = statistics.mean(l_vals) if l_vals else 0
        l_med = statistics.median(l_vals) if l_vals else 0
        
        diff = (w_mean - l_mean) / (l_mean if l_mean != 0 else 1) * 100
        disc = f"{diff:+.1f}% shift"
        print(f"{label:<25} | {w_mean:>12.2f}  | {w_med:>12.2f}  | {l_mean:>12.2f}  | {l_med:>12.2f}  | {disc:<18}")
        
    print("=" * 105)
    
    # PARAMETRIC ENTRY FILTER SWEEP
    print("\nPARAMETRIC ENTRY FILTER SWEEP: TESTING CANDIDATE ENTRY GATES")
    print("Goal: Eliminate True Losses without discarding Winners")
    print("-" * 95)
    
    gates = [
        ("Baseline (No Additional Gates)", lambda r: True),
        ("Gate 1: Reserve >= 10.8 SOL (Survival Shelf)", lambda r: r['reserve_SOL'] >= 10.8),
        ("Gate 2: Buyer Breadth >= 25 Wallets", lambda r: r['breadth'] >= 25),
        ("Gate 3: Buyer Breadth >= 30 Wallets", lambda r: r['breadth'] >= 30),
        ("Gate 4: Creator Held <= 10%", lambda r: r['creator_dumped']),
        ("Gate 5: Reserve >= 10.8 SOL + Breadth >= 25", lambda r: r['reserve_SOL'] >= 10.8 and r['breadth'] >= 25),
        ("Gate 6: Reserve >= 10.8 SOL + Creator Held <= 10%", lambda r: r['reserve_SOL'] >= 10.8 and r['creator_dumped']),
        ("Gate 7: Reserve >= 10.8 SOL + Breadth >= 25 + Creator <= 10%", lambda r: r['reserve_SOL'] >= 10.8 and r['breadth'] >= 25 and r['creator_dumped']),
        ("Gate 8: Reserve >= 15.0 SOL (Late Mature)", lambda r: r['reserve_SOL'] >= 15.0),
        ("Gate 9: Reserve >= 20.0 SOL (Upper Curve)", lambda r: r['reserve_SOL'] >= 20.0),
    ]
    
    print(f"{'Gate Description':<55} | {'Passed':<8} | {'Winners Kept':<13} | {'Losers Cut':<12} | {'New Win Rate':<12}")
    print("-" * 105)
    
    gate_results = {}
    for name, g_fn in gates:
        passed = [r for r in records if g_fn(r)]
        p_w = sum(1 for r in passed if r['is_winner'])
        p_l = sum(1 for r in passed if r['is_true_loss'])
        n_p = len(passed)
        wr = p_w / n_p * 100 if n_p else 0
        losers_cut = len(losers) - p_l
        w_retained_pct = p_w / len(winners) * 100 if winners else 0
        print(f"{name:<55} | {n_p:<8} | {p_w:>2}/{len(winners)} ({w_retained_pct:4.1f}%) | {losers_cut:>2}/{len(losers)} ({losers_cut/len(losers)*100:4.1f}%) | {wr:>5.1f}%")
        gate_results[name] = {
            'passed_count': n_p,
            'winners_kept': p_w,
            'losers_cut': losers_cut,
            'win_rate': wr
        }
    print("=" * 105)
    
    (P / "ENTRY_DISCRIMINANT_RESULTS.json").write_text(json.dumps(gate_results, indent=2))

if __name__ == '__main__':
    main()
