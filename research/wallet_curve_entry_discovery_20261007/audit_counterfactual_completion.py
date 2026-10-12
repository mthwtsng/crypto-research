"""Corrected finite entry paths; explicitly audit eligibility for actual migration."""
import collections,concurrent.futures,gzip,json,pathlib,pickle,sys
P=pathlib.Path(__file__).resolve().parent;R=P.parents[1]
sys.path.insert(0,str(R/'research/amm_multiday_20261006'));import opportunity as O
import curve_adapter as A
sys.path.insert(0,str(R/'research/day_general_20261004/helpers'));import build
O.C.P=P

def simulate(t,s,scenario):
 gs=[dict(g,trades=g['events']) for g in t['groups']];key=dict(s,pool=t['curve']);i=s['index'];j,slot=O.landing(gs,i,s['slot'],O.branch(key,scenario));_,tm=O.block_at(slot)
 base=dict(s,scenario=scenario,entry_index=j,entry_slot=slot,entry_time=tm)
 ref=A.buy(gs[i]['state'],.5);q=A.buy(gs[j]['state'],.5)
 if not ref or not q or q[1]<ref[1]*9700//10000:return dict(base,status='failed',reason='entry_guard',failed_fee_SOL=.000505)
 h=build.inventory(gs[:j+1]);cf=dict(h);st=A.moved(gs[j]['state'],q[0],q[1]);n=q[1];bill=q[0]+A.fee(q[0],st['fee_bps'])+A.fee(q[0],st['creator_fee_bps']);states=[];completion=None;reason=None;reverts=[];v3_crossings=[]
 def add(gindex,time):
  v=A.sell(st,n) if st['rtokens_raw'] else None
  states.append(dict(index=gindex,time=time,state=dict(st),quote_ROI=(v[0]-bill-3010000)/bill if v else None))
 add(j,tm)
 if st['rtokens_raw']==0:completion=dict(index=j,time=tm,slot=slot)
 for k in range(j+1,len(gs)):
  g=gs[k]
  if g['block_time']>tm+600:break
  if st['rtokens_raw']==0:break
  st,h,cf,ag,err=A.apply(st,g,h,cf)
  if err:reason=err;break
  if ag.get('counterfactual_revert'):
   reverts.append(dict(index=k,signature=g['signature'],slot=g['slot'],time=g['block_time'],reason=ag['counterfactual_revert'],instructions=[e.get('instruction_name',e['ix_name']) for e in g['events']]))
  if st['rtokens_raw']==0 and any(e.get('instruction_name','').endswith('_v3') and e['buy'] for e in g['events']):
   v3_crossings.append(g['signature'])
  add(k,g['block_time'])
  if st['rtokens_raw']==0:completion=dict(index=k,time=g['block_time'],slot=g['slot'],signature=g['signature']);break
 observed=next((g for g in gs if g['state']['rtokens_raw']==0),None)
 return dict(base,status='filled',remaining_tokens=n,entry_bill_lamports=bill,historical_completion_time=observed['block_time'] if observed else None,counterfactual_completion=completion,completion_shift_seconds=completion['time']-observed['block_time'] if completion and observed else None,migration_eligibility='v3_crossing_requires_pool_leg' if v3_crossings else 'counterfactual_complete_within_curve_history' if completion else 'recorded_completion_displaced' if observed else 'no_recorded_completion',reason=reason,source_reverts=st.get('source_reverts',0),reverted_transactions=reverts,v3_crossing_signatures=v3_crossings,last_state=st,last_valid_time=states[-1]['time'],states=states,historical_inventory=h,counterfactual_inventory=cf,warning='No exit, no realized PnL. Completion alone does not authenticate counterfactual AMM timing or custody. Future private retries/requotes not invented.')

def main():
 originals=pickle.load(gzip.open(R/'research/day_general_20261004/TAPES.pkl.gz','rb'));by={t['mint']:t for t in originals};ss=json.loads((P/'SIGNALS.json').read_text());jobs=[];rows=[];errors=[]
 for s in ss:
  old=by[s['mint']];signature=old['groups'][s['index']]['signature'];t=json.load(gzip.open(P/'bound_curve_tapes'/(s['mint']+'.json.gz'),'rt'));i=next(i for i,g in enumerate(t['groups']) if g['signature']==signature);sig=dict(s,index=i,signal_signature=signature)
  for g in t['groups']:O.CLOCK[g['slot']]=g['block_time']
  for sc in ['fast','central80','central85','slow']:jobs.append((t,sig,sc))
 with concurrent.futures.ThreadPoolExecutor(4) as ex:
  fs={ex.submit(simulate,*args):args[1] for args in jobs}
  for f in concurrent.futures.as_completed(fs):
   try:rows.append(f.result())
   except Exception as e:errors.append(dict(signal=fs[f],error=str(e)))
 with gzip.open(P/'CORRECTED_CURVE_PATHS.json.gz','wt',compresslevel=1) as f:json.dump(rows,f)
 summary=[]
 for sc in ['fast','central80','central85','slow']:
  for rule in ['broad_recovery','fresh_expansion','quiet_absorption','late_continuation']:
   rr=[r for r in rows if r['scenario']==sc and r['rule']==rule];summary.append(dict(rule=rule,scenario=sc,attempts=len(rr),statuses=dict(collections.Counter(r['status'] for r in rr)),eligibility=dict(collections.Counter(r.get('migration_eligibility') for r in rr)),errors=sum(bool(r.get('reason')) and r['status']=='filled' for r in rr)))
 (P/'COMPLETION_ELIGIBILITY.json').write_text(json.dumps(dict(summary=summary,errors=errors),indent=2)+'\n');print('COMPLETION_AUDIT',len(rows),'errors',len(errors));print(json.dumps([r for r in summary if r['scenario']=='central85'],indent=2))
if __name__=='__main__':main()
