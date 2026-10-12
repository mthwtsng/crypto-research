"""Complete-group no-intervention custody and pool state parity after repairs."""
import gzip,json,pathlib
import amm_counterparty as C
P=pathlib.Path(__file__).resolve().parent
def main():
 audits=[]
 for f in sorted((P/'normalized_amm_tapes').glob('*.gz')):
  t=json.load(gzip.open(f,'rt'));gs=t['groups'];st=dict(gs[0]['state']);h={};cf={};errors=[];checked=0
  # Genesis is authenticated as one atomic migration group, before the first
  # tradable AMM boundary. Its vault deposit is validated by the bridge audit.
  for g in gs[1:]:
   z,hh,cc,err=C.advance(st,g,h,cf)
   if err or any(z[k]!=g['state'][k] for k in ('base','quote','virtual','supply')) or hh!=cc or z.get('source_reverts',0):
    errors.append(dict(signature=g['signature'],reason=err or 'state_or_custody_mismatch',expected=g['state'],actual=z));break
   st,h,cf=z,hh,cc;checked+=1
  audits.append(dict(pool=t['pool'],mint=t['mint'],checked_groups=checked,total_groups=len(gs)-1,errors=errors,pass_all=checked==len(gs)-1));print('AMM_FULL_PARITY',t['mint'][:8],checked,len(errors),flush=True)
 (P/'AMM_COUNTERPARTY_PARITY.json').write_text(json.dumps(dict(audits=audits,scope='whole source replay from authenticated post-migration genesis, no own intervention'),indent=2)+'\n')
if __name__=='__main__':main()
