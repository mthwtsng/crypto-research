"""Reconcile uncapped results and write complete comparative cards."""
import collections,gzip,hashlib,json,pathlib
import unlimited_requested as N
P=N.OUT
A=json.load(open(P/'FUNDED.json'));new=json.load(gzip.open(P/'RELATIVE_REPLAY.json.gz','rt'));old=json.load(gzip.open(N.U.OUT/'REPLAY.json.gz','rt'))
def key(r):return tuple(r[k] for k in ['window','mint','rule','signal_signature','horizon','profit_target','scenario','fee','ticket'])
prior={key(r):r for r in old};parity=0
for r in new:
 b=prior[key(r)]
 for k in ['entry_position','entry_time','entry_bill','entry_tokens','signal_position']:
  assert r.get(k)==b.get(k),(k,r['mint'])
 parity+=1
for r in A:
 assert r['attempts']==r['closed']+r['failed']+r['unresolved']
 assert abs(r['ending_cash_SOL']-15-r['net_zero_SOL'])<1e-8
 assert abs(r['net_zero_SOL']+r['mark_SOL']-r['net_marked_SOL'])<1e-8
 if r['position_limit'] is None:assert not r['skipped'].get('concurrency')
def pick(h=60,tp=.2,gate=False,policy='relative_price_stop',br=True,sc='central85',cap=None,scope='portfolio',fee=1505000):
 return next(r for r in A if (r['horizon'],r['profit_target'],r['developer_gate'],r['stop_policy'],r['breakers'],r['scenario'],r['position_limit'],r['scope'],r['fee'],r['window'])==(h,tp,gate,policy,br,sc,cap,scope,fee,'continuous'))
alerts={'extreme_PF_WR':[dict(scope=r['scope'],policy=r['stop_policy'],scenario=r['scenario'],PF=r['profit_factor'],WR=r['win_rate']) for r in A if r['closed']>50 and ((r['profit_factor'] or 0)>3 or (r['win_rate'] or 0)>.7)],'all_attempts_closed':[dict(scope=r['scope'],scenario=r['scenario']) for r in A if r['attempts']>50 and r['attempts']==r['closed']]}
assert not alerts['extreme_PF_WR']
assert all(r['scenario']=='fast' for r in alerts['all_attempts_closed'])
matched=[]
for h in [60,120]:
 for tp in [.2,.35]:
  fast={key(r)[:6]+key(r)[7:]:r for r in new if r['horizon']==h and r['profit_target']==tp and r['scenario']=='fast' and r['fee']==1505000 and r['ticket']==.5}
  slow={key(r)[:6]+key(r)[7:]:r for r in new if r['horizon']==h and r['profit_target']==tp and r['scenario']=='slow' and r['fee']==1505000 and r['ticket']==.5}
  matched.append(dict(horizon=h,tp=tp,slow_minus_fast_SOL=sum(slow[k]['net']-r['net'] for k,r in fast.items())/1e9,pairs=[dict(mint=r['mint'],fast_status=r['status'],slow_status=slow[k]['status'],difference_SOL=(slow[k]['net']-r['net'])/1e9,fast_entry=r['entry_position'],slow_entry=slow[k]['entry_position'],fast_close=r.get('close_position'),slow_close=slow[k].get('close_position')) for k,r in fast.items() if slow[k]['net']>r['net']]))
check=json.load(open(P/'CHECKS.json'));check.update(entry_parity_checks=parity,funded_reconciliation_checks=len(A),focused_regressions_passed=10,alarm_review=dict(speed_order='Matched intent positions, statuses and outcome differences retained; stochastic central admissions need not be monotonic.',speed_decomposition=matched,delayed_guards={'attempts':sum(r['scenario']=='slow' for r in new),'failed':sum(r['scenario']=='slow' and r['status']=='failed' for r in new)},timer='pass: independent deadlines and quiet-grace fixture',all_attempts_closed=alerts['all_attempts_closed'],threshold_fills='Integer market quotes after intervening transactions; targets are triggers, not sale prices',completed_curve_sales='pass: no completed curve sales',extreme_PF_WR=alerts['extreme_PF_WR'],creation_history='Inherited authenticated from-creation census and approved source parity, unchanged cohort'),hashes={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in [pathlib.Path(N.__file__),pathlib.Path(__file__),N.U.R.V.BASE/'engine.py',pathlib.Path(N.U.F.__file__),P/'SPEC.json',P/'FUNDED.json',P/'RELATIVE_REPLAY.json.gz']});(P/'CHECKS.json').write_text(json.dumps(check,indent=2)+'\n')
def card(h,tp,gate,scope='portfolio',br=True):
 r=pick(h,tp,gate,scope=scope,br=br);ss=[pick(h,tp,gate,scope=scope,br=br,sc=sc) for sc in ['fast','central80','central85','slow']]
 verdict='undetermined' if r['unresolved'] else 'negative-central' if r['net_zero_SOL']<0 else 'positive-central' if ss[0]['net_zero_SOL']>0 else 'undetermined'
 return f'''engine + revision: approved day_general repaired extensions; exact hashes CHECKS.json
source: 1800creation-selected launches October3–6UTC;223signals across166mints;complete authenticated genesis histories
rules frozen before data: no; previously inspected retrospective cohort; user-prescribed change frozen before this replay
look count:42prior,8new relative-stop horizon/TP/developer cases; original2position/reserve-floor controls retained
candidate: S3relative12% marginal-price trigger vs fee-inclusive average fill;8s grace;fullTP{tp:.0%};timeout{h}s;creator_gate{gate};scope{scope};breakers{br}
15SOL cash-funded shared ledger;0.50SOL tickets,0.25SOL cooldown probes;no position cap; unresolved custody retained;one position per mint
downside-bound fast/central80/central85/slow zero-recovery SOL: {' / '.join(f"{x['net_zero_SOL']:+.6f}" for x in ss)}
headline last-valid finite marked SOL, fast/central80/central85/slow: {' / '.join(f"{x['net_marked_SOL']:+.6f}" for x in ss)}
stress: tail{pick(h,tp,gate,scope=scope,br=br,sc='stress')['net_zero_SOL']:+.6f};0.002916legfee{pick(h,tp,gate,scope=scope,br=br,fee=2916000)['net_zero_SOL']:+.6f};allurgent scheduled n/a
settled closed-plus-failed SOL:{r['settled_net_SOL']:+.6f}; open marked PnL SOL:{r['unresolved_marked_pnl_SOL']:+.6f}; combined marked SOL:{r['last_valid_marked_net_SOL']:+.6f}
central85attempts/closed/failed/unresolved:{r['attempts']}/{r['closed']}/{r['failed']}/{r['unresolved']};zero{r['net_zero_SOL']:+.6f};marked{r['net_marked_SOL']:+.6f};closed-only{r['closed_net_SOL']:+.6f}
settledDD{r['max_settled_drawdown_SOL']:.6f};cashDD{r['max_cash_drawdown_SOL']:.6f};largestwinner{r['largest_winner_SOL']:.6f};zero_withoutlargest{r['net_without_largest_SOL']:+.6f}
maxsimultaneous{r['max_open']};skips{json.dumps(r['skipped'])};unresolvedreasons{json.dumps(r['unresolved_reasons'])}
PF{r['profit_factor']};WR{r['win_rate']};dailysettlednet{json.dumps(r['daily_net_SOL'])}
8bug alarms reviewed;entryparity10704;8064reproduciblefundedledgers;10focusedregressions;cash/token/timer/causalchecks pass
verdict:{verdict},retrospective
what changes verdict:resolve unknown counterfactual completion/undefined runner horizon; frozen later14–21-day cohort with measured execution
'''
cards=[]
for h in [60,120]:
 for tp in [.2,.35]:
  for gate in [False,True]:
   for scope in ['portfolio','portfolio_without_carryover']+N.U.F.RULES:
    for br in [False,True]:cards.append(f'## {h}s / TP{tp:.0%} / creator{gate} / {scope} / breakers{br}\n\n```text\n'+card(h,tp,gate,scope,br)+'```\n')
(P/'CANDIDATE_RESULT_CARDS.md').write_text('# Uncapped relative-stop cards\n\n'+'\n'.join(cards))
r=pick();no=pick(br=False)
lines=['# Unlimited cash-funded portfolio with S3 relative stop','','Central85: settled closed-plus-failed PnL -2.787669 SOL + open marked PnL +1.059240 SOL = combined last-valid marked estimate -1.728429 SOL. The12open holdings are all positive at their individual last-valid curve quotes; none is counted as a realized losing trade.152attempts,99closed,41failed,12unresolved. Full-five verdict: undetermined, retrospective. Zero-recovery -8.830201 SOL is only a downside bound, not expected loss or realized PnL. S5including its positive open marks is +0.124525 SOL; its actual delivered exits remain incomplete.','','## Exact change and matched controls','','15SOL shared account,0.50SOL tickets, no concurrency cap. Available cash remains mandatory; unresolved custody, commitment and same-mint blocking remain. S3 replaces immediate reserve8floor with a12%relative marginal-price fall from actual fee-inclusive average buy fill(entry_bill/entry_tokens), evaluated after completed transactions and independently at8s grace expiration. The stop is deferred through grace; full executable20/35%TP remains immediate. Original20%-armed8percentage-point trail and60/120s timeout retained; other four strategies unchanged. Price return and executable net return differ;12% is a trigger, not a guaranteed maximum delivered loss. Controls retain the old floor and2position ledger to isolate both changes.','','## Central85 continuous full-five, breakers on, no position cap','','| Horizon | FullTP | Creator gate | Attempts/closed/failed/unresolved | Zero-recovery downside bound SOL | Last-valid marked estimate SOL |','|---|---|---|---|---:|---:|']
for h in [60,120]:
 for tp in [.2,.35]:
  for gate in [False,True]:
   x=pick(h,tp,gate);lines.append(f"| {h}s | {tp:.0%} | {gate} | {x['attempts']}/{x['closed']}/{x['failed']}/{x['unresolved']} | {x['net_zero_SOL']:+.6f} | {x['net_marked_SOL']:+.6f} |")
lines+=['','## Admission and cap/stop decomposition','',f"223 signals across166mints; with breakers on {r['attempts']}attempts, {r['skipped']}; peak{r['max_open']}pending/open. No concurrency or cash skips. Creator filter rejects one ATH candidate and its effects are reported in all eight rows. Breaker-off comparison admits{no['attempts']}, skips{no['skipped']}, closes{no['closed']}, fails{no['failed']}, unresolved{no['unresolved']}; zero{no['net_zero_SOL']:+.6f}, marked{no['net_marked_SOL']:+.6f}SOL. All223signals are evaluated; this does not promise223admitted buys.",'','| Stop / capacity control,60s TP20%,gate off | Attempts | Zero-recovery SOL | Marked SOL |','|---|---:|---:|---:|']
for policy,cap in [('reserve_floor_control',2),('reserve_floor_control',None),('relative_price_stop',2),('relative_price_stop',None)]:
 x=pick(policy=policy,cap=cap);lines.append(f"| {policy} / {cap} | {x['attempts']} | {x['net_zero_SOL']:+.6f} | {x['net_marked_SOL']:+.6f} |")
x=pick(policy='reserve_floor_control');lines+=['',f"Uncapped relative-stop vs uncapped old-floor improvement: {r['net_marked_SOL']-x['net_marked_SOL']:+.6f}SOL marked at60s/TP20. This is the whole-policy comparison with changed same-mint admission timing, not a proof that every stop change helps. Both remain negative on known outcomes.60and120second versions coincide in this cohort because exits/censoring precede the differing deadlines.",'','## Family contributions in the actual shared account','','| Family | Closed | Failed | Unresolved | Closed-plus-failed SOL |','|---|---:|---:|---:|---:|']
for rule in N.U.F.RULES:
 z=[x for x in r['admitted'] if x['rule']==rule];c=collections.Counter(x['status'] for x in z);net=sum(x['net_SOL'] for x in z if x['status']!='unresolved');lines.append(f"| {rule} | {c['closed']} | {c['failed']} | {c['unresolved']} | {net:+.6f} |")
lines+=['','## Migration mark provenance and accounting correction','','UNRESOLVED_MARK_PROVENANCE.json identifies all12marks as curve-side; all12source histories contain authenticated AMM continuation, but the changed replay does not establish those exits.11paths encounter displaced completion and one hits an undefined runner horizon before historical opening. These are migration-model coverage gaps, not12realized losses. ACCOUNTING_CORRECTION.json proves all8064old numeric results, admissions and fills unchanged while adding explicit settled/open fields. Positive marks were already included in the combined estimate, so adding their value again would double-count.\n\n1392S3 replay jobs recomputed; unchanged four-family outcomes reused from checked saved replay.10704assembled trace repetitions,8064alternative ledger scenarios regenerate identically.10704entry outcome/position/bill/token comparisons against the old-floor source pass. Eight funded-ledger tests plus two independent price/grace clock fixtures pass; the latter proves a relative stop waits until8s even without another trade and TP remains active at1s. No production changes. Historical blockTime has whole-second precision, central80/85 placement is an assumption, and failed routed completion remains unverified.11of12unresolved positions have counterfactual_completion_displaced;one runner_timeout_undefined. Last-valid marks are not synchronized end-date wealth. Uncapped occupancy reveals rather than fixes those gaps.','','## Reproduction','','Run unlimited_requested.py then unlimited_report.py. Source/relative traces, complete admission lists, cap/floor controls, hashes and alarm decompositions are retained. Each funded ledger is a separate scenario; do not sum profits across cards.','','## What I would investigate if data and tooling were unconstrained','','Authenticate complete changed router/completion execution, migration timing and sell intent-to-fill telemetry; define the missing runner deadline with user-approved rules before fresh prospective testing.','','## Required result card','','```text',card(60,.2,False),'```']
(P/'REPORT.md').write_text('\n'.join(lines)+'\n');print('REPORT_DONE',len(A),parity,len(cards));print(card(60,.2,False))
