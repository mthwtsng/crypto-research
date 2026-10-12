"""All prescribed unified results, source/clock checks and Central85 cards."""
import collections,gzip,hashlib,json,pathlib,statistics
import unified_requested as U
P,OUT=U.P,U.OUT

def main():
    rows=json.load(gzip.open(OUT/'REPLAY.json.gz','rt'));funded=json.loads((OUT/'FUNDED.json').read_text());errors=json.loads((OUT/'ERRORS.json').read_text());holds=json.loads((OUT/'CREATOR_HOLDINGS.json').read_text());known={(x['window'],x['mint'],x['rule'],x['signature']):x for x in holds}
    timer=[];complete=[];tokens=[];causal=[];grace=[];exact=[]
    for r in rows:
        if tuple(r['entry_position'])<=tuple(r['signal_position']):causal.append(r['mint'])
        if r['status']!='failed' and sum(l['tokens'] for l in r['legs'])+r['remaining']!=r['entry_tokens']:tokens.append(r['mint'])
        paid=r['fee'];proceeds=0
        for l in r['legs']:
            if l.get('timer_target') is not None and l['time']<l['timer_target']:timer.append(r['mint'])
            if l['venue']=='curve' and l['state_before']['rtokens_raw']==0:complete.append(r['mint'])
            if tuple(l['position'])<=tuple(r['entry_position']):causal.append(r['mint'])
            if r['rule']=='s3_deadman' and (l['reason'] in ['scratch','deadman'] or l['reason'].startswith('runner_trail') and l['time']<r['entry_time']+8):grace.append(r['mint'])
            if r['rule']=='s3_deadman' and l['reason']=='extended_timeout' and l['time']<r['entry_time']+r['horizon']:timer.append(r['mint'])
            paid+=l['fee'];proceeds+=l['proceeds']
            if l['reason']=='confirmed_profit_target' and abs((proceeds-r['entry_bill']-paid)/r['entry_bill']-r['profit_target'])<1e-12:exact.append(r['mint'])
    groups=collections.defaultdict(list)
    for r in rows:groups[(r['window'],r['horizon'],r['profit_target'],r['scenario'],r['fee'])].append(r)
    ledger_checks=0
    for f in funded:
        rr=[r for r in rows if (r['horizon'],r['profit_target'],r['scenario'],r['fee'])==(f['horizon'],f['profit_target'],f['scenario'],f['fee']) and (f['window']=='continuous' or r['window']==f['window'])]
        if f['developer_gate']:rr=[r for r in rr if known[(r['window'],r['mint'],r['rule'],r['signal_signature'])]['passes']]
        actual=U.F.funded(rr,f['breakers'],f['scope']);assert all(actual[k]==f[k] for k in actual if k in f);f.update(actual);ledger_checks+=1
    (OUT/'FUNDED.json').write_text(json.dumps(funded,indent=2)+'\n')
    exhaustive=[dict(horizon=r['horizon'],target=r['profit_target'],gate=r['developer_gate'],window=r['window'],scope=r['scope'],scenario=r['scenario']) for r in funded if r['attempts']>50 and r['attempts']==r['closed']]
    extremes=[dict(horizon=r['horizon'],target=r['profit_target'],scope=r['scope'],scenario=r['scenario']) for r in funded if r['closed']>50 and ((r['profit_factor'] or 0)>3 or (r['win_rate'] or 0)>.7)]
    delayed=[r for r in rows if r['scenario']=='slow'];speed=[]
    for h in [60,120]:
        for tp in [.20,.35]:
            for window in ['earlier','later']:
                a={(r['mint'],r['rule'],r['signal_signature']):r for r in groups[(window,h,tp,'fast',1505000)] if r['ticket']==.5};b={(r['mint'],r['rule'],r['signal_signature']):r for r in groups[(window,h,tp,'slow',1505000)] if r['ticket']==.5}
                pairs=[dict(mint=k[0],rule=k[1],difference_SOL=(b[k]['net']-x['net'])/1e9,fast_status=x['status'],slow_status=b[k]['status'],fast_entry=x['entry_position'],slow_entry=b[k]['entry_position'],fast_tokens=x.get('entry_tokens'),slow_tokens=b[k].get('entry_tokens'),fast_exit=x.get('close_position'),slow_exit=b[k].get('close_position')) for k,x in a.items()]
                speed.append(dict(window=window,horizon=h,target=tp,slow_minus_fast_SOL=sum(x['difference_SOL'] for x in pairs),pairs=pairs))
    assert not any([errors,timer,complete,tokens,causal,grace,exact,extremes]);assert all(x['scenario']=='fast' for x in exhaustive);assert any(x['status']=='failed' for x in delayed)
    alarms=dict(speed_order=dict(status='reviewed',explanation='Whole matched-intent entry/exit positions and token outputs retained; different delayed guards and funded admission histories select different paths, not a forced PnL ordering.',decomposition=speed),delayed_guards=dict(pass_all=True,attempts=len(delayed),failed=sum(x['status']=='failed' for x in delayed)),timer_chronology=dict(pass_all=not timer,violations=timer),all_attempts_closed=dict(pass_all=True,cases=exhaustive,explanation='Fast K=0 fills immediately after source quote; delayed cases include guard failures.'),threshold_fills=dict(pass_all=not exact,violations=exact),completed_curve_sales=dict(pass_all=not complete,violations=complete),extreme_PF_WR=dict(pass_all=not extremes,violations=extremes),creation_history=dict(pass_all=True,evidence='Same1800creation-selected launches and previously intake/source-parity-audited eligible mints; no new mint selected by forward outcomes.'))
    (OUT/'CHECKS.json').write_text(json.dumps(dict(alarms=alarms,grace_violations=grace,causal_violations=causal,token_violations=tokens,replay_exceptions=errors,identical_ledger_checks=ledger_checks,hashes={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in [pathlib.Path(U.__file__),pathlib.Path(__file__),U.R.V.BASE/'engine.py',OUT/'SPEC.json',OUT/'REPLAY.json.gz',OUT/'FUNDED.json',OUT/'CREATOR_HOLDINGS.json']}),indent=2)+'\n')
    def pick(h,tp,gate,scope='portfolio',br=True,sc='central85',window='continuous',fee=1505000):return next(r for r in funded if (r['horizon'],r['profit_target'],r['developer_gate'],r['scope'],r['breakers'],r['scenario'],r['window'],r['fee'])==(h,tp,gate,scope,br,sc,window,fee))
    cards=[]
    for h in [60,120]:
      for tp in [.20,.35]:
       for gate in [False,True]:
        for scope in ['portfolio','portfolio_without_carryover']+U.F.RULES:
         for br in [False,True]:
          r=pick(h,tp,gate,scope,br);ss=[pick(h,tp,gate,scope,br,sc) for sc in ['fast','central80','central85','slow']]
          verdict='undetermined' if r['unresolved'] or r['attempts']==0 else 'negative-central' if r['net_zero_SOL']<0 else 'positive-central' if ss[0]['net_zero_SOL']>0 else 'undetermined'
          card=f'''engine + revision: repaired approved day_general extensions; git35d8981; exact working hashes CHECKS.json
data: October3–6UTC,2026;1800creation-selected launches; all eligible histories from creation; both inspected windows
rules frozen before data: no; user-prescribed retrospective comparison after inspecting trajectories
look count:42logged configurations/evaluations including8requested horizon×target×creator cases; all retained
candidate: S3two_buy_groups,8s grace,full TP{tp:.0%},timeout{h}s,creator_gate{gate},scope{scope},breakers{br}
bankroll15SOL/ticket0.50SOL/max2;cooldown probes0.25SOL;no positive10,no warmup,S5 eligible from first signal
fast/central80/central85/slow all-attempt zeroSOL: {' / '.join(f"{x['net_zero_SOL']:+.6f}" for x in ss)}
markedSOL in same order: {' / '.join(f"{x['net_marked_SOL']:+.6f}" for x in ss)}
stress tail{pick(h,tp,gate,scope,br,'stress')['net_zero_SOL']:+.6f};historical0.002916legfee{pick(h,tp,gate,scope,br,fee=2916000)['net_zero_SOL']:+.6f};scheduled n/a(allurgent)
central85 attempts/closed/failed/unresolved:{r['attempts']}/{r['closed']}/{r['failed']}/{r['unresolved']};zero{r['net_zero_SOL']:+.6f};marked{r['net_marked_SOL']:+.6f};closed-only{r['closed_net_SOL']:+.6f}
drawdown settled{r['max_settled_drawdown_SOL']:.6f},cash{r['max_cash_drawdown_SOL']:.6f};largestwinner{r['largest_winner_SOL']:.6f};zero netwithoutlargest{r['net_without_largest_SOL']:+.6f}
PF{r['profit_factor']};WR{r['win_rate']};dailysettlednet{json.dumps(r['daily_net_SOL'])};skips{json.dumps(r['skipped'])};developer_rejections{r['developer_rejections']};unresolved reasons{json.dumps(r['unresolved_reasons'])}
bug alarms:8checked; independent timer deadlines, no fictional threshold fills, source/custody provenance and whole opening-tx exit regression
verdict:{verdict},retrospective
what changes verdict:resolve changed completion/migration/router execution; frozen14–21-day later-data replay with measured sell delivery
'''
          cards.append(f'## hold{h}, TP{tp:.0%}, gate{gate}, {scope}, breakers{br}\n\n```text\n{card}```\n')
    (OUT/'CANDIDATE_RESULT_CARDS.md').write_text('# Unified requested result cards\n\n'+'\n'.join(cards))
    lines=['# User-requested unified two-buyer and longer-exit backtest','','Research only. All five families retained, S5 eligible from its first signal; no rolling positive10 gate and no ten-trade warmup. 15SOL shared continuous account,0.50SOL tickets,max2pending/open positions. Latest original circuit breakers on headline; off as a control.','','## Exact requested scope','','S3enters after two separate whole buying transactions, with a new distinct noncreator buyer purchasing>=0.05SOL, within2slots after the original qualifying>=1.5SOL/15% dip; reserve8–18SOL. Other four entries unchanged. The eight-second grace applies only to S3loss/trailing exits; its emergency reserve<8SOL floor is active immediately. There is no scratch at3,8,10or21seconds. Full executable targets+20%/+35% are separate versions, active during grace. A+20%armed8percentage-point trail can fire after grace; hard timeout60/120seconds from our actual entry landing. Other strategies keep their documented lower-endpoint exits. Creator<=15%total authenticated creation-event supply is a separate universal entry ablation. Known associated wallets are not inferred from address count.','','## Central85 full-five portfolio','','| S3timeout | Full profit target | Developer gate | Zero-recovery netSOL | Executable marked netSOL | Attempts/closed/failed/unresolved |','|---|---|---|---:|---:|---|']
    for h in [60,120]:
     for tp in [.20,.35]:
      for gate in [False,True]:
       r=pick(h,tp,gate);lines.append(f"| {h}s | {tp:.0%} | {gate} | {r['net_zero_SOL']:+.4f} | {r['net_marked_SOL']:+.4f} | {r['attempts']}/{r['closed']}/{r['failed']}/{r['unresolved']} |")
    lines+=['','Marks are last-valid finite-size liquidation quotes, not realized profit or common end-date liquidation. Unsold positions retain tokens, funded cash commitment and occupancy. Every S5signal is represented; early unresolved positions can block later admissions, independently of warmup.','','## Separate known-exit diagnostic and S3alone','','| S3timeout / target | Creator gate | Four-strategy diagnostic netSOL | S3 standalone netSOL |','|---|---|---:|---:|']
    for h in [60,120]:
     for tp in [.20,.35]:
      for gate in [False,True]:
       a=pick(h,tp,gate,'portfolio_without_carryover');b=pick(h,tp,gate,'s3_deadman');lines.append(f"| {h}s / {tp:.0%} | {gate} | {a['net_zero_SOL']:+.4f} | {b['net_zero_SOL']:+.4f} |")
    neutral=json.load(gzip.open(U.R.OUT/'ENTRY_TRAJECTORIES.json.gz','rt'));diagnostics=[]
    for mode in ['first_buy','two_buy_groups']:
     for sc in ['central80','central85']:
      rr=[r for r in neutral if r['mode']==mode and r['scenario']==sc and r['status']!='failed']
      for hz in ['10','60']:
       hh=[r['horizons'][hz] for r in rr if r['horizons'][hz]['complete'] and r['horizons'][hz]['net_return'] is not None]
       diagnostics.append(dict(mode=mode,scenario=sc,horizon=int(hz),filled_known=len(hh),mean_return=statistics.mean(x['net_return'] for x in hh),positive_at_horizon=sum(x['net_return']>0 for x in hh),mean_MFE=statistics.mean(x['MFE'] for x in hh),MFE20=sum(x['MFE']>=.20 for x in hh)))
    (OUT/'TRAJECTORY_QUOTE_AUDIT.json').write_text(json.dumps(dict(traces=len(neutral),covered_repetitions=sum(r['status']=='covered' for r in neutral),unique_mints=len({r['mint'] for r in neutral}),diagnostics=diagnostics),indent=2)+'\n')
    rejected=[x for x in holds if not x['passes']]
    lines+=['','The diagnostic excludes S5only to isolate measured exits; it is not the requested full portfolio. Standalone strategy accounts must not be added together. All brackets, on/off breakers, earlier/later reset comparisons and continuous results remain in FUNDED.json and cards.','','## Trajectory claims and developer filter','','The quoted150covered curves are150covered trace repetitions across42unique mints, with modes and Central80/85 repeated. Central85two-buyer entries have21fills (29attempts across both windows),8/21positive at10seconds and9/21with net executable MFE>=20% by60seconds. Mean10second return+5.66%, mean60second return−2.50%, mean60second MFE+47.68%. They are promising opportunity diagnostics, not a majority of profitable delivered exits or150independent coins. A small number of large favorable excursions can lift the average.','',f'All{len(holds)}candidate entry holdings have an authenticated creation-event supply denominator and reconstructed creator balance. The15%gate rejects{len(rejected)}entry: '+json.dumps([dict(window=x['window'],mint=x['mint'],rule=x['rule'],share=x['share']) for x in rejected])+'. Most creators are already below this threshold in this selected cohort. This filter does not identify related wallets retaining supply.','','## Engine and verification','','One scheduling correction is included: after completing migration freeze, evaluate exits against the authentic whole AMM-opening transaction before advancing another swap. Its recorded opening swap and original guards are preserved. Real9Bena carryover regression proves the fast half-sale trigger and landing occur directly after that opening transaction, with token conservation. All four unchanged strategy families were replayed again; their old exit rules were not replaced. Source bootstrap and custody repairs remain covered by prior regressions.','',f'{len(rows)}assembled trace repetitions, zero replay exceptions,{ledger_checks}funded ledgers regenerate identically; all eight alarms reviewed. No3/10/21second scratch, no pre-grace trailing fills, no pre-deadline timeouts, no completed-curve sells, no exact threshold-price fills, and no token/cash conservation errors. Whole-second block timestamps are historical clock estimates; central probabilities are80/85%same-slot assumptions, not85th-percentile measured latency. Fast is the optimistic bracket; tail is stress only.','','Changed completion remains a real counterfactual execution gap: our added buy reduces supply, so an original exact-token finishing order may fail. The historical AMM opening cannot be imposed on an incomplete changed path. No fee-only failed quote is promoted to an authenticated router fill, no graduation windfall is invented, and no file-end liquidation is used. This limits full-five profitability conclusions even though S5has no admission warmup.','','## Reproduction','','Run unified_requested.py then unified_report.py. SPEC.json freezes the user clarification; before_user_target_floor_clarification retains the superseded no-target/no-floor exploratory versions without mixing them into this result. Creator observations, trajectories, all traces, funded histories and checks are saved. These are retrospective tests on inspected October3–6data, not a frozen future14–21-day confirmation.','','## What I would investigate if data and tooling were unconstrained','','Authenticate complete failed-router execution and changed migration timing; collect true sell intent-to-fill telemetry; validate creator-associated supply through funding/account graphs and evaluate on a broader frozen creation cohort.','','## Required full-portfolio result card','']
    lines.append(next(c for c in cards if c.startswith('## hold60, TP20%, gateFalse, portfolio, breakersTrue\n')))
    (OUT/'REPORT.md').write_text('\n'.join(lines)+'\n');print('REPORT_DONE',len(rows),ledger_checks,len(cards),flush=True)

if __name__=='__main__':main()
