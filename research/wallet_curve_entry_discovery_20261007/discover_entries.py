"""Initial opportunity diagnostics; no exit strategy or realized PnL claim."""
import collections,concurrent.futures,gzip,hashlib,json,pathlib,pickle,statistics,sys
P=pathlib.Path(__file__).resolve().parent;R=P.parents[1]
sys.path.insert(0,str(R/'research/amm_multiday_20261006'));import opportunity as O
sys.path.insert(0,str(R/'research/day_general_20261004/helpers'));import replay as B,build
from entry_signals import extract,RULES
# Write RPC cache in this study, preserve earlier research.
O.C.P=P

def trace(t,s,scenario):
 gs=[dict(g,trades=g['events']) for g in t['groups']];sig=dict(s,pool=t['curve'])
 j,slot=O.landing(gs,s['index'],s['slot'],O.branch(sig,scenario));_,tm=O.block_at(slot)
 base=dict(s,scenario=scenario,entry_index=j,entry_slot=slot,entry_time=tm,horizons={},migration_pending=False)
 if tm>t['end_time']:return dict(base,status='missing',reason='entry_outside_coverage')
 ref=B.buy(gs[s['index']]['state'],.5);q=B.buy(gs[j]['state'],.5)
 if not ref or not q or q[1]<ref[1]*9700//10000:return dict(base,status='failed',reason='entry_guard',failed_fee_SOL=.000505)
 try:h=build.inventory(gs[:j+1])
 except ValueError as e:return dict(base,status='missing',reason=str(e))
 cf=dict(h);st=B.moved(gs[j]['state'],q[0],q[1]);n=q[1];bill=q[0]+B.fee(q[0],st['fee_bps'])+B.fee(q[0],st['creator_fee_bps'])
 quotes=[];reason=None;end=tm+600
 def quote(time,index):
  v=B.sell(st,n)
  quotes.append(dict(time=time,index=index,net_ROI=(v[0]-bill-3010000)/bill if v else None,spot=st['vsol_raw']/st['vtokens_raw']))
 quote(tm,j)
 for k in range(j+1,len(gs)):
  g=gs[k]
  if g['block_time']>end:break
  if st['rtokens_raw']<=0:reason='requires_authenticated_AMM_continuation';base['migration_pending']=True;break
  z,hh,cc,adjusted,err=B.apply(st,g,h,cf)
  if err:
   reason=err;base['censor_time']=g['block_time'];break
  st,h,cf=z,hh,cc;quote(g['block_time'],k)
  if st['rtokens_raw']==0:
   reason='requires_authenticated_AMM_continuation';base['migration_pending']=True;base['completion_signature']=g['signature'];base['completion_time']=g['block_time'];base['censor_time']=g['block_time'];break
 horizon={}
 for sec in [10,30,60,180,600]:
  target=tm+sec;valid=target<=t['end_time'] and (reason is None or target<base.get('censor_time',quotes[-1]['time']))
  eligible=[r for r in quotes if r['time']<=target]
  horizon[str(sec)]=eligible[-1]['net_ROI'] if valid and eligible else None
 finite=[r for r in quotes if r['net_ROI'] is not None];up=next((k for k,r in enumerate(finite) if r['net_ROI']>=.1),None);dn=next((k for k,r in enumerate(finite) if r['net_ROI']<=-.1),None)
 return dict(base,status='partial' if reason or tm+600>t['end_time'] else 'covered',reason=reason,entry_tokens=n,entry_bill_lamports=bill,horizons=horizon,MFE=max((r['net_ROI'] for r in finite),default=None),MAE=min((r['net_ROI'] for r in finite),default=None),up10_before_down10=up is not None and (dn is None or up<dn),quotes=quotes,remaining_tokens=n,warning='Finite-size immediate liquidation quote diagnostics, not delivered sells or funded profit. Base-family counterparty intents fixed; continuation still requires authenticated cross-venue replay.')

def main():
 tapes=pickle.load(gzip.open(R/'research/day_general_20261004/TAPES.pkl.gz','rb'));signals=[];jobs=[];errors=[];rows=[]
 for t in tapes:
  for g in t['groups']:O.CLOCK[g['slot']]=g['block_time']
 for t in tapes:
  ss=extract(t);signals+=ss
  for s in ss:
   for scenario in ['fast','central80','central85','slow']:jobs.append((t,s,scenario))
 (P/'SIGNALS.json').write_text(json.dumps(signals,indent=2)+'\n');print('SIGNALS',len(signals),dict(collections.Counter(s['rule'] for s in signals)),flush=True)
 with concurrent.futures.ThreadPoolExecutor(4) as ex:
  fs={ex.submit(trace,*a):a[1] for a in jobs}
  for k,f in enumerate(concurrent.futures.as_completed(fs),1):
   try:rows.append(f.result())
   except Exception as e:errors.append(dict(signal=fs[f],error=str(e)))
   if k%100==0:print('TRACES',k,'/',len(jobs),'errors',len(errors),flush=True)
 summaries=[]
 for rule in RULES:
  for sc in ['fast','central80','central85','slow']:
   rr=[r for r in rows if r['rule']==rule and r['scenario']==sc];filled=[r for r in rr if r['status'] in ('covered','partial')];hs={}
   for sec in [10,30,60,180,600]:
    vals=[r['horizons'][str(sec)] for r in filled if r['horizons'].get(str(sec)) is not None]
    hs[str(sec)]=dict(n=len(vals),mean=statistics.mean(vals) if vals else None,median=statistics.median(vals) if vals else None,positive=sum(v>0 for v in vals))
   summaries.append(dict(rule=rule,scenario=sc,attempts=len(rr),statuses=dict(collections.Counter(r['status'] for r in rr)),reasons=dict(collections.Counter(r.get('reason') for r in rr if r.get('reason'))),migration_continuation_needed=sum(r['migration_pending'] for r in rr),horizons=hs,scope='initial entry opportunities, censored cases retained; not executable exit PnL'))
 with gzip.open(P/'ENTRY_TRACES.json.gz','wt',compresslevel=1) as f:json.dump(rows,f)
 (P/'ENTRY_DIAGNOSTICS.json').write_text(json.dumps(summaries,indent=2)+'\n');(P/'ENTRY_ERRORS.json').write_text(json.dumps(errors,indent=2)+'\n');print('DONE',len(rows),len(errors),flush=True)
if __name__=='__main__':main()
