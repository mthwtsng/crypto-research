"""Small mechanism tests fixed after entry diagnostics, before new sell runs."""
import concurrent.futures,datetime,gzip,hashlib,json,pathlib,pickle,sys
P=pathlib.Path(__file__).resolve().parent;ROOT=P.parents[1];BASE=P.parent/'core_plan_audit_20261007'
sys.path.insert(0,str(BASE));import engine as E,ledger as F
from analyze_entries import features

CONFIGS={
 'baseline':{},
 'dev_breadth':dict(entry='dev_breadth'),
 'dev_small_target':dict(s1_target=.10),
 'shelf_full_trail':dict(s2_full_trail=True),
 'deadman_scratch3':dict(s3_scratch=3),
 'deadman_scratch5':dict(s3_scratch=5),
 'deadman_confirm':dict(entry='dip_confirm'),
 'ath_timer20':dict(s4_timeout=20),
 'ath_stop15':dict(s4_stop=.15),
 'ath_timer20_stop15':dict(s4_timeout=20,s4_stop=.15),
 'deadman_next_group':dict(entry='dip_next_group'),
 'joint_keep_targets_dead10':dict(s4_timeout=20,s4_stop=.15),
 'joint_lower_target_dead10':dict(s1_target=.10,s4_timeout=20,s4_stop=.15),
 'joint_keep_targets_dead3':dict(s3_scratch=3,s4_timeout=20,s4_stop=.15),
 'joint_lower_target_dead3':dict(s1_target=.10,s3_scratch=3,s4_timeout=20,s4_stop=.15),
 'confirmed_full5':dict(entry='dip_confirm',s3_full_target=.05),
 'confirmed_full10':dict(entry='dip_confirm',s3_full_target=.10),
 'confirmed_half10':dict(entry='dip_confirm',s3_half_target=.10),
 'joint_confirmed_half10':dict(s3_half_target=.10,s4_timeout=20,s4_stop=.15),
}
TARGET_RULE={
 'dev_breadth':'s1_dev_absorption','dev_small_target':'s1_dev_absorption',
 'shelf_full_trail':'s2_survival_shelf',
 'deadman_scratch3':'s3_deadman','deadman_scratch5':'s3_deadman','deadman_confirm':'s3_deadman',
 'ath_timer20':'s4_upper_ath','ath_stop15':'s4_upper_ath','ath_timer20_stop15':'s4_upper_ath',
 'deadman_next_group':'s3_deadman',
 'confirmed_full5':'s3_deadman','confirmed_full10':'s3_deadman','confirmed_half10':'s3_deadman',
}

def selected(signals,raw,variant):
 if variant=='baseline':return signals
 if variant.startswith('confirmed_'):return selected(signals,raw,'deadman_confirm')
 if variant.startswith('joint_'):
  return selected(signals,raw,'dev_breadth')+selected(signals,raw,'deadman_confirm')+[s for s in signals if s['rule'] in ['s2_survival_shelf','s4_upper_ath','s5_carryover']]
 target=TARGET_RULE[variant];out=[]
 for s in signals:
  if s['rule']!=target:continue
  t=raw[s['mint']];ff=features(t,s)
  if variant=='dev_breadth' and (ff['recent_buyers']<3 or ff['recent_buy_SOL']<.5):continue
  if variant in ['deadman_confirm','deadman_next_group']:
   i=next(i for i,g in enumerate(t['groups']) if g['signature']==s['signal_signature']);chosen=None
   for g in t['groups'][i+1:]:
    if g['slot']>s['slot']+2:break
    reserve=g['state']['rsol_raw']/1e9
    if g['state']['rtokens_raw']==0:break
    if not g['events']:continue
    qualifies=variant=='deadman_next_group' or any(e['buy'] and e['user']!=t['creator'] and e['sol_raw']>=50000000 for e in g['events'])
    if qualifies:
     if 8<=reserve<=18:chosen=g
     break
   if chosen is None:continue
   s=dict(s,original_signal_signature=s['signal_signature'],original_signal_slot=s['slot'],signal_signature=chosen['signature'],slot=chosen['slot'],time=chosen['block_time'],reserve=chosen['state']['rsol_raw']/1e9)
  out.append(s)
 return out

def prepare():
 tapes,ss=E.load();raw={t['mint']:t for t in pickle.load(gzip.open(ROOT/'research/day_general_20261004/TAPES.pkl.gz','rb'))};selection={v:selected(ss,raw,v) for v in CONFIGS};(P/'VARIANT_SIGNALS.json').write_text(json.dumps(selection,indent=2)+'\n');return tapes,selection

def run():
 tapes,selection=prepare();scenarios=[(s,1505000) for s in ['fast','central80','central85','slow','stress']]+[('central85',2916000)];jobs=[]
 results=[];errors=[]
 if '--incremental' in sys.argv:
  results=json.load(gzip.open(P/'VARIANT_REPLAY.json.gz','rt'));errors=json.loads((P/'VARIANT_ERRORS.json').read_text())
 done={r['variant'] for r in results}
 for variant,cfg in CONFIGS.items():
  if variant in done:continue
  for s in selection[variant]:
   for sc,fee in scenarios:
    for ticket in [.5,.25]:jobs.append((variant,tapes[s['mint']],s,sc,fee,ticket,cfg))
 def execute(j):
  variant,t,s,sc,fee,ticket,cfg=j;r=E.simulate(t,s,sc,'lower',ticket,fee,cfg);return dict(r,variant=variant)
 with concurrent.futures.ThreadPoolExecutor(4) as ex:
  futures={ex.submit(execute,j):j for j in jobs}
  for f in concurrent.futures.as_completed(futures):
   try:results.append(f.result())
   except Exception as e:errors.append(dict(variant=futures[f][0],signal=futures[f][2],error=repr(e)))
   if (len(results)+len(errors))%100==0:print('VARIANTS',len(results),len(errors),'of',len(jobs),flush=True)
 with gzip.open(P/'VARIANT_REPLAY.json.gz','wt',compresslevel=1) as f:json.dump(results,f)
 (P/'VARIANT_ERRORS.json').write_text(json.dumps(errors,indent=2)+'\n');print('COMPLETE',len(results),len(errors),flush=True)

def ledger():
 rows=json.load(gzip.open(P/'VARIANT_REPLAY.json.gz','rt'));groups={};results=[]
 for r in rows:groups.setdefault((r['variant'],r['scenario'],r['fee']),[]).append(r)
 for (v,sc,fee),rr in sorted(groups.items()):
  scopes=['portfolio','portfolio_without_carryover']+F.RULES if v=='baseline' or v.startswith('joint_') else [TARGET_RULE[v]]
  for scope in scopes:
   for br in [False,True]:results.append(dict(variant=v,scenario=sc,fee=fee,**F.funded(rr,br,scope)))
 (P/'VARIANT_FUNDED.json').write_text(json.dumps(results,indent=2)+'\n')
 for r in results:
  if r['scenario']=='central85' and r['fee']==1505000 and not r['breakers']:print(r['variant'],r['scope'],r['attempts'],r['closed'],r['failed'],r['unresolved'],round(r['net_zero_SOL'],4),round(r['net_marked_SOL'],4))

def freeze():
 spec=dict(created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),stage='mechanism-based refinements after entry-only diagnostics; before variant sell outcomes',data='600 inspected October3–4 launches; retrospective development; not a holdout',looks=dict(exit_changes=8,entry_changes=2,configs=len(CONFIGS)-1),configs=CONFIGS,selection={'dev_breadth':'additional >=3 outside buyers and >=0.5SOL buys in trailing3 slots, same signal; baseline exit retained','dip_confirm':'first >=0.05SOL outside buy within2slots after dip, reserve8–18; baseline exit retained; new quote/guard at new signal'},constraints=dict(bankroll=15,ticket=.5,probe=.25,max_open=2),hashes={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in [P/'variants.py',BASE/'engine.py',P/'ENTRY_TRAJECTORIES.json.gz']})
 (P/'STAGE2_SPEC.json').write_text(json.dumps(spec,indent=2)+'\n')
if __name__=='__main__':
 if '--freeze' in sys.argv:freeze()
 elif '--ledger' in sys.argv:ledger()
 else:run()
