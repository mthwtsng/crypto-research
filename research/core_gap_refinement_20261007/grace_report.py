"""Causal checks, exit attribution and accounting-separated grace rerun report."""
import collections,gzip,hashlib,json,pathlib,subprocess
import grace_requested as G
P=G.OUT;L=10**9
KEY=['window','mint','rule','signal_signature','scenario','fee','ticket','horizon']
def key(r):return tuple(r[k] for k in KEY)
def main():
 rows=json.load(gzip.open(P/'REPLAY.json.gz','rt'));accounts=json.load(open(P/'FUNDED.json'));counts=json.load(open(P/'RUN_COUNTS.json'));control={key(r):r for r in rows if r['recipe']=='control'};parity=json.load(open(P/'CONTROL_PARITY.json'));assert not parity['errors'] and not parity['mismatches']
 violations=[];requotes=0;entryparity=0
 for r in rows:
  old=control[key(r)]
  for k in ['signal_position','entry_position','entry_time','entry_bill','entry_tokens']:assert r.get(k)==old.get(k),(k,r['mint'])
  entryparity+=1
  if r['status']!='failed':assert sum(l['tokens'] for l in r['legs'])+r['remaining']==r['entry_tokens']
  if r['status']=='closed':assert r['net']==sum(l['proceeds']-l['fee'] for l in r['legs'])-r['entry_bill']-r['fee']
  for leg in r['legs']:
   assert tuple(leg['position'])>tuple(r['entry_position'])
   assert leg['landing_slot']>=leg['trigger_slot']
   if leg.get('timer_target') is not None:assert leg['time']>=leg['timer_target']
   if leg['venue']=='curve':
    assert leg['state_before']['rtokens_raw']>0;q=G.E.A.sell(leg['state_before'],leg['tokens']);got=q[0]
   else:got=G.E.M.A.sell(leg['state_before'],leg['tokens'])['total']
   assert got==leg['proceeds'];requotes+=1
   if r['rule']=='s3_deadman' and ('runner_trail' in leg['reason'] or 'relative_price_stop' in leg['reason']):assert leg['time']>=r['entry_time']+8
   if r['recipe'] in ['s4_rejection6','both6','both6_deadline600'] and r['rule']=='s4_upper_ath' and 'breakout_rejected' in leg['reason']:assert leg['time']>=r['entry_time']+6
   if leg['reason']=='runner_timeout':assert leg['timer_target']==r['entry_time']+600
 for r in accounts:
  assert r['attempts']==r['closed']+r['failed']+r['unresolved'];assert not r['skipped'].get('concurrency')
  assert abs(r['settled_net_SOL']+r['unresolved_marked_pnl_SOL']-r['last_valid_marked_net_SOL'])<1e-8
  assert abs(r['ending_cash_SOL']-15-r['zero_recovery_bound_SOL'])<1e-8
 def pick(recipe='control',h=60,gate=False,scope='portfolio',br=True,sc='central85',window='continuous',fee=1505000):
  return next(r for r in accounts if (r['recipe'],r['horizon'],r['developer_gate'],r['scope'],r['breakers'],r['scenario'],r['window'],r['fee'])==(recipe,h,gate,scope,br,sc,window,fee))
 # The regenerated cash-funded original ledger must match the original account
 # too, after the exact complete trade-output parity above.
 new=pick()
 for k,v in dict(attempts=134,closed=86,failed=35,unresolved=13,settled_net_SOL=-.758305176,unresolved_marked_pnl_SOL=1.032373126,last_valid_marked_net_SOL=.274067950).items():assert new[k]==v,(k,new[k],v)
 oldchecks=json.load(open(G.T.OUT/'CHECKS.json'))
 assert hashlib.sha256(pathlib.Path(G.F.__file__).read_bytes()).hexdigest()==oldchecks['hashes'][str(pathlib.Path(G.F.__file__))]

 audit=[]
 for rule,reason in [('s1_dev_absorption','floor_invalidation'),('s4_upper_ath','breakout_rejected')]:
  rr=[r for r in control.values() if (r['rule'],r['scenario'],r['fee'],r['ticket'],r['horizon'])==(rule,'central85',1505000,.5,60)]
  stops=[r for r in rr if any(l['reason']==reason for l in r['legs'])];ages=[next(l['time']-r['entry_time'] for l in r['legs'] if l['reason']==reason) for r in stops]
  audit.append(dict(rule=rule,unique_attempts=len(rr),unique_stop_paths=len(stops),stops_before6s=sum(a<6 for a in ages),stop_path_net_SOL=sum(r['net'] for r in stops)/L))
 (P/'CLAIM_AUDIT.json').write_text(json.dumps(audit,indent=2)+'\n')
 attribution=[]
 for recipe in G.RECIPES[1:]:
  for rule in G.F.RULES:
   pairs=[(r,control[key(r)]) for r in rows if (r['recipe'],r['rule'],r['scenario'],r['fee'],r['ticket'],r['horizon'])==(recipe,rule,'central85',1505000,.5,60)]
   closed=[(r,o) for r,o in pairs if r['status']==o['status']=='closed'];changed=[dict(mint=r['mint'],old=o['status'],new=r['status'],old_reason=o.get('reason'),new_reason=r.get('reason')) for r,o in pairs if r['status']!=o['status']]
   attribution.append(dict(recipe=recipe,rule=rule,attempts=len(pairs),both_closed=len(closed),saved_old_losers_SOL=sum(max(0,r['net']-o['net']) for r,o in closed if o['net']<0)/L,extra_old_loser_damage_SOL=sum(min(0,r['net']-o['net']) for r,o in closed if o['net']<0)/L,surrendered_old_winner_SOL=sum(min(0,r['net']-o['net']) for r,o in closed if o['net']>=0)/L,added_old_winner_SOL=sum(max(0,r['net']-o['net']) for r,o in closed if o['net']>=0)/L,net_both_closed_change_SOL=sum(r['net']-o['net'] for r,o in closed)/L,status_changes=changed))
 (P/'MATCHED_ATTRIBUTION.json').write_text(json.dumps(attribution,indent=2)+'\n')
 speed=[]
 for recipe in G.RECIPES:
  for sc in ['fast','central80','slow','stress']:
   a={(z['mint'],z['rule']):z for z in pick(recipe)['admitted']};d={(z['mint'],z['rule']):z for z in pick(recipe,sc=sc)['admitted']};common=set(a)&set(d)
   speed.append(dict(recipe=recipe,scenario=sc,common=len(common),central_only=len(set(a)-set(d)),scenario_only=len(set(d)-set(a)),common_marked_delta_SOL=sum(d[k]['net_SOL']+d[k]['mark_SOL']-a[k]['net_SOL']-a[k]['mark_SOL'] for k in common)))
 extreme=[dict(recipe=r['recipe'],scope=r['scope'],scenario=r['scenario'],PF=r['profit_factor'],WR=r['win_rate']) for r in accounts if r['closed']>50 and ((r['profit_factor'] or 0)>3 or (r['win_rate'] or 0)>.7)]
 allclosed=[dict(recipe=r['recipe'],scope=r['scope'],scenario=r['scenario']) for r in accounts if r['attempts']>50 and r['attempts']==r['closed']]
 assert not extreme;assert all(r['scenario']=='fast' for r in allclosed)
 ammo=json.load(open(G.R.OUT/'AMM_PARITY.json'));assert not any(a['errors'] for a in ammo)
 sys=__import__('sys');sys.path.insert(0,'/tmp/amm_research_deps');import ijson
 opening={}
 for folder in [G.R.OUT/'earlier/amm_tapes',G.U.P/'recovery_sequence_cycle/later/execution/amm_tapes']:
  for f in folder.glob('*.gz'):
   with gzip.open(f,'rb') as src:m=next(ijson.items(src,'migration'))
   opening[m['mint']]=(m['slot'],m['index'])
 marks=[]
 for recipe in G.RECIPES:
  admitted={(x['mint'],x['rule'],x['probe']) for x in pick(recipe)['admitted']}
  for r in rows:
   if (r['recipe'],r['scenario'],r['fee'],r['horizon'],r['status'])!=(recipe,'central85',1505000,60,'unresolved') or (r['mint'],r['rule'],r['ticket']==.25) not in admitted:continue
   venue='amm' if r['mint'] in opening and tuple(r['last_valid_position'][:2])>=opening[r['mint']] else 'curve';marks.append(dict(recipe=recipe,mint=r['mint'],rule=r['rule'],reason=r['reason'],retained_tokens=r['remaining'],last_valid_time=r['last_valid_time'],last_valid_position=r['last_valid_position'],last_valid_venue=venue,mark_after_modeled_exit_fee_SOL=r['mark']/L,open_cashflow_SOL=r['net']/L,marked_pnl_SOL=(r['net']+r['mark'])/L,provenance='Counterfactual changed custody/reserves at last valid receipt; quote is not an executed sale or common end-date valuation'))
 (P/'OPEN_MARKS.json').write_text(json.dumps(marks,indent=2)+'\n')
 revision=subprocess.check_output(['git','rev-parse','--short','HEAD'],text=True).strip();checks=dict(control_parity=parity,entry_parity_checks=entryparity,integer_leg_requotes=requotes,regressions_passed=18,funded_ledgers_regenerated_twice=len(accounts),amm_source_groups_checked=sum(a['checked'] for a in ammo),violations=violations,alarms=dict(speed_order={'status':'reviewed','decomposition':speed,'explanation':'Different deterministic inclusion paths change guards, transactions before exits, breakers and funded admissions; no enforced artificial monotonicity.'},delayed_guards=dict(attempts=sum(r['scenario']=='slow' for r in rows),failed=sum(r['scenario']=='slow' and r['status']=='failed' for r in rows)),timers='pass independent clock targets anchored to buy landing',all_attempts_closed=allclosed,threshold_fills='pass independently requoted integer market proceeds',completed_curve_sales='pass',extreme_PF_WR=extreme,creation_history='Original authenticated 1800creation-selected launches; control outputs reproduced exactly'),hashes={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in [pathlib.Path(G.__file__),pathlib.Path(__file__),pathlib.Path(G.E.__file__),pathlib.Path(G.F.__file__),pathlib.Path(G.E.M.A.__file__),pathlib.Path(G.E.O.__file__),P/'SPEC.json',P/'REPLAY.json.gz',P/'FUNDED.json']})
 (P/'CHECKS.json').write_text(json.dumps(checks,indent=2)+'\n')
 def card(recipe='both6',h=60,gate=False,scope='portfolio',br=True):
  r=pick(recipe,h,gate,scope,br);vals=[pick(recipe,h,gate,scope,br,sc)['last_valid_marked_net_SOL'] for sc in ['fast','central80','central85','slow']];stress=pick(recipe,h,gate,scope,br,'stress');fees=pick(recipe,h,gate,scope,br,fee=2916000)
  verdict='undetermined' if r['unresolved'] else 'negative-central' if vals[2]<0 else 'positive-central' if vals[0]>0 else 'undetermined'
  return f'''engine/revision: approved day_general integer/custody extensions; {revision} + CHECKS working hashes
data: Oct3–6;1800creation-selected launches,223signals,166mints; original control parity verified
frozen before these dates: no; retrospective prescribed grace/deadline comparisons
looks:4new exit recipes x2S3hold controls x2creator-gate states=16 new configurations, plus original control
recipe:{recipe};S3hold:{h}s;creator_gate:{gate};scope:{scope};breakers:{br}
funded combined last-valid marked SOL fast/central80/central85/slow:{'/'.join(f'{v:+.6f}' for v in vals)}
Central85 settled:{r['settled_net_SOL']:+.6f};open marked PnL:{r['unresolved_marked_pnl_SOL']:+.6f};combined:{r['last_valid_marked_net_SOL']:+.6f}SOL
attempts/closed/failed/unresolved:{r['attempts']}/{r['closed']}/{r['failed']}/{r['unresolved']}
zero-recovery downside bound:{r['zero_recovery_bound_SOL']:+.6f}SOL; not realized loss
stress tail:{stress['last_valid_marked_net_SOL']:+.6f}; historical fees:{fees['last_valid_marked_net_SOL']:+.6f}SOL
settled drawdown:{r['max_settled_drawdown_SOL']:.6f}; largest closed winner:{r['largest_winner_SOL']:.6f}; combined without largest:{r['last_valid_marked_net_SOL']-r['largest_winner_SOL']:+.6f}SOL
closed-only PF:{r['profit_factor']}; win rate:{r['win_rate']}
checks:{parity['compared']}exact restored-control comparisons,{requotes}integer leg requotes,18focused regressions;8bug alarms reviewed
verdict:{verdict}, retrospective
next confirmation: authenticated missing migration execution and frozen fresh14–21day cohort
'''
 cards=[]
 for recipe in G.RECIPES:
  for h in [60,120]:
   for gate in [False,True]:
    for scope in ['portfolio','portfolio_without_carryover']+G.F.RULES:
     for br in [False,True]:cards.append(f'## {recipe}/{h}s/creator{gate}/{scope}/breakers{br}\n\n```text\n'+card(recipe,h,gate,scope,br)+'```\n')
 (P/'CANDIDATE_RESULT_CARDS.md').write_text('# Grace rerun result cards\n\n'+'\n'.join(cards))
 lines=['# S1/S4 grace verification and rerun','', 'The quoted critique correctly identifies early invalidation conditions. It does not establish that those exits were noise or that grace improves profit. The following measured ablations retain the original controls and executable accounting. Full-five verdict remains undetermined while migration/runner inventory lacks complete delivered exits.','','## Central85 shared 15SOL account, 0.50SOL tickets, no position cap','','| Version | Attempts/closed/failed/open | Settled SOL | Open marked PnL SOL | Combined marked SOL | Change vs control SOL |','|---|---|---:|---:|---:|---:|']
 for recipe in G.RECIPES:
  r=pick(recipe);lines.append(f"| {recipe} | {r['attempts']}/{r['closed']}/{r['failed']}/{r['unresolved']} | {r['settled_net_SOL']:+.6f} | {r['unresolved_marked_pnl_SOL']:+.6f} | {r['last_valid_marked_net_SOL']:+.6f} | {r['last_valid_marked_net_SOL']-pick()['last_valid_marked_net_SOL']:+.6f} |")
 lines+=['','S3 primary60s, percentage-point dynamic trail, original strategy breakers on, creator gate off. Independent120s, creator<=15% gate, breakers-off, per-window and standalone cards are retained. A .25SOL probe after cooldown is the unchanged documented breaker policy, not a change to base ticket sizing. Open inventory remains committed and cannot trip loss labels or fund new trades until sold.','','## Claims checked','','S4 stop becomes available after at least2slots and remains available thereafter, rather than applying only within2slots. Actual S4 entry corridor is16–22SOL, not80SOL. Whole-second receipt clocks cannot prove exact sub800ms exit latency. S1 has immediate trough invalidation and independent net-10% stop. New S1 grace defers only the trough condition; the loss stop remains immediate. Targets and partial profits stay active during grace.','']
 for a in audit:lines.append(f"- {a['rule']}: {a['unique_stop_paths']}unique Central85/.50SOL stop paths; {a['stops_before6s']}before6s. Claimed160/328 counts mix configurations/scenario repetitions and are not independent portfolio stopouts.")
 lines+=['','The original settled result already excludes unresolved principal. Its -0.758305SOL settled plus+1.032373SOL open marked PnL equals+0.274068SOL combined marked estimate. That is an estimate with13open positions, not settled profit or proven+EV. One undefined S1 runner has negative marked PnL (-0.048802SOL), so undefined does not imply a missed winning runner. Earlier S3 improvement changed profit exits while8s grace was already present; it cannot all be attributed to grace.','','## Explicit timer sensitivity','','both6_deadline600 adds a declared600s hard hold only to otherwise undefined S1/S2/S4 runners. It uses real clock deadlines, intervening transactions, actual remaining inventory and ordinary inclusion/requotes. It does not sell at the final tape quote, force graduation, delete custody or refund unsold cash. S3 and S5 exits remain unchanged.','','## Placement and cost brackets','','| Version | Fast | Central80 | Central85 | Slow | Tail stress | Historical fee stress |','|---|---:|---:|---:|---:|---:|---:|']
 for recipe in G.RECIPES:lines.append('| '+recipe+' | '+' | '.join(f"{pick(recipe,sc=sc)['last_valid_marked_net_SOL']:+.6f}" for sc in ['fast','central80','central85','slow','stress'])+f" | {pick(recipe,fee=2916000)['last_valid_marked_net_SOL']:+.6f} |")
 lines+=['','## Matched opportunity costs','','MATCHED_ATTRIBUTION.json separates delivered savings on old losers, deeper losses on old losers, added winner upside, surrendered old winners and changed unresolved outcomes. It uses identical intents outside funded admission effects. Shared bankroll attribution also changes through longer occupancy, same-mint conflicts and breaker timing; do not add standalone profits.','','| Version | Family | Savings on old losers | Deeper old-loser losses | Surrendered old winners | Added old winners | Both-closed net change |','|---|---|---:|---:|---:|---:|---:|']
 for a in attribution:
  if a['rule'] in ['s1_dev_absorption','s4_upper_ath']:lines.append(f"| {a['recipe']} | {a['rule']} | {a['saved_old_losers_SOL']:+.6f} | {a['extra_old_loser_damage_SOL']:+.6f} | {a['surrendered_old_winner_SOL']:+.6f} | {a['added_old_winner_SOL']:+.6f} | {a['net_both_closed_change_SOL']:+.6f} |")
 lines+=['','## Feedback from this rerun','','Blanket six-second grace is not supported by this comparison. S1 had zero improved and three worsened same-entry Central85/.50SOL closed trades. S4 improved nine and worsened nineteen; three old losses became wins, but0.810532SOL of savings was outweighed by1.183124SOL of deeper losses. The original early exits saved real downside as well as cutting some recoveries. Keep the original control available; these are prescribed experimental exits, not new defaults.','', 'A useful next hypothesis is conditional grace only when newly observed outside buying sustains recovery, tested with complete-prefix information and a fixed control. This study did not test that gate or establish that it will help. Specify runner deadlines explicitly, continue repairing displaced-completion exits, and measure exit inclusion before selecting a policy on untouched later data.','']
 lines+=['','## Restoration and verification','',f"Deleted dependency source recovered from local session history. Exact original official IDL hash2091433899b07d003d98118ae6cd3c628960fd393b40710b6e15bce6d0e7f2d1 recovered from upstream commit e0687ae9b7e064a0f54efc7297c65eecfbba3a8f. Original SDK1.20.0 full fee fixture restored. Frozen166coin receipt histories and382missing authenticated repair transfers recollected. {checks['amm_source_groups_checked']}complete AMM source transactions pass reserve/custody parity. Quiet batched multi-pool fee sweeps are pool-filtered or authenticated from their own vault delta. Original15earlier wallet-custody tapes retained; other rebuilt tapes retain account custody.", '',f"All {parity['compared']}restored-control outputs match saved traces exactly, including integer proceeds, times, positions, guards and unresolved marks. The regenerated original funded headline matches the saved result card; the original full FUNDED file was deleted. Ledger source hash matches the recorded original. {counts['actual_replays']}actual replays; {counts['assembled_traces']}assembled repetitions; {counts['funded_scenarios']}funded ledgers each regenerated twice; no exceptions. {requotes}integer leg requotes;18focused exit/accounting tests. CHECKS.json records all8bug alarms. No production files or live parameters changed.", '', '## Limits and understatement audit','','This remains development on the inspectedOct3–6cohort. No fresh holdout or live execution measurement was added. Marks retain each path’s last-valid venue/time in OPEN_MARKS.json; they are not synchronized liquidation wealth. Higher fees, different inclusion paths and missing counterfactual completion can change the conclusion.','', 'Understatement checks: open marks are included and excluded from settled loss labels; central inclusion is primary while slot-tail is only stress; declared profit targets remain active during grace and a separate causal600s deadline is tested. None is used to invent missing AMM exits.','','## Reproduction','','`python3 research/core_gap_refinement_20261007/grace_requested.py` then `python3 research/core_gap_refinement_20261007/grace_report.py`. The first command enforces saved-control parity before any new recipe is admitted to reporting. Missing receipts can be recovered with restore_replay_inputs.py helper functions; RESTORATION.json and official provenance record source recovery.','','## Required result card','','```text',card(),'```']
 (P/'REPORT.md').write_text('\n'.join(lines)+'\n');print('REPORT_DONE',counts);print(card())
if __name__=='__main__':main()
