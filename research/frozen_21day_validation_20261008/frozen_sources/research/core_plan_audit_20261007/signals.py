"""Causal interpretation of FINAL_CORE_STRATEGY_AND_CIRCUIT_BREAKER_PLAN.

One signal per family/mint. Holder balances include observed transfers; unseen
associated developer wallets are unknown, not assumed to be cleared.
"""
import collections,gzip,json,pathlib,pickle,sys,hashlib
P=pathlib.Path(__file__).resolve().parent;ROOT=P.parents[1]
sys.path.insert(0,str(ROOT/'research/day_general_20261004/helpers'));import build

def spot(st):return st['vsol_raw']/st['vtokens_raw']
def demand(t,i):
 """Outside wallet-level demand known after the complete signal transaction.

 Four slots include current and three preceding slots. First-time means no
 observed earlier buy, including tiny buys; addresses are not assumed to be
 independent people or unrelated funding clusters.
 """
 dev=t['creator'];start=t['groups'][i]['slot']-3;by=collections.Counter();sold=0;old=set()
 for g in t['groups'][:i+1]:
  for e in g['events']:
   if e['user']==dev:continue
   if g['slot']<start:
    if e['buy']:old.add(e['user'])
   elif e['buy']:by[e['user']]+=e['sol_raw']
   else:sold+=e['sol_raw']
 total=sum(by.values());qualified={w for w,n in by.items() if n>=50_000_000}
 return dict(buyers=len(qualified),first_time_buyers=len(qualified-old),buy_raw=total,sell_raw=sold,largest_share=max(by.values(),default=0)/total if total else 1.,sell_buy_ratio=sold/total if total else None)

def detect(t,cfg=None):
 cfg=cfg or {}
 if not t['normal']:return [],[]
 h=collections.Counter();buyers=set();seen=set();out=[];errors=[];dev=t['creator'];devbought=0;devsold=0;prior=[];lastoutside=[];low=None;lowindex=0;peak=0.;prevr=0.
 for i,g in enumerate(t['groups']):
  if g['state']['rtokens_raw']==0:break
  for op in build.ops(g):
   if op['kind']=='trade':
    e=op['event'];w=op['owner'];h[w]+=e['tokens_raw'] if e['buy'] else -e['tokens_raw']
    if w==dev:
     if e['buy']:devbought+=e['tokens_raw']
     else:devsold+=e['tokens_raw']
   elif op['kind']=='transfer':
    if op['from_owner']!=op['to_owner']:h[op['from_owner']]-=op['raw'];h[op['to_owner']]+=op['raw']
   else:errors.append(dict(index=i,reason='unknown_custody_op'));return out,errors
  if min(h.values(),default=0)<0:errors.append(dict(index=i,reason='source_inventory_gap'));return out,errors
  st=g['state'];r=st['rsol_raw']/1e9;s=spot(st);tm=g['block_time'];age=tm-t['creation_time']
  # A post-dump trough is measured after the preceding peak, not against
  # the launch's initial low (which would silently discard ordinary dips).
  if s>=peak:peak=s;low=s;lowindex=i
  outside=[e for e in g['events'] if e['user']!=dev]
  for e in outside:
   if e['buy'] and e['sol_raw']>=50_000_000:buyers.add(e['user'])
  buys=[e for e in outside if e['buy']]
  if g['events']:lastoutside.append(bool(buys) and not any(not e['buy'] for e in g['events']));lastoutside=lastoutside[-2:]
  if low is None or s<low:low=s;lowindex=i
  after=[e for gg in t['groups'][lowindex+1:i+1] if gg['slot']<=t['groups'][lowindex]['slot']+3 for e in gg['events'] if e['buy'] and e['user']!=dev]
  local=[z for time,z in prior if time>=tm-30];localhigh=max(local,default=0.)
  circulating=sum(max(0,n) for n in h.values());holdercount=sum(n>0 for n in h.values());topshare=max(h.values(),default=0)/circulating if circulating else 1.
  # Exhaustion must follow an observed creator allocation and sale. A zero
  # genesis allocation is not evidence of a full developer liquidation.
  tests={
   's1_dev_absorption': devbought>0 and devsold>0 and (h[dev]==0 or devsold>=.95*devbought) and 1<=r<=5 and .25<=1-s/peak<=.60 and g['slot']<=t['groups'][lowindex]['slot']+3 and len({e['user'] for e in after})>=2 and sum(e['sol_raw'] for e in after)>=300_000_000,
   's2_survival_shelf': prevr<10.8<=r<=14 and age>=30 and len(buyers)>=25 and topshare<=.20 and len(lastoutside)==2 and all(lastoutside) and s>localhigh,
   's3_deadman':8<=r<=18 and len(buyers)>=2 and bool(prior) and s<=prior[-1][1]*.85 and any(not e['buy'] and e['sol_raw']>=1_500_000_000 for e in outside),
   's4_upper_ath':16<=r<=22 and s>max((z for _,z in prior),default=0.) and len(buyers)>=22 and any(e['sol_raw']>=1_000_000_000 for e in buys),
   's5_carryover':prevr<72<=r and holdercount>=100 and sum((e['sol_raw'] if e['buy'] else -e['sol_raw']) for gg in t['groups'][:i+1] if gg['slot']>=g['slot']-4 for e in gg['events'] if e['user']!=dev)>0
  }
  if cfg.get('demand_gate') and any(tests[r] for r in ['s2_survival_shelf','s4_upper_ath']):
   f=demand(t,i);quality=f['buyers']>=3 and f['largest_share']<=.5 and f['sell_buy_ratio'] is not None and f['sell_buy_ratio']<=.5
   if cfg.get('first_time_gate'):quality=quality and f['first_time_buyers']>=2
   for rule in ['s2_survival_shelf','s4_upper_ath']:tests[rule]=tests[rule] and quality
  for rule,yes in tests.items():
   if yes and rule not in seen:
    seen.add(rule);out.append(dict(mint=t['mint'],curve=t['curve'],rule=rule,index=i,slot=g['slot'],time=tm,signal_signature=g['signature'],reserve=r,age_seconds=age,outside_buyers=len(buyers),holders=holdercount,top_holder_share=topshare,trough_spot=low))
  prevr=r;prior.append((tm,s))
 return out,errors

def main():
 tapes=pickle.load(gzip.open(ROOT/'research/day_general_20261004/TAPES.pkl.gz','rb'));rows=[];errors=[]
 for t in tapes:
  ss,ee=detect(t);rows+=ss;errors.extend(dict(mint=t['mint'],**e) for e in ee)
 (P/'SIGNALS.json').write_text(json.dumps(rows,indent=2)+'\n')
 summary=dict(coins=len(tapes),dates=dict(collections.Counter(t['date'] for t in tapes)),signals=dict(collections.Counter(s['rule'] for s in rows)),eligible_mints=len({s['mint'] for s in rows}),errors=errors)
 (P/'SIGNAL_AUDIT.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
