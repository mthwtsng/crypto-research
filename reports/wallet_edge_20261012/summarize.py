"""Build the reviewed, compact entry-profile table from frozen study artifacts."""
import collections,csv,hashlib,json,pathlib,statistics,subprocess
P=pathlib.Path(__file__).resolve().parent;R=P.parents[1]
CLUES={
'C4J':'Momentum/near observed highs; recent size differs from longer capture.',
'97jv':'Renewed buy flow: immediately after a buy in 24/24 sampled entries.',
'nya':'Small tickets, early flow and shallow pullbacks; brief source holds.',
'85Y':'Early momentum scalp; one-second median completed hold.',
'niggerd':'KOL-following candidate: recent KOL buy within two slots in 12/24.',
'AURA':'Later-stage demand/momentum; wide actual entry reserve distribution.',
'4BHB':'Large tickets and extra custody/signers; only four prefix samples.',
'8TP':'Mature pullbacks, often after sells; frequent separate re-entries.',
'4yFA':'Creation-slot entry in 16/17; short holds and frequent partial exits.',
'8dtx':'Mature pullback followed by renewed buying; 23/24 immediately followed a buy.',
'J3g':'Pullback/sell-response scalps; frequent re-entries.',
'bcnz':'Controller funds 12 trading signers; older recovery entries and partial exits.',
'Eaa':'Pullback/sell-response scalps; frequent re-entries.',
'7ovu':'Strong wallet-following clue: named holder present in 15/15 buy receipts.',
'Buek':'KOL account references in custom program; only two successful buy prefixes.',
'5DC':'Very early momentum scalp; one-second median completed hold.',
'Fhbh':'KOL-following candidate: recent KOL buy within two slots in 12/24.',
'9Qbc':'Early sell-pressure/recovery entries; some adds and partial exits.',
'2gn':'Recovery buyers at substantial observed drawdown; variable tickets and re-entries.',
'72MU':'Sell-response pullbacks; near-constant gross one-SOL sizing.',
'haqq':'Low-reserve sell-response; observed adds and staged sales.',
'94i':'Rapid sell-response/custom execution; sparse recovered full cycles.'}
def main():
    d=json.loads((P/'entry_patterns.json').read_text())
    entries=d['entries']+d['successful_history_supplement']['entries']+d['bcnz_payer_linked_child_sample']['entries']
    anchors={a['signature']:a for a in json.loads((P/'creation_anchors.json').read_text())['anchors']}
    accounting={a['wallet']['address']:a for a in json.loads((P/'accounting.json').read_text())}
    assert len(accounting)==22
    group=json.loads((P/'bottimus_complete.json').read_text())
    by=collections.defaultdict(list)
    for e in entries:by[e['wallet']].append(e)
    rows=[]
    for w in json.loads((P/'wallets.json').read_text()):
        addr=w['address'];ee=by[addr];a=accounting[addr]
        def median(fn):return statistics.median(fn(e) for e in ee) if ee else None
        k5=sum(bool(e['pre_entry_context']['roster_pre_entry_participation']['kol_current_snapshot']['cumulative_slot_window_addresses']['5']) for e in ee)
        k2=sum(bool(e['pre_entry_context']['roster_pre_entry_participation']['kol_current_snapshot']['cumulative_slot_window_addresses']['2']) for e in ee)
        cycles=a['cycles'];holds=[c['hold_seconds'] for c in cycles]
        if addr.startswith('bcnz'):
            cycles=[c for c in group['complete_cycles'] if not c.get('tainted')]
            holds=[c['hold_seconds'] for c in cycles]
        mintcounts=collections.Counter(c['mint'] for c in cycles)
        repeated=sum(n-1 for n in mintcounts.values())
        pred=collections.Counter()
        for e in ee:
            p=e['pre_entry_context']['immediate_prior_trade_group']
            pred['buy' if p and p['net_buy_sol']>0 else 'sell' if p and p['net_buy_sol']<0 else 'none']+=1
        clue=next(v for k,v in CLUES.items() if addr.startswith(k))
        rows.append(dict(wallet=w,selected_entry_prefixes=len(ee),sample_sources=dict(collections.Counter(e['sample_source'] for e in ee)),
                         median_age_seconds=median(lambda e:anchors[e['signature']]['age_seconds']),
                         creation_slot_entries=sum(e['slot']==anchors[e['signature']]['creation_slot'] for e in ee),
                         creator_entry_count=sum(anchors[e['signature']]['creator_is_event_user'] for e in ee),
                         median_pre_real_sol=median(lambda e:e['pre_entry_context']['pre_entry_reserve_state']['real_sol']),
                         median_curve_sol_input=median(lambda e:e['entry_sol_input']),
                         median_observed_prefix_drawdown_pct=median(lambda e:e['pre_entry_context']['observed_drawdown_from_peak_pct']),
                         median_outside_net_sol_5slots=median(lambda e:e['pre_entry_context']['pre_entry_flow_by_cumulative_slot_window']['5']['net_sol']),
                         median_recent_unique_buyers=median(lambda e:e['pre_entry_context']['pre_entry_flow_by_cumulative_slot_window']['5']['unique_buyers']),
                         immediately_previous_trade_side=dict(pred),recent_kol_2slots=k2,recent_kol_5slots=k5,
                         observed_completed_cycles=len(cycles),median_observed_completed_hold_seconds=statistics.median(holds) if holds else None,
                         subsequent_completed_cycles_same_mint=repeated,subsequent_cycle_share=repeated/len(cycles) if cycles else None,
                         coverage=a.get('coverage'),clue=clue))
    cost_path=P/'execution_costs.json'
    if cost_path.exists():
        cost={w['address']:w for w in json.loads(cost_path.read_text())['wallets']}
        for r in rows:
            c=cost.get(r['wallet']['address'],{}).get('sample',{})
            r['execution_cost_sample']={k:c[k] for k in ['sample_n','observed_network_fee_plus_adjusted_residual_outflow_lamports','observed_overhead_by_trade_side'] if k in c}
    output=dict(source_cutoff=d['run']['freeze'],entry_prefixes=len(entries),wallets=len(rows),unique_entry_mints=len({e['mint'] for e in entries}),
                scope='Observed entry states and source execution profiles; exact private rules and transferable profitability undetermined. Mixed fixed-hash cohort origins retained.',rows=rows)
    (P/'ANALYSIS_SUMMARY.json').write_text(json.dumps(output,indent=2)+'\n')
    with (P/'ENTRY_PROFILES.csv').open('w') as f:
        fields=['name','address','sample_n','median_age_s','pre_real_sol','curve_input_sol','observed_drawdown_pct','outside_net_sol_5slots','completed_hold_s','KOL_2slots','clue']
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for r in rows:writer.writerow(dict(name=r['wallet']['name'],address=r['wallet']['address'],sample_n=r['selected_entry_prefixes'],median_age_s=r['median_age_seconds'],pre_real_sol=r['median_pre_real_sol'],curve_input_sol=r['median_curve_sol_input'],observed_drawdown_pct=r['median_observed_prefix_drawdown_pct'],outside_net_sol_5slots=r['median_outside_net_sol_5slots'],completed_hold_s=r['median_observed_completed_hold_seconds'],KOL_2slots=r['recent_kol_2slots'],clue=r['clue']))
    def f(v,n=1):return '—' if v is None else f'{v:.{n}f}'
    table=['| Wallet / address prefix | Buys sampled | Median age (s) | Pre-buy real SOL | Curve SOL input | Observed prefix drawdown | Prior 5-slot net SOL | Completed hold (s) | Clue |',
           '|---|---:|---:|---:|---:|---:|---:|---:|---|']
    for r in rows:
        addr=r['wallet']['address'];label=r['wallet']['name']+((' / '+addr[:7]) if r['wallet']['name'].lower()=='bot' else '')
        table.append('| '+label+' | '+str(r['selected_entry_prefixes'])+' | '+f(r['median_age_seconds'])+' | '+f(r['median_pre_real_sol'],2)+' | '+f(r['median_curve_sol_input'],3)+' | '+f(r['median_observed_prefix_drawdown_pct'])+'% | '+f(r['median_outside_net_sol_5slots'],2)+' | '+f(r['median_observed_completed_hold_seconds'])+' | '+r['clue']+' |')
    (P/'PROFILE_TABLE.md').write_text('\n'.join(table)+'\n')
    provenance_files=['entry_patterns.json','creation_anchors.json','collection.json','accounting.py','bottimus_accounting.py','held_leaders.py','shadow_opens.json','shadow_overlap.py','ANALYSIS_SUMMARY.json']
    sources=['research/day_general_20261004/helpers/decoder.py','research/day_general_20261004/helpers/OFFICIAL_PUMP_IDL.json','research/amm_multiday_20261006/amm_adapter.py','research/amm_multiday_20261006/official/SOURCE_PUMP_AMM_IDL.json','research/MASTER_STRATEGY_REGISTRY.md']
    prov={str(x.relative_to(R)):hashlib.sha256(x.read_bytes()).hexdigest() for x in [P/f for f in provenance_files]+[R/f for f in sources]}
    (P/'PROVENANCE.json').write_text(json.dumps(dict(git_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip(),files_sha256=prov,raw_page_hashes='collection.json and prefix cache request/receipt artifacts'),indent=2))
    print('summarized',len(entries),'entry prefixes,',len(rows),'wallets')
if __name__=='__main__':main()
