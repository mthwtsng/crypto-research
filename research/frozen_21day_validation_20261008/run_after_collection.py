"""Continue preparation, authenticated migration recovery and frozen replay."""
import concurrent.futures,datetime,gzip,hashlib,importlib.util,json,pathlib,sys,time
import rpc_pool as R
import collect_validation as C
import prepare_validation as B
P=R.OUT;ROOT=R.ROOT
sys.path.insert(0,str(ROOT/'research/core_plan_audit_20261007'));import engine as E,ledger as F
sys.path.insert(0,str(ROOT/'research/core_gap_refinement_20261007'));import tailored_requested as T
sys.path.insert(0,str(ROOT/'research/wallet_curve_entry_discovery_20261007'));import repair_amm_custody as AC
spec=importlib.util.spec_from_file_location('validation_migration_codec',ROOT/'research/amm_multiday_20261006/collect.py');MC=importlib.util.module_from_spec(spec);spec.loader.exec_module(MC)
spec=importlib.util.spec_from_file_location('validation_amm_prepare',ROOT/'research/amm_multiday_20261006/prepare.py');AP=importlib.util.module_from_spec(spec);spec.loader.exec_module(AP)
MC.MIG={k:v for k,v in MC.MIG.items() if v['name'] in ['migrate','migrate_v2']}
E.O.C.rpc=R.rpc;E.O.C.P=P

def pool(m):
 dest=P/'amm_tapes'/(m['pool']+'.json.gz')
 if dest.exists():return json.load(gzip.open(dest,'rt'))
 raw=P/'continuation_pools'/dest.name
 if not raw.exists():
  through=m['time']+3600;rows=C.history(m['pool'],m['time'],through,'succeeded')
  if m['signature'] not in {t['transaction']['signatures'][0] for t in rows}:raise ValueError('pool_opening_receipt_missing')
  R.save(raw,dict(coverage=dict(pool=m['pool'],complete=True,through_time=through,migration=m),transactions=rows))
 tape,audit=AP.prepare(raw);d=json.load(gzip.open(raw,'rt'));by={t['transaction']['signatures'][0]:t for t in d['transactions']};gs=tape['groups']
 for g in gs:
  g['raw_events']=[e for e in E.M.A.events(by[g['signature']]) if e.get('pool')==m['pool']]
  g['custody_ops'],g['custody_error']=AC.custody(by[g['signature']],m,g['trades'],g);g.pop('raw_events',None)
 v=gs[0]['state']['virtual']
 for g in gs[1:]:
  if g.get('reserve_shift') and not g['trades'] and (sum(o.get('raw',0) for o in g['custody_ops'] if o['kind']=='sweep')!=g['reserve_shift'] or g.get('custody_error')):
   if not g.get('fee_sweep') or g['pre'][1]-g['post'][1]!=g['reserve_shift'] or g.get('custody_error') not in [None,'sweep_instruction_event_count']:raise ValueError('unauthenticated_quiet_sweep')
   g['custody_ops']=[dict(kind='sweep',raw=g['reserve_shift'])];g['custody_error']=None
  g['before']['virtual']=v;st=dict(g['before'])
  for op in g['custody_ops']:
   if op['kind']=='sweep':v+=op['raw'];st['virtual']=v;st['quote']-=op['raw'];continue
   if op['kind']!='trade':continue
   e=op['event']
   if e['virtual']!=v:raise ValueError('virtual_prestate_gap')
   val=dict(st,historical_rates=e['rates']);q=(E.M.A.buy(val,e['gross']) if e['ix'].startswith('buy_exact_quote_in') else E.M.A.exact_buy(val,e['n'])) if e['buy'] else E.M.A.sell(val,e['n'])
   if not q or (q['n'],q['q'])!=(e['n'],e['q']):raise ValueError('pool_source_quote_mismatch')
   st=E.M.moved(st,q,e['buy'],e.get('deferred',False));v=st['virtual']
  g['state']['virtual']=v
 st=dict(gs[0]['state']);h={};cf={};checked=0
 for g in gs[1:]:
  z,hh,cc,error=E.M.advance(st,g,h,cf)
  if error or hh!=cc or z.get('source_reverts',0) or any(z[k]!=g['state'][k] for k in ['base','quote','virtual','supply']):raise ValueError(dict(reason='pool_whole_source_parity',signature=g['signature'],error=error))
  st,h,cf=z,hh,cc;checked+=1
 tape['signals']=[];R.save(dest,tape);R.save(P/'pool_audits'/(m['pool']+'.json'),dict(pool=m['pool'],groups_checked=checked,source_audit=audit,whole_source_parity=True));return tape

def continuation(mint,signals):
 dest=P/'execution_tapes'/(mint+'.json.gz')
 if dest.exists():return json.load(gzip.open(dest,'rt'))
 raw=P/'raw_curves'/dest.name;original=json.load(gzip.open(raw,'rt'));t=json.load(gzip.open(P/'bound_curve_tapes'/dest.name,'rt'))
 latest=max(s['time'] for s in signals);end=max(original['requested_end_time'],latest+86400)
 # Every eligible path gets the same one-day migration search, independent of returns.
 extended=P/'migration_receipts'/dest.name
 if extended.exists():d=json.load(gzip.open(extended,'rt'))
 else:
  rows=C.history(t['curve'],t['creation_time'],end,'succeeded');d=dict(original,transactions=rows,requested_end_time=end);R.save(extended,d)
 migrations=[m for tx in d['transactions'] for m in MC.migrations(tx) if m['mint']==mint]
 if len({m['pool'] for m in migrations})>1:raise ValueError('ambiguous_migration')
 if migrations and not any(g['state']['rtokens_raw']==0 for g in t['groups']):
  # Repair the full genuine source continuation instead of treating late
  # migration as an unresolved file-end artifact.
  oldsignals=json.load(open(P/'signals_by_mint'/(mint+'.json')))
  B.build(extended,force=True)
  newsignals=json.load(open(P/'signals_by_mint'/(mint+'.json')))
  if {(s['rule'],s['signal_signature']) for s in oldsignals}!={(s['rule'],s['signal_signature']) for s in newsignals}:raise ValueError('historical_prefix_changed_after_coverage_repair')
  t=json.load(gzip.open(P/'bound_curve_tapes'/dest.name,'rt'))
 gs=[dict(g,venue='curve',trades=g['events'],time=g['block_time']) for g in t['groups']]
 for m in migrations:
  if m['quote_mint']!=MC.WSOL:raise ValueError('unsupported_migration_quote')
  pt=pool(m)
  complete=next((g for g in gs if g['state']['rtokens_raw']==0),None)
  if complete is None:raise ValueError('migration_beyond_initial_curve_coverage_requires_curve_extension')
  t['migration_quote_difference']=complete['state']['rsol_raw']-pt['groups'][0]['before']['quote'];gs.extend(dict(g,venue='amm') for g in pt['groups']);t['end_time']=max(t['end_time'],m['time']+3600)
 gs.sort(key=lambda g:(g['slot'],g['index']));t['groups']=gs
 R.save(dest,t);return t

def primary(s):return s['rule']!='s2_survival_shelf' or s['age_seconds']<=240 and s['outside_buyers']<=80

def main():
 while not (P/'COLLECTION_COMPLETE.json').exists():
  time.sleep(30)
 frozen=json.load(open(P/'FREEZE.json'))
 for name,digest in {**frozen['hashes'],**frozen['execution_code_pin']}.items():
  if name.endswith('.py') and hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:raise RuntimeError('frozen execution source changed: '+name)
 complete=json.load(open(P/'COLLECTION_COMPLETE.json'))
 if complete['errors']:raise RuntimeError('collection errors require repair before validation')
 B.main();signals=json.load(open(P/'SIGNALS.json'));by={}
 for s in signals:by.setdefault(s['mint'],[]).append(s)
 tapes={};errors=[]
 with concurrent.futures.ThreadPoolExecutor(4) as ex:
  fs={ex.submit(continuation,m,ss):m for m,ss in by.items()}
  for f in concurrent.futures.as_completed(fs):
   try:tapes[fs[f]]=f.result()
   except Exception as e:errors.append(dict(mint=fs[f],error=str(e)))
   if (len(tapes)+len(errors))%10==0:print('CONTINUATION',len(tapes),len(errors),'/',len(by),flush=True);R.save(P/'CONTINUATION_PROGRESS.json',dict(total=len(by),recovered=len(tapes),errors=errors))
 R.save(P/'CONTINUATION_COMPLETE.json',dict(total=len(by),recovered=len(tapes),errors=errors))
 if errors:raise RuntimeError('repair coverage; do not silently omit eligible signals')
 for t in tapes.values():
  for g in t['groups']:E.O.CLOCK[g['slot']]=g['time']
 jobs=[]
 for policy in ['control','primary']:
  for s in signals:
   if policy=='primary' and not primary(s):continue
   config=T.cfg(s['rule'],60,'percentage_points')
   if policy=='primary' and s['rule']=='s4_upper_ath':config['s4_rejection_grace']=4
   for sc,fee in [(x,1505000) for x in ['fast','central80','central85','slow','stress']]+[('central85',2916000)]:
    for ticket in [.5,.25]:jobs.append((policy,s,sc,fee,ticket,config))
 rows=[];errors=[]
 def run(j):
  policy,s,sc,fee,ticket,config=j;return dict(E.simulate(tapes[s['mint']],s,sc,'lower',ticket,fee,config),policy=policy)
 with concurrent.futures.ThreadPoolExecutor(4) as ex:
  fs={ex.submit(run,j):j for j in jobs}
  for f in concurrent.futures.as_completed(fs):
   try:rows.append(f.result())
   except Exception as e:errors.append(dict(mint=fs[f][1]['mint'],error=str(e)))
   if (len(rows)+len(errors))%100==0:print('REPLAY',len(rows),len(errors),'/',len(jobs),flush=True)
 R.save(P/'REPLAY.json.gz',rows);R.save(P/'REPLAY_ERRORS.json',errors)
 if errors:raise RuntimeError('replay errors, no profit headline')
 accounts=[]
 for policy in ['control','primary']:
  for sc,fee in [(x,1505000) for x in ['fast','central80','central85','slow','stress']]+[('central85',2916000)]:
   rr=[r for r in rows if (r['policy'],r['scenario'],r['fee'])==(policy,sc,fee)]
   for cap in [2,5,10,15,None]:
    for br in [True,False]:accounts.append(dict(policy=policy,position_limit=cap,scenario=sc,fee=fee,**F.funded(rr,br,'portfolio',position_limit=cap)))
 R.save(P/'FUNDED.json',accounts);R.save(P/'REPLAY_COMPLETE.json',dict(sampled=complete['selected'],signals=len(signals),replays=len(rows),funded=len(accounts),headline_ready=False,next='Independent fill checks, bug-alarm attribution, mark provenance and block-bootstrap uncertainty required before verdict'))
 print('REPLAY_COMPLETE; AWAIT INDEPENDENT REPORT CHECKS',flush=True)
if __name__=='__main__':
 try:main()
 except Exception as e:
  R.save(P/'PIPELINE_STOP.json',dict(time=datetime.datetime.now(datetime.timezone.utc).isoformat(),error=str(e),status='explicit stop; no incomplete-coverage profit claim'));raise
