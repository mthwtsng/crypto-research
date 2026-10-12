"""Independent clock fixtures for user-requested relative stop and grace."""
import contextlib,unittest
from unittest.mock import patch
# Compile only the actual production simulation functions for independent
# mocked clock/quote fixtures. This does not validate missing real AMM adapters.
import ast,bisect,types
from pathlib import Path
source=Path(__file__).resolve().parents[1]/'core_plan_audit_20261007/engine.py'
tree=ast.parse(source.read_text())
functions=ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ['pos','simulate']],type_ignores=[])
noop=lambda *a,**k:None
E=types.ModuleType('fixture_engine')
E.__dict__.update(bisect=bisect,L=10**9,RENT=2039280,FAILED=505000,A=types.SimpleNamespace(buy=noop,fee=noop,moved=noop,apply=noop,sell=noop,build=types.SimpleNamespace(inventory=noop)),O=types.SimpleNamespace(branch=noop,landing=noop,block_at=noop),W=types.SimpleNamespace(timer_slot=noop),M=types.SimpleNamespace())
exec(compile(functions,str(source),'exec'),E.__dict__)
class RelativeStopTests(unittest.TestCase):
 def simulate(self,nextprice,cfg_extra=None,rule='s3_deadman',laterprice=None,trough=1,coverage=200):
  st=dict(vsol_raw=5000000,vtokens_raw=1,rsol_raw=10000000000,rtokens_raw=1000,fee_bps=0,creator_fee_bps=0)
  gs=[dict(signature='signal',slot=0,index=0,time=0,venue='curve',state=st,events=[]),dict(signature='move',slot=1,index=0,time=1,venue='curve',state=dict(st,vsol_raw=nextprice),events=[]),dict(signature='later',slot=20,index=0,time=20,venue='curve',state=dict(st,vsol_raw=laterprice or st['vsol_raw']),events=[])]
  t=dict(groups=gs,end_time=coverage,curve='fixture',inventory_key='wallet');s=dict(mint='fixture',signal_signature='signal',slot=0,time=0,rule=rule,trough_spot=trough)
  with contextlib.ExitStack() as x:
   x.enter_context(patch.object(E.O,'branch',return_value='fast'))
   x.enter_context(patch.object(E.O,'landing',side_effect=lambda gs,i,slot,b:(i,slot)))
   x.enter_context(patch.object(E.O,'block_at',side_effect=lambda slot:(None,slot)))
   x.enter_context(patch.object(E.W,'timer_slot',side_effect=lambda t,slot,target:target))
   x.enter_context(patch.object(E.A,'buy',return_value=(500000000,100)))
   x.enter_context(patch.object(E.A,'fee',return_value=0))
   x.enter_context(patch.object(E.A,'moved',side_effect=lambda st,*args:dict(st)))
   x.enter_context(patch.object(E.A.build,'inventory',return_value={}))
   x.enter_context(patch.object(E.A,'apply',side_effect=lambda st,g,h,cf:(dict(g['state']),h,cf,None,None)))
   x.enter_context(patch.object(E.A,'sell',side_effect=lambda st,n:(n*st['vsol_raw']//st['vtokens_raw'],0)))
   cfg=dict(s3_extended_hold=60,s3_grace=8,s3_full_target=.2,s3_relative_price_stop=.12);cfg.update(cfg_extra or {})
   return E.simulate(t,s,'fast','lower',.5,cfg=cfg)
 def test_stop_waits_for_grace_and_fires_in_quiet_market(self):
  r=self.simulate(4000000);self.assertEqual(r['status'],'closed')
  self.assertEqual(r['legs'][0]['reason'],'relative_price_stop_after_grace')
  self.assertEqual(r['legs'][0]['time'],8)
 def test_profit_target_remains_active_during_grace(self):
  r=self.simulate(6500000);self.assertEqual(r['status'],'closed')
  self.assertEqual(r['legs'][0]['reason'],'confirmed_profit_target')
  self.assertEqual(r['legs'][0]['time'],1)
 def test_s1_tailored_sale_preserves_exact_remainder(self):
  r=self.simulate(6500000,dict(s1_dynamic_exit=True),rule='s1_dev_absorption',laterprice=4800000)
  self.assertEqual(r['status'],'closed')
  self.assertEqual(r['legs'][0]['tokens'],40);self.assertEqual(r['legs'][1]['tokens'],60)
  self.assertEqual(r['legs'][1]['reason'],'tailored_runner_trail')
 def test_percentage_point_and_relative_trails_differ(self):
  cfg=dict(s3_full_target=None,s3_dynamic_arm=.75,s3_dynamic_width=.2,tailored_trail_basis='percentage_points')
  pp=self.simulate(15000000,cfg,laterprice=13900000)
  cfg['tailored_trail_basis']='relative'
  relative=self.simulate(15000000,cfg,laterprice=13900000)
  self.assertEqual(pp['legs'][0]['reason'],'runner_trail')
  self.assertEqual(relative['legs'][0]['reason'],'extended_timeout')
 def test_s1_trough_only_grace_waits_in_quiet_market(self):
  r=self.simulate(4800000,dict(s1_dynamic_exit=True,s1_trough_grace=6),rule='s1_dev_absorption',trough=4900000)
  self.assertEqual(r['legs'][0]['reason'],'floor_invalidation_after_grace')
  self.assertEqual(r['legs'][0]['time'],6)
 def test_s1_hard_loss_remains_active_during_trough_grace(self):
  r=self.simulate(4000000,dict(s1_dynamic_exit=True,s1_trough_grace=6),rule='s1_dev_absorption')
  self.assertEqual(r['legs'][0]['time'],1)
  self.assertEqual(r['legs'][0]['reason'],'floor_invalidation')
 def test_s1_profit_clip_remains_active_during_trough_grace(self):
  r=self.simulate(6500000,dict(s1_dynamic_exit=True,s1_trough_grace=6),rule='s1_dev_absorption',laterprice=4800000)
  self.assertEqual(r['legs'][0]['time'],1)
  self.assertEqual(r['legs'][0]['tokens'],40)
 def test_s4_profit_clip_remains_active_during_rejection_grace(self):
  r=self.simulate(6500000,dict(s4_remove_short_timeout=True,s4_rejection_grace=6),rule='s4_upper_ath')
  self.assertEqual(r['legs'][0]['time'],1)
  self.assertEqual(r['legs'][0]['tokens'],50)
 def test_s4_rejection_checks_grace_deadline_without_next_trade(self):
  r=self.simulate(4000000,dict(s4_remove_short_timeout=True,s4_rejection_grace=6),rule='s4_upper_ath')
  self.assertEqual(r['legs'][0]['reason'],'breakout_rejected_after_grace')
  self.assertEqual(r['legs'][0]['time'],6)
 def test_declared_runner_timeout_is_not_file_end_liquidation(self):
  r=self.simulate(5000000,dict(s1_dynamic_exit=True,runner_max_hold=600),rule='s1_dev_absorption',coverage=700)
  self.assertEqual(r['status'],'closed');self.assertEqual(r['legs'][0]['time'],600)
  self.assertEqual(r['legs'][0]['reason'],'runner_timeout')
if __name__=='__main__':unittest.main()
