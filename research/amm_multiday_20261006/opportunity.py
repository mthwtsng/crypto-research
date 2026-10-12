"""Entry-only finite-size AMM opportunity with own impact and custody repricing."""
import json,pathlib,gzip,hashlib,bisect,collections,statistics,concurrent.futures,sys,threading
P=pathlib.Path(__file__).resolve().parent;import amm_adapter as A;import collect as C
SCENARIOS=['fast','central80','central85','slow'];CLOCK={};CL=threading.Lock()

def block_at(slot):
 with CL:
  if slot in CLOCK:return slot,CLOCK[slot]
 for s in range(slot,slot+12):
  try:b=C.rpc('getBlock',[s,dict(commitment='finalized',transactionDetails='none',rewards=False,maxSupportedTransactionVersion=1)])
  except Exception as e:
   if '-32007' in str(e) or '-32009' in str(e) or 'skipped' in str(e).lower():continue
   raise
  if b and b.get('blockTime') is not None:
   if s>slot and b['parentSlot']>=slot:raise ValueError('unproven_missing_clock')
   with CL:CLOCK[s]=b['blockTime']
   return s,b['blockTime']
 raise ValueError('no_clock')

def branch(sig,scenario,leg='entry'):
 if scenario=='fast':return ('same',0)
 if scenario=='slow':return ('next',2)
 if scenario=='stress':return ('next',10**9)
 h=hashlib.sha256(f"AMM-fixed-v1|{sig['pool']}|{sig['rule']}|{sig['index']}|{leg}".encode()).digest();u=int.from_bytes(h[:8],'little')/2**64;v=int.from_bytes(h[8:16],'little')/2**64
 if u>=float(scenario[-2:])/100:return ('next',1)
 return ('same',0 if v<29/132 else 1 if v<49/132 else 2)

def landing(gs,index,refslot,br):
 kind,k=br
 if kind=='same':slot=refslot
 else:slot=block_at(refslot+1)[0]
 matches=[j for j in range(index+1,len(gs)) if gs[j]['slot']==slot and gs[j]['trades']]
 # Whole transactions; no fill inside the signal or atomic multi-swap group.
 j=matches[min(k,len(matches))-1] if k and matches else index
 if kind=='next' and not matches:j=bisect.bisect_right([g['slot'] for g in gs],slot)-1
 return j,slot

def advance(st,g,h,cf):
 if g.get('custody_error'):return st,h,cf,'unverified_transaction_custody'
 if g['other_liquidity_events']:return st,h,cf,'unsupported_counterfactual_LP_action'
 z=dict(st);historical=dict(h);inventory=dict(cf)
 ops=g.get('custody_ops',[dict(kind='trade',event=e) for e in g['trades']])
 touched=set()
 for op in ops:
  if op['kind']=='trade':
   e=op['event']
   if not (e['zero_fee'] and e['account']=='11111111111111111111111111111111'):touched.add(e['account'])
  else:touched.update(ac for ac in [op['source'],op.get('destination')] if ac)
 for ac in touched:
  old=g['tokenpre'].get(ac,0)
  if ac not in historical:historical[ac]=old;inventory[ac]=old
  elif historical[ac]!=old:
   if inventory[ac]!=historical[ac]:return st,h,cf,'counterfactual_inventory_transfer_gap'
   historical[ac]=old;inventory[ac]=old
 original_cf=dict(inventory);start_h=dict(historical)
 # Advance the historical branch independently, including every ordered transfer.
 for op in ops:
  if op['kind']=='trade':
   e=op['event'];ac=e['account']
   if e['zero_fee'] and ac=='11111111111111111111111111111111':continue
   historical[ac]+=e['n'] if e['buy'] else -e['n']
  else:
   historical[op['source']]-=op['raw']
   if op.get('destination'):historical[op['destination']]+=op['raw']
 shift=g.get('reserve_shift',0)
 if shift:
  if shift>z['quote']:return st,h,cf,'counterfactual_fee_sweep_liquidity'
  z['quote']-=shift;z['virtual']+=shift
 hh=start_h
 for op in ops:
  if op['kind']!='trade':
   ac=op['source'];old=hh[ac];raw=op['raw'];held=inventory[ac]
   if old<=0 and raw:return st,h,cf,'invalid_transfer_inventory'
   n=held if raw==old else held*raw//old if old else 0
   hh[ac]-=raw;inventory[ac]-=n
   if op.get('destination'):hh[op['destination']]+=raw;inventory[op['destination']]+=n
   else:z['supply_diff']=z.get('supply_diff',0)+raw-n
   continue
  e=op['event'];ac=e['account'];old=e['prehold'];obs=e['n'];burn=e['zero_fee'] and ac=='11111111111111111111111111111111'
  supply_diff=z.get('supply_diff',0);z['virtual']=e['virtual'];z['supply']=e['supply']+supply_diff
  val=dict(z,historical_rates=[0,0,0]) if e['zero_fee'] else z
  if e['buy']:
   r=A.buy(val,e['gross']) if e['ix'].startswith('buy_exact_quote_in') else A.exact_buy(val,obs)
   failed=not r or (e['ix'] in ['buy','buy_v2'] and r['total']>e.get('max_quote',10**30)) or (e['ix'].startswith('buy_exact_quote_in') and r['n']<e.get('min_base',0))
   if failed:return dict(st,source_reverts=st.get('source_reverts',0)+1),historical,original_cf,None
   if burn:z['supply_diff']=supply_diff+obs-r['n'];z['supply']=e['supply']+z['supply_diff']
   else:hh[ac]+=obs;inventory[ac]+=r['n']
   z=A.moved(z,r,True,e.get('deferred',False))
  else:
   held=inventory[ac];n=held if obs==old else held*obs//old
   r=A.sell(val,n)
   if not r or r['total']<e.get('min_quote',0):return dict(st,source_reverts=st.get('source_reverts',0)+1),historical,original_cf,None
   hh[ac]-=obs;inventory[ac]-=n;z=A.moved(z,r,False,e.get('deferred',False))
 return z,historical,inventory,None

def trace(t,sig,scenario,ticket,control=False):
 gs=t['groups'];i=sig['index'];slots=[g['slot'] for g in gs]
 for g in gs:CLOCK[g['slot']]=g['time']
 j,slot=landing(gs,i,sig['slot'],branch(sig,scenario));_,tm=block_at(slot);ref=A.buy(gs[i]['state'],round(ticket*1e9));r=A.buy(gs[j]['state'],round(ticket*1e9))
 base=dict(sig,scenario=scenario,ticket=ticket,entry_slot=slot,entry_index=j,entry_time=tm,control=control)
 if not ref or not r or r['n']<ref['n']*9700//10000:return dict(base,status='failed',failed_fee_SOL=.000505)
 if tm+600>t['coverage']['through_time']:return dict(base,status='missing',reason='insufficient_requested_coverage')
 st=A.moved(gs[j]['state'],r,True);n=r['n'];h={};cf={};states=[dict(time=tm,index=j,slot=slot,state=dict(st))];reason=None;censor_time=None
 for k in range(j+1,len(gs)):
  g=gs[k]
  if g['time']>tm+600:break
  st,h,cf,reason=advance(st,g,h,cf)
  if reason:censor_time=g['time'];break
  states.append(dict(time=g['time'],index=k,slot=g['slot'],state=dict(st)))
 quotes=[]
 for s in states:
  out=A.sell(s['state'],n);quotes.append(dict(time=s['time'],index=s['index'],slot=s['slot'],net_ROI=(out['total']/1e9-ticket-.00301)/ticket if out else None))
 horizons={}
 for secs in [5,15,30,60,180,600]:
  target=tm+secs;valid=reason is None or target<censor_time;at=max((z for z in quotes if z['time']<=target),key=lambda z:(z['time'],z['index']),default=None)
  horizons[str(secs)]=at['net_ROI'] if valid and at else None
 finite=[q for q in quotes if q['net_ROI'] is not None];hits={}
 for frac in [.05,.10,.20]:hits[str(frac)]=next((q['time']-tm for q in finite if q['net_ROI']>=frac),None)
 up=next((k for k,q in enumerate(finite) if q['net_ROI']>=.10),None);dn=next((k for k,q in enumerate(finite) if q['net_ROI']<=-.10),None)
 return dict(base,status='covered' if reason is None else 'partial',reason=reason,entry_tokens=n,entry_bill_SOL=r['total']/1e9,horizons=horizons,hit_times=hits,up10_before_down10=up is not None and (dn is None or up<dn),MFE=max((q['net_ROI'] for q in finite),default=None),MAE=min((q['net_ROI'] for q in finite),default=None),last_valid_time=states[-1]['time'],counterparty_reverts=st.get('source_reverts',0),quotes=quotes)

def main():
 audits=json.loads((P/'PREPARE_CHECKS.json').read_text());good={a['pool'] for a in audits if a['good']};rows=[];missing=[];jobs=[];tapes={}
 for f in sorted((P/'tapes').glob('*.gz')):
  t=json.load(gzip.open(f,'rt'))
  if t['pool'] not in good:continue
  tapes[t['pool']]=t
  for s in t['signals']:
   s=dict(s,pool=t['pool'],mint=t['mint']);indices=[k for k,g in enumerate(t['groups'][:s['index']]) if g['time']<=s['time']-10 and abs(g['time']-t['migration']['time']-s['age'])<=max(20,s['age']*.25) and abs((g['state']['quote']+g['state']['virtual'])/(t['groups'][s['index']]['state']['quote']+t['groups'][s['index']]['state']['virtual'])-1)<=.20]
   ctl=dict(s,index=indices[-1],slot=t['groups'][indices[-1]]['slot'],time=t['groups'][indices[-1]]['time']) if indices else None
   for scenario in SCENARIOS:
    for ticket in [.5,1.]:
     jobs.append((t,s,scenario,ticket,False))
     if ctl:jobs.append((t,ctl,scenario,ticket,True))
 with concurrent.futures.ThreadPoolExecutor(6) as ex:
  fs={ex.submit(trace,*j):j[1] for j in jobs}
  for f in concurrent.futures.as_completed(fs):
   try:rows.append(f.result())
   except Exception as e:missing.append(dict(signal=fs[f],error=str(e)))
 out=[]
 for rule in ['amm_pullback_recovery','amm_second_wave','amm_dormant_revival']:
  for scenario in SCENARIOS:
   for ticket in [.5,1.]:
    for control in [False,True]:
     rr=[r for r in rows if r['rule']==rule and r['scenario']==scenario and r['ticket']==ticket and r['control']==control];filled=[r for r in rr if r['status'] in ['covered','partial']];covered=[r for r in filled if r['status']=='covered'];hs={}
     for sec in [5,15,30,60,180,600]:
      vals=[r['horizons'][str(sec)] for r in filled if r['horizons'][str(sec)] is not None];hs[str(sec)]=dict(n=len(vals),mean_ROI=statistics.mean(vals) if vals else None,median_ROI=statistics.median(vals) if vals else None)
     out.append(dict(rule=rule,scenario=scenario,ticket=ticket,control=control,attempts=len(rr),failed=sum(r['status']=='failed' for r in rr),fully_covered=len(covered),partial=len(filled)-len(covered),horizons=hs,up10_before_down10=sum(r['up10_before_down10'] for r in covered),MFE_hit10=sum(r['hit_times']['0.1'] is not None for r in covered)))
 with gzip.open(P/'OPPORTUNITY_TRACES.json.gz','wt',compresslevel=1) as f:json.dump(rows,f)
 (P/'OPPORTUNITY_SUMMARY.json').write_text(json.dumps(out,indent=2));(P/'OPPORTUNITY_ERRORS.json').write_text(json.dumps(missing,indent=2));print('OPPORTUNITY DONE',len(rows),'missing',len(missing))
if __name__=='__main__':main()
