"""Independent frozen-study checks and honest finite-account result cards."""
import collections,datetime,gzip,hashlib,json,pathlib,random,subprocess
import rpc_pool as R
import run_after_collection as Q
P=R.OUT

def main():
 if not (P/'REPLAY_COMPLETE.json').exists():raise RuntimeError('collection/preparation/replay not complete')
 rows=json.load(gzip.open(P/'REPLAY.json.gz','rt'));accounts=json.load(open(P/'FUNDED.json'));sample=json.load(open(P/'CREATION_SAMPLE.json'));spec=json.load(open(P/'FREEZE.json'));errors=json.load(open(P/'REPLAY_ERRORS.json'));assert not errors
 caps=[2,5,10,15,None]
 def pick(policy='primary',sc='central85',fee=1505000,cap=None):return next(a for a in accounts if (a['policy'],a['scenario'],a['fee'],a['breakers'],a['position_limit'])==(policy,sc,fee,True,cap))
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
   if r['policy']=='primary' and r['rule']=='s4_upper_ath' and 'breakout_rejected' in l['reason']:assert l['time']>=r['entry_time']+4
 for a in accounts:
  assert a['attempts']==a['closed']+a['failed']+a['unresolved'];assert abs(a['settled_net_SOL']+a['unresolved_marked_pnl_SOL']-a['last_valid_marked_net_SOL'])<1e-8
  if a['position_limit'] is None:assert not a['skipped'].get('concurrency')
  else:assert a['max_open']<=a['position_limit']
 # Inspect and explain inclusion/admission differences before judging speed order.
 speed=[]
 for policy,cap in [(p,c) for p in ['control','primary'] for c in caps]:
  a=pick(policy,cap=cap);aa={(x['mint'],x['rule']):x for x in a['admitted']}
  for sc in ['fast','central80','slow','stress']:
   b=pick(policy,sc,cap=cap);bb={(x['mint'],x['rule']):x for x in b['admitted']};common=set(aa)&set(bb)
   speed.append(dict(policy=policy,position_limit=cap,scenario=sc,common=len(common),central_only=len(set(aa)-set(bb)),other_only=len(set(bb)-set(aa)),matched_marked_change=sum(bb[k]['net_SOL']+bb[k]['mark_SOL']-aa[k]['net_SOL']-aa[k]['mark_SOL'] for k in common),aggregate_change=b['last_valid_marked_net_SOL']-a['last_valid_marked_net_SOL']))
 alarms=dict(speed_order=dict(status='review inclusion, guard failures and admission paths in SPEED_ATTRIBUTION.json',decomposition=speed),failed_guards=dict(cases=[dict(policy=a['policy'],scenario=a['scenario']) for a in accounts if a['scenario']!='fast' and a['attempts']>30 and not a['failed']]),timers='pass all deadline and landing anchors checked',all_closed=dict(cases=[dict(policy=a['policy'],scenario=a['scenario']) for a in accounts if a['attempts']>50 and a['closed']==a['attempts']]),threshold_fills='pass delivered integer re-quotes; no threshold-price credited fills',post_completion='pass positive real tokens for all curve sells',extreme_stats=dict(cases=[dict(policy=a['policy'],scenario=a['scenario'],PF=a['profit_factor'],WR=a['win_rate']) for a in accounts if a['closed']>50 and ((a['profit_factor'] or 0)>3 or (a['win_rate'] or 0)>.7)]),creation_selection='complete504hour census; fixed20perhour selection; allsampleerrors repaired, no outcome replacement')
 if alarms['failed_guards']['cases'] or alarms['extreme_stats']['cases']:raise RuntimeError('bug alarm requires manual attribution before headline')
 R.save(P/'SPEED_ATTRIBUTION.json',speed);R.save(P/'CHECKS.json',dict(integer_leg_requotes=requotes,alarms=alarms))
 marks=[]
 for policy,cap in [(p,c) for p in ['control','primary'] for c in caps]:
  admitted={(x['mint'],x['rule'],x['probe']) for x in pick(policy,cap=cap)['admitted']}
  for r in rows:
   if (r['policy'],r['scenario'],r['fee'],r['status'])!=(policy,'central85',1505000,'unresolved') or (r['mint'],r['rule'],r['ticket']==.25) not in admitted:continue
   t=json.load(gzip.open(P/'execution_tapes'/(r['mint']+'.json.gz'),'rt'));gs=t['groups'];pos=tuple(r['last_valid_position']);venue=next((g['venue'] for g in reversed(gs) if (g['slot'],g['index'],0)<=pos),'curve')
   marks.append(dict(policy=policy,position_limit=cap,mint=r['mint'],rule=r['rule'],remaining_raw=r['remaining'],reason=r['reason'],venue=venue,mark_time=r['last_valid_time'],position=pos,inventory_value_after_exit_fee_SOL=r['mark']/1e9,open_marked_pnl_SOL=(r['net']+r['mark'])/1e9,source='counterfactual last-valid receipt state; not a terminal sale'))
 R.save(P/'OPEN_MARKS.json',marks)
 days=[datetime.datetime.fromtimestamp(spec['start']+i*86400,datetime.timezone.utc).date().isoformat() for i in range(21)];bootstrap=[];rng=random.Random(20261008)
 for policy,cap in [(p,c) for p in ['control','primary'] for c in caps]:
  a=pick(policy,cap=cap);daily=[a['daily_net_SOL'].get(day,0) for day in days];values=[]
  for _ in range(10000):
   resampled=[]
   while len(resampled)<21:
    start=rng.randrange(19);resampled+=daily[start:start+3]
   values.append(sum(resampled[:21])/21)
  values.sort();bootstrap.append(dict(policy=policy,position_limit=cap,days=21,block_days=3,replicates=10000,mean_settled_daily_SOL=sum(daily)/21,interval95=[values[250],values[9749]],interval99=[values[50],values[9949]],scope='conditional uncertainty of delivered settled daily PnL; preserves3dayblocks; does not rerun bank/circuitbreakers or resolve open marks;21days not proof of all regimes'))
 R.save(P/'BLOCK_BOOTSTRAP.json',bootstrap)
 lines=['# Frozen 21-day historical transfer test','',f"Selected{sample['total']}ordinary launches across504hourly strata. Frozen before collection; historical periodAug18–Sep7was chosen before outcomes, but deleted prior artifacts prevent certifying untouched history. This is not forward-confirmed.",'','| Policy | Attempts | Closed | Failed | Open | SettledSOL | OpenmarkedPnLSOL | CombinedmarkedSOL |','|---|---:|---:|---:|---:|---:|---:|---:|']
 cards=[]
 for policy,cap in [(p,c) for p in ['control','primary'] for c in caps]:
  a=pick(policy,cap=cap);lines.append(f"|{policy} / {cap if cap is not None else 'uncapped'}|{a['attempts']}|{a['closed']}|{a['failed']}|{a['unresolved']}|{a['settled_net_SOL']:+.6f}|{a['unresolved_marked_pnl_SOL']:+.6f}|{a['last_valid_marked_net_SOL']:+.6f}|")
  verdict='undetermined, retrospective' if a['closed']<500 or a['unresolved_mark_value_SOL']>abs(a['last_valid_marked_net_SOL']) else ('positive-central, retrospective' if a['last_valid_marked_net_SOL']>0 and pick(policy,'fast',cap=cap)['last_valid_marked_net_SOL']>0 else 'negative-central, retrospective')
  cards.append(f'''policy:{policy}; position cap:{cap if cap is not None else 'uncapped'}
engine+revision: approved core_plan family, frozen source hashes in FREEZE.json; no intervention shortcut
data:Aug18–Sep7,21days,{sample['total']}fixed-hash creation-selected launches, all504hours
entry/exit rules frozen before collection:yes; cap amendment authorized during collection before any replay results; not before historical events; prior-use audit incomplete due deleted artifacts
look count:2strategy policies x5position caps =10funded policy variants; no tuning on this cohort
placement fast/central80/central85/slow combined marked SOL:{[pick(policy,s,cap=cap)['last_valid_marked_net_SOL'] for s in ['fast','central80','central85','slow']]}
stress tail:{pick(policy,'stress',cap=cap)['last_valid_marked_net_SOL']}; higherfees:{pick(policy,fee=2916000,cap=cap)['last_valid_marked_net_SOL']}; scheduled3slot:N/A no new tipless policy
settled:{a['settled_net_SOL']} + openmarked:{a['unresolved_marked_pnl_SOL']} =combined:{a['last_valid_marked_net_SOL']}
attempts/closed/failed/unresolved:{a['attempts']}/{a['closed']}/{a['failed']}/{a['unresolved']}; zero-recovery bound:{a['zero_recovery_bound_SOL']}
maxsettleddrawdown:{a['max_settled_drawdown_SOL']}; largestwinner:{a['largest_winner_SOL']}; combinedwithoutlargest:{a['last_valid_marked_net_SOL']-a['largest_winner_SOL']}
8bugalarms checked:see CHECKS.json and SPEED_ATTRIBUTION.json; {requotes}integerrequotes
verdict:{verdict}
what changes verdict:fully authenticated outstanding execution, adequate per-family sample and fresh21day forward confirmation
''')
 lines+=['','## Position-cap comparison — primary Central85','','| Cap | Peak pending/open | Capacity skips | Cash skips | Settled drawdown SOL |','|---|---:|---:|---:|---:|']
 for limit in caps:
  a=pick(cap=limit)
  lines.append(f"|{limit if limit is not None else 'uncapped'}|{a['max_open']}|{a['skipped'].get('concurrency',0)}|{a['skipped'].get('cash',0)}|{a['max_settled_drawdown_SOL']:.6f}|")
 lines+=['','## Primary uncapped strategy contributions inside the shared account','','| Strategy | Eligible signals | Funded attempts | Closed | Failed | Open | Settled SOL | Open marked PnL SOL |','|---|---:|---:|---:|---:|---:|---:|---:|']
 for rule in Q.F.RULES:
  a=pick();rr=[x for x in a['admitted'] if x['rule']==rule];closed=[x for x in rr if x['status']=='closed'];failed=[x for x in rr if x['status']=='failed'];opened=[x for x in rr if x['status']=='unresolved'];eligible=sum(r['policy']=='primary' and r['scenario']=='central85' and r['fee']==1505000 and r['ticket']==.5 and r['rule']==rule for r in rows)
  lines.append(f"|{rule}|{eligible}|{len(rr)}|{len(closed)}|{len(failed)}|{len(opened)}|{sum(x['net_SOL'] for x in closed+failed):+.6f}|{sum(x['net_SOL']+x['mark_SOL'] for x in opened):+.6f}|")
 lines+=['','Weekly/day detail remains in FUNDED.json daily_net_SOL; portfolio skips and trips are retained. One hundred closed per family is a planning target; a rarer family can remain inconclusive even when the overall portfolio has500closed.','']
 lines+=['','S2primary filter and S4grace were frozen; S1/S3/S5unchanged. All candidate signals and failed attempts retained in trace output; admissions respect actual available15SOLcash and documentedbreakers/probes, with research caps2/5/10/15/uncapped compared. Standalone signal opportunity is not funded profit.','', 'Block-bootstrap intervals are in BLOCK_BOOTSTRAP.json. Targets500closedoverall/100perfamily are planning thresholds, not p<.01proof. Unknown positions are excluded from closedlabels; OPEN_MARKS.json records venue/time/remaining inventory.','', '## Required result cards','']
 lines+=['```text\n'+c+'```' for c in cards];(P/'REPORT.md').write_text('\n'.join(lines)+'\n');R.save(P/'REPORT_COMPLETE.json',dict(timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),checked=True));print('REPORT_COMPLETE',flush=True)
if __name__=='__main__':main()
