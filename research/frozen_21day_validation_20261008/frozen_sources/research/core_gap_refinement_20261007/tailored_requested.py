"""Tailored runner exits on the existing five causal entry families."""
import collections,concurrent.futures,datetime,gzip,hashlib,json,pathlib
import unlimited_requested as N
U=N.U;OUT=U.P/'tailored_requested_cycle';OUT.mkdir(exist_ok=True)
def cfg(rule,h,basis):
 common={'tailored_trail_basis':basis}
 if rule=='s1_dev_absorption':common.update(s1_dynamic_exit=True)
 if rule=='s2_survival_shelf':common.update(s2_dynamic_exit=True)
 if rule=='s3_deadman':common.update(s3_extended_hold=h,s3_grace=8,s3_relative_price_stop=.12,s3_dynamic_arm=.75,s3_dynamic_width=.20)
 if rule=='s4_upper_ath':common.update(s4_remove_short_timeout=True)
 return common

def main():
 spec=dict(frozen_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),source='User requests retest each entry with its tailored new exit; optional scope questions unanswered after60s',entry_scope='Assumption: existing five S1–S5 entries, including S3two_buy_groups; pasted new architecture gives no new entry thresholds; not equivalent to four generic path families',trail_scope='Primary percentage-points on executable total-position ROI including delivered realized tranches; relative wealth-factor trailing sensitivity separately labeled; S4/S5original relative trails unchanged',S1='Keep trough/net-10 invalidation; remove6s timer;40%original tokens at executable25%;trail60%15pp',S2='Keep9.8shelf and10%armed breakeven;40%original tokens at30%;trail60%15pp',S3='Keep fill-relative12%price stop after8s grace;no hardTP;arm full executable trail75%;giveback20pp;60/120s hard timeout',S4='Keep >=2slot -8% rejection;half20%+relative6%remainder trail;remove short7s pre-clip timeout, allow migration',S5='Unchanged72crossing entry;curve<=60invalidation;halfafterwholeauthenticAMMopen;8%relative trail;documented30s AMMtimeout',missing_timeout='S1/S2/S4undefined long runner deadline remains coverage-censored at600s, not an invented sell; retained custody/capital',bankroll_SOL=15,ticket_SOL=.5,position_limit=None,creator_ablation=[False,True],breakers=[False,True],data='Same1800previously inspected October3–6launches;223signals166mints;no new date confirmation',looks='50prior configurations;four tailored horizon×trail-basis cases with/without developer gate =8new looks',engine_hashes={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in [pathlib.Path(__file__),U.R.V.BASE/'engine.py',pathlib.Path(U.F.__file__)]})
 (OUT/'SPEC.json').write_text(json.dumps(spec,indent=2)+'\n')
 old=json.load(gzip.open(N.OUT/'RELATIVE_REPLAY.json.gz','rt'));selection=json.load(open(U.R.OUT/'SIGNALS.json'));base=[r for r in old if r['horizon']==60 and r['profit_target']==.2];rows=[];errors=[];jobs_count=0
 for window in ['earlier','later']:
  tapes,_,_=U.R.prepare(window,selection[window]);jobs=[(r,h,b) for r in base if r['window']==window for h in ([60,120] if r['rule']=='s3_deadman' else [0]) for b in (['percentage_points','relative'] if r['rule'] in ['s1_dev_absorption','s2_survival_shelf','s3_deadman'] else ['unchanged'])];jobs_count+=len(jobs)
  def run(j):
   r,h,b=j
   return dict(U.E.simulate(tapes[r['mint']],r,r['scenario'],'lower',r['ticket'],r['fee'],cfg(r['rule'],h,b)),window=window,horizon=h,trail_basis=b)
  with concurrent.futures.ThreadPoolExecutor(4) as ex:
   fs={ex.submit(run,j):j for j in jobs}
   for f in concurrent.futures.as_completed(fs):
    try:rows.append(f.result())
    except Exception as e:errors.append(dict(job=fs[f],error=repr(e)))
    if (len(rows)+len(errors))%100==0:print('REPLAY',len(rows),len(errors),flush=True)
  print('WINDOW_DONE',window,len(rows),flush=True)
 expanded=[]
 for r in rows:
  for h in ([r['horizon']] if r['horizon'] else [60,120]):
   for b in ([r['trail_basis']] if r['trail_basis']!='unchanged' else ['percentage_points','relative']):expanded.append(dict(r,horizon=h,trail_basis=b))
 rows=expanded
 with gzip.open(OUT/'REPLAY.json.gz','wt',compresslevel=1) as f:json.dump(rows,f)
 (OUT/'ERRORS.json').write_text(json.dumps(errors,indent=2)+'\n');assert not errors,errors
 holds={(a['window'],a['mint'],a['rule'],a['signature']):a for a in json.load(open(U.OUT/'CREATOR_HOLDINGS.json'))};funded=[]
 for h in [60,120]:
  for b in ['percentage_points','relative']:
   for gate in [False,True]:
    for window in ['earlier','later','continuous']:
     for sc,fee in [(x,1505000) for x in ['fast','central80','central85','slow','stress']]+[('central85',2916000)]:
      rr=[r for r in rows if (r['horizon'],r['trail_basis'],r['scenario'],r['fee'])==(h,b,sc,fee) and (window=='continuous' or r['window']==window)]
      if gate:rr=[r for r in rr if holds[(r['window'],r['mint'],r['rule'],r['signal_signature'])]['passes']]
      for scope in ['portfolio','portfolio_without_carryover']+U.F.RULES:
       for br in [False,True]:
        actual=U.F.funded(rr,br,scope,position_limit=None);assert actual==U.F.funded(rr,br,scope,position_limit=None)
        funded.append(dict(horizon=h,trail_basis=b,developer_gate=gate,window=window,scenario=sc,fee=fee,**actual))
 (OUT/'FUNDED.json').write_text(json.dumps(funded,indent=2)+'\n');(OUT/'RUN_COUNTS.json').write_text(json.dumps(dict(actual_replays=jobs_count,assembled_traces=len(rows),funded_scenarios=len(funded),exceptions=len(errors)),indent=2)+'\n')
 for r in funded:
  if r['window']=='continuous' and r['scenario']=='central85' and r['fee']==1505000 and r['scope']=='portfolio' and r['breakers']:print('RESULT',r['horizon'],r['trail_basis'],r['developer_gate'],r['attempts'],r['closed'],r['failed'],r['unresolved'],r['settled_net_SOL'],r['unresolved_marked_pnl_SOL'],r['last_valid_marked_net_SOL'],flush=True)
 print('DONE',jobs_count,len(rows),len(funded),flush=True)
if __name__=='__main__':main()
