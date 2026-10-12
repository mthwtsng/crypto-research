"""Fail-closed diagnostics for public landed-failed curve transactions.

This module never commits a resurrected swap from a quote alone. It separates
orders which still fail an authenticated Pump limit from orders requiring
wrapper, funding or whole-transaction execution evidence.
"""
import collections
import curve_adapter as A
PUMP='6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P'
COMPUTE='ComputeBudget111111111111111111111111111111'

def check(st,group):
 if group.get('source_status')!='failed':raise ValueError('expected_failed_receipt')
 intents=group.get('failed_intents',[])
 if not intents:return dict(status='unmodeled_outer_program',committed=False)
 if any(i['parent_program']!=PUMP or i['inner_index']!=-1 for i in intents):
  return dict(status='unmodeled_router',committed=False)
 if len(intents)!=1:return dict(status='unmodeled_atomic_multi_trade',committed=False)
 i=intents[0];name=i['instruction'];accounts=i['accounts']
 if not accounts:return dict(status='missing_instruction_account_schema',committed=False)
 if name.endswith('_v3'):return dict(status='unmodeled_v3_pool_leg',committed=False)
 if st['rtokens_raw']==0:return dict(status='known_still_failed',reason='curve_complete',committed=False)
 if name.startswith('buy_exact'):
  r=A.buy_budget(st,i['args'][0])
  if not r:return dict(status='known_still_failed',reason='unquotable_buy',committed=False)
  if r[1]<i['args'][1]:return dict(status='known_still_failed',reason='min_tokens',committed=False)
 elif name.startswith('buy'):
  r=A.exact_buy(st,i['args'][0])
  if not r:return dict(status='known_still_failed',reason='remaining_supply',committed=False)
  q,n=r;gross=q+A.fee(q,st['fee_bps'])+A.fee(q,st['creator_fee_bps'])
  if gross>i['args'][1]:return dict(status='known_still_failed',reason='max_cost',committed=False)
 else:return dict(status='sell_requires_counterfactual_account_inventory',committed=False)
 q,n=r;gross=q+A.fee(q,st['fee_bps'])+A.fee(q,st['creator_fee_bps'])
 # Passing quotes are not fills: account existence, cash, source fee tiers,
 # instructions after the original failure and compute limits remain relevant.
 return dict(status='quote_passes_requires_atomic_execution',committed=False,q=q,n=n,gross=gross,actor=accounts.get('user'),token_account=accounts.get('associated_base_user',accounts.get('associated_user')),completes=n==st['rtokens_raw'])

def annotate(paths,tapes):
 out=[]
 for p in paths:
  if p['scenario']!='central85' or p.get('migration_eligibility')!='recorded_completion_displaced':continue
  gs=tapes[p['mint']]['groups'];completion=p['historical_completion_time'];counts=collections.Counter();examples=[]
  for g in gs:
   if g['source_status']!='failed' or g['block_time']<completion:continue
   result=check(p['last_state'],g);counts[result['status']]+=1
   if result['status']=='quote_passes_requires_atomic_execution' and len(examples)<5:examples.append(dict(result,signature=g['signature'],slot=g['slot'],index=g['index']))
  out.append(dict(mint=p['mint'],rule=p['rule'],counts=dict(counts),examples=examples))
 return out
