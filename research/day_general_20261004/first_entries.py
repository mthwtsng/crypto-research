"""Predeclared day first-entry-per-rule/mint benchmark; no selection on PnL."""
import collections,gzip,json
import collect as N
import screen as S
rows=[json.loads(x) for x in gzip.open(N.HERE/'TRADES.jsonl.gz','rt')]
arms=collections.defaultdict(dict)
for r in rows:
 a=arms[r['rule'],r['scenario'],r['mode']]
 if r['mint'] not in a or r['decision_slot']<a[r['mint']]['decision_slot']:a[r['mint']]=r
out=[dict(rule=k[0],scenario=k[1],mode=k[2],summary=S.C.A.summarize(list(v.values())),funded5=S.C.AC.ledger(list(v.values()),5.,2),scope='Predeclared day benchmark; first attempted entry per rule/mint, independent of outcome; retrospective transfer, not a later day holdout') for k,v in sorted(arms.items())]
(N.HERE/'FIRST_ENTRY_LEDGER.json').write_text(json.dumps(out,indent=2))
