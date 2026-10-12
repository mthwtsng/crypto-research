"""Receipt-checked extension of approved day_general integer/custody mechanics."""
import pathlib,sys
R=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(R/'research/day_general_20261004/helpers'))
import replay as BASE,build
fee=BASE.fee;moved=BASE.moved;sell=BASE.sell

def exact_buy(st,n):
 if n<=0 or n>=st['vtokens_raw'] or n>st['rtokens_raw'] or st['rtokens_raw']==0:return None
 return st['vsol_raw']*n//(st['vtokens_raw']-n)+1,n

def exact_net_buy(st,q):
 if q<=1 or st['rtokens_raw']==0:return None
 n=st['vtokens_raw']*(q-1)//(st['vsol_raw']+q-1)
 if n>st['rtokens_raw']:return exact_buy(st,st['rtokens_raw'])
 return (q,n) if n>0 else None

def buy(st,ticket):
 return buy_budget(st,round(ticket*1e9))

def buy_budget(st,budget):
 if not isinstance(budget,int) or budget<=0:return None
 lo,hi=0,budget
 while lo<hi:
  q=(lo+hi+1)//2
  if q+fee(q,st['fee_bps'])+fee(q,st['creator_fee_bps'])<=budget:lo=q
  else:hi=q-1
 return exact_net_buy(st,lo)

def apply(st,group,hist,cf):
 """Recorded intents, scaled custody, atomic guard reverts, historical branch retained."""
 if group.get('custody_error'):return st,hist,cf,None,'unverified_custody'
 z=dict(st);h=dict(hist);c=dict(cf);ops=build.ops(group);historical=dict(hist)
 # Historical custody always follows the authenticated original transaction,
 # even when our intervention causes that original intent to revert.
 for op in ops:
  if op['kind']=='trade':
   e=op['event'];w=op['owner'];historical[w]=historical.get(w,0)+(e['tokens_raw'] if e['buy'] else -e['tokens_raw'])
  elif op['kind']=='transfer':
   src,dst,n=op['from_owner'],op['to_owner'],op['raw'];historical[src]=historical.get(src,0)-n;historical[dst]=historical.get(dst,0)+n
  else:return st,hist,cf,None,'unsupported_custody_op'
 if any(v<0 for v in historical.values()):return st,hist,cf,None,'source_inventory_gap'
 adjusted=[];adjusted_ops=[]
 def revert(why):return dict(st,source_reverts=st.get('source_reverts',0)+1),historical,dict(cf),dict(group,events=[],custody_ops=[],state=dict(st),counterfactual_revert=why),None
 for op in ops:
  if op['kind']=='transfer':
   src,dst,raw=op['from_owner'],op['to_owner'],op['raw']
   if src==dst or raw==0:continue
   old=h.get(src,0);held=c.get(src,0)
   if old<=0 or raw>old:return st,hist,cf,None,'source_inventory_gap'
   n=held if raw==old else held*raw//old
   h[src]-=raw;h[dst]=h.get(dst,0)+raw;c[src]=held-n;c[dst]=c.get(dst,0)+n;adjusted_ops.append(dict(op,raw=n));continue
  e=op['event'];w=op['owner'];old=h.get(w,0);held=c.get(w,0)
  z['fee_bps']=e['fee_bps'];z['creator_fee_bps']=e['creator_fee_bps']
  if z['rtokens_raw']==0:return revert('curve_complete')
  if e['buy']:
   name=e['ix_name']
   if name in ('buy','buy_v2'):
    r=exact_buy(z,e['tokens_raw'])
    if not r:return revert('insufficient_remaining_curve_tokens')
    q,n=r;gross=q+fee(q,z['fee_bps'])+fee(q,z['creator_fee_bps'])
    if gross>e.get('max_cost_raw',10**30):return revert('max_cost')
   elif name in ('buy_exact_sol_in','buy_exact_quote_in','buy_exact_quote_in_v2'):
    # Net is computed from the original instruction's gross budget, retaining
    # its fee policy. Completing partial fills may spend less than the budget.
    budget=e.get('budget_raw',e['sol_raw']+fee(e['sol_raw'],z['fee_bps'])+fee(e['sol_raw'],z['creator_fee_bps']))
    r=buy_budget(z,budget)
    if not r:return revert('unquotable_exact_input')
    q,n=r
    if n<e.get('min_tokens_raw',0):return revert('min_tokens')
   else:return st,hist,cf,None,'unsupported_buy_instruction'
   z=moved(z,q,n);h[w]=old+e['tokens_raw'];c[w]=held+n
  else:
   obs=e['tokens_raw']
   if old<=0 or obs>old:return st,hist,cf,None,'source_inventory_gap'
   n=held if obs==old else held*obs//old
   quote=sell(z,n)
   if not quote:return revert('sell_liquidity')
   if quote[0]<e.get('min_quote_raw',0):return revert('min_quote')
   q=quote[1];z=moved(z,q,n,False);h[w]=old-obs;c[w]=held-n
  ae=dict(e,tokens_raw=n,sol_raw=q,inventory_owner=w);adjusted.append(ae);adjusted_ops.append(dict(op,event=ae))
 return z,h,c,dict(group,events=adjusted,custody_ops=adjusted_ops,state=z),None
