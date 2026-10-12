"""Custody repair, causal signal detection and authenticated pool preparation.

Retain every creation-selected coin. Repair pre-completion gaps before applying
holder-based entry rules. Eligible continuations are collected irrespective of
subsequent performance.
"""
import collections,concurrent.futures,gzip,json,pathlib,pickle,sys
P=pathlib.Path(__file__).resolve().parent/'fresh_oct05_oct06';ROOT=P.parents[2];OLD=ROOT/'research/wallet_curve_entry_discovery_20261007';BASE=ROOT/'research/core_plan_audit_20261007'
sys.path.insert(0,str(BASE));import signals as S,engine as E
sys.path.insert(0,str(OLD));import repair_curve_custody as H,collect_continuations as C,bind_curve_limits as B,merge_curve_receipts as J
H.P=P;H.H.HERE=P/'custody';H.H.HERE.mkdir(exist_ok=True);C.P=P;B.P=P
def save(f,x):H.C.save(f,x)
def metadata(t):return dict(mint=t['mint'],curve=t['curve'],through_time=t['end_time'],from_creation=True)

def repair_selection():
 tapes=pickle.load(gzip.open(P/'TAPES.pkl.gz','rb'));aud=[];errors=[];jobs=[]
 for t in tapes:
  if H.gap(t):
   d=json.load(gzip.open(P/'raw_curves'/(t['mint']+'.json.gz'),'rt'));f=P/'gap_continuations'/(t['mint']+'.json.gz');save(f,dict(audit=metadata(t),transactions=d['transactions']));jobs.append(f)
 with concurrent.futures.ThreadPoolExecutor(2) as ex:
  fs={ex.submit(H.run,f):f for f in jobs}
  for f in concurrent.futures.as_completed(fs):
   try:a=f.result();aud.append(a);print('INITIAL_CUSTODY',len(aud),len(jobs),a['status'],a.get('remaining_gap'),flush=True)
   except Exception as e:errors.append(dict(file=fs[f].name,error=repr(e)));print('ERROR',errors[-1],flush=True)
 updated=[];signals=[];signal_errors=[]
 for t in tapes:
  decision_end=t['end_time']
  f=P/'repaired_curve_tapes'/(t['mint']+'.json.gz')
  if f.exists():t=json.load(gzip.open(f,'rt'))
  # Continuation receipts repair custody and cover exits; they cannot extend
  # the frozen 1,800-second window in which entry signals are searched.
  t=dict(t,groups=[g for g in t['groups'] if g['block_time']<=decision_end],end_time=decision_end)
  updated.append(t);ss,ee=S.detect(t);signals+=ss;signal_errors.extend(dict(mint=t['mint'],**e) for e in ee)
 with gzip.open(P/'REPAIRED_SELECTION.pkl.gz','wb') as f:pickle.dump(updated,f)
 (P/'SIGNALS.json').write_text(json.dumps(signals,indent=2)+'\n');save(P/'SIGNAL_AUDIT.json',dict(coins=len(tapes),mints=len({s['mint'] for s in signals}),signals=dict(collections.Counter(s['rule'] for s in signals)),errors=signal_errors,repair_errors=errors,repair_audits=aud));return updated,signals

def continuations(signals):
 jobs={};aud=[];errors=[]
 for s in signals:
  j=jobs.setdefault(s['mint'],dict(mint=s['mint'],curve=s['curve'],latest_signal_time=s['time']));j['latest_signal_time']=max(j['latest_signal_time'],s['time'])
 with concurrent.futures.ThreadPoolExecutor(2) as ex:
  fs={ex.submit(C.run,j):j for j in jobs.values()}
  for f in concurrent.futures.as_completed(fs):
   try:a=f.result();aud.append(a);print('CONTINUATION',len(aud),len(jobs),a['mint'][:8],a['status'],flush=True)
   except Exception as e:errors.append(dict(mint=fs[f]['mint'],error=repr(e)));print('ERROR',errors[-1],flush=True)
 save(P/'CONTINUATION_COMPLETE.json',dict(total=len(jobs),audits=aud,errors=errors))
 if errors:raise ValueError('eligible_continuation_errors')
 for j in jobs.values():
  old=P/'repaired_curve_tapes'/(j['mint']+'.json.gz')
  through=json.load(gzip.open(P/'continuations'/(j['mint']+'.json.gz'),'rt'))['audit']['through_time']
  if old.exists() and json.load(gzip.open(old,'rt'))['end_time']<through:
   (P/'custody_audits'/(j['mint']+'.json')).unlink(missing_ok=True);(P/'custody/custody_extended'/(j['mint']+'.json.gz')).unlink(missing_ok=True)
  a=H.run(P/'continuations'/(j['mint']+'.json.gz'));print('ELIGIBLE_CUSTODY',j['mint'][:8],a['status'],a.get('remaining_gap'),flush=True)
 (P/'bound_curve_tapes').mkdir(exist_ok=True);B.main()
 # Bind only eligible source paths into token-account custody, retaining actual
 # transfers between accounts owned by the same wallet.
 for j in jobs.values():
  f=P/'bound_curve_tapes'/(j['mint']+'.json.gz');t=json.load(gzip.open(f,'rt'));source=P/'custody/custody_extended'/f.name
  if not source.exists():source=P/'custody_inputs'/f.name
  by={r['transaction']['signatures'][0]:r for r in json.load(gzip.open(source,'rt'))['transactions']};t['groups']=[J.account_group(g,by[g['signature']],t['mint']) for g in t['groups']];t['inventory_key']='token_account';save(P/'merged_account_tapes'/f.name,t)

def pools(finalize_only=False):
 import repair_amm_custody as Q,normalize_amm_virtual as N,verify_amm_counterparty as V,audit_migration_custody as D,verify_curve_replay as CV
 Q.P=P;N.P=P;V.P=P;D.P=P;CV.P=P
 # The receipt parser is explicitly loaded by Q, avoiding ambiguous prepare
 # module names shared by the curve and AMM historical workflows.
 for f in ([] if finalize_only else sorted((P/'continuation_pools').glob('*.gz'))):
  out=P/'amm_tapes'/f.name
  if out.exists():continue
  t,a=Q.B.prepare(f);t['signals']=[];save(out,t);print('AMM_PREPARE',t['mint'][:8],a['good'],len(a['errors']),flush=True)
 sys.path.insert(0,'/tmp/amm_research_deps')
 if not finalize_only:Q.main();N.main();V.main()
 D.main();CV.main()
 dest=P/'execution';dest.mkdir(exist_ok=True)
 latest={}
 for s in json.loads((P/'SIGNALS.json').read_text()):latest[s['mint']]=max(latest.get(s['mint'],0),s['time'])
 for folder,source in [('bound_curve_tapes',P/'bound_curve_tapes'),('amm_tapes',P/'normalized_amm_tapes')]:
  target=dest/folder;target.mkdir(exist_ok=True)
  for f in source.glob('*.gz'):
   if (target/f.name).exists():continue
   if folder=='amm_tapes':
    t=json.load(gzip.open(f,'rt'));cut=latest[t['mint']]+660;t['groups']=[g for i,g in enumerate(t['groups']) if i==0 or g['time']<=cut];save(target/f.name,t)
   else:(target/f.name).symlink_to(f.resolve())
 (dest/'SIGNALS.json').write_text((P/'SIGNALS.json').read_text());save(P/'PIPELINE_COMPLETE.json',dict(bound_tapes=len(list((P/'bound_curve_tapes').glob('*.gz'))),pools=len(list((P/'normalized_amm_tapes').glob('*.gz')))))

if __name__=='__main__':
 if '--finalize' in sys.argv:pools(True)
 else:tapes,signals=repair_selection();continuations(signals);pools()
