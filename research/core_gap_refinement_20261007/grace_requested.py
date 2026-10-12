"""Verify the restored control, then fixed S1/S4 grace and deadline ablations."""
import collections,concurrent.futures,datetime,gzip,hashlib,json,pathlib,sys
import tailored_requested as T,restore_replay_inputs as R
U=T.U;E=U.E;F=U.F;OUT=U.P/'grace_verification_cycle';OUT.mkdir(exist_ok=True)
RECIPES=['control','s1_trough6','s4_rejection6','both6','both6_deadline600']
def config(rule,h,recipe):
 c=T.cfg(rule,h,'percentage_points')
 if recipe in ['s1_trough6','both6','both6_deadline600'] and rule=='s1_dev_absorption':c['s1_trough_grace']=6
 if recipe in ['s4_rejection6','both6','both6_deadline600'] and rule=='s4_upper_ath':c['s4_rejection_grace']=6
 if recipe=='both6_deadline600' and rule in ['s1_dev_absorption','s2_survival_shelf','s4_upper_ath']:c['runner_max_hold']=600
 return c

def load(window):
 saved=json.load(gzip.open(T.OUT/'REPLAY.json.gz','rt'));ss=[r for r in saved if r['window']==window and r['scenario']=='central85' and r['fee']==1505000 and r['ticket']==.5 and r['horizon']==60 and r['trail_basis']=='percentage_points'];tapes={};pools={}
 ammdir=R.OUT/'earlier/amm_tapes' if window=='earlier' else U.P/'recovery_sequence_cycle/later/execution/amm_tapes'
 for f in ammdir.glob('*.gz'):
  t=json.load(gzip.open(f,'rt'));pools[t['mint']]=t
 for mint in {s['mint'] for s in ss}:
  f=R.OUT/window/'bound_curve_tapes'/(mint+'.json.gz');key='token_account'
  original=U.R.V.BASE/'bound_curve_tapes'/f.name
  if window=='earlier' and original.exists() and not original.is_symlink():f=original;key='wallet'
  t=json.load(gzip.open(f,'rt'));gs=[dict(g,venue='curve',trades=g['events'],time=g['block_time']) for g in t['groups']]
  if mint in pools:
   pool=pools[mint];t['migration_quote_difference']=next(g['state']['rsol_raw'] for g in gs if g['state']['rtokens_raw']==0)-pool['groups'][0]['before']['quote'];gs.extend(dict(g,venue='amm') for g in pool['groups'])
  gs.sort(key=lambda g:(g['slot'],g['index']));t.update(groups=gs,inventory_key=key);tapes[mint]=t
  for g in gs:E.O.CLOCK[g['slot']]=g['time']
 E.O.C.P=R.OUT
 return tapes

def main():
 saved=json.load(gzip.open(T.OUT/'REPLAY.json.gz','rt'));base=[r for r in saved if r['trail_basis']=='percentage_points' and (r['horizon']==60 or r['rule']=='s3_deadman')]
 # Same source/control hash, parameters and complete scenario/ticket grid.
 spec=dict(frozen_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),status='retrospective development, same inspected1800launches/223signals/166mints',recipes=RECIPES,grace='S1: only trough invalidation deferred6s; net-10% remains immediate. S4: defer -8% rejection to6s, retaining >=2slot condition. Independent quiet-market deadlines; profit targets remain active.',deadline='Separate declared600s hard hold for undefined S1/S2/S4 runners; ordinary causal sell placement/requote; never a last-tape sale. S3/S5 unchanged.',bankroll=15,ticket=.5,position_limit=None,probe_ticket=.25,horizons=[60,120],trail_basis='percentage_points; original S4/S5relative trails unchanged',new_exit_looks=4,hashes={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in [pathlib.Path(__file__),pathlib.Path(E.__file__),pathlib.Path(F.__file__),pathlib.Path(E.M.A.__file__),pathlib.Path(E.O.__file__)]})
 (OUT/'SPEC.json').write_text(json.dumps(spec,indent=2)+'\n')
 control=[];errors=[];mismatches=[];tapesby={}
 for window in ['earlier','later']:
  tapes=load(window);tapesby[window]=tapes;rr=[r for r in base if r['window']==window]
  def run(r):
   return dict(E.simulate(tapes[r['mint']],r,r['scenario'],'lower',r['ticket'],r['fee'],config(r['rule'],r['horizon'],'control')),window=window,horizon=r['horizon'],trail_basis='percentage_points')
  with concurrent.futures.ThreadPoolExecutor(4) as ex:
   fs={ex.submit(run,r):r for r in rr}
   for f in concurrent.futures.as_completed(fs):
    r=fs[f]
    try:
     z=f.result();z=json.loads(json.dumps(z));different=[k for k in set(r)|set(z) if r.get(k)!=z.get(k)]
     if different:mismatches.append(dict(window=window,mint=r['mint'],rule=r['rule'],scenario=r['scenario'],fee=r['fee'],ticket=r['ticket'],horizon=r['horizon'],fields=different,saved={k:r.get(k) for k in different},restored={k:z.get(k) for k in different}))
     control.append(z)
    except Exception as e:errors.append(dict(window=window,mint=r['mint'],error=repr(e)))
    if (len(control)+len(errors))%100==0:print('CONTROL',len(control),len(errors),'mismatches',len(mismatches),flush=True)
  print('CONTROL_WINDOW',window,len(control),len(mismatches),len(errors),flush=True)
 with gzip.open(OUT/'CONTROL_REPLAY.json.gz','wt',compresslevel=1) as f:json.dump(control,f)
 (OUT/'CONTROL_PARITY.json').write_text(json.dumps(dict(compared=len(control),errors=errors,mismatches=mismatches),indent=2)+'\n')
 if errors or mismatches:raise AssertionError(('restored control differs',len(errors),len(mismatches)))
 rows=[dict(r,recipe='control') for r in control];count=len(control)
 for window,tapes in tapesby.items():
  jobs=[]
  for r in control:
   if r['window']!=window:continue
   for recipe in RECIPES[1:]:
    if config(r['rule'],r['horizon'],recipe)==config(r['rule'],r['horizon'],'control'):rows.append(dict(r,recipe=recipe))
    else:jobs.append((r,recipe))
  def run(j):
   r,recipe=j;return dict(E.simulate(tapes[r['mint']],r,r['scenario'],'lower',r['ticket'],r['fee'],config(r['rule'],r['horizon'],recipe)),window=window,horizon=r['horizon'],trail_basis='percentage_points',recipe=recipe)
  with concurrent.futures.ThreadPoolExecutor(4) as ex:
   fs={ex.submit(run,j):j for j in jobs}
   for f in concurrent.futures.as_completed(fs):
    try:rows.append(f.result());count+=1
    except Exception as e:errors.append(dict(job=fs[f],error=repr(e)))
    if count%100==0:print('GRACE_REPLAY',count,'errors',len(errors),flush=True)
 with gzip.open(OUT/'REPLAY.json.gz','wt',compresslevel=1) as f:json.dump(rows,f)
 (OUT/'ERRORS.json').write_text(json.dumps(errors,indent=2)+'\n');assert not errors
 expanded=[]
 for r in rows:
  for h in ([r['horizon']] if r['rule']=='s3_deadman' else [60,120]):expanded.append(dict(r,horizon=h))
 holds={(a['window'],a['mint'],a['rule'],a['signature']):a for a in json.load(open(U.OUT/'CREATOR_HOLDINGS.json'))};funded=[]
 for recipe in RECIPES:
  for h in [60,120]:
   for gate in [False,True]:
    for window in ['earlier','later','continuous']:
     for sc,fee in [(x,1505000) for x in ['fast','central80','central85','slow','stress']]+[('central85',2916000)]:
      rr=[r for r in expanded if (r['recipe'],r['horizon'],r['scenario'],r['fee'])==(recipe,h,sc,fee) and (window=='continuous' or r['window']==window)]
      if gate:rr=[r for r in rr if holds[(r['window'],r['mint'],r['rule'],r['signal_signature'])]['passes']]
      for scope in ['portfolio','portfolio_without_carryover']+F.RULES:
       for br in [False,True]:
        actual=F.funded(rr,br,scope,position_limit=None);assert actual==F.funded(rr,br,scope,position_limit=None)
        funded.append(dict(recipe=recipe,horizon=h,developer_gate=gate,window=window,scenario=sc,fee=fee,**actual))
 (OUT/'FUNDED.json').write_text(json.dumps(funded,indent=2)+'\n');(OUT/'RUN_COUNTS.json').write_text(json.dumps(dict(control_replays=len(control),actual_replays=count,assembled_traces=len(expanded),funded_scenarios=len(funded),exceptions=len(errors)),indent=2)+'\n')
 for r in funded:
  if (r['horizon'],r['developer_gate'],r['window'],r['scenario'],r['fee'],r['scope'],r['breakers'])==(60,False,'continuous','central85',1505000,'portfolio',True):print('RESULT',r['recipe'],r['attempts'],r['closed'],r['failed'],r['unresolved'],r['settled_net_SOL'],r['unresolved_marked_pnl_SOL'],r['last_valid_marked_net_SOL'],flush=True)
if __name__=='__main__':main()
