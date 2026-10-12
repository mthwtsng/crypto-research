"""Two declared accounting/execution sensitivities, no tuning or new coin selection."""
import collections,concurrent.futures,gzip,json,pickle
import collect as N
import screen as S
import engine as E
C=S.C;W=C.W

def main():
 manifest=json.loads((N.HERE/'COIN_MANIFEST.json').read_text());ids={c['mint']for c in manifest};ts=[t for t in pickle.load(gzip.open(N.HERE/'TAPES.pkl.gz','rb'))if t['mint']in ids];original={sn:dict(c)for sn,c in C.SCENARIOS.items()};W.rpc=N.rpc
 for t in ts:
  for g in t['groups']:W.TIMES[g['slot']]=g['block_time']
 rows=[];errors=[]
 for policy in ['historical_entry_mean','passive_short_timer_sensitivity']:
  for sn in C.SCENARIOS:
   C.SCENARIOS[sn]=dict(original[sn])
   if policy=='historical_entry_mean':C.SCENARIOS[sn].update(buy=.002915606,fast=.002915606)
  fn=E.replay if policy=='historical_entry_mean'else C.replay;jobs=[(t,s,sn,mode)for t in ts for s in S.detect(t)for sn in C.SCENARIOS for mode in(['full_timer','staged_ladder']if policy=='historical_entry_mean'else['full_timer'])]
  with concurrent.futures.ThreadPoolExecutor(4)as ex:
   fs={ex.submit(fn,j):j for j in jobs}
   for f in concurrent.futures.as_completed(fs):
    try:r=f.result();r['policy']=policy;rows.append(r)
    except Exception as e:
     t,s,sn,m=fs[f];errors.append(dict(mint=t['mint'],rule=s['rule'],scenario=sn,mode=m,policy=policy,error=str(e)))
  print('sensitivity',policy,'done',len(jobs),flush=True)
 arms=collections.defaultdict(list)
 for r in rows:arms[r['policy'],r['rule'],r['scenario'],r['mode']].append(r)
 out=[dict(policy=p,rule=rule,scenario=sn,mode=m,summary=C.A.summarize(rs),funded5=C.AC.ledger(rs,5.,2))for(p,rule,sn,m),rs in sorted(arms.items())]
 (N.HERE/'SENSITIVITY.json').write_text(json.dumps(out,indent=2));(N.HERE/'SENSITIVITY_ERRORS.json').write_text(json.dumps(errors,indent=2))
 with gzip.open(N.HERE/'SENSITIVITY_TRADES.jsonl.gz','wt')as f:
  for r in rows:f.write(json.dumps(r)+'\n')
 print('sensitivities',len(rows),'errors',len(errors),flush=True)
if __name__=='__main__':main()
