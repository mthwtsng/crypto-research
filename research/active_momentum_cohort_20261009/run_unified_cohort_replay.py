#!/usr/bin/env python3
"""
Unified Multi-Strategy Active Cohort Replay (562 Admitted Coins).

Evaluates the unified cash-funded portfolio on the 562 verified active coins
from the August 18 - September 7, 2026 active momentum cohort:
- S1: Dev Dump Absorption (15s relief wick scalp, target +20%, 15pp trail)
- S2: 10.8 SOL Shelf (Freshness age<=240s, outside_buyers<=80, min_tokens_bps=9000, 35s hold)
- S3: Deadman Dip Bounce Tight Scalp (2-group confirmation, 0s grace, hard -6% stop, 20s bounce deadline)
- S4: Upper ATH Breakout (4s rejection grace, -8% stop, +20% half target, 6% runner trail)
- S5: Pre-Migration Carryover (Dual-venue Raydium AMM exits: 50% open dump + 8% runner trail)

Execution & Accounting:
- Shared 15.0 SOL cash bankroll, 0.50 SOL base ticket (0.25 SOL cooldown probe)
- Mandatory Headline: Central85 placement scenario (plus Fast, Central80, Slow sensitivities)
- Concurrency Limits: Max 2 (Headline), Max 5, Max 10, Uncapped
- Breakers ON vs Breakers OFF
"""

import collections
import concurrent.futures
import datetime
import gzip
import hashlib
import importlib.util
import json
import os
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
COHORT_DIR = ROOT / "research/active_momentum_cohort_20261009"
BATCH2_DIR = COHORT_DIR / "strategy_validation_batch2"

sys.path.insert(0, str(BATCH2_DIR / "deps"))
for folder in ("research/day_general_20261004/helpers", "research/core_plan_audit_20261007",
               "research/wallet_curve_entry_discovery_20261007", "research/amm_multiday_20261006"):
    sys.path.insert(0, str(ROOT / folder))

import signals as S
import curve_adapter as A
import amm_counterparty as M
import repair_amm_custody as AC
AP = AC.B

# Cashback replaces creator fee
_decoded_amm_events = M.A.events
def effective_amm_events(tx):
    result = []
    for decoded in _decoded_amm_events(tx):
        e = dict(decoded)
        if e['kind'] in ('BuyEvent', 'SellEvent') and e.get('cashback_fee_basis_points', 0):
            if e.get('coin_creator_fee_basis_points', 0):
                raise ValueError('simultaneous_creator_cashback_requires_separate_rounding')
            e['decoded_coin_creator_fee_basis_points'] = e.get('coin_creator_fee_basis_points', 0)
            e['decoded_coin_creator_fee'] = e.get('coin_creator_fee', 0)
            e['coin_creator_fee_basis_points'] = e['cashback_fee_basis_points']
            e['coin_creator_fee'] = e.get('cashback', 0)
        result.append(e)
    return result
M.A.events = effective_amm_events

def loadmodule(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

E = loadmodule("active_validation_engine", BATCH2_DIR / "engine_frozen.py")
F = loadmodule("active_validation_ledger", ROOT / "research/core_plan_audit_20261007/ledger.py")
RPC = loadmodule("active_validation_rpc", COHORT_DIR / "rpc_pool.py")

def wallet_view(t):
    owners = {}
    groups = []
    for g in t['groups']:
        if g.get('source_status') == 'failed':
            continue
        owners.update({k:v for k,v in g.get('account_owners', {}).items() if v is not None})
        ops = []
        for op in g['custody_ops']:
            if op['kind'] == 'trade':
                owner = op.get('inventory_owner') or owners.get(op['owner'])
                if not owner: raise ValueError('unknown_signal_wallet_owner')
                ops.append(dict(op, owner=owner))
            elif op['kind'] == 'transfer':
                src, dst = owners.get(op['from_owner']), owners.get(op['to_owner'])
                if src and dst:
                    if src != dst: ops.append(dict(op, from_owner=src, to_owner=dst))
                elif op['raw']:
                    raise ValueError('unknown_signal_transfer_wallet_owner')
            else:
                raise ValueError('unsupported_signal_custody_operation')
        groups.append(dict(g, custody_ops=ops))
    return dict(t, groups=groups, inventory_key='wallet')

def detect_signals(t):
    wallet = wallet_view(t)
    end = min(t['creation_time'] + 1800, t['end_time'])
    decision = dict(wallet, groups=[g for g in wallet['groups'] if g['block_time'] <= end], end_time=end)
    sigs, errors = S.detect(decision)
    if errors: raise ValueError(errors)
    final = []
    for sig in sigs:
        if sig['rule'] != 's3_deadman':
            final.append(sig)
            continue
        first = None
        count = 0
        for g in decision['groups'][sig['index'] + 1:]:
            if g['slot'] > sig['slot'] + 2 or g['state']['rtokens_raw'] == 0: break
            buyers = {e['user'] for e in g['events'] if e['buy'] and e['user'] != t['creator'] and e['sol_raw'] >= 50_000_000}
            if buyers:
                count += 1
                if first is None: first = buyers
            if count >= 2 and buyers - first:
                reserve = g['state']['rsol_raw'] / 1e9
                if 8 <= reserve <= 18:
                    final.append(dict(sig, original_signal_signature=sig['signal_signature'],
                        original_signal_slot=sig['slot'], signal_signature=g['signature'],
                        slot=g['slot'], time=g['block_time'], reserve=reserve, confirmation_buy_groups=count))
                break
    return final

def prepare_single_pool(mint):
    raw_path = COHORT_DIR / "raw_pools" / f"{mint}.json.gz"
    with gzip.open(raw_path, 'rt') as f:
        raw = json.load(f)
    m = raw['migration']
    txs = [z for z in raw['transactions'] if z['meta']['err'] is None]
    tmp_path = COHORT_DIR / "probes" / f"{mint}_prep.json.gz"
    tmp_path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(tmp_path, 'wt') as f:
        json.dump(dict(coverage=dict(raw['coverage'], migration=m, complete=True,
                       through_time=raw['coverage']['upper_time']), transactions=txs), f)
    tape, audit = AP.prepare(tmp_path)
    tape['coverage'].update(raw['coverage'])
    tape['coverage']['through_time'] = raw['coverage']['upper_time']
    tape['coverage']['successful_receipts_parsed'] = True
    if tmp_path.exists(): tmp_path.unlink()
    if not audit['good']: raise ValueError(dict(reason='pool_prepare_parity', errors=audit['errors'][:3]))
    
    by = {z['transaction']['signatures'][0]:z for z in txs}
    gs = tape['groups']
    for g in gs:
        g['raw_events'] = [e for e in M.A.events(by[g['signature']]) if e.get('pool') == m['pool']]
        g['custody_ops'],g['custody_error'] = AC.custody(by[g['signature']],m,g['trades'],g)
        g.pop('raw_events', None)
    v = gs[0]['state']['virtual']
    for g in gs[1:]:
        if g.get('reserve_shift') and not g['trades'] and (sum(o.get('raw',0) for o in g['custody_ops'] if o['kind'] == 'sweep') != g['reserve_shift'] or g.get('custody_error')):
            if not g.get('fee_sweep') or g['pre'][1]-g['post'][1] != g['reserve_shift'] or g.get('custody_error') not in (None,'sweep_instruction_event_count'):
                raise ValueError('unauthenticated_quiet_sweep')
            g['custody_ops'] = [dict(kind='sweep',raw=g['reserve_shift'])]
            g['custody_error'] = None
        g['before']['virtual'] = v
        st = dict(g['before'])
        for op in g['custody_ops']:
            if op['kind'] == 'sweep':
                v += op['raw']; st['virtual'] = v; st['quote'] -= op['raw']; continue
            if op['kind'] != 'trade': continue
            e = op['event']
            if e['virtual'] != v: raise ValueError('virtual_prestate_gap')
            val = dict(st,historical_rates=e['rates'])
            q = (M.A.buy(val,e['gross']) if e['ix'].startswith('buy_exact_quote_in') else M.A.exact_buy(val,e['n'])) if e['buy'] else M.A.sell(val,e['n'])
            if not q or (q['n'],q['q']) != (e['n'],e['q']): raise ValueError('pool_source_quote_mismatch')
            st = M.moved(st,q,e['buy'],e.get('deferred',False)); v = st['virtual']
        g['state']['virtual'] = v
    st,h,cf = dict(gs[0]['state']),{},{}
    for g in gs[1:]:
        z,hh,cc,err = M.advance(st,g,h,cf)
        if err or hh != cc or z.get('source_reverts',0) or any(z[k] != g['state'][k] for k in ('base','quote','virtual','supply')):
            raise ValueError(dict(reason='pool_whole_source_parity',signature=g['signature'],error=err))
        st,h,cf = z,hh,cc
    return tape

def config(rule, recipe='refined_actual'):
    cfg = dict(tailored_trail_basis='percentage_points')
    if recipe == 'registry_control':
        if rule in ('s1_dev_absorption','s2_survival_shelf'): cfg[rule[:2]+'_dynamic_exit'] = True
        if rule == 's3_deadman': cfg.update(s3_extended_hold=60,s3_grace=8,s3_relative_price_stop=.12,s3_dynamic_arm=.75,s3_dynamic_width=.20)
        if rule == 's4_upper_ath': cfg['s4_remove_short_timeout'] = True
        return cfg
    if rule == 's1_dev_absorption': cfg.update(s1_dynamic_exit=True,s1_trough_grace=0,s1_target=.20,runner_max_hold=15)
    if rule == 's2_survival_shelf': cfg.update(s2_dynamic_exit=True,s2_target=.30,min_tokens_bps=9000,runner_max_hold=35)
    if rule == 's3_deadman': cfg.update(s3_extended_hold=20,s3_grace=0,s3_relative_price_stop=.06,s3_dynamic_arm=.35,s3_dynamic_width=.10)
    if rule == 's4_upper_ath':
        cfg.update(s4_remove_short_timeout=True,s4_rejection_grace=4,s4_stop=.08)
        if recipe == 'refined_documented40': cfg['runner_max_hold'] = 40
    if rule == 's5_carryover': cfg['s5_amm_timeout'] = None
    return cfg

def main():
    print("=" * 80)
    print(" UNIFIED 562-COIN ACTIVE MOMENTUM COHORT REPLAY")
    print("=" * 80)
    
    with open(COHORT_DIR / "COHORT_MANIFEST.json") as f:
        manifest = json.load(f)
    print(f"Loaded manifest with {len(manifest['coins'])} admitted coins.")
    
    # 1. Load existing simulations from batch2
    batch2_replay_path = BATCH2_DIR / "REPLAY.json.gz"
    all_results = []
    done_keys = set()
    if batch2_replay_path.exists():
        with gzip.open(batch2_replay_path, 'rt') as f:
            batch2_results = json.load(f)
        all_results.extend(batch2_results)
        for r in batch2_results:
            done_keys.add((r['recipe'], r['mint'], r['rule'], r['signal_signature'], r['scenario'], r['fee'], r['ticket'], r.get('placement_seed', 0)))
        print(f"Loaded {len(batch2_results)} prior trade executions from batch2.")

    # 2. Identify new coins and signals
    batch2_tapes_dir = BATCH2_DIR / "execution_tapes"
    batch2_mints = {os.path.basename(p).replace('.json.gz', '') for p in batch2_tapes_dir.glob('*.json.gz')}
    
    new_signals = []
    new_tapes = {}
    bound_dir = COHORT_DIR / "bound_curve_tapes"
    
    for row in manifest['coins']:
        mint = row['mint']
        if mint in batch2_mints:
            continue
        bound_path = bound_dir / f"{mint}.json.gz"
        if not bound_path.exists():
            continue
        with gzip.open(bound_path, 'rt') as f:
            t = json.load(f)
        sigs = detect_signals(t)
        if not sigs:
            continue
            
        gs = [dict(g, venue='curve', trades=g['events'], time=g['block_time']) for g in t['groups']]
        if t.get('migration'):
            try:
                pool = prepare_single_pool(mint)
                complete = next(g for g in gs if g['state']['rtokens_raw'] == 0)
                t['migration_quote_difference'] = complete['state']['rsol_raw'] - pool['groups'][0]['before']['quote']
                gs.extend(dict(g, venue='amm') for g in pool['groups'])
                t['end_time'] = pool['coverage']['through_time']
            except Exception as e:
                print(f"Note: pool prepare exception on {mint}: {e}")
        gs.sort(key=lambda g: (g['slot'], g['index']))
        t.update(groups=gs, inventory_key='token_account')
        new_tapes[mint] = t
        new_signals.extend(sigs)
        for g in gs:
            E.O.CLOCK[g['slot']] = g['time']

    print(f"Identified {len(new_tapes)} new coins producing {len(new_signals)} new signals.")
    
    # 3. Simulate new signals
    recipes = ['refined_actual', 'refined_documented40', 'registry_control']
    scenarios = [(s, 1505000) for s in ['fast', 'central80', 'central85', 'slow']]
    
    new_jobs = []
    for sig in new_signals:
        for recipe in recipes:
            if recipe != 'registry_control' and sig['rule'] == 's2_survival_shelf' and not (sig.get('age_seconds', 0) <= 240 and sig.get('outside_buyers', 0) <= 80):
                continue
            for sc, fee in scenarios:
                for ticket in (0.5, 0.25):
                    k = (recipe, sig['mint'], sig['rule'], sig['signal_signature'], sc, fee, ticket, 0)
                    if k not in done_keys:
                        new_jobs.append((recipe, sig, sc, fee, ticket, 0))

    print(f"Simulating {len(new_jobs)} trade executions across 4 workers...")
    t0 = time.time()
    
    def run_job(job):
        recipe, sig, sc, fee, ticket, seed = job
        tape = new_tapes[sig['mint']]
        cfg = config(sig['rule'], recipe)
        cfg['_placement_seed'] = seed
        res = E.simulate(tape, sig, sc, 'lower', ticket, fee, cfg)
        return dict(res, recipe=recipe, placement_seed=seed)
        
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futures = {ex.submit(run_job, j): j for j in new_jobs}
        for fut in concurrent.futures.as_completed(futures):
            res = fut.result()
            all_results.append(res)
            
    print(f"Completed simulation in {time.time()-t0:.2f}s. Total combined trades: {len(all_results)}.")

    # 4. Evaluate funded accounts across portfolio combinations
    print("\nEvaluating cash-funded portfolios (15.0 SOL bankroll)...")
    portfolios = dict(
        trio=["s5_carryover", "s3_deadman", "s4_upper_ath"],
        core4=["s2_survival_shelf", "s3_deadman", "s4_upper_ath", "s5_carryover"],
        all5=["s1_dev_absorption", "s2_survival_shelf", "s3_deadman", "s4_upper_ath", "s5_carryover"]
    )
    
    accounts = []
    cells = sorted({(r['recipe'], r['scenario'], r['fee'], r.get('placement_seed', 0)) for r in all_results})
    
    for recipe, sc, fee, seed in cells:
        for scope, rules in portfolios.items():
            subset = [r for r in all_results if (r['recipe'], r['scenario'], r['fee'], r.get('placement_seed', 0)) == (recipe, sc, fee, seed) and r['rule'] in rules]
            for cap in (2, 5, 10, None):
                for breakers in (True, False):
                    acct = F.funded(subset, breakers, 'portfolio', position_limit=cap)
                    
                    # Rule breakdown
                    rule_breakdown = {}
                    for r_name in rules:
                        admitted = [r for r in acct["admitted"] if r["rule"] == r_name]
                        settled = sum(r["net_SOL"] for r in admitted if r["status"] != "unresolved")
                        marked = sum(r["net_SOL"] + r["mark_SOL"] for r in admitted if r["status"] == "unresolved")
                        closed = [r for r in admitted if r["status"] == "closed"]
                        wr = sum(r["net_SOL"] > 0 for r in closed) / len(closed) if closed else 0.0
                        rule_breakdown[r_name] = {
                            "attempts": len(admitted),
                            "closed": len(closed),
                            "settled_sol": settled,
                            "open_mark_sol": marked,
                            "combined_sol": settled + marked,
                            "win_rate": wr,
                        }
                    
                    acct.update(
                        recipe=recipe, scenario=sc, fee=fee, placement_seed=seed,
                        portfolio=scope, position_limit=cap, breakers=breakers,
                        rules_breakdown=rule_breakdown
                    )
                    accounts.append(acct)
                    
    print(f"Generated {len(accounts)} funded portfolio ledger evaluations.")
    
    # Save full dataset
    out_dir = ROOT / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_json = out_dir / "ACTIVE_COHORT_MOMENTUM_REPLAY_REPORT.json"
    with open(out_json, "w") as f:
        json.dump(accounts, f, indent=2)
    print(f"Saved full funded results to {out_json}.")
    
    # Print Headline Tables
    print("\n" + "=" * 105)
    print("      UNIFIED 562-COIN ACTIVE MOMENTUM COHORT REPLAY REPORT")
    print("      Bankroll: 15.0 SOL Cash | Ticket: 0.50 SOL (0.25 probe) | Fee: 1,505,000 lamports")
    print("=" * 105)
    
    for scope_key, scope_title in [
        ("all5", "FULL 5-STRATEGY PORTFOLIO (S1 WICK + S2 SHELF + S3 DEADMAN + S4 ATH + S5 AMM)"),
        ("core4", "CORE 4-STRATEGY PORTFOLIO (S2 SHELF + S3 DEADMAN + S4 ATH + S5 AMM)"),
        ("trio", "WINNING TRIO PORTFOLIO (S3 DEADMAN + S4 ATH + S5 AMM)")
    ]:
        print("\n" + "#" * 105)
        print(f"  {scope_title}")
        print("#" * 105)
        
        for b_mode in [True, False]:
            b_label = "CIRCUIT BREAKERS ON" if b_mode else "CIRCUIT BREAKERS OFF"
            print(f"\n--- {b_label} (CENTRAL85 MANDATORY HEADLINE) ---")
            print(f" {'Cap':<12} {'Settled SOL':<15} {'Open Mark':<14} {'Combined Net':<16} {'Win Rate':<10} {'Profit Factor':<14} {'Attempts (C/F/U)'}")
            print(" " + "-" * 100)
            
            for cap in [2, 5, 10, None]:
                c_tag = f"Max {cap}" if cap is not None else "Uncapped"
                match = next((a for a in accounts if a['recipe'] == 'refined_actual' and a['scenario'] == 'central85'
                              and a['fee'] == 1505000 and a['portfolio'] == scope_key and a['position_limit'] == cap
                              and a['breakers'] == b_mode and a.get('placement_seed', 0) == 0), None)
                if match:
                    wr = (match.get('win_rate') or 0.0) * 100
                    pf = match.get('profit_factor') or 0.0
                    print(f" {c_tag:<12} {match['settled_net_SOL']:>+9.4f} SOL   {match['unresolved_marked_pnl_SOL']:>+8.4f} SOL   {match['last_valid_marked_net_SOL']:>+10.4f} SOL "
                          f"{wr:>5.1f}%     {pf:>6.3f}         "
                          f"{match['attempts']:>3} ({match['closed']}C/{match['failed']}F/{match['unresolved']}U)")

        # Strategy Attribution for Central85 Max 2
        match_p2 = next((a for a in accounts if a['recipe'] == 'refined_actual' and a['scenario'] == 'central85'
                         and a['fee'] == 1505000 and a['portfolio'] == scope_key and a['position_limit'] == 2
                         and a['breakers'] == True and a.get('placement_seed', 0) == 0), None)
        if match_p2 and match_p2.get('rules_breakdown'):
            print(f"\n--- STRATEGY ATTRIBUTION: MAX 2 POSITIONS (CENTRAL85, BREAKERS ON) ---")
            print(f" {'Strategy':<24} {'Settled SOL':<14} {'Open Mark':<14} {'Combined SOL':<14} {'Attempts':<10} {'Closed':<8} {'Win Rate'}")
            print(" " + "-" * 100)
            for r_name, rd in match_p2['rules_breakdown'].items():
                print(f" {r_name:<24} {rd['settled_sol']:>+8.4f} SOL   {rd['open_mark_sol']:>+8.4f} SOL   {rd['combined_sol']:>+8.4f} SOL   "
                      f"{rd['attempts']:>6}     {rd['closed']:>6}   {rd['win_rate']*100:>5.1f}%")

    # Execution Scenario Sensitivity for All 5 at Max 2
    print("\n" + "=" * 105)
    print("      EXECUTION SCENARIO SENSITIVITY: FULL 5-STRATS (MAX 2 POSITIONS, BREAKERS ON)")
    print("=" * 105)
    print(f" {'Scenario':<16} {'Settled SOL':<15} {'Open Mark':<14} {'Combined Net':<16} {'Win Rate':<10} {'Profit Factor':<14} {'Attempts (C/F/U)'}")
    print("-" * 105)
    for sc in ["fast", "central80", "central85", "slow"]:
        match = next((a for a in accounts if a['recipe'] == 'refined_actual' and a['scenario'] == sc
                      and a['fee'] == 1505000 and a['portfolio'] == 'all5' and a['position_limit'] == 2
                      and a['breakers'] == True and a.get('placement_seed', 0) == 0), None)
        if match:
            wr = (match.get('win_rate') or 0.0) * 100
            pf = match.get('profit_factor') or 0.0
            print(f" {sc:<16} {match['settled_net_SOL']:>+9.4f} SOL   {match['unresolved_marked_pnl_SOL']:>+8.4f} SOL   {match['last_valid_marked_net_SOL']:>+10.4f} SOL "
                  f"{wr:>5.1f}%     {pf:>6.3f}         "
                  f"{match['attempts']:>3} ({match['closed']}C/{match['failed']}F/{match['unresolved']}U)")
    print("=" * 105 + "\n")

if __name__ == "__main__":
    main()
