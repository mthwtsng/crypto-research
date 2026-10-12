"""Extend capped recovery for all selected coins with gaps, not selected PnL cases."""
import collections,concurrent.futures,datetime,gzip,inspect,json,pickle,shutil
import collect as N
import screen as S
import repair_source as F
R=F.R

def main():
 cs=json.loads((N.HERE/'COIN_MANIFEST.json').read_text());ids=[c['mint']for c in cs];ts=pickle.load(gzip.open(N.HERE/'TAPES.pkl.gz','rb'));by={t['mint']:t for t in ts};wanted=[m for m in ids if R.gap(by[m])]
 (N.HERE/'COHORT_IDS.json').write_text(json.dumps(ids,indent=2));save=N.HERE/'initial_supported';save.mkdir(exist_ok=True)
 for name in ['TAPES.pkl.gz','RESULTS.json','TRADES.jsonl.gz','PORTFOLIOS.json','COIN_MANIFEST.json','COINS.csv','AUTHENTICATION.json','EVALUATION_FREEZE.json','SCREENING_AUDIT.json','SENSITIVITY.json','SENSITIVITY_TRADES.jsonl.gz','EXIT_TRADEOFFS.json']:
  p=N.HERE/name
  if p.exists():shutil.copy(p,save/name)
 (N.HERE/'CUSTODY_EXTENSION_FREEZE.json').write_text(json.dumps(dict(time=datetime.datetime.now(datetime.timezone.utc).isoformat(),mints=wanted,rule='All original40sampledcoinswithanyunresolvedcustodyprefix;30morepasses,notoutcome-selected. Mintcohortidentitiesfixed;supersedeinitialpartialresults,notnewholdout.',earlier_issue='Initial5-passcapreachedwhileaddingearliertransfers;gapwasrecoverable,notproofunknownpositionloss.'),indent=2));print('EXTEND CUSTODY',len(wanted),flush=True)
 ns=dict(R.__dict__);ns['HERE']=N.HERE/'custody_second';ns['HERE'].mkdir(exist_ok=True);exec(inspect.getsource(R.one).replace('range(5)','range(30)'),ns);one=ns['one'];out=[]
 with concurrent.futures.ThreadPoolExecutor(3)as ex:
  fs={}
  for m in wanted:
   patched=F.R.HERE/'custody_extended'/(m+'.json.gz');fp=patched if patched.exists()else N.HERE/'extended'/(m+'.json.gz');fs[ex.submit(one,fp)]=m
  for f in concurrent.futures.as_completed(fs):
   try:a=f.result()
   except Exception as e:a=dict(mint=fs[f],error=str(e))
   out.append(a);print('custody extension',a['mint'],a.get('status'),len(a.get('passes',[])),flush=True)
 for a in out:
  fp=ns['HERE']/'custody_extended'/(a['mint']+'.json.gz')
  if fp.exists():
   t,z=N.P.make(json.load(gzip.open(fp,'rt')))
   if t:t['creation_metadata']=by[t['mint']]['creation_metadata'];t['source']=by[t['mint']]['source'];by[t['mint']]=t
 with gzip.open(N.HERE/'TAPES.pkl.gz','wb')as f:pickle.dump(list(by.values()),f)
 (N.HERE/'CUSTODY_EXTENSION.json').write_text(json.dumps(out,indent=2));print('extended done',dict(collections.Counter(a.get('status','error')for a in out)),flush=True)
if __name__=='__main__':main()
