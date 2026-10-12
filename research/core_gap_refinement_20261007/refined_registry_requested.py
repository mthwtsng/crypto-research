"""Frozen diagnostic refinements on restored approved tapes and shared cash ledger."""
import collections, concurrent.futures, datetime, gzip, hashlib, json, pathlib
import grace_requested as G
import entry_only as N
E,F=G.E,G.F
OUT=G.U.P/'refined_registry_cycle'
RECIPES=['control','s1_confirmation','s1_age30','s1_both','s2_cap80','s2_age240','s2_target18','s2_target20','s2_cap_target18','s4_grace2','s4_grace4','combined18_2','combined20_4','combined18_2_age240']

def accept(s,t,recipe):
 rule=s['rule']
 if rule=='s1_dev_absorption':
  if recipe in ['s1_age30','s1_both','combined18_2','combined20_4','combined18_2_age240'] and s['age_seconds']<30:return False
  if recipe in ['s1_confirmation','s1_both','combined18_2','combined20_4','combined18_2_age240'] and not confirms(s,t):return False
 if rule=='s2_survival_shelf':
  if recipe in ['s2_cap80','s2_cap_target18','combined18_2','combined20_4','combined18_2_age240'] and s['outside_buyers']>80:return False
  if recipe in ['s2_age240','combined18_2_age240'] and s['age_seconds']>240:return False
 return True

def confirms(s,t):
 # Same causal signal, not a new future-selected dip. Reconstruct the most
 # recent post-peak trough, matching detect(); require distinct buying groups.
 gs=[g for g in t['groups'] if g['venue']=='curve'];i=next(i for i,g in enumerate(gs) if g['signature']==s['signal_signature'])
 peak=0;low=None;lo=0
 for k,g in enumerate(gs[:i+1]):
  p=g['state']['vsol_raw']/g['state']['vtokens_raw']
  if p>=peak:peak=p;low=p;lo=k
  if low is None or p<low:low=p;lo=k
 prior=[]
 for g in gs[lo+1:i+1]:
  if g['slot']>gs[lo]['slot']+3:break
  buyers={e['user'] for e in g['events'] if e['buy'] and e['user']!=t['creator'] and e['sol_raw']>=50_000_000}
  if any(a!=b for old in prior for a in old for b in buyers):return True
  if buyers:prior.append(buyers)
 return False

def cfg(s,recipe,h):
 c=G.T.cfg(s['rule'],h,'percentage_points')
 if s['rule']=='s2_survival_shelf':
  if recipe in ['s2_target18','s2_cap_target18','combined18_2','combined18_2_age240']:c['s2_target']=.18
  if recipe in ['s2_target20','combined20_4']:c['s2_target']=.20
 if s['rule']=='s4_upper_ath':
  if recipe in ['s4_grace2','combined18_2','combined18_2_age240']:c['s4_rejection_grace']=2
  if recipe in ['s4_grace4','combined20_4']:c['s4_rejection_grace']=4
 return c

def write(name,value): (OUT/name).write_text(json.dumps(value,indent=2)+'\n')
def main():
 OUT.mkdir(exist_ok=True)
 saved=json.load(gzip.open(G.OUT/'CONTROL_REPLAY.json.gz','rt'))
 # Existing exact restored-control parity verified in previous study; independently
 # regenerate the full headline grid before allowing any treatment results.
 base=[r for r in saved if r['horizon']==60]
 spec=dict(frozen_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),recipes=RECIPES,looks=13,retrospective=True,data='October3–6:1800creation-selectedlaunches,223signals166mints',bankroll_SOL=15,position_limit=None,ticket_SOL=.5,probe_SOL=.25,entry_scope='Original authenticated saved signals; S1 individual>=.05 buys in two distinct complete groups after original trough (original3slot window), age30 filter; S2 prefix outsidebuyers<=80; optionalage<=240 separate. No later reentry after filter rejection.',exit_scope='S2 40% at18/20 executable net percent; original remainder15pp trail. S4 rejection grace2/4s, independent clock. S3/S5 unchanged. Undefined runners remain open; no file-end sale.',registry_reconciliation='Registry prose misstates source entries: original S1 1–5SOL/95%creator exhaustion/2buyers total.3SOL/3slot recovery; S2 10.8crossing<=14/25buyers/top20%; S4 16–22SOL ATH/22buyers/1SOLbuy; S5 72crossing/100holders/positiveflow. This compares exact benchmark source, not untested prose substitutes.',hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [pathlib.Path(__file__),pathlib.Path(E.__file__),pathlib.Path(F.__file__)]})
 write('SPEC.json',spec)
 tapes={w:G.load(w) for w in ['earlier','later']}
 canonical=[r for r in base if r['scenario']=='central85' and r['fee']==1505000 and r['ticket']==.5]
 assert len(canonical)==223
 jobs=[r for r in base if r['scenario']=='central85' and r['fee']==1505000]
 def replay(r,recipe='control',h=60):
  return dict(E.simulate(tapes[r['window']][r['mint']],r,r['scenario'],'lower',r['ticket'],r['fee'],cfg(r,recipe,h)),window=r['window'],horizon=h,trail_basis='percentage_points')
 with concurrent.futures.ThreadPoolExecutor(4) as ex: recovered=list(ex.map(replay,jobs))
 mismatches=[]
 for r,z in zip(jobs,recovered):
  z=json.loads(json.dumps(z));different=[k for k in set(r)|set(z) if r.get(k)!=z.get(k)]
  if different:mismatches.append(dict(mint=r['mint'],fields=different))
 write('CONTROL_PARITY.json',dict(compared=len(jobs),mismatches=mismatches));assert not mismatches
 print('CONTROL_PARITY',len(jobs),flush=True)
 selection=[]
 for s in canonical:
  t=tapes[s['window']][s['mint']]
  selection.append(dict(window=s['window'],mint=s['mint'],rule=s['rule'],age_seconds=s.get('age_seconds'),outside_buyers=s.get('outside_buyers'),confirmation=confirms(s,t) if s['rule']=='s1_dev_absorption' else None,admitted_by_entry={p:accept(s,t,p) for p in RECIPES}))
 write('ENTRY_SELECTION.json',selection)
 # Entry-first diagnostics: evaluate unchanged causal fills independent of exits.
 entry=[]
 with concurrent.futures.ThreadPoolExecutor(4) as ex:
  ss=[s for s in canonical if s['rule'] in ['s1_dev_absorption','s2_survival_shelf']]
  for s,z in zip(ss,ex.map(lambda s:N.trace(tapes[s['window']][s['mint']],s,'central85'),ss)):
   entry.append(dict(z,window=s['window'],selection={p:accept(s,tapes[s['window']][s['mint']],p) for p in RECIPES}))
 with gzip.open(OUT/'ENTRY_TRAJECTORIES.json.gz','wt',compresslevel=1) as f:json.dump(entry,f)
 print('ENTRY_FIRST',len(entry),flush=True)
 rows=[];cache={};actual=0
 for h in [60,120]:
  source=[r for r in saved if r['horizon']==h or r['rule']!='s3_deadman' and r['horizon']==60]
  for recipe in RECIPES:
   batch=[]
   for r in source:
    if not accept(r,tapes[r['window']][r['mint']],recipe):continue
    c=cfg(r,recipe,h)
    if c==G.T.cfg(r['rule'],h,'percentage_points'):z=dict(r,horizon=h)
    else:
     key=(r['window'],r['mint'],r['rule'],r['signal_signature'],r['scenario'],r['fee'],r['ticket'],json.dumps(c,sort_keys=True))
     if key not in cache:batch.append((key,r))
     continue
    rows.append(dict(z,recipe=recipe))
   with concurrent.futures.ThreadPoolExecutor(4) as ex:
    for (key,r),z in zip(batch,ex.map(lambda j:replay(j[1],recipe,h),batch)):cache[key]=z;actual+=1
   for r in source:
    if not accept(r,tapes[r['window']][r['mint']],recipe):continue
    c=cfg(r,recipe,h)
    if c==G.T.cfg(r['rule'],h,'percentage_points'):continue
    key=(r['window'],r['mint'],r['rule'],r['signal_signature'],r['scenario'],r['fee'],r['ticket'],json.dumps(c,sort_keys=True))
    rows.append(dict(cache[key],horizon=h,recipe=recipe))
   print('RECIPE',h,recipe,'actual',actual,flush=True)
 with gzip.open(OUT/'REPLAY.json.gz','wt',compresslevel=1) as f:json.dump(rows,f)
 funded=[]
 for h in [60,120]:
  for recipe in RECIPES:
   for sc,fee in [(s,1505000) for s in ['fast','central80','central85','slow','stress']]+[('central85',2916000)]:
    rr=[r for r in rows if (r['horizon'],r['recipe'],r['scenario'],r['fee'])==(h,recipe,sc,fee)]
    for br in [True,False]:
     a=F.funded(rr,br,'portfolio',position_limit=None)
     funded.append(dict(recipe=recipe,horizon=h,scenario=sc,fee=fee,**a))
    for rule in F.RULES:
     a=F.funded(rr,True,rule,position_limit=None)
     funded.append(dict(recipe=recipe,horizon=h,scenario=sc,fee=fee,**a))
 write('FUNDED.json',funded)
 for a in funded:
  if (a['horizon'],a['scenario'],a['fee'],a['scope'],a['breakers'])==(60,'central85',1505000,'portfolio',True):print('RESULT',a['recipe'],a['attempts'],a['settled_net_SOL'],a['unresolved_marked_pnl_SOL'],a['last_valid_marked_net_SOL'],flush=True)
 write('RUN_COUNTS.json',dict(control_replays=len(jobs),entry_diagnostics=len(entry),new_replays=actual,assembled=len(rows),funded=len(funded),exceptions=0))
if __name__=='__main__':main()
