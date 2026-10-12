"""Research-only current-shadow exit derivative of the approved replay.

Recorded successful counterparty instructions are repriced with guards. Public
failed routed intents stay explicit execution uncertainty, never quote-only
resurrected fills. Migration uses authenticated opening deposits and custody.

The source engine is pinned below. This file keeps its simulation API and its
whole-transaction, quote, custody, migration, and censoring mechanics. The
CURRENT-only edits are limited to the current shadow min-token guard, ROI
denominator, capped curve sell behavior, exit rules, diagnostic snapshots, and
optional scheduled-timer landing sensitivity.
"""
import bisect,collections,concurrent.futures,gzip,hashlib,heapq,json,pathlib,sys
P=pathlib.Path(__file__).resolve().parent;ROOT=P.parents[1];OLD=ROOT/'research/wallet_curve_entry_discovery_20261007'
sys.path.insert(0,str(OLD));import curve_adapter as A,amm_counterparty as M
sys.path.insert(0,str(ROOT/'research/amm_multiday_20261006'));import opportunity as O
sys.path.insert(0,str(ROOT/'research/day_general_20261004'));import clock as W
W.time_at=O.block_at;W.TIMES=O.CLOCK;O.C.P=P
L=10**9;RENT=2039280;FAILED=505000
SOURCE_ENGINE_PATH='research/core_plan_audit_20261007/engine.py'
SOURCE_ENGINE_SHA256='bb844aaf9b8c8fad050bc69b35b379b325cdd31a1f5a91482d93f420108a8976'
CURRENT_POLICY='2026-10-11 current Rust shadow exits; research-only derivative'

def opening_state(curve,g,t,h,cf):
 """Pool deposit/boost followed by the whole opening transaction's swaps.

 A migration receipt may also buy from its new pool. Post-transaction reserves
 cannot be treated as opening deposits or skip that buyer's custody.
 """
 opening=g['before'];effective=curve['rsol_raw']-t['migration_quote_difference'];base=opening['base'];supply=g['trades'][0]['supply'] if g['trades'] else g['state']['supply'];virtual=effective*base//supply
 if effective<=0 or base<=0:return None,h,cf,'invalid_migration_deposit'
 st=dict(g['state'],base=base,quote=effective-virtual,virtual=virtual,supply=supply,source_reverts=curve.get('source_reverts',0))
 z,hh,cc,err=M.advance(st,g,h,cf)
 if err:return None,h,cf,err
 if z.get('source_reverts',0)>st.get('source_reverts',0):return None,h,cf,'atomic_pool_opening_reverted'
 return z,hh,cc,None

def pos(gs,j,slot):return (slot,gs[j]['index'] if j>=0 and gs[j]['slot']==slot else -1,1)

def curve_sell_capped(st,requested):
 """Mirror Rust QuoteState.quote_sell_capped; return (net,gross,sold).

 A full-exit landing explicitly writes off any unsold remainder in `execute`,
 matching current Rust. Partial capped fills retain unsold paper custody.
 """
 if requested<=0 or st.get('rtokens_raw',0)==0:return None
 # Retain the approved adapter's full-fill path. Its `None` on reserve
 # exhaustion is where the current Rust-compatible cap below is applied.
 full=A.sell(st,requested)
 if full is not None:
  return (full[0],full[1],requested) if full[0]>=0 else None
 vs=st['vsol_raw'];vt=st['vtokens_raw'];rs=st['rsol_raw']
 if vs<=0 or vt<=0 or rs>vs or st['rtokens_raw']>vt:return None
 gross=vs*requested//(vt+requested)
 sold=requested
 if gross>rs:
  denominator=vs-(rs+1)
  if denominator<=0:return None
  sold=min(requested,(((rs+1)*vt)-1)//denominator)
  if sold<=0:return None
  gross=vs*sold//(vt+sold)
  if gross>rs:return None
 protocol=A.fee(gross,st['fee_bps']);creator=A.fee(gross,st['creator_fee_bps'])
 if protocol+creator>gross:return None
 return gross-protocol-creator,gross,sold

def simulate(t,sig,sc,endpoint,ticket=.5,fee=1505000,cfg=None):
 cfg=cfg or {}
 gs=t['groups'];i=next(i for i,g in enumerate(gs) if g['signature']==sig['signal_signature']);sig=dict(sig,index=i,pool=t['curve'])
 def branch(intent,leg='entry'):
  seed=cfg.get('_placement_seed',0)
  return O.branch(dict(intent,pool=intent['pool']+(f'|replicate{seed}' if seed else '')),sc,leg)
 j,slot=O.landing(gs,i,sig['slot'],branch(sig));_,tm=O.block_at(slot)
 base=dict(sig,scenario=sc,endpoint=endpoint,ticket=ticket,fee=fee,legs=[],signal_position=(sig['slot'],gs[i]['index'],0),entry_position=pos(gs,j,slot),entry_time=tm)
 ref=A.buy(gs[i]['state'],ticket);r=A.buy(gs[j]['state'],ticket) if gs[j]['venue']=='curve' else None
 # CURRENT Rust entry guard is fixed at 90% of signal-time expected tokens.
 min_bps=9000
 if not ref or not r or r[1]<ref[1]*min_bps//10000:
  return dict(base,status='failed',net=-FAILED,mark=0,entry_bill=0,close_position=base['entry_position'],close_time=tm,
              mark_venue=gs[j]['venue'],last_valid_time=None,entry_state=None,entry_roi=None,peak_roi=None,realized=0,fees=FAILED)
 st=A.moved(gs[j]['state'],*r);h=A.build.inventory(gs[:j+1]);cf=dict(h);n=r[1];original=n;bill=r[0]+A.fee(r[0],st['fee_bps'])+A.fee(r[0],st['creator_fee_bps']);fees=fee;realized=0;venue='curve';lastpos=base['entry_position'];lasttime=tm;clip=False;ratchet=False;peak=0.;handled=set();migration_time=None;entryspot=st['vsol_raw']/st['vtokens_raw'];reason=None
 entry_state=dict(st);amm_open_roi=None
 base.update(entry_bill=bill,entry_tokens=n)
 entry_cost=bill+fee
 def quote(amount):return curve_sell_capped(st,amount) if venue=='curve' else M.A.sell(st,amount) if venue=='amm' else None
 def proceeds(q):return q[0] if venue=='curve' else q['total']
 def roi():
  # Match PaperPosition.entry_cost_sol: denominator includes the entry network
  # fee. The quote includes our own impact and this estimate reserves one fee
  # for the eventual sale, as update_at_ms does for market-trigger decisions.
  q=quote(n);return (realized+proceeds(q)-bill-fees-fee)/entry_cost if q else None
 entry_roi=roi()
 def unresolved(why):
  q=quote(n);mark=max(0,proceeds(q)-fee) if q else 0
  return dict(base,status='unresolved',reason=why,net=realized-bill-fees-RENT,mark=mark,remaining=n,last_valid_time=lasttime,last_valid_position=lastpos,close_position=None,counterparty_reverts=st.get('source_reverts',0),mark_venue=venue,entry_state=entry_state,entry_roi=entry_roi,peak_roi=peak,realized=realized,fees=fees)
 def advance(k):
  nonlocal st,h,cf,venue,j,lastpos,lasttime,migration_time
  g=gs[k]
  if g['venue']=='curve':
   if venue!='curve':return 'curve_activity_after_AMM_open'
   # Version3 crossing can have a pool leg beyond curve completion.
   before=dict(st);st,h,cf,ag,err=A.apply(st,g,h,cf)
   if err:return err
   if st['rtokens_raw']==0 and before['rtokens_raw'] and any(e.get('instruction_name','').endswith('_v3') and e['buy'] for e in g['events']):return 'v3_post_completion_pool_leg_unmodeled'
  elif venue=='curve':
   if st['rtokens_raw']!=0:return 'counterfactual_completion_displaced'
   if t['inventory_key']!='token_account':return 'migration_account_mapping_unverified'
   z,hh,cc,err=opening_state(st,g,t,h,cf)
   if err:return err
   st,h,cf=z,hh,cc;venue='amm';migration_time=g['time']
   # Market holders retain account custody across the source's atomic opening.
  else:
   st,h,cf,err=M.advance(st,g,h,cf)
   if err:return err
  j=k;lastpos=(g['slot'],g['index'],0);lasttime=g['time'];return None
 def execute(anchor,refslot,amount,why,target=None):
  nonlocal st,n,realized,fees,j,lastpos,lasttime
  scheduled_slots=cfg.get('scheduled_slots') if target is not None else None
  if scheduled_slots is not None:
   if scheduled_slots not in (1,3):raise ValueError('scheduled_slots must be 1 or 3')
   # Uncalibrated scheduled-timer sensitivity: count produced slots after the
   # timer slot, then land after that slot's first complete event group.
   dest=refslot
   for _ in range(scheduled_slots):dest,_=O.block_at(dest+1)
   when=O.block_at(dest)[1]
   first=bisect.bisect_left([g['slot'] for g in gs],dest)
   land=max(j,first if first<len(gs) and gs[first]['slot']==dest else first-1)
  else:
   land,dest=O.landing(gs,anchor,refslot,branch(dict(sig,index=anchor),leg=f'{why}-{len(base["legs"])}'))
   _,when=O.block_at(dest)
  if target is not None and when<target:raise AssertionError('timer_fill_before_deadline')
  if dest<refslot or land<anchor:raise AssertionError('sell_before_trigger')
  if when>t['end_time']:return 'sell_outside_coverage'
  for k in range(j+1,land+1):
   e=advance(k)
   if e:return e
  amount=min(n,amount);requested=amount;full_exit=requested>=n;q=quote(requested)
  if not q:
   # A pending curve sell that loses its venue retains custody, not a fake fill.
   if venue=='curve' and st['rtokens_raw']==0:
    fees+=FAILED;handled.add('pending_migration_exit');return 'migration_wait'
   return 'unquotable_own_sell'
  sold=q[2] if venue=='curve' else requested
  before=dict(st);got=proceeds(q);st=A.moved(st,q[1],sold,False) if venue=='curve' else M.moved(st,q,False,False);realized+=got;fees+=fee;n-=sold
  # Rust closes a full-exit intent after a capped quote and explicitly writes
  # off tokens the drained real reserve cannot pay for. A partial intent keeps
  # those unsold tokens in custody and marks them at their capped value.
  written_off=n if full_exit else 0
  if full_exit:n=0
  lastpos=pos(gs,j,dest);lasttime=when
  base['legs'].append(dict(tokens=sold,requested_tokens=requested,written_off_tokens=written_off,proceeds=got,fee=fee,venue=venue,reason=why,trigger_slot=refslot,landing_slot=dest,position=lastpos,time=when,timer_target=target,scheduled_slots=scheduled_slots,delivery=('scheduled_uncalibrated' if scheduled_slots is not None else 'reactive_placement'),state_before=before));return None
 opening_evaluation=False
 while n:
  k=j+1;targets=[];rule=sig['rule'];value=roi()
  # CURRENT S3/S5 timers are causal deadlines. Undefined S1/S2/S4 runners stay
  # open; coverage end is censoring and never causes a sale.
  if rule=='s3_deadman':
   if 's3_stop_grace' not in handled:targets.append((tm+18,'s3_stop_grace'))
   if 's3_timeout' not in handled:targets.append((tm+60,'s3_timeout'))
  if rule=='s5_carryover':
   if migration_time is None:targets=[(tm+600,'s5_curve_timeout')]
   else:
    if 's5_amm_trail_grace' not in handled:targets.append((migration_time+60,'s5_amm_trail_grace'))
    targets.append((migration_time+600,'s5_amm_timeout'))
  target,why=min(targets,default=(tm+cfg.get('runner_max_hold',600),'runner_timeout' if cfg.get('runner_max_hold') else 'coverage_horizon'))
  if (k>=len(gs) or gs[k]['time']>=target) and venue=='curve' and st['rtokens_raw']==0:
   # No curve market exists in the freeze. Preserve custody until actual pool
   # opening; expired timer intents retry there and never sell fictitious tokens.
   nextamm=next((z for z in range(k,len(gs)) if gs[z]['venue']=='amm'),None)
   if nextamm is None:return unresolved('migration_coverage_missing')
   for z in range(k,nextamm+1):
    e=advance(z)
    if e:return unresolved(e)
   opening_evaluation=True
   continue
  # Include a transaction stamped exactly at the deadline before evaluating
  # its post-transaction exit state. A later/no transaction invokes the timer.
  if not opening_evaluation and (k>=len(gs) or gs[k]['time']>target):
   if target>t['end_time']:return unresolved('coverage_before_requested_timer')
   if why=='coverage_horizon':return unresolved('runner_timeout_undefined')
   fireslot=max(W.timer_slot(t,slot,target),gs[j]['slot'],lastpos[0]);anchor=max(j,bisect.bisect_left([g['slot'] for g in gs],fireslot)-1)
   for z in range(j+1,anchor+1):
    e=advance(z)
    if e:return unresolved(e)
   handled.add(why);v=roi()
   if v is None:return unresolved('timer_unquotable_position')
   if why=='s3_stop_grace':
    if v<=-.18:why='relative_price_stop'
    else:continue
   if why=='s5_amm_trail_grace':
    if 1+v<=(1+peak)*.82:why='AMM_runner_trail'
    else:continue
   e=execute(j,fireslot,n,why,target)
   if e=='migration_wait':continue
   if e:return unresolved(e)
   continue
  if opening_evaluation:opening_evaluation=False
  else:
   e=advance(k)
   if e:return unresolved(e)
  v=roi()
  if v is None:
   if venue=='curve' and st['rtokens_raw']==0:continue
   return unresolved('unquotable_position')
  peak=max(peak,v);why=None;amount=n
  if 'pending_migration_exit' in handled:why='migration_retry';handled.discard('pending_migration_exit')
  elif rule=='s1_dev_absorption':
   current=st['vsol_raw']/st['vtokens_raw'] if venue=='curve' else (st['quote']+st['virtual'])/st['base']
   below_trough=sig.get('trough_spot') is not None and current<sig['trough_spot']
   # S1: before the first 40% tranche, hard -10% and trough invalidation;
   # after it, only the 15 percentage-point runner trail remains.
   if not clip and (v<=-.10 or below_trough):why='floor_invalidation'
   elif not clip and v>=.25:clip=True;amount=max(1,original*40//100);why='tailored_40pct_profit_target'
   elif clip and v<=peak-.15:why='tailored_runner_trail'
  elif rule=='s2_survival_shelf':
   ratchet=ratchet or v>=.20
   # S2: curve reserve floor has priority; +20% arms breakeven only before
   # the +30% tranche; the delivered remainder uses a 15pp giveback trail.
   if venue=='curve' and st['rsol_raw']<=9_800_000_000:why='shelf_invalidation'
   elif ratchet and not clip and v<=0:why='breakeven_ratchet'
   elif not clip and v>=.30:clip=True;amount=max(1,original*40//100);why='tailored_40pct_profit_target'
   elif clip and v<=peak-.15:why='tailored_runner_trail'
  elif rule=='s3_deadman':
   # S3 trail arms at +20% and is active immediately; only the net -18% stop
   # waits 18 seconds. The independently checked 60s timeout is below.
   ratchet=ratchet or peak>=.20
   if ratchet and v<=peak-.10:why='runner_trail'
   elif lasttime-tm>=18 and v<=-.18:why='relative_price_stop'
   elif lasttime-tm>=60:why='s3_timeout'
  elif rule=='s4_upper_ath':
   # S4 target/trail decisions lead; catastrophic and delayed rejection
   # invalidations apply only while the original full bag is still held.
   if not clip and v>=.20:clip=True;amount=max(1,original//2);why='half_profit_target'
   elif clip and 1+v<=(1+peak)*.94:why='runner_trail'
   elif not clip and v<=-.22:why='severe_dump_stop'
   elif not clip and gs[j]['slot']>=slot+25 and v<=-.18 and peak<.10:why='breakout_rejected'
  elif rule=='s5_carryover':
   if venue=='curve':
    if st['rsol_raw']<=60_000_000_000:why='carryover_invalidation'
    elif lasttime-tm>=600:why='s5_curve_timeout'
   else:
    # AMM first evaluation is this replay's whole authenticated opening group.
    # RPC first-snapshot timing can be later in the live shadow implementation.
    if amm_open_roi is None:amm_open_roi=v;peak=v
    vs_open=(1+v)/max(1+amm_open_roi,1e-9)-1
    if vs_open<=-.35 or v<=-.45:why='s5_amm_hard_stop'
    elif not clip and v>=amm_open_roi+.50:clip=True;amount=max(1,original//2);why='AMM_open_half'
    elif lasttime-migration_time>=60 and 1+v<=(1+peak)*.82:why='AMM_runner_trail'
    elif lasttime-migration_time>=600:why='s5_amm_timeout'
  if why:
   timer_target=target if why in ('s3_timeout','s5_curve_timeout','s5_amm_timeout') else None
   e=execute(j,gs[j]['slot'],amount,why,timer_target)
   if e=='migration_wait':continue
   if e:return unresolved(e)
 return dict(base,status='closed',net=realized-bill-fees,mark=0,remaining=0,close_position=lastpos,close_time=lasttime,counterparty_reverts=st.get('source_reverts',0),mark_venue=venue,last_valid_time=lasttime,entry_state=entry_state,entry_roi=entry_roi,peak_roi=peak,realized=realized,fees=fees)

def load():
 signals=json.loads((P/'SIGNALS.json').read_text());tapes={};pools={}
 for f in (P/'amm_tapes').glob('*.gz'):
  t=json.load(gzip.open(f,'rt'));pools[t['mint']]=t
 for mint in {s['mint'] for s in signals}:
  af=OLD/'merged_account_tapes'/(mint+'.json.gz');f=P/'bound_curve_tapes'/(mint+'.json.gz');t=json.load(gzip.open(af if af.exists() else f,'rt'));key='token_account' if af.exists() else 'wallet'
  gs=[dict(g,venue='curve',trades=g['events'],time=g['block_time']) for g in t['groups'] if g.get('source_status','succeeded')=='succeeded']
  pool=pools.get(mint)
  if pool:
   fee_difference=next(g['state']['rsol_raw'] for g in gs if g['state']['rtokens_raw']==0)-pool['groups'][0]['before']['quote'];gs.extend(dict(g,venue='amm') for g in pool['groups']);t['migration_quote_difference']=fee_difference
  gs.sort(key=lambda g:(g['slot'],g['index']));t.update(groups=gs,inventory_key=key);tapes[mint]=t
  for g in gs:O.CLOCK[g['slot']]=g['time']
 return tapes,signals

def main():
 tapes,ss=load();jobs=[];results=[];errors=[]
 for s in ss:
  for endpoint in ['lower','upper']:
   for sc,fee in [(sc,1505000) for sc in ['fast','central80','central85','slow','stress']]+[('central85',2916000)]:
    for ticket in [.5,.25]:jobs.append((tapes[s['mint']],s,sc,endpoint,ticket,fee))
 with concurrent.futures.ThreadPoolExecutor(4) as ex:
  fs={ex.submit(simulate,*j):j[1] for j in jobs}
  for f in concurrent.futures.as_completed(fs):
   try:results.append(f.result())
   except Exception as e:errors.append(dict(signal=fs[f],error=repr(e)))
   if (len(results)+len(errors))%100==0:print('REPLAY',len(results),len(errors),'of',len(jobs),flush=True)
 with gzip.open(P/'REPLAY_RESULTS.json.gz','wt',compresslevel=1) as f:json.dump(results,f)
 (P/'REPLAY_ERRORS.json').write_text(json.dumps(errors,indent=2)+'\n');print('COMPLETE',len(results),len(errors),flush=True)
if __name__=='__main__':main()
