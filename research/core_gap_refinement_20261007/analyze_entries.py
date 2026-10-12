"""Opportunity denominators, causal entry features and exit-gap diagnostics."""
import collections,datetime,gzip,json,pathlib,pickle,statistics,sys
P=pathlib.Path(__file__).resolve().parent;ROOT=P.parents[1];BASE=P.parent/'core_plan_audit_20261007'
sys.path.insert(0,str(BASE));import signals as S

def features(t,s):
 gs=t['groups'];i=next(i for i,g in enumerate(gs) if g['signature']==s['signal_signature']);g=gs[i];dev=t['creator'];recent=[e for z in gs[:i+1] if z['slot']>=s['slot']-3 for e in z['events'] if e['user']!=dev];buys=[e for e in recent if e['buy']];sells=[e for e in recent if not e['buy']];h=S.build.inventory(gs[:i+1]);whales=[e for e in g['events'] if not e['buy'] and e['user']!=dev and e['sol_raw']>=1500000000]
 sold=collections.Counter()
 for e in g['events']:
  if not e['buy']:sold[e['user']]+=e['tokens_raw']
 whale_remaining=[h.get(e['user'],0)/(h.get(e['user'],0)+sold[e['user']]) for e in whales if h.get(e['user'],0)+sold[e['user']]>0]
 return dict(mint=s['mint'],rule=s['rule'],reserve=s['reserve'],age=s['age_seconds'],recent_buyers=len({e['user'] for e in buys}),recent_buy_SOL=sum(e['sol_raw'] for e in buys)/1e9,recent_sell_SOL=sum(e['sol_raw'] for e in sells)/1e9,whale_remaining_max=max(whale_remaining,default=None))

def main():
 rows=json.load(gzip.open(P/'ENTRY_TRAJECTORIES.json.gz','rt'));baseline=json.load(gzip.open(BASE/'REPLAY_RESULTS.json.gz','rt'));tapes=pickle.load(gzip.open(ROOT/'research/day_general_20261004/TAPES.pkl.gz','rb'));by={t['mint']:t for t in tapes};ss=json.loads((BASE/'SIGNALS.json').read_text());ff={(s['mint'],s['rule']):features(by[s['mint']],s) for s in ss};summaries=[];gaps=[]
 for sc in ['fast','central80','central85','slow']:
  for rule in sorted({r['rule'] for r in rows}):
   rr=[r for r in rows if r['scenario']==sc and r['rule']==rule];filled=[r for r in rr if r['status']!='failed'];hh={}
   for horizon in [2,5,10,20,30,60,180,600]:
    points=[r['horizons'][str(horizon)] for r in filled];known=[h for h in points if h['complete']];vals=[h['net_return'] for h in known if h['net_return'] is not None]
    hh[str(horizon)]=dict(known=len(known),censored=len(points)-len(known),currently_quotable=len(vals),median_net_return=statistics.median(vals) if vals else None,mean_net_return=statistics.mean(vals) if vals else None,net_positive_at_horizon=sum(v>0 for v in vals),net_hit_counts={str(v):sum(h['net_hits'][str(v)] is not None for h in known) for v in [.02,.05,.10,.20,.25]},spot_hit5=sum(h['spot_MFE'] is not None and h['spot_MFE']>=.05 for h in known))
   summaries.append(dict(rule=rule,scenario=sc,attempts=len(rr),fills=len(filled),failed=len(rr)-len(filled),horizons=hh,gap_reasons=dict(collections.Counter(r.get('reason') for r in filled if r['status']=='censored'))))
 for r in rows:
  if r['scenario']!='central85' or r['status']=='failed':continue
  b=next(b for b in baseline if b['mint']==r['mint'] and b['rule']==r['rule'] and b['scenario']=='central85' and b['endpoint']=='lower' and b['ticket']==.5 and b['fee']==1505000);close=b.get('close_time');before=[p['net_return'] for p in r['points'] if close is not None and p['time']<close and p['net_return'] is not None];after=[p['net_return'] for p in r['points'] if close is not None and close<=p['time']<r['entry_time']+60 and p['net_return'] is not None]
  gaps.append(dict(**ff[(r['mint'],r['rule'])],baseline_status=b['status'],baseline_net_SOL=b['net']/1e9,baseline_exit=b['legs'][-1]['reason'] if b['legs'] else None,baseline_hold=close-r['entry_time'] if close else None,neutral_MFE_before_exit=max(before,default=None),neutral_MFE_after_exit_until60=max(after,default=None),horizon10=r['horizons']['10'],horizon20=r['horizons']['20'],horizon60=r['horizons']['60']))
 (P/'ENTRY_SUMMARY.json').write_text(json.dumps(summaries,indent=2)+'\n');(P/'ENTRY_EXIT_GAPS.json').write_text(json.dumps(gaps,indent=2)+'\n')
 lines=['# Entry-only patterns before exit refinement','','Retrospective October 3–4, 600 creation-selected launches. 76 unchanged signals; no sell recipe used in these trajectories. A favorable quote/peak is an opportunity diagnostic, not realized profit. Horizon states use all complete groups strictly before the deadline; equal-second intrablock timing is not inferred. Failed attempts and incomplete horizons remain explicit.','','| Setup | Attempts / fills | Executable +5% by 10s | By 20s | By 60s | Spot +5% by 20s | Median executable return at 20s |','|---|---|---|---|---|---|---|']
 for s in [s for s in summaries if s['scenario']=='central85']:
  h=s['horizons'];fmt=lambda v:f"{h[str(v)]['net_hit_counts']['0.05']}/{h[str(v)]['known']}";med=h['20']['median_net_return'];lines.append(f"| {s['rule']} | {s['attempts']} / {s['fills']} | {fmt(10)} | {fmt(20)} | {fmt(60)} | {h['20']['spot_hit5']}/{h['20']['known']} | {med:+.1%} |" if med is not None else f"| {s['rule']} | {s['attempts']} / {s['fills']} | {fmt(10)} | {fmt(20)} | {fmt(60)} | unknown | unknown |")
 lines+=['','Interpretation:','- Dev absorption: fewer than half the fills offer +5% within its short exit window; selection/recovery quality needs testing, not just a higher target.','- Survival shelf: follow-through is slower—8/11 reach executable +5% by60s. Existing staged exits already show positive pilot cash; preserve this control.','- Dead-man: only6/15 offer +5% by10s; losing fills continue falling. Test recovery confirmation separately from earlier stagnation exits.','- Upper ATH:11/16 reach executable +5% by20s and12/16 by60s, versus its7–12s timeout and early8% stop. This is the clearest exit-gap candidate, though fees and failed guards still matter.','- Carryover: whole-transaction completion changes censor many paths. Early known quote trajectory can be measured; postmigration profitability cannot be concluded from this sample.','','The denominator is known filled trajectories at each horizon. Censored fills cannot be counted as either failed opportunities or successful opportunities. ENTRY_SUMMARY.json includes all four placement cases, spot versus executable moves and every horizon. ENTRY_EXIT_GAPS.json links each fill to causal pre-entry features and baseline exit behavior.']
 (P/'STAGE1_REPORT.md').write_text('\n'.join(lines)+'\n');print('\n'.join(lines[:15]))
if __name__=='__main__':main()
