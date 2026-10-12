"""Frozen later-sample baseline/exit-only/combined transfer and seed checks."""
import collections,concurrent.futures,gzip,json,pathlib,pickle,sys
P=pathlib.Path(__file__).resolve().parent;FRESH=P/'fresh_oct05_oct06';sys.path.insert(0,str(P));import variants as V,entry_only as N
E,F=V.E,V.F

def main():
 E.P=FRESH/'execution';E.OLD=FRESH;E.O.C.P=E.P
 signals=json.loads((E.P/'SIGNALS.json').read_text());latest={}
 for s in signals:latest[s['mint']]=max(latest.get(s['mint'],0),s['time'])
 # Older live intake processes may have written symlinks before this trim was
 # added. Retain full parity-audited sources; cap execution memory only beyond
 # every requested 600-second horizon plus sixty seconds of landing coverage.
 for f in (E.P/'amm_tapes').glob('*.gz'):
  if not f.is_symlink():continue
  t=json.load(gzip.open(f,'rt'));t['groups']=[g for i,g in enumerate(t['groups']) if i==0 or g['time']<=latest[t['mint']]+660];f.unlink()
  with gzip.open(f,'wt',compresslevel=1) as out:json.dump(t,out)
 tapes,signals=E.load();raw={t['mint']:t for t in pickle.load(gzip.open(FRESH/'REPAIRED_SELECTION.pkl.gz','rb'))};selections={v:V.selected(signals,raw,v) for v in ['baseline','joint_keep_targets_dead10']};jobs=[];rows=[];errors=[]
 for variant in ['baseline','ath_only','joint_keep_targets_dead10','joint_confirmed_half10']:
  ss=selections['baseline' if variant=='ath_only' else 'joint_keep_targets_dead10' if variant=='joint_confirmed_half10' else variant];cfg={} if variant=='baseline' else dict(s4_timeout=20,s4_stop=.15)
  if variant=='joint_confirmed_half10':cfg['s3_half_target']=.10
  for sc,fee in [(s,1505000) for s in ['fast','central80','central85','slow','stress']]+[('central85',2916000)]:
   for seed in ([0,1,2] if sc in ['central80','central85'] and fee==1505000 else [0]):
    for s in ss:
     for ticket in [.5,.25]:jobs.append((variant,tapes[s['mint']],s,sc,fee,ticket,dict(cfg,_placement_seed=seed),seed))
 def execute(j):
  v,t,s,sc,fee,ticket,cfg,seed=j;return dict(E.simulate(t,s,sc,'lower',ticket,fee,cfg),variant=v,placement_seed=seed)
 with concurrent.futures.ThreadPoolExecutor(4) as ex:
  fs={ex.submit(execute,j):j for j in jobs}
  for f in concurrent.futures.as_completed(fs):
   try:rows.append(f.result())
   except Exception as e:errors.append(dict(variant=fs[f][0],signal=fs[f][2],error=repr(e)))
   if (len(rows)+len(errors))%100==0:print('TRANSFER',len(rows),len(errors),'of',len(jobs),flush=True)
 with gzip.open(P/'TRANSFER_REPLAY.json.gz','wt',compresslevel=1) as f:json.dump(rows,f)
 (P/'TRANSFER_ERRORS.json').write_text(json.dumps(errors,indent=2)+'\n');groups=collections.defaultdict(list);results=[]
 for r in rows:groups[(r['variant'],r['scenario'],r['fee'],r['placement_seed'])].append(r)
 for (variant,sc,fee,seed),rr in sorted(groups.items()):
  for scope in ['portfolio','portfolio_without_carryover']+F.RULES:
   for br in [False,True]:results.append(dict(variant=variant,scenario=sc,fee=fee,placement_seed=seed,**F.funded(rr,br,scope)))
 (P/'TRANSFER_FUNDED.json').write_text(json.dumps(results,indent=2)+'\n');print('COMPLETE',len(rows),len(errors),len(results),flush=True)
 # Entry-only paths for original and recovery-confirmed entries. No execution
 # recipe used; altered own inventory is propagated independently of exits.
 neutral=[];ee=[];nj=[]
 for v in ['baseline','joint_keep_targets_dead10']:
  for s in selections[v]:
   if v!='baseline' and s['rule'] not in ['s1_dev_absorption','s3_deadman']:continue
   for sc in ['central80','central85']:nj.append((v,tapes[s['mint']],s,sc))
 with concurrent.futures.ThreadPoolExecutor(4) as ex:
  fs={ex.submit(N.trace,t,s,sc):(v,s) for v,t,s,sc in nj}
  for f in concurrent.futures.as_completed(fs):
   v,s=fs[f]
   try:neutral.append(dict(f.result(),variant=v))
   except Exception as e:ee.append(dict(variant=v,signal=s,error=repr(e)))
 with gzip.open(P/'TRANSFER_ENTRY_TRAJECTORIES.json.gz','wt',compresslevel=1) as f:json.dump(neutral,f)
 (P/'TRANSFER_ENTRY_ERRORS.json').write_text(json.dumps(ee,indent=2)+'\n');print('NEUTRAL_COMPLETE',len(neutral),len(ee),flush=True)
if __name__=='__main__':main()
