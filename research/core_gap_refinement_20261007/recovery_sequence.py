"""Entry-first sustained-recovery test on both inspected windows."""
import collections,concurrent.futures,datetime,gzip,hashlib,json,pathlib,pickle,sys
import variants as V,entry_only as N,next_mechanisms as C
P=V.P;OUT=P/'recovery_sequence_cycle';OUT.mkdir(exist_ok=True)
MODES=['first_buy','second_event','two_buy_groups']

def choose(t,s,mode):
    i=next(i for i,g in enumerate(t['groups']) if g['signature']==s['signal_signature']);count=0;first=set();groups=0
    for g in t['groups'][i+1:]:
        if g['slot']>s['slot']+2 or g['state']['rtokens_raw']==0:break
        if not g['events']:continue
        count+=1
        buyers={e['user'] for e in g['events'] if e['buy'] and e['user']!=t['creator'] and e['sol_raw']>=50000000}
        if buyers:
            groups+=1
            if groups==1:first=buyers
        yes=bool(buyers) if mode=='first_buy' else count==2 if mode=='second_event' else groups>=2 and bool(buyers-first)
        if yes:
            r=g['state']['rsol_raw']/1e9
            if not 8<=r<=18:return None
            return dict(s,original_signal_signature=s['signal_signature'],original_signal_slot=s['slot'],signal_signature=g['signature'],slot=g['slot'],time=g['block_time'],reserve=r,confirmation_groups=count,confirmation_buy_groups=groups)
    return None

def source(window):
    if window=='earlier':
        V.E.P=V.BASE;V.E.OLD=P.parent/'wallet_curve_entry_discovery_20261007';V.E.O.C.P=V.E.P
        tapes,baseline=V.E.load();raw=pickle.load(gzip.open(P.parent/'day_general_20261004/TAPES.pkl.gz','rb'))
    else:
        baseline=json.loads((C.FRESH/'SIGNALS.json').read_text());raw=pickle.load(gzip.open(C.FRESH/'REPAIRED_SELECTION.pkl.gz','rb'));tapes=None
    return tapes,baseline,{t['mint']:t for t in raw}

def prepare(window,selection):
    tapes,baseline,raw=source(window)
    if window=='later':
        saved=C.OUT;C.OUT=OUT/'later';C.OUT.mkdir(exist_ok=True)
        tapes=C.prepare(baseline+[s for ss in selection.values() for s in ss]);C.OUT=saved
    return tapes,baseline,raw

def entries():
    spec=dict(frozen_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),status='retrospective October3–6development; all inspected',prior_logged_looks=28,new_entry_definitions=2,entry_modes=MODES,description='First >=0.05SOL outside buy control; second eventful whole transaction delay control; two separate >=0.05SOL outside buying transactions with a new distinct buyer. All within original2slot window after first qualifying dip and reserves8–18; no threshold selected from new outcomes.',entry_first='Exit-free neutral trajectories before sells; old unchanged10s/21s and earlier3s scratch as two fixed exit comparisons',hashes={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in [pathlib.Path(__file__),V.BASE/'engine.py',P/'entry_only.py']})
    (OUT/'SPEC.json').write_text(json.dumps(spec,indent=2)+'\n');allselection={};results=[];errors=[];audit=[];features=[]
    for window in ['earlier','later']:
        _,baseline,raw=source(window);selection={mode:[] for mode in MODES};prefixes=0
        for s in baseline:
            if s['rule']!='s3_deadman':continue
            t=raw[s['mint']];i=next(i for i,g in enumerate(t['groups']) if g['signature']==s['signal_signature']);h=V.E.A.build.inventory(t['groups'][:i+1]);whales=[e for e in t['groups'][i]['events'] if not e['buy'] and e['user']!=t['creator'] and e['sol_raw']>=1500000000];holders=sorted([max(0,x) for x in h.values()],reverse=True);total=sum(holders)
            features.append(dict(window=window,mint=s['mint'],whale_remaining_raw={e['user']:h.get(e['user'],0) for e in whales},top10_supply_share=sum(holders[:10])/total if total else None))
            for mode in MODES:
                chosen=choose(t,s,mode)
                if chosen:
                    selection[mode].append(chosen);j=next(j for j,g in enumerate(t['groups']) if g['signature']==chosen['signal_signature']);check=choose(dict(t,groups=t['groups'][:j+1]),s,mode);assert check==chosen;prefixes+=1
        first=V.selected(baseline,raw,'deadman_confirm');key=lambda s:(s['mint'],s['signal_signature']);assert {key(s) for s in first}=={key(s) for s in selection['first_buy']}
        allselection[window]=selection;tapes,_,_=prepare(window,selection);jobs=[(mode,s,sc) for mode,ss in selection.items() for s in ss for sc in ['central80','central85']]
        def run(j):
            mode,s,sc=j;return dict(N.trace(tapes[s['mint']],s,sc),mode=mode,window=window)
        with concurrent.futures.ThreadPoolExecutor(4) as ex:
            fs={ex.submit(run,j):j for j in jobs}
            for f in concurrent.futures.as_completed(fs):
                try:results.append(f.result())
                except Exception as e:errors.append(dict(window=window,job=fs[f],error=repr(e)))
        audit.append(dict(window=window,baseline_dips=sum(s['rule']=='s3_deadman' for s in baseline),selection={k:len(v) for k,v in selection.items()},prefix_checks=prefixes,first_buy_parity=True));print('ENTRY',audit[-1],flush=True)
    (OUT/'SIGNALS.json').write_text(json.dumps(allselection,indent=2)+'\n');(OUT/'SELECTION_CHECKS.json').write_text(json.dumps(audit,indent=2)+'\n');(OUT/'SUPPLY_FEATURES.json').write_text(json.dumps(features,indent=2)+'\n')
    with gzip.open(OUT/'ENTRY_TRAJECTORIES.json.gz','wt',compresslevel=1) as f:json.dump(results,f)
    (OUT/'ENTRY_ERRORS.json').write_text(json.dumps(errors,indent=2)+'\n');print('ENTRY_DONE',len(results),len(errors),flush=True)

def sells():
    assert not json.loads((OUT/'ENTRY_ERRORS.json').read_text());assert (OUT/'ENTRY_TRAJECTORIES.json.gz').exists()
    allselection=json.loads((OUT/'SIGNALS.json').read_text());rows=[];errors=[]
    (OUT/'SELL_SPEC.json').write_text(json.dumps(dict(frozen_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),recipes=['original','scratch3'],new_assembly_looks=2,total_logged_looks=32,full_portfolio='Replace only S3 entry/exit, other four families remain frozen; neither graduation nor tape end closes inventory'),indent=2)+'\n')
    for window,selection in allselection.items():
        tapes,baseline,_=prepare(window,selection);jobs=[(mode,recipe,s,sc,fee,ticket) for mode,ss in selection.items() for recipe in ['original','scratch3'] for s in ss for sc,fee in [(x,1505000) for x in ['fast','central80','central85','slow','stress']]+[('central85',2916000)] for ticket in [.5,.25]]
        def run(j):
            mode,recipe,s,sc,fee,ticket=j;cfg={} if recipe=='original' else dict(s3_scratch=3)
            return dict(V.E.simulate(tapes[s['mint']],s,sc,'lower',ticket,fee,cfg),mode=mode,recipe=recipe,window=window)
        with concurrent.futures.ThreadPoolExecutor(4) as ex:
            fs={ex.submit(run,j):j for j in jobs}
            for f in concurrent.futures.as_completed(fs):
                try:rows.append(f.result())
                except Exception as e:errors.append(dict(window=window,job=fs[f],error=repr(e)))
        print('SELL',window,len(rows),len(errors),flush=True)
    with gzip.open(OUT/'REPLAY.json.gz','wt',compresslevel=1) as f:json.dump(rows,f)
    (OUT/'ERRORS.json').write_text(json.dumps(errors,indent=2)+'\n');print('SELL_DONE',len(rows),len(errors),flush=True)

if __name__=='__main__':
    if '--sell' in sys.argv:sells()
    else:entries()
