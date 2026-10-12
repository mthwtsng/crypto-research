"""User-prescribed two-buyer/grace/long-exit full portfolio, dev gate ablation."""
import collections,concurrent.futures,datetime,gzip,hashlib,json,pathlib,sys
import recovery_sequence as R
P,OUT,E,F=R.P,R.P/'unified_requested_cycle',R.V.E,R.V.F
OUT.mkdir(exist_ok=True)
CREATIONS={x['mint']:x['creation'] for x in json.loads((R.C.FRESH/'CREATION_SAMPLE.json').read_text())['chosen']}

def creator_hold(t,s):
    i=next(i for i,g in enumerate(t['groups']) if g['signature']==s['signal_signature'])
    h=E.A.build.inventory(t['groups'][:i+1]);metadata=t.get('creation_metadata') or CREATIONS.get(t['mint'],{});supply=metadata.get('token_total_supply')
    if not supply or h.get(t['creator'],0)<0:return dict(known=False,reason='unverified_supply_or_custody')
    return dict(known=True,held_raw=h.get(t['creator'],0),total_supply_raw=supply,share=h.get(t['creator'],0)/supply,passes=h.get(t['creator'],0)*100<=supply*15)

def main():
    spec=dict(frozen_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),source='explicit user-requested unified comparison and target/floor clarification',data='1800creation-selected October3–6launches, inspected retrospective development',constraints=dict(bankroll=15,ticket=.5,max_open=2),entries='S3two_buy_groups: two separate completed buying groups, new distinct noncreator buyer>=0.05SOL, within2slots of dip, reserve8–18; other four original entries unchanged',exit='S3only: no3s/10s/21s scratches;8s grace before trail; immediate full TP20/35% as separate endpoint recipes;arm trail at executable20% at any age,8percentage-point giveback;hard60/120s timeout; emergency reserve<8SOL active during grace; other four original lower-endpoint exits retained',developer_gate='universal creator held/creation-event authenticated total mint supply<=15%, after whole qualifying source transaction, independent ablation; associated wallets unknown; no later new signal search after filter rejection',portfolio='no positive10,no warmup,S5 eligible from first signal;latest original breakers on/off',look_count='eight prescribed horizon×profit-target×developer variants;prior28loggedlooks plus two recovery entry definitions plus four pre-clarification requested variants=34; total42; paused old recovery sell experiment was not run',opening_execution_repair='Evaluate exits immediately after the whole authentic opening transaction; source bootstrap unchanged, no wait for another swap before AMM-open half sale',hashes={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in [pathlib.Path(__file__),pathlib.Path(R.__file__),R.V.BASE/'engine.py']})
    (OUT/'SPEC.json').write_text(json.dumps(spec,indent=2)+'\n');selection=json.loads((R.OUT/'SIGNALS.json').read_text());jobs_by_window={};held_audit=[]
    for window in ['earlier','later']:
        _,baseline,raw=R.source(window);ss=[s for s in baseline if s['rule']!='s3_deadman']+selection[window]['two_buy_groups']
        jobs_by_window[window]=ss
        for s in ss:held_audit.append(dict(window=window,mint=s['mint'],rule=s['rule'],signature=s['signal_signature'],**creator_hold(raw[s['mint']],s)))
    assert all(a['known'] for a in held_audit),'must recover unknown developer observations before gate claims'
    (OUT/'CREATOR_HOLDINGS.json').write_text(json.dumps(held_audit,indent=2)+'\n');rows=[];errors=[]
    for window,ss in jobs_by_window.items():
        tapes,_,_=R.prepare(window,selection[window]);jobs=[(s,horizon,target,sc,fee,ticket) for s in ss for horizon,target in ([(h,t) for h in [60,120] for t in [.20,.35]] if s['rule']=='s3_deadman' else [(0,0)]) for sc,fee in [(x,1505000) for x in ['fast','central80','central85','slow','stress']]+[('central85',2916000)] for ticket in [.5,.25]]
        def run(j):
            s,horizon,target,sc,fee,ticket=j
            cfg=dict(s3_extended_hold=horizon,s3_grace=8,s3_full_target=target,s3_emergency_reserve=8) if horizon else {}
            return dict(E.simulate(tapes[s['mint']],s,sc,'lower',ticket,fee,cfg),window=window,horizon=horizon,profit_target=target)
        with concurrent.futures.ThreadPoolExecutor(4) as ex:
            fs={ex.submit(run,j):j for j in jobs}
            for f in concurrent.futures.as_completed(fs):
                try:rows.append(f.result())
                except Exception as e:errors.append(dict(window=window,job=fs[f],error=repr(e)))
        print('S3_REPLAY',window,len(rows),len(errors),flush=True)
    common=[r for r in rows if r['horizon']==0];rows=[r for r in rows if r['horizon']]
    for horizon in [60,120]:
        for target in [.20,.35]:rows.extend(dict(r,horizon=horizon,profit_target=target) for r in common)
    with gzip.open(OUT/'REPLAY.json.gz','wt',compresslevel=1) as f:json.dump(rows,f)
    (OUT/'ERRORS.json').write_text(json.dumps(errors,indent=2)+'\n');holds={(a['window'],a['mint'],a['rule'],a['signature']):a for a in held_audit};results=[]
    for horizon in [60,120]:
      for target in [.20,.35]:
        for gate in [False,True]:
            for window in ['earlier','later','continuous']:
                for sc,fee in [(x,1505000) for x in ['fast','central80','central85','slow','stress']]+[('central85',2916000)]:
                    rr=[r for r in rows if r['horizon']==horizon and r['profit_target']==target and r['scenario']==sc and r['fee']==fee and (window=='continuous' or r['window']==window)]
                    rejected=[r for r in rr if gate and not holds[(r['window'],r['mint'],r['rule'],r['signal_signature'])]['passes']]
                    rr=[r for r in rr if not gate or holds[(r['window'],r['mint'],r['rule'],r['signal_signature'])]['passes']]
                    for scope in ['portfolio','portfolio_without_carryover']+F.RULES:
                        for br in [False,True]:results.append(dict(horizon=horizon,profit_target=target,developer_gate=gate,window=window,scenario=sc,fee=fee,developer_rejections=sum(r['ticket']==.5 for r in rejected if scope=='portfolio' or scope=='portfolio_without_carryover' and r['rule']!='s5_carryover' or scope==r['rule']),**F.funded(rr,br,scope)))
    (OUT/'FUNDED.json').write_text(json.dumps(results,indent=2)+'\n');print('COMPLETE',len(rows),len(errors),len(results),flush=True)
    for r in results:
        if r['window']=='continuous' and r['scenario']=='central85' and r['fee']==1505000 and r['breakers'] and r['scope'] in ['portfolio','portfolio_without_carryover','s3_deadman']:
            print(r['horizon'],r['profit_target'],r['developer_gate'],r['scope'],r['net_zero_SOL'],r['net_marked_SOL'],r['attempts'],r['closed'],r['failed'],r['unresolved'],flush=True)

if __name__=='__main__':main()
