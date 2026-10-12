"""Unchanged frozen plan's upper endpoints on the same later cohort."""
import concurrent.futures, gzip, json
import transfer as T

P, E, F = T.P, T.E, T.F

def main():
    E.P=T.FRESH/'execution'; E.OLD=T.FRESH; E.O.C.P=E.P
    tapes, signals=E.load()
    jobs=[(tapes[s['mint']],s,sc,fee,ticket) for sc,fee in
          [(s,1505000) for s in ['fast','central80','central85','slow','stress']]+[('central85',2916000)]
          for s in signals for ticket in [.5,.25]]
    rows=[]; errors=[]
    def run(j):
        t,s,sc,fee,ticket=j
        return dict(E.simulate(t,s,sc,'upper',ticket,fee),variant='baseline',placement_seed=0)
    with concurrent.futures.ThreadPoolExecutor(4) as ex:
        for n,f in enumerate(ex.map(run,jobs),1):
            rows.append(f)
            if n%200==0: print('UPPER',n,len(jobs),flush=True)
    with gzip.open(P/'UPPER_REPLAY.json.gz','wt',compresslevel=1) as out: json.dump(rows,out)
    (P/'UPPER_ERRORS.json').write_text(json.dumps(errors)+'\n')
    results=[]
    for sc,fee in sorted({(r['scenario'],r['fee']) for r in rows}):
        rr=[r for r in rows if r['scenario']==sc and r['fee']==fee]
        for scope in ['portfolio','portfolio_without_carryover']+F.RULES:
            for br in [False,True]:
                results.append(dict(variant='baseline',endpoint='upper',scenario=sc,fee=fee,placement_seed=0,**F.funded(rr,br,scope)))
    (P/'UPPER_FUNDED.json').write_text(json.dumps(results,indent=2)+'\n')
    print('COMPLETE',len(rows),len(results),flush=True)

if __name__=='__main__': main()
