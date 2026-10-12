"""Cash-funded uncapped comparison, with an isolated S3 relative-price stop."""
import collections,concurrent.futures,datetime,gzip,hashlib,json,pathlib
import unified_requested as U
OUT=U.P/'unlimited_requested_cycle';OUT.mkdir(exist_ok=True)
def main():
 spec=dict(frozen_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),authorization='User requests unlimited cash-funded positions and S3 relative12% price stop',source_spec=str(U.OUT/'SPEC.json'),bankroll_SOL=15,ticket_SOL=.5,position_limit=None,unresolved='Retain tokens, committed capital and same-mint occupancy; no invented exits',S3='12% price fall from actual fee-inclusive average fill price entry_bill/entry_tokens, compared with post-transaction marginal price; stop deferred until8s, including independent quiet-market grace deadline; immediate executable fullTP20/35%,60/120s timeout, original20%-armed8pp trail retained',controls='Previous reserve8floor trace set; run each with original2-position and unlimited cash-funded ledger; retain all eight horizon/TP/developer cases',data='Same inspected1800launches October3–6;223signals/166mints; retrospective',look_count='42prior looks;8new user-prescribed relative-stop cases; position-cap controls disclosed separately',limitation='Each historical intent has its own-impact counterfactual trace; simultaneous positions on different mints share cash, no coupled cross-market historical strategy response',hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [pathlib.Path(__file__),U.R.V.BASE/'engine.py',pathlib.Path(U.F.__file__)]})
 (OUT/'SPEC.json').write_text(json.dumps(spec,indent=2)+'\n')
 prior=json.load(gzip.open(U.OUT/'REPLAY.json.gz','rt'));selection=json.load(open(U.R.OUT/'SIGNALS.json'));rows=[];errors=[]
 for window in ['earlier','later']:
  tapes,_,_=U.R.prepare(window,selection[window]);jobs=[r for r in prior if r['window']==window and r['rule']=='s3_deadman']
  def run(r):
   cfg=dict(s3_extended_hold=r['horizon'],s3_grace=8,s3_full_target=r['profit_target'],s3_relative_price_stop=.12)
   return dict(U.E.simulate(tapes[r['mint']],r,r['scenario'],'lower',r['ticket'],r['fee'],cfg),window=window,horizon=r['horizon'],profit_target=r['profit_target'])
  with concurrent.futures.ThreadPoolExecutor(4) as ex:
   fs={ex.submit(run,r):r for r in jobs}
   for f in concurrent.futures.as_completed(fs):
    try:rows.append(f.result())
    except Exception as e:errors.append(dict(mint=fs[f]['mint'],error=repr(e)))
    if (len(rows)+len(errors))%100==0:print('S3',len(rows),len(errors),flush=True)
 rows.extend(r for r in prior if r['rule']!='s3_deadman')
 with gzip.open(OUT/'RELATIVE_REPLAY.json.gz','wt',compresslevel=1) as f:json.dump(rows,f)
 (OUT/'ERRORS.json').write_text(json.dumps(errors,indent=2)+'\n')
 assert not errors,errors
 holds={(a['window'],a['mint'],a['rule'],a['signature']):a for a in json.load(open(U.OUT/'CREATOR_HOLDINGS.json'))};results=[]
 for policy,source in [('reserve_floor_control',prior),('relative_price_stop',rows)]:
  for h in [60,120]:
   for tp in [.2,.35]:
    for gate in [False,True]:
     for window in ['earlier','later','continuous']:
      for sc,fee in [(x,1505000) for x in ['fast','central80','central85','slow','stress']]+[('central85',2916000)]:
       rr=[r for r in source if (r['horizon'],r['profit_target'],r['scenario'],r['fee'])==(h,tp,sc,fee) and (window=='continuous' or r['window']==window)]
       rejected=[r for r in rr if gate and not holds[(r['window'],r['mint'],r['rule'],r['signal_signature'])]['passes']]
       rr=[r for r in rr if not gate or holds[(r['window'],r['mint'],r['rule'],r['signal_signature'])]['passes']]
       for scope in ['portfolio','portfolio_without_carryover']+U.F.RULES:
        for br in [False,True]:
         for cap in [2,None]:
          result=U.F.funded(rr,br,scope,position_limit=cap)
          assert result==U.F.funded(rr,br,scope,position_limit=cap)
          if cap is None:assert not result['skipped'].get('concurrency')
          results.append(dict(stop_policy=policy,horizon=h,profit_target=tp,developer_gate=gate,window=window,scenario=sc,fee=fee,position_limit=cap,**result))
 (OUT/'FUNDED.json').write_text(json.dumps(results,indent=2)+'\n')
 bad=[]
 for r in rows:
  if r['status']!='failed' and sum(l['tokens'] for l in r['legs'])+r['remaining']!=r['entry_tokens']:bad.append(('tokens',r['mint']))
  for l in r['legs']:
   if l.get('timer_target') is not None and l['time']<l['timer_target']:bad.append(('timer',r['mint']))
   if l['venue']=='curve' and l['state_before']['rtokens_raw']==0:bad.append(('completed_curve',r['mint']))
   if r['rule']=='s3_deadman' and ('relative_price_stop' in l['reason'] or 'runner_trail' in l['reason']) and l['time']<r['entry_time']+8:bad.append(('grace',r['mint']))
   if tuple(l['position'])<=tuple(r['entry_position']):bad.append(('causality',r['mint']))
 assert not bad,bad
 (OUT/'CHECKS.json').write_text(json.dumps(dict(violations=bad,identical_ledger_regenerations=len(results),cash_and_net_reconciled=True,source_trace_checks=str(U.OUT/'CHECKS.json'),alarms='Inherited source-history checks; new funded PF/WR, guard and placement alarms evaluated in report',source_hashes=spec['hashes']),indent=2)+'\n')
 for r in results:
  if r['window']=='continuous' and r['scenario']=='central85' and r['fee']==1505000 and r['scope']=='portfolio' and r['breakers'] and r['position_limit'] is None:
   print('RESULT',json.dumps({k:v for k,v in r.items() if k!='admitted'}),flush=True)
 print('DONE',len(rows),len(results),flush=True)
if __name__=='__main__':main()
