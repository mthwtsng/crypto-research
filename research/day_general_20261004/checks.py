import gzip,importlib.util,json,pickle,unittest
from unittest.mock import patch
import collect as N
import screen as S
import engine as E
spec=importlib.util.spec_from_file_location('prior_replay_checks',N.HERE/'prior_checks.py');prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
class Checks(prior.Checks):
 def test_short_timer_is_urgent(self):
  t,s=self.toy()
  with patch.object(S.C.W,'time_at',side_effect=lambda slot:(slot,1000+slot-100)),patch.object(S.C.W,'timer_slot',side_effect=lambda t,e,target:e+10):r=E.replay((t,s,'next_slot_tail','full_timer'))
  self.assertEqual(r['status'],'closed');self.assertEqual(r['settle_slot'],113);self.assertAlmostEqual(r['total_sell_fees'],.001505)
 def test_screen_first_signals_are_prefix_invariant(self):
  ids={c['mint']for c in json.loads((N.HERE/'COIN_MANIFEST.json').read_text())};ts=[t for t in pickle.load(gzip.open(N.HERE/'TAPES.pkl.gz','rb'))if t['mint']in ids];n=0
  for t in ts:
   for s in S.detect(t):
    self.assertIn(s,S.detect(dict(t,groups=t['groups'][:s['index']+1])));n+=1
  self.assertGreaterEqual(n,1)
 def test_selected_quality_is_available_at_decision(self):
  cs=json.loads((N.HERE/'COIN_MANIFEST.json').read_text());self.assertGreater(len(cs),0)
  for c in cs:
   for s in c['signals']:
    q=s['quality'];self.assertGreaterEqual(q['age_seconds'],30);self.assertGreaterEqual(q['meaningful_buyers'],8);self.assertGreaterEqual(q['outside_buy_sol'],2);self.assertLessEqual(q['largest_outside_buy_share'],.5)
 def test_followup_never_admits_later_signals(self):
  ts=pickle.load(gzip.open(N.HERE/'TAPES.pkl.gz','rb'));n=0
  for t in ts:
   if 'decision_end_time'not in t:continue
   self.assertEqual(t['end_time']-t['decision_end_time'],60)
   for sig in S.detect(t):self.assertLessEqual(t['groups'][sig['index']]['block_time'],t['decision_end_time'])
   n+=1
  self.assertEqual(n,len(ts))
 def test_window_and_hash_sample_remain_frozen(self):
  fr=json.loads((N.HERE/'FREEZE.json').read_text());cs=json.loads((N.HERE/'COIN_MANIFEST.json').read_text());from datetime import datetime
  ranks=[c['hash_rank']for c in cs];self.assertEqual(ranks,sorted(ranks))
  for c in cs:
   tt=int(datetime.fromisoformat(c['creation_utc']).timestamp());self.assertGreaterEqual(tt,fr['window_start_utc_epoch']);self.assertLess(tt,fr['creation_end_utc_epoch'])
if __name__=='__main__':unittest.main()
