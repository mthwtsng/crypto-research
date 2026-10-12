"""Complete pre-cutoff exits for all fixed-cohort coins; never admit later signals."""
import concurrent.futures,datetime,gzip,hashlib,json,pickle,shutil
import collect as N

def main():
 ids=set(json.loads((N.HERE/'COHORT_IDS.json').read_text()));ts=pickle.load(gzip.open(N.HERE/'TAPES.pkl.gz','rb'));by={t['mint']:t for t in ts};ends={m:by[m]['end_time']for m in ids};backup=N.HERE/'before_exit_followup';backup.mkdir(exist_ok=True)
 for name in ['TAPES.pkl.gz','RESULTS.json','TRADES.jsonl.gz','PORTFOLIOS.json','COIN_MANIFEST.json','COINS.csv','AUTHENTICATION.json','EVALUATION_FREEZE.json']:
  if(N.HERE/name).exists():shutil.copy(N.HERE/name,backup/name)
 (N.HERE/'FOLLOWUP_FREEZE.json').write_text(json.dumps(dict(time=datetime.datetime.now(datetime.timezone.utc).isoformat(),decision_ends=ends,followup_seconds=60,policy='Alloriginal40cohortcoins,notselectedbyprofit; extendexithistory60seconds,admitnosignalsafteroriginalper-mintcutoff; windowandcohortstayfixed.'),indent=2))
 def one(m):
  fp=N.HERE/'custody_second/custody_extended'/(m+'.json.gz')
  if not fp.exists():fp=N.HERE/'custody_repair/custody_extended'/(m+'.json.gz')
  if not fp.exists():fp=N.HERE/'extended'/(m+'.json.gz')
  d=json.load(gzip.open(fp,'rt'));old=ends[m];token=None;txs={t['transaction']['signatures'][0]:t for t in d['transactions']}
  for page in range(20):
   cfg=dict(transactionDetails='full',encoding='jsonParsed',maxSupportedTransactionVersion=1,sortOrder='asc',limit=1000,commitment='finalized',filters=dict(status='succeeded',blockTime=dict(gte=old,lte=old+60)))
   if token:cfg['paginationToken']=token
   r=N.rpc('getTransactionsForAddress',[by[m]['curve'],cfg])
   for z in r['data']:txs[z['transaction']['signatures'][0]]=z
   nxt=r.get('paginationToken')
   if not nxt:break
   if nxt==token:raise ValueError('pagination cycle')
   token=nxt
  else:raise ValueError('followup cap')
  d['transactions']=list(txs.values());d['requested_end_time']=old+60;N.save(N.HERE/'followup_extended'/(m+'.json.gz'),d);t,a=N.P.make(d)
  if t:t['creation_metadata']=by[m]['creation_metadata'];t['source']=by[m]['source'];t['decision_end_time']=old
  return t,a
 out=[]
 with concurrent.futures.ThreadPoolExecutor(4)as ex:
  fs={ex.submit(one,m):m for m in ids}
  for k,f in enumerate(concurrent.futures.as_completed(fs),1):
   try:t,a=f.result()
   except Exception as e:t=None;a=dict(mint=fs[f],error=str(e))
   if t:by[t['mint']]=t
   else:by[fs[f]]['decision_end_time']=ends[fs[f]]
   out.append(a)
   if k%10==0:print('followup',k,'/40',flush=True)
 with gzip.open(N.HERE/'TAPES.pkl.gz','wb')as f:pickle.dump(list(by.values()),f)
 (N.HERE/'FOLLOWUP_AUDIT.json').write_text(json.dumps(out,indent=2));print('followup done',len(out),'errors',sum('error'in a for a in out),flush=True)
if __name__=='__main__':main()
