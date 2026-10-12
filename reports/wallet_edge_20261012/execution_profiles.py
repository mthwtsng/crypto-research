"""Public instruction/role fingerprints; account references are not copy proof."""
import collections,json,pathlib,statistics,sys,hashlib
from accounting import source_rows,keys,tokens,D,A,WSOL,ammevents,quantile
P=pathlib.Path(__file__).resolve().parent;R=P.parents[1]
def roster(path):
    z={}
    for line in path.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith('#'):continue
        a,_,name=line.partition('#');z[a.strip()]=name.strip()
    return z
def main():
    snap=P/'execution_roster.json'
    if snap.exists():labels=json.loads(snap.read_text())['labels']
    else:
        labels=roster(R/'kol_wallets.txt');labels.update(roster(R/'tracked_wallets.txt'))
        snap.write_text(json.dumps(dict(labels=labels,source_sha256={f:hashlib.sha256((R/f).read_bytes()).hexdigest() for f in ['kol_wallets.txt','tracked_wallets.txt']}),indent=2))
    targets={w['address'] for w in json.loads((P/'wallets.json').read_text())}
    labels={a:name for a,name in labels.items() if a not in targets};out=[]
    for w in json.loads((P/'wallets.json').read_text()):
        addr=w['address'];rows=source_rows(addr);programs=collections.Counter();refs=collections.Counter();signers=collections.Counter();users=collections.Counter();quotes=collections.Counter();noops=0;good=0;reference_examples=[];trunc=0
        native_noop_fees=0
        for t in rows:
            message=t['transaction']['message'];ks=keys(t);m=t['meta'];ix=message['instructions']
            programs.update(set(x.get('programId','unknown') for x in ix))
            signers.update(k['pubkey'] for k in message['accountKeys'] if k.get('signer') and k['pubkey']!=addr)
            # Only named references passed to custom top-level programs, not
            # pooled transaction account keys or standard protocol recipients.
            named=set()
            for i in ix:
                pr=i.get('programId','')
                if pr in [D.PUMP,A.AMM,'11111111111111111111111111111111','ComputeBudget111111111111111111111111111111','TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA','TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb','ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL']:continue
                named|={a for a in i.get('accounts',[]) if a in labels}
            refs.update(named)
            if named and len(reference_examples)<5:reference_examples.append(dict(signature=t['transaction']['signatures'][0],slot=t['slot'],index=t['transactionIndex'],success=m['err'] is None,programs=[i.get('programId') for i in ix],named=[dict(address=a,name=labels[a]) for a in sorted(named)]))
            if any('truncated' in l.lower() for l in m.get('logMessages',[]) or []):trunc+=1
            if m['err'] is not None:continue
            good+=1
            events=D.events(t);users.update(e['user'] for e in events)
            quotes.update(str(e.get('quote_mint','native_SOL')) for e in events)
            before=tokens(t,addr,'pre');after=tokens(t,addr,'post')
            if all(before[a]==after[a] for a in set(before)|set(after)):
                noops+=1
                if ks[0]==addr:native_noop_fees+=m['fee']
        out.append(dict(wallet=w,receipts=len(rows),successful=good,successful_with_no_owned_token_change=noops,paid_network_sol_on_no_token_change=native_noop_fees/1e9,
                        top_programs=programs.most_common(8),co_signers=signers.most_common(5),pump_event_users=users.most_common(5),quote_mints=quotes.most_common(5),
                        custom_program_named_wallet_references=[dict(address=a,name=labels[a],transactions=n) for a,n in refs.most_common(16)],reference_examples=reference_examples,truncated_logs=trunc,
                        interpretation='read-only account reference/role fingerprint; does not decode private trigger or prove buy followed referenced wallet'))
        print(w['name'],addr[:7],good,noops,refs.most_common(2),users.most_common(2),flush=True)
    (P/'execution_profiles.json').write_text(json.dumps(out,indent=2)+'\n')
if __name__=='__main__':main()
