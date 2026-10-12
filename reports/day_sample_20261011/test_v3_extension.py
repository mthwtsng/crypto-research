import copy, unittest
import curve_v3_extension as V
BASE=V.A.apply
EXT=V.install()

class ReceiptDispatchParity(unittest.TestCase):
 def fixture(self,name):
  st=dict(vsol_raw=30000000000,vtokens_raw=1073000000000000,rsol_raw=0,rtokens_raw=793100000000000,fee_bps=95,creator_fee_bps=30)
  q,n=V.A.buy_budget(st,500000000)
  if name in ('buy','buy_v2','buy_v3'):q=V.A.exact_buy(st,n)[0]
  after=V.A.moved(st,q,n)
  e=dict(buy=True,user='wallet',tokens_raw=n,sol_raw=q,fee_bps=95,creator_fee_bps=30,ix_name=name,max_cost_raw=500000000,budget_raw=500000000,min_tokens_raw=0)
  return st,dict(events=[e],state=after,custody_ops=[dict(kind='trade',owner='account',event=e)])

 def test_noncompletion_v3_matches_original_v2_quote_and_custody(self):
  for legacy,new in [('buy_v2','buy_v3'),('buy_exact_quote_in_v2','buy_exact_quote_in_v3')]:
   st,g=self.fixture(legacy);expected=BASE(st,g,{},{});modern=copy.deepcopy(g)
   modern['events'][0]['ix_name']=new
   actual=EXT(st,modern,{},{})
   self.assertEqual(expected[:3],actual[:3]);self.assertIsNone(actual[4])
   self.assertEqual(actual[0],g['state'])

 def test_v3_guard_reverts_atomically_and_retains_historical_custody(self):
  st,g=self.fixture('buy_v3');g['events'][0]['max_cost_raw']=1
  z,h,cf,adjusted,error=EXT(st,g,{},{})
  self.assertIsNone(error);self.assertEqual(adjusted['counterfactual_revert'],'max_cost')
  self.assertEqual(z['rsol_raw'],0);self.assertEqual(cf,{})
  self.assertGreater(h['account'],0);self.assertEqual(z['source_reverts'],1)

 def test_legacy_outputs_unchanged(self):
  for name in ['buy','buy_v2','buy_exact_sol_in','buy_exact_quote_in','buy_exact_quote_in_v2']:
   st,g=self.fixture(name)
   self.assertEqual(BASE(st,g,{},{}),EXT(st,g,{},{}))

if __name__=='__main__':unittest.main()
