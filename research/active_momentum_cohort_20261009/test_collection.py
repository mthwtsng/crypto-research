"""Collection integrity regressions; no exits, simulated trades or RPC calls."""
import sys
sys.dont_write_bytecode=True
import copy,unittest
import collect_cohort as C

class IntegrityTests(unittest.TestCase):
 def tape(self):
  r=C.read(C.P/'STRICT_PILOT.json');t=C.read(C.P/r['bound_path'])
  t['groups']=[g for g in t['groups'] if g['source_status']=='succeeded']
  return t
 def test_authenticated_source_passes_from_creation(self):
  r=C.parity(self.tape());self.assertIsNone(r['error']);self.assertGreater(r['groups_checked'],50)
 def test_one_lamport_reserve_mismatch_is_rejected(self):
  t=self.tape();t['groups'][1]['state']['rsol_raw']+=1
  self.assertEqual(C.parity(t)['error'],'whole_source_parity')
 def test_missing_token_inventory_is_not_invented(self):
  t=self.tape();g=t['groups'][0]
  ac=next(ac for ac in g['tokenpre'] if g['account_owners'].get(ac)!=t['curve'])
  g['tokenpre'][ac]+=1
  self.assertEqual(C.parity(t)['error'],'source_inventory_gap')
 def test_canonical_order_and_deduplication(self):
  a=dict(slot=5,transactionIndex=2,blockTime=100,transaction=dict(signatures=['a']))
  b=dict(slot=4,transactionIndex=9,blockTime=100,transaction=dict(signatures=['b']))
  self.assertEqual([C.sig(x) for x in C.ordered([a,b,a])],['b','a'])
 def test_conflicting_block_index_is_rejected(self):
  a=dict(slot=5,transactionIndex=2,blockTime=100,transaction=dict(signatures=['a']))
  b=dict(a,transaction=dict(signatures=['b']))
  with self.assertRaises(ValueError):C.ordered([a,b])
 def test_missing_order_is_rejected(self):
  a=dict(slot=5,blockTime=100,transaction=dict(signatures=['a']))
  with self.assertRaises(ValueError):C.ordered([a])
if __name__=='__main__':unittest.main()
