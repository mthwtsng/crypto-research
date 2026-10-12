"""Frozen five-strategy replay across the original and expanded cohorts.

Engines: as_reported (exact-token buys revert above remaining curve tokens),
capped (Pump caps such buys at remaining tokens), capped_residual (additionally an
outside buyer completes any residual curve before the authentic pool opening;
labelled assumption). One continuous 15 SOL cash-funded ledger, 0.50 SOL tickets,
no position cap, breakers on/off. Usage: expanded_replay.py COHORT [COHORT ...]
"""
import collections,concurrent.futures,datetime,gzip,json,pathlib,pickle,sys,types
HERE=pathlib.Path(__file__).resolve().parent;P0=HERE.parent;sys.path.insert(0,str(P0))
import unlimited_requested as N
U=N.U;R=U.R;V=R.V;E=V.E;A=E.A;F=U.F
OUT=HERE/'expanded_results';OUT.mkdir(exist_ok=True)
S3CFG=dict(s3_extended_hold=60,s3_grace=8,s3_full_target=.2,s3_relative_price_stop=.12)
SCEN=[(x,1505000) for x in ['fast','central80','central85','slow','stress']]+[('central85',2916000)]
_orig=A.exact_buy
def capped(st,n):
 if st['rtokens_raw'] and n>st['rtokens_raw']:n=st['rtokens_raw']
 return _orig(st,n)
src=pathlib.Path(E.__file__).read_text()
old="   if st['rtokens_raw']!=0:return 'counterfactual_completion_displaced'\n"
new="""   if st['rtokens_raw']!=0:
    rr=A.exact_buy(st,st['rtokens_raw'])
    if not rr:return 'counterfactual_completion_displaced'
    RESIDUAL.append(dict(mint=t['mint'],tokens=st['rtokens_raw'],sol_raw=rr[0]));st=A.moved(st,*rr)
"""
assert src.count(old)==1
RES=types.ModuleType('engine_residual');RES.__file__=E.__file__;RES.RESIDUAL=[]
exec(compile(src.replace(old,new),'engine_residual','exec'),RES.__dict__)
ENGINES={'as_reported':(E.simulate,_orig),'capped':(E.simulate,capped),'capped_residual':(RES.simulate,capped)}

def cohort_inputs(name):
 if name in ('earlier','later'):
  sel=json.load(open(R.OUT/'SIGNALS.json'));tapes,baseline,_=R.prepare(name,sel[name])
  return tapes,[s for s in baseline if s['rule']!='s3_deadman']+sel[name]['two_buy_groups']
 P=HERE/name;raw={t['mint']:t for t in pickle.load(gzip.open(P/'REPAIRED_SELECTION.pkl.gz','rb'))};baseline=json.loads((P/'SIGNALS.json').read_text())
 ss=[s for s in baseline if s['rule']!='s3_deadman']
 for s in baseline:
  if s['rule']=='s3_deadman':
   c=R.choose(raw[s['mint']],s,'two_buy_groups')
   if c:ss.append(c)
 ep=OUT/('exec_'+name);(ep/'amm_tapes').mkdir(parents=True,exist_ok=True);(ep/'bound_curve_tapes').mkdir(exist_ok=True)
 (ep/'SIGNALS.json').write_text(json.dumps(ss)+'\n');latest={}
 for s in ss:latest[s['mint']]=max(latest.get(s['mint'],0),s['time'])
 for f in (P/'execution/bound_curve_tapes').glob('*.gz'):
  d=ep/'bound_curve_tapes'/f.name
  if not d.exists():d.symlink_to(f.resolve())
 for f in (P/'normalized_amm_tapes').glob('*.gz'):
  t=json.load(gzip.open(f,'rt'))
  if t['mint'] not in latest:continue
  t['groups']=[g for i,g in enumerate(t['groups']) if i==0 or g['time']<=latest[t['mint']]+660]
  with gzip.open(ep/'amm_tapes'/f.name,'wt',compresslevel=1) as o:json.dump(t,o)
 E.P=ep;E.OLD=P;E.O.C.P=ep;tapes=E.load()[0]
 return tapes,ss

def replay(name):
 f=OUT/f'REPLAY_{name}.json.gz'
 if f.exists():return json.load(gzip.open(f,'rt'))
 tapes,ss=cohort_inputs(name);rows=[];errors=[]
 print('COHORT',name,'signals',dict(collections.Counter(s['rule'] for s in ss)),flush=True)
 for engine,(sim,buy) in ENGINES.items():
  A.exact_buy=buy;RES.A.exact_buy=buy
  scen=SCEN if engine!='as_reported' else [('central85',1505000)]
  jobs=[(s,sc,fee,ticket) for s in ss if s['mint'] in tapes for sc,fee in scen for ticket in [.5,.25]]
  def run(j):
   s,sc,fee,ticket=j;cfg=S3CFG if s['rule']=='s3_deadman' else {}
   return dict(sim(tapes[s['mint']],s,sc,'lower',ticket,fee,cfg),cohort=name,engine=engine)
  with concurrent.futures.ThreadPoolExecutor(4) as ex:
   fs={ex.submit(run,j):j for j in jobs}
   for fu in concurrent.futures.as_completed(fs):
    try:rows.append(fu.result())
    except Exception as e:errors.append(dict(cohort=name,engine=engine,mint=fs[fu][0]['mint'],rule=fs[fu][0]['rule'],error=repr(e)))
  print('ENGINE',name,engine,len(rows),'errors',len(errors),flush=True)
 A.exact_buy=_orig
 missing=[s['mint'] for s in ss if s['mint'] not in tapes]
 with gzip.open(f,'wt',compresslevel=1) as o:json.dump(rows,o)
 (OUT/f'ERRORS_{name}.json').write_text(json.dumps(dict(errors=errors,missing_tapes=missing,residual=RES.RESIDUAL),indent=1))
 return rows

def summarize(rows,label):
 out=[]
 for engine in ENGINES:
  for sc,fee in SCEN:
   rr=[r for r in rows if r['engine']==engine and r['scenario']==sc and r['fee']==fee]
   if not rr:continue
   for scope in ['portfolio','portfolio_without_carryover']+F.RULES:
    for br in [True,False]:
     res=F.funded(rr,br,scope,position_limit=None);res.pop('admitted');res.pop('trips',None)
     out.append(dict(label=label,engine=engine,scenario=sc,fee=fee,**res))
 return out

def main():
 names=sys.argv[1:];allrows=[]
 for n in names:allrows+=replay(n)
 results=[]
 for n in names:results+=summarize([r for r in allrows if r['cohort']==n],n)
 results+=summarize(allrows,'continuous_all')
 (OUT/'FUNDED.json').write_text(json.dumps(results,indent=1))
 for r in results:
  if r['scenario']=='central85' and r['fee']==1505000 and r['breakers'] and r['scope'] in ['portfolio','portfolio_without_carryover','s5_carryover']:
   print(r['label'],r['engine'],r['scope'],'a/c/f/u',r['attempts'],r['closed'],r['failed'],r['unresolved'],'settled',round(r['settled_net_SOL'],4),'open',round(r['unresolved_marked_pnl_SOL'],4),'combined',round(r['last_valid_marked_net_SOL'],4),flush=True)
if __name__=='__main__':main()
