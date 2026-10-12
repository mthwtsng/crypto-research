"""Outcome-independent hourly creation sample on later October5–6 data."""
import concurrent.futures,datetime,gzip,hashlib,json,pathlib,pickle,sys
P=pathlib.Path(__file__).resolve().parent/'fresh_oct05_oct06';ROOT=P.parents[2]
sys.path.insert(0,str(ROOT/'research/day_general_20261004'));import collect as G
sys.path.insert(0,str(ROOT/'research/automated_wallet_expansion_20261006'));import collect_wallets as R
P.mkdir(exist_ok=True)
def request(method,params):
 key=hashlib.sha256(json.dumps([method,params],sort_keys=True).encode()).hexdigest();return R.rpc(method,params,P/'rpc'/(key+'.json.gz'))
G.rpc=request;G.HERE=P

def run_tape(item):
 f=P/'raw_curves'/(item['mint']+'.json.gz')
 if f.exists():d=json.load(gzip.open(f,'rt'))
 else:
  end=item['creation_time']+1800;ts=[];token=None
  for page in range(100):
   cfg=dict(transactionDetails='full',encoding='jsonParsed',maxSupportedTransactionVersion=1,sortOrder='asc',limit=1000,commitment='finalized',filters=dict(status='succeeded',blockTime=dict(lte=end)))
   if token:cfg['paginationToken']=token
   r=request('getTransactionsForAddress',[item['creation']['bonding_curve'],cfg]);ts+=r['data'];nxt=r.get('paginationToken')
   if not nxt:break
   if nxt==token:raise ValueError('pagination_cycle')
   token=nxt
  else:raise ValueError('history_cap')
  if any(t.get('transactionIndex') is None for t in ts):raise ValueError('missing_provider_index')
  d=dict(mint=item['mint'],requested_end_time=end,transactions=list({t['transaction']['signatures'][0]:t for t in ts}.values()));R.save(f,d)
 t,a=G.P.make(d)
 if t:t['creation_metadata']=item['creation'];t['source']='frozen_later_hourly_creation_sample'
 return t,a

def main():
 fr=json.loads((P/'FREEZE.json').read_text());jobs=[(fr['start']+i*3600,fr['start']+(i+1)*3600) for i in range(48)];census=[]
 with concurrent.futures.ThreadPoolExecutor(4) as ex:
  fs={ex.submit(G.census,j):j for j in jobs}
  for f in concurrent.futures.as_completed(fs):
   try:r=f.result()
   except Exception as e:r=dict(start=fs[f][0],end=fs[f][1],complete=False,error=repr(e),creations=[])
   census.append(r);R.save(P/'CENSUS.json',census);print('CENSUS',len(census),len(r['creations']),r.get('error',''),flush=True)
 if not all(r['complete'] for r in census):raise ValueError('incomplete_creation_census')
 chosen=[]
 for r in sorted(census,key=lambda r:r['start']):
  ordinary=[c for c in r['creations'] if c['creation'].get('quote_mint') in [None,'11111111111111111111111111111111','So11111111111111111111111111111111111111112'] and not c['creation'].get('is_mayhem_mode',False) and not c['creation'].get('is_holder_reward',False)]
  chosen.extend(sorted(ordinary,key=lambda c:hashlib.sha256((fr['seed']+c['mint']).encode()).hexdigest())[:fr['per_hour']])
 R.save(P/'CREATION_SAMPLE.json',dict(chosen=chosen,selection='fixed hash within each complete hourly creation census, before curve outcomes',hours=48,total_creations=sum(len(r['creations']) for r in census)));tapes=[];audit=[]
 with concurrent.futures.ThreadPoolExecutor(4) as ex:
  fs={ex.submit(run_tape,c):c for c in chosen}
  for f in concurrent.futures.as_completed(fs):
   try:t,a=f.result()
   except Exception as e:t=None;a=dict(mint=fs[f]['mint'],error=repr(e))
   if t:tapes.append(t)
   audit.append(a)
   if len(audit)%25==0:R.save(P/'PREPARE_AUDIT.json',audit);print('CURVES',len(audit),'of',len(chosen),flush=True)
 with gzip.open(P/'TAPES.pkl.gz','wb') as f:pickle.dump(tapes,f)
 R.save(P/'PREPARE_AUDIT.json',audit);R.save(P/'COMPLETE.json',dict(selected=len(chosen),tapes=len(tapes),errors=[a for a in audit if a.get('error')],custody_gaps=[a for a in audit if a.get('custody_gap')],dates=dict(__import__('collections').Counter(t['date'] for t in tapes))));print('COMPLETE',len(tapes),len(chosen),flush=True)
if __name__=='__main__':main()
