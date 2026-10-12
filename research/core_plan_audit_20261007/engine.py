"""Starting-Five replay using repaired approved curve/AMM adapters.

Recorded successful counterparty instructions are repriced with guards. Public
failed routed intents stay explicit execution uncertainty, never quote-only
resurrected fills. Migration uses authenticated opening deposits and custody.
"""
import bisect,collections,concurrent.futures,gzip,hashlib,heapq,json,pathlib,sys
P=pathlib.Path(__file__).resolve().parent;ROOT=P.parents[1];OLD=ROOT/'research/wallet_curve_entry_discovery_20261007'
sys.path.insert(0,str(OLD));import curve_adapter as A,amm_counterparty as M
sys.path.insert(0,str(ROOT/'research/amm_multiday_20261006'));import opportunity as O
sys.path.insert(0,str(ROOT/'research/day_general_20261004'));import clock as W
W.time_at=O.block_at;W.TIMES=O.CLOCK;O.C.P=P
L=10**9;RENT=2039280;FAILED=505000

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

def simulate(t,sig,sc,endpoint,ticket=.5,fee=1505000,cfg=None):
 cfg=cfg or {}
 gs=t['groups'];i=next(i for i,g in enumerate(gs) if g['signature']==sig['signal_signature']);sig=dict(sig,index=i,pool=t['curve'])
 def branch(intent,leg='entry'):
  seed=cfg.get('_placement_seed',0)
  return O.branch(dict(intent,pool=intent['pool']+(f'|replicate{seed}' if seed else '')),sc,leg)
 j,slot=O.landing(gs,i,sig['slot'],branch(sig));_,tm=O.block_at(slot)
 base=dict(sig,scenario=sc,endpoint=endpoint,ticket=ticket,fee=fee,legs=[],signal_position=(sig['slot'],gs[i]['index'],0),entry_position=pos(gs,j,slot),entry_time=tm)
 ref=A.buy(gs[i]['state'],ticket);r=A.buy(gs[j]['state'],ticket) if gs[j]['venue']=='curve' else None
 min_bps=cfg.get(f"{sig['rule']}_min_tokens_bps",cfg.get('min_tokens_bps',9700))
 if not ref or not r or r[1]<ref[1]*min_bps//10000:return dict(base,status='failed',net=-FAILED,mark=0,entry_bill=0,close_position=base['entry_position'],close_time=tm)
 st=A.moved(gs[j]['state'],*r);h=A.build.inventory(gs[:j+1]);cf=dict(h);n=r[1];original=n;bill=r[0]+A.fee(r[0],st['fee_bps'])+A.fee(r[0],st['creator_fee_bps']);fees=fee;realized=0;venue='curve';lastpos=base['entry_position'];lasttime=tm;clip=False;ratchet=False;peak=-1.;handled=set();migration_time=None;entryspot=st['vsol_raw']/st['vtokens_raw'];reason=None
 base.update(entry_bill=bill,entry_tokens=n)
 entry_fill_price=bill/n
 def relative_stop_hit():
  current=st['vsol_raw']/st['vtokens_raw'] if venue=='curve' else (st['quote']+st['virtual'])/st['base']
  return cfg.get('s3_relative_price_stop') is not None and current<=entry_fill_price*(1-cfg['s3_relative_price_stop'])
 def quote(amount):return A.sell(st,amount) if venue=='curve' and st['rtokens_raw'] else M.A.sell(st,amount) if venue=='amm' else None
 def proceeds(q):return q[0] if venue=='curve' else q['total']
 def roi():
  q=quote(n);return (realized+proceeds(q)-bill-fees-fee)/bill if q else None
 def tailored_trail_hit(v,width):
  return v<=peak-width if cfg.get('tailored_trail_basis','percentage_points')=='percentage_points' else 1+v<=(1+peak)*(1-width)
 def unresolved(why):
  q=quote(n);mark=max(0,proceeds(q)-fee) if q else 0
  return dict(base,status='unresolved',reason=why,net=realized-bill-fees-RENT,mark=mark,remaining=n,last_valid_time=lasttime,last_valid_position=lastpos,close_position=None,counterparty_reverts=st.get('source_reverts',0))
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
  land,dest=O.landing(gs,anchor,refslot,branch(dict(sig,index=anchor),leg=f'{why}-{len(base["legs"])}'));_,when=O.block_at(dest)
  if target is not None and when<target:raise AssertionError('timer_fill_before_deadline')
  if dest<refslot or land<anchor:raise AssertionError('sell_before_trigger')
  if when>t['end_time']:return 'sell_outside_coverage'
  for k in range(j+1,land+1):
   e=advance(k)
   if e:return e
  amount=min(n,amount);q=quote(amount)
  if not q:
   # A pending curve sell that loses its venue retains custody, not a fake fill.
   if venue=='curve' and st['rtokens_raw']==0:
    fees+=FAILED;handled.add('pending_migration_exit');return 'migration_wait'
   return 'unquotable_own_sell'
  before=dict(st);got=proceeds(q);st=A.moved(st,q[1],amount,False) if venue=='curve' else M.moved(st,q,False,False);realized+=got;fees+=fee;n-=amount;lastpos=pos(gs,j,dest);lasttime=when
  base['legs'].append(dict(tokens=amount,proceeds=got,fee=fee,venue=venue,reason=why,trigger_slot=refslot,landing_slot=dest,position=lastpos,time=when,timer_target=target,state_before=before));return None
 opening_evaluation=False
 while n:
  k=j+1;targets=[];rule=sig['rule'];value=roi()
  if rule=='s1_dev_absorption' and not cfg.get('s1_dynamic_exit'):targets=[(tm+cfg.get('s1_timeout',6 if endpoint=='lower' else 8),'timeout')]
  if rule=='s1_dev_absorption' and cfg.get('s1_trough_grace') and 's1_grace_expired' not in handled:targets.append((tm+cfg['s1_trough_grace'],'s1_grace_expired'))
  if rule=='s4_upper_ath' and cfg.get('s4_rejection_grace') and 's4_grace_expired' not in handled:targets.append((tm+cfg['s4_rejection_grace'],'s4_grace_expired'))
  if rule=='s3_deadman':
   if cfg.get('s3_extended_hold'):
    if 'breathing_grace' not in handled:targets.append((tm+cfg.get('s3_grace',8),'breathing_grace'))
    targets.append((tm+cfg['s3_extended_hold'],'extended_timeout'))
   else:
    if 'scratch' not in handled:targets.append((tm+cfg.get('s3_scratch',10),'scratch'))
    if 'deadman' not in handled:targets.append((tm+21,'deadman'))
  if rule=='s4_upper_ath' and not cfg.get('s4_remove_short_timeout') and 'velocity_timeout' not in handled:targets=[(tm+cfg.get('s4_timeout',7 if endpoint=='lower' else 12),'velocity_timeout')]
  if rule=='s5_carryover' and migration_time is not None:targets=[(migration_time+(30 if endpoint=='lower' else 60),'amm_timeout')]
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
  if not opening_evaluation and (k>=len(gs) or gs[k]['time']>=target):
   if target>t['end_time']:return unresolved('coverage_before_requested_timer')
   if why=='coverage_horizon':return unresolved('runner_timeout_undefined')
   fireslot=max(W.timer_slot(t,slot,target),gs[j]['slot'],lastpos[0]);anchor=max(j,bisect.bisect_left([g['slot'] for g in gs],fireslot)-1)
   for z in range(j+1,anchor+1):
    e=advance(z)
    if e:return unresolved(e)
   handled.add(why);v=roi()
   if v is None:return unresolved('timer_unquotable_position')
   if why=='breathing_grace':
    if relative_stop_hit():why='relative_price_stop_after_grace'
    elif ratchet and (tailored_trail_hit(v,cfg['s3_dynamic_width']) if cfg.get('s3_dynamic_width') is not None else v<=peak-.08):why='runner_trail_after_grace'
    else:continue
   if why=='s1_grace_expired':
    current=st['vsol_raw']/st['vtokens_raw'] if venue=='curve' else (st['quote']+st['virtual'])/st['base']
    if v>-.10 and current>=sig['trough_spot']:continue
    why='floor_invalidation_after_grace'
   if why=='s4_grace_expired':
    if v>-cfg.get('s4_stop',.08) or fireslot<slot+2:continue
    why='breakout_rejected_after_grace'
   if why=='scratch' and v>.02:continue
   if why=='deadman' and v>=.15:continue
   if why=='velocity_timeout' and clip:continue
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
   if v<=-.10 or current<sig['trough_spot'] and lasttime>=tm+cfg.get('s1_trough_grace',0):why='floor_invalidation'
   elif cfg.get('s1_dynamic_exit') and not clip and v>=cfg.get('s1_target',.25):clip=True;amount=max(1,original*40//100);why='tailored_40pct_profit_target'
   elif cfg.get('s1_dynamic_exit') and clip and tailored_trail_hit(v,.15):why='tailored_runner_trail'
   elif cfg.get('s1_dynamic_exit'):pass
   elif v>=cfg.get('s1_target',.25 if endpoint=='lower' else .35):why='full_profit_target'
  elif rule=='s2_survival_shelf':
   ratchet=ratchet or v>=.10
   if venue=='curve' and st['rsol_raw']<=9_800_000_000:why='shelf_invalidation'
   elif ratchet and v<=0:why='breakeven_ratchet'
   elif cfg.get('s2_full_trail') and ratchet and 1+v<=(1+peak)*.92:why='full_runner_trail'
   elif cfg.get('s2_dynamic_exit') and not clip and v>=cfg.get('s2_target',.30):clip=True;amount=max(1,original*40//100);why='tailored_40pct_profit_target'
   elif cfg.get('s2_dynamic_exit') and clip and tailored_trail_hit(v,.15):why='tailored_runner_trail'
   elif not cfg.get('s2_dynamic_exit') and not cfg.get('s2_full_trail') and not clip and v>=.25:clip=True;amount=max(1,original//2);why='half_profit_target'
   elif not cfg.get('s2_dynamic_exit') and clip and 1+v<=(1+peak)*.92:why='runner_trail'
  elif rule=='s3_deadman':
   if (cfg.get('s3_extended_hold') or lasttime<=tm+20) and v>=cfg.get('s3_dynamic_arm',.20):ratchet=True
   if cfg.get('s3_emergency_reserve') is not None and venue=='curve' and st['rsol_raw']<round(cfg['s3_emergency_reserve']*L):why='catastrophic_reserve_floor'
   elif cfg.get('s3_full_target') is not None and v>=cfg['s3_full_target']:why='confirmed_profit_target'
   elif cfg.get('s3_relative_price_stop') is not None and lasttime>=tm+cfg.get('s3_grace',8) and relative_stop_hit():why='relative_price_stop'
   elif cfg.get('s3_half_target') is not None and not clip and v>=cfg['s3_half_target']:clip=True;amount=max(1,original//2);why='confirmed_half_target'
   elif clip and v<=peak-.08:why='runner_trail'
   elif ratchet and (tailored_trail_hit(v,cfg['s3_dynamic_width']) if cfg.get('s3_dynamic_width') is not None else v<=peak-.08) and (not cfg.get('s3_extended_hold') or lasttime>=tm+cfg.get('s3_grace',8)):why='runner_trail'
  elif rule=='s4_upper_ath':
   if gs[j]['slot']>=slot+2 and lasttime>=tm+cfg.get('s4_rejection_grace',0) and v<=-cfg.get('s4_stop',.08):why='breakout_rejected'
   elif not clip and v>=.20:clip=True;amount=max(1,original//2);why='half_profit_target'
   elif clip and 1+v<=(1+peak)*.94:why='runner_trail'
  elif rule=='s5_carryover':
   if venue=='curve' and st['rsol_raw']<=60_000_000_000:why='carryover_invalidation'
   elif venue=='amm' and not clip:clip=True;amount=max(1,original//2);why='AMM_open_half'
   elif venue=='amm' and clip and 1+v<=(1+peak)*.92:why='AMM_runner_trail'
  if why:
   e=execute(j,gs[j]['slot'],amount,why)
   if e=='migration_wait':continue
   if e:return unresolved(e)
 return dict(base,status='closed',net=realized-bill-fees,mark=0,remaining=0,close_position=lastpos,close_time=lasttime,counterparty_reverts=st.get('source_reverts',0))

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
