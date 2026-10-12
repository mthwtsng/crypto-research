"""Regression on authentic carryover: react to pool opening, not next swap."""
import unittest
import recovery_sequence as R

class RequestedExitTests(unittest.TestCase):
 def test_half_exit_can_fire_after_opening_transaction(self):
  tapes,signals,_=R.source('earlier');mint='9BenaMeegjDL87qjc8sJiYBCW9FYLx53t5FwJuZsvRKX'
  s=next(s for s in signals if s['mint']==mint and s['rule']=='s5_carryover');t=tapes[mint]
  genesis=next(g for g in t['groups'] if g['venue']=='amm')
  r=R.V.E.simulate(t,s,'fast','lower',.5)
  self.assertEqual(r['status'],'closed')
  half=next(l for l in r['legs'] if l['reason']=='AMM_open_half')
  self.assertEqual(half['trigger_slot'],genesis['slot'])
  self.assertEqual(tuple(half['position']),(genesis['slot'],genesis['index'],1))
  self.assertEqual(half['tokens'],r['entry_tokens']//2)
  self.assertEqual(sum(l['tokens'] for l in r['legs']),r['entry_tokens'])

if __name__=='__main__':unittest.main()
