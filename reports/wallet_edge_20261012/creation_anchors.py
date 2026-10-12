"""Recover authenticated token age without pretending to repair full price tapes."""
import concurrent.futures,datetime,json,pathlib,sys
from rpc import rpc
from accounting import D
P=pathlib.Path(__file__).resolve().parent
def one(e):
    if e['genesis']['found']:
        c=e['genesis']['event']
        return dict(signature=e['signature'],wallet=e['wallet'],mint=e['mint'],creation_signature=c['signature'],creation_slot=c['slot'],creation_index=c['transaction_index'],creation_time=c['block_time'],creator=c['creator'],age_seconds=e['blockTime']-c['block_time'],creator_is_event_user=c['creator']==e['event_user'],source='creation_in_saved_prefix',continuous_prefix_repair=False)
    resolution=e.get('official_curve_resolution') or {}
    a=resolution.get('address') or e['mint']
    cfg=dict(transactionDetails='full',encoding='jsonParsed',maxSupportedTransactionVersion=1,sortOrder='asc',limit=10,commitment='finalized',filters=dict(blockTime=dict(lte=e['blockTime']),status='succeeded'))
    try:
        rows=rpc('getTransactionsForAddress',[a,cfg])['data']
        for t in rows:
            if (t['slot'],t['transactionIndex'])>(e['slot'],e['transaction_index']):continue
            for c in D.creations(t):
                if c['mint']==e['mint']:
                    return dict(signature=e['signature'],wallet=e['wallet'],mint=e['mint'],creation_signature=t['transaction']['signatures'][0],creation_slot=t['slot'],creation_index=t['transactionIndex'],creation_time=t['blockTime'],creator=c['deployer'],age_seconds=e['blockTime']-t['blockTime'],creator_is_event_user=c['deployer']==e['event_user'],source='separate_first10_successful_curve_receipts',continuous_prefix_repair=False)
        return dict(signature=e['signature'],wallet=e['wallet'],mint=e['mint'],error='creation_not_in_earliest10_successful_curve_receipts')
    except Exception as x:return dict(signature=e['signature'],wallet=e['wallet'],mint=e['mint'],error=str(x))
def main():
    document=json.loads((P/'entry_patterns.json').read_text())
    ee=document['entries'];out={}
    for key in ['successful_history_supplement','bcnz_payer_linked_child_sample']:
        ee+=document.get(key,{}).get('entries',[])
    for name in ['entry_patterns_extension.json','entry_patterns_linked.json','entry_patterns_success_extension.json','payer_linked_entry_patterns.json']:
        extra=P/name
        if extra.exists():ee+=json.loads(extra.read_text()).get('entries',[])
    path=P/'creation_anchors.json'
    if path.exists():out={e['signature']:e for e in json.loads(path.read_text())['anchors']}
    missing=[e for e in ee if e['signature'] not in out]
    with concurrent.futures.ThreadPoolExecutor(4) as pool:
        fs=[pool.submit(one,e) for e in missing]
        for f in concurrent.futures.as_completed(fs):
            z=f.result();out[z['signature']]=z
            path.write_text(json.dumps(dict(scope='independent CreateEvent anchors establish age/creator only; gaps between creation and saved prefix remain incomplete',anchors=list(out.values())),indent=2))
    print('creation anchors',len(out),'unknown',sum('error' in e for e in out.values()),flush=True)
if __name__=='__main__':main()
