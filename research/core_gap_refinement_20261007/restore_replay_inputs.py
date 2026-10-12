"""Recollect deleted frozen-cohort receipts; never substitute synthetic fills."""
import collections,concurrent.futures,gzip,importlib.util,json,pathlib,sys
P=pathlib.Path(__file__).resolve().parent;ROOT=P.parents[1];OUT=P/'grace_verification_cycle/restored_inputs';OUT.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(ROOT/'research/amm_multiday_20261006'));import collect as RPC
sys.path.insert(0,str(ROOT/'research/day_general_20261004/helpers'))
sys.path.insert(0,str(ROOT/'research/wallet_curve_entry_discovery_20261007'));import bind_curve_limits as LIMIT,merge_curve_receipts as ACCOUNT
spec=importlib.util.spec_from_file_location('restore_curve_prepare',ROOT/'research/day_general_20261004/prepare.py');B=importlib.util.module_from_spec(spec);spec.loader.exec_module(B)
RPC.P=OUT
saved=json.load(gzip.open(P/'tailored_requested_cycle/REPLAY.json.gz','rt'));jobs={}
for r in saved:
 key=r['window'],r['mint'];j=jobs.setdefault(key,dict(window=r['window'],mint=r['mint'],curve=r['curve'],latest_signal_time=r['time']))
 j['latest_signal_time']=max(j['latest_signal_time'],r['time'])
def history(address,end):
 cfg=dict(transactionDetails='full',encoding='jsonParsed',maxSupportedTransactionVersion=1,commitment='finalized',sortOrder='asc',limit=1000,filters=dict(status='succeeded',blockTime=dict(lte=end)))
 rows=[];seen=set()
 for page in range(200):
  res=RPC.rpc('getTransactionsForAddress',[address,cfg]);rows+=res['data'];token=res.get('paginationToken')
  if not token:break
  if token in seen:raise ValueError('pagination_cycle')
  seen.add(token);cfg['paginationToken']=token
 else:raise ValueError('history_cap')
 by={t['transaction']['signatures'][0]:t for t in rows}
 if any(t.get('transactionIndex') is None for t in by.values()):raise ValueError('missing_transaction_order')
 return sorted(by.values(),key=lambda t:(t['slot'],t['transactionIndex']))
def one(j):
 path=OUT/j['window']/'receipts'/(j['mint']+'.json.gz')
 if path.exists():return dict(j,status='cached')
 end=j['latest_signal_time']+1800;rows=history(j['curve'],end)
 RPC.save(path,dict(mint=j['mint'],transactions=rows,requested_end_time=end))
 return dict(j,status='collected',receipts=len(rows))
def main():
 progress=[];errors=[]
 with concurrent.futures.ThreadPoolExecutor(4) as ex:
  fs={ex.submit(one,j):j for j in jobs.values()}
  for f in concurrent.futures.as_completed(fs):
   try:progress.append(f.result())
   except Exception as e:errors.append(dict(job=fs[f],error=repr(e)))
   RPC.save(OUT/'COLLECTION.json',dict(total=len(jobs),progress=progress,errors=errors))
   print('RECEIPTS',len(progress),len(errors),'/',len(jobs),flush=True)
 print('COLLECTED',len(progress),'ERRORS',len(errors),flush=True)
if __name__=='__main__':main()

def rebuild_curves():
 import collections
 audits=[]
 for j in jobs.values():
  dest=OUT/j['window']/'bound_curve_tapes'/(j['mint']+'.json.gz')
  if dest.exists():continue
  d=json.load(gzip.open(OUT/j['window']/'receipts'/dest.name,'rt'));by={x['transaction']['signatures'][0]:x for x in d['transactions']}
  t,a=B.make(d)
  if t is None:raise ValueError(a)
  # Same pre-completion domain as the original repaired/bound curve tapes.
  end=next((i+1 for i,g in enumerate(t['groups']) if g['state']['rtokens_raw']==0),len(t['groups']));t['groups']=t['groups'][:end]
  for g in t['groups']:
   limits=LIMIT.bind(by[g['signature']],t['mint'])
   if len(limits)!=len(g['events']):raise ValueError(('instruction_event_count',t['mint'],g['signature']))
   for e,lim in zip(g['events'],limits):e.update(lim['fields']);e['instruction_name']=lim['name']
  t['groups']=[ACCOUNT.account_group(g,by[g['signature']],t['mint']) for g in t['groups']]
  t['inventory_key']='token_account'
  RPC.save(dest,t);audits.append(dict(mint=t['mint'],window=j['window'],groups=len(t['groups']),source_audit=a,custody_issue_groups=sum(bool(g['custody_issues']) for g in t['groups'])))
  RPC.save(OUT/'CURVE_REBUILD.json',audits)
  print('BOUND',len(audits),j['window'],j['mint'][:8],flush=True)

def rebuild_pools():
 import collections,hashlib,struct
 import amm_adapter as A
 spec=importlib.util.spec_from_file_location('restored_amm_prepare',ROOT/'research/amm_multiday_20261006/prepare.py');AP=importlib.util.module_from_spec(spec);spec.loader.exec_module(AP)
 spec=importlib.util.spec_from_file_location('restored_amm_custody',ROOT/'research/wallet_curve_entry_discovery_20261007/repair_amm_custody.py');C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C)
 import amm_counterparty as M
 RPC.MIG={d:i for d,i in RPC.MIG.items() if i['name'] in ('migrate','migrate_v2')}
 names={f.name for f in (ROOT/'research/core_plan_audit_20261007/amm_tapes').glob('*.gz')}
 migrations=[]
 for j in jobs.values():
  if j['window']!='earlier':continue
  d=json.load(gzip.open(OUT/'earlier/receipts'/(j['mint']+'.json.gz'),'rt'))
  migrations +=[(j,m) for tx in d['transactions'] for m in RPC.migrations(tx) if m['pool']+'.json.gz' in names]
 audits=[]
 for j,m in migrations:
  dest=OUT/'earlier/amm_tapes'/(m['pool']+'.json.gz')
  if dest.exists():continue
  raw=OUT/'earlier/pool_receipts'/dest.name
  if not raw.exists():
   end=max(j['latest_signal_time']+1800,m['time']+600);txs=history(m['pool'],end)
   RPC.save(raw,dict(coverage=dict(pool=m['pool'],complete=True,through_time=end,migration=m),transactions=txs))
  tape,audit=AP.prepare(raw);d=json.load(gzip.open(raw,'rt'));by={x['transaction']['signatures'][0]:x for x in d['transactions']}
  for g in tape['groups']:
   tx=by[g['signature']];g['raw_events']=[e for e in A.events(tx) if e.get('pool')==m['pool']];g['custody_ops'],g['custody_error']=C.custody(tx,m,g['trades'],g);g.pop('raw_events',None)
  v=tape['groups'][0]['state']['virtual'];normalization_errors=[]
  for g in tape['groups'][1:]:
   g['before']['virtual']=v;st=dict(g['before'])
   for op in g['custody_ops']:
    if op['kind']=='sweep':v+=op['raw'];st['virtual']=v;st['quote']-=op['raw'];continue
    if op['kind']!='trade':continue
    e=op['event']
    if e['virtual']!=v:normalization_errors.append(dict(signature=g['signature'],kind='virtual_prestate_gap'))
    val=dict(st,historical_rates=e['rates']);r=(A.buy(val,e['gross']) if e['ix'].startswith('buy_exact_quote_in') else A.exact_buy(val,e['n'])) if e['buy'] else A.sell(val,e['n'])
    if not r or (r['n'],r['q'])!=(e['n'],e['q']):normalization_errors.append(dict(signature=g['signature'],kind='source_quote_mismatch'));continue
    st=M.moved(st,r,e['buy'],e.get('deferred',False));v=st['virtual']
   g['state']['virtual']=v
  tape['signals']=[];RPC.save(dest,tape)
  audit.update(normalization_errors=normalization_errors,custody_gaps=sum(bool(g['custody_error']) for g in tape['groups']))
  audits.append(audit);RPC.save(OUT/'AMM_REBUILD.json',audits)
  print('AMM_REBUILT',m['pool'][:8],'groups',len(tape['groups']),'parser_errors',len(audit['errors']),'virtual_errors',len(normalization_errors),'custody_gaps',audit['custody_gaps'],flush=True)

def restore_pkl_transfers():
 """Restore authenticated repair receipts whose signatures survive in PKL."""
 import pickle
 missing=[];pkl={}
 for window,src in [('earlier',ROOT/'research/day_general_20261004/TAPES.pkl.gz'),('later',P/'fresh_oct05_oct06/REPAIRED_SELECTION.pkl.gz')]:
  pkl[window]={t['mint']:t for t in pickle.load(gzip.open(src,'rb'))}
  for j in jobs.values():
   if j['window']!=window:continue
   d=json.load(gzip.open(OUT/window/'receipts'/(j['mint']+'.json.gz'),'rt'));sigs={tx['transaction']['signatures'][0] for tx in d['transactions']}
   for g in pkl[window][j['mint']]['groups']:
    if g['signature'] not in sigs:missing.append((window,j['mint'],g))
 def get(job):
  window,mint,g=job;raw=RPC.rpc('getTransaction',[g['signature'],dict(encoding='jsonParsed',commitment='finalized',maxSupportedTransactionVersion=1)])
  if raw is None or raw['slot']!=g['slot'] or raw['blockTime']!=g['block_time']:raise ValueError('repair_receipt_mismatch')
  raw['transactionIndex']=g['index'] # Original authenticated provider order preserved in PKL.
  return window,mint,raw
 additions=collections.defaultdict(list)
 with concurrent.futures.ThreadPoolExecutor(4) as ex:
  for i,(w,m,tx) in enumerate(ex.map(get,missing),1):
   additions[w,m].append(tx)
   if i%25==0:print('REPAIR_RECEIPT',i,'/',len(missing),flush=True)
 for (w,m),rows in additions.items():
  f=OUT/w/'receipts'/(m+'.json.gz');d=json.load(gzip.open(f,'rt'));d['transactions']+=rows;RPC.save(f,d)
  dest=OUT/w/'bound_curve_tapes'/f.name
  if dest.exists():dest.unlink()
 print('RESTORED_REPAIR_RECEIPTS',len(missing),flush=True)
 rebuild_curves()

def reconcile_pools():
 """Repair codec-name drift using authenticated quiet fee-sweep vault deltas."""
 import amm_counterparty as M
 audits=[]
 for f in (OUT/'earlier/amm_tapes').glob('*.gz'):
  t=json.load(gzip.open(f,'rt'));gs=t['groups'];fixed=0;v=gs[0]['state']['virtual'];errors=[]
  for g in gs[1:]:
   if g.get('reserve_shift') and not g['trades'] and (sum(o.get('raw',0) for o in g['custody_ops'] if o['kind']=='sweep')!=g['reserve_shift'] or g.get('custody_error')):
    if not g.get('fee_sweep') or g['trades'] or g['pre'][1]-g['post'][1]!=g['reserve_shift']:raise ValueError('unauthenticated_quiet_sweep')
    if g.get('custody_error') not in [None,'sweep_instruction_event_count']:raise ValueError('non_sweep_custody_gap')
    g['custody_ops']=[dict(kind='sweep',raw=g['reserve_shift'])];g['custody_error']=None;fixed+=1
   g['before']['virtual']=v;st=dict(g['before'])
   for op in g['custody_ops']:
    if op['kind']=='sweep':v+=op['raw'];st['virtual']=v;st['quote']-=op['raw'];continue
    if op['kind']!='trade':continue
    e=op['event']
    if e['virtual']!=v:errors.append(dict(signature=g['signature'],kind='virtual_prestate_gap',expected=v,observed=e['virtual']))
    val=dict(st,historical_rates=e['rates']);r=(M.A.buy(val,e['gross']) if e['ix'].startswith('buy_exact_quote_in') else M.A.exact_buy(val,e['n'])) if e['buy'] else M.A.sell(val,e['n'])
    if not r or (r['n'],r['q'])!=(e['n'],e['q']):errors.append(dict(signature=g['signature'],kind='source_quote_mismatch'));continue
    st=M.moved(st,r,e['buy'],e.get('deferred',False));v=st['virtual']
   g['state']['virtual']=v
  RPC.save(f,t);st=dict(gs[0]['state']);h={};cf={};checked=0
  for g in gs[1:]:
   z,hh,cc,err=M.advance(st,g,h,cf)
   if err or any(z[k]!=g['state'][k] for k in ['base','quote','virtual','supply']) or hh!=cc or z.get('source_reverts',0):errors.append(dict(signature=g['signature'],kind='whole_source_parity',reason=err));break
   st,h,cf=z,hh,cc;checked+=1
  audits.append(dict(pool=t['pool'],groups=len(gs),checked=checked,quiet_sweeps_restored=fixed,errors=errors));print('AMM_PARITY',t['pool'][:8],checked,'/',len(gs)-1,'errors',len(errors),flush=True)
  RPC.save(OUT/'AMM_PARITY.json',audits)
