"""Verification: Pump exact-token buys are capped at remaining curve tokens.

Every recorded completion buy receives exactly the remaining curve inventory, so
the requested amount was at least that inventory. Reverting such buys when our
own purchase shrinks the curve leaves an artificial uncompleted curve.
"""
import collections,concurrent.futures,gzip,json,pathlib,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import unlimited_requested as N
U=N.U;A=U.E.A;OUT=pathlib.Path(__file__).resolve().parent
_orig=A.exact_buy
def capped(st,n):
 if st['rtokens_raw'] and n>st['rtokens_raw']:n=st['rtokens_raw']
 return _orig(st,n)
A.exact_buy=capped
rows=json.load(gzip.open(N.OUT/'RELATIVE_REPLAY.json.gz','rt'));sel=json.load(open(U.R.OUT/'SIGNALS.json'))
old=[r for r in rows if r['rule']=='s5_carryover'];new=[];errors=[]
uniq={}
for r in old:uniq.setdefault((r['window'],r['mint'],r['signal_signature'],r['scenario'],r['fee'],r['ticket']),r)
for window in ['earlier','later']:
 tapes,_,_=U.R.prepare(window,sel[window])
 jobs=[r for k,r in uniq.items() if k[0]==window]
 def run(r):return dict(U.E.simulate(tapes[r['mint']],r,r['scenario'],'lower',r['ticket'],r['fee'],{}),window=window)
 with concurrent.futures.ThreadPoolExecutor(4) as ex:
  fs={ex.submit(run,r):r for r in jobs}
  for f in concurrent.futures.as_completed(fs):
   try:new.append(f.result())
   except Exception as e:errors.append(dict(mint=fs[f]['mint'],error=repr(e)))
print('S5 rerun',len(new),'errors',len(errors),errors[:3])
fixed={}
for r in new:fixed[(r['window'],r['mint'],r['signal_signature'],r['scenario'],r['fee'],r['ticket'])]=r
patched=[r if r['rule']!='s5_carryover' else dict(fixed[(r['window'],r['mint'],r['signal_signature'],r['scenario'],r['fee'],r['ticket'])],horizon=r['horizon'],profit_target=r['profit_target']) for r in rows]
with gzip.open(OUT/'S5_CLAMPED_REPLAY.json.gz','wt') as f:json.dump(new,f)
L=1e9
c85=[r for r in new if r['scenario']=='central85' and r['fee']==1505000 and r['ticket']==.5]
print('S5 central85 standalone statuses',collections.Counter((r['status'],r.get('reason')) for r in c85))
for r in sorted(c85,key=lambda r:r['entry_time']):
 print(r['window'],r['mint'][:8],r['status'],r.get('reason'),'net',round(r['net']/L,6),'mark',round(r['mark']/L,6),[(l['venue'],l['reason'],round(l['proceeds']/L,4)) for l in r['legs']])
out=[]
for sc,fee in [(x,1505000) for x in ['fast','central80','central85','slow','stress']]+[('central85',2916000)]:
 rr=[r for r in patched if (r['horizon'],r['profit_target'],r['scenario'],r['fee'])==(60,.2,sc,fee)]
 for scope in ['portfolio','s5_carryover']:
  for br in [True,False]:
   res=U.F.funded(rr,br,scope,position_limit=None)
   res={k:v for k,v in res.items() if k!='admitted'};res.update(scenario=sc,fee=fee)
   out.append(res)
   print(sc,fee,scope,'breakers',br,'att/cl/fail/unres',res['attempts'],res['closed'],res['failed'],res['unresolved'],'settled',round(res['settled_net_SOL'],6),'open_marked',round(res['unresolved_marked_pnl_SOL'],6),'combined',round(res['last_valid_marked_net_SOL'],6),'zero',round(res['zero_recovery_bound_SOL'],6),'reasons',res['unresolved_reasons'])
(OUT/'CLAMPED_FUNDED.json').write_text(json.dumps(out,indent=1))
