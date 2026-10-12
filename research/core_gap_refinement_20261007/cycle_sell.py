"""Causal sell tests following the second cycle's completed neutral diagnostics."""
import collections,concurrent.futures,datetime,gzip,json,pickle
import next_mechanisms as C
P,OUT,E,F=C.P,C.OUT,C.V.E,C.V.F
CONFIGS={'confirmed_control':{},'confirmed_full5':dict(s3_full_target=.05),'confirmed_full10':dict(s3_full_target=.10),'confirmed_scratch3':dict(s3_scratch=3)}

def main():
    assert (OUT/'ENTRY_TRAJECTORIES.json.gz').exists()
    assert not json.loads((OUT/'ENTRY_ERRORS.json').read_text())
    selection=json.loads((OUT/'SIGNALS.json').read_text());raw={t['mint']:t for t in pickle.load(gzip.open(C.FRESH/'REPAIRED_SELECTION.pkl.gz','rb'))}
    confirmed=C.V.selected(selection['baseline'],raw,'deadman_confirm')
    complete={}
    for v in CONFIGS:complete[v]=confirmed+[s for s in selection['baseline'] if s['rule']!='s3_deadman']
    for v in ['broad_demand','first_time_demand']:complete[v]=selection[v]
    (OUT/'SELL_SPEC.json').write_text(json.dumps(dict(frozen_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),development=True,new_entry_mechanisms=2,new_exit_mechanisms=3,portfolio_assemblies=3,total_new_looks_including_prior=26,configs=CONFIGS,control='Original Starting Five lower exits on gated entries; confirmed S3 control with original exits; all other strategies unchanged, every S5 retained'),indent=2)+'\n')
    ss={ (s['mint'],s['rule'],s['signal_signature']):s for arr in complete.values() for s in arr};tapes=C.prepare(list(ss.values()));jobs=[]
    for v,arr in complete.items():
        changed=[s for s in arr if s['rule'] in ['s2_survival_shelf','s4_upper_ath']] if v in C.ENTRIES else [s for s in arr if s['rule']=='s3_deadman']
        for sc,fee in [(s,1505000) for s in ['fast','central80','central85','slow','stress']]+[('central85',2916000)]:
            for s in changed:
                for ticket in [.5,.25]:jobs.append((v,s,sc,fee,ticket))
    def run(j):
        v,s,sc,fee,ticket=j
        return dict(E.simulate(tapes[s['mint']],s,sc,'lower',ticket,fee,CONFIGS.get(v,{})),variant=v,placement_seed=0)
    rows=[];errors=[]
    with concurrent.futures.ThreadPoolExecutor(4) as ex:
        fs={ex.submit(run,j):j for j in jobs}
        for f in concurrent.futures.as_completed(fs):
            try:rows.append(f.result())
            except Exception as e:errors.append(dict(job=fs[f],error=repr(e)))
            if (len(rows)+len(errors))%200==0:print('CYCLE_SELL',len(rows),len(errors),len(jobs),flush=True)
    # Reuse unchanged counterfactual paths, not their funded admission results.
    baseline=[r for r in json.load(gzip.open(P/'TRANSFER_REPLAY.json.gz','rt')) if r['variant']=='baseline' and r['placement_seed']==0]
    for v in complete:
        keep=['s1_dev_absorption','s3_deadman','s5_carryover'] if v in C.ENTRIES else ['s1_dev_absorption','s2_survival_shelf','s4_upper_ath','s5_carryover']
        rows.extend(dict(r,variant=v) for r in baseline if r['rule'] in keep)
    with gzip.open(OUT/'REPLAY.json.gz','wt',compresslevel=1) as o:json.dump(rows,o)
    (OUT/'ERRORS.json').write_text(json.dumps(errors,indent=2)+'\n');groups=collections.defaultdict(list)
    for r in rows:groups[(r['variant'],r['scenario'],r['fee'])].append(r)
    results=[]
    for (v,sc,fee),rr in sorted(groups.items()):
        for scope in ['portfolio','portfolio_without_carryover']+F.RULES:
            for br in [False,True]:results.append(dict(variant=v,scenario=sc,fee=fee,placement_seed=0,**F.funded(rr,br,scope)))
    (OUT/'FUNDED.json').write_text(json.dumps(results,indent=2)+'\n')
    print('COMPLETE',len(rows),len(errors),len(results),flush=True)
    for r in results:
        if r['scenario']=='central85' and r['fee']==1505000 and not r['breakers'] and r['scope'] in ['portfolio_without_carryover','s2_survival_shelf','s3_deadman','s4_upper_ath']:
            print(r['variant'],r['scope'],r['net_zero_SOL'],r['net_marked_SOL'],r['attempts'],r['closed'],r['failed'],r['unresolved'],flush=True)

if __name__=='__main__':main()
