"""Authenticate opening state and each actual subsequent swap, without own trades."""
import gzip,json,pathlib,sys,time
P=pathlib.Path(__file__).resolve().parent;R=P.parents[1]
sys.path.insert(0,str(R/'research/amm_multiday_20261006'));import prepare as A
sys.path.insert(0,str(R/'research/day_general_20261004'));import prepare as unused
# curve preparation loaded explicitly because module names are shared across historical studies.
import importlib.util
s=importlib.util.spec_from_file_location('curve_prepare',R/'research/day_general_20261004/prepare.py');B=importlib.util.module_from_spec(s);s.loader.exec_module(B)
def save(f,a):
 f.parent.mkdir(parents=True,exist_ok=True)
 if f.suffix=='.gz':
  with gzip.open(f,'wt',compresslevel=1) as out:json.dump(a,out)
 else:f.write_text(json.dumps(a,indent=2)+'\n')
def main():
 audits=json.loads((P/'AMM_PREPARE_AUDITS.json').read_text()) if (P/'AMM_PREPARE_AUDITS.json').exists() else []
 curve_audits=json.loads((P/'CURVE_PREPARE_AUDITS.json').read_text()) if (P/'CURVE_PREPARE_AUDITS.json').exists() else []
 done={a['pool']+'.json.gz' for a in audits if (P/'amm_tapes'/(a['pool']+'.json.gz')).exists()}
 curve_done={a['mint']+'.json.gz' for a in curve_audits if (P/'curve_tapes'/(a['mint']+'.json.gz')).exists()}
 while True:
  for f in sorted((P/'continuation_pools').glob('*.json.gz')):
   if f.name in done:continue
   t,a=A.prepare(f);t['signals']=[];save(P/'amm_tapes'/f.name,t);audits.append(a);done.add(f.name);save(P/'AMM_PREPARE_AUDITS.json',audits);print('AMM_PARITY',a['pool'][:8],a['good'],len(a['errors']),flush=True)
  for f in sorted((P/'continuations').glob('*.json.gz')):
   if f.name in curve_done:continue
   x=json.load(gzip.open(f,'rt'));audit=x['audit'];t,a=B.make(dict(mint=audit['mint'],transactions=x['transactions'],requested_end_time=audit['through_time']))
   if t:save(P/'curve_tapes'/f.name,t)
   curve_done.add(f.name);curve_audits.append(a);save(P/'CURVE_PREPARE_AUDITS.json',curve_audits)
  if (P/'CONTINUATION_COMPLETE.json').exists():
   curve_files={f.name for f in (P/'continuations').glob('*.json.gz')}
   pool_files={f.name for f in (P/'continuation_pools').glob('*.json.gz')}
   if curve_files<=curve_done and pool_files<=done:break
  time.sleep(3)
 save(P/'PREPARATION_COMPLETE.json',dict(curve_tapes=len(curve_done),amm_tapes=len(done),amm_audits=audits,curve_audits=curve_audits));print('PREPARED',len(curve_done),len(done),flush=True)
if __name__=='__main__':main()
