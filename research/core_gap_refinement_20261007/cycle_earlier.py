"""Same frozen demand mechanisms on earlier inspected data, never a holdout."""
import collections,concurrent.futures,gzip,json,pickle
import cycle_sell as C
P,OUT,E,F=C.P,C.OUT,C.E,C.F

def main():
    E.P=C.C.V.BASE;E.OLD=P.parent/'wallet_curve_entry_discovery_20261007';E.O.C.P=E.P
    tapes,original=E.load();raw=pickle.load(gzip.open(P.parent/'day_general_20261004/TAPES.pkl.gz','rb'));ss={};default=[];prefix_checks=0
    key=lambda s:(s['mint'],s['rule'],s['signal_signature'])
    for t in raw:
        s,errors=C.C.S.detect(t);assert not errors,errors;default+=s
    assert {key(s) for s in default}=={key(s) for s in original}
    for v in ['broad_demand','first_time_demand']:
        arr=[]
        for t in raw:
            s,errors=C.C.S.detect(t,C.C.ENTRIES[v]);assert not errors,errors
            arr.extend(z for z in s if z['rule'] in ['s2_survival_shelf','s4_upper_ath'])
        assert all(s['mint'] in tapes for s in arr),'new eligible mint needs intake'
        ss[v]=arr
        by={t['mint']:t for t in raw}
        for s in arr:
            t=by[s['mint']];i=next(i for i,g in enumerate(t['groups']) if g['signature']==s['signal_signature'])
            pre,errors=C.C.S.detect(dict(t,groups=t['groups'][:i+1]),C.C.ENTRIES[v]);assert not errors
            assert key(s) in {key(z) for z in pre};prefix_checks+=1
    jobs=[(v,s,sc,fee,ticket) for v,arr in ss.items() for s in arr for sc,fee in [(x,1505000) for x in ['fast','central80','central85','slow','stress']]+[('central85',2916000)] for ticket in [.5,.25]]
    rows=[]
    def run(j):
        v,s,sc,fee,ticket=j;return dict(E.simulate(tapes[s['mint']],s,sc,'lower',ticket,fee),variant=v,placement_seed=0)
    with concurrent.futures.ThreadPoolExecutor(4) as ex:rows=list(ex.map(run,jobs))
    with gzip.open(OUT/'EARLIER_REPLAY.json.gz','wt',compresslevel=1) as o:json.dump(rows,o)
    results=[];groups=collections.defaultdict(list)
    for r in rows:groups[(r['variant'],r['scenario'],r['fee'],r['rule'])].append(r)
    for (v,sc,fee,rule),rr in sorted(groups.items()):
        for br in [False,True]:results.append(dict(variant=v,scenario=sc,fee=fee,placement_seed=0,**F.funded(rr,br,rule)))
    (OUT/'EARLIER_FUNDED.json').write_text(json.dumps(results,indent=2)+'\n')
    checks=dict(default_signal_parity=True,prefix_checks=prefix_checks,
        pre_deadline_timer_fills=[r['mint'] for r in rows for l in r['legs'] if l.get('timer_target') is not None and l['time']<l['timer_target']],
        completed_curve_sales=[r['mint'] for r in rows for l in r['legs'] if l['venue']=='curve' and l['state_before']['rtokens_raw']==0],
        token_errors=[r['mint'] for r in rows if r['status']!='failed' and sum(l['tokens'] for l in r['legs'])+r['remaining']!=r['entry_tokens']],
        source_evidence='All eligible mints remain within original600creation-selected cohort; repaired approved source parity in parent pilot.',
        delayed_failed=sum(r['status']=='failed' for r in rows if r['scenario']=='slow'),
        extremes=[r['variant'] for r in results if r['closed']>50 and ((r['profit_factor'] or 0)>3 or (r['win_rate'] or 0)>.7)])
    assert not any(checks[k] for k in ['pre_deadline_timer_fills','completed_curve_sales','token_errors','extremes'])
    (OUT/'EARLIER_CHECKS.json').write_text(json.dumps(checks,indent=2)+'\n')
    print('EARLIER_DONE',len(rows),len(results),flush=True)
    for r in results:
        if r['scenario']=='central85' and r['fee']==1505000 and not r['breakers']:print(r['variant'],r['scope'],r['net_zero_SOL'],r['largest_winner_SOL'],r['net_without_largest_SOL'],r['attempts'],r['closed'],r['failed'],r['unresolved'],flush=True)

if __name__=='__main__':main()
