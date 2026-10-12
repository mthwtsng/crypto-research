"""Reconstruct post-transaction virtual reserves from source fees and sweeps.

Trade events expose pre-trade virtual reserves. Retained deferred protocol and
creator fees reduce virtual reserves after that trade. Do not report the event's
pre-value as the complete transaction's post-state.
"""
import gzip,json,pathlib
import amm_counterparty as C
P=pathlib.Path(__file__).resolve().parent
def main():
 (P/'normalized_amm_tapes').mkdir(exist_ok=True);audits=[]
 for f in sorted((P/'repaired_amm_tapes').glob('*.gz')):
  t=json.load(gzip.open(f,'rt'));v=t['groups'][0]['state']['virtual'];errors=[];updates=0
  for g in t['groups'][1:]:
   g['before']['virtual']=v
   st=dict(g['before'])
   for op in g['custody_ops']:
    if op['kind']=='sweep':v+=op['raw'];st['virtual']=v;st['quote']-=op['raw'];continue
    if op['kind']!='trade':continue
    e=op['event']
    if e['virtual']!=v:errors.append(dict(signature=g['signature'],reason='virtual_prestate_gap',expected=v,observed=e['virtual']))
    # Exact-input quote fees can be computed before a one-lamport input
    # adjustment. Reuse independently receipt-checked fee components rather
    # than recomputing ceil fees on the adjusted event input.
    val=dict(st,historical_rates=e['rates'])
    r=(C.A.buy(val,e['gross']) if e['ix'].startswith('buy_exact_quote_in') else C.A.exact_buy(val,e['n'])) if e['buy'] else C.A.sell(val,e['n'])
    if not r or (r['n'],r['q'])!=(e['n'],e['q']):
     errors.append(dict(signature=g['signature'],reason='source_quote_mismatch'));continue
    st=C.moved(st,r,e['buy'],e.get('deferred',False));v=st['virtual']
    if e.get('deferred'):updates+=1
   g['state']['virtual']=v
  with gzip.open(P/'normalized_amm_tapes'/f.name,'wt',compresslevel=1) as out:json.dump(t,out)
  audits.append(dict(pool=t['pool'],mint=t['mint'],deferred_updates=updates,errors=errors));print('VIRTUAL_NORMALIZE',t['mint'][:8],updates,len(errors),flush=True)
 (P/'AMM_VIRTUAL_NORMALIZATION.json').write_text(json.dumps(dict(audits=audits),indent=2)+'\n')
if __name__=='__main__':main()
