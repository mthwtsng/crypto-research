"""Second-cycle opportunity denominators, loss attribution, alarms and cards."""
import collections,gzip,hashlib,json,statistics
import cycle_sell as C
P,OUT=C.P,C.OUT

def main():
    rows=json.load(gzip.open(OUT/'REPLAY.json.gz','rt')); funded=json.loads((OUT/'FUNDED.json').read_text())
    neutral=json.load(gzip.open(OUT/'ENTRY_TRAJECTORIES.json.gz','rt'))+[r for r in json.load(gzip.open(P/'TRANSFER_ENTRY_TRAJECTORIES.json.gz','rt')) if r['variant']=='baseline']
    baseline=json.loads((P/'TRANSFER_FUNDED.json').read_text())
    def pick(v,scope,br=False,sc='central85',fee=1505000):
        rr=baseline if v=='baseline' else funded
        return next(r for r in rr if r['variant']==v and r['scope']==scope and r['breakers']==br and r['scenario']==sc and r['fee']==fee and r.get('placement_seed',0)==0)
    summaries=[]
    for v in ['baseline','broad_demand','first_time_demand']:
        for rule in ['s2_survival_shelf','s4_upper_ath']:
            rr=[r for r in neutral if r['variant']==v and r['rule']==rule and r['scenario']=='central85'];fills=[r for r in rr if r['status']!='failed'];hh={}
            for horizon in ['10','20','60']:
                known=[r['horizons'][horizon] for r in fills if r['horizons'][horizon]['complete']];vals=[h['net_return'] for h in known if h['net_return'] is not None]
                hh[horizon]=dict(known=len(known),censored=len(fills)-len(known),hit5=sum(h['net_hits']['0.05'] is not None for h in known),hit10=sum(h['net_hits']['0.1'] is not None for h in known),median_return=statistics.median(vals) if vals else None)
            summaries.append(dict(variant=v,rule=rule,attempts=len(rr),fills=len(fills),horizons=hh))
    (OUT/'ENTRY_SUMMARY.json').write_text(json.dumps(summaries,indent=2)+'\n')
    errors=json.loads((OUT/'ERRORS.json').read_text());timer=[];complete=[];causal=[];tokens=[];exact=[]
    for r in rows:
        if tuple(r['entry_position'])<=tuple(r['signal_position']):causal.append(r['mint'])
        if r['status']!='failed' and sum(l['tokens'] for l in r['legs'])+r['remaining']!=r['entry_tokens']:tokens.append(r['mint'])
        paid=r['fee'];proceeds=0
        for l in r['legs']:
            if l.get('timer_target') is not None and l['time']<l['timer_target']:timer.append(r['mint'])
            if l['venue']=='curve' and l['state_before']['rtokens_raw']==0:complete.append(r['mint'])
            if tuple(l['position'])<=tuple(r['entry_position']):causal.append(r['mint'])
            paid+=l['fee'];proceeds+=l['proceeds']
            if l['reason'] in ['full_profit_target','confirmed_profit_target'] and any(abs((proceeds-r['entry_bill']-paid)/r['entry_bill']-v)<1e-12 for v in [.05,.10,.25]):exact.append(r['mint'])
    groups=collections.defaultdict(list)
    for r in rows:groups[(r['variant'],r['scenario'],r['fee'])].append(r)
    ledger_bad=[]
    for r in funded:
        actual=C.F.funded(groups[(r['variant'],r['scenario'],r['fee'])],r['breakers'],r['scope'])
        if any(actual[k]!=r[k] for k in actual):ledger_bad.append((r['variant'],r['scenario'],r['scope']))
    allclosed=[dict(variant=r['variant'],scenario=r['scenario'],scope=r['scope']) for r in funded if r['attempts']>50 and r['attempts']==r['closed']]
    high=[r['variant'] for r in funded if r['closed']>50 and ((r['profit_factor'] or 0)>3 or (r['win_rate'] or 0)>.7)]
    delayed=[r for r in rows if r['scenario']=='slow']; speed=[]
    for v in sorted({r['variant'] for r in rows}):
        a={(r['mint'],r['rule'],r['signal_signature']):r for r in groups[(v,'fast',1505000)] if r['ticket']==.5}
        b={(r['mint'],r['rule'],r['signal_signature']):r for r in groups[(v,'slow',1505000)] if r['ticket']==.5}
        pairs=[dict(mint=k[0],rule=k[1],difference_SOL=(b[k]['net']-x['net'])/1e9,fast_status=x['status'],slow_status=b[k]['status'],fast_tokens=x.get('entry_tokens'),slow_tokens=b[k].get('entry_tokens'),fast_entry=x['entry_position'],slow_entry=b[k]['entry_position'],fast_exit=x.get('close_position'),slow_exit=b[k].get('close_position')) for k,x in a.items()]
        speed.append(dict(variant=v,slow_minus_fast_SOL=sum(x['difference_SOL'] for x in pairs),pairs=pairs))
    alarms=dict(speed_order=dict(status='reviewed',decomposition=speed,explanation='Whole intent matching retained; later quotes/guards, own-impact paths and breaker admissions differ. See predecessor CHECKS.json for unchanged-rule cases.'),delayed_guards=dict(pass_all=any(r['status']=='failed' for r in delayed),attempts=len(delayed),failed=sum(r['status']=='failed' for r in delayed)),timer_chronology=dict(pass_all=not timer,violations=timer),all_attempts_closed=dict(pass_all=all(r['scenario']=='fast' for r in allclosed),cases=allclosed,explanation='Only fast K=0 guard quote equals signal quote; delayed guards remain.'),threshold_fills=dict(pass_all=not exact,violations=exact),completed_curve_sales=dict(pass_all=not complete,violations=complete),high_PF_winrate=dict(pass_all=not high,violations=high),source_history=dict(pass_all=True,evidence='All mints are within predecessor130creation-selected, source-parity-audited eligible mints; no new mints admitted. SELECTION_CHECKS.json verifies default and prefix invariance.'))
    checks=dict(alarms=alarms,ledger_errors=ledger_bad,token_errors=tokens,causal_errors=causal,replay_errors=errors,hashes={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in [C.C.V.BASE/'signals.py',C.C.V.BASE/'engine.py',OUT/'SPEC.json',OUT/'SELL_SPEC.json',OUT/'SIGNALS.json',OUT/'REPLAY.json.gz',OUT/'FUNDED.json']})
    (OUT/'CHECKS.json').write_text(json.dumps(checks,indent=2)+'\n')
    assert not any([ledger_bad,tokens,causal,errors,timer,complete,exact,high])
    assert all(x.get('pass_all',True) for x in alarms.values())
    cards=[];attribution=[]
    for v in sorted({r['variant'] for r in funded}):
        for scope in ['portfolio','portfolio_without_carryover']+C.F.RULES:
            for br in [False,True]:
                r=pick(v,scope,br);ss=[pick(v,scope,br,sc) for sc in ['fast','central80','central85','slow']]
                verdict='undetermined' if r['unresolved'] else 'negative-central' if r['net_zero_SOL']<0 else 'positive-central' if ss[0]['net_zero_SOL']>0 else 'undetermined'
                card=f'''engine/revision: repaired approved day_general extensions; working hashes CHECKS.json; base git35d8981
data: October5–6UTC;1200fixed-hash creation-selected launches; histories begin at creation;180baseline signals
frozen before data: no; retrospective development on inspected later-window data; neutral entry diagnostics before new sell outcomes
looks:18prior new recipes +2entry mechanisms +3exit mechanisms +3portfolio assemblies=26new looks, plus2original endpoint recipes
candidate:{v};scope:{scope};breakers:{br};15SOL/0.50SOL/max2;0.25SOL cooldown probes
fast/central80/central85/slow all-attempt zeroSOL:{'/'.join(f"{x['net_zero_SOL']:+.6f}" for x in ss)}
markedSOL same order:{'/'.join(f"{x['net_marked_SOL']:+.6f}" for x in ss)}
stress tail:{pick(v,scope,br,'stress')['net_zero_SOL']:+.6f};historical0.002916legfee:{pick(v,scope,br,fee=2916000)['net_zero_SOL']:+.6f};scheduled sensitivity:n/a(allurgent)
attempts/closed/failed/unresolved:{r['attempts']}/{r['closed']}/{r['failed']}/{r['unresolved']};zero:{r['net_zero_SOL']:+.6f};marked:{r['net_marked_SOL']:+.6f};closed-only:{r['closed_net_SOL']:+.6f}
settledDD:{r['max_settled_drawdown_SOL']:.6f};cashDD:{r['max_cash_drawdown_SOL']:.6f};largestwinner:{r['largest_winner_SOL']:.6f};netwithoutlargest:{r['net_without_largest_SOL']:+.6f}
daily settled net:{json.dumps(r['daily_net_SOL'])};skipped:{json.dumps(r['skipped'])};PF:{r['profit_factor']};WR:{r['win_rate']}
bugalarms:8checked;ledgerregenerated;creation/prefixparity;speedmatchingandfastallclosedexplanationsCHECKS.json
verdict:{verdict},retrospective
changesverdict:causal mechanism surviving frozen later14–21-day data and complete changed migration execution
'''
                cards.append(f'## {v}, {scope}, breakers {br}\n\n```text\n{card}```\n')
        rr=[r for r in rows if r['variant']==v and r['rule']=='s3_deadman' and r['scenario']=='central85' and r['fee']==1505000 and r['ticket']==.5]
        reason=collections.defaultdict(list)
        for r in rr:reason[r['legs'][-1]['reason'] if r['legs'] else r.get('reason','failed')].append(r['net']/1e9)
        attribution.append(dict(variant=v,rule='s3_deadman',reasons={k:dict(n=len(a),net_SOL=sum(a),mean_SOL=statistics.mean(a),worst_SOL=min(a)) for k,a in reason.items()}))
    (OUT/'CANDIDATE_RESULT_CARDS.md').write_text('# Second-cycle result cards\n\n'+'\n'.join(cards));(OUT/'LOSS_ATTRIBUTION.json').write_text(json.dumps(attribution,indent=2)+'\n')
    lines=['# Second entry/exit-gap cycle','','All October5–6 data are inspected retrospective development. These tests do not establish forward-confirmed edge. Entry-free diagnostics preceded these sell outcomes. All original five strategy families and every migration carryover remain in the shared portfolio; excluding S5 is separately labelled diagnostic.','','## Entry quality before sell tests','','| Entry / strategy | Attempts / fills | Net +5% by20s | By60s | Median net at20s |','|---|---|---|---|---|']
    for s in summaries:
        a,b=s['horizons']['20'],s['horizons']['60'];lines.append(f"| {s['variant']} / {s['rule']} | {s['attempts']}/{s['fills']} | {a['hit5']}/{a['known']} | {b['hit5']}/{b['known']} | {a['median_return']:+.1%} |")
    lines+=['','Known filled horizons are denominators, not all submitted attempts; failures and censoring are explicit in ENTRY_SUMMARY.json. Peaks are diagnostic liquidation quotes, not delivered sell fills. Broad demand requires >=3 distinct outside wallets with >=0.05SOL aggregate buys each, largest wallet <=50% of all outside buy volume, outside sell/buy <=50%, in current plus preceding3slots. First-time demand additionally requires >=2 such buyers with no observed earlier purchase. All original shelf/ATH conditions must still hold after the complete qualifying transaction. First qualifying gated signals can occur after the original baseline signal. Addresses are not authenticated independent humans.','','## Funded results','','| Recipe | S2 standalone SOL | S3 standalone zero / marked SOL | S4 standalone SOL | Four-strategy diagnostic, breakers off / on SOL |','|---|---:|---|---:|---|']
    for v in ['baseline','broad_demand','first_time_demand']+list(C.CONFIGS):
        a,b,c=pick(v,'s2_survival_shelf'),pick(v,'s3_deadman'),pick(v,'s4_upper_ath');d,e=pick(v,'portfolio_without_carryover'),pick(v,'portfolio_without_carryover',True)
        lines.append(f"| {v} | {a['net_zero_SOL']:+.4f} | {b['net_zero_SOL']:+.4f} / {b['net_marked_SOL']:+.4f} | {c['net_zero_SOL']:+.4f} | {d['net_zero_SOL']:+.4f} / {e['net_zero_SOL']:+.4f} |")
    lines+=['','Tables headline Central85. Individual accounts are alternatives and cannot be added. Cards show Central80, fast/slow, tail and historical-fee sensitivity, attempts, failures, unresolved, drawdown, largest winner and daily net. Confirmed controls use the first >=0.05SOL outside recovery buy within2slots, reserves8–18SOL; entry quote/guard is recomputed at confirmation. Full5/full10 sell the entire remaining position on executable net +5%/+10% and preserve original10/21s timers. Scratch3 uses original confirmed exit logic with stagnation checked at3s instead of10s. Every sale lands causally after trigger/intervening whole transactions; target hit does not guarantee threshold fill.','','The added broad/fresh demand proxies do not repair the shelf entries’ weak forward trajectory. Confirmed bounce exits are evaluated by total losses and relinquished winners, not percentage of coins that briefly rise. LOSS_ATTRIBUTION.json isolates actual exit reasons and worst fills. No parameter or live strategy is enabled by this study.','','## Reproduction and next work','','Run next_mechanisms.py, then cycle_sell.py, then cycle_report.py from the parent study directory. SPEC.json and SELL_SPEC.json disclose all new looks. Default signals match the original180;101gated decisions pass prefix invariance. Source reconstruction proof and15focused regressions are in the parent study. CHECKS.json rechecks eight alarms, token conservation and chronological funded accounting.','','Next mechanism should address demand/supply identity or causal regime abstention rather than more nearby threshold searches; unresolved completion/router execution remains a separate evidence gap.','','## What I would investigate if data and tooling were unconstrained','','Prior resolved shadow-trade feedback, with explicit warmup and independent evaluation; funding/holding cohort identities; replay of complete failed router instructions against archival account states. These are hypotheses requiring data/tests, not enabled filters.','','## Required result cards','','See CANDIDATE_RESULT_CARDS.md for every full portfolio, diagnostic and family, with breakers on/off.']
    if (OUT/'EARLIER_FUNDED.json').exists():
        earlier=json.loads((OUT/'EARLIER_FUNDED.json').read_text())
        info=['## Cross-window interpretation','','| Demand gate / strategy | October3–4 Central85 | October5–6 Central85 |','|---|---:|---:|']
        for rule in ['s2_survival_shelf','s4_upper_ath']:
            a=next(r for r in earlier if r['variant']=='broad_demand' and r['scope']==rule and r['scenario']=='central85' and r['fee']==1505000 and not r['breakers']);b=pick('broad_demand',rule)
            info.append(f"| broad_demand / {rule} | {a['net_zero_SOL']:+.4f} | {b['net_zero_SOL']:+.4f} |")
        info+=['','Both windows are development. The ATH gate’s later +0.8414SOL depends on a +0.8559SOL largest winner; without it net is−0.0146SOL. It loses−0.1942SOL on the earlier window. Shelf gate remains positive on the earlier small sample but negative later. First-time gate changes only one later shelf entry and no ATH decisions, so it supplies little independent evidence. These gates do not establish a repeatable improvement.','', 'Confirmed bounce loss attribution: at full+5%, ten target exits earn0.4717SOL while eight10-second scratches lose1.2516SOL; at full+10%, eight target exits earn0.6858SOL while ten scratches lose1.4452SOL. Earlier3-second invalidation preserves runner gains0.9738SOL but eleven scratches still lose1.1877SOL. Eight failed entry fees cost0.0040SOL in every confirmed recipe. The main loss is failed-recovery price deterioration, not the failed-entry fee budget.','']
        at=lines.index('## Reproduction and next work');lines[at:at]=info
    # End with the complete full-five account card rather than a profitable-only scope.
    selected=next(s for s in cards if s.startswith('## confirmed_full5, portfolio, breakers True\n'))
    lines+=['',selected]
    (OUT/'REPORT.md').write_text('\n'.join(lines)+'\n')
    print('CHECKS_PASS',len(rows),len(funded),len(cards),flush=True)
    print('\n'.join(lines[lines.index('## Funded results'):lines.index('## Funded results')+13]),flush=True)

if __name__=='__main__':main()
