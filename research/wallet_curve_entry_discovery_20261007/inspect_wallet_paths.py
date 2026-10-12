"""Receipt-derived pre-entry observations and explicit same-coin opportunity controls."""
import collections,gzip,json,pathlib,statistics,sys
P=pathlib.Path(__file__).resolve().parent;R=P.parents[1]
sys.path.insert(0,str(R/'research/day_general_20261004/helpers'));import decoder as D

def describe(es,creator,own,now,start):
 outside=[e for e in es if e['user'] not in (creator,own)]
 recent=[e for e in outside if now-4<=e['time']<=now]
 buys=[e for e in recent if e['buy'] and e['sol_raw']>=50_000_000]
 vol=collections.Counter()
 for e in buys:vol[e['user']]+=e['sol_raw']
 allbuyers={e['user'] for e in outside if e['buy'] and e['sol_raw']>=50_000_000}
 oldbuyers={e['user'] for e in outside if e['buy'] and e['sol_raw']>=50_000_000 and e['time']<now-4}
 prices=[e['vsol_raw']/e['vtokens_raw'] for e in es if e['vtokens_raw']>0]
 return dict(age=now-start,reserve_SOL=es[-1]['rsol_raw']/1e9 if es else None,breadth=len(allbuyers),recent_buyers=len(vol),fresh_buyers=len(set(vol)-oldbuyers),recent_buy_SOL=sum(vol.values())/1e9,dominance=max(vol.values())/sum(vol.values()) if vol else None,recent_sell_SOL=sum(e['sol_raw'] for e in recent if not e['buy'])/1e9,drawdown=1-prices[-1]/max(prices) if prices else None,last_side='buy' if es and es[-1]['buy'] else 'sell' if es else None)

def main():
 paths=[];comparisons=[];errors=[]
 for f in sorted((P/'trajectories').glob('*.json.gz')):
  try:
   x=json.load(gzip.open(f,'rt'));b=x['entry'];mint=b['mint'];w=b['wallet'];ts=x['transactions'];target=next(i for i,t in enumerate(ts) if t['transaction']['signatures'][0]==b['signature'])
   ct,c=next((t,c) for t in ts for c in D.creations(t) if c['mint']==mint);dev=c['deployer'];es=[];snap=[]
   for i,t in enumerate(ts[:target]):
    ev=[dict(e,time=t['blockTime'],slot=t['slot'],index=t['transactionIndex'],signature=t['transaction']['signatures'][0]) for e in D.events(t) if e['mint']==mint];es+=ev
    if ev:snap.append((i,describe(es,dev,w,t['blockTime'],ct['blockTime'])))
   entry=describe(es,dev,w,b['time'],ct['blockTime'])
   candidates=[(i,s) for i,s in snap if s['reserve_SOL'] is not None and entry['reserve_SOL']*.8<=s['reserve_SOL']<=entry['reserve_SOL']*1.2 and abs(s['age']-entry['age'])<=max(10,entry['age']*.5) and s['age']>=5]
   control=min(candidates,key=lambda z:abs(z[1]['reserve_SOL']-entry['reserve_SOL'])/max(entry['reserve_SOL'],.01)+abs(z[1]['age']-entry['age'])/max(entry['age'],1)) if candidates else None
   # Exclude immediately adjacent causal anchor, which is the same opportunity.
   candidates=[z for z in candidates if ts[z[0]]['slot']<b['slot']-2]
   control=min(candidates,key=lambda z:abs(z[1]['reserve_SOL']-entry['reserve_SOL'])/max(entry['reserve_SOL'],.01)+abs(z[1]['age']-entry['age'])/max(entry['age'],1)) if candidates else None
   short=[dict(age=e['time']-ct['blockTime'],side='B' if e['buy'] else 'S',actor=e['user'][:8],SOL=round(e['sol_raw']/1e9,4),reserve=round(e['rsol_raw']/1e9,3)) for e in es[-12:]]
   paths.append(dict(wallet=w,mint=mint,signature=b['signature'],entry=entry,prior12=short,full_pre_entry_events=es,source_file=str(f.relative_to(R))))
   if control:comparisons.append(dict(wallet=w,mint=mint,entry=entry,control=control[1],control_signature=ts[control[0]]['transaction']['signatures'][0],scope='earlier same-coin state,>=3slots before entry; age and reserves matched; descriptive only, not causal effect or future profitability'))
  except Exception as e:errors.append(dict(file=str(f),error=str(e)))
 summary=[]
 for w in sorted({r['wallet'] for r in paths}):
  rr=[r for r in paths if r['wallet']==w];mm=[r for r in comparisons if r['wallet']==w]
  def median(rows,k):
   a=[r[k] for r in rows if r.get(k) is not None];return statistics.median(a) if a else None
  summary.append(dict(wallet=w,entries=len(rr),matched_controls=len(mm),entry_medians={k:median([r['entry'] for r in rr],k) for k in ['age','reserve_SOL','breadth','recent_buyers','fresh_buyers','drawdown','dominance']},paired_median_differences={k:statistics.median([r['entry'][k]-r['control'][k] for r in mm if r['entry'].get(k) is not None and r['control'].get(k) is not None]) if any(r['entry'].get(k) is not None and r['control'].get(k) is not None for r in mm) else None for k in ['recent_buyers','fresh_buyers','drawdown','recent_buy_SOL']}))
 with gzip.open(P/'RAW_WALLET_PATHS.json.gz','wt') as f:json.dump(paths,f)
 for name,a in [('WALLET_PATH_REVIEW.json',[{k:v for k,v in r.items() if k!='full_pre_entry_events'} for r in paths]),('ENTRY_CONTROL_PAIRS.json',comparisons),('PATH_SUMMARY.json',summary),('PATH_ERRORS.json',errors)]:
  (P/name).write_text(json.dumps(a,indent=2)+'\n')
 print(json.dumps(summary,indent=2));print('ERRORS',errors)
if __name__=='__main__':main()
