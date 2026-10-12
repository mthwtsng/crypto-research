"""Repair every source custody gap without consulting modeled trade outcomes."""
import collections,concurrent.futures,gzip,json,pickle,sys
import collect as N
import repair_helpers as R
R.HERE=N.HERE/'custody_repair';R.HERE.mkdir(exist_ok=True);R.rpc=N.rpc;R.save=N.save

def main():
 audits=json.loads((N.HERE/'PREFIX_PREPARE_AUDIT.json').read_text());wanted=[a['mint']for a in audits if a.get('custody_gap')and a.get('normal')];prior=json.loads((N.HERE/'PREFETCH_CUSTODY.json').read_text())if(N.HERE/'PREFETCH_CUSTODY.json').exists()else[];out=[z for z in prior if z['mint']in wanted and 'error'not in z];done={z['mint']for z in out};print('CUSTODY REPAIR',len(wanted),flush=True)
 # Preserve the frozen raw preparation before any repaired counterparties.
 src=N.HERE/'TAPES.pkl.gz';(N.HERE/'TAPES_BEFORE_CUSTODY.pkl.gz').write_bytes(src.read_bytes())
 with concurrent.futures.ThreadPoolExecutor(3)as ex:
  fs={ex.submit(R.one,N.HERE/'extended'/(m+'.json.gz')):m for m in wanted if m not in done}
  for k,f in enumerate(concurrent.futures.as_completed(fs),1):
   try:a=f.result()
   except Exception as e:a=dict(mint=fs[f],error=str(e))
   out.append(a)
   if k%10==0:print('custody',k,'/',len(wanted),flush=True)
 ts=pickle.load(gzip.open(src,'rb'));by={t['mint']:t for t in ts};newaud=[]
 for a in out:
  fp=R.HERE/'custody_extended'/(a['mint']+'.json.gz')
  if fp.exists():
   t,z=N.P.make(json.load(gzip.open(fp,'rt')))
   if t:
    t['creation_metadata']=by[t['mint']]['creation_metadata'];t['source']=by[t['mint']]['source'];t['decision_end_time']=by[t['mint']]['decision_end_time'];by[t['mint']]=t;newaud.append(z)
 with gzip.open(src,'wb')as f:pickle.dump(list(by.values()),f)
 (N.HERE/'CUSTODY_REPAIR.json').write_text(json.dumps(dict(initial_gaps=len(wanted),results=out,reprepared=newaud),indent=2));print('CUSTODY DONE',dict(collections.Counter(a.get('status','error')for a in out)),flush=True)
if __name__=='__main__':main()
