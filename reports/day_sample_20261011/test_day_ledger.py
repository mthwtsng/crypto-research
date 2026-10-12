import unittest
import run_day as R

class FundedAccountingTests(unittest.TestCase):
 def options(self,rule,status='unresolved',signal=100,close=101):
  rows=[]
  for ticket in [.5,.25]:
   bill=round(ticket*1e9);fee=1505000
   r=dict(mint='m',rule=rule,signal_signature=rule+str(signal),ticket=ticket,fee=fee,time=signal,signal_position=(signal,0,0),entry_position=(signal,0,1),entry_time=signal,entry_bill=bill,status=status,legs=[])
   if status=='unresolved':r.update(net=-bill-fee-R.F.RENT,mark=bill+100000000,last_valid_position=(close,0,0),reason='runner_timeout_undefined')
   else:r.update(net=100000000,mark=0,legs=[dict(proceeds=bill+2*fee+100000000,fee=fee,position=(close,0,1),time=close)])
   rows.append(r)
  return rows

 def test_positive_open_mark_is_not_a_closed_win_or_loss(self):
  for fun in [R.F.funded,R.current_ledger()]:
   f=fun(self.options('s1_dev_absorption'),True,'portfolio',None)
   self.assertEqual(f['closed'],0);self.assertEqual(f['unresolved'],1)
   self.assertEqual(f['settled_net_SOL'],0)
   self.assertGreater(f['unresolved_marked_pnl_SOL'],0)
   self.assertEqual(f['last_valid_marked_net_SOL'],f['unresolved_marked_pnl_SOL'])
   self.assertIsNone(f['win_rate'])

 def test_current_lock_is_causal_after_delivered_close(self):
  rows=self.options('s1_dev_absorption','closed',100,101)+self.options('s4_upper_ath','closed',103,104)
  baseline=R.F.funded(rows,True,'portfolio',None)
  current=R.current_ledger()(rows,True,'portfolio',None)
  self.assertEqual(baseline['closed'],2);self.assertEqual(current['closed'],1)
  self.assertEqual(current['skipped']['mint_previously_closed'],1)
  self.assertEqual(current['settled_net_SOL'],.1)

 def test_canonical_scheduled_patch_anchor_compiles(self):
  self.assertTrue(callable(R.scheduled_canonical()))

if __name__=='__main__':unittest.main()
