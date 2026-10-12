"""Merge landed outcomes in canonical order and retain account-level custody.

Failed receipt inner instructions describe attempted execution, not committed
token movements. Historical failed groups remain no-ops; their intents are
retained for a separately checked counterfactual executor.
"""
import collections,gzip,json,pathlib
import bind_curve_limits as B
import curve_adapter as A
import receipt_custody as C
P=pathlib.Path(__file__).resolve().parent

def failed_intents(tx,mint):
 top=tx['transaction']['message']['instructions'];inner={x['index']:x['instructions'] for x in tx['meta'].get('innerInstructions',[]) or []};rows=[]
 for k,ix in enumerate(top):
  for sub,a in [(-1,ix)]+list(enumerate(inner.get(k,[]))):
   if a.get('programId')!=B.D.PUMP:continue
   raw=B.raw(a.get('data',''));definition=B.I.get(raw[:8])
   if not definition or definition['name'] not in B.TRADE or mint not in a.get('accounts',[]):continue
   if len(raw)<24:raise ValueError('short_failed_trade_instruction')
   name=definition['name'];v=[int.from_bytes(raw[o:o+8],'little') for o in (8,16)]
   # The published account schema is required. Hash-only instruction-name
   # recognition cannot establish signer/custody mappings.
   schema=next((d for d in B.D.IDL['instructions'] if d['name']==name),None)
   accounts={d['name']:ac for d,ac in zip(schema['accounts'],a['accounts'])} if schema else None
   rows.append(dict(instruction=name,top_index=k,inner_index=sub,parent_program=ix.get('programId'),args=v,accounts=accounts))
 return rows

def account_group(g,tx,mint):
 custody=C.parse_receipt(tx,g['events'],mint);bindings={b['event_index']:b for b in custody['trade_bindings']};ops=[]
 for tr in custody['transfers']:
  if tr['trade_event_indices']:
   for i in tr['trade_event_indices']:
    b=bindings[i];ops.append(dict(kind='trade',event=g['events'][i],owner=b['trader_token_account'],inventory_owner=b['inventory_owner'],order=tr['order']))
  else:
   # Preserve same-owner transfers between distinct token accounts.
   ops.append(dict(kind='transfer',from_owner=tr['source_account'],to_owner=tr['destination_account'],raw=tr['raw'],order=tr['order']))
 if len(bindings)!=len(g['events']):raise ValueError('missing_trade_account_binding')
 ops.sort(key=lambda op:tuple(op['order']))
 return dict(g,custody_ops=ops,account_owners={ac:r.get('owner') for ac,r in custody['accounts'].items()},tokenpre={ac:r.get('pre_raw',0) for ac,r in custody['accounts'].items()},tokenpost={ac:r.get('post_raw',0) for ac,r in custody['accounts'].items()},custody_issues=custody['issues'],source_status='succeeded')

def prepare(f):
 t=json.load(gzip.open(f,'rt'));mint=t['mint'];raw=P/'custody/custody_extended'/f.name
 if not raw.exists():raw=P/'custody_inputs'/f.name
 source=json.load(gzip.open(raw,'rt'));by={tx['transaction']['signatures'][0]:tx for tx in source['transactions']};failed=json.load(gzip.open(P/'failed_curve_intents'/f.name,'rt'))['transactions']
 groups=[account_group(g,by[g['signature']],mint) for g in t['groups']]
 for tx in failed:
  if (tx['slot'],tx['transactionIndex'])<(t['groups'][0]['slot'],t['groups'][0]['index']):continue
  groups.append(dict(signature=tx['transaction']['signatures'][0],slot=tx['slot'],index=tx['transactionIndex'],block_time=tx['blockTime'],events=[],custody_ops=[],source_status='failed',source_error=tx['meta']['err'],source_network_fee=tx['meta']['fee'],failed_intents=failed_intents(tx,mint),log_messages=tx['meta'].get('logMessages',[]),message=tx['transaction']['message'],pre_balances=tx['meta']['preBalances'],post_balances=tx['meta']['postBalances'],token_pre_balances=tx['meta'].get('preTokenBalances',[])))
 groups.sort(key=lambda g:(g['slot'],g['index']));seen=set();st=None;h={};cf={};error=None;checked=0;owners={}
 for g in groups:
  if g['signature'] in seen:raise ValueError('duplicate_source_signature')
  seen.add(g['signature'])
  if g['source_status']=='failed':
   if st is None:raise ValueError('failed_before_creation')
   g['state']=dict(st);continue
  owners.update(g['account_owners'])
  if st is None:
   first=next(iter(g['events']),None)
   if first:
    q,n=first['sol_raw'],first['tokens_raw'];d=1 if first['buy'] else -1;st=dict(vsol_raw=first['vsol_raw']-d*q,vtokens_raw=first['vtokens_raw']+d*n,rsol_raw=first['rsol_raw']-d*q,rtokens_raw=first['real_token_reserves']+d*n,fee_bps=first['fee_bps'],creator_fee_bps=first['creator_fee_bps'])
   else:st=dict(g['state'])
  original=g['state'];z,hh,cc,adjusted,err=A.apply(st,g,h,cf)
  if err or adjusted.get('counterfactual_revert') or hh!=cc or any(z[k]!=original[k] for k in ('vsol_raw','vtokens_raw','rsol_raw','rtokens_raw')):
   error=dict(signature=g['signature'],reason=err or adjusted.get('counterfactual_revert') or 'state_or_custody_mismatch');break
  st,h,cf=z,hh,cc;checked+=1
 result=dict(t,groups=groups,inventory_key='token_account',account_owners=owners)
 with gzip.open(P/'merged_account_tapes'/f.name,'wt',compresslevel=1) as out:json.dump(result,out)
 return dict(mint=mint,successful_groups=len(t['groups']),failed_groups=sum(g['source_status']=='failed' for g in groups),account_groups_checked=checked,error=error,account_parity_pass=error is None,intents=sum(len(g.get('failed_intents',[])) for g in groups))

def main():
 (P/'merged_account_tapes').mkdir(exist_ok=True);audits=[];errors=[]
 for f in sorted((P/'bound_curve_tapes').glob('*.gz')):
  try:a=prepare(f);audits.append(a);print('MERGED',a['mint'][:8],a['account_parity_pass'],a['error'],flush=True)
  except Exception as e:errors.append(dict(file=f.name,error=str(e)));print('ERROR',errors[-1],flush=True)
 result=dict(audits=audits,errors=errors,scope='canonical receipt merge and historical token-account source parity, not counterfactual failed-order or migration execution')
 (P/'MERGED_ACCOUNT_PARITY.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
