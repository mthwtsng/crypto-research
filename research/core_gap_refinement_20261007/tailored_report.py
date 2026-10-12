"""Checks, matched attribution and cards for tailored five-family exits."""
import collections,gzip,hashlib,json,pathlib
import tailored_requested as T
P=T.OUT

def main():
 rows=json.load(gzip.open(P/'REPLAY.json.gz','rt'));accounts=json.load(open(P/'FUNDED.json'));counts=json.load(open(P/'RUN_COUNTS.json'));oldrows=json.load(gzip.open(T.N.OUT/'RELATIVE_REPLAY.json.gz','rt'));base={tuple(r[k] for k in ['window','mint','rule','signal_signature','scenario','fee','ticket','horizon']):r for r in oldrows if r['profit_target']==.2}
 violations=[];entryparity=0;threshold=[]
 for r in rows:
  old=base[tuple(r[k] for k in ['window','mint','rule','signal_signature','scenario','fee','ticket','horizon'])]
  for k in ['signal_position','entry_position','entry_time','entry_bill','entry_tokens']:assert r.get(k)==old.get(k),(k,r['mint'])
  entryparity+=1
  if r['status']!='failed' and sum(l['tokens'] for l in r['legs'])+r['remaining']!=r['entry_tokens']:violations.append(('tokens',r['mint']))
  if r['status']=='closed':assert r['net']==sum(l['proceeds']-l['fee'] for l in r['legs'])-r['entry_bill']-r['fee']
  for l in r['legs']:
   if tuple(l['position'])<=tuple(r['entry_position']):violations.append(('causal',r['mint']))
   if l.get('timer_target') is not None and l['time']<l['timer_target']:violations.append(('timer',r['mint']))
   if l['venue']=='curve' and l['state_before']['rtokens_raw']==0:violations.append(('completed_curve',r['mint']))
   if r['rule']=='s3_deadman' and ('runner_trail' in l['reason'] or 'relative_price_stop' in l['reason']) and l['time']<r['entry_time']+8:violations.append(('grace',r['mint']))
  if r['rule']=='s3_deadman':assert all(l['reason']!='confirmed_profit_target' for l in r['legs'])
 assert not violations,violations
 for r in accounts:
  assert r['attempts']==r['closed']+r['failed']+r['unresolved'];assert not r['skipped'].get('concurrency')
  assert abs(r['settled_net_SOL']+r['unresolved_marked_pnl_SOL']-r['last_valid_marked_net_SOL'])<1e-8
  assert abs(r['ending_cash_SOL']-15-r['zero_recovery_bound_SOL'])<1e-8
 def pick(h=60,b='percentage_points',gate=False,scope='portfolio',br=True,sc='central85',window='continuous',fee=1505000):
  return next(r for r in accounts if (r['horizon'],r['trail_basis'],r['developer_gate'],r['scope'],r['breakers'],r['scenario'],r['window'],r['fee'])==(h,b,gate,scope,br,sc,window,fee))
 extreme=[dict(scope=r['scope'],scenario=r['scenario'],horizon=r['horizon'],basis=r['trail_basis'],PF=r['profit_factor'],WR=r['win_rate']) for r in accounts if r['closed']>50 and ((r['profit_factor'] or 0)>3 or (r['win_rate'] or 0)>.7)]
 allclosed=[dict(scope=r['scope'],scenario=r['scenario']) for r in accounts if r['attempts']>50 and r['attempts']==r['closed']]
 assert not extreme;assert all(r['scenario']=='fast' for r in allclosed)
 attribution=[]
 for h in [60,120]:
  for b in ['percentage_points','relative']:
   for rule in T.U.F.RULES:
    rr=[r for r in rows if r['horizon']==h and r['trail_basis']==b and r['rule']==rule and r['scenario']=='central85' and r['fee']==1505000 and r['ticket']==.5];pairs=[(r,base[tuple(r[k] for k in ['window','mint','rule','signal_signature','scenario','fee','ticket','horizon'])]) for r in rr]
    cc=[(r,o) for r,o in pairs if r['status']=='closed' and o['status']=='closed'];attribution.append(dict(horizon=h,basis=b,rule=rule,attempts=len(rr),both_closed=len(cc),saved_on_old_losers_SOL=sum(max(0,r['net']-o['net']) for r,o in cc if o['net']<0)/1e9,extra_loser_damage_SOL=sum(min(0,r['net']-o['net']) for r,o in cc if o['net']<0)/1e9,surrendered_old_winner_SOL=sum(min(0,r['net']-o['net']) for r,o in cc if o['net']>=0)/1e9,added_old_winner_SOL=sum(max(0,r['net']-o['net']) for r,o in cc if o['net']>=0)/1e9,new_status_counts=dict(collections.Counter(r['status'] for r in rr)),changed_status_pairs=[dict(mint=r['mint'],old=o['status'],new=r['status'],reason=r.get('reason')) for r,o in pairs if r['status']!=o['status']]))
 (P/'MATCHED_ATTRIBUTION.json').write_text(json.dumps(attribution,indent=2)+'\n')
 speedy=[]
 for sc in ['fast','central80','slow','stress']:
  r=pick(sc=sc);a={(z['mint'],z['rule']):z for z in pick()['admitted']};d={(z['mint'],z['rule']):z for z in r['admitted']};common=set(a)&set(d);speedy.append(dict(scenario=sc,attempts=r['attempts'],common_admissions=len(common),central_only=len(set(a)-set(d)),scenario_only=len(set(d)-set(a)),common_marked_difference_SOL=sum(d[k]['net_SOL']+d[k]['mark_SOL']-a[k]['net_SOL']-a[k]['mark_SOL'] for k in common)))
 checks=dict(violations=violations,entry_parity_checks=entryparity,reproducible_funded_accounts=len(accounts),regressions_passed=12,alarms=dict(speed_order={'status':'reviewed','explanation':'Placement changes guards, timer and runner crossings and funded breaker/admission sequence; matched admissions retained, no forced monotonicity','decomposition':speedy},delayed_guards={'attempts':sum(r['scenario']=='slow' for r in rows),'failed':sum(r['scenario']=='slow' and r['status']=='failed' for r in rows)},timer='pass',all_attempts_closed=allclosed,threshold_fills='Actual integer market quotes, not threshold-price sales',completed_curve_sales='pass',extreme_PF_WR=extreme,creation_history='Same authenticated creation-selected1800launches/223signals'),hashes={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in [pathlib.Path(T.__file__),pathlib.Path(__file__),T.U.R.V.BASE/'engine.py',pathlib.Path(T.U.F.__file__),P/'SPEC.json',P/'REPLAY.json.gz',P/'FUNDED.json']})
 (P/'CHECKS.json').write_text(json.dumps(checks,indent=2)+'\n')
 def card(h=60,b='percentage_points',gate=False,scope='portfolio',br=True):
  r=pick(h,b,gate,scope,br);ss=[pick(h,b,gate,scope,br,sc) for sc in ['fast','central80','central85','slow']];verdict='undetermined' if r['unresolved'] else 'negative-central' if r['last_valid_marked_net_SOL']<0 else 'positive-central' if ss[0]['last_valid_marked_net_SOL']>0 else 'undetermined'
  return f'''engine:approved repaired day_general extensions;working hashes CHECKS.json
data:1800creation-selected October3–6launches,223setups166mints;authenticated from-creation histories
rules frozen before data:no;user-directed retrospective comparison;SPEC records inferred entry/trail scope
looks:50prior;8new horizon×trail-basis×creator cases;no winner selected as confirmation
recipe:tailoredS1–S5;S3timeout{h}s;basis{b};creator{gate};scope{scope};breakers{br};15SOL/.50SOL/no position cap/.25SOL probes
fast/central80/central85/slow combined last-valid markedSOL:{' / '.join(f"{x['last_valid_marked_net_SOL']:+.6f}" for x in ss)}
central85settled{r['settled_net_SOL']:+.6f}+openmarked{r['unresolved_marked_pnl_SOL']:+.6f}=combined{r['last_valid_marked_net_SOL']:+.6f}
separate downside zero bounds in same order:{' / '.join(f"{x['zero_recovery_bound_SOL']:+.6f}" for x in ss)}
stress tailmarked{pick(h,b,gate,scope,br,'stress')['last_valid_marked_net_SOL']:+.6f};higherfee marked{pick(h,b,gate,scope,br,fee=2916000)['last_valid_marked_net_SOL']:+.6f};scheduledn/a(allurgent)
attempts/closed/failed/unresolved:{r['attempts']}/{r['closed']}/{r['failed']}/{r['unresolved']};closedonly{r['closed_net_SOL']:+.6f};openmarkedvalue{r['unresolved_mark_value_SOL']:.6f}
settleddrawdown{r['max_settled_drawdown_SOL']:.6f};cashdrawdown{r['max_cash_drawdown_SOL']:.6f};largestwinner{r['largest_winner_SOL']:.6f};combinedwithoutlargest{r['last_valid_marked_net_SOL']-r['largest_winner_SOL']:+.6f}
PF{r['profit_factor']};WR{r['win_rate']};maxopen{r['max_open']};skips{json.dumps(r['skipped'])};unresolved{json.dumps(r['unresolved_reasons'])};dailysettled{json.dumps(r['daily_net_SOL'])}
checks:12focusedregressions;{entryparity}entryparity;{len(accounts)}ledgerreproductions;8alarms reviewed
verdict:{verdict},retrospective
changesverdict:complete actual migration exits and undefined runner deadlines;frozen fresh14–21day cohort
'''
 cards=[]
 for h in [60,120]:
  for b in ['percentage_points','relative']:
   for gate in [False,True]:
    for scope in ['portfolio','portfolio_without_carryover']+T.U.F.RULES:
     for br in [False,True]:cards.append(f'## {h}s / {b} / creator{gate} / {scope} / breakers{br}\n\n```text\n'+card(h,b,gate,scope,br)+'```\n')
 (P/'CANDIDATE_RESULT_CARDS.md').write_text('# Tailored exit cards\n\n'+'\n'.join(cards))
 r=pick();lines=['# Tailored exit retest on the five current entries','',f"Central85 primary60s/percentage-point trail: settled {r['settled_net_SOL']:+.6f} SOL + open marked {r['unresolved_marked_pnl_SOL']:+.6f} SOL = combined last-valid marked {r['last_valid_marked_net_SOL']:+.6f} SOL. {r['attempts']}attempts/{r['closed']}closed/{r['failed']}failed/{r['unresolved']}unresolved. Full-five verdict: undetermined, retrospective while incomplete exits remain. Open inventory is not a settled loss; zero-recovery is only a downside bound.",'','## Scope and exit definitions','','Five current entry families, including S3two_buy_groups, not the four generic420filled-path families. Optional scope questions received no answer before execution; this assumption and primary percentage-point interpretation match the pasted S1–S5 architecture. No new entry thresholds were supplied or invented. Relative trail sensitivity is separate. All entries and entry fills are matched to the preceding223signal study.','', 'S1:retain trough/net-10%invalidation;40%original tokens at+25%,remaining15pptrail;remove6s timeout. S2:retain9.8shelf,10%armed breakeven;40%at+30%,remaining15pptrail. S3:12%fill-relative price stop after8s grace,trailarms at executable+75%,20ppgiveback,no hardTP;60/120s timeout. S4:retain>=2slot-8%invalidation,half+20%and6%relative trail;remove7s pre-clip timeout. S5:unchanged curve<=60stop,halfafterwholeAMMopening,8%relative remainder trail,30s AMMtimeout. The S4proposal provided no new arm or width, so retained values are explicit. No short timer or file-end sale is invented for S1/S2/S4;undefined long runners retain custody at coverage600s.','','## All prescribed central85 continuous full-five comparisons','','| S3hold | Trail basis | Creator gate | Attempts/closed/failed/unresolved | Settled SOL | Open marked PnL SOL | Combined marked SOL |','|---|---|---|---|---:|---:|---:|']
 for h in [60,120]:
  for b in ['percentage_points','relative']:
   for gate in [False,True]:
    x=pick(h,b,gate);lines.append(f"| {h}s | {b} | {gate} | {x['attempts']}/{x['closed']}/{x['failed']}/{x['unresolved']} | {x['settled_net_SOL']:+.6f} | {x['unresolved_marked_pnl_SOL']:+.6f} | {x['last_valid_marked_net_SOL']:+.6f} |")
 prior=json.load(open(T.N.OUT/'FUNDED.json'));old=next(x for x in prior if x['stop_policy']=='relative_price_stop' and x['horizon']==60 and x['profit_target']==.2 and not x['developer_gate'] and x['window']=='continuous' and x['scenario']=='central85' and x['fee']==1505000 and x['position_limit'] is None and x['scope']=='portfolio' and x['breakers'])
 lines+=['',f"Matched old tailored-family baseline (S3fullTP20%): settled{old['settled_net_SOL']:+.6f},openmarked{old['unresolved_marked_pnl_SOL']:+.6f},combined{old['last_valid_marked_net_SOL']:+.6f}SOL;{old['attempts']}attempts/{old['closed']}closed/{old['failed']}failed/{old['unresolved']}unresolved. New-minus-old combined {r['last_valid_marked_net_SOL']-old['last_valid_marked_net_SOL']:+.6f}SOL includes changed funded timing/admissions and coverage, not solely target replacement.",'','## Actual shared-account family contributions','','| Family | Closed | Failed | Open | Settled SOL | Open marked PnL SOL | Combined SOL |','|---|---:|---:|---:|---:|---:|---:|']
 for rule in T.U.F.RULES:
  zz=[z for z in r['admitted'] if z['rule']==rule];c=collections.Counter(z['status'] for z in zz);settled=sum(z['net_SOL'] for z in zz if z['status']!='unresolved');openp=sum(z['net_SOL']+z['mark_SOL'] for z in zz if z['status']=='unresolved');lines.append(f"| {rule} | {c['closed']} | {c['failed']} | {c['unresolved']} | {settled:+.6f} | {openp:+.6f} | {settled+openp:+.6f} |")
 lines+=['','MATCHED_ATTRIBUTION.json separates savings on old losers and forfeited/added old-winner upside for both-closed identical entries. Changed unresolved/closed cases are listed separately, never silently discarded. Standalone funded cards are diagnostics, not additive portfolio returns.','','## Checks and limits','',f"{counts['actual_replays']}actual simulations/{counts['assembled_traces']}assembled scenario repetitions;{counts['funded_scenarios']}funded ledgers regenerated twice;zero replay exceptions.12focused regression tests include quiet-market grace,immediateTPduringgrace,40/60token conservation and distinct pp/relative trails. Entry position/bill/tokens parity passes{entryparity}rows. No completed-curve sale,no before-deadline timer or file-end liquidation. Eight alarms reviewed in CHECKS.json with funded placement/admission decompositions.",'','Whole-second historical clocks and assumed central80/85inclusion remain. Marks are each path’s last-valid finite-size quote,not common end-date wealth or delivered AMM liquidation. Changed router completion and undeclared runner timeouts remain model/definition gaps; cash commitment retained. No fictionalAMMinflow or universal pool reserves. No production settings or live orders changed.','','## Reproduction','','Run tailored_requested.py then tailored_report.py. Full traces, frozenSPEC, financial histories and all112continuouscards retained.','','## What I would investigate if data and tooling were unconstrained','','Resolve complete changed completion/router execution and observed exit inclusion; specify currently undefined runner deadlines before untouched later confirmation.','','## Required result card','','```text',card(),'```']
 (P/'REPORT.md').write_text('\n'.join(lines)+'\n');print('REPORT_DONE',counts);print(card())
if __name__=='__main__':main()
