"""One diagnostic: canonical exits on the same current/local entry signals.

Entry guard stays at 9000bps; current closed-mint admissions and canonical
risk controls remain fixed. This is a policy comparison, not optimization.
"""
import concurrent.futures,gzip,json,pickle
import run_day as R
import curve_v3_extension as V3

def main():
 V3.install();R.E.O.C.rpc=R.clock_rpc
 tt=pickle.load(gzip.open(R.OUT/'PREPARED_TAPES.pkl.gz','rb'));tt={t['mint']:t for t in tt}
 for t in tt.values():
  for g in t['groups']:R.E.O.CLOCK[g['slot']]=g['time']
 ids={tuple(x) for x in json.loads((R.OUT/'SIGNAL_SETS.json').read_text())['current|local']}
 ss=[s for s in json.loads((R.OUT/'SIGNALS.json').read_text()) if (s['mode'],s['mint'],s['rule'],s['signal_signature']) in ids]
 jobs=[(s,sc,fee,ticket) for s in ss for sc,fee in [(sc,1505000) for sc in ['fast','central80','central85','slow','stress']]+[('central85',2916000)] for ticket in [.5,.25]]
 fun=R.diagnostic_simulate(R.E.simulate);rows=[];errors=[]
 def work(j):
  s,sc,fee,ticket=j;cfg=R.config(s['rule']);cfg['min_tokens_bps']=9000
  return fun(tt[s['mint']],s,sc,'lower',ticket,fee,cfg)
 with concurrent.futures.ThreadPoolExecutor(4) as ex:
  fs={ex.submit(work,j):j for j in jobs}
  for f in concurrent.futures.as_completed(fs):
   try:rows.append(f.result())
   except Exception as e:errors.append(dict(signal=fs[f][0],error=repr(e)))
 R.save('MATCHED_EXIT_REPLAY.json.gz',rows);R.save('MATCHED_EXIT_ERRORS.json',errors)
 if errors:raise RuntimeError('matched exit exceptions')
 out=[];fund=R.current_ledger()
 for sc,fee in [(sc,1505000) for sc in ['fast','central80','central85','slow','stress']]+[('central85',2916000)]:
  rr=[r for r in rows if r['scenario']==sc and r['fee']==fee]
  f=R.enrich(fund(rr,True,'portfolio',None));f.update(scenario=sc,fee=fee,comparison='current_local_entries|canonical_exit_recipe_9000bps')
  out.append(f)
 R.save('MATCHED_EXIT_FUNDED.json',out)
 for f in out:print(f['scenario'],f['fee'],f['attempts'],f['closed'],f['failed'],f['unresolved'],f['last_valid_marked_net_SOL'],flush=True)

if __name__=='__main__':main()
