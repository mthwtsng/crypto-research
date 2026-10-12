"""Group-custody receipt accounting for the frozen Bottimus payer window."""
import collections, gzip, json, pathlib, re, statistics, sys
P=pathlib.Path(__file__).resolve().parent; R=P.parents[1]
sys.path.insert(0,str(P)); from accounting import D, ammevents, keys, tokens, WSOL
PAYER='bcnzSs3F6F3MG7utvEQHpd8A53nRBM8ZM4TfEs2Zmcp'
SSS='sss5N9Bf7ptzSfn2mPB7t775Hjoxx4vsTChNt8Hfdrp'; SYSTEM='11111111111111111111111111111111'

def ixes(t):
    return t['transaction']['message'].get('instructions',[])+[i for g in t['meta'].get('innerInstructions',[]) or [] for i in g['instructions']]

def parsed(ix):
    p=ix.get('parsed')
    return p if isinstance(p,dict) else {}

def trade_events(t):
    return [dict(e,venue='Pump') for e in D.events(t)]+ammevents(t)

def successful_program(t, program):
    logs=t['meta'].get('logMessages',[]) or []
    return any(x==f'Program {program} success' for x in logs)

def load_rows():
    fs=sorted((P/'raw_wallets/history'/PAYER).glob('page-*.json.gz')); bysig={}
    for f in fs:
        v=json.load(gzip.open(f,'rt'))
        for t in v['transactions']:
            if 'transaction' not in t or 'meta' not in t or t.get('transactionIndex') is None: raise ValueError(f'incomplete receipt: {f}')
            bysig[t['transaction']['signatures'][0]]=t
    return sorted(bysig.values(),key=lambda t:(t['slot'],t['transactionIndex'])),fs

def find_members(rows, roles):
    candidates=set(roles['co_signed_event_users']); ev=collections.Counter(); event_sigs=collections.defaultdict(set); signed_sigs=collections.defaultdict(set)
    sss=collections.Counter(); funded=collections.Counter(); funds=collections.Counter(); ss_sigs=collections.defaultdict(set); fund_sigs=collections.defaultdict(set)
    for t in rows:
        if t['meta']['err'] is not None: continue
        es=trade_events(t); ks=keys(t); sig=t['transaction']['signatures'][0]
        signers={k['pubkey'] for k in t['transaction']['message']['accountKeys'] if isinstance(k,dict) and k.get('signer')}
        for e in es:
            u=e.get('user')
            if u in candidates:
                ev[u]+=1; event_sigs[u].add(sig)
                if u in signers: signed_sigs[u].add(sig)
        ins=ixes(t)
        if successful_program(t,SSS):
            for ix in ins:
                if ix.get('programId')==SSS:
                    refs=set(ix.get('accounts',[]))
                    if PAYER in refs:
                        for u in candidates & refs: sss[u]+=1; ss_sigs[u].add(sig)
        for ix in ins:
            info=parsed(ix).get('info',{})
            if ix.get('programId')==SYSTEM and parsed(ix).get('type')=='transfer' and info.get('source')==PAYER and info.get('destination') in candidates:
                u=info['destination']; funded[u]+=1; funds[u]+=int(info.get('lamports',0)); fund_sigs[u].add(sig)
    members={u for u in candidates if ev[u] and signed_sigs[u] and (ss_sigs[u] or fund_sigs[u])}
    evidence={u:dict(role_event_count=roles['co_signed_event_users'][u],authenticated_event_occurrences=ev[u],
                     authenticated_event_receipts=len(event_sigs[u]),signed_event_receipts=len(signed_sigs[u]),
                     successful_sss_link_instructions=sss[u],successful_sss_link_receipts=len(ss_sigs[u]),
                     direct_funding_transfers=funded[u],direct_funding_receipts=len(fund_sigs[u]),gross_direct_funding_sol=funds[u]/1e9,
                     any_link_receipts=len(ss_sigs[u]|fund_sigs[u]),linked=u in members) for u in sorted(candidates)}
    return members,evidence

def cash_delta(t,members):
    ks=keys(t); m=t['meta']; native=0; wsol=0
    for a in members:
        if a in ks:
            i=ks.index(a); native+=m['postBalances'][i]-m['preBalances'][i]
        wsol+=tokens(t,a,'post')[WSOL]-tokens(t,a,'pre')[WSOL]
    return native,wsol

def instruction_cash(t,members):
    m=t['meta']; ks=keys(t); created=closed=0
    for ix in ixes(t):
        info=parsed(ix).get('info',{}); typ=parsed(ix).get('type','')
        if typ in ('createAccount','createAccountWithSeed') and info.get('source') in members:
            created+=int(info.get('lamports',0))
        if typ=='closeAccount' and info.get('destination') in members and info.get('account') in ks:
            j=ks.index(info['account']); closed+=m['preBalances'][j]-m['postBalances'][j]
    return created,closed

def zero_token_account_lamports(t,owner,mint):
    ks=keys(t); m=t['meta']; total=0
    for b in m.get('postTokenBalances',[]) or []:
        if b.get('owner')==owner and b.get('mint')==mint and int(b['uiTokenAmount']['amount'])==0:
            i=b['accountIndex']
            if i<len(m['postBalances']): total+=m['postBalances'][i]
    return total

def analyze():
    rows,fs=load_rows(); roles=json.loads((P/'bottimus_roles.json').read_text()); members,links=find_members(rows,roles)
    group={PAYER}|members; active={}; cycles=[]; unclassified=[]; inherited=[]; decode_errors=[]; nontrade=0; last_inventory={}; last_inv_sig={}
    event_counts=collections.Counter(); venue_counts=collections.Counter(); payer_fees=failed_fees=failed_n=0; net_native=net_wsol=0; matched=[]
    member_activity=collections.Counter();
    for t in rows:
        sig=t['transaction']['signatures'][0]; m=t['meta']; ks=keys(t); payer=ks[0]
        nd,wd=cash_delta(t,group); net_native+=nd; net_wsol+=wd
        for account in group:
            before=tokens(t,account,'pre'); after=tokens(t,account,'post')
            for mi in set(before)|set(after):
                if mi==WSOL: continue
                key=(account,mi); last_inventory[key]=after[mi]; last_inv_sig[key]=(sig,t.get('blockTime'))
        if payer in group: payer_fees+=m['fee']
        if m['err'] is not None:
            if payer in group: failed_n+=1; failed_fees+=m['fee']
            continue
        try: es=trade_events(t)
        except Exception as e:
            decode_errors.append(dict(signature=sig,error=str(e))); es=[]
        for e in es:
            if e.get('user') in group: event_counts[(e['user'],e['venue'],e['kind'] if 'kind' in e else ('buy' if e['buy'] else 'sell'))]+=1
        changes={}
        for owner in group:
            pre=tokens(t,owner,'pre'); post=tokens(t,owner,'post')
            for mint in set(pre)|set(post):
                if mint!=WSOL and pre[mint]!=post[mint]: changes[(owner,mint)]=post[mint]-pre[mint]
        all_event_keys={(e.get('user'),e.get('mint')) for e in es if e.get('kind') in ('BuyEvent','SellEvent') or 'buy' in e}
        good=[]
        if len(all_event_keys)==1:
            owner,mint=next(iter(all_event_keys)); ee=[e for e in es if (e.get('user'),e.get('mint'))==(owner,mint)]
            delta=sum(int(e['tokens_raw'])*(1 if e['buy'] else -1) for e in ee)
            if owner in group and set(changes)=={(owner,mint)} and delta==changes[(owner,mint)] and all(e.get('quote_is_sol') for e in ee): good=[(owner,mint,ee,delta)]
        if len(good)!=1:
            if changes:
                rec=dict(signature=sig,slot=t['slot'],index=t['transactionIndex'],time=t['blockTime'],reason='mixed_owner_mint_or_transfer_custody_or_quote',
                         changes=[dict(owner=o,mint=mi,delta_raw=d,active=(o,mi) in active) for (o,mi),d in changes.items()],group_cash_raw=nd+wd)
                unclassified.append(rec)
                for key in changes:
                    if key in active: active[key]['tainted']=True
            else: nontrade+=1
            continue
        owner,mint,ee,delta=good[0]; key=(owner,mint); buys=[e for e in ee if e['buy']]; sells=[e for e in ee if not e['buy']]
        q=dict(signature=sig,slot=t['slot'],index=t['transactionIndex'],time=t['blockTime'],owner=owner,mint=mint,
               side='buy' if delta>0 else 'sell',tokens_raw=abs(delta),group_native_raw=nd,group_wsol_raw=wd,group_cash_raw=nd+wd,
               owner_native_raw=(m['postBalances'][ks.index(owner)]-m['preBalances'][ks.index(owner)]) if owner in ks else 0,
               payer=payer,fee_raw=m['fee'] if payer in group else 0,pre_raw=tokens(t,owner,'pre')[mint],post_raw=tokens(t,owner,'post')[mint],
               venues=sorted({e.get('venue','Pump') for e in ee}),events=len(ee),event_quote_sol_raw=sum(int(e['sol_raw']) for e in ee))
        if ee[0].get('venue','Pump')=='Pump' and 'rsol_raw' in ee[0]:
            q['pre_real_sol_raw']=ee[0]['rsol_raw']-ee[0]['sol_raw']*(1 if ee[0]['buy'] else -1)
        q['system_account_create_lamports'],q['closed_token_account_lamports']=instruction_cash(t,group)
        matched.append(q); venue_counts.update(q['venues']); member_activity[owner]+=1
        if key not in active:
            if delta>0 and q['pre_raw']==0 and buys and not sells:
                active[key]=dict(owner=owner,mint=mint,start=t['blockTime'],start_slot=t['slot'],cash_raw=0,buy_legs=0,sell_legs=0,
                                 tainted=False,venues=[],entry_venue=q['venues'][0] if len(q['venues'])==1 else 'mixed_same_receipt',
                                 signatures=[],account_create_raw=0,closed_account_raw=0)
            else:
                inherited.append(dict(signature=sig,owner=owner,mint=mint,time=t['blockTime'],reason='inherited_or_no_zero_inventory_opening',
                                      pre_raw=q['pre_raw'],post_raw=q['post_raw'],group_cash_raw=q['group_cash_raw']))
                continue
        c=active[key]; c['cash_raw']+=q['group_cash_raw']; c['buy_legs']+=len(buys); c['sell_legs']+=len(sells)
        c['signatures'].append(sig); c['venues']=sorted(set(c['venues'])|set(q['venues']))
        c['account_create_raw']+=q['system_account_create_lamports']; c['closed_account_raw']+=q['closed_token_account_lamports']; c['retained_raw']=q['post_raw']; c['last_time']=t['blockTime']
        if q['post_raw']==0:
            c['end']=t['blockTime']; c['hold_seconds']=c['end']-c['start']; c['group_cash_sol']=c['cash_raw']/1e9
            c['zero_token_account_lamports_at_exit']=zero_token_account_lamports(t,owner,mint); cycles.append(c); del active[key]
    clean=[c for c in cycles if not c['tainted']]; tainted=[c for c in cycles if c['tainted']]
    manifest=json.loads((P/'collection.json').read_text()); h=manifest['wallets'][PAYER].get('history_summary',{}); hist=manifest['wallets'][PAYER].get('history',{})
    def quant(v):
        if not v:return None
        z=sorted(v); return dict(min=z[0],q25=z[int((len(z)-1)*.25)],median=statistics.median(z),q75=z[int((len(z)-1)*.75)],max=z[-1])
    opens=[dict(owner=o,mint=mi,tokens_raw=n,last_signature=last_inv_sig[(o,mi)][0],last_time=last_inv_sig[(o,mi)][1],
                 status='tracked_zero-entry_cycle_open' if (o,mi) in active else 'inherited_or_unclassified_open_inventory')
           for (o,mi),n in last_inventory.items() if n>0]
    summary=dict(receipts=len(rows),first_time=min(t['blockTime'] for t in rows),last_time=max(t['blockTime'] for t in rows),pages=len(fs),
        linked_children=len(members),candidate_children=len(links),linked_receipts_by_member={u:v['any_link_receipts'] for u,v in links.items() if v['linked']},
        group_members=sorted(group),authenticated_trade_events=sum(event_counts.values()),trade_receipts=len(matched),
        complete_clean_cycles=len(clean),complete_tainted_cycles=len(tainted),open_cycles=len(active),inherited_trade_receipts=len(inherited),
        unclassified_token_change_receipts=len(unclassified),decode_errors=len(decode_errors),nontrade_receipts=nontrade,
        failed_group_payer_attempts=failed_n,failed_network_sol=failed_fees/1e9,paid_group_network_sol=payer_fees/1e9,
        clean_complete_group_cash_delta_sol=sum(c['group_cash_sol'] for c in clean),
        clean_complete_group_cash_delta_after_once_per_signature_failed_fees_sol=(sum(c['group_cash_sol'] for c in clean)-failed_fees/1e9),
        native_plus_wsol_group_account_delta_sol=(net_native+net_wsol)/1e9,coverage=h)
    return {
        'scope':'Observed per-event-owner/mint zero-to-zero group account cash only; not whole-wallet or beneficial-ownership accounting, PnL verdict, or copy replay.',
        'collection':{
            'history_status':hist.get('status'),'full_rows_verified':hist.get('full_rows_verified'),
            'requested_start_utc':hist.get('requested_start_utc'),'cutoff_utc_exclusive':hist.get('cutoff_utc_exclusive'),
            'page_cap':hist.get('page_cap'),'page_count':len(fs),
            'observed_first_utc':__import__('datetime').datetime.fromtimestamp(min(t['blockTime'] for t in rows),__import__('datetime').timezone.utc).isoformat(),
            'observed_last_utc':__import__('datetime').datetime.fromtimestamp(max(t['blockTime'] for t in rows),__import__('datetime').timezone.utc).isoformat(),
            'requested_window':manifest.get('requested_interval')},
        'summary':summary,'link_evidence':links,'member_activity':dict(member_activity),
        'event_counts':[dict(owner=o,venue=v,side=s,count=n) for (o,v,s),n in sorted(event_counts.items())],
        'venue_counts':dict(venue_counts),'complete_cycles':cycles,
        'open_cycles':[dict(**c,owner=k[0],mint=k[1]) for k,c in active.items()],
        'observed_open_inventory':opens,'inherited_trade_receipts':inherited,
        'unclassified_token_change_receipts':unclassified,'decode_errors':decode_errors,'matched_trade_receipts':matched,
        'execution_profile':{
            'buy_event_quote_sol':quant([t['event_quote_sol_raw']/1e9 for t in matched if t['side']=='buy']),
            'curve_pre_buy_real_sol':quant([t['pre_real_sol_raw']/1e9 for t in matched if t['side']=='buy' and 'pre_real_sol_raw' in t]),
            'matched_cycle_holds_seconds':quant([c['hold_seconds'] for c in clean]),
            'cycles_with_multiple_sells':sum(c['sell_legs']>1 for c in clean),
            'pump_pumpswap_carryovers':sum(c['entry_venue']=='Pump' and 'PumpSwap' in c['venues'] for c in clean),
            'note':'Observed source-cycle profile only; event quotes and holds do not establish copy-entry prices or PnL.'}}

if __name__=='__main__':
    out=analyze(); (P/'bottimus_complete.json').write_text(json.dumps(out,indent=2)+'\n')
    s=out['summary']; print(json.dumps({k:s[k] for k in ['receipts','linked_children','trade_receipts','complete_clean_cycles','complete_tainted_cycles','open_cycles','inherited_trade_receipts','unclassified_token_change_receipts','failed_network_sol','clean_complete_group_cash_delta_sol']}))
