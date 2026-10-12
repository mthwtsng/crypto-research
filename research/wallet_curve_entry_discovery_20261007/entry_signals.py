"""Four bounded wallet-inspired hypotheses. Only complete transaction prefixes."""
import collections
RULES=('broad_recovery','fresh_expansion','quiet_absorption','late_continuation')
def extract(t):
 if not t.get('normal'):return []
 gs=t['groups'];seen=set();events=[];prices=[];buyers=set();out=[]
 for i,g in enumerate(gs):
  if g['state']['rtokens_raw']<=0:break
  now=g['block_time'];age=now-t['creation_time'];fresh_this=set()
  for e in g['events']:
   if e['user']==t['creator']:continue
   if e['buy'] and e['sol_raw']>=50_000_000:
    if e['user'] not in buyers:fresh_this.add(e['user'])
    buyers.add(e['user'])
   events.append(dict(e,time=now,index=i))
  price=g['state']['vsol_raw']/g['state']['vtokens_raw'];prices.append((now,i,price))
  recent=[e for e in events if now-4<=e['time']<=now];prior=[e for e in events if now-8<=e['time']<now-4]
  def bucket(es):
   b=collections.Counter()
   for e in es:
    if e['buy'] and e['sol_raw']>=50_000_000:b[e['user']]+=e['sol_raw']
   return b,sum(e['sol_raw']*(1 if e['buy'] else -1) for e in es)
  rb,net=bucket(recent);pb,pnet=bucket(prior);old={e['user'] for e in events if e['buy'] and e['sol_raw']>=50_000_000 and e['time']<now-4};fresh=len(set(rb)-old);total=sum(rb.values());dominance=max(rb.values())/total if total else 1
  r=g['state']['rsol_raw']/1e9
  peak=max(p for tm,_,p in prices if tm>=now-30);dd=1-price/peak
  lows=[(p,j) for tm,j,p in prices if tm>=now-8];low,li=min(lows)
  after=[e for e in recent if e['index']>li and e['buy'] and e['sol_raw']>=50_000_000];ab={e['user'] for e in after};av=sum(e['sol_raw'] for e in after)
  isbuy=any(e['buy'] and e['user']!=t['creator'] and e['sol_raw']>=50_000_000 for e in g['events'])
  tests={
   'broad_recovery':age>=15 and 5<=r<=35 and len(buyers)>=20 and dd>=.15 and price>=low*1.03 and len(ab)>=3 and av>=750_000_000 and fresh>=2 and dominance<=.5 and isbuy,
   'fresh_expansion':age>=15 and 8<=r<=45 and len(buyers)>=20 and len(rb)>=4 and len(pb)>=3 and fresh>=3 and net>=1_000_000_000 and pnet>0 and dominance<=.5 and isbuy,
   'quiet_absorption':age>=60 and 8<=r<=35 and len(buyers)>=40 and .10<=dd<=.45 and 1<=len(rb)<=4 and len(pb)<=2 and net>0 and price>=low*1.02 and isbuy,
   'late_continuation':age>=15 and 68<=r<=82 and len(buyers)>=40 and len(rb)>=3 and fresh>=2 and net>=1_000_000_000 and dominance<=.5 and isbuy}
  for rule,ok in tests.items():
   if ok and rule not in seen:
    seen.add(rule);out.append(dict(rule=rule,index=i,slot=g['slot'],time=now,mint=t['mint'],reserve_SOL=r,age=age,breadth=len(buyers),recent_buyers=len(rb),fresh_buyers=fresh,drawdown=dd,dominance=dominance))
 return out
