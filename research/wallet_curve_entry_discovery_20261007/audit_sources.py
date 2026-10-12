import json, pathlib, statistics, hashlib
R=pathlib.Path(__file__).resolve().parents[2]; P=pathlib.Path(__file__).resolve().parent
S=R/'research/automated_wallet_expansion_20261006'
main=json.loads((S/'STAGE_FOCUS_MAIN.json').read_text())
features=json.loads((R/'research/automated_wallet_discovery_20261006/ENTRY_FEATURES.json').read_text())
wallets={r['wallet'] for r in main}
rows=[]
for w in sorted(wallets):
 fs=[f for f in features if f['wallet']==w and f.get('genesis_verified') and f.get('quote_is_sol') and not f.get('wallet_is_launch_role')]
 def med(k):
  vs=[f[k] for f in fs if isinstance(f.get(k),(int,float))];return statistics.median(vs) if vs else None
 source=next(r for r in main if r['wallet']==w)
 rows.append(dict(wallet=w,contexts=len(fs),age_median=med('age'),reserve_median=med('reserve_SOL'),drawdown_median=med('drawdown'),recent_buyers_median=med('recent_unique_meaningful_buyers'),breadth_median=med('meaningful_outside_buyers'),sample_entries_at_68_SOL_or_above=sum(f.get('reserve_SOL',0)>=68 for f in fs),curve_only_cash=source['pre_curve_cash_SOL'],curve_to_AMM_cash=source['curve_entry_AMM_exit_cash_SOL'],warning='Sampled observed entries, not non-entry controls or recovered private rules; venue must be authenticated per receipt.'))
(P/'WALLET_CONTEXT_AUDIT.json').write_text(json.dumps(rows,indent=2)+'\n')
code=(R/'research/curve_to_amm_carryover_20261007/carryover_engine.py').read_text()
checks={'fabricated_25_SOL_demand':"quote=amm_st_after['quote'] + 25 * 10**9" in code,'fabricated_30_SOL_demand':"quote=amm_st['quote'] + 30 * 10**9" in code,'file_end_liquidation':"final_g = groups[-1]" in code,'reserve_84_used_instead_of_authenticated_completion':"r_sol >= 84.0" in code,'fixed_AMM_opening_state':"def get_initial_amm_state()" in code,'counterfactual_source_repricing_absent':"g['state']" in code,'invented_migration_slot':"grad_g['slot'] + 2" in code}
(P/'CARRYOVER_REPORT_AUDIT.json').write_text(json.dumps({'code_sha256':hashlib.sha256(code.encode()).hexdigest(),'findings':checks,'usable_for_profitability_claim':False},indent=2)+'\n')
print(json.dumps(rows,indent=2));print('AUDIT',checks)
