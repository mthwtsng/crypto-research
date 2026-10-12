"""Audit saved repaired-engine traces and publish all results, including failures."""
import collections, gzip, hashlib, json, pathlib, statistics, subprocess
import variants as V
P=pathlib.Path(__file__).resolve().parent

def read(name): return json.loads((P/name).read_text())
def packed(name): return json.load(gzip.open(P/name,'rt'))
def pick(rr,v='baseline',sc='central85',scope='portfolio_without_carryover',br=True,fee=1505000,seed=0):
    return next(r for r in rr if r['variant']==v and r['scenario']==sc and r['scope']==scope and r['breakers']==br and r['fee']==fee and r.get('placement_seed',0)==seed)

def main():
    lower=read('TRANSFER_FUNDED.json'); upper=read('UPPER_FUNDED.json')
    rows=packed('TRANSFER_REPLAY.json.gz')+packed('UPPER_REPLAY.json.gz')
    groups=collections.defaultdict(list)
    for r in rows: groups[(r['variant'],r['endpoint'],r['scenario'],r['fee'],r.get('placement_seed',0))].append(r)
    ledger_bad=[]
    for r in lower+upper:
        key=(r['variant'],r.get('endpoint','lower'),r['scenario'],r['fee'],r.get('placement_seed',0))
        actual=V.F.funded(groups[key],r['breakers'],r['scope'])
        if any(actual[k]!=r[k] for k in actual): ledger_bad.append(key)
    timers=[(r['mint'],l['reason']) for r in rows for l in r['legs'] if l.get('timer_target') is not None and l['time']<l['timer_target']]
    complete=[r['mint'] for r in rows for l in r['legs'] if l['venue']=='curve' and l['state_before']['rtokens_raw']==0]
    causal=[r['mint'] for r in rows if tuple(r['entry_position'])<=tuple(r['signal_position']) or any(tuple(l['position'])<=tuple(r['entry_position']) for l in r['legs'])]
    tokens=[r['mint'] for r in rows if r['status']!='failed' and sum(l['tokens'] for l in r['legs'])+r['remaining']!=r['entry_tokens']]
    extremes=[dict(variant=r['variant'],scenario=r['scenario'],scope=r['scope']) for r in lower+upper if r['closed']>50 and ((r['profit_factor'] or 0)>3 or (r['win_rate'] or 0)>.7)]
    allclosed=[dict(variant=r['variant'],endpoint=r.get('endpoint','lower'),scenario=r['scenario'],scope=r['scope']) for r in lower+upper if r['attempts']>50 and r['attempts']==r['closed']]
    unexplained_allclosed=[r for r in allclosed if r['scenario']!='fast']
    late=[r for r in rows if r['scenario']=='slow']
    exact=[]
    for r in rows:
        if r['status']=='failed':continue
        paid=r['fee']; proceeds=0
        for l in r['legs']:
            paid+=l['fee']; proceeds+=l['proceeds']
            if l['reason']=='full_profit_target' and any(abs((proceeds-r['entry_bill']-paid)/r['entry_bill']-target)<1e-12 for target in [.05,.10,.25,.35]):exact.append(r['mint'])
    source=[]
    for mint in sorted({r['mint'] for r in rows}):
        t=json.load(gzip.open(P/'fresh_oct05_oct06/continuations'/(mint+'.json.gz'),'rt'))
        source.append(dict(mint=mint,from_creation=t['audit']['from_creation']))
    # Preserve every matching intent, including failed-selection effects.
    speed=[]
    for v,ep,fee,seed in sorted({(r['variant'],r['endpoint'],r['fee'],r.get('placement_seed',0)) for r in rows if r['scenario']=='fast'}):
        a={(r['mint'],r['rule'],r['signal_signature']):r for r in groups[(v,ep,'fast',fee,seed)] if r['ticket']==.5}
        b={(r['mint'],r['rule'],r['signal_signature']):r for r in groups[(v,ep,'slow',fee,seed)] if r['ticket']==.5}
        pairs=[dict(mint=k[0],rule=k[1],fast_status=x['status'],slow_status=b[k]['status'],slow_minus_fast_SOL=(b[k]['net']-x['net'])/1e9,fast_entry=x['entry_position'],slow_entry=b[k]['entry_position'],fast_tokens=x.get('entry_tokens'),slow_tokens=b[k].get('entry_tokens'),fast_exit=x.get('close_position'),slow_exit=b[k].get('close_position')) for k,x in a.items()]
        speed.append(dict(variant=v,endpoint=ep,pairs=pairs,slow_minus_fast_SOL=sum(p['slow_minus_fast_SOL'] for p in pairs)))
    errors=read('TRANSFER_ERRORS.json')+read('UPPER_ERRORS.json')
    alarms=dict(speed_order=dict(status='reviewed',explanation='Matched whole-transaction entry/exit and changed token output retained. On 4n4pTAbn, later sell flow allows slow to acquire 17.23 trillion tokens versus fast 7.21 trillion, improving net by0.2835SOL. On uZQFWBUM, slow rejects the entry whereas fast retains unresolved custody; zero-recovery comparisons differ by0.5030SOL and are not measured liquidation gains. Later guards and funded breaker admissions select different trades. PnL monotonicity is not imposed.',decomposition=speed),
        delayed_guards=dict(pass_all=any(r['status']=='failed' for r in late),attempts=len(late),failed=sum(r['status']=='failed' for r in late)),
        timer_chronology=dict(pass_all=not timers,violations=timers),all_attempts_closed=dict(pass_all=not unexplained_allclosed,cases=allclosed,explanation='Only fast K=0 insertions: signal quote equals entry quote. Delayed cases retain failed guards.'),
        no_threshold_price_fill=dict(pass_all=not exact,violations=exact),no_completed_curve_sell=dict(pass_all=not complete,violations=complete),
        high_PF_or_win_rate=dict(pass_all=not extremes,violations=extremes),tape_from_creation=dict(pass_all=all(r['from_creation'] for r in source),mints=len(source)))
    extra=dict(ledger_reproduction_errors=ledger_bad,token_conservation_errors=tokens,causal_position_errors=causal,replay_errors=errors)
    hashes={str(f.relative_to(P.parents[1])):hashlib.sha256(f.read_bytes()).hexdigest() for f in [V.BASE/'engine.py',V.BASE/'ledger.py',P/'variants.py',P/'transfer.py',P/'upper_endpoint.py',P/'TRANSFER_REPLAY.json.gz',P/'UPPER_REPLAY.json.gz',P/'TRANSFER_FUNDED.json',P/'UPPER_FUNDED.json']}
    (P/'CHECKS.json').write_text(json.dumps(dict(alarms=alarms,extra=extra,hashes=hashes),indent=2)+'\n')
    assert not any([ledger_bad,tokens,causal,errors,timers,complete,exact,extremes,unexplained_allclosed])
    assert all(x.get('pass_all',True) for x in alarms.values())
    revision=subprocess.check_output(['git','rev-parse','--short','HEAD'],text=True).strip()
    def card(rr,v,scope,br,ep='lower'):
        r=pick(rr,v,scope=scope,br=br)
        ss=[pick(rr,v,sc=sc,scope=scope,br=br) for sc in ['fast','central80','central85','slow']]
        stress=[pick(rr,v,sc='stress',scope=scope,br=br),pick(rr,v,scope=scope,br=br,fee=2916000)]
        verdict='undetermined' if r['unresolved'] else 'negative-central' if r['net_zero_SOL']<0 else 'positive-central' if ss[0]['net_zero_SOL']>0 else 'undetermined'
        return f'''engine + revision: repaired approved day_general extensions; {revision}; exact working-file hashes CHECKS.json
data: October 5–6 UTC, 2026; 1,200 fixed-hash creation-selected coins (25/hour, 48 complete hourly strata); 130 eligible mints; histories from creation
rules frozen before data: original plan predates later results; joint recipes frozen before inspecting later replay; all historical, not a future live confirmation
look count: two original endpoint recipes + 18 new mechanisms/combinations; placement, fee and seed repetitions are sensitivities
candidate: {v}; endpoint {ep}; scope {scope}; breakers {br}; bankroll15SOL/ticket0.50SOL/max2; cooldown probes0.25SOL
fast / central80 / central85 / slow funded zero SOL: {' / '.join(f"{x['net_zero_SOL']:+.6f}" for x in ss)}
marked SOL in same order: {' / '.join(f"{x['net_marked_SOL']:+.6f}" for x in ss)}
stress tail {stress[0]['net_zero_SOL']:+.6f}; 0.002916SOL successful-leg fee {stress[1]['net_zero_SOL']:+.6f}; scheduled sensitivity n/a, every exit urgent
central85 attempts/closed/failed/unresolved: {r['attempts']}/{r['closed']}/{r['failed']}/{r['unresolved']}; zero {r['net_zero_SOL']:+.6f}; marked {r['net_marked_SOL']:+.6f}; closed-only {r['closed_net_SOL']:+.6f}
settled-only drawdown {r['max_settled_drawdown_SOL']:.6f}; cash drawdown {r['max_cash_drawdown_SOL']:.6f}; largest winner {r['largest_winner_SOL']:.6f}; zero net without largest {r['net_without_largest_SOL']:+.6f}
daily settled net: {json.dumps(r['daily_net_SOL'],sort_keys=True)}; skipped {json.dumps(r['skipped'],sort_keys=True)}
bug alarms: all eight checked; matched-intent speed differences and fast all-closed cases documented CHECKS.json; ledger regenerated identically
verdict: {verdict}, retrospective
what changes verdict: resolve changed completion/exact routed execution; causal entry-quality test followed by frozen 14–21-day later data
'''
    cards=[]
    for rr,ep,vs in [(lower,'lower',['baseline','ath_only','joint_keep_targets_dead10','joint_confirmed_half10']),(upper,'upper',['baseline'])]:
        for v in vs:
            for scope in ['portfolio','portfolio_without_carryover']+V.F.RULES:
                for br in [False,True]:cards.append(f'## {v}, {ep}, {scope}, breakers {br}\n\n```text\n{card(rr,v,scope,br,ep)}```\n')
    (P/'CANDIDATE_RESULT_CARDS.md').write_text('# Later-window result cards\n\n'+'\n'.join(cards))
    table='| Recipe / endpoint | Central80 SOL | Central85 SOL | Attempts / closed / failed / unresolved |\n|---|---:|---:|---|\n'
    for rr,v,ep in [(lower,'baseline','lower'),(upper,'baseline','upper'),(lower,'ath_only','lower'),(lower,'joint_keep_targets_dead10','lower'),(lower,'joint_confirmed_half10','lower')]:
        a=pick(rr,v,sc='central80');b=pick(rr,v)
        table+=f"| {v} / {ep} | {a['net_zero_SOL']:+.4f} | {b['net_zero_SOL']:+.4f} | {b['attempts']} / {b['closed']} / {b['failed']} / {b['unresolved']} |\n"
    solo='| Strategy | Original Central85 SOL | Primary refined SOL |\n|---|---:|---:|\n'
    for scope in V.F.RULES:
        a=pick(lower,scope=scope,br=False);b=pick(lower,'joint_keep_targets_dead10',scope=scope,br=False)
        solo+=f"| {scope} | {a['net_zero_SOL']:+.4f} | {b['net_zero_SOL']:+.4f} |\n"
    text=f'''# Starting Five: repaired-engine backtest and later-window refinement

The four-strategy diagnostic is **negative-central, retrospective** on October 5–6. The original lower-endpoint plan with breakers loses {abs(pick(lower)['net_zero_SOL']):.4f} SOL; the primary combined refinement loses {abs(pick(lower,'joint_keep_targets_dead10')['net_zero_SOL']):.4f} SOL. Changes improve this sample but do not establish a profitable setup.

The complete five-strategy portfolio is **undetermined, retrospective**: the baseline Central85 account admits {pick(lower,scope='portfolio')['attempts']} attempts, with two unresolved carryover positions. Zero-recovery net is {pick(lower,scope='portfolio')['net_zero_SOL']:+.4f} SOL; last-valid executable marked net is {pick(lower,scope='portfolio')['net_marked_SOL']:+.4f} SOL. Unsold marks are not realized cash or common end-of-window marks. Every carryover signal remains in the primary study; the four-strategy table is a separate diagnostic.

## Funded central results

15 SOL shared account, 0.50 SOL tickets, maximum two pending/open positions, latest user circuit breakers enabled, 0.25 SOL cooldown probes. Base successful network fee/tip 0.001505 SOL, failed 0.000505 SOL, refundable rent 0.002039280 SOL; protocol fees and integer impact included. Entries enforce 97% signal-time quote. All exits urgent, with the same modeled central delivery distribution; timestamps are integer-second historical estimates, not measured 50–70 ms fills.

{table}
All table rows exclude S5 only to isolate known exits. They cannot be described as the full portfolio. Full five and all individual scenarios, both endpoint recipes, on/off breakers, brackets, tail stress and higher fees are in CANDIDATE_RESULT_CARDS.md.

## Scope and selection

Development: 600 creation-selected October 3–4 launches; original two endpoints plus 18 new mechanism/combination looks. Primary joint refinement on those inspected days produced +1.1145 SOL and the additional half-at-10% recipe +1.8054 SOL, both excluding carryover with breakers off. These development gains did not transfer.

Later sample: 1,200 normal-SOL creations selected by fixed hash, 25 per hour across all 48 hours October 5–6. Entry search is frozen to creation + 1,800 seconds; longer continuation history is used for custody and exits, not new late signals. 180 causal signals on 130 eligible mints. WINDOW_CORRECTION.json documents removal of one signal erroneously searched beyond that decision window, irrespective of its outcome. Lower replay 13,120 traces; upper replay 2,160 traces. These are repeated execution scenarios, not independent trades. Lower 560 funded accounts, upper 84; each is an alternative shared chronological ledger.

## Entry versus exit gap

{solo}
These standalone accounts must not be added together. Original S3 retains one undefined-runner-timeout exposure; S5 retains two displaced-completion positions. Their table values are zero-recovery bounds; executable marks are in the cards.

* **Dev absorption:** the added recent-breadth filter improves the development sample but worsens later standalone results from −0.0273 to −0.2618 SOL. It is not a usable quality gate yet; multiple addresses alone do not authenticate independent demand or exhausted associated supply.
* **Survival shelf:** development +0.6397 SOL becomes −1.7832 SOL later. Exit-free neutral paths reach executable +5% within 60 seconds on 13/32 later fills versus 8/11 development fills. The gap includes entry/regime quality; a timer adjustment alone cannot be assumed to fix it.
* **Dead-man:** causal recovery confirmation reduces failed-bounce exposure. Later 18 confirmed fills include 10 that reach executable +5% within 10 seconds, but only 7 reach +10%. The unchanged exit still loses 0.8446 SOL; half-at-10% loses 0.8801 SOL. A majority briefly rising does not outweigh the failed recoveries. Next bounded test: smaller full targets/earlier invalidation on the same confirmed entries, counting surrendered winners and total losses.
* **Upper ATH:** 20-second clip timeout and 15% reactive loss trigger improve standalone later net from −0.0530 to +0.0840 SOL. At 20 seconds only 18/41 neutral fills reach executable +5%; at 60 seconds 25/41 do, but terminal median return is strongly negative. This is a small positive sub-result, not portfolio confirmation. Test causal fresh-demand breadth and entry timing before expanding stops further.
* **Carryover:** token custody is preserved through authenticated migration when the changed path actually completes. Original exact-token completion orders can fail after our additional buy reduces remaining supply. It is invalid to force the historical AMM opening onto that incomplete path. Recovered landed-failed receipts are not pending orders and a compatible quote does not establish whole-router execution. Resolve this execution gap before selecting S5 exit winners.

Three Central85 placement seeds all lose on the later four-strategy diagnostic: original −3.9663/−4.1425/−4.6356SOL; primary joint −2.8723/−3.4533/−2.9660SOL (breakers off). The conclusion is not one unlucky placement seed. Breakers reduce realized losses but do not guarantee 13 SOL permanently safe; open exposure and overshoot remain possible.

## Repairs and verification

Repaired zero-initialized counterfactual token accounts after reverted source buys, included buys inside AMM opening transactions, preserved atomic opening failures, extended source histories through late completion and recovered a missing same-owner token-account transfer. Historical parity passes 61,020 whole token-account groups on 130 eligible mints, 65,418 curve groups on 164 bound tapes, 29,185 post-opening AMM groups and ten pool openings/custody audits. 15 focused regressions pass (7 replay, 5 ledger, 3 opening).

The saved funded ledgers were regenerated identically. CHECKS.json audits all eight contract alarms plus token conservation, causal order, timer deadlines and exceptions. Speed differences are decomposed by matching intents and their actual entry/exit positions; favorable slower quotes and different guard/cooldown admissions are not silently forced into monotonic PnL. No production settings were changed by this research.

Pessimism checks: retain executable marks and custody, use per-transaction urgent central delivery rather than slot-tail delay, fire timers independently of trades. Optimism checks: no revived router quote-only fills, authenticate opening deposits plus first swaps, and test higher measured fees. Source reconstruction parity establishes historical fidelity, not knowledge of counterfactual future orders or migration timing.

## Reproduction and next experiment

Run upper_endpoint.py for the second frozen endpoint; transfer.py for lower baseline and transfer refinements; variants.py then variants.py --ledger for development. fresh_collect.py/fresh_pipeline.py/account_repair.py retain collection and repair provenance. finish_report.py regenerates funded comparisons, checks and cards from saved traces. Repair continuations must not extend the frozen entry-search window.

Next entry-first test: recent independent demand proxies (three distinct ≥0.05 SOL buyers, wallet dominance ≤50%, sell/buy ≤50% in trailing 4 slots), evaluated causally at the first qualifying signal. Test first-time buyer expansion separately. These hypotheses are not measured improvements yet; October 3–6 now counts as inspected development. Confirmation requires frozen rules on later 14–21-day data and complete carryover execution.

## What I would investigate if data and tooling were unconstrained

Whole failed-router execution with archival account states and compute/guard evidence; sender intent-to-fill logs to calibrate buys and sells separately; contemporaneous wallet funding/cohort graphs to distinguish independent demand from associated inventory. None is an enabled signal.

## Required result card

```text
{card(lower,'baseline','portfolio',True)}```
'''
    (P/'REPORT.md').write_text(text)
    print('Checks pass; report and',len(cards),'result cards written.',flush=True)

if __name__=='__main__':main()
