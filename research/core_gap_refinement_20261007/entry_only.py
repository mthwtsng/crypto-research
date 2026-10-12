"""Exit-free opportunity diagnostics using the repaired approved adapters.

Observation horizons never liquidate inventory. Peaks are diagnostics, not fills.
"""
import collections,concurrent.futures,gzip,json,pathlib,sys
P=pathlib.Path(__file__).resolve().parent;BASE=P.parent/'core_plan_audit_20261007'
sys.path.insert(0,str(BASE));import engine as E
A,M,O=E.A,E.M,E.O
HORIZONS=[2,5,10,20,30,60,180,600];HITS=[.02,.05,.10,.20,.25]

def trace(t,sig,scenario,fee=1505000):
 gs=t['groups'];i=next(i for i,g in enumerate(gs) if g['signature']==sig['signal_signature']);s=dict(sig,index=i,pool=t['curve']);j,slot=O.landing(gs,i,s['slot'],O.branch(s,scenario));_,tm=O.block_at(slot)
 out=dict(s,scenario=scenario,fee=fee,entry_time=tm,entry_position=E.pos(gs,j,slot),points=[],horizons={},error=None)
 ref=A.buy(gs[i]['state'],.5);r=A.buy(gs[j]['state'],.5) if gs[j]['venue']=='curve' else None
 if not ref or not r or r[1]<ref[1]*9700//10000:return dict(out,status='failed',net=-505000)
 st=A.moved(gs[j]['state'],*r);n=r[1];bill=r[0]+A.fee(r[0],st['fee_bps'])+A.fee(r[0],st['creator_fee_bps']);h=A.build.inventory(gs[:j+1]);cf=dict(h);venue='curve';initialspot=st['vsol_raw']/st['vtokens_raw'];reason=None;coverage=min(t['end_time'],tm+600);censor=None
 def point(gtime,gslot,index):
  q=A.sell(st,n) if venue=='curve' and st['rtokens_raw'] else M.A.sell(st,n) if venue=='amm' else None
  spot=st['vsol_raw']/st['vtokens_raw'] if venue=='curve' else (st['quote']+st['virtual'])/st['base']
  proceeds=q[0] if venue=='curve' and q else q['total'] if q else None
  return dict(time=gtime,elapsed=gtime-tm,slot=gslot,index=index,venue=venue,net_return=(proceeds-bill-2*fee)/bill if proceeds is not None else None,spot_return=spot/initialspot-1,source_reverts=st.get('source_reverts',0))
 out['points'].append(point(tm,slot,out['entry_position'][1]))
 for k in range(j+1,len(gs)):
  g=gs[k]
  if g['time']>coverage:break
  if g['venue']=='curve':
   if venue!='curve':reason='curve_activity_after_AMM_open';censor=g['time'];break
   st,h,cf,ag,err=A.apply(st,g,h,cf)
   if err:reason=err;censor=g['time'];break
   if st['rtokens_raw']==0 and any(e.get('instruction_name','').endswith('_v3') and e['buy'] for e in g['events']):reason='v3_pool_leg_unmodeled';censor=g['time'];break
  elif venue=='curve':
   if st['rtokens_raw']!=0:reason='counterfactual_completion_displaced';censor=g['time'];break
   if t['inventory_key']!='token_account':reason='migration_account_mapping_unverified';censor=g['time'];break
   z,hh,cc,err=E.opening_state(st,g,t,h,cf)
   if err:reason=err;censor=g['time'];break
   st,h,cf=z,hh,cc;venue='amm'
  else:
   st,h,cf,err=M.advance(st,g,h,cf)
   if err:reason=err;censor=g['time'];break
  out['points'].append(point(g['time'],g['slot'],g['index']))
 for secs in HORIZONS:
  target=tm+secs;known=coverage>=target and (censor is None or target<censor);pp=[p for p in out['points'] if p['time']<target];at=pp[-1] if pp else out['points'][0];values=[p['net_return'] for p in pp if p['net_return'] is not None];spots=[p['spot_return'] for p in pp]
  out['horizons'][str(secs)]=dict(complete=known,net_return=at['net_return'] if known else None,spot_return=at['spot_return'] if known else None,MFE=max(values,default=None),MAE=min(values,default=None),spot_MFE=max(spots,default=None),net_hits={str(v):next((p['elapsed'] for p in pp if p['net_return'] is not None and p['net_return']>=v),None) for v in HITS})
 return dict(out,status='covered' if reason is None else 'censored',reason=reason,censor_time=censor,coverage_time=coverage,entry_bill=bill,entry_tokens=n,last_state=st)

def main():
 tapes,ss=E.load();jobs=[(tapes[s['mint']],s,sc) for s in ss for sc in ['fast','central80','central85','slow']];rows=[];errors=[]
 with concurrent.futures.ThreadPoolExecutor(4) as ex:
  futures={ex.submit(trace,*j):j[1] for j in jobs}
  for f in concurrent.futures.as_completed(futures):
   try:rows.append(f.result())
   except Exception as e:errors.append(dict(signal=futures[f],error=repr(e)))
   if (len(rows)+len(errors))%25==0:print('ENTRY_ONLY',len(rows),len(errors),'of',len(jobs),flush=True)
 with gzip.open(P/'ENTRY_TRAJECTORIES.json.gz','wt',compresslevel=1) as f:json.dump(rows,f)
 (P/'ENTRY_ERRORS.json').write_text(json.dumps(errors,indent=2)+'\n');print('COMPLETE',len(rows),len(errors),flush=True)
if __name__=='__main__':main()
