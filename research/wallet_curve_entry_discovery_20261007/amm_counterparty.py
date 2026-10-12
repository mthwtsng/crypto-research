"""Approved AMM counterparty extension preserving counterfactual virtual reserves.

Historical per-event virtual reserves authenticate source parity; they cannot
reset a previously changed counterfactual reserve. Actual fee sweeps are replayed
in custody operation order. Source LP actions remain explicit unsupported cases.
"""
import pathlib,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'amm_multiday_20261006'))
import amm_adapter as A

def moved(st,r,buying,deferred=False):
 z=A.moved(st,r,buying,deferred)
 if deferred:
  payout=0 if not isinstance(deferred,dict) else r['protocol']*deferred['buyback_bps']//10000+A.fee(r['q'],deferred['cashback_bps'])
  retained=r['protocol']+r['creator']-payout
  z['virtual']=z.get('virtual',0)-retained
 return z

def advance(st,g,h,cf):
 if g.get('custody_error'):return st,h,cf,'unverified_transaction_custody'
 if g['other_liquidity_events']:return st,h,cf,'unsupported_counterfactual_LP_action'
 z=dict(st);historical=dict(h);inventory=dict(cf)
 ops=g.get('custody_ops',[dict(kind='trade',event=e) for e in g['trades']])
 touched=set()
 for op in ops:
  if op['kind']=='sweep':continue
  if op['kind']=='trade':
   e=op['event']
   if not (e['zero_fee'] and e['account']=='11111111111111111111111111111111'):touched.add(e['account'])
  else:touched.update(ac for ac in [op['source'],op.get('destination')] if ac)
 for ac in touched:
  old=g['tokenpre'].get(ac,0)
  if ac not in historical:historical[ac]=old;inventory[ac]=old
  else:
   # A source buy may have reverted in the counterfactual curve branch.
   # Historical custody then knows this account while CF custody correctly
   # has no tokens/key. Its subsequent AMM buy must start from zero.
   inventory.setdefault(ac,0)
   if historical[ac]!=old:
    if inventory[ac]!=historical[ac]:return st,h,cf,'counterfactual_inventory_transfer_gap'
    historical[ac]=old;inventory[ac]=old
 original_cf=dict(inventory);start_h=dict(historical)
 # Advance the historical branch independently, including every ordered transfer.
 for op in ops:
  if op['kind']=='sweep':continue
  if op['kind']=='trade':
   e=op['event'];ac=e['account']
   if e['zero_fee'] and ac=='11111111111111111111111111111111':continue
   historical[ac]+=e['n'] if e['buy'] else -e['n']
  else:
   historical[op['source']]-=op['raw']
   if op.get('destination'):historical[op['destination']]+=op['raw']
 hh=start_h
 for op in ops:
  if op['kind']=='sweep':
   if op['raw']>z['quote']:return st,h,cf,'counterfactual_fee_sweep_liquidity'
   z['quote']-=op['raw'];z['virtual']+=op['raw'];continue
  if op['kind']!='trade':
   ac=op['source'];old=hh[ac];raw=op['raw'];held=inventory[ac]
   if old<=0 and raw:return st,h,cf,'invalid_transfer_inventory'
   n=held if raw==old else held*raw//old if old else 0
   hh[ac]-=raw;inventory[ac]-=n
   if op.get('destination'):hh[op['destination']]+=raw;inventory[op['destination']]+=n
   else:z['supply_diff']=z.get('supply_diff',0)+raw-n
   continue
  e=op['event'];ac=e['account'];old=e['prehold'];obs=e['n'];burn=e['zero_fee'] and ac=='11111111111111111111111111111111'
  supply_diff=z.get('supply_diff',0);z['supply']=e['supply']+supply_diff
  val=dict(z,historical_rates=[0,0,0]) if e['zero_fee'] else z
  if e['buy']:
   r=A.buy(val,e['gross']) if e['ix'].startswith('buy_exact_quote_in') else A.exact_buy(val,obs)
   failed=not r or (e['ix'] in ['buy','buy_v2'] and r['total']>e.get('max_quote',10**30)) or (e['ix'].startswith('buy_exact_quote_in') and r['n']<e.get('min_base',0))
   if failed:return dict(st,source_reverts=st.get('source_reverts',0)+1),historical,original_cf,None
   if burn:z['supply_diff']=supply_diff+obs-r['n'];z['supply']=e['supply']+z['supply_diff']
   else:hh[ac]+=obs;inventory[ac]+=r['n']
   z=moved(z,r,True,e.get('deferred',False))
  else:
   held=inventory[ac];n=held if obs==old else held*obs//old
   r=A.sell(val,n)
   if not r or r['total']<e.get('min_quote',0):return dict(st,source_reverts=st.get('source_reverts',0)+1),historical,original_cf,None
   hh[ac]-=obs;inventory[ac]-=n;z=moved(z,r,False,e.get('deferred',False))
 return z,historical,inventory,None
