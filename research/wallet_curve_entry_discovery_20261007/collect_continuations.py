"""Recover authentic curve+AMM continuations for every frozen eligible mint, including failures to migrate."""
import concurrent.futures,gzip,hashlib,importlib.util,json,pathlib,sys
P=pathlib.Path(__file__).resolve().parent;R=P.parents[1]
sys.path.insert(0,str(R/'research/automated_wallet_expansion_20261006'));import collect_wallets as RPC
spec=importlib.util.spec_from_file_location('migration_decode',R/'research/amm_multiday_20261006/collect.py');M=importlib.util.module_from_spec(spec);spec.loader.exec_module(M)
# Creator fee-sharing reassignment is not token graduation or pool migration.
M.MIG={d:i for d,i in M.MIG.items() if i['name'] in ('migrate','migrate_v2')}

def request(method,params):
 key=hashlib.sha256(json.dumps([method,params],sort_keys=True).encode()).hexdigest()
 return RPC.rpc(method,params,P/'continuation_rpc'/(key+'.json.gz'))

def history(address,end):
 token=None;ts=[];seen=set()
 for _ in range(200):
  cfg=dict(transactionDetails='full',encoding='jsonParsed',maxSupportedTransactionVersion=1,commitment='finalized',sortOrder='asc',limit=1000,filters=dict(status='succeeded',blockTime=dict(lte=end)))
  if token:cfg['paginationToken']=token
  res=request('getTransactionsForAddress',[address,cfg]);ts+=res['data'];nxt=res.get('paginationToken')
  if not nxt:break
  if nxt in seen:raise ValueError('pagination_cycle')
  token=nxt;seen.add(token)
 else:raise ValueError('history_cap')
 ts=list({t['transaction']['signatures'][0]:t for t in ts}.values())
 if any(t.get('transactionIndex') is None for t in ts):raise ValueError('missing_provider_order')
 return sorted(ts,key=lambda t:(t['slot'],t['transactionIndex']))

def run(job):
 mint=job['mint'];out=P/'continuations'/(mint+'.json.gz')
 if out.exists():return json.load(gzip.open(out,'rt'))['audit']
 end=job['latest_signal_time']+1800;ts=history(job['curve'],end)
 if not any(c['mint']==mint for t in ts for c in M.D.creations(t)):raise ValueError('creation_missing')
 migrations=[m for t in ts for m in M.migrations(t) if m['mint']==mint]
 if len({m['pool'] for m in migrations})>1:raise ValueError('ambiguous_migration')
 pools=[]
 for m in migrations:
  if m['quote_mint']!=M.WSOL:raise ValueError('unsupported_quote')
  through=max(end,m['time']+600);pts=history(m['pool'],through)
  if not any(t['transaction']['signatures'][0]==m['signature'] for t in pts):raise ValueError('missing_pool_creation')
  coverage=dict(pool=m['pool'],complete=True,transactions=len(pts),through_time=through,decision_end=through-600,migration=m)
  RPC.save(P/'continuation_pools'/(m['pool']+'.json.gz'),dict(coverage=coverage,transactions=pts));pools.append(dict(migration=m,coverage=coverage))
 complete_events=[dict(signature=t['transaction']['signatures'][0],slot=t['slot'],index=t['transactionIndex'],time=t['blockTime']) for t in ts if any(e['mint']==mint and e['real_token_reserves']==0 for e in M.D.events(t))]
 audit=dict(mint=mint,curve=job['curve'],curve_receipts=len(ts),from_creation=True,through_time=end,migrations=migrations,completion_events=complete_events,amm_pools=pools,status='migration_recovered' if pools else 'curve_history_recovered_no_migration_in_window',scope='actual source receipts; not counterfactual PnL or predicted graduation')
 RPC.save(out,dict(audit=audit,transactions=ts));return audit
if __name__=='__main__':
 import pickle
 tapes=pickle.load(gzip.open(R/'research/day_general_20261004/TAPES.pkl.gz','rb'));by={t['mint']:t for t in tapes};signals=json.loads((P/'SIGNALS.json').read_text());jobs={}
 for s in signals:
  m=s['mint'];j=jobs.setdefault(m,dict(mint=m,curve=by[m]['curve'],latest_signal_time=s['time'],rules=[]));j['latest_signal_time']=max(j['latest_signal_time'],s['time']);j['rules'].append(s['rule'])
 jobs=sorted(jobs.values(),key=lambda j:('late_continuation' not in j['rules'],hashlib.sha256(j['mint'].encode()).hexdigest()))
 RPC.save(P/'CONTINUATION_SELECTION.json',dict(jobs=jobs,selection='all eligible mints from four frozen entry hypotheses on600creation-sampled launches; includes every nongraduating eligible mint; late-rule priority changes acquisition order only',curve_extra_seconds=1800,amm_extra_seconds=600))
 audits=[];errors=[]
 with concurrent.futures.ThreadPoolExecutor(2) as ex:
  fs={ex.submit(run,j):j for j in jobs}
  for f in concurrent.futures.as_completed(fs):
   j=fs[f]
   try:audits.append(f.result());print('CONTINUATION',j['mint'][:8],audits[-1]['status'],len(audits[-1]['migrations']),flush=True)
   except Exception as e:errors.append(dict(mint=j['mint'],error=str(e)));print('ERROR',errors[-1],flush=True)
   RPC.save(P/'CONTINUATION_PROGRESS.json',dict(total=len(jobs),audits=audits,errors=errors))
 RPC.save(P/'CONTINUATION_COMPLETE.json',dict(total=len(jobs),audits=audits,errors=errors));print('CONTINUATION_COMPLETE',len(audits),len(errors),flush=True)
