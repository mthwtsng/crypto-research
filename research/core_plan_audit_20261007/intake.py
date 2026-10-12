"""Recover all eligible plan signals, reusing authenticated research receipts."""
import concurrent.futures,gzip,json,pathlib,pickle,sys
P=pathlib.Path(__file__).resolve().parent;ROOT=P.parents[1];OLD=ROOT/'research/wallet_curve_entry_discovery_20261007'
sys.path.insert(0,str(OLD));import collect_continuations as C

def link(source,target):
 target.parent.mkdir(parents=True,exist_ok=True)
 if not target.exists():target.symlink_to(source.resolve())

def main():
 tapes=pickle.load(gzip.open(ROOT/'research/day_general_20261004/TAPES.pkl.gz','rb'));by={t['mint']:t for t in tapes};ss=json.loads((P/'SIGNALS.json').read_text());jobs={};new=[];audits=[]
 for s in ss:
  j=jobs.setdefault(s['mint'],dict(mint=s['mint'],curve=s['curve'],latest_signal_time=s['time'],rules=[]));j['latest_signal_time']=max(j['latest_signal_time'],s['time']);j['rules'].append(s['rule'])
 for j in jobs.values():
  m=j['mint'];f=OLD/'bound_curve_tapes'/(m+'.json.gz')
  if f.exists():
   t=json.load(gzip.open(f,'rt'))
   if t['end_time']>=j['latest_signal_time']+600:
    link(f,P/'bound_curve_tapes'/f.name);link(OLD/'continuations'/f.name,P/'continuations'/f.name);link(OLD/'failed_curve_intents'/f.name,P/'failed_curve_intents'/f.name);audits.append(dict(mint=m,status='reused'));continue
  new.append(j)
 C.P=P
 with concurrent.futures.ThreadPoolExecutor(2) as ex:
  futures={ex.submit(C.run,j):j for j in new}
  for f in concurrent.futures.as_completed(futures):
   j=futures[f]
   try:a=f.result();audits.append(dict(mint=j['mint'],status='collected'));print('COLLECTED',j['mint'][:8],flush=True)
   except Exception as e:audits.append(dict(mint=j['mint'],status='error',error=str(e)));print('ERROR',audits[-1],flush=True)
 (P/'INTAKE_AUDIT.json').write_text(json.dumps(dict(total=len(jobs),audits=audits),indent=2)+'\n')
 # Reuse the receipt/custody repair and original-instruction binding workflows.
 import repair_curve_custody as H
 H.P=P;H.H.HERE=P/'custody';H.H.HERE.mkdir(exist_ok=True)
 for j in new:
  f=P/'continuations'/(j['mint']+'.json.gz')
  if f.exists():a=H.run(f);print('CUSTODY',j['mint'][:8],a.get('status'),flush=True)
 import bind_curve_limits as B
 B.P=P;B.main()
 # Binding touches only locally repaired files; reused symlink tapes stay intact.
 # Authentic pool continuations already recovered in the previous study.
 for f in (OLD/'normalized_amm_tapes').glob('*.gz'):link(f,P/'amm_tapes'/f.name)
 (P/'INTAKE_COMPLETE.json').write_text(json.dumps(dict(mints=len(jobs),bound_tapes=len(list((P/'bound_curve_tapes').glob('*.gz')))),indent=2)+'\n')
if __name__=='__main__':main()
