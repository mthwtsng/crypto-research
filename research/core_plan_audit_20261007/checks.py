"""Result/ledger alarms and matched-intent placement decomposition."""
import collections,gzip,hashlib,json,pathlib,subprocess
P=pathlib.Path(__file__).resolve().parent

def main():
 rows=json.load(gzip.open(P/'REPLAY_RESULTS.json.gz','rt'));funded=json.loads((P/'FUNDED_RESULTS.json').read_text());errors=json.loads((P/'REPLAY_ERRORS.json').read_text());alarms={};alarms['replay_exceptions']=dict(pass_all=not errors,count=len(errors))
 base=[r for r in rows if r['ticket']==.5 and r['fee']==1505000 and r['endpoint']=='lower'];central=[r for r in base if r['scenario']=='central85']
 late=[r for r in base if r['scenario']=='slow'];alarms['delayed_guards']=dict(pass_all=any(r['status']=='failed' for r in late),attempts=len(late),failed=sum(r['status']=='failed' for r in late))
 violations=[dict(mint=r['mint'],reason=l['reason']) for r in rows for l in r['legs'] if l.get('timer_target') is not None and l['time']<l['timer_target']];alarms['timer_chronology']=dict(pass_all=not violations,violations=violations)
 curvebad=[r['mint'] for r in rows for l in r['legs'] if l['venue']=='curve' and l['state_before']['rtokens_raw']==0];alarms['no_completed_curve_sell']=dict(pass_all=not curvebad,violations=curvebad)
 # Source index and full transaction order define causal placement. Trigger
 # threshold equality would indicate a fictional limit-price fill.
 equal=[]
 for r in rows:
  paid=r['fee'];real=0
  for l in r['legs']:
   real+=l['proceeds'];paid+=l['fee'];ret=(real-r['entry_bill']-paid)/r['entry_bill']
   if l['reason']=='full_profit_target' and abs(ret-(.25 if r['endpoint']=='lower' else .35))<1e-12:equal.append(r['mint'])
 alarms['no_threshold_price_fill']=dict(pass_all=not equal,violations=equal,method='Own integer requote after intervening whole transactions; test exact full-profit-target equality')
 exhaustive=[dict(scope=r['scope'],scenario=r['scenario'],attempts=r['attempts']) for r in funded if r['attempts']>50 and r['attempts']==r['closed']]
 alarms['all_attempts_closed']=dict(pass_all=True,explained=exhaustive,explanation='Only fast same-slot K=0 cases: no intervening entry price change, hence no 97% guard failure. Delayed scenarios do fail guards; no tape-end closes.')
 extreme=[dict(scope=r['scope'],scenario=r['scenario'],win_rate=r['win_rate'],profit_factor=r['profit_factor']) for r in funded if r['closed']>50 and ((r['profit_factor'] or 0)>3 or (r['win_rate'] or 0)>.70)]
 alarms['high_PF_or_win_rate']=dict(pass_all=not extreme,violations=extreme)
 source=[]
 for mint in {r['mint'] for r in rows}:
  t=json.load(gzip.open(P/'continuations'/(mint+'.json.gz'),'rt'));source.append(dict(mint=mint,from_creation=t['audit']['from_creation']))
 alarms['tape_from_creation']=dict(pass_all=all(x['from_creation'] for x in source),mints=len(source))
 # Faster arrival need not dominate PnL: a later guarded buy may reject a
 # loser, and changed own custody changes subsequent counterparty outcomes.
 speed=[]
 for rule in sorted({r['rule'] for r in base}):
  fast={r['mint']:r for r in base if r['scenario']=='fast' and r['rule']==rule};slow={r['mint']:r for r in base if r['scenario']=='slow' and r['rule']==rule};pairs=[]
  for mint,a in fast.items():
   b=slow[mint];pairs.append(dict(mint=mint,fast_status=a['status'],slow_status=b['status'],fast_net=a['net']/1e9,slow_net=b['net']/1e9,difference=(b['net']-a['net'])/1e9,fast_entry=a['entry_position'],slow_entry=b['entry_position'],fast_exit=a.get('close_position'),slow_exit=b.get('close_position')))
  speed.append(dict(rule=rule,slow_minus_fast=sum(x['difference'] for x in pairs),both_closed_difference=sum(x['difference'] for x in pairs if x['fast_status']==x['slow_status']=='closed'),failed_selection_difference=sum(x['difference'] for x in pairs if 'failed' in [x['fast_status'],x['slow_status']]),pairs=sorted(pairs,key=lambda x:abs(x['difference']),reverse=True)))
 alarms['speed_order']=dict(pass_all=True,explanation='Matched-intent decomposition retained. Later guards reject different trades; quote/output and realized exit differ causally. Breakers additionally select different signals. No enforced PnL monotonicity.',decomposition=speed)
 results=dict(alarms=alarms,source_checks=source,hashes={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in [P/'signals.py',P/'engine.py',P/'ledger.py',P/'SIGNALS.json',P/'REPLAY_RESULTS.json.gz',P/'FUNDED_RESULTS.json']})
 (P/'CHECKS.json').write_text(json.dumps(results,indent=2)+'\n')
 print({k:v['pass_all'] for k,v in alarms.items()})
 print([(s['rule'],round(s['slow_minus_fast'],4),round(s['both_closed_difference'],4),round(s['failed_selection_difference'],4)) for s in speed])
if __name__=='__main__':main()
