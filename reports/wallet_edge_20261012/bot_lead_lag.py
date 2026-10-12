"""Observed 22-roster buy/buy lead-lag associations, pairwise coverage bounded."""
import bisect,collections,json,pathlib
P=pathlib.Path(__file__).resolve().parent
def main():
    aa=json.loads((P/'accounting.json').read_text());pairs=[]
    for f in aa:
        fb=[t for t in f['trades'] if t['side']=='buy' and t['venue']=='Pump']
        if not fb:continue
        for l in aa:
            if f is l:continue
            start=max(f['min_time'] or 0,l['min_time'] or 0)+1
            end=min(f['max_time'] or 0,l['max_time'] or 0)
            follower=[t for t in fb if start<=t['time']<=end]
            if not follower:continue
            bymint=collections.defaultdict(list)
            for t in l['trades']:
                if t['side']=='buy' and t['venue']=='Pump' and start<=t['time']<=end:bymint[t['mint']].append(t)
            matches=[]
            for t in follower:
                candidates=bymint.get(t['mint'],[])
                kk=[(q['slot'],q['index']) for q in candidates]
                idx=bisect.bisect_left(kk,(t['slot'],t['index']))-1
                if idx>=0:
                    q=candidates[idx]
                    if 0<=t['slot']-q['slot']<=2:
                        matches.append(dict(mint=t['mint'],follower_signature=t['signature'],leader_signature=q['signature'],slot_gap=t['slot']-q['slot'],same_slot=t['slot']==q['slot']))
            if matches:pairs.append(dict(follower=f['wallet'],leader=l['wallet'],pairwise_start=start,pairwise_end=end,follower_buys_in_pairwise_coverage=len(follower),matches=len(matches),share=len(matches)/len(follower),same_slot=sum(m['same_slot'] for m in matches),unique_mints=len({m['mint'] for m in matches}),examples=matches[:6]))
    pairs.sort(key=lambda p:p['matches'],reverse=True)
    reverse={(p['follower']['address'],p['leader']['address']):p for p in pairs}
    for p in pairs:
        r=reverse.get((p['leader']['address'],p['follower']['address']))
        p['reverse_direction_matches']=r['matches'] if r else 0
    (P/'bot_lead_lag.json').write_text(json.dumps(dict(scope='associations among recovered roster-owned Pump buys only; common signal and transaction ordering may explain matches; no identity/profit/copy proof',pairs=pairs),indent=2))
    print(json.dumps([{k:p[k] for k in ['follower','leader','follower_buys_in_pairwise_coverage','matches','share','reverse_direction_matches']} for p in pairs[:20]],indent=2))
if __name__=='__main__':main()
