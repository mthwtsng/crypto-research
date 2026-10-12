"""Authenticate complete opening transactions, including their first swap."""
import gzip,json,pathlib,sys,unittest
P=pathlib.Path(__file__).resolve().parent;sys.path.insert(0,str(P.parent/'core_plan_audit_20261007'));import engine as E

class OpeningTests(unittest.TestCase):
 def test_source_opening_matches_every_new_pool(self):
  files=list((P/'fresh_oct05_oct06/normalized_amm_tapes').glob('*.gz'));self.assertEqual(len(files),10)
  for f in files:
   t=json.load(gzip.open(f,'rt'));g=t['groups'][0];curve=dict(rsol_raw=g['before']['quote']+15000001);z,h,cf,err=E.opening_state(curve,g,dict(migration_quote_difference=15000001),{},{});self.assertIsNone(err,(t['mint'],err))
   for key in ['base','quote','virtual','supply']:self.assertEqual(z[key],g['state'][key],(t['mint'],key))
   self.assertEqual(h,cf)
 def test_counterfactual_opening_preserves_extra_reserves(self):
  f=next(f for f in (P/'fresh_oct05_oct06/normalized_amm_tapes').glob('*.gz') if json.load(gzip.open(f,'rt'))['groups'][0]['trades']);g=json.load(gzip.open(f,'rt'))['groups'][0];z,_,_,err=E.opening_state(dict(rsol_raw=g['before']['quote']+15000001+500000000),g,dict(migration_quote_difference=15000001),{},{});self.assertIsNone(err);self.assertGreater(z['virtual'],g['state']['virtual'])
 def test_opening_swap_failure_does_not_commit_pool(self):
  f=next(f for f in (P/'fresh_oct05_oct06/normalized_amm_tapes').glob('*.gz') if json.load(gzip.open(f,'rt'))['groups'][0]['trades']);g=json.load(gzip.open(f,'rt'))['groups'][0]
  for e in g['trades']:e['max_quote']=0
  for op in g['custody_ops']:
   if op['kind']=='trade':op['event']['max_quote']=0
  z,_,_,err=E.opening_state(dict(rsol_raw=g['before']['quote']+15000001),g,dict(migration_quote_difference=15000001),{},{});self.assertIsNone(z);self.assertEqual(err,'atomic_pool_opening_reverted')

if __name__=='__main__':unittest.main()
