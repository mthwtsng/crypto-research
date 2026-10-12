"""Frozen authenticated receipt preparation, vendored without algorithm changes."""
import collections,datetime
import decoder
import receipt_custody as C
import build
def group(tx,mint):
 ev=[e for e in decoder.events(tx) if e['mint']==mint];p=C.parse_receipt(tx,ev,mint)
 ops=[];bindings={b['event_index']:b for b in p['trade_bindings']}
 for tr in p['transfers']:
  if tr['trade_event_indices']:
   for i in tr['trade_event_indices']:ops.append(dict(kind='trade',event=ev[i],owner=bindings[i]['inventory_owner'],order=tr['order']))
  elif tr['from_owner'] and tr['to_owner']:ops.append(dict(kind='transfer',from_owner=tr['from_owner'],to_owner=tr['to_owner'],raw=tr['raw'],order=tr['order']))
 for i,e in enumerate(ev):
  e['fee_bps']=e.get('fee_basis_points',0);e['creator_fee_bps']=e.get('creator_fee_basis_points',0)
  if i not in bindings:ops.append(dict(kind='trade',event=e,owner=e['user'],order=[999,i]))
 ops.sort(key=lambda o:tuple(o['order']))
 return dict(signature=tx['transaction']['signatures'][0],slot=tx['slot'],index=tx.get('transactionIndex'),block_time=tx['blockTime'],events=ev,custody_ops=ops,custody_issues=p['issues'])


def make(d):
 mint=d['mint'];txs=sorted(d['transactions'],key=lambda x:(x['slot'],x.get('transactionIndex',-1)));cre=[(tx,e) for tx in txs for e in decoder.creations(tx) if e['mint']==mint]
 if not cre:return None,dict(mint=mint,error='creation_missing')
 ctx,c=cre[0];gs=[];st=None
 for tx in txs:
  if tx['slot']<ctx['slot']:continue
  g=group(tx,mint)
  if not g['events'] and not g['custody_ops'] and tx['transaction']['signatures'][0]!=ctx['transaction']['signatures'][0]:continue
  if st is None and tx['transaction']['signatures'][0]==ctx['transaction']['signatures'][0]:
   st=dict(vsol_raw=c['virtual_sol_reserves'],vtokens_raw=c['virtual_token_reserves'],rsol_raw=0,rtokens_raw=c['real_token_reserves'],fee_bps=95,creator_fee_bps=c.get('creator_fee_bps',30))
  if g['events']:
   e=g['events'][-1];st=dict(vsol_raw=e['vsol_raw'],vtokens_raw=e['vtokens_raw'],rsol_raw=e['rsol_raw'],rtokens_raw=e['real_token_reserves'],fee_bps=e['fee_bps'],creator_fee_bps=e['creator_fee_bps'])
  if st is None:continue
  g['state']=dict(st);gs.append(g)
 normal=c.get('quote_mint') in [None,'11111111111111111111111111111111','So11111111111111111111111111111111111111112'] and not c.get('is_mayhem_mode',False) and not c.get('is_holder_reward',False)
 creation_i=next((i for i,g in enumerate(gs) if g['signature']==ctx['transaction']['signatures'][0]),None)
 if creation_i is None:return None,dict(mint=mint,error='no_creation_trade')
 gs=gs[creation_i:];h=collections.Counter();gap=None
 for i,g in enumerate(gs):
  try:h=build.inventory(gs[:i+1])
  except ValueError:gap=dict(index=i,signature=g['signature']);break
 t=dict(mint=mint,creator=c['user'],curve=c['bonding_curve'],creation_slot=ctx['slot'],creation_time=ctx['blockTime'],end_time=d['requested_end_time'],groups=gs,normal=normal,date=datetime.datetime.fromtimestamp(ctx['blockTime'],datetime.timezone.utc).date().isoformat(),source='extended317')
 return t,dict(mint=mint,groups=len(gs),normal=normal,custody_gap=gap,custody_issue_groups=sum(bool(g['custody_issues']) for g in gs),all_events_sol=all(e['quote_is_sol'] for g in gs for e in g['events']))
