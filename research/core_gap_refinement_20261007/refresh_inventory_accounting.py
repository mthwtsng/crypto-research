"""Add explicit settled/open decomposition without changing historical fills."""
import gzip,json,pathlib
import unlimited_requested as N
P=N.OUT
sources={'reserve_floor_control':json.load(gzip.open(N.U.OUT/'REPLAY.json.gz','rt')),'relative_price_stop':json.load(gzip.open(P/'RELATIVE_REPLAY.json.gz','rt'))}
holds={(a['window'],a['mint'],a['rule'],a['signature']):a for a in json.load(open(N.U.OUT/'CREATOR_HOLDINGS.json'))}
rows=json.load(open(P/'FUNDED.json'));groups={};count=0
for f in rows:
 key=(f['stop_policy'],f['horizon'],f['profit_target'],f['scenario'],f['fee'],f['window'],f['developer_gate'])
 if key not in groups:
  ss=[r for r in sources[f['stop_policy']] if (r['horizon'],r['profit_target'],r['scenario'],r['fee'])==(f['horizon'],f['profit_target'],f['scenario'],f['fee']) and (f['window']=='continuous' or r['window']==f['window'])]
  if f['developer_gate']:ss=[r for r in ss if holds[(r['window'],r['mint'],r['rule'],r['signal_signature'])]['passes']]
  groups[key]=ss
 actual=N.U.F.funded(groups[key],f['breakers'],f['scope'],position_limit=f['position_limit'])
 for k,v in actual.items():
  if k in f:assert f[k]==v,(k,f[k],v)
 f.update(actual)
 assert abs(f['settled_net_SOL']+f['unresolved_marked_pnl_SOL']-f['last_valid_marked_net_SOL'])<1e-8
 count+=1
(P/'FUNDED.json').write_text(json.dumps(rows,indent=2)+'\n')
(P/'ACCOUNTING_CORRECTION.json').write_text(json.dumps(dict(reconciled_ledgers=count,all_legacy_fills_admissions_and_numeric_results_unchanged=True,new_fields=['settled_net_SOL','unresolved_cashflow_SOL','unresolved_marked_pnl_SOL','unresolved_mark_value_SOL','zero_recovery_bound_SOL','last_valid_marked_net_SOL','unresolved_excluded_from_win_loss'],mark_provenance='UNRESOLVED_MARK_PROVENANCE.json',source='User-requested accounting audit; retain unknown custody and causal fill requirements'),indent=2)+'\n')
print('ACCOUNTING_REFRESH',count,flush=True)
