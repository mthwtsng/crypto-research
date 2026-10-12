"""Matched-entry assessment labels only; no future labels used in trading rules."""
import collections,gzip,json
import collect as N
rows=[json.loads(x)for x in gzip.open(N.HERE/'TRADES.jsonl.gz','rt')];pairs=collections.defaultdict(dict)
for r in rows:pairs[(r['rule'],r['scenario'],r['mint'],r['decision_slot'])][r['mode']]=r
out=[]
for rule in ['dislocation','velocity','liquidity','mature_fresh']:
 for sn in ['same_slot_one','next_slot_tail']:
  ps=[v for k,v in pairs.items()if k[:2]==(rule,sn)and len(v)==2 and all(r['status']=='closed'for r in v.values())];losers=[p for p in ps if p['full_timer']['pnl']<0];winners=[p for p in ps if p['full_timer']['pnl']>0]
  out.append(dict(rule=rule,scenario=sn,matched_closes=len(ps),baseline_losers=len(losers),loser_damage_saved=sum(p['staged_ladder']['pnl']-p['full_timer']['pnl']for p in losers),baseline_winners=len(winners),winner_upside_surrendered=sum(p['full_timer']['pnl']-p['staged_ladder']['pnl']for p in winners),total_staged_improvement=sum(p['staged_ladder']['pnl']-p['full_timer']['pnl']for p in ps),note='Winner/loser labels used only to assess unchanged causal exit policies; not live routing inputs.'))
(N.HERE/'EXIT_TRADEOFFS.json').write_text(json.dumps(out,indent=2))
print('matched tradeoff summaries',len(out))
