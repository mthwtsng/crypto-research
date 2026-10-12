"""Collect and prepare an additional creation-selected cohort with the existing pipeline.

Usage: expand_cohort.py NAME START_EPOCH HOURS PER_HOUR SEED [EXCLUDE_SAMPLE_JSON ...]
Selection: fixed hash order inside each complete hourly creation census, before any
curve outcome, excluding mints already sampled by earlier cohorts.
"""
import collections,concurrent.futures,datetime,gzip,hashlib,json,pathlib,pickle,sys,traceback
HERE=pathlib.Path(__file__).resolve().parent;P0=HERE.parent;sys.path.insert(0,str(P0))
# fresh_pipeline rebinds collect.P, so collection and preparation run in separate processes.
STAGE='prepare' if '--prepare' in sys.argv else 'collect'
if '--prepare' in sys.argv:sys.argv.remove('--prepare')
if STAGE=='collect':import fresh_collect as FC
else:import fresh_pipeline as FP,account_repair as AR

def bind(P):
 P.mkdir(parents=True,exist_ok=True)
 if STAGE=='collect':FC.P=P;FC.G.HERE=P;return
 for m in (FP,AR):m.P=P
 FP.H.P=P;FP.H.H.HERE=P/'custody';FP.H.H.HERE.mkdir(exist_ok=True);FP.C.P=P;FP.B.P=P
 AR.H.P=P;AR.H.H.HERE=P/'custody';AR.B.P=P

def collect(P,fr,excluded):
 jobs=[(fr['start']+i*3600,fr['start']+(i+1)*3600) for i in range(fr['hours'])];census=[]
 with concurrent.futures.ThreadPoolExecutor(4) as ex:
  fs={ex.submit(FC.G.census,j):j for j in jobs}
  for f in concurrent.futures.as_completed(fs):
   try:r=f.result()
   except Exception as e:r=dict(start=fs[f][0],end=fs[f][1],complete=False,error=repr(e),creations=[])
   census.append(r);print('CENSUS',len(census),len(r['creations']),r.get('error',''),flush=True)
 FC.R.save(P/'CENSUS.json',census)
 if not all(r['complete'] for r in census):raise ValueError('incomplete_creation_census')
 chosen=[]
 for r in sorted(census,key=lambda r:r['start']):
  ordinary=[c for c in r['creations'] if c['creation'].get('quote_mint') in [None,'11111111111111111111111111111111','So11111111111111111111111111111111111111112'] and not c['creation'].get('is_mayhem_mode',False) and not c['creation'].get('is_holder_reward',False) and c['mint'] not in excluded]
  chosen.extend(sorted(ordinary,key=lambda c:hashlib.sha256((fr['seed']+c['mint']).encode()).hexdigest())[:fr['per_hour']])
 FC.R.save(P/'CREATION_SAMPLE.json',dict(chosen=chosen,selection=fr['selection'],hours=fr['hours'],total_creations=sum(len(r['creations']) for r in census),excluded=len(excluded)))
 tapes=[];audit=[]
 with concurrent.futures.ThreadPoolExecutor(6) as ex:
  fs={ex.submit(FC.run_tape,c):c for c in chosen}
  for f in concurrent.futures.as_completed(fs):
   try:t,a=f.result()
   except Exception as e:t=None;a=dict(mint=fs[f]['mint'],error=repr(e))
   if t:tapes.append(t)
   audit.append(a)
   if len(audit)%200==0:print('CURVES',len(audit),'of',len(chosen),flush=True)
 with gzip.open(P/'TAPES.pkl.gz','wb') as f:pickle.dump(tapes,f)
 FC.R.save(P/'PREPARE_AUDIT.json',audit);FC.R.save(P/'COMPLETE.json',dict(selected=len(chosen),tapes=len(tapes),errors=[a for a in audit if a.get('error')]))
 print('COLLECT_DONE',len(tapes),len(chosen),flush=True)

def main():
 name,start,hours,per_hour,seed=sys.argv[1],int(sys.argv[2]),int(sys.argv[3]),int(sys.argv[4]),sys.argv[5]
 P=HERE/name;bind(P);excluded=set()
 for f in sys.argv[6:]:excluded|={c['mint'] for c in json.load(open(f))['chosen']}
 fr=dict(frozen_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),start=start,hours=hours,per_hour=per_hour,seed=seed,capture_seconds=1800,selection='ordinary normal-SOL creations, minimum-hash per complete hourly census stratum, excluding earlier sampled mints, before curve outcomes',rules='All five strategies frozen before collection: S1/S2/S4/S5 original lower endpoint; S3 two-buy-group entry, 12% relative stop, 8s grace, TP20%, 60s timeout',excluded_sources=sys.argv[6:])
 if not (P/'FREEZE.json').exists():(P/'FREEZE.json').write_text(json.dumps(fr,indent=2)+'\n')
 fr=json.loads((P/'FREEZE.json').read_text())
 if STAGE=='collect':
  if not (P/'TAPES.pkl.gz').exists():collect(P,fr,excluded)
  return
 if not (P/'SIGNALS.json').exists() or not (P/'CONTINUATION_COMPLETE.json').exists():
  tapes,signals=FP.repair_selection();print('SIGNALS',dict(collections.Counter(s['rule'] for s in signals)),flush=True);FP.continuations(signals)
 try:FP.pools()
 except Exception:traceback.print_exc();print('POOLS_FIRST_PASS_FAILED; running account repair',flush=True)
 AR.main();FP.pools(True);print('PIPELINE_DONE',name,flush=True)
if __name__=='__main__':main()
