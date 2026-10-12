"""Observed receipt/custody diagnostics, never a hypothetical strategy replay.

Only owner-account reconciled, SOL-quoted Pump/PumpSwap trades enter cycles.
Unknown inherited/transfer custody stays separate. Actual native+WSOL cash
includes paid fees, tips and rent; standalone transfers never become profits.
"""
import collections, gzip, hashlib, json, pathlib, statistics, sys, os
P = pathlib.Path(__file__).resolve().parent
R = P.parents[1]
sys.path.insert(0, str(R/'research/day_general_20261004/helpers'))
import decoder as D
sys.path.insert(0, str(R/'research/amm_multiday_20261006'))
import amm_adapter as A
WSOL=A.WSOL
SPECS={bytes(i['discriminator']):i for i in A.IDL['instructions']}

def raw58(s):
    n=0
    for c in s:n=n*58+D.ALPHABET.index(c)
    return b'\0'*(len(s)-len(s.lstrip('1')))+n.to_bytes((n.bit_length()+7)//8,'big')

def keys(t):
    return [x['pubkey'] if isinstance(x,dict) else x for x in t['transaction']['message']['accountKeys']]

def tokens(t,owner,side):
    z=collections.defaultdict(int)
    for x in t['meta'].get(side+'TokenBalances',[]) or []:
        if x.get('owner')==owner:z[x['mint']]+=int(x['uiTokenAmount']['amount'])
    return z

def ammevents(t):
    pools={}
    for ix in t['transaction']['message']['instructions']+[i for g in t['meta'].get('innerInstructions',[]) or [] for i in g['instructions']]:
        if ix.get('programId')!=A.AMM or not ix.get('data'):continue
        spec=SPECS.get(raw58(ix['data'])[:8])
        if not spec:continue
        a=dict(zip([x['name'] for x in spec['accounts']],ix.get('accounts',[])))
        if all(k in a for k in ['pool','base_mint','quote_mint']):pools[a['pool']]=a
    z=[]
    for e in A.events(t):
        if e['kind'] not in ['BuyEvent','SellEvent']:continue
        a=pools.get(e['pool'])
        if not a:continue
        buy=e['kind']=='BuyEvent'
        z.append(dict(venue='PumpSwap',mint=a['base_mint'],user=e['user'],buy=buy,
                      tokens_raw=e['base_amount_out'] if buy else e['base_amount_in'],
                      quote_is_sol=a['quote_mint']==WSOL,
                      sol_raw=e['user_quote_amount_in'] if buy else e['user_quote_amount_out'],
                      pool=e['pool']))
    return z

def source_rows(wallet):
    fs=[] if os.environ.get('WALLET_EDGE_RECENT_ONLY') else sorted((P/'raw_wallets/history'/wallet).glob('page-*.json.gz'))
    if not fs:fs=[P/'raw_wallets'/('recent_'+wallet+'.json.gz')]
    z={}
    for f in fs:
        if not f.exists():continue
        v=json.load(gzip.open(f,'rt'))
        if any('transaction' not in t or 'meta' not in t for t in v['transactions']):
            raise ValueError('signatures_only_input_rejected: '+str(f))
        for t in v['transactions']:z[t['transaction']['signatures'][0]]=t
    if any(t.get('transactionIndex') is None for t in z.values()):
        raise ValueError('canonical_transaction_index_missing')
    return sorted(z.values(),key=lambda t:(t['slot'],t['transactionIndex']))

def quantile(v):
    if not v:return None
    s=sorted(v)
    return {'min':s[0],'q25':s[int((len(s)-1)*.25)],'median':statistics.median(s),'q75':s[int((len(s)-1)*.75)],'max':s[-1]}

def analyze(w):
    addr=w['address'];rows=source_rows(addr)
    owner=addr;members=[addr]
    cycles=[];active={};trades=[];excluded=[];failed_fee=0;failed=0;decode_errors=[]
    nontrade=[];net_delta=0;all_fee=0;observed_accounts=collections.defaultdict(set)
    for t in rows:
        sig=t['transaction']['signatures'][0];m=t['meta'];ks=keys(t);payer=ks[0]
        if addr not in ks:continue
        native=sum(m['postBalances'][ks.index(a)]-m['preBalances'][ks.index(a)] for a in members if a in ks)
        pre=tokens(t,owner,'pre');post=tokens(t,owner,'post')
        extra_wsol=sum(tokens(t,a,'post')[WSOL]-tokens(t,a,'pre')[WSOL] for a in members if a!=owner)
        for side in ['pre','post']:
            for b in m.get(side+'TokenBalances',[]) or []:
                if b.get('owner')==owner:observed_accounts[b['mint']].add(ks[b['accountIndex']])
        cash=native+post[WSOL]-pre[WSOL]+extra_wsol;net_delta+=cash
        if payer in members:all_fee+=m['fee']
        if m['err'] is not None:
            if payer in members:failed+=1;failed_fee+=m['fee']
            continue
        try:es=[dict(e,venue='Pump') for e in D.events(t)]+ammevents(t)
        except Exception as e:
            decode_errors.append(dict(signature=sig,error=str(e)))
            for mint in set(pre)|set(post):
                if pre[mint]!=post[mint] and mint in active:active[mint]['tainted']=True
            continue
        bymint=collections.defaultdict(list)
        for e in es:
            if e.get('user')==owner:bymint[e['mint']].append(e)
        changes={mint:post[mint]-pre[mint] for mint in set(pre)|set(post) if mint!=WSOL and post[mint]!=pre[mint]}
        matches=[]
        for mint,ee in bymint.items():
            delta=sum(e['tokens_raw']*(1 if e['buy'] else -1) for e in ee)
            if delta!=changes.get(mint,0) or not all(e['quote_is_sol'] for e in ee):continue
            matches.append((mint,ee))
        # Mixed mints/quotes/custody are not apportioned speculatively.
        if len(matches)!=1 or len(changes)!=1:
            if changes:
                excluded.append(dict(signature=sig,time=t['blockTime'],changes=changes,cash_raw=cash,reason='nontrade_or_ambiguous_custody_or_quote'))
                for mint in changes:
                    if mint in active:active[mint]['tainted']=True
            else:nontrade.append(dict(signature=sig,cash_raw=cash))
            continue
        mint,ee=matches[0];delta=changes[mint]
        buys=[e for e in ee if e['buy']];sells=[e for e in ee if not e['buy']]
        q=dict(signature=sig,slot=t['slot'],index=t.get('transactionIndex'),time=t['blockTime'],mint=mint,
               side='buy' if delta>0 else 'sell',tokens_raw=abs(delta),cash_raw=cash,fee_raw=m['fee'] if payer in members else 0,
               pre_raw=pre[mint],post_raw=post[mint],venue=ee[0]['venue'],event_sol_raw=sum(e['sol_raw'] for e in ee),
               events=len(ee),payer_is_owner=payer==addr)
        if ee[0]['venue']=='Pump':
            e=ee[0];q['pre_real_sol']= (e['rsol_raw']-e['sol_raw']*(1 if e['buy'] else -1))/1e9
            q['post_real_sol']=ee[-1]['rsol_raw']/1e9
        trades.append(q)
        if mint not in active:
            if delta>0 and pre[mint]==0 and buys and not sells:
                active[mint]=dict(mint=mint,start=t['blockTime'],start_slot=t['slot'],cash_raw=0,buy_legs=0,sell_legs=0,
                                  tainted=False,venues=[],signatures=[],cost_raw=0,entry_venue=ee[0]['venue'])
            else:
                excluded.append(dict(signature=sig,mint=mint,reason='inherited_or_no_zero_inventory_opening',cash_raw=cash));continue
        c=active[mint]
        if len(observed_accounts[mint])>1:c['tainted']=True
        # Balance changes in other observed accounts were already excluded above.
        c['cash_raw']+=cash;c['buy_legs']+=len(buys);c['sell_legs']+=len(sells)
        c['signatures'].append(sig);c['venues']=sorted(set(c['venues'])|{e['venue'] for e in ee})
        c['retained_raw']=post[mint];c['last_time']=t['blockTime']
        if cash<0:c['cost_raw']-=cash
        if post[mint]==0:
            c['end']=t['blockTime'];c['hold_seconds']=c['end']-c['start'];c['net_sol']=c['cash_raw']/1e9
            cycles.append(c);del active[mint]
    clean=[c for c in cycles if not c['tainted']]
    gains=sum(c['net_sol'] for c in clean if c['net_sol']>0);loss=-sum(c['net_sol'] for c in clean if c['net_sol']<0)
    buys=[t for t in trades if t['side']=='buy'];countsm=collections.Counter(c['mint'] for c in clean)
    gross=sum(c['net_sol'] for c in clean)
    byday=collections.defaultdict(lambda:dict(cycles=0,cycle_cash_sol=0,failed_fee_sol=0))
    import datetime
    for c in clean:
        day=datetime.datetime.fromtimestamp(c['end'],datetime.timezone.utc).date().isoformat()
        byday[day]['cycles']+=1;byday[day]['cycle_cash_sol']+=c['net_sol']
    for t in rows:
        if t['meta']['err'] is not None and keys(t)[0] in members and t.get('blockTime'):
            day=datetime.datetime.fromtimestamp(t['blockTime'],datetime.timezone.utc).date().isoformat()
            byday[day]['failed_fee_sol']+=t['meta']['fee']/1e9
    for d in byday.values():d['completed_cycle_cash_minus_failed_fees_sol']=d['cycle_cash_sol']-d['failed_fee_sol']
    manifest=json.loads((P/'collection.json').read_text())
    coverage=manifest['wallets'][addr].get('history_summary',{}) if not os.environ.get('WALLET_EDGE_RECENT_ONLY') else dict(status='latest250_fixed_cutoff_receipts_only')
    group_report='bottimus_complete.json' if addr=='bcnzSs3F6F3MG7utvEQHpd8A53nRBM8ZM4TfEs2Zmcp' else None
    return dict(wallet=w,asset_owner=owner,cash_members=members,separate_controller_group_report=group_report,coverage=coverage,receipts=len(rows),min_time=min((t['blockTime'] for t in rows if t.get('blockTime')),default=None),
                max_time=max((t['blockTime'] for t in rows if t.get('blockTime')),default=None),
                decoded_trades=len(trades),buys=len(buys),venues=dict(collections.Counter(t['venue'] for t in buys)),
                failed_payer_attempts=failed,failed_network_sol=failed_fee/1e9,paid_network_sol=all_fee/1e9,
                completed_observed_account_cycles=len(clean),tainted_cycles=sum(c['tainted'] for c in cycles),
                cycle_cash_sol=gross,completed_cycle_cash_minus_all_failed_fees_sol=gross-failed_fee/1e9,
                win_rate=sum(c['net_sol']>0 for c in clean)/len(clean) if clean else None,
                profit_factor=gains/loss if loss else None,largest_cycle_sol=max((c['net_sol'] for c in clean),default=None),
                hold_seconds=quantile([c['hold_seconds'] for c in clean]),buy_sol=quantile([t['event_sol_raw']/1e9 for t in buys]),
                entry_real_sol=quantile([t['pre_real_sol'] for t in buys if 'pre_real_sol' in t]),
                repeated_completed_mints=sum(n>1 for n in countsm.values()),multi_buy_cycles=sum(c['buy_legs']>1 for c in clean),
                multi_sell_cycles=sum(c['sell_legs']>1 for c in clean),carryover_cycles=sum(c['entry_venue']=='Pump' and 'PumpSwap' in c['venues'] for c in clean),
                native_plus_wsol_net_change_sol=net_delta/1e9,open_observed_cycles=list(active.values()),
                excluded_receipts=len(excluded),decode_errors=decode_errors,
                nontrade_cash_sol=sum(n['cash_raw'] for n in nontrade)/1e9,
                scope='observed zero-to-zero token account cycle cash; transferred/inherited/unclassified custody excluded; open marks unknown; rent remaining locked or refunded outside trade receipts separate; not whole-wallet PnL or copy replay',
                daily=dict(sorted(byday.items())),cycles=clean,trades=trades,excluded=excluded)

def main():
    wallets=json.loads((P/'wallets.json').read_text());out=[]
    for w in wallets:
        z=analyze(w);out.append(z)
        print(w['name'],w['address'][:8],z['receipts'],z['buys'],z['completed_observed_account_cycles'],round(z['completed_cycle_cash_minus_all_failed_fees_sol'],6),flush=True)
        (P/'accounting.json').write_text(json.dumps(out,indent=2)+'\n')
    fields=['name','address','receipts','buys','cycles','cycle_cash_minus_failed','win_rate','hold_median_s','entry_real_sol_median','buy_sol_median','repeated_mints','multi_buy_cycles','multi_sell_cycles','carryover_cycles','open_cycles','excluded']
    import csv
    with (P/'wallet_summary.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for z in out:
            def median(k):return z[k]['median'] if z[k] else None
            writer.writerow(dict(name=z['wallet']['name'],address=z['wallet']['address'],receipts=z['receipts'],buys=z['buys'],cycles=z['completed_observed_account_cycles'],cycle_cash_minus_failed=z['completed_cycle_cash_minus_all_failed_fees_sol'],win_rate=z['win_rate'],hold_median_s=median('hold_seconds'),entry_real_sol_median=median('entry_real_sol'),buy_sol_median=median('buy_sol'),repeated_mints=z['repeated_completed_mints'],multi_buy_cycles=z['multi_buy_cycles'],multi_sell_cycles=z['multi_sell_cycles'],carryover_cycles=z['carryover_cycles'],open_cycles=len(z['open_observed_cycles']),excluded=z['excluded_receipts']))
if __name__=='__main__':main()
