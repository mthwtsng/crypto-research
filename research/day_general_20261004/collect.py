"""Independent creation-index census; read-only RPC, no trading."""
import collections,concurrent.futures,datetime,gzip,hashlib,json,pathlib,pickle,sys,time,threading,urllib.request
HERE=pathlib.Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE/'helpers'))
MINT_AUTH='TSLvdd1pWpHVjahSpsvCXUbgwsL3JAcvokwaKt1eokM'
RATE_LOCK=threading.Lock();LAST_REQUEST=[0.]
RPC='https://solana-mainnet.g.alchemy.com/v2/8jufMAGFyazXvclfVdzH_e-TxbvZHvqG';SHYFT='https://rpc.shyft.to?api_key=owfc3zuSXH37YG0U'
def rpc(method,params):
 key=hashlib.sha256(json.dumps([method,params],sort_keys=True).encode()).hexdigest();p=HERE/'raw'/(key+'.json.gz');p.parent.mkdir(exist_ok=True)
 if p.exists():return json.load(gzip.open(p,'rt'))['result']
 for k in range(12):
  try:
   endpoint=SHYFT if k%2==0 else RPC
   with RATE_LOCK:
    time.sleep(max(0.,.6-(time.monotonic()-LAST_REQUEST[0])));LAST_REQUEST[0]=time.monotonic()
   req=urllib.request.Request(endpoint,json.dumps(dict(jsonrpc='2.0',id=1,method=method,params=params)).encode(),{'Content-Type':'application/json'});r=json.load(urllib.request.urlopen(req,timeout=35))
   if 'error'in r:raise ValueError(str(r['error']))
   with gzip.open(p,'wt')as f:json.dump(dict(method=method,params=params,result=r['result']),f)
   return r['result']
  except Exception as e:
   if any(x in str(e).lower()for x in ['skipped','-32007','-32009']):raise
   if k==11:raise
   time.sleep(min(5+2*k,20))
def save(path,data):
 path.parent.mkdir(parents=True,exist_ok=True)
 with gzip.open(path,'wt')as f:json.dump(data,f)

import prepare as P

def census(job):
 a,b=job;out={};token=None;complete=False;receipts=0
 for page in range(100):
  cfg=dict(transactionDetails='full',encoding='jsonParsed',maxSupportedTransactionVersion=1,sortOrder='asc',limit=1000,commitment='finalized',filters=dict(status='succeeded',blockTime=dict(gte=a,lt=b)))
  if token:cfg['paginationToken']=token
  r=rpc('getTransactionsForAddress',[MINT_AUTH,cfg]);receipts+=len(r['data'])
  for tx in r['data']:
   for c in P.decoder.creations(tx):
    if a<=tx['blockTime']<b:out[c['mint']]=dict(mint=c['mint'],creation=c,creation_time=tx['blockTime'],creation_slot=tx['slot'],signature=tx['transaction']['signatures'][0])
  nxt=r.get('paginationToken')
  if not nxt:complete=True;break
  if nxt==token:raise ValueError('pagination cycle')
  token=nxt
  print('census pages',a,page+1,'creations',len(out),flush=True)
 return dict(start=a,end=b,complete=complete,pages=page+1,receipts=receipts,creations=list(out.values()))
def tape(item):
 fr=json.loads((HERE/'FREEZE.json').read_text());decision_end=min(item['creation_time']+fr['capture_seconds'],fr['creation_end_utc_epoch']);end=decision_end+60;p=HERE/'extended'/(item['mint']+'.json.gz');p.parent.mkdir(exist_ok=True)
 if p.exists():d=json.load(gzip.open(p,'rt'))
 else:
  ts=[];token=None;complete=False
  for page in range(80):
   cfg=dict(transactionDetails='full',encoding='jsonParsed',maxSupportedTransactionVersion=1,sortOrder='asc',limit=1000,commitment='finalized',filters=dict(status='succeeded',blockTime=dict(lte=end)))
   if token:cfg['paginationToken']=token
   r=rpc('getTransactionsForAddress',[item['creation']['bonding_curve'],cfg]);ts+=r['data'];nxt=r.get('paginationToken')
   if not nxt:complete=True;break
   if nxt==token:raise ValueError('pagination cycle')
   token=nxt
  if not complete:raise ValueError('curve pagination cap')
  if any(t.get('transactionIndex')is None for t in ts):raise ValueError('missing transaction index')
  d=dict(mint=item['mint'],requested_end_time=end,transactions=list({t['transaction']['signatures'][0]:t for t in ts}.values()))
  with gzip.open(p,'wt')as f:json.dump(d,f)
 t,a=P.make(d)
 if t:t['source']='independent_day_mint_authority_census';t['creation_metadata']=item['creation'];t['decision_end_time']=decision_end
 return t,a

def main():
 fr=json.loads((HERE/'FREEZE.json').read_text());a,b=fr['window_start_utc_epoch'],fr['creation_end_utc_epoch'];jobs=[(a+i*3600,a+(i+1)*3600)for i in range(24)];results=[]
 with concurrent.futures.ThreadPoolExecutor(4)as ex:
  fs={ex.submit(census,j):j for j in jobs}
  for f in concurrent.futures.as_completed(fs):
   try:r=f.result()
   except Exception as e:r=dict(start=fs[f][0],end=fs[f][1],complete=False,error=str(e),creations=[])
   results.append(r);(HERE/'CENSUS.json').write_text(json.dumps(results,indent=2));print('census hour',len(results),len(r['creations']),r.get('error',''),flush=True)
 excluded=set(json.loads((HERE/'EXCLUDED_PRIOR_MINTS.json').read_text()));chosen=[];pool={};ordinary_total=0
 for r in sorted(results,key=lambda x:x['start']):
  if not r['complete']:continue
  pool.update({c['mint']:c for c in r['creations']})
  ordinary=[c for c in r['creations']if c['mint']not in excluded and c['creation'].get('quote_mint')in[None,'11111111111111111111111111111111','So11111111111111111111111111111111111111112']and not c['creation'].get('is_mayhem_mode',False)and not c['creation'].get('is_holder_reward',False)];ordinary_total+=len(ordinary)
  chosen+=sorted(ordinary,key=lambda c:hashlib.sha256((fr['seed']+c['mint']).encode()).hexdigest())[:25]
 (HERE/'CREATION_SAMPLE.json').write_text(json.dumps(dict(total_creations=len(pool),ordinary=ordinary_total,chosen=chosen,census_complete=all(r['complete']for r in results)),indent=2));print('fixed sample',len(chosen),flush=True)
 if not all(r['complete']for r in results):raise ValueError('Incomplete census; no day claim')
 out=[];aud=[]
 with concurrent.futures.ThreadPoolExecutor(6)as ex:
  fs={ex.submit(tape,c):c for c in chosen}
  for k,f in enumerate(concurrent.futures.as_completed(fs),1):
   try:t,z=f.result()
   except Exception as e:t=None;z=dict(mint=fs[f]['mint'],error=str(e))
   if t:out.append(t)
   aud.append(z)
   if k%25==0:print('curves',k,'/',len(chosen),flush=True);(HERE/'PREPARE_AUDIT.json').write_text(json.dumps(aud,indent=2))
 with gzip.open(HERE/'TAPES.pkl.gz','wb')as f:pickle.dump(out,f)
 (HERE/'PREPARE_AUDIT.json').write_text(json.dumps(aud,indent=2));(HERE/'PREFIX_PREPARE_AUDIT.json').write_text(json.dumps(aud,indent=2))
 print('DAY COLLECTED',len(out),flush=True)
if __name__=='__main__':main()
