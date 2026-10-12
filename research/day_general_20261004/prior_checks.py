import unittest
from unittest.mock import patch
import base_engine as C
class Checks(unittest.TestCase):
 def toy(self):
  st=dict(vsol_raw=30_000_000_000,vtokens_raw=1_073_000_000_000_000,rsol_raw=0,rtokens_raw=793_100_000_000_000,fee_bps=95,creator_fee_bps=30);gs=[]
  for i,(w,x)in enumerate([('D',3),('A',5)]):
   q,n=C.T.R.buy(st,x);st=C.T.R.moved(st,q,n);e=dict(user=w,buy=True,sol_raw=q,tokens_raw=n,ix_name='buy_exact_sol_in',fee_bps=95,creator_fee_bps=30);gs.append(dict(slot=100+i,block_time=1000+i,state=dict(st),signature=str(i),events=[e]))
  return dict(mint='toy',creator='D',creation_slot=100,creation_time=1000,end_time=1200,date='2026-10-03',groups=gs),dict(rule='velocity',index=1,slot=101,ticket=.5)
 def test_sale_reduces_sol_restores_tokens(self):
  t,_=self.toy();st=t['groups'][-1]['state'];q,n=C.T.R.buy(st,.5);b=C.T.R.moved(st,q,n);out=C.T.R.sell(b,n);s=C.T.R.moved(b,out[1],n,False)
  self.assertLess(s['rsol_raw'],b['rsol_raw']);self.assertGreater(s['rtokens_raw'],b['rtokens_raw']);self.assertEqual(s['rtokens_raw'],st['rtokens_raw'])
 def test_timer_closes_without_later_trade(self):
  t,s=self.toy()
  with patch.object(C.W,'time_at',side_effect=lambda slot:(slot,1000+slot-100)),patch.object(C.W,'timer_slot',side_effect=lambda t,e,target:e+10):r=C.replay((t,s,'next_slot_tail','full_timer'))
  self.assertEqual(r['status'],'closed');self.assertEqual(r['settle_slot'],115);self.assertLess(r['pnl'],0)
 def test_missing_timer_coverage_never_fabricates_fill(self):
  t,s=self.toy();t['end_time']=1005
  with patch.object(C.W,'time_at',side_effect=lambda slot:(slot,1000+slot-100)),patch.object(C.W,'timer_slot',side_effect=lambda t,e,target:e+10):r=C.replay((t,s,'next_slot_tail','full_timer'))
  self.assertEqual(r['status'],'missing');self.assertIsNone(r['pnl'])
 def test_next_slot_guard_uses_intervening_buy(self):
  t,s=self.toy();st=t['groups'][-1]['state'];q,n=C.T.R.buy(st,5);st=C.T.R.moved(st,q,n);e=dict(user='B',buy=True,sol_raw=q,tokens_raw=n,ix_name='buy_exact_sol_in',fee_bps=95,creator_fee_bps=30);t['groups'].append(dict(slot=102,block_time=1002,state=st,events=[e]))
  r=C.replay((t,s,'next_slot_tail','full_timer'));self.assertEqual(r['status'],'failed');self.assertEqual(r['reason'],'entry_guard');self.assertEqual(r['pnl'],-.000505)
 def test_real_signal_prefix_invariance(self):
  checked=0
  for t in C.A.selected(C.A.load()):
   if not t['normal']:continue
   for s in C.detect(t):
    short=dict(t,groups=t['groups'][:s['index']+1]);self.assertIn(s,C.detect(short));checked+=1
    if checked>=30:break
   if checked>=30:break
  self.assertGreaterEqual(checked,30)
