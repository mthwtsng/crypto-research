"""Read-only multi-provider RPC with durable cache and explicit failure telemetry."""
import concurrent.futures,gzip,hashlib,json,pathlib,re,threading,time,urllib.request
ROOT=pathlib.Path(__file__).resolve().parents[2];OUT=pathlib.Path(__file__).resolve().parent
text=(ROOT/'AGENTS.md').read_text()
PROVIDERS={'alchemy':re.search(r'https://solana-mainnet\.g\.alchemy\.com/v2/[A-Za-z0-9_-]+',text).group(),'shyft':re.search(r'https://rpc\.shyft\.to\?api_key=[A-Za-z0-9_-]+',text).group(),'solami':'https://rpc.solami.dev/sol?api_key='+re.search(r'\bsk_[A-Za-z0-9_-]+',text).group()}
LOCK=threading.Lock();NEXT={p:0 for p in PROVIDERS};COUNTS={};DISABLED=set()
def save(path,value):
 path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+'.partial')
 if path.suffix=='.gz':
  with gzip.open(tmp,'wt',compresslevel=1) as f:json.dump(value,f)
 else:tmp.write_text(json.dumps(value,indent=2)+'\n')
 tmp.replace(path)
def request(provider,method,params):
 with LOCK:
  delay=max(0,NEXT[provider]-time.monotonic());NEXT[provider]=time.monotonic()+delay+.20
 if delay:time.sleep(delay)
 req=urllib.request.Request(PROVIDERS[provider],json.dumps(dict(jsonrpc='2.0',id=1,method=method,params=params)).encode(),{'Content-Type':'application/json'})
 started=time.monotonic()
 try:
  r=json.load(urllib.request.urlopen(req,timeout=35))
  if 'error' in r:raise RuntimeError(json.dumps(r['error']))
  if 'result' not in r:raise RuntimeError('missing_result')
  status='ok';return r['result']
 except Exception as e:status=str(e)[:240];raise
 finally:
  with LOCK:
   key=(provider,method,'ok' if status=='ok' else 'error');COUNTS[key]=COUNTS.get(key,0)+1
   with (OUT/'RPC_EVENTS.jsonl').open('a') as f:f.write(json.dumps(dict(provider=provider,method=method,status=status,elapsed=time.monotonic()-started))+'\n')
def rpc(method,params):
 cache=OUT/'rpc'/(hashlib.sha256(json.dumps([method,params],sort_keys=True).encode()).hexdigest()+'.json.gz')
 if cache.exists():return json.load(gzip.open(cache,'rt'))['result']
 failures=[]
 # Enhanced historical address API and historical getBlock first use established Alchemy route.
 names=['alchemy','shyft','solami'] if method in ['getTransactionsForAddress','getBlock'] else ['shyft','alchemy','solami']
 for attempt in range(3):
  for name in names:
   if (name,method) in DISABLED:continue
   try:
    result=request(name,method,params);save(cache,dict(provider=name,method=method,params=params,result=result));return result
   except Exception as e:
    error=str(e);failures.append(dict(provider=name,error=error[:240]))
    if '-32601' in error or '401' in error or '403' in error or '404' in error:DISABLED.add((name,method))
  time.sleep(attempt+1)
 raise RuntimeError(dict(method=method,failures=failures))
def health():
 jobs=[(name,'getSlot',[]) for name in PROVIDERS]+[(name,'getTransactionsForAddress',['TSLvdd1pWpHVjahSpsvCXUbgwsL3JAcvokwaKt1eokM',dict(transactionDetails='full',encoding='jsonParsed',maxSupportedTransactionVersion=1,sortOrder='asc',limit=1,commitment='finalized',filters=dict(status='succeeded',blockTime=dict(gte=1755475200,lt=1755478800)))]) for name in PROVIDERS]
 results=[]
 def test(job):
  name,method,params=job
  try:r=request(*job);return dict(provider=name,method=method,ok=True,value=r if method=='getSlot' else dict(rows=len(r.get('data',[])),token=bool(r.get('paginationToken'))))
  except Exception as e:return dict(provider=name,method=method,ok=False,error=str(e)[:240])
 with concurrent.futures.ThreadPoolExecutor(6) as ex:results=list(ex.map(test,jobs))
 save(OUT/'RPC_HEALTH.json',results);print(json.dumps(results,indent=2),flush=True)
if __name__=='__main__':health()
