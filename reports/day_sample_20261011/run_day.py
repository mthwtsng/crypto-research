#!/usr/bin/env python3
"""Frozen-day comparison through the approved atomic replay and funded ledger.

Current exits are a separately audited derivative. Screens are historical;
missing balance history never becomes clear. No policy is tuned in this runner.
"""
import collections, concurrent.futures, copy, gzip, hashlib, importlib.util, inspect, json, pathlib, pickle, sys, threading

OUT=pathlib.Path(__file__).resolve().parent
ROOT=OUT.parents[1]
sys.path.insert(0,str(OUT));sys.path.insert(0,str(ROOT/'research/core_plan_audit_20261007'))
import engine as E, ledger as F, collect_day as C, signals_current as S
RPC_LOCK=threading.Lock();RPC_KEYS={}
def clock_rpc(method,params):
 key=json.dumps([method,params],sort_keys=True)
 with RPC_LOCK:lock=RPC_KEYS.setdefault(key,threading.Lock())
 with lock:return C.rpc(method,params)

def save(name,value): C.save(OUT/name,value)
def config(rule):
 c=dict(tailored_trail_basis='percentage_points')
 if rule=='s1_dev_absorption':c.update(s1_dynamic_exit=True,s1_trough_grace=0)
 if rule=='s2_survival_shelf':c.update(s2_dynamic_exit=True)
 if rule=='s3_deadman':c.update(s3_extended_hold=60,s3_grace=8,s3_relative_price_stop=.12,s3_dynamic_arm=.75,s3_dynamic_width=.20)
 if rule=='s4_upper_ath':c.update(s4_remove_short_timeout=True,s4_rejection_grace=0)
 return c

def schedule_landing(gs,anchor,slot,count):
 dest=slot
 for _ in range(count):dest=E.O.block_at(dest+1)[0]
 # Timer-only sensitivity: after the first eventful whole transaction in the
 # specified produced slot. This is an assumption, not calibrated timing.
 import bisect
 matches=[k for k in range(anchor+1,len(gs)) if gs[k]['slot']==dest and gs[k]['trades']]
 return (matches[0] if matches else bisect.bisect_right([g['slot'] for g in gs],dest)-1),dest

def diagnostic_source(fun):
 source=inspect.getsource(fun)
 old="return dict(base,status='unresolved',reason=why,"
 assert source.count(old)==1,'approved unresolved diagnostic anchor changed'
 return source.replace(old,"return dict(base,status='unresolved',mark_available=q is not None,mark_state=dict(st),reason=why,")

def diagnostic_simulate(fun):
 namespace=dict(fun.__globals__)
 exec(compile(diagnostic_source(fun),'<approved mark availability diagnostics>','exec'),namespace)
 return namespace['simulate']

def scheduled_canonical():
 source=diagnostic_source(E.simulate)
 old="land,dest=O.landing(gs,anchor,refslot,branch(dict(sig,index=anchor),leg=f'{why}-{len(base[\"legs\"])}'));_,when=O.block_at(dest)"
 assert source.count(old)==1,'approved timer patch anchor changed'
 new="land,dest=(_schedule_landing(gs,anchor,refslot,cfg['scheduled_slots']) if target is not None and cfg.get('scheduled_slots') else O.landing(gs,anchor,refslot,branch(dict(sig,index=anchor),leg=f'{why}-{len(base[\"legs\"])}')));_,when=O.block_at(dest)"
 namespace=dict(E.__dict__,_schedule_landing=schedule_landing)
 exec(compile(source.replace(old,new),'<approved canonical timer sensitivity>','exec'),namespace)
 return namespace['simulate']

def current_ledger():
 # The live wrapper refuses another entry in a mint after a delivered close.
 # Keep identical cash, breaker and probe machinery for the risk-controlled
 # comparison. This deliberately does not imitate the incomplete S4-only map.
 source=inspect.getsource(F.funded)
 replacements=[
  ("cash=15*L;active={};admitted=[]", "cash=15*L;active={};closed_mints=set();admitted=[]"),
  ("if r['mint'] in active:skipped['same_mint_open']+=1;continue", "if r['mint'] in closed_mints:skipped['mint_previously_closed']+=1;continue\n   if r['mint'] in active:skipped['same_mint_open']+=1;continue"),
  ("active.pop(r['mint']);book(r,leg['time'],r['net'],True)","active.pop(r['mint']);closed_mints.add(r['mint']);book(r,leg['time'],r['net'],True)")]
 for old,new in replacements:
  assert source.count(old)==1,'approved ledger patch anchor changed'
  source=source.replace(old,new)
 namespace=dict(F.__dict__);exec(compile(source,'<approved current closed-mint admission>','exec'),namespace)
 return namespace['funded']

def wallet_tape(t):
 # Detection uses owner-level custody; execution uses token-account custody.
 if 'signal_groups' in t:return dict(t,groups=t['signal_groups'])
 out=[]
 for g in t['groups']:
  if g.get('venue')=='amm':continue
  z=copy.deepcopy(g);owners=z.get('account_owners',{})
  for op in z.get('custody_ops',[]):
   if op['kind']=='trade':op['owner']=op.get('inventory_owner',owners.get(op['owner'],op['event']['user']))
   elif op['kind']=='transfer':
    op['from_owner']=owners.get(op['from_owner'],op['from_owner']);op['to_owner']=owners.get(op['to_owner'],op['to_owner'])
  out.append(z)
 return dict(t,groups=out)

def hindsight_label(t):
 gs=wallet_tape(t)['groups'];first=None
 for g in gs:
  st=g['state'];mc=st['vsol_raw']/st['vtokens_raw']*1e6*145
  if first is None and mc>=20000:first=g['block_time']
  if first is not None and g['block_time']<=first+180 and mc<=6000:
   return dict(label='rapid_pump_then_collapse',cross_20k_time=first,collapse_time=g['block_time'],basis='curve spot at fixed 145 USD/SOL; hindsight only')
 return dict(label='not_observed_rapid_collapse',basis='absence is censored by collection; not proof of safe coin')

def marks(rows):
 return [dict(mint=r['mint'],rule=r['rule'],reason=r.get('reason'),venue=r.get('mark_venue','see_last_valid_group'),time=r.get('last_valid_time'),position=r.get('last_valid_position'),mark_available=r['mark_available'],mark_sol=r['mark']/1e9 if r['mark_available'] else None,open_marked_pnl_sol=(r['net']+r['mark'])/1e9 if r['mark_available'] else None) for r in rows if r['status']=='unresolved']

def enrich(result):
 result['combined_without_largest_SOL']=result['last_valid_marked_net_SOL']-result['largest_winner_SOL']
 result['rules']={}
 for rule in F.RULES:
  rr=[r for r in result['admitted'] if r['rule']==rule]
  settled=sum(r['net_SOL'] for r in rr if r['status']!='unresolved')
  opened=sum(r['net_SOL']+r['mark_SOL'] for r in rr if r['status']=='unresolved')
  result['rules'][rule]=dict(attempts=len(rr),closed=sum(r['status']=='closed' for r in rr),failed=sum(r['status']=='failed' for r in rr),unresolved=sum(r['status']=='unresolved' for r in rr),settled_sol=settled,open_marked_sol=opened,combined_sol=settled+opened)
 assert abs(result['settled_net_SOL']+result['unresolved_marked_pnl_SOL']-result['last_valid_marked_net_SOL'])<1e-8
 return result

def main():
 import current_engine as CE
 import curve_v3_extension as V3
 V3.install()
 E.O.C.rpc=clock_rpc
 if hasattr(CE,'O'):CE.O.C.rpc=clock_rpc
 tapes=pickle.load(gzip.open(OUT/'PREPARED_TAPES.pkl.gz','rb'))
 if isinstance(tapes,list):tapes={t['mint']:t for t in tapes}
 holder_rows=json.loads((OUT/'HOLDER_HISTORY.json').read_text())
 for t in tapes.values():
  for g in t['groups']:E.O.CLOCK[g['slot']]=g['time']
 prep=json.loads((OUT/'PREPARATION_AUDIT.json').read_text())
 sets={};audits=[];signals={};labels={};unmodeled=[]
 for mode in ['canonical','current']:
  for gate in ['off','local','onchain']:
   key=mode+'|'+gate;sets[key]=[]
   for t in tapes.values():
    wt=wallet_tape(t);ss,a=S.detect(wt,mode=mode,screen_mode=gate,holder_screens=holder_rows)
    audits.append(dict(comparison=key,**a))
    for s in ss:
     mint_a=prep['mints'][t['mint']]
     source_a=mint_a.get('source_parity_audit',{})
     bad=source_a.get('source_parity',{}).get('errors',[])+source_a.get('instruction_errors',[])+source_a.get('account_group_errors',[])
     if source_a.get('inventory_error'):bad.append(source_a['inventory_error'])
     positions={g['signature']:(g['slot'],g['index']) for g in wt['groups']}
     earliest=min((positions[x['signature']] for x in bad if x.get('signature') in positions),default=None)
     if not t['groups'] or (earliest is not None and earliest<=positions[s['signal_signature']]) or (bad and earliest is None):
      unmodeled.append(dict(comparison=key,signal=s,reason='source_parity_or_binding_unverified_before_entry',source_errors=bad))
      continue
     ident=(mode,s['mint'],s['rule'],s['signal_signature']);signals[ident]=s;sets[key].append(ident)
    labels[t['mint']]=hindsight_label(t)
 save('SIGNAL_AUDIT.json',audits);save('UNMODELED_SIGNALS.json',unmodeled);save('SIGNAL_SETS.json',{k:[list(x) for x in v] for k,v in sets.items()});save('SIGNALS.json',[dict(mode=k[0],**s) for k,s in signals.items()]);save('HINDSIGHT_LABELS.json',labels)
 print('SIGNALS',len(signals),{k:len(v) for k,v in sets.items()},flush=True)
 canonical_scheduled=scheduled_canonical();canonical_sim=diagnostic_simulate(E.simulate);current_sim=diagnostic_simulate(CE.simulate);current_funded=current_ledger()
 profiles=[(s,1505000,None) for s in ['fast','central80','central85','slow','stress']]+[('central85',2916000,None),('central85',1505000,1),('central85',1505000,3)]
 jobs=[]
 for ident,s in signals.items():
  for sc,fee,scheduled in profiles:
   for ticket in [.5,.25]:jobs.append((ident,s,sc,fee,scheduled,ticket))
 results=[];errors=[]
 def run(job):
  ident,s,sc,fee,scheduled,ticket=job;mode=ident[0];cfg=config(s['rule'])
  if scheduled:cfg['scheduled_slots']=scheduled
  fun=(canonical_scheduled if scheduled else canonical_sim) if mode=='canonical' else current_sim
  r=fun(tapes[s['mint']],s,sc,'lower',ticket,fee,cfg)
  r.update(mode=mode,scheduled_slots=scheduled,hindsight_label=labels[s['mint']]['label'])
  if r['status']=='unresolved' and 'mark_venue' not in r:
   p=r['last_valid_position'];r['mark_venue']='amm' if any(g.get('venue')=='amm' and (g['slot'],g['index'])<=tuple(p[:2]) for g in tapes[s['mint']]['groups']) else 'curve'
  return r
 with concurrent.futures.ThreadPoolExecutor(4) as ex:
  fs={ex.submit(run,j):j for j in jobs}
  for f in concurrent.futures.as_completed(fs):
   try:results.append(f.result())
   except Exception as exc:
    j=fs[f];errors.append(dict(identity=list(j[0]),scenario=j[2],fee=j[3],scheduled_slots=j[4],ticket=j[5],error=repr(exc)))
   if (len(results)+len(errors))%50==0:print('REPLAY',len(results),len(errors),'/',len(jobs),flush=True)
 save('REPLAY_RESULTS.json.gz',results);save('REPLAY_ERRORS.json',errors)
 if errors:raise RuntimeError('Replay exceptions retained: repair before funded headlines')
 funded=[]
 for key,ids in sets.items():
  allowed={tuple(x) for x in ids}
  for sc,fee,scheduled in profiles:
   rr=[r for r in results if (r['mode'],r['mint'],r['rule'],r['signal_signature']) in allowed and r['scenario']==sc and r['fee']==fee and r['scheduled_slots']==scheduled]
   f=(current_funded if key.startswith('current|') else F.funded)(rr,True,'portfolio',position_limit=None)
   f.update(comparison=key,scenario=sc,fee=fee,scheduled_slots=scheduled,eligible_replayable_signals=len(ids),eligible_unmodeled_signals=sum(x['comparison']==key for x in unmodeled),risk_policy='canonical all-family/global breakers/probes held fixed in both comparisons; not deployed S4-only map')
   f=enrich(f)
   admitted_keys={(r['mint'],r['rule'],.25 if r['probe'] else .5) for r in f['admitted']}
   f['mark_provenance']=marks([r for r in rr if (r['mint'],r['rule'],r['ticket']) in admitted_keys])
   f['unavailable_mark_count']=sum(not m['mark_available'] for m in f['mark_provenance'])
   f['available_open_marked_pnl_SOL']=sum(m['open_marked_pnl_sol'] for m in f['mark_provenance'] if m['mark_available'])
   if f['unavailable_mark_count']:
    # Raw ledger cash flows remain auditable. Its zero placeholders must not
    # become an expected portfolio PnL when an executable mark is unavailable.
    f['last_valid_marked_net_SOL']=None;f['net_marked_SOL']=None;f['unresolved_marked_pnl_SOL']=None;f['combined_without_largest_SOL']=None
    for rule in {m['rule'] for m in f['mark_provenance'] if not m['mark_available']}:
     f['rules'][rule]['open_marked_sol']=None;f['rules'][rule]['combined_sol']=None
   funded.append(f)
 save('FUNDED_RESULTS.json',funded)
 print('FUNDED_COMPLETE',len(funded),'results',len(results),flush=True)
 for f in funded:
  if f['scenario']=='central85' and f['fee']==1505000 and not f['scheduled_slots']:
   print(f['comparison'],f['attempts'],f['closed'],f['failed'],f['unresolved'],f['settled_net_SOL'],f['unresolved_marked_pnl_SOL'],f['last_valid_marked_net_SOL'],flush=True)

if __name__=='__main__':main()
