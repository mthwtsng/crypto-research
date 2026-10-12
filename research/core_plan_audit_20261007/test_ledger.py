import unittest
from ledger import funded,L,RENT

def trade(mint,signal,entry,close,net,rule='s1_dev_absorption',ticket=.5,status='closed',legs=None):
 bill=round(ticket*L);fee=1505000
 if legs is None:legs=[dict(position=[close,0,1],time=close,proceeds=bill+2*fee+net,fee=fee)] if status=='closed' else []
 return dict(mint=mint,rule=rule,signal_signature=mint,time=signal,signal_position=[signal,0,0],entry_position=[entry,0,1],entry_time=entry,entry_bill=bill if status!='failed' else 0,ticket=ticket,fee=fee,legs=legs,status=status,net=net,mark=0,close_time=close,last_valid_position=[close,0,1])

def options(r):return [r,dict(r,ticket=.25,entry_bill=250000000,net=-505000,status='failed',legs=[])]

class LedgerTests(unittest.TestCase):
 def test_unlimited_retains_unresolved_and_admits_more(self):
  rows=sum((options(trade(str(i),i,i+1,100,-501505000-RENT,status='unresolved')) for i in [1,3,5]),[])
  r=funded(rows,position_limit=None)
  self.assertEqual(r['attempts'],3);self.assertEqual(r['unresolved'],3)
  self.assertEqual(r['max_open'],3);self.assertNotIn('concurrency',r['skipped'])
  self.assertAlmostEqual(r['ending_cash_SOL'],15-3*(.501505+RENT/L))
 def test_profitable_unresolved_mark_is_not_a_settled_loss(self):
  x=trade('open',1,2,100,-501505000-RENT,status='unresolved')
  x['mark']=610000000
  r=funded(options(x),position_limit=None)
  self.assertEqual(r['settled_net_SOL'],0)
  self.assertAlmostEqual(r['unresolved_marked_pnl_SOL'],.610-.501505-RENT/L)
  self.assertEqual(r['unresolved'],1);self.assertEqual(r['closed'],0)
  self.assertIsNone(r['win_rate']);self.assertTrue(r['unresolved_excluded_from_win_loss'])
  self.assertAlmostEqual(r['last_valid_marked_net_SOL'],r['settled_net_SOL']+r['unresolved_marked_pnl_SOL'])
 def test_unlimited_still_requires_cash(self):
  rows=sum((options(trade(str(i),i*2,i*2+1,100,-501505000-RENT,status='unresolved')) for i in range(40)),[])
  r=funded(rows,position_limit=None)
  self.assertEqual(r['attempts'],29);self.assertEqual(r['skipped']['cash'],11)
  self.assertGreaterEqual(r['ending_cash_SOL'],0)
 def test_pending_entries_count_toward_cap(self):
  rows=sum((options(trade(str(i),i,5,10,100)) for i in [1,2,3]),[])
  r=funded(rows);self.assertEqual(r['attempts'],2);self.assertEqual(r['skipped']['concurrency'],1)
 def test_unresolved_retains_cash_and_capacity(self):
  rows=options(trade('a',1,2,20,-501505000-RENT,status='unresolved'))
  r=funded(rows);self.assertEqual(r['unresolved'],1);self.assertAlmostEqual(r['ending_cash_SOL'],15-.501505-RENT/L)
 def test_partial_cash_is_credited(self):
  legs=[dict(position=[3,0,1],time=3,proceeds=300000000,fee=1505000),dict(position=[10,0,1],time=10,proceeds=250000000,fee=1505000)]
  r=funded(options(trade('a',1,2,10,45500000,legs=legs)))
  self.assertAlmostEqual(r['net_zero_SOL'],.0455)
 def test_cooldown_and_probe(self):
  rows=options(trade('a',1,2,3,-350000000))+options(trade('b',4,5,6,-350000000))+options(trade('c',7,8,9,100))+options(trade('d',10810,10811,10812,100))
  r=funded(rows,True);self.assertEqual(r['skipped']['strategy_pause'],1);self.assertTrue(r['admitted'][-1]['probe']);self.assertEqual(r['admitted'][-1]['status'],'failed')
 def test_global_brake_does_not_force_close(self):
  rows=options(trade('a',1,2,5,-500000000))+options(trade('b',3,4,6,-500000000,rule='s2_survival_shelf'))+options(trade('c',7,8,9,-500000000,rule='s3_deadman'))+options(trade('d',10,11,12,-500000000,rule='s4_upper_ath'))+options(trade('e',13,14,15,100))
  r=funded(rows,True);self.assertEqual(r['skipped']['global_pause'],1);self.assertEqual(r['closed'],4)

if __name__=='__main__':unittest.main()
