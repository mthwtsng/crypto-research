"""Whole-day accounting and source-boundary scope checks."""
import gzip,json,pickle,collections
import collect as N
P=N.HERE;rows=[json.loads(x)for x in gzip.open(P/'TRADES.jsonl.gz','rt')];ts=pickle.load(gzip.open(P/'TAPES.pkl.gz','rb'));by={t['mint']:t for t in ts};a=json.loads((P/'AUTHENTICATION.json').read_text());scope=[]
for t in a['transitions']:
 for err in t['material_errors']:
  g=next(g for g in by[t['mint']]['groups']if g['signature']==err['signature']);rr=[r for r in rows if r['mint']==t['mint']];latest=max(r.get('settle_slot',r['decision_slot'])for r in rr)if rr else None
  scope.append(dict(mint=t['mint'],reason=err.get('reason'),error_slot=g['slot'],latest_modeled_settle_slot=latest,all_modeled_trades_settled_before_error=latest is not None and latest<g['slot'],historical_curve_completed=g['state']['rtokens_raw']==0))
assert all(x['all_modeled_trades_settled_before_error']for x in scope)
assert len(ts)==600
assert all(r['pnl']is not None and r['status']in ['closed','failed']for r in rows)
assert not json.loads((P/'REPLAY_ERRORS.json').read_text())
assert not json.loads((P/'SENSITIVITY_ERRORS.json').read_text())
for file in ['RESULTS.json','FIRST_ENTRY_LEDGER.json','PORTFOLIOS.json','SENSITIVITY.json']:
 for cell in json.loads((P/file).read_text()):
  l=cell['funded5'];assert l['cash_reconciled'] and l['missing_not_modeled']==0 and l['remaining_open_positions']==0
fr=json.loads((P/'FREEZE.json').read_text());sample=json.loads((P/'CREATION_SAMPLE.json').read_text())['chosen'];hours=collections.Counter((x['creation_time']-fr['window_start_utc_epoch'])//3600 for x in sample)
assert hours==collections.Counter({h:25 for h in range(24)})
assert not set(x['mint']for x in sample)&set(json.loads((P/'EXCLUDED_PRIOR_MINTS.json').read_text()))
(P/'FINAL_CHECKS.json').write_text(json.dumps(dict(primary_records=len(rows),statuses=dict(collections.Counter(r['status']for r in rows)),fixed_hour_counts=dict(hours),source_boundary_checks=scope,all_funded_ledgers_reconcile=True,no_incomplete_intents=True),indent=2))
print('FINAL accounting/coverage checks passed',len(rows),'records')
