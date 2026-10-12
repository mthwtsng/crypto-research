"""Sensitivity: capped exact-token buys plus anonymous completion of a residual curve.

When our counterfactual leaves residual curve tokens at the historical completion,
an outside buyer is assumed to purchase that residual before the authentic pool
opening. Labelled assumption; residual SOL cost is recorded per position.
"""
import collections,concurrent.futures,gzip,json,pathlib,sys,types
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import unlimited_requested as N
U=N.U;A=U.E.A;OUT=pathlib.Path(__file__).resolve().parent
_orig=A.exact_buy
def capped(st,n):
 if st['rtokens_raw'] and n>st['rtokens_raw']:n=st['rtokens_raw']
 return _orig(st,n)
A.exact_buy=capped
src=pathlib.Path(U.E.__file__).read_text()
old="   if st['rtokens_raw']!=0:return 'counterfactual_completion_displaced'\n"
new="""   if st['rtokens_raw']!=0:
    rr=A.exact_buy(st,st['rtokens_raw'])
    if not rr:return 'counterfactual_completion_displaced'
    RESIDUAL.append(dict(mint=t['mint'],tokens=st['rtokens_raw'],sol_raw=rr[0]));st=A.moved(st,*rr)
"""
assert src.count(old)==1
mod=types.ModuleType('engine_residual');mod.__file__=U.E.__file__;mod.RESIDUAL=[]
exec(compile(src.replace(old,new),'engine_residual',  'exec'),mod.__dict__)
mod.A.exact_buy=capped
rows=json.load(gzip.open(N.OUT/'RELATIVE_REPLAY.json.gz','rt'));sel=json.load(open(U.R.OUT/'SIGNALS.json'))
uniq={}
for r in rows:
 if r['rule']=='s5_carryover':uniq.setdefault((r['window'],r['mint'],r['signal_signature'],r['scenario'],r['fee'],r['ticket']),r)
new_rows={};errors=[]
for window in ['earlier','later']:
 tapes,_,_=U.R.prepare(window,sel[window])
 for k,r in uniq.items():
  if k[0]!=window:continue
  try:new_rows[k]=dict(mod.simulate(tapes[r['mint']],r,r['scenario'],'lower',r['ticket'],r['fee'],{}),window=window)
  except Exception as e:errors.append((r['mint'],repr(e)))
print('errors',errors)
res_by_mint={}
for x in mod.RESIDUAL:res_by_mint[x['mint']]=max(res_by_mint.get(x['mint'],0),x['sol_raw'])
print('residual completion SOL (max over scenarios):',{m[:8]:round(v/1e9,4) for m,v in res_by_mint.items()})
L=1e9
c85=[r for k,r in new_rows.items() if k[3]=='central85' and k[4]==1505000 and k[5]==.5]
print('central85 S5',collections.Counter((r['status'],r['reason'] if r['status']=='unresolved' else '') for r in c85))
for r in sorted(c85,key=lambda r:r['entry_time']):
 print(r['window'],r['mint'][:8],r['status'],'net',round(r['net']/L,6),[(l['venue'],l['reason'],round(l['proceeds']/L,4),l['time']-r['entry_time']) for l in r['legs']])
patched=[r if r['rule']!='s5_carryover' else dict(new_rows[(r['window'],r['mint'],r['signal_signature'],r['scenario'],r['fee'],r['ticket'])],horizon=r['horizon'],profit_target=r['profit_target']) for r in rows]
out=[]
for sc,fee in [(x,1505000) for x in ['fast','central80','central85','slow','stress']]+[('central85',2916000)]:
 rr=[r for r in patched if (r['horizon'],r['profit_target'],r['scenario'],r['fee'])==(60,.2,sc,fee)]
 for scope in ['portfolio','portfolio_without_carryover','s5_carryover']:
  for br in [True,False]:
   res=U.F.funded(rr,br,scope,position_limit=None);adm=res.pop('admitted');res.update(scenario=sc,fee=fee);out.append(res)
   print(sc,fee,scope,'br',br,'a/c/f/u',res['attempts'],res['closed'],res['failed'],res['unresolved'],'settled',round(res['settled_net_SOL'],4),'open',round(res['unresolved_marked_pnl_SOL'],4),'combined',round(res['last_valid_marked_net_SOL'],4),'largest',round(res['largest_winner_SOL'],4),'PF',res['profit_factor'] and round(res['profit_factor'],3),'WR',res['win_rate'] and round(res['win_rate'],3))
(OUT/'RESIDUAL_FUNDED.json').write_text(json.dumps(out,indent=1))
with gzip.open(OUT/'S5_RESIDUAL_REPLAY.json.gz','wt') as f:json.dump(list(new_rows.values()),f)
