"""Compare observed source entries with frozen paper signal anchors on same mint.

No paper PnL comparison: epochs contain known calculation defects and no real fills.
"""
import collections,hashlib,json,pathlib,statistics
P=pathlib.Path(__file__).resolve().parent;R=P.parents[1]
def main():
    target=P/'shadow_opens.json'
    if not target.exists():
        raw=(R/'data/ghost_trades_master.jsonl').read_bytes()
        records=[];bad=0
        for line in raw.splitlines():
            try:
                z=json.loads(line)
                if z.get('event')=='OPEN':records.append(z)
            except Exception:bad+=1
        unique={r.get('position_id'):r for r in records}
        target.write_text(json.dumps(dict(source='data/ghost_trades_master.jsonl',sha256=hashlib.sha256(raw).hexdigest(),bad_lines=bad,opens=list(unique.values())),indent=2))
    cutoff=json.loads((P/'raw_wallets/freeze.json').read_text())['block_time']
    opens=[o for o in json.loads(target.read_text())['opens'] if o.get('timestamp',cutoff)>=0 and o.get('timestamp',cutoff)<cutoff]
    accounting=json.loads((P/'accounting.json').read_text());bymint=collections.defaultdict(list)
    for a in accounting:
        for t in a['trades']:
            if t['side']=='buy':bymint[t['mint']].append(dict(t,wallet=a['wallet']))
    rows=[]
    for o in opens:
        if o.get('source_slot') is None or o.get('source_transaction_index') is None:continue
        actual=bymint.get(o['mint'],[])
        if not actual:continue
        anchor=(o['source_slot'],o['source_transaction_index'])
        perwallet=collections.defaultdict(list)
        for t in actual:perwallet[t['wallet']['address']].append(t)
        candidates=[min(tt,key=lambda t:(abs(t['slot']-anchor[0]),abs(t['index']-anchor[1]))) for tt in perwallet.values()]
        for t in candidates:
            if abs(t['time']-o['timestamp'])>300:continue
            source_account=next(a for a in accounting if a['wallet']['address']==t['wallet']['address'])
            cycle=next((c for c in source_account['cycles'] if t['signature'] in c['signatures']),None)
            sold_before=None
            if cycle:
                close=next(q for q in source_account['trades'] if q['signature']==cycle['signatures'][-1] and q['mint']==t['mint'])
                sold_before=(close['slot'],close['index'])<anchor
            rows.append(dict(mint=o['mint'],strategy=o.get('strategy_code'),vm=o.get('vm_id'),paper_model=o.get('execution_model'),
                             paper_position=o.get('position_id'),paper_signal_slot=anchor[0],paper_signal_index=anchor[1],paper_time=o['timestamp'],paper_signal_reserve=o.get('signal_reserve_sol'),
                             bot_wallet=t['wallet'],bot_slot=t['slot'],bot_index=t['index'],bot_time=t['time'],bot_pre_reserve=t.get('pre_real_sol'),
                             bot_minus_paper_slots=t['slot']-anchor[0],bot_minus_paper_seconds=t['time']-o['timestamp'],
                             bot_before_paper_anchor=(t['slot'],t['index'])<anchor,bot_signature=t['signature'],paper_anchor_signature=o.get('source_signature'),
                             matched_source_cycle_sold_before_paper_anchor=sold_before,source_cycle_cash_sol=cycle['net_sol'] if cycle else None))
    grouped=[]
    for a in accounting:
        rr=[r for r in rows if r['bot_wallet']['address']==a['wallet']['address']]
        if rr:grouped.append(dict(wallet=a['wallet'],matches=len(rr),unique_mints=len({r['mint'] for r in rr}),before=sum(r['bot_before_paper_anchor'] for r in rr),already_sold=sum(r['matched_source_cycle_sold_before_paper_anchor'] is True for r in rr),median_slot_gap=statistics.median(r['bot_minus_paper_slots'] for r in rr),median_second_gap=statistics.median(r['bot_minus_paper_seconds'] for r in rr)))
    (P/'shadow_overlap.json').write_text(json.dumps(dict(scope='descriptive actual source buys vs paper signal anchors; repeated wallet buys are not independent matches; no real user fill or comparable PnL',paper_opens=len(opens),matched_rows=len(rows),unique_mints=len({r['mint'] for r in rows}),summary=grouped,rows=rows),indent=2))
    print(json.dumps(grouped,indent=2))
if __name__=='__main__':main()
