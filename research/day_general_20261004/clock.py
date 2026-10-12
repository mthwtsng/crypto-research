"""Estimated-production-second timers; no within-slot clock inference."""
import threading
LOCK=threading.Lock();TIMES={};KEYLOCKS={}
def rpc(method,params):
 import collect
 return collect.rpc(method,params)
def time_at(slot):
 with LOCK:
  if slot in TIMES:return slot,TIMES[slot]
  kl=KEYLOCKS.setdefault(slot,threading.Lock())
 with kl:
  if slot in TIMES:return slot,TIMES[slot]
  for k in range(9):
   try:r=rpc('getBlock',[slot+k,dict(commitment='finalized',transactionDetails='none',rewards=False,maxSupportedTransactionVersion=1)])
   except Exception as e:
    if 'skipped'in str(e).lower() or '-32007'in str(e) or '-32009'in str(e):continue
    raise
   if r is not None and r.get('blockTime') is not None:
    with LOCK:TIMES[slot+k]=r['blockTime']
    return slot+k,r['blockTime']
  raise ValueError('no produced block in9slots')


def timer_slot(t,entry,target):
 gs=t['groups'];before=[g['slot'] for g in gs if g['slot']>=entry and g['block_time']<target];after=[g['slot'] for g in gs if g['slot']>=entry and g['block_time']>=target]
 lo=max(before,default=entry);hi=min(after,default=lo+max(8,round((target-time_at(lo)[1])/.25)+8))
 for _ in range(8):
  sh,th=time_at(hi)
  if th>=target:hi=sh;break
  hi=sh+max(8,round((target-th)/.25)+8)
 else:raise ValueError('timer bracket failed')
 while hi-lo>1:
  mid=(lo+hi)//2;sm,tm=time_at(mid)
  if sm>=hi:hi=sm;break
  if tm>=target:hi=sm
  else:lo=sm
 return time_at(hi)[0]
