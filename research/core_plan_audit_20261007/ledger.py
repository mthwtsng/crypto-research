"""Chronological shared cash ledger; breakers affect admissions, never exits.

Reservations include pending entries. Cash is credited only at each delivered
sell leg. Unresolved custody stays funded and occupies a concurrency slot.
"""
import collections,datetime,gzip,heapq,json,pathlib
P=pathlib.Path(__file__).resolve().parent;L=10**9;RENT=2039280
RULES=['s1_dev_absorption','s2_survival_shelf','s3_deadman','s4_upper_ath','s5_carryover']
MATRIX=dict(zip(RULES,[(5,.60,6,3),(8,.60,8,4),(10,.50,4,2),(6,.75,8,4),(5,.80,12,6)]))

def funded(rows,breakers=False,scope='portfolio',position_limit=2):
 rows=[r for r in rows if scope=='portfolio' or (scope=='portfolio_without_carryover' and r['rule']!='s5_carryover') or r['rule']==scope]
 by=collections.defaultdict(dict)
 for r in rows:by[(r['mint'],r['rule'],r['signal_signature'])][r['ticket']]=r
 q=[];serial=0
 def push(position,kind,data):
  nonlocal serial
  serial+=1;heapq.heappush(q,(tuple(position),serial,kind,data))
 for key,options in sorted(by.items()):push(options[.5]['signal_position'],'signal',(key,options))
 cash=15*L;active={};admitted=[];skipped=collections.Counter();history=collections.defaultdict(list);global_history=[];global_until=0;states={r:dict(until=0,mode='active',streak=0) for r in RULES};trips=[];cash_path=[(0,cash)];max_committed=0
 def book(r,tm,net,closed):
  nonlocal global_until
  rule=r['rule'];s=states[rule];history[rule].append((tm,net));global_history.append((tm,net))
  if closed:
   if net>0:s['streak']=0
   elif net<0:s['streak']+=1
  if not breakers:return
  limit,loss,hours,sleep=MATRIX[rule]
  rolling=sum(v for t,v in history[rule] if t>=tm-hours*3600)
  if r.get('probe'):
   if closed and net>0:s['mode']='active';s['streak']=0
   else:s.update(until=tm+sleep*3600,mode='cooldown');trips.append(dict(rule=rule,time=tm,reason='probe_nonwin'))
  elif s['mode']=='active' and (s['streak']>=limit or rolling<=-round(loss*L)):
   s.update(until=tm+sleep*3600,mode='cooldown');trips.append(dict(rule=rule,time=tm,reason='streak' if s['streak']>=limit else 'rolling_net',rolling=rolling))
  total=sum(v for t,v in global_history if t>=tm-86400)
  if tm>=global_until and total<=-2*L:
   global_until=tm+43200;trips.append(dict(rule='global',time=tm,reason='rolling_net',rolling=total))
 while q:
  position,_,kind,data=heapq.heappop(q)
  if kind=='signal':
   key,options=data;r=options[.5];tm=r['time'];rule=r['rule'];s=states[rule]
   if breakers and tm<global_until:skipped['global_pause']+=1;continue
   if breakers and s['mode']=='cooldown':
    if tm<s['until']:skipped['strategy_pause']+=1;continue
    s['mode']='probe'
   if breakers and s['mode']=='probe_pending':skipped['probe_pending']+=1;continue
   if r['mint'] in active:skipped['same_mint_open']+=1;continue
   if position_limit is not None and len(active)>=position_limit:skipped['concurrency']+=1;continue
   ticket=.25 if breakers and s['mode']=='probe' else .5;r=dict(options[ticket]);r['probe']=ticket==.25;reserved=round(ticket*L)+r['fee']+RENT
   if cash<reserved:skipped['cash']+=1;continue
   if r['probe']:s['mode']='probe_pending'
   cash-=reserved;r['reservation']=reserved;active[r['mint']]=r;admitted.append(r);max_committed=max(max_committed,len(active));push(r['entry_position'],'entry',r)
   for leg in r['legs']:push(leg['position'],'leg',(r,leg))
   if r['status']=='unresolved':
    missing=r['net']-(sum(x['proceeds']-x['fee'] for x in r['legs'])-r['entry_bill']-r['fee']-RENT)
    if missing:push(r.get('last_valid_position',r['entry_position']),'extra_fee',(r,missing))
  elif kind=='entry':
   r=data
   if r['status']=='failed':
    cash+=r['reservation']+r['net'];active.pop(r['mint']);book(r,r['entry_time'],r['net'],False)
   else:
    cash+=r['reservation']-r['entry_bill']-r['fee']-RENT
  elif kind=='extra_fee':cash+=data[1]
  else:
   r,leg=data;cash+=leg['proceeds']-leg['fee']
   if r['status']=='closed' and leg is r['legs'][-1]:
    computed=sum(x['proceeds']-x['fee'] for x in r['legs'])-r['entry_bill']-r['fee'];cash+=r['net']-computed+RENT;active.pop(r['mint']);book(r,leg['time'],r['net'],True)
  cash_path.append((position[0],cash))
  if cash<0:raise AssertionError('negative_cash')
 zero=sum(r['net'] for r in admitted);mark=sum(r['mark'] for r in admitted if r['status']=='unresolved');assert cash-15*L==zero,(cash-15*L,zero)
 closed=[r for r in admitted if r['status']=='closed'];wins=[r['net'] for r in closed if r['net']>0];losses=[r['net'] for r in closed if r['net']<0];largest=max(wins,default=0);high=15*L;dd=0
 for _,v in cash_path:high=max(high,v);dd=max(dd,high-v)
 # Settled equity includes principal still committed to pending/open trades.
 # Cash-path drawdown is liquidity drawdown, not an unrealized loss estimate.
 settled=15*L;hi=settled;settled_dd=0
 for tm,v in sorted(global_history):settled+=v;hi=max(hi,settled);settled_dd=max(settled_dd,hi-settled)
 daily=collections.Counter()
 for tm,v in global_history:daily[datetime.datetime.fromtimestamp(tm,datetime.timezone.utc).date().isoformat()]+=v
 # Cash invested in unsold inventory is not a settled trading loss. Preserve
 # the legacy zero-bound field, but expose the components for honest reporting.
 settled_net=sum(r['net'] for r in admitted if r['status']!='unresolved')
 unresolved_cashflow=sum(r['net'] for r in admitted if r['status']=='unresolved')
 assert settled_net+unresolved_cashflow==zero
 return dict(settled_net_SOL=settled_net/L,unresolved_cashflow_SOL=unresolved_cashflow/L,unresolved_marked_pnl_SOL=(unresolved_cashflow+mark)/L,unresolved_mark_value_SOL=mark/L,zero_recovery_bound_SOL=zero/L,last_valid_marked_net_SOL=(zero+mark)/L,unresolved_excluded_from_win_loss=True,scope=scope,breakers=breakers,attempts=len(admitted),closed=len(closed),failed=sum(r['status']=='failed' for r in admitted),unresolved=len(active),net_zero_SOL=zero/L,net_marked_SOL=(zero+mark)/L,mark_SOL=mark/L,ending_cash_SOL=cash/L,closed_net_SOL=sum(r['net'] for r in closed)/L,win_rate=len(wins)/len(closed) if closed else None,profit_factor=sum(wins)/-sum(losses) if losses else None,max_settled_drawdown_SOL=settled_dd/L,max_cash_drawdown_SOL=dd/L,largest_winner_SOL=largest/L,net_without_largest_SOL=(zero-largest)/L,skipped=dict(skipped),trips=trips,max_open=max_committed,daily_net_SOL={k:v/L for k,v in daily.items()},status_by_strategy={rule:dict(collections.Counter(r['status'] for r in admitted if r['rule']==rule)) for rule in RULES},unresolved_reasons=dict(collections.Counter(r.get('reason') for r in admitted if r['status']=='unresolved')),admitted=[dict(mint=r['mint'],rule=r['rule'],status=r['status'],net_SOL=r['net']/L,mark_SOL=r['mark']/L,probe=r['probe'],legs=r['legs']) for r in admitted])

def main():
 rows=json.load(gzip.open(P/'REPLAY_RESULTS.json.gz','rt'));groups=collections.defaultdict(list)
 for r in rows:groups[(r['scenario'],r['endpoint'],r['fee'])].append(r)
 results=[]
 for (scenario,endpoint,fee),rr in sorted(groups.items()):
  for scope in ['portfolio','portfolio_without_carryover']+RULES:
   for breakers in [False,True]:results.append(dict(scenario=scenario,endpoint=endpoint,fee=fee,**funded(rr,breakers,scope)))
 (P/'FUNDED_RESULTS.json').write_text(json.dumps(results,indent=2)+'\n')
 for r in results:
  if r['scope']=='portfolio':print(r['scenario'],r['endpoint'],r['fee'],r['breakers'],r['attempts'],r['closed'],r['failed'],r['unresolved'],round(r['net_zero_SOL'],4),round(r['net_marked_SOL'],4))
if __name__=='__main__':main()
