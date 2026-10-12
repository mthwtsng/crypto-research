"""Outcome-independent pinned migration census and pool history collection."""
import pathlib,json,gzip,hashlib,urllib.request,time,threading,concurrent.futures,sys,datetime,re
P=pathlib.Path(__file__).resolve().parent;R=P.parent.parent
sys.path.insert(0,str(R/'research/day_general_20261004/helpers'));import decoder as D
AMM='pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA';WSOL='So11111111111111111111111111111111111111112';AUTH='39azUYFWPz3VHgKCf3VChUwbpURdCHRxjWVowf5jUJjg'
URLS=['https://solana-mainnet.g.alchemy.com/v2/8jufMAGFyazXvclfVdzH_e-TxbvZHvqG','https://rpc.shyft.to?api_key=owfc3zuSXH37YG0U'];LOCK=threading.Lock();LAST=[0]
PIDL=json.loads((R/'research/day_general_20261004/helpers/OFFICIAL_PUMP_IDL.json').read_text());MIG={bytes(i['discriminator']):i for i in PIDL['instructions'] if i['name'].startswith('migrate')}
def save(f,d):
 f.parent.mkdir(parents=True,exist_ok=True)
 if str(f).endswith('.gz'):
  tmp=f.with_suffix(f.suffix+'.partial')
  with gzip.open(tmp,'wt',compresslevel=1) as o:json.dump(d,o)
  tmp.replace(f)
 else:f.write_text(json.dumps(d,indent=2))
def rpc(method,params):
 f=P/'raw'/(hashlib.sha256(json.dumps([method,params],sort_keys=True).encode()).hexdigest()+'.json.gz')
 if f.exists():
  try:return json.load(gzip.open(f,'rt'))['result']
  except (EOFError,OSError,json.JSONDecodeError):f.replace(f.with_suffix('.truncated'))
 for k in range(8):
  try:
   with LOCK:
    time.sleep(max(0,.1-(time.monotonic()-LAST[0])));LAST[0]=time.monotonic()
   endpoint=URLS[0]
   if method!='getTransactionsForAddress' and k:
    key=re.search(r'\bsk_[A-Za-z0-9_-]+',(R/'AGENTS.md').read_text())
    safe_solami=method!='getBlock' or len(params)>1 and params[1].get('transactionDetails')=='none'
    endpoint=('https://rpc.solami.dev/sol?api_key='+key.group()) if key and k>=2 and safe_solami else URLS[k%2]
   req=urllib.request.Request(endpoint,json.dumps(dict(jsonrpc='2.0',id=1,method=method,params=params)).encode(),{'Content-Type':'application/json'})
   r=json.load(urllib.request.urlopen(req,timeout=90))
   if 'error' in r:raise ValueError(str(r['error']))
   save(f,r);return r['result']
  except Exception:
   if k==7:raise
   time.sleep(min(1+k,5))
def raw(s):
 n=0
 for c in s:n=n*58+D.ALPHABET.index(c)
 return b'\0'*(len(s)-len(s.lstrip('1')))+n.to_bytes((n.bit_length()+7)//8,'big')
def allix(t):return t['transaction']['message']['instructions']+[i for g in t['meta'].get('innerInstructions',[]) or [] for i in g['instructions']]
def migrations(t):
 out=[]
 for ix in allix(t):
  if ix.get('programId')!=D.PUMP:continue
  spec=MIG.get(raw(ix.get('data',''))[:8])
  if not spec:continue
  a=dict(zip([z['name'] for z in spec['accounts']],ix.get('accounts',[])))
  if a.get('withdraw_authority')!=AUTH:raise ValueError('authority_changed')
  if a.get('pump_amm')!=AMM:continue
  quote=a.get('quote_mint',a.get('wsol_mint'))
  out.append(dict(pool=a['pool'],mint=a.get('base_mint',a.get('mint')),quote_mint=quote,time=t['blockTime'],slot=t['slot'],index=t['transactionIndex'],signature=t['transaction']['signatures'][0],instruction=spec['name'],base_vault=a['pool_base_token_account'],quote_vault=a['pool_quote_token_account'],creator=a['user']))
 return out

def census(day):
 rows=[];token=None;receipts=0
 for page in range(200):
  cfg=dict(transactionDetails='full',encoding='jsonParsed',maxSupportedTransactionVersion=1,commitment='finalized',sortOrder='asc',limit=1000,filters=dict(status='succeeded',blockTime=dict(gte=day,lt=day+86400)))
  if token:cfg['paginationToken']=token
  r=rpc('getTransactionsForAddress',[AUTH,cfg]);receipts+=len(r['data'])
  for t in r['data']:
   if t.get('transactionIndex') is None:raise ValueError('migration_order_missing')
   rows+=migrations(t)
  nxt=r.get('paginationToken')
  if not nxt:break
  if nxt==token:raise ValueError('pagination_cycle')
  token=nxt
 else:raise ValueError('census_page_cap')
 rows=list({x['pool']:x for x in rows}.values());z=dict(day=day,complete=True,receipts=receipts,migrations=rows);save(P/'census'/(str(day)+'.json'),z);print('CENSUS',day,len(rows),'migrations',receipts,'receipts',flush=True);return z

def pool(m):
 f=P/'pools'/(m['pool']+'.json.gz')
 if f.exists():
  try:return json.load(gzip.open(f,'rt'))['coverage']
  except (EOFError,OSError,json.JSONDecodeError):f.replace(f.with_suffix('.truncated'))
 end=m['time']+21600+600;token=None;tx=[]
 for page in range(640):
  cfg=dict(transactionDetails='full',encoding='jsonParsed',maxSupportedTransactionVersion=1,commitment='finalized',sortOrder='asc',limit=250,filters=dict(status='succeeded',blockTime=dict(lte=end)))
  if token:cfg['paginationToken']=token
  r=rpc('getTransactionsForAddress',[m['pool'],cfg]);tx+=r['data'];nxt=r.get('paginationToken')
  if not nxt:break
  if nxt==token:raise ValueError('pool_pagination_cycle')
  token=nxt
 else:raise ValueError('pool_page_cap')
 tx=list({t['transaction']['signatures'][0]:t for t in tx}.values());tx.sort(key=lambda t:(t['slot'],t.get('transactionIndex',-1)))
 if any(t.get('transactionIndex') is None for t in tx):raise ValueError('pool_order_missing')
 if m['signature'] not in {t['transaction']['signatures'][0] for t in tx}:raise ValueError('pool_genesis_missing')
 z=dict(pool=m['pool'],complete=True,transactions=len(tx),through_time=end,decision_end=m['time']+21600,migration=m);save(f,dict(coverage=z,transactions=tx));print('POOL',m['pool'][:8],len(tx),flush=True);return z

def main():
 start=int(datetime.datetime(2026,10,2,tzinfo=datetime.timezone.utc).timestamp());days=[start+86400*i for i in range(3)];freeze=P/'FREEZE.json'
 if not freeze.exists():save(freeze,dict(created=datetime.datetime.now(datetime.timezone.utc).isoformat(),migration_days_UTC=['2026-10-02','2026-10-03','2026-10-04'],sample_per_day=24,hash_seed='amm_20261006_multiday_fixed_v1',decision_seconds_after_migration=21600,coverage_extra_seconds=600,universe='all recognized official Pump migration receipts indexed by withdraw authority; WSOL only; no wallet/profit/volume/peak selection',rules_source_sha256=hashlib.sha256((R/'research/amm_strategy_discovery_20261006/EXPERIMENT_SPEC.json').read_bytes()).hexdigest(),same_slot_probabilities=[.8,.85],scope='fixed72pool bounded6h age pilot over3migrationdays; not full all-AMM account or forwardconfirmation'))
 fr=json.loads(freeze.read_text());cs=[]
 with concurrent.futures.ThreadPoolExecutor(3) as ex:
  for c in ex.map(census,days):cs.append(c)
 chosen=[]
 for c in cs:
  eligible=[m for m in c['migrations'] if m['quote_mint']==WSOL]
  chosen+=sorted(eligible,key=lambda m:hashlib.sha256((fr['hash_seed']+m['pool']).encode()).hexdigest())[:fr['sample_per_day']]
 save(P/'SELECTION.json',dict(census_counts=[dict(day=c['day'],total=len(c['migrations']),normal_SOL=sum(m['quote_mint']==WSOL for m in c['migrations'])) for c in cs],chosen=chosen));print('SELECTED',len(chosen),flush=True);results=[]
 with concurrent.futures.ThreadPoolExecutor(6) as ex:
  fs={ex.submit(pool,m):m for m in chosen}
  for f in concurrent.futures.as_completed(fs):
   try:results.append(f.result())
   except Exception as e:results.append(dict(pool=fs[f]['pool'],complete=False,error=str(e)));print('POOLERROR',str(e),flush=True)
   save(P/'COLLECTION_CHECKS.json',results)
 print('COLLECT DONE',len(results),flush=True)
if __name__=='__main__':main()
