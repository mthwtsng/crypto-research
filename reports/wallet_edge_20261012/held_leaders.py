"""Verify pre-buy named-wallet token holdings included in successful receipts."""
import collections,gzip,json,pathlib
P=pathlib.Path(__file__).resolve().parent
def main():
    d=json.loads((P/'entry_patterns.json').read_text())
    ee=d['entries']+d['successful_history_supplement']['entries']
    selected=[e for e in ee if e['wallet'].startswith(('7ovu','Buek','Fhbh','niggerd'))]
    bywallet=collections.defaultdict(list)
    for e in selected:bywallet[e['wallet']].append(e)
    out=[]
    for addr,entries in bywallet.items():
        signatures={e['signature'] for e in entries};receipts={}
        files=[P/'raw_wallets'/('recent_'+addr+'.json.gz')]+sorted((P/'raw_wallets/successful_history'/addr).glob('*.gz'))
        for f in files:
            if not f.exists():continue
            for t in json.load(gzip.open(f,'rt'))['transactions']:
                sig=t['transaction']['signatures'][0]
                if sig in signatures:receipts[sig]=t
        for e in entries:
            t=receipts.get(e['signature']);refs=e['current_roster_transaction_account_references']
            roster=set(refs['kol_current_snapshot_account_keys'])|set(refs['tracked16_current_file_account_keys'])
            if t is None:
                out.append(dict(wallet=addr,signature=e['signature'],error='source_receipt_not_found'));continue
            holds=[]
            for b in t['meta'].get('preTokenBalances',[]) or []:
                if b.get('mint')==e['mint'] and b.get('owner') in roster and b.get('owner')!=e['event_user']:
                    raw=int(b['uiTokenAmount']['amount'])
                    if raw>0:holds.append(dict(owner=b['owner'],tokens_raw=raw,account_index=b['accountIndex'],token_account=t['transaction']['message']['accountKeys'][b['accountIndex']]['pubkey']))
            out.append(dict(wallet=addr,wallet_name=e['wallet_name'],signature=e['signature'],mint=e['mint'],slot=e['slot'],index=e['transaction_index'],source=e['sample_source'],pre_buy_named_wallet_holdings=holds))
    summary=[]
    for addr,entries in bywallet.items():
        rr=[r for r in out if r['wallet']==addr]
        summary.append(dict(wallet=addr,name=entries[0]['wallet_name'],entries=len(rr),holding_present=sum(bool(r.get('pre_buy_named_wallet_holdings')) for r in rr),owners=dict(collections.Counter(h['owner'] for r in rr for h in r.get('pre_buy_named_wallet_holdings',[])))))
    (P/'held_leaders.json').write_text(json.dumps(dict(scope='receipt metadata authenticates already-held traded tokens for named accounts passed in transaction; source current identity labels are exploratory; does not decode custom predicate or establish copying/profit',summary=summary,rows=out),indent=2))
    print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
