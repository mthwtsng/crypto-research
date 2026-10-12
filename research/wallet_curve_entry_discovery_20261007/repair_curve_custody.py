"""Recover missing transfers for all pre-completion source gaps; retain migration separately."""
import concurrent.futures,gzip,importlib.util,json,pathlib,sys
P=pathlib.Path(__file__).resolve().parent;R=P.parents[1]
sys.path.insert(0,str(R/'research/day_general_20261004/helpers'));sys.path.insert(0,str(R/'research/day_general_20261004'))
import repair_helpers as H,prepare as B
sys.path.insert(0,str(R/'research/automated_wallet_expansion_20261006'));import collect_wallets as C
import hashlib
H.HERE=P/'custody';H.HERE.mkdir(exist_ok=True)
def rpc(method,params):
 key=hashlib.sha256(json.dumps([method,params],sort_keys=True).encode()).hexdigest()
 return C.rpc(method,params,P/'custody_rpc'/(key+'.json.gz'))
H.rpc=rpc;H.save=C.save
oldgap=H.gap
def curve_only(t):
 gs=t['groups'];end=next((i+1 for i,g in enumerate(gs) if g['state']['rtokens_raw']==0),len(gs))
 return dict(t,groups=gs[:end])
def gap(t):return oldgap(curve_only(t))
H.gap=gap

def run(f):
 mint=f.name.split('.')[0];done=P/'custody_audits'/(mint+'.json')
 if done.exists():return json.loads(done.read_text())
 x=json.load(gzip.open(f,'rt'));d=dict(mint=mint,transactions=x['transactions'],requested_end_time=x['audit']['through_time']);raw=P/'custody_inputs'/f.name;C.save(raw,d)
 t,a=B.make(d);initial=gap(t) if t else None
 result=H.one(raw) if initial else dict(mint=mint,passes=[],status='supported')
 repaired=H.HERE/'custody_extended'/f.name
 if repaired.exists():d=json.load(gzip.open(repaired,'rt'))
 t,a=B.make(d)
 if t:
  t=curve_only(t);bad=gap(t);result['remaining_gap']=dict(signature=bad[0]['signature'],owner=bad[1]) if bad else None
  result['source_receipts']=len(d['transactions']);result['curve_groups']=len(t['groups']);C.save(P/'repaired_curve_tapes'/f.name,t)
 result['initial_precompletion_gap']=bool(initial);C.save(done,result);return result
if __name__=='__main__':
 files=sorted((P/'continuations').glob('*.json.gz'));audits=[];errors=[]
 with concurrent.futures.ThreadPoolExecutor(2) as ex:
  fs={ex.submit(run,f):f for f in files}
  for f in concurrent.futures.as_completed(fs):
   try:audits.append(f.result());print('CUSTODY',audits[-1]['mint'][:8],audits[-1]['status'],len(audits[-1]['passes']),flush=True)
   except Exception as e:errors.append(dict(file=fs[f].name,error=str(e)));print('ERROR',errors[-1],flush=True)
   C.save(P/'CURVE_CUSTODY_PROGRESS.json',dict(total=len(files),audits=audits,errors=errors))
 C.save(P/'CURVE_CUSTODY_COMPLETE.json',dict(total=len(files),audits=audits,errors=errors));print('CUSTODY_COMPLETE',len(audits),len(errors),flush=True)
