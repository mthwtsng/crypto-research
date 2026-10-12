import gzip,pickle,pathlib,unittest
from entry_signals import extract
R=pathlib.Path(__file__).resolve().parents[2]
class EntryTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.ts=pickle.load(gzip.open(R/'research/day_general_20261004/TAPES.pkl.gz','rb'))
 def test_prefix_invariance_at_every_signal(self):
  count=0
  for t in self.ts:
   full=extract(t)
   for s in full:
    partial=extract(dict(t,groups=t['groups'][:s['index']+1]))
    self.assertEqual(partial,[z for z in full if z['index']<=s['index']]);count+=1
  self.assertGreater(count,100)
 def test_no_signal_after_completion_and_one_per_family(self):
  for t in self.ts:
   ss=extract(t);self.assertEqual(len(ss),len({s['rule'] for s in ss}))
   for s in ss:
    self.assertGreater(t['groups'][s['index']]['state']['rtokens_raw'],0)
    self.assertGreaterEqual(s['age'],15)
 def test_normal_quote_cohort_only(self):
  for t in self.ts[:20]:self.assertEqual(extract(dict(t,normal=False)),[])
if __name__=='__main__':unittest.main()
