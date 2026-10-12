"""Frozen finite own/counterparty replay; local dependencies only."""
import bisect,collections,gzip,heapq,json,pathlib,pickle,types
import replay as R,build
import clock as W
HERE=pathlib.Path(__file__).resolve().parent
HOLDS={'velocity': 10, 'liquidity': 10, 'dislocation': 8, 'mature_fresh': 45}
SCENARIOS={'same_slot_one': {'buy': 0.001505, 'fast': 0.001505, 'scheduled': 1e-05, 'delay': 1}, 'next_slot_tail': {'buy': 0.001505, 'fast': 0.001505, 'scheduled': 0.000505, 'delay': 3}}
def apply_fixed(st,g):
 z=dict(st)
 for e in g['events']:
  if e['buy']:
   if e.get('ix_name') in ['buy','buy_v2']:
    n=e['tokens_raw']
    if n>=z['vtokens_raw'] or n>z['rtokens_raw']:return st,'counterparty_liquidity'
    q=z['vsol_raw']*n//(z['vtokens_raw']-n)+1
   else:
    q=e['sol_raw'];n=z['vtokens_raw']*q//(z['vsol_raw']+q)
    if n>z['rtokens_raw']:return st,'counterparty_liquidity'
   z=R.moved(z,q,n)
  else:
   n=e['tokens_raw'];q=R.sell(z,n)
   if q is None:return st,'counterparty_liquidity'
   z=R.moved(z,q[1],n,False)
  z['fee_bps']=e['fee_bps'];z['creator_fee_bps']=e['creator_fee_bps']
 return z,None

T=types.SimpleNamespace(R=R,build=build,apply_fixed=apply_fixed)
def detect_signals(t):
    """Extract candidate signals across the tape:
    - dislocation: group ends in sell, pre-reserves 8-25, drop >= 1.5 SOL and >= 15%, outside >= 15
    - velocity: reserve 6-16, outside gross buy >= 0.8 SOL by >= 2 addresses in last 10 groups
    - liquidity: reserve 6-16, >= 2 prior outside buyers
    - mature_fresh: age >= 50 slots, reserve 10.5-24, outside >= 40, fresh demand in last 4 slots
    """
    gs = t['groups']
    dev = t['creator']
    buyers = set()
    outside = set()
    outside_recent_buys = collections.deque()
    
    signals = []
    seen_rules_for_coin = set()
    prev_r = 0.0

    for i, g in enumerate(gs):
        ev = g.get('events', [])
        r = g['state']['rsol_raw'] / 1e9
        age = g['slot'] - t['creation_slot']
        
        # Track outside recent buyers for fresh demand predicate
        slot_buys = []
        for e in ev:
            if e['buy']:
                buyers.add(e['user'])
                if e['user'] != dev:
                    outside.add(e['user'])
                    slot_buys.append(dict(slot=g['slot'], user=e['user'], sol=e['sol_raw'] / 1e9))

        outside_recent_buys.extend(slot_buys)
        while outside_recent_buys and outside_recent_buys[0]['slot'] < g['slot'] - 4:
            outside_recent_buys.popleft()

        is_buy = bool(ev and ev[-1]['buy'])
        
        # 1. Dislocation (Post-dump dip)
        if bool(ev) and not is_buy and 8.0 <= prev_r <= 25.0:
            drop = prev_r - r
            if drop >= 1.5 and (drop / prev_r) >= 0.15 and len(outside) >= 15:
                # Dislocation can fire multiple times per coin on distinct dumps
                signals.append(dict(
                    rule='dislocation', index=i, slot=g['slot'], age_slots=age,
                    reserve=r, pre_reserve=prev_r, drop=drop, outside=len(outside),
                    ticket=0.75, max_hold=20 # 8 seconds nominal
                ))

        # 2. Velocity 10s (First time momentum hits 6-16 SOL)
        if 'velocity' not in seen_rules_for_coin and 6.0 <= r <= 16.0 and i >= 5:
            # Check last 10 groups gross outside buying
            trailing_groups = gs[max(0, i - 10):i + 1]
            out_gross = sum(e['sol_raw'] / 1e9 for tg in trailing_groups for e in tg.get('events', []) if e['buy'] and e['user'] != dev)
            out_users = {e['user'] for tg in trailing_groups for e in tg.get('events', []) if e['buy'] and e['user'] != dev}
            if out_gross >= 0.8 and len(out_users) >= 2:
                seen_rules_for_coin.add('velocity')
                signals.append(dict(
                    rule='velocity', index=i, slot=g['slot'], age_slots=age,
                    reserve=r, pre_reserve=prev_r, outside=len(outside),
                    ticket=0.50, max_hold=25 # 10 seconds nominal
                ))

        # 3. Simple Liquidity 10s (Control for velocity)
        if 'liquidity' not in seen_rules_for_coin and 6.0 <= r <= 16.0 and len(outside) >= 2:
            seen_rules_for_coin.add('liquidity')
            signals.append(dict(
                rule='liquidity', index=i, slot=g['slot'], age_slots=age,
                reserve=r, pre_reserve=prev_r, outside=len(outside),
                ticket=0.50, max_hold=25 # 10 seconds nominal
            ))

        # 4. Mature Breakout with Fresh Demand
        if 'mature_fresh' not in seen_rules_for_coin and is_buy and age >= 50 and 10.5 <= r <= 24.0 and len(outside) >= 40:
            # Check 4-slot fresh demand predicate
            meaningful = [b for b in outside_recent_buys if b['sol'] >= 0.05]
            m_users = {b['user'] for b in meaningful}
            user_vols = collections.Counter()
            for b in meaningful:
                user_vols[b['user']] += b['sol']
            tot_m_vol = sum(user_vols.values())
            top_share = (max(user_vols.values()) / tot_m_vol) if tot_m_vol > 0 else 1.0

            # Sell / buy ratio in trailing 4 slots
            recent_sells = sum(e['sol_raw'] / 1e9 for g_r in gs[:i + 1] if g['slot'] - 4 <= g_r['slot'] <= g['slot'] for e in g_r.get('events', []) if not e['buy'] and e['user'] != dev)
            recent_buys = sum(e['sol_raw'] / 1e9 for g_r in gs[:i + 1] if g['slot'] - 4 <= g_r['slot'] <= g['slot'] for e in g_r.get('events', []) if e['buy'] and e['user'] != dev)
            sell_buy_ratio = (recent_sells / recent_buys) if recent_buys > 0 else 1.0

            if len(m_users) >= 3 and top_share <= 0.50 and sell_buy_ratio <= 0.50:
                seen_rules_for_coin.add('mature_fresh')
                signals.append(dict(
                    rule='mature_fresh', index=i, slot=g['slot'], age_slots=age,
                    reserve=r, pre_reserve=prev_r, outside=len(outside),
                    ticket=0.75, max_hold=112 # 45 seconds nominal
                ))

        prev_r = r

    return signals

O=types.SimpleNamespace(detect_signals=detect_signals)
detect=detect_signals
def replay(item):
 t,sig,sn,mode=item;gs=t['groups'];cost=SCENARIOS[sn];ii=sig['index'];entry=sig['slot']
 if sn=='next_slot_tail':entry+=1;ii=bisect.bisect_right([g['slot']for g in gs],entry)-1
 else:
  j=ii+1
  while j<len(gs)and gs[j]['slot']==entry:
   ii=j
   if gs[j]['events']:break
   j+=1
 hold=HOLDS[sig['rule']];ticket=sig['ticket'];reservation=ticket+.003+cost['buy']+3*max(cost['fast'],cost['scheduled']);base=dict(mint=t['mint'],date=t['date'],rule=sig['rule'],scenario=sn,mode=mode,decision_slot=sig['slot'],entry_slot=entry,signal=sig,reservation_sol=reservation)
 def missing(reason):return dict(base,status='missing',reason=reason,pnl=None)
 st=dict(gs[ii]['state']);ref=T.R.buy(gs[sig['index']]['state'],ticket);qt=T.R.buy(st,ticket)
 if ref is None or qt is None or qt[1]<ref[1]*9700//10000:
  pnl=-.000505;return dict(base,status='failed',reason='entry_guard',pnl=pnl,settle_slot=entry,cash_return=reservation+pnl)
 try:h=T.build.inventory(gs[:ii+1]);cf=dict(h)
 except ValueError:return missing('unsupported_entry_custody')
 produced,et=W.time_at(entry)
 if produced!=entry:return missing('entry_slot_skipped')
 fire=W.timer_slot(t,entry,et+hold);exit_slot,xt=W.time_at(fire+cost['delay'])
 if xt>t['end_time']:return missing('requested_interval_exit_coverage')
 q,n=qt;bill=(q+T.R.fee(q,st['fee_bps'])+T.R.fee(q,st['creator_fee_bps']))/1e9;st=T.R.moved(st,q,n);total=n;proceeds=0.;sellfees=0.;pending=None;t1=t2=False;peak=0.;gi=ii+1;reason=None;settle=entry
 for slot in range(entry,exit_slot+1):
  while gi<len(gs)and gs[gi]['slot']<=slot:
   st,h,cf,_,reason=T.R.apply(st,gs[gi],h,cf);gi+=1
   if reason:break
   if st['rtokens_raw']==0:reason='migration';break
  if reason:break
  if pending is not None and slot>=pending['slot']:
   selln=pending['n'];out=T.R.sell(st,selln)
   if out is None:reason='unfillable_sell';break
   st=T.R.moved(st,out[1],selln,False);proceeds+=out[0]/1e9;sellfees+=cost['fast']if pending['fast']else cost['scheduled'];n-=selln;settle=slot;pending=None
   if n==0:break
  if n<=0:break
  quote=T.R.sell(st,n)
  if quote:peak=max(peak,quote[0]/n)
  # Hard independent timer supersedes a pending partial order at deadline.
  if slot>=fire and(pending is None or pending['kind']!='timer'):
   pending=dict(kind='timer',n=n,slot=exit_slot,fast=False);continue
  if pending is not None or mode=='full_timer':continue
  if not t1:
   out=T.R.sell(st,total//2)
   if out and out[0]/1e9>=bill*.5*1.25:t1=True;pending=dict(kind='t1',n=total//2,slot=slot+cost['delay'],fast=False)
  elif not t2:
   out=T.R.sell(st,total//4)
   if out and out[0]/1e9>=bill*.25*1.5:t2=True;pending=dict(kind='t2',n=total//4,slot=slot+cost['delay'],fast=False)
  elif quote and peak and quote[0]/n<=peak*.85:pending=dict(kind='trail',n=n,slot=slot+1,fast=True)
 pnl=proceeds-bill-cost['buy']-sellfees-(.003 if n else 0)
 return dict(base,status='unresolved'if n else'closed',reason=reason or('remaining_inventory'if n else'completed'),pnl=pnl,cash_return=reservation+pnl,settle_slot=settle if not n else min(gs[min(gi,len(gs))-1]['slot'],exit_slot),remaining_tokens=n,entry_bill=bill,proceeds=proceeds,total_sell_fees=sellfees,timer_slot=fire,actual_age_seconds=gs[sig['index']]['block_time']-t['creation_time'])

def summarize(rs):
 closed=[r for r in rs if r['status']=='closed'];ws=[r['pnl']for r in closed if r['pnl']>0];ls=[r['pnl']for r in closed if r['pnl']<=0]
 return dict(attempts=len(rs),closed=len(closed),closed_pnl=sum(r['pnl']for r in closed),known_pnl=sum(r['pnl']for r in rs if r['pnl']is not None),pf=sum(ws)/abs(sum(ls))if sum(ls)else 999.,win_rate=100*len(ws)/len(closed)if closed else 0.,statuses=dict(collections.Counter(r['status']for r in rs)))

def ledger(rows,capital,limit=2):
 cash=capital;pending=[];open_mints=set();accepted=[];cash_skip=cap_skip=missing=duplicate=0;peak=capital;draw=0.;eq=capital
 for r in sorted(rows,key=lambda r:(r['decision_slot'],r['mint'])):
  while pending and pending[0][0]<r['decision_slot']:
   _,_,old=heapq.heappop(pending);cash+=old['cash_return'];eq+=old['pnl'];peak=max(peak,eq);draw=max(draw,peak-eq)
   if old['status']!='unresolved':open_mints.discard(old['mint'])
  if r['pnl'] is None:missing+=1;continue
  if r['mint']in open_mints:duplicate+=1;continue
  if len(open_mints)>=limit:cap_skip+=1;continue
  if cash<r['reservation_sol']-1e-12:cash_skip+=1;continue
  cash-=r['reservation_sol'];open_mints.add(r['mint']);accepted.append(r);heapq.heappush(pending,(r['settle_slot'],len(accepted),r))
 while pending:
  _,_,r=heapq.heappop(pending);cash+=r['cash_return'];eq+=r['pnl'];peak=max(peak,eq);draw=max(draw,peak-eq)
  if r['status']!='unresolved':open_mints.discard(r['mint'])
 net=sum(r['pnl'] for r in accepted)
 assert abs(cash-capital-net)<1e-8
 return dict(initial_capital=capital,position_limit=limit,admitted=len(accepted),statuses=dict(collections.Counter(r['status'] for r in accepted)),ending_cash=cash,net_zero_recovery_sol=net,closed_net_sol=sum(r['pnl'] for r in accepted if r['status']=='closed'),cash_skips=cash_skip,position_skips=cap_skip,duplicate_skips=duplicate,missing_not_modeled=missing,remaining_open_positions=len(open_mints),max_settled_drawdown=draw,cash_reconciled=True,caveat='known-outcome intents only; incomplete intents not imputed or secretly profitable; unresolved remains open at conservative value')

def load():return pickle.load(gzip.open(HERE/'TAPES.pkl.gz','rb'))
def selected(ts):return[t for t in ts if t['normal']]
A=types.SimpleNamespace(summarize=summarize,load=load,selected=selected)
AC=types.SimpleNamespace(ledger=ledger)
