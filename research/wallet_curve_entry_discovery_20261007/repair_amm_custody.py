"""Recover temporary base-token-account transfers omitted by old AMM parsing.

Vault moves are reserve operations. Trade accounts and checked-mint transfers
authenticate transient accounts absent from RPC pre/post token balance arrays.
Do not infer unrelated mint ownership from wallet addresses.
"""
import collections,gzip,importlib.util,json,pathlib,sys
P=pathlib.Path(__file__).resolve().parent;ROOT=P.parents[1]
sys.path.insert(0,str(ROOT/'research/amm_multiday_20261006'))
spec=importlib.util.spec_from_file_location('source_amm_prepare',ROOT/'research/amm_multiday_20261006/prepare.py');B=importlib.util.module_from_spec(spec);spec.loader.exec_module(B)
TOKENS={'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA','TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb'}

def custody(tx,m,tr,g):
 inner={x['index']:x['instructions'] for x in tx['meta'].get('innerInstructions',[]) or []};ordered=[]
 for k,outer in enumerate(tx['transaction']['message']['instructions']):ordered.extend([outer]+inner.get(k,[]))
 known=set(g['tokenpre'])|set(g['tokenpost'])|{e['account'] for e in tr}
 transfers=[]
 for ix in ordered:
  if ix.get('programId') not in TOKENS:continue
  parsed=ix.get('parsed',{});info=parsed.get('info',{}) if isinstance(parsed,dict) else {};kind=parsed.get('type') if isinstance(parsed,dict) else None
  if kind not in {'transfer','transferChecked','burn','burnChecked'}:continue
  src=info.get('source',info.get('account'));dst=info.get('destination');mint=info.get('mint')
  if mint and mint!=m['mint']:continue
  if mint==m['mint']:known.update(ac for ac in [src,dst] if ac)
  transfers.append((src,dst,info))
 # Unchecked transfers inherit the authenticated token mint of their connected
 # account. Token-program transfers cannot connect accounts of different mints.
 changed=True
 while changed:
  changed=False
  for src,dst,_ in transfers:
   if src in known or dst in known:
    for ac in [src,dst]:
     if ac and ac not in known:known.add(ac);changed=True
 ops=[];ti=0;err=None;sweeps=collections.deque(e for e in g.get('raw_events',[]) if e['kind']=='ObservedFeeSweepEvent')
 for ix in ordered:
  method=B.METHODS.get(B.b58decode(ix.get('data',''))[:8]) if ix.get('programId')==B.A.AMM else None
  if method in {'sweep_protocol_fee','sweep_coin_creator_fee','sweep_creator_fee'} and m['pool'] in ix.get('accounts',[]):
   creator=method!='sweep_protocol_fee';match=next((e for e in sweeps if e['creator']==creator),None)
   if match is not None:ops.append(dict(kind='sweep',raw=match['amount']));sweeps.remove(match)
   continue
  if method in {'buy','buy_v2','buy_exact_quote_in','buy_exact_quote_in_v2','sell','sell_v2','boost_buy_and_burn'} and m['pool'] in ix.get('accounts',[]):
   if ti>=len(tr):err='trade_instruction_event_count';continue
   ops.append(dict(kind='trade',event=tr[ti]));ti+=1;continue
  if ix.get('programId') not in TOKENS:continue
  parsed=ix.get('parsed',{});info=parsed.get('info',{}) if isinstance(parsed,dict) else {};kind=parsed.get('type') if isinstance(parsed,dict) else None
  if kind not in {'transfer','transferChecked','burn','burnChecked'}:continue
  src=info.get('source',info.get('account'));dst=info.get('destination')
  if info.get('mint') and info['mint']!=m['mint']:continue
  if src not in known and dst not in known:continue
  if src==m['base_vault'] or dst==m['base_vault']:continue
  n=int(info.get('amount',info.get('tokenAmount',{}).get('amount',0)));ops.append(dict(kind='transfer' if dst else 'burn',source=src,destination=dst,raw=n))
 if ti!=len(tr):err='trade_instruction_event_count'
 if sweeps:err='sweep_instruction_event_count'
 balances=dict(g['tokenpre'])
 for op in ops:
  if op['kind']=='sweep':continue
  if op['kind']=='trade':
   e=op['event'];ac=e['account']
   if e['zero_fee'] and ac=='11111111111111111111111111111111':continue
   balances.setdefault(ac,0)
   if balances[ac]!=e['prehold']:err='custody_prehold_mismatch'
   balances[ac]+=e['n'] if e['buy'] else -e['n']
  else:
   src,dst=op['source'],op['destination'];balances[src]=balances.get(src,0)-op['raw']
   if balances[src]<0:err='negative_custody'
   if dst:balances[dst]=balances.get(dst,0)+op['raw']
 for ac,n in g['tokenpost'].items():
  if ac!=m['base_vault'] and balances.get(ac,0)!=n:err='custody_post_mismatch'
 return ops,err

def main():
 (P/'repaired_amm_tapes').mkdir(exist_ok=True);audits=[]
 for f in sorted((P/'amm_tapes').glob('*.gz')):
  t=json.load(gzip.open(f,'rt'));oldbad=sum(bool(g['custody_error']) for g in t['groups']);needed={g['signature'] for g in t['groups'] if g['custody_error'] or g['signature']==t['migration']['signature']};receipts={}
  # Stream large raw pool histories to keep this repair's memory bounded.
  import ijson
  with gzip.open(P/'continuation_pools'/f.name,'rb') as src:
   for tx in ijson.items(src,'transactions.item'):
    sig=tx['transaction']['signatures'][0]
    if sig in needed:receipts[sig]=tx
  for g in t['groups']:
   if g['signature'] not in needed:continue
   tx=receipts[g['signature']];g['raw_events']=B.A.events(tx);g['custody_ops'],g['custody_error']=custody(tx,t['migration'],g['trades'],g);g.pop('raw_events',None)
  remaining=[dict(signature=g['signature'],reason=g['custody_error']) for g in t['groups'] if g['custody_error']]
  with gzip.open(P/'repaired_amm_tapes'/f.name,'wt',compresslevel=1) as out:json.dump(t,out)
  audit=dict(pool=t['pool'],mint=t['mint'],groups=len(t['groups']),previous_custody_gaps=oldbad,remaining_custody_gaps=remaining);audits.append(audit);print('AMM_CUSTODY',t['mint'][:8],oldbad,len(remaining),flush=True)
 (P/'AMM_CUSTODY_REPAIR.json').write_text(json.dumps(dict(audits=audits),indent=2)+'\n')
if __name__=='__main__':main()
