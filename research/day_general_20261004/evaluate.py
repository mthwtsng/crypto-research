"""Frozen sample before PnL; conditional on causal activity, not future survival."""
import collections,concurrent.futures,csv,datetime,gzip,hashlib,json,pathlib,pickle,statistics
import collect as N
import screen as S
import engine as E
C=S.C;T=C.T;W=C.W;HERE=N.HERE

def screen_summary(t,sig):
 gs=t['groups'];pref=gs[:sig['index']+1];now=gs[sig['index']]['block_time'];vs=collections.Counter();first={}
 for g in pref:
  for e in g['events']:
   if e['buy']and e['user']!=t['creator']:vs[e['user']]+=e['sol_raw']/1e9;first.setdefault(e['user'],g['block_time'])
 gross=sum(vs.values());return dict(age_seconds=now-t['creation_time'],reserve_sol=sig['reserve'],outside_buy_sol=gross,meaningful_buyers=sum(v>=.05 for v in vs.values()),largest_outside_buy_share=max(vs.values(),default=0)/gross if gross else None,name=t['creation_metadata'].get('name'),symbol=t['creation_metadata'].get('symbol'),top_buyers=[dict(wallet=w,gross_sol=v,first_buy_time=first[w])for w,v in vs.most_common(12)])

def main():
 fr=json.loads((HERE/'FREEZE.json').read_text());ts=pickle.load(gzip.open(HERE/'TAPES.pkl.gz','rb'));pool=[];sourcecases=[]
 for t in ts:
  for g in t['groups']:W.TIMES[g['slot']]=g['block_time']
  if not t['normal']:continue
  sigs=S.detect(t);sourcecases.append(dict(mint=t['mint'],creator=t['creator'],creation_time=t['creation_time'],groups=len(t['groups']),signalled=bool(sigs),custody_issue_groups=sum(bool(g.get('custody_issues'))for g in t['groups'])))
  if sigs:pool.append((hashlib.sha256((fr['seed']+t['mint']).encode()).hexdigest(),t,sigs))
 if (HERE/'COHORT_IDS.json').exists():
  pinned=set(json.loads((HERE/'COHORT_IDS.json').read_text()));chosen=sorted([x for x in pool if x[1]['mint']in pinned],key=lambda x:x[0])
 else:chosen=sorted(pool,key=lambda x:x[0])[:fr['target_triggered_coins']]
 manifest=[];jobs=[]
 for rank,t,sigs in chosen:
  manifest.append(dict(mint=t['mint'],name=t['creation_metadata'].get('name'),symbol=t['creation_metadata'].get('symbol'),creator=t['creator'],creation_utc=datetime.datetime.fromtimestamp(t['creation_time'],datetime.timezone.utc).isoformat(),hash_rank=rank,signals=[dict(s,quality=screen_summary(t,s))for s in sigs],future_completed_in_capture=any(g['state']['rtokens_raw']==0 for g in t['groups'])))
  for sig in sigs:
   for sn in C.SCENARIOS:
    for mode in ['full_timer','staged_ladder']:jobs.append((t,sig,sn,mode))
 (HERE/'SCREENING_AUDIT.json').write_text(json.dumps(dict(prepared=len(ts),supported_normal=sum(t['normal']for t in ts),triggered_coins=len(pool),chosen_coins=len(chosen),cases=sourcecases),indent=2));(HERE/'COIN_MANIFEST.json').write_text(json.dumps(manifest,indent=2));(HERE/'EVALUATION_FREEZE.json').write_text(json.dumps(dict(time=datetime.datetime.now(datetime.timezone.utc).isoformat(),source_sha256=hashlib.sha256((HERE/'TAPES.pkl.gz').read_bytes()).hexdigest(),manifest_sha256=hashlib.sha256((HERE/'COIN_MANIFEST.json').read_bytes()).hexdigest(),selected_before_pnl=True,code_sha256=hashlib.sha256(pathlib.Path(C.__file__).read_bytes()).hexdigest(),engine_sha256=hashlib.sha256((HERE/'engine.py').read_bytes()).hexdigest(),screen_sha256=hashlib.sha256((HERE/'screen.py').read_bytes()).hexdigest()),indent=2));print('SCREEN FROZEN:',len(chosen),'of',len(pool),'triggered',flush=True)
 # Global production-clock helper consumes only this study's raw cache/provider.
 W.rpc=N.rpc
 rows=[];errs=[]
 with concurrent.futures.ThreadPoolExecutor(4)as ex:
  fs={ex.submit(E.replay,j):j for j in jobs}
  for k,f in enumerate(concurrent.futures.as_completed(fs),1):
   try:rows.append(f.result())
   except Exception as e:
    t,sig,sn,m=fs[f];errs.append(dict(mint=t['mint'],rule=sig['rule'],scenario=sn,mode=m,error=str(e)))
   if k%100==0:print('replay',k,'/',len(jobs),flush=True)
 with gzip.open(HERE/'TRADES.jsonl.gz','wt')as f:
  for r in rows:f.write(json.dumps(r)+'\n')
 arms=collections.defaultdict(list)
 for r in rows:arms[r['rule'],r['scenario'],r['mode']].append(r)
 out=[]
 for(r,sn,m),rs in sorted(arms.items()):
  z=C.A.summarize(rs);cl=[x for x in rs if x['status']=='closed'];wins=sorted([x['pnl']for x in cl if x['pnl']>0],reverse=True);losses=[x['pnl']for x in cl if x['pnl']<0]
  out.append(dict(rule=r,scenario=sn,mode=m,summary=z,closed_win_sol=sum(wins),closed_loss_sol=sum(losses),mean_win=statistics.mean(wins)if wins else None,mean_loss=statistics.mean(losses)if losses else None,largest_win=max(wins,default=0),worst_loss=min(losses,default=0),funded5=C.AC.ledger(rs,5.,2)))
 (HERE/'RESULTS.json').write_text(json.dumps(out,indent=2));(HERE/'REPLAY_ERRORS.json').write_text(json.dumps(errs,indent=2))
 priority={'dislocation':0,'velocity':1,'mature_fresh':2};portfolios=[]
 for sn in C.SCENARIOS:
  for mode in ['full_timer','staged_ladder']:
   first={}
   for r in rows:
    if r['rule']not in priority or r['scenario']!=sn or r['mode']!=mode:continue
    key=r['decision_slot'],priority[r['rule']]
    if r['mint']not in first or key<first[r['mint']][0]:first[r['mint']]=(key,r)
   union=[x[1]for x in first.values()];portfolios.append(dict(scenario=sn,mode=mode,policy='First eligible dislocation/velocity/mature per mint; fixed tie priority; one entry per mint, not all engine profits summed',summary=C.A.summarize(union),funded5=C.AC.ledger(union,5.,2)))
 (HERE/'PORTFOLIOS.json').write_text(json.dumps(portfolios,indent=2))
 with(HERE/'COINS.csv').open('w')as f:
  w=csv.writer(f);w.writerow(['mint','name','symbol','creator','creation_utc','rules','first_signal_age_seconds','first_signal_reserve_SOL','meaningful_outside_buyers','largest_outside_share','completed_during_capture'])
  for c in manifest:
   ss=min(c['signals'],key=lambda x:x['slot']);q=ss['quality'];w.writerow([c['mint'],c['name'],c['symbol'],c['creator'],c['creation_utc'],','.join(sorted({s['rule']for s in c['signals']})),q['age_seconds'],ss['reserve'],q['meaningful_buyers'],q['largest_outside_buy_share'],c['future_completed_in_capture']])
 print('EVALUATED',len(rows),'errors',len(errs),flush=True)
if __name__=='__main__':main()
