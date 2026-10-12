"""Regression tests for demonstrated custody/reserve/atomicity failures."""
import unittest
import amm_counterparty as C
import curve_adapter as A
from repair_amm_custody import custody,TOKENS
from failed_order_checks import check,PUMP

class ReplayRepairs(unittest.TestCase):
 def test_deferred_fees_keep_effective_reserves_consistent(self):
  st=dict(base=200_000_000_000_000,quote=70_000_000_000,virtual=17_000_000_000,supply=10**15)
  r=C.A.buy(st,500_000_000);deferred=dict(buyback_bps=5000,cashback_bps=0)
  z=C.moved(st,r,True,deferred)
  self.assertEqual(z['quote']+z['virtual'],st['quote']+st['virtual']+r['q']+r['lp'])
  self.assertLess(z['virtual'],st['virtual'])

 def test_deferred_fee_rounding_uses_original_quote_components(self):
  # Authenticated Ad3gZohC exact-input receipt: fee calculation precedes
  # a one-lamport net-input correction. Recomputing from adjusted q loses 1.
  st=dict(base=200_000_000_000_000,quote=70_000_000_000,virtual=17_546_125_467,historical_rates=[20,5,95])
  r=C.A.buy(st,191_738_954)
  self.assertEqual((r['q'],r['creator']),(189_465_368,1_799_922))
  z=C.moved(st,r,True,dict(buyback_bps=5000,cashback_bps=0))
  self.assertEqual(st['virtual']-z['virtual'],1_847_289)

 def test_next_swap_preserves_counterfactual_virtual_difference(self):
  source=dict(base=200_000_000_000_000,quote=70_000_000_000,virtual=17_000_000_000,supply=10**15)
  own=C.moved(source,C.A.buy(source,500_000_000),True,dict(buyback_bps=5000,cashback_bps=0));q=C.A.buy(source,100_000_000)
  e=dict(buy=True,account='trader',n=q['n'],gross=q['total'],prehold=0,ix='buy_exact_quote_in',zero_fee=False,virtual=source['virtual'],supply=source['supply'],min_base=0,deferred=False)
  g=dict(custody_error=None,other_liquidity_events=[],tokenpre={'trader':0},trades=[e],custody_ops=[dict(kind='trade',event=e)])
  z,h,cf,err=C.advance(own,g,{},{});self.assertIsNone(err);self.assertEqual(z['virtual'],own['virtual'])

 def test_closed_temporary_account_transfer_is_retained(self):
  token=next(iter(TOKENS));mint='mint';tr=[dict(account='temporary',buy=True,n=25,prehold=0,zero_fee=False)]
  # A direct AMM swap plus unchecked transfer from its temporary output account.
  from repair_amm_custody import B
  data=B.A.D.b58(next(d for d,n in B.METHODS.items() if n=='buy'))
  tx=dict(transaction=dict(message=dict(instructions=[dict(programId=B.A.AMM,data=data,accounts=['pool']),dict(programId=token,parsed=dict(type='transfer',info=dict(source='temporary',destination='recipient',amount='25')))])),meta=dict(innerInstructions=[]))
  g=dict(tokenpre={},tokenpost={'recipient':25},raw_events=[]);ops,err=custody(tx,dict(pool='pool',mint=mint,base_vault='vault'),tr,g)
  self.assertIsNone(err);self.assertEqual([o['kind'] for o in ops],['trade','transfer'])

 def test_AMM_buy_after_reverted_curve_buy_starts_from_zero(self):
  st=dict(base=200_000_000_000_000,quote=70_000_000_000,virtual=17_000_000_000,supply=10**15)
  r=C.A.buy(st,100_000_000)
  e=dict(buy=True,account='trader',n=r['n'],gross=r['total'],prehold=25,ix='buy_exact_quote_in',zero_fee=False,virtual=st['virtual'],supply=st['supply'],min_base=0,deferred=False)
  g=dict(custody_error=None,other_liquidity_events=[],tokenpre={'trader':25},trades=[e],custody_ops=[dict(kind='trade',event=e)])
  z,h,cf,err=C.advance(st,g,{'trader':25},{})
  self.assertIsNone(err);self.assertEqual(h['trader'],25+r['n']);self.assertEqual(cf['trader'],r['n'])

 def test_routed_failed_order_is_not_promoted_to_fill(self):
  g=dict(source_status='failed',failed_intents=[dict(parent_program='router',inner_index=0)])
  result=check({},g);self.assertEqual(result['status'],'unmodeled_router');self.assertFalse(result['committed'])

 def test_curve_transaction_guard_rolls_back_all_swaps(self):
  st=dict(vsol_raw=40_000_000_000,vtokens_raw=800_000_000_000_000,rsol_raw=10_000_000_000,rtokens_raw=520_100_000_000_000,fee_bps=95,creator_fee_bps=30)
  e=dict(buy=True,ix_name='buy',tokens_raw=10_000_000,sol_raw=1,fee_bps=95,creator_fee_bps=30,max_cost_raw=10**12,user='alice')
  doomed=dict(e,user='bob',max_cost_raw=0)
  g=dict(events=[e,doomed],custody_ops=[dict(kind='trade',owner='alice',event=e),dict(kind='trade',owner='bob',event=doomed)])
  z,h,cf,ag,err=A.apply(st,g,{},{});self.assertIsNone(err);self.assertEqual(cf,{});self.assertEqual(z['vsol_raw'],st['vsol_raw']);self.assertEqual(ag['counterfactual_revert'],'max_cost');self.assertEqual(h,dict(alice=e['tokens_raw'],bob=e['tokens_raw']))

if __name__=='__main__':unittest.main()
