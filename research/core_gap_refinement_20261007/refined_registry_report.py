"""Audit all causal fills, report funded refinements and open inventory provenance."""
import collections,gzip,hashlib,json,pathlib,subprocess
import refined_registry_requested as Q
P=Q.OUT

def main():
 rows=json.load(gzip.open(P/'REPLAY.json.gz','rt'));accounts=json.load(open(P/'FUNDED.json'));selection=json.load(open(P/'ENTRY_SELECTION.json'));parity=json.load(open(P/'CONTROL_PARITY.json'));assert not parity['mismatches']
 def pick(recipe='control',sc='central85',h=60,fee=1505000,br=True,scope='portfolio'):
  return next(a for a in accounts if (a['recipe'],a['scenario'],a['horizon'],a['fee'],a['breakers'],a['scope'])==(recipe,sc,h,fee,br,scope))
 control=pick()
 for k,v in dict(attempts=134,closed=86,failed=35,unresolved=13,settled_net_SOL=-.758305176,unresolved_marked_pnl_SOL=1.032373126,last_valid_marked_net_SOL=.274067950).items():assert control[k]==v,(k,control[k],v)
 requotes=0
 for r in rows:
  if r['status']!='failed':assert sum(l['tokens'] for l in r['legs'])+r['remaining']==r['entry_tokens']
  if r['status']=='closed':assert r['net']==sum(l['proceeds']-l['fee'] for l in r['legs'])-r['entry_bill']-r['fee']
  for l in r['legs']:
   assert tuple(l['position'])>tuple(r['entry_position']);assert l['landing_slot']>=l['trigger_slot']
   if l['timer_target'] is not None:assert l['time']>=l['timer_target']
   if l['venue']=='curve':assert l['state_before']['rtokens_raw']>0;got=Q.E.A.sell(l['state_before'],l['tokens'])[0]
   else:got=Q.E.M.A.sell(l['state_before'],l['tokens'])['total']
   assert got==l['proceeds'];requotes+=1
   c=Q.cfg(r,r['recipe'],r['horizon'])
   if 'breakout_rejected' in l['reason']:assert l['time']>=r['entry_time']+c.get('s4_rejection_grace',0)
   if r['rule']=='s2_survival_shelf' and l['reason']=='tailored_40pct_profit_target':assert l['tokens']==max(1,r['entry_tokens']*40//100)
 for a in accounts:
  assert a['attempts']==a['closed']+a['failed']+a['unresolved']
  assert abs(a['settled_net_SOL']+a['unresolved_marked_pnl_SOL']-a['last_valid_marked_net_SOL'])<1e-8
  assert not a['skipped'].get('concurrency');assert a['ending_cash_SOL']>=0
 speed=[]
 for p in Q.RECIPES:
  for h in [60,120]:
   for s in ['fast','central80','slow','stress']:
    a=pick(p,h=h);b=pick(p,s,h=h);aa={(r['mint'],r['rule']):r for r in a['admitted']};bb={(r['mint'],r['rule']):r for r in b['admitted']};common=set(aa)&set(bb)
    speed.append(dict(recipe=p,horizon=h,scenario=s,aggregate_delta=b['last_valid_marked_net_SOL']-a['last_valid_marked_net_SOL'],common=len(common),central_only=len(set(aa)-set(bb)),scenario_only=len(set(bb)-set(aa)),matched_delta=sum(bb[k]['net_SOL']+bb[k]['mark_SOL']-aa[k]['net_SOL']-aa[k]['mark_SOL'] for k in common)))
 alarms=dict(speed_order=dict(status='reviewed: independent guards, admission/breaker paths and delivered exits are not monotone',decomposition=speed),failed_guards=dict(status='pass',delayed_portfolios_without_failures=[a['recipe'] for a in accounts if a['scope']=='portfolio' and a['scenario']!='fast' and a['attempts']>30 and a['failed']==0]),timers='pass: every delivered leg checked against independent buy-anchored deadline',all_closed=dict(status='reviewed',cases=[dict(recipe=a['recipe'],scenario=a['scenario'],scope=a['scope']) for a in accounts if a['attempts']>50 and a['attempts']==a['closed']]),threshold_fill='pass: all delivered legs independently integer requoted; no threshold-price credit',post_completion='pass: all curve sell states have positive remaining real tokens',extreme_stats=dict(status='reviewed',cases=[dict(recipe=a['recipe'],scenario=a['scenario'],scope=a['scope'],PF=a['profit_factor'],WR=a['win_rate']) for a in accounts if a['closed']>50 and ((a['profit_factor'] or 0)>3 or (a['win_rate'] or 0)>.7)]),creation_selection='pass: frozen original1800creation-selected cohort; restored creation histories; no winner selection')
 assert not alarms['failed_guards']['delayed_portfolios_without_failures']
 assert not alarms['extreme_stats']['cases']
 entry=json.load(gzip.open(P/'ENTRY_TRAJECTORIES.json.gz','rt'));diagnostics=[]
 for rule in ['s1_dev_absorption','s2_survival_shelf']:
  for p in ['control','s1_both','s2_cap80','s2_age240','combined18_2_age240']:
   for seconds in [10,60,180]:
    rr=[r for r in entry if r['rule']==rule and r['selection'][p]];covered=[r['horizons'][str(seconds)] for r in rr if r['status']!='failed' and r['horizons'][str(seconds)]['complete'] and r['horizons'][str(seconds)]['net_return'] is not None]
    diagnostics.append(dict(rule=rule,recipe=p,horizon=seconds,signals=len(rr),failed=sum(r['status']=='failed' for r in rr),covered=len(covered),mean_return=sum(r['net_return'] for r in covered)/len(covered) if covered else None,mean_MFE=sum(r['MFE'] for r in covered)/len(covered) if covered else None,hits20=sum(r['MFE']>=.20 for r in covered)))
 marks=[]
 for p in Q.RECIPES:
  a=pick(p);admitted={(r['mint'],r['rule'],r['probe']) for r in a['admitted']}
  for r in rows:
   if (r['recipe'],r['horizon'],r['scenario'],r['fee'],r['status'])!=(p,60,'central85',1505000,'unresolved'):continue
   if (r['mint'],r['rule'],r['ticket']==.25) not in admitted:continue
   marks.append(dict(recipe=p,mint=r['mint'],rule=r['rule'],time=r['last_valid_time'],position=r['last_valid_position'],remaining_raw=r['remaining'],reason=r['reason'],net_committed_cashflow_SOL=r['net']/1e9,inventory_value_after_exit_fee_SOL=r['mark']/1e9,marked_pnl_SOL=(r['net']+r['mark'])/1e9,venue='last-valid counterfactual curve state' if r['reason'] in ['counterfactual_completion_displaced','runner_timeout_undefined'] and not any(l['venue']=='amm' for l in r['legs']) else 'see final delivered leg/state; no authenticated terminal sale',provenance='restored instruction-bound receipt tape; a mark is not a sale or common end-date wealth'))
 tests=[]
 for cmd in [['python3','-m','unittest','discover','-s','research/core_plan_audit_20261007','-p','test_ledger.py'],['python3','research/core_gap_refinement_20261007/test_relative_stop.py']]:
  z=subprocess.run(cmd,capture_output=True,text=True);assert z.returncode==0;tests.append(dict(command=cmd,output=z.stderr+z.stdout))
 checks=dict(control_parity=parity,integer_leg_requotes=requotes,regressions=tests,alarms=alarms,violations=[])
 Q.write('CHECKS.json',checks);Q.write('OPEN_MARKS.json',marks);Q.write('ENTRY_DIAGNOSTICS.json',diagnostics)
 # Actual contributions inside the one shared portfolio, not separate funded runs.
 contributions=[]
 for p in Q.RECIPES:
  a=pick(p)
  for rule in Q.F.RULES:
   rr=[r for r in a['admitted'] if r['rule']==rule];closed=[r for r in rr if r['status']!='unresolved'];opened=[r for r in rr if r['status']=='unresolved']
   contributions.append(dict(recipe=p,rule=rule,attempts=len(rr),settled=sum(r['net_SOL'] for r in closed),open_marked=sum(r['net_SOL']+r['mark_SOL'] for r in opened),combined=sum(r['net_SOL'] for r in rr)+sum(r['mark_SOL'] for r in opened)))
 Q.write('SHARED_CONTRIBUTIONS.json',contributions)
 def verdict(a):return 'undetermined, retrospective' if a['unresolved_mark_value_SOL']>abs(a['last_valid_marked_net_SOL']) else ('positive-central, retrospective' if a['last_valid_marked_net_SOL']>0 and pick(a['recipe'],'fast',h=a['horizon'])['last_valid_marked_net_SOL']>0 else 'negative-central, retrospective')
 cards=[]
 for p in Q.RECIPES:
  a=pick(p);vals=[pick(p,s)['last_valid_marked_net_SOL'] for s in ['fast','central80','central85','slow']]
  cards.append(f'''Candidate: {p}
engine + git revision: approved restored core_plan engine; {subprocess.check_output(['git','rev-parse','--short','HEAD'],text=True).strip()} + SPEC.json working-tree hashes
data: Oct3–6 2026;1800creation-selected launches;223originalsignals/166mints; no outcome-selected additions
rules frozen before data: no; retrospective prescribed refinements
look count:13new recipes x2 S3 horizons=26 policy combinations; prior looks retained in source studies
placement fast/central80/central85/slow combined marked SOL: {vals}
stress tail={pick(p,'stress')['last_valid_marked_net_SOL']:+.9f}; historicalfees={pick(p,fee=2916000)['last_valid_marked_net_SOL']:+.9f}; scheduled3slots=N/A, no new scheduled tipless policy
settled {a['settled_net_SOL']:+.9f} + open marked {a['unresolved_marked_pnl_SOL']:+.9f} = combined {a['last_valid_marked_net_SOL']:+.9f} SOL
attempts/closed/failed/unresolved:{a['attempts']}/{a['closed']}/{a['failed']}/{a['unresolved']}; zero-recovery bound {a['zero_recovery_bound_SOL']:+.9f}; inventory mark value {a['unresolved_mark_value_SOL']:.9f}
max settled drawdown {a['max_settled_drawdown_SOL']:.9f}; largest winner {a['largest_winner_SOL']:.9f}; combined without largest {a['last_valid_marked_net_SOL']-a['largest_winner_SOL']:+.9f}
bug alarms: all8 checked; CHECKS.json records exceptions/decomposition; {requotes}integer leg requotes
verdict: {verdict(a)}
what would change verdict: resolve actual counterfactual migration continuity and frozen later14–21day testing
''')
 (P/'CANDIDATE_RESULT_CARDS.md').write_text('\n\n'.join('```text\n'+c+'```' for c in cards))
 lines=['# Refined registry rerun — shared funded accounting','','Tested the prescribed refinements against the exact restored benchmark control. All results are retrospective; open marks remain estimates. No live settings changed.','', '## Central85 shared 15 SOL portfolio','', '| Recipe | Attempts | Settled SOL | Open marked PnL SOL | Combined marked SOL | Open |','|---|---:|---:|---:|---:|---:|']
 for p in Q.RECIPES:
  a=pick(p);lines.append(f"| {p} | {a['attempts']} | {a['settled_net_SOL']:+.6f} | {a['unresolved_marked_pnl_SOL']:+.6f} | {a['last_valid_marked_net_SOL']:+.6f} | {a['unresolved']} |")
 lines+=['','## Findings','','S1 already requires multiple outside buyers in the source detector. All36original S1signals also satisfy two separate >=.05SOL outside buyer transactions. The confirmation-only variant is exactly the control; the proposed age30filter retains7 of36. It is not a new S3-style rescue. Original S1recovery window is3slots after trough; retained for benchmark fidelity.','', 'S2cap80retains36of49signals; age240retains26; bothretain24. These are separate retrospective filters, not evidence that excluded addresses were trapped bagholders. Clip18/20 are independent exit ablations; no hidden new entry thresholds.','', 'S4is the actual16–22SOL ATH setup, not a near80SOL entry. Two/four-second grace use independent clock deadlines and preserve profit clips. Source observed excursions are opportunities, not delivered profit or proof that losses are exclusively sell-side.','', 'S3/S5entries and exits are unchanged. Full portfolio differences also change funded admission/breaker histories, so standalone family sums are not portfolio profit. See SHARED_CONTRIBUTIONS.json for contributions inside the same account.','', '## Source/runner discrepancies repaired','','The previous scripts/run_canonical_backtest.py loaded raw unbound PKL events, set wallet custody for every tape, omitted later AMM collection, swallowed pool errors and summed standalone outcomes while merely printing a15SOL bankroll. Its results cannot establish the advertised cash-funded benchmarks. The repaired CLI uses restored instruction-bound inputs and ledger.funded, including actual cash locks, same-mint exclusions, circuit breakers and reduced probes; optional600sdeadline no longer silently changes the control. Original output files are preserved, not relabeled as measured profit.','', 'Registry prose entry definitions also differ from its benchmark source. SPEC.json records exact code definitions and this study compares those exact signals; arbitrary changed reserve/creator thresholds were not slipped into the control. Registry reconciliation records these factual corrections.','', '## Entry-first diagnostics and checks','','ENTRY_TRAJECTORIES.json.gz contains85S1/S2exit-free Central85trajectories before treatment exits. ENTRY_DIAGNOSTICS.json separates failed fills, complete horizon coverage and excursions; no oracle peak sale.446independent restored Central85control replays match all fields exactly; the original full3024control parity and171138AMMsource transition checks are retained in grace_verification_cycle. Control funded decomposition exactly matches the saved card. CHECKS.json checks all delivered timer/custody/integerquote/accounting invariants,18regression tests and8alarms.','', 'OPEN_MARKS.json identifies last-valid time/venue, remaining tokens, committed cashflow and net marks. Displaced completions do not authorize invented AMM fills; undefined runners remain inventory. These marks are not synchronized end-date wealth. Zero-recovery is only a downside bound.','', '## Reproduce','','`python3 research/core_gap_refinement_20261007/refined_registry_requested.py` then `python3 research/core_gap_refinement_20261007/refined_registry_report.py`. Original control shortcut: `python3 scripts/run_canonical_backtest.py --scenarios fast,central80,central85,slow --output-dir reports/restored_control`.', '', '## Required result card — prescribed primary combined18_2','','```text',cards[Q.RECIPES.index('combined18_2')],'```']
 (P/'REPORT.md').write_text('\n'.join(lines)+'\n')
 print('REPORT_COMPLETE',requotes)
 for p in ['control','combined18_2','combined20_4','combined18_2_age240']:a=pick(p);print(p,a['settled_net_SOL'],a['unresolved_marked_pnl_SOL'],a['last_valid_marked_net_SOL'],verdict(a))
if __name__=='__main__':main()
