"""Public post-completion orders omitted by succeeded-only source histories.

Diagnostics only: a price/limit-compatible order is not proof that its entire
transaction would succeed. Do not add these quotes to realized PnL.
"""
import collections,gzip,json,pathlib
import bind_curve_limits as B
import curve_adapter as A
P=pathlib.Path(__file__).resolve().parent

def main():
 paths=json.load(gzip.open(P/'CORRECTED_CURVE_PATHS.json.gz','rt'));rows=[];coverage=[]
 for mint in sorted({p['mint'] for p in paths if p.get('migration_eligibility')=='recorded_completion_displaced'}):
  f=P/'failed_curve_intents'/(mint+'.json.gz')
  if not f.exists():coverage.append(dict(mint=mint,status='collection_pending'));continue
  d=json.load(gzip.open(f,'rt'));coverage.append(dict(mint=mint,status='collected',receipts=d['audit']['receipts']))
  for p in paths:
   if p['mint']!=mint or p['scenario']!='central85' or p.get('migration_eligibility')!='recorded_completion_displaced':continue
   st=p['last_state'];candidates=[];counts=collections.Counter()
   for t in d['transactions']:
    if t['blockTime']<p['historical_completion_time']:continue
    # Completion failures isolate a state condition changed by our intervention.
    if not any('BondingCurveComplete' in line for line in t['meta'].get('logMessages',[]) or []):continue
    try:instructions=B.bind(t,mint)
    except Exception as e:counts['decode_error']+=1;continue
    for b in instructions:
     if not b['name'].startswith('buy'):continue
     counts['public_completion_failed_buys']+=1
     if b['name'].endswith('_v3'):
      counts['v3_requires_pool_leg']+=1;continue
     r=A.buy_budget(st,b['fields']['budget_raw']) if 'budget_raw' in b['fields'] else A.exact_buy(st,b['encoded_tokens_or_budget'])
     if not r:continue
     q,n=r;gross=q+A.fee(q,st['fee_bps'])+A.fee(q,st['creator_fee_bps'])
     if gross>b['fields'].get('max_cost_raw',10**30) or n<b['fields'].get('min_tokens_raw',0):continue
     counts['quote_limit_compatible']+=1
     if n==st['rtokens_raw']:
      counts['quote_could_exhaust_remaining']+=1
      if len(candidates)<10:candidates.append(dict(signature=t['transaction']['signatures'][0],slot=t['slot'],index=t['transactionIndex'],time=t['blockTime'],instruction=b['name'],gross_lamports=gross,tokens_raw=n))
   rows.append(dict(mint=mint,rule=p['rule'],counts=dict(counts),completion_candidates=candidates))
 result=dict(scope='Counterfactual quote-only completion diagnostics, no full failed-transaction execution or migration proof. Bounds use last retained source fee rates; dynamic fee uncertainty remains.',coverage=coverage,rows=rows)
 (P/'FAILED_COMPLETION_ORDER_DIAGNOSTICS.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(rows,indent=2))
if __name__=='__main__':main()
