"""Second bounded entry-first cycle; all four dates are development now."""
import collections, concurrent.futures, datetime, gzip, hashlib, json, pickle, pathlib
import variants as V, entry_only as N
import signals as S
P=V.P; FRESH=P/'fresh_oct05_oct06'; OUT=P/'demand_and_bounce_cycle'; OUT.mkdir(exist_ok=True)
ENTRIES={'baseline':{},'broad_demand':dict(demand_gate=True),'first_time_demand':dict(demand_gate=True,first_time_gate=True)}

def select():
    raw=pickle.load(gzip.open(FRESH/'REPAIRED_SELECTION.pkl.gz','rb')); selections={};errors=[]
    for name,cfg in ENTRIES.items():
        ss=[]
        for t in raw:
            s,e=S.detect(t,cfg);ss+=s;errors.extend(dict(variant=name,mint=t['mint'],**x) for x in e)
        selections[name]=ss
        print(name,len(ss),dict(collections.Counter(s['rule'] for s in ss)),flush=True)
    baseline=json.loads((FRESH/'SIGNALS.json').read_text())
    key=lambda s:(s['mint'],s['rule'],s['signal_signature'])
    assert {key(s) for s in selections['baseline']}=={key(s) for s in baseline},'default signal behavior changed'
    assert not errors,errors[:5]
    old={s['mint'] for s in baseline}
    assert all(s['mint'] in old for ss in selections.values() for s in ss),'new eligible mint requires intake'
    # A prefix containing a chosen decision must produce that same decision.
    by={t['mint']:t for t in raw};prefix_count=0
    for name in ['broad_demand','first_time_demand']:
        for s in selections[name]:
            if s['rule'] not in ['s2_survival_shelf','s4_upper_ath']:continue
            t=by[s['mint']];i=next(i for i,g in enumerate(t['groups']) if g['signature']==s['signal_signature'])
            pp,_=S.detect(dict(t,groups=t['groups'][:i+1]),ENTRIES[name])
            assert key(s) in {key(z) for z in pp};prefix_count+=1
    (OUT/'SIGNALS.json').write_text(json.dumps(selections,indent=2)+'\n')
    (OUT/'SELECTION_CHECKS.json').write_text(json.dumps(dict(default_parity=True,prefix_checks=prefix_count,errors=errors),indent=2)+'\n')
    return selections

def prepare(ss):
    ep=OUT/'execution';(ep/'amm_tapes').mkdir(parents=True,exist_ok=True);(ep/'bound_curve_tapes').mkdir(exist_ok=True)
    (ep/'SIGNALS.json').write_text(json.dumps(ss)+'\n'); latest={}
    for s in ss:latest[s['mint']]=max(latest.get(s['mint'],0),s['time'])
    for f in (FRESH/'execution/bound_curve_tapes').glob('*.gz'):
        dst=ep/'bound_curve_tapes'/f.name
        if not dst.exists():dst.symlink_to(f.resolve())
    for f in (FRESH/'normalized_amm_tapes').glob('*.gz'):
        t=json.load(gzip.open(f,'rt'))
        if t['mint'] not in latest:continue
        t['groups']=[g for i,g in enumerate(t['groups']) if i==0 or g['time']<=latest[t['mint']]+660]
        with gzip.open(ep/'amm_tapes'/f.name,'wt',compresslevel=1) as o:json.dump(t,o)
    V.E.P=ep;V.E.OLD=FRESH;V.E.O.C.P=ep
    return V.E.load()[0]

def main():
    spec=dict(frozen_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),status='retrospective development on inspected October5–6; not holdout',entry_looks=2,exit_looks=3,prior_new_looks=18,entry_configs=ENTRIES,exit_configs={'confirmed_full5':dict(s3_full_target=.05),'confirmed_full10':dict(s3_full_target=.10),'confirmed_scratch3':dict(s3_scratch=3)},entry_first='Neutral exit-free trajectories completed before sell outcomes; exact original shelf/ATH conditions still required at each qualifying prefix',denominators='all attempts, filled and horizon-known separate',hashes={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in [pathlib.Path(__file__),V.BASE/'signals.py',V.BASE/'engine.py']})
    (OUT/'SPEC.json').write_text(json.dumps(spec,indent=2)+'\n')
    selections=select();allss={ (s['mint'],s['rule'],s['signal_signature']):s for ss in selections.values() for s in ss};tapes=prepare(list(allss.values()));jobs=[]
    for name in ['broad_demand','first_time_demand']:
        for s in selections[name]:
            if s['rule'] not in ['s2_survival_shelf','s4_upper_ath']:continue
            for sc in ['central80','central85']:jobs.append((name,s,sc))
    rows=[];errors=[]
    def run(j):
        name,s,sc=j;return dict(N.trace(tapes[s['mint']],s,sc),variant=name)
    with concurrent.futures.ThreadPoolExecutor(4) as ex:
        futures={ex.submit(run,j):j for j in jobs}
        for f in concurrent.futures.as_completed(futures):
            try:rows.append(f.result())
            except Exception as e:errors.append(dict(job=futures[f],error=repr(e)))
    with gzip.open(OUT/'ENTRY_TRAJECTORIES.json.gz','wt',compresslevel=1) as o:json.dump(rows,o)
    (OUT/'ENTRY_ERRORS.json').write_text(json.dumps(errors,indent=2)+'\n')
    print('ENTRY_DONE',len(rows),len(errors),flush=True)

if __name__=='__main__':main()
