"""Independent event-local reconstruction, not the helper's own generated expected output."""
import collections,gzip,json,pathlib
import curve_adapter as A
P=pathlib.Path(__file__).resolve().parent
def main():
 counts=collections.Counter();bad=[];completions=[]
 for f in (P/'bound_curve_tapes').glob('*.gz'):
  t=json.load(gzip.open(f,'rt'))
  for g in t['groups']:
   for e in g['events']:
    q,n=e['sol_raw'],e['tokens_raw'];d=1 if e['buy'] else -1
    st=dict(vsol_raw=e['vsol_raw']-d*q,vtokens_raw=e['vtokens_raw']+d*n,rsol_raw=e['rsol_raw']-d*q,rtokens_raw=e['real_token_reserves']+d*n,fee_bps=e['fee_bps'],creator_fee_bps=e['creator_fee_bps'])
    if e['buy']:
     quote=A.buy_budget(st,e['budget_raw']) if e['ix_name'].startswith('buy_exact') else A.exact_buy(st,n)
     actual=quote
     expected=(q,n)
    else:
     quote=A.sell(st,n);actual=quote[1] if quote else None;expected=q
    counts[e['ix_name']]+=1
    if actual!=expected:bad.append(dict(mint=t['mint'],signature=g['signature'],name=e['ix_name'],expected=expected,actual=actual))
    if e['buy'] and e['real_token_reserves']==0:completions.append(dict(mint=t['mint'],name=e['ix_name'],q=q,n=n,parity=actual==expected))
 result=dict(counts=dict(counts),errors=bad,completion_examples=completions,scope='event-local reserve transitions independently reversed from authenticated poststate; full no-intervention custody/limits replay still required')
 (P/'CURVE_MATH_VERIFICATION.json').write_text(json.dumps(result,indent=2)+'\n');print('QUOTE_PARITY',sum(counts.values()),len(bad));print(bad[:5])
if __name__=='__main__':main()
