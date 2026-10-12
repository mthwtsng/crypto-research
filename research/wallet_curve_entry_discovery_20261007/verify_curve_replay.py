"""No-intervention full-prefix state/custody/recorded-limit parity."""
import collections,gzip,json,pathlib
import curve_adapter as A
P=pathlib.Path(__file__).resolve().parent

def main():
 audits=[];errors=[]
 for f in sorted((P/'bound_curve_tapes').glob('*.gz')):
  t=json.load(gzip.open(f,'rt'));first=next(e for g in t['groups'] for e in g['events']);q,n=first['sol_raw'],first['tokens_raw'];d=1 if first['buy'] else -1
  st=dict(vsol_raw=first['vsol_raw']-d*q,vtokens_raw=first['vtokens_raw']+d*n,rsol_raw=first['rsol_raw']-d*q,rtokens_raw=first['real_token_reserves']+d*n,fee_bps=first['fee_bps'],creator_fee_bps=first['creator_fee_bps']);h={};cf={};done=0
  for g in t['groups']:
   z,hh,cc,gg,err=A.apply(st,g,h,cf)
   expected=g['state'];keys=['vsol_raw','vtokens_raw','rsol_raw','rtokens_raw']
   if err or gg.get('counterfactual_revert') or any(z[k]!=expected[k] for k in keys) or hh!=cc:
    errors.append(dict(mint=t['mint'],signature=g['signature'],reason=err or gg.get('counterfactual_revert') or 'state_or_custody_parity',expected={k:expected[k] for k in keys},actual={k:z[k] for k in keys}));break
   st,h,cf=z,hh,cc;done+=1
  audits.append(dict(mint=t['mint'],groups_checked=done,total_groups=len(t['groups']),pass_all=done==len(t['groups'])))
 result=dict(audits=audits,errors=errors,groups_checked=sum(r['groups_checked'] for r in audits));(P/'CURVE_REPLAY_PARITY.json').write_text(json.dumps(result,indent=2)+'\n');print('SOURCE_PARITY',result['groups_checked'],'errors',len(errors));print(errors[:3])
if __name__=='__main__':main()
