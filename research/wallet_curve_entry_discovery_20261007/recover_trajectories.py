"""Recover fixed outcome-independent wallet entry samples from creation through +600s."""
import concurrent.futures,gzip,hashlib,importlib.util,json,pathlib,sys
P=pathlib.Path(__file__).resolve().parent;R=P.parents[1]
sys.path.insert(0,str(R/'research/automated_wallet_expansion_20261006'))
import collect_wallets as C
sys.path.insert(0,str(R/'research/day_general_20261004/helpers'))
import decoder as D
W=('88887','9999hu','sssss','3VUN')
features=json.loads((R/'research/automated_wallet_discovery_20261006/ENTRY_FEATURES.json').read_text())
freeze=P/'TRAJECTORY_SELECTION.json'
if freeze.exists():selected=json.loads(freeze.read_text())['entries']
else:
 selected=[]
 for prefix in W:
  rows=[r for r in features if r.get('wallet','').startswith(prefix) and r.get('genesis_verified') and r.get('quote_is_sol') and not r.get('wallet_is_launch_role')]
  selected+=sorted(rows,key=lambda r:hashlib.sha256(('curve-entry-study-v1|'+r['signature']).encode()).hexdigest())[:10]
 C.save(freeze,dict(entries=selected,selection='10 fixedhash previously sampled entries per four wallets; no per-trade profit filter; wallet universe historically selected for profitability; retrospective',horizon_seconds=600))
def allix(t):return t['transaction']['message']['instructions']+[i for g in t['meta'].get('innerInstructions',[]) or [] for i in g['instructions']]
def run(b):
 dest=P/'trajectories'/(b['signature']+'.json.gz')
 if dest.exists():return json.load(gzip.open(dest,'rt'))['audit']
 t=C.rpc('getTransaction',[b['signature'],dict(encoding='jsonParsed',commitment='finalized',maxSupportedTransactionVersion=1)],P/'rpc'/(b['signature']+'.json.gz'))
 own=[e for e in D.events(t) if e['mint']==b['mint'] and e['user']==b['wallet'] and e['buy']]
 if not own:raise ValueError('not_authenticated_curve_buy')
 curves=[]
 for ix in allix(t):
  if ix.get('programId')!=D.PUMP:continue
  ac=ix.get('accounts',[])
  if len(ac)>3 and ac[2]==b['mint']:curves.append(ac[3])
  elif len(ac)>10 and ac[1]==b['mint']:curves.append(ac[10])
 if len(set(curves))!=1:raise ValueError('curve_binding_ambiguous')
 curve=curves[0];token=None;ts=[];seen=set();complete=False
 for page in range(150):
  cfg=dict(transactionDetails='full',encoding='jsonParsed',maxSupportedTransactionVersion=1,commitment='finalized',sortOrder='asc',limit=1000,filters=dict(status='succeeded',blockTime=dict(lte=b['time']+600)))
  if token:cfg['paginationToken']=token
  params=[curve,cfg];key=hashlib.sha256(json.dumps(params,sort_keys=True).encode()).hexdigest()
  res=C.rpc('getTransactionsForAddress',params,P/'history'/(key+'.json.gz'));ts+=res['data'];nxt=res.get('paginationToken')
  if not nxt:complete=True;break
  if nxt in seen:raise ValueError('pagination_cycle')
  seen.add(nxt);token=nxt
 if not complete:raise ValueError('history_cap')
 ts=list({x['transaction']['signatures'][0]:x for x in ts}.values())
 if any(x.get('transactionIndex') is None for x in ts):raise ValueError('missing_order')
 ts.sort(key=lambda x:(x['slot'],x['transactionIndex']))
 creates=[c for x in ts for c in D.creations(x) if c['mint']==b['mint']]
 if not creates:raise ValueError('missing_creation')
 if not any(x['transaction']['signatures'][0]==b['signature'] for x in ts):raise ValueError('missing_entry')
 audit=dict(wallet=b['wallet'],mint=b['mint'],signature=b['signature'],curve=curve,receipts=len(ts),authenticated_curve_buy=True,from_creation=True,requested_through=b['time']+600,complete_filtered_census=True)
 C.save(dest,dict(entry=b,transactions=ts,audit=audit));return audit
if __name__=='__main__':
 good=[];bad=[]
 with concurrent.futures.ThreadPoolExecutor(2) as ex:
  jobs={ex.submit(run,b):b for b in selected}
  for f in concurrent.futures.as_completed(jobs):
   b=jobs[f]
   try:good.append(f.result());print('RECOVERED',b['wallet'][:8],b['mint'][:8],good[-1]['receipts'],flush=True)
   except Exception as e:bad.append(dict(wallet=b['wallet'],mint=b['mint'],signature=b['signature'],error=str(e)));print('ERROR',bad[-1],flush=True)
   C.save(P/'RECOVERY_PROGRESS.json',dict(total=len(selected),recovered=good,errors=bad))
 C.save(P/'RECOVERY_COMPLETE.json',dict(total=len(selected),recovered=good,errors=bad));print('RECOVERY_COMPLETE',len(good),len(bad),flush=True)
