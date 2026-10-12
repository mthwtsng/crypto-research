"""Bounded read-only forensic probe; no trading RPC calls or credentials saved."""
import concurrent.futures
import datetime
import json
from pathlib import Path
import re
import time
import requests

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
MINT = 'CvyUsq67bCiZZwr1dZKu2y1HXojjrz6tvdkKY4XGpump'
URLS = re.findall(r'https://(?:rpc\.shyft\.to\?api_key=[A-Za-z0-9_-]+|solana-mainnet\.g\.alchemy\.com/v2/[A-Za-z0-9_-]+)', (ROOT/'AGENTS.md').read_text())
EVENTS = json.loads((OUT/'target_events.json').read_text())
WALLETS = json.loads((OUT/'target_wallets.json').read_text())
FIRST = {}
for event in EVENTS:
    FIRST.setdefault(event['user'], event)

def rpc(method, params):
    for attempt in range(3):
        for index, url in enumerate(URLS):
            try:
                reply = requests.post(url, json={'jsonrpc':'2.0','id':1,'method':method,'params':params}, timeout=12).json()
                if isinstance(reply, dict) and 'result' in reply:
                    return {'result':reply['result'], 'provider_index':index, 'fetched_at_ms':int(time.time()*1000)}
            except Exception:
                pass
        time.sleep(.2*(attempt+1))
    return {'error':'bounded_rpc_failure', 'method':method}

explicit = ['FcNHxPSqQ1ChyWmwW8C4zzXuUvQR3b7zBNBxk84VPmSv','Dv4MuKsqjXZPMsep9ZDdXrRvNmCEFFGPoYidRMgJQsad','B9ksmPhuhj43BBWXJxm1SUXDbVZRthmvf8FZMpYhVhoH','CMcKT7wshBUjRrPy6uH4bdTRkmxFLngQh2kTXrrzRVdC','Hy4ZuryDVXuytB3TGXmAdcqHQeF7WMQD4dZLdAipyVFt','7dGV2auDmovmUbb27KBW1QNN52aLXd4ZZbafG9nyr5VT']
top = [w for w,_ in sorted(WALLETS.items(),key=lambda item:item[1]['buy_sol']+item[1]['sell_sol'],reverse=True)[:10]]
holder_rows = [json.loads(line) for line in (OUT/'ghost_holder_screen.jsonl').read_text().splitlines()]
entry = next(r for r in holder_rows if r['report']['audit_completed_at_ms']==1791760693840)
holder = [r['wallet'] for r in entry['report']['evidence'][:4]]
selected = list(dict.fromkeys(explicit+top+holder))

def history(wallet):
    first = FIRST.get(wallet)
    if not first:
        return wallet, {'error':'no_observed_curve_buy'}
    result = rpc('getSignaturesForAddress',[wallet,{'limit':50,'before':first['signature'],'commitment':'confirmed'}])
    result['before_signature']=first['signature']
    result['first_target_ms']=first['received_at_ms']
    return wallet,result

with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    histories = dict(pool.map(history,selected))
(OUT/'rpc_wallet_prior_signatures.json').write_text(json.dumps(histories,indent=2))
signatures = set()
for wallet,h in histories.items():
    if isinstance(h.get('result'),list):
        valid = [r for r in h['result'] if r.get('err') is None]
        # Both nearest and oldest sampled history; not asserted complete funding history.
        signatures.update(r['signature'] for r in valid[:5]+valid[-5:])
    if wallet in FIRST:
        signatures.add(FIRST[wallet]['signature'])

def transaction(signature):
    return signature,rpc('getTransaction',[signature,{'encoding':'jsonParsed','maxSupportedTransactionVersion':1,'commitment':'confirmed'}])

with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    transactions = dict(pool.map(transaction,sorted(signatures)))
(OUT/'rpc_funding_transactions.json').write_text(json.dumps(transactions))
transfers = []
for signature,wrapped in transactions.items():
    tx=wrapped.get('result')
    if not tx or not tx.get('meta') or tx['meta'].get('err') is not None:
        continue
    instructions=list(tx['transaction']['message'].get('instructions',[]))
    for group in tx['meta'].get('innerInstructions') or []:
        instructions.extend(group.get('instructions',[]))
    for instruction in instructions:
        parsed=instruction.get('parsed')
        if not isinstance(parsed,dict) or instruction.get('program')!='system':
            continue
        info=parsed.get('info',{})
        if parsed.get('type') not in ('transfer','createAccount','transferWithSeed'):
            continue
        destination=info.get('destination',info.get('newAccount'))
        if destination not in selected:
            continue
        transfers.append({'signature':signature,'slot':tx['slot'],'block_time':tx.get('blockTime'),'source':info.get('source'),'destination':destination,'lamports':info.get('lamports'),'type':parsed.get('type')})
(OUT/'rpc_incoming_transfer_sample.json').write_text(json.dumps(transfers,indent=2))
meta={'asof_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'wallets':selected,'history_limit_per_wallet':50,'transaction_selection':'first observed target receipt plus five nearest and five oldest successful prior signatures in the bounded50 sample','transactions_requested':len(signatures),'transactions_resolved':sum(isinstance(r.get('result'),dict) for r in transactions.values()),'incoming_transfers':len(transfers),'funding_history_complete':False,'rpc_methods':['getSignaturesForAddress','getTransaction'],'max_supported_transaction_version':1}
(OUT/'rpc_funding_manifest.json').write_text(json.dumps(meta,indent=2))
print(json.dumps({k:v for k,v in meta.items() if k!='wallets'}))
print(json.dumps(transfers[:20]))
