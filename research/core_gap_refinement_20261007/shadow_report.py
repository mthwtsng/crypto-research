"""Report causal feedback experiments without calling reduced exposure an edge."""
import collections,gzip,json,hashlib,pathlib
import shadow_feedback as S
P,OUT=S.P,S.OUT

def main():
    rows=S.inputs();funded=json.loads((OUT/'FUNDED.json').read_text());audit=json.load(gzip.open(OUT/'DECISIONS.json.gz','rt'))
    groups=collections.defaultdict(list)
    for r in rows:groups[(r['recipe'],r['scenario'],r['fee'])].append(r)
    prefix_checks=0;ledger_checks=0
    for a in audit:
        rr=groups[(a['recipe'],a['scenario'],a['fee'])];d=S.decisions(rr,a['policy']);assert json.loads(json.dumps(d))==a['decisions']
        cuts=sorted({tuple(r['signal_position']) for r in rr})
        for cutoff in cuts[::20]+cuts[-1:]:
            prefix=[r for r in rr if tuple(r['signal_position'])<=cutoff]
            actual=S.decisions(prefix,a['policy']);expected=[x for x in d if tuple(x['signal_position'])<=cutoff];assert actual==expected;prefix_checks+=1
        allowed={tuple(x['key']) for x in d if x['allowed']};selected=[r for r in rr if S.key(r) in allowed]
        for r in [r for r in funded if (r['recipe'],r['scenario'],r['fee'],r['policy'])==(a['recipe'],a['scenario'],a['fee'],a['policy'])]:
            f=S.V.F.funded(selected,r['breakers'],r['scope']);assert all(r[k]==f[k] for k in f);ledger_checks+=1
    timers=[r['mint'] for r in rows for l in r['legs'] if l.get('timer_target') is not None and l['time']<l['timer_target']]
    completed=[r['mint'] for r in rows for l in r['legs'] if l['venue']=='curve' and l['state_before']['rtokens_raw']==0]
    extremes=[r['recipe'] for r in funded if r['closed']>50 and ((r['profit_factor'] or 0)>3 or (r['win_rate'] or 0)>.7)]
    exhaustive=[dict(recipe=r['recipe'],policy=r['policy'],scope=r['scope'],scenario=r['scenario']) for r in funded if r['attempts']>50 and r['attempts']==r['closed']]
    assert not any([timers,completed,extremes]);assert all(r['scenario']=='fast' for r in exhaustive)
    sourcechecks=json.loads((P/'CHECKS.json').read_text())['alarms'];cyclechecks=json.loads((P/'demand_and_bounce_cycle/CHECKS.json').read_text())['alarms']
    assert all(a.get('pass_all',True) for a in sourcechecks.values());assert all(a.get('pass_all',True) for a in cyclechecks.values())
    checks=dict(prefix_checks=prefix_checks,identical_ledger_regenerations=ledger_checks,no_future_outcomes=True,alarms=dict(speed_order='Inherited exact intent traces; funded gate/cooldown selection varies with placement. Source matched-intent decompositions in predecessor CHECKS.json.',delayed_guards=sum(r['status']=='failed' for r in rows if r['scenario']=='slow'),timer_violations=timers,all_closed_cases=exhaustive,threshold_fill_check='Inherited integer-delivered curve/AMM requotes; full targets checked in predecessor, no new exit thresholds.',completed_curve_sales=completed,high_PF_or_WR=extremes,creation_history='All1800creation-selected coins and eligible mints unchanged; predecessor source/account parity.'),hashes={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in [pathlib.Path(S.__file__),pathlib.Path(__file__),OUT/'SPEC.json',OUT/'FUNDED.json',OUT/'DECISIONS.json.gz']})
    (OUT/'CHECKS.json').write_text(json.dumps(checks,indent=2)+'\n')
    def pick(recipe,policy,scope='portfolio_without_carryover',br=False,sc='central85',fee=1505000):return next(r for r in funded if r['recipe']==recipe and r['policy']==policy and r['scope']==scope and r['breakers']==br and r['scenario']==sc and r['fee']==fee)
    cards=[]
    for recipe in ['baseline','confirmed_scratch3']:
        for policy in ['baseline','warmup10','positive10']:
            for scope in ['portfolio','portfolio_without_carryover']+S.V.F.RULES:
                for br in [False,True]:
                    r=pick(recipe,policy,scope,br);ss=[pick(recipe,policy,scope,br,sc) for sc in ['fast','central80','central85','slow']]
                    verdict='undetermined' if r['unresolved'] or r['attempts']==0 else 'negative-central' if r['net_zero_SOL']<0 else 'positive-central' if ss[0]['net_zero_SOL']>0 else 'undetermined'
                    card=f'''engine + revision: repaired approved day_general extensions; git35d8981; working code/data hashes CHECKS.json
data: October3–6UTC,2026;1800creation-selected launches,600earlier+1200later; sampled opportunity stream, not complete live activity
frozen before data: no; retrospective development after inspecting these periods
looks:26prior logged development looks +2feedback policies; baseline and confirmed3s recipes fixed, no gate threshold tuning
candidate: {recipe}/{policy}/{scope};breakers{br};15SOL/0.50SOL/max2;0.25SOL cooldown probes
fast/central80/central85/slow zeroSOL: {' / '.join(f"{x['net_zero_SOL']:+.6f}" for x in ss)}
markedSOL same order: {' / '.join(f"{x['net_marked_SOL']:+.6f}" for x in ss)}
stress tail {pick(recipe,policy,scope,br,'stress')['net_zero_SOL']:+.6f}; historical0.002916legfee {pick(recipe,policy,scope,br,fee=2916000)['net_zero_SOL']:+.6f};scheduled n/a(all urgent)
central85 attempts/closed/failed/unresolved:{r['attempts']}/{r['closed']}/{r['failed']}/{r['unresolved']};zero{r['net_zero_SOL']:+.6f};marked{r['net_marked_SOL']:+.6f};closed-only{r['closed_net_SOL']:+.6f}
settled drawdown{r['max_settled_drawdown_SOL']:.6f};cash drawdown{r['max_cash_drawdown_SOL']:.6f};largestwinner{r['largest_winner_SOL']:.6f};netwithoutlargest{r['net_without_largest_SOL']:+.6f}
opportunities{r['opportunities']};gate rejection{json.dumps(r['gate_rejections'])};funding skips{json.dumps(r['skipped'])};daily{json.dumps(r['daily_net_SOL'])}
PF{r['profit_factor']};WR{r['win_rate']};eightalarms reviewed;causalprefix/ledger checks CHECKS.json
verdict:{verdict},retrospective
changesverdict:entry information beyond recent strategy PnL, complete opportunity stream and frozen14–21-day evaluation; authenticate migration execution before S5 claims
'''
                    cards.append(f'## {recipe}, {policy}, {scope}, breakers {br}\n\n```text\n{card}```\n')
    (OUT/'CANDIDATE_RESULT_CARDS.md').write_text('# Feedback result cards\n\n'+'\n'.join(cards))
    lines=['# Causal shadow-feedback experiment','','**The positive-last-ten feedback gate remains negative-central, retrospective.** It reduces exposure and losses compared with the matching warmup control but does not repair expected value. Both recipes and all three policies are retained.','','## Central funded results','','| Recipe / admission policy | Central80 SOL | Central85 SOL | Attempts / closed / failed / unresolved |','|---|---:|---:|---|']
    for recipe in ['baseline','confirmed_scratch3']:
        for policy in ['baseline','warmup10','positive10']:
            a=pick(recipe,policy,sc='central80');r=pick(recipe,policy)
            lines.append(f"| {recipe} / {policy} | {a['net_zero_SOL']:+.4f} | {r['net_zero_SOL']:+.4f} | {r['attempts']}/{r['closed']}/{r['failed']}/{r['unresolved']} |")
    lines+=['','Table is the separate four-strategy diagnostic, breakers off, shared continuous15SOL/max2 account across all four dates. Individual strategy accounts are not summed. Full five, breakers on/off, placement brackets and cost stress are in the cards. Ungated full five remains blocked by two unsold migration paths; zero−0.9379SOL/mark+0.2655SOL. Gated full-five accounts have no carryover admissions because S5 never obtains ten resolved shadows; their equality to four-strategy accounts is not evidence of profitable migration carryover.','','## Causal policy and control','','Maintain the last ten resolved0.50SOL independently replayed shadow attempts for each strategy. The warmup control admits once ten outcomes are known. The positive gate additionally requires their all-cost net sum>0. Failures contribute their actual−0.000505SOL fee; unsent actual orders pay nothing. Unresolved shadows remain unknown, not zero or profitable. Shadow computation continues while actual admissions pause. Strategy/deployer gates were not added because this cohort is too sparse for a reliable ten-outcome history per deployer.','','Only closes/failures strictly before each signal’s canonical position can enter feedback. Outcomes are not available at entry, and partial proceeds are not treated as resolved attempts. Three targeted regressions cover future closes, unresolved warmup, failed fees and recovery while paused. Production settings remain unchanged.','','## What the result means','','Recent strategy profitability is not enough to select profitable next trades in this sample. Original recipe gate loses1.9094SOL versus warmup4.2228SOL; confirmed3-second recipe gate loses1.4190SOL versus warmup2.5658SOL. Much of the difference comes from admitting only63/57trades instead of190/168, respectively. Even reduced exposure stays negative.','','ATH is a counterexample: standalone ungated−0.1705SOL, warmup−0.2975SOL, positive gate−0.5183SOL. The gate drops opportunities that later recover and selects some losses after a previously good patch. Survival shelf improves its loss to−0.4598SOL but only seven attempts pass. Confirmed dead-man improves almost nothing after warmup:−0.2700SOL versus gated−0.2638SOL, while attempts fall from26to8. These small samples do not support treating feedback as an alpha signal.','','## Scope and checks','','Data are the existing1800fixed creation-selected launches across October3–6, not a full market census or14–21-day confirmation. Combining their traces creates one chronological account, not a sum of reset balances.5832input trace repetitions and504alternative funded ledgers; no new entry/exit fill recipes. Sampling may omit real strategy opportunities and change the live feedback history. Shadow own-impact trajectories are modeled, not observable live wallet PnL.','',f'{prefix_checks}decision-prefix checks pass;504funded ledgers regenerate identically. Historical whole-transaction/source-custody proofs, integer causal requotes and eight alarm checks are retained; new decision-history checks prohibit future outcomes. Fast all-closed cases are explained by K=0 entry placement; delayed cases have failed guards.','','## Next falsification test','','Investigate entry information describing failed recovery versus sustained new demand: sequential outside recovery transactions and residual sellable inventory, rather than optimizing the rolling window until it happens to win. Earlier3-second invalidation is a loss-reduction candidate, not a profitable strategy. Completion/migration execution remains independently incomplete.','','## What I would investigate if data and tooling were unconstrained','','Complete live shadow-intent stream for feedback calibration; archival funding/cohort inventory to distinguish coordinated sell supply; full failed-router simulation with original account/compute limits.','','## Required result card','']
    lines.append(next(c for c in cards if c.startswith('## confirmed_scratch3, positive10, portfolio, breakers False\n')))
    (OUT/'REPORT.md').write_text('\n'.join(lines)+'\n');print('REPORT_DONE',prefix_checks,ledger_checks,len(cards),flush=True)

if __name__=='__main__':main()
