"""Causal strategy-level resolved-shadow feedback with a matched warmup control.

Shadow outcomes are independently replayed 0.50SOL intents, not observed live
profits. Unresolved shadows never become fictitious resolved losses or wins.
"""
import collections,datetime,gzip,hashlib,json,pathlib,sys,unittest
P=pathlib.Path(__file__).resolve().parent;sys.path.insert(0,str(P));import variants as V
OUT=P/'shadow_feedback_cycle';OUT.mkdir(exist_ok=True)

def key(r):return (r['mint'],r['rule'],r['signal_signature'])

def decisions(rows,policy):
    signals={key(r):r for r in rows if r['ticket']==.5}
    events=[]
    for k,r in signals.items():
        if r['status'] in ['closed','failed']:
            position=r['close_position'] if r['status']=='closed' else r['entry_position']
            events.append((tuple(position),k,r['net']))
    events.sort();history=collections.defaultdict(list);i=0;out=[]
    for k,r in sorted(signals.items(),key=lambda kv:(tuple(kv[1]['signal_position']),kv[0])):
        position=tuple(r['signal_position'])
        while i<len(events) and events[i][0]<position:
            pos,kk,net=events[i];history[kk[1]].append(dict(key=kk,position=pos,net=net));i+=1
        h=history[r['rule']][-10:];total=sum(x['net'] for x in h)
        admit=policy=='baseline' or len(h)>=10 and (policy=='warmup10' or total>0)
        assert all(x['position']<position for x in h)
        out.append(dict(key=k,signal_position=position,rule=r['rule'],allowed=admit,reason='allowed' if admit else 'warmup' if len(h)<10 else 'nonpositive_shadow',history_count=len(h),history_net_SOL=total/1e9,history=h))
    return out

def inputs():
    old=json.load(gzip.open(P/'VARIANT_REPLAY.json.gz','rt'))
    new=json.load(gzip.open(P/'demand_and_bounce_cycle/REPLAY.json.gz','rt'))
    later=json.load(gzip.open(P/'TRANSFER_REPLAY.json.gz','rt'))
    out=[]
    for recipe in ['baseline','confirmed_scratch3']:
        earlier=[r for r in old if r['variant']=='baseline' and (recipe=='baseline' or r['rule']!='s3_deadman')]
        if recipe!='baseline':earlier += [r for r in old if r['variant']=='joint_keep_targets_dead3' and r['rule']=='s3_deadman']
        fresh=[r for r in later if r['variant']=='baseline' and r['placement_seed']==0] if recipe=='baseline' else [r for r in new if r['variant']==recipe]
        out += [dict(r,recipe=recipe) for r in earlier+fresh]
    return out

def main():
    files=[P/'VARIANT_REPLAY.json.gz',P/'TRANSFER_REPLAY.json.gz',P/'demand_and_bounce_cycle/REPLAY.json.gz',pathlib.Path(__file__)]
    spec=dict(frozen_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),status='all October3–6data inspected; retrospective development',recipes=['baseline','confirmed_scratch3'],policies=['baseline','warmup10','positive10'],new_policy_looks=2,prior_logged_development_looks=26,gate='last10resolved independent0.50SOL shadow attempts per strategy; admit only when sum>0; failures pay network fee, unresolved ignored; continue shadow tracking while paused',control='same10resolved warmup but no positive-net gate',limitations='Sampled launches do not establish complete live strategy opportunity coverage. Shadow own impact is modeled, not measured. S5 may never warm up because custody is unresolved; no claim of profitable migration execution.',hashes={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in files})
    (OUT/'SPEC.json').write_text(json.dumps(spec,indent=2)+'\n')
    rows=inputs();groups=collections.defaultdict(list)
    for r in rows:groups[(r['recipe'],r['scenario'],r['fee'])].append(r)
    results=[];audit=[]
    for (recipe,sc,fee),rr in sorted(groups.items()):
        assert len({(key(r),r['ticket']) for r in rr})==len(rr),'duplicate intent'
        for policy in ['baseline','warmup10','positive10']:
            dd=decisions(rr,policy);allowed={tuple(d['key']) for d in dd if d['allowed']};selected=[r for r in rr if key(r) in allowed]
            audit.append(dict(recipe=recipe,scenario=sc,fee=fee,policy=policy,decisions=dd))
            for scope in ['portfolio','portfolio_without_carryover']+V.F.RULES:
                for br in [False,True]:
                    funded=V.F.funded(selected,br,scope)
                    scoped=[d for d in dd if scope=='portfolio' or scope=='portfolio_without_carryover' and d['rule']!='s5_carryover' or d['rule']==scope]
                    results.append(dict(recipe=recipe,scenario=sc,fee=fee,policy=policy,opportunities=len(scoped),gate_rejections=dict(collections.Counter(d['reason'] for d in scoped if not d['allowed'])),**funded))
    (OUT/'FUNDED.json').write_text(json.dumps(results,indent=2)+'\n')
    with gzip.open(OUT/'DECISIONS.json.gz','wt',compresslevel=1) as f:json.dump(audit,f)
    print('COMPLETE',len(rows),len(results),flush=True)
    for r in results:
        if r['scenario']=='central85' and r['fee']==1505000 and not r['breakers'] and r['scope'] in ['portfolio','portfolio_without_carryover']:
            print(r['recipe'],r['policy'],r['scope'],r['net_zero_SOL'],r['net_marked_SOL'],r['attempts'],r['closed'],r['failed'],r['unresolved'],flush=True)

class CausalTests(unittest.TestCase):
    def make(self,i,net,delay=1,status='closed'):
        return dict(mint=str(i),rule='s2_survival_shelf',signal_signature=str(i),ticket=.5,signal_position=(i*10,0,0),entry_position=(i*10,0,1),close_position=(i*10+delay,0,1),status=status,net=net)
    def test_unresolved_does_not_complete_warmup(self):
        rr=[self.make(i,100,status='unresolved') for i in range(10)]+[self.make(10,1)]
        self.assertFalse(decisions(rr,'positive10')[-1]['allowed'])
    def test_future_close_and_future_append_cannot_influence_decision(self):
        rr=[self.make(i,100,delay=1000) for i in range(10)]+[self.make(10,1)]
        self.assertFalse(decisions(rr,'positive10')[-1]['allowed'])
        initial=decisions(rr,'positive10');self.assertEqual(initial,decisions(rr+[self.make(11,-100000)],'positive10')[:len(initial)])
    def test_failed_fees_count_and_shadow_recovery_resumes(self):
        rr=[self.make(i,-505000,status='failed') for i in range(10)]+[self.make(i,1000000) for i in range(10,21)]
        dd=decisions(rr,'positive10');self.assertFalse(dd[10]['allowed']);self.assertTrue(dd[-1]['allowed'])

if __name__=='__main__':
    if '--test' in sys.argv:sys.argv.remove('--test');unittest.main()
    else:main()
