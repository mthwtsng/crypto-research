"""Recover missing same-owner transfers at individual token-account level."""
import collections,concurrent.futures,gzip,json,pathlib,sys
P=pathlib.Path(__file__).resolve().parent/'fresh_oct05_oct06';OLD=P.parents[2]/'research/wallet_curve_entry_discovery_20261007';sys.path.insert(0,str(OLD));import repair_curve_custody as H,merge_curve_receipts as J,bind_curve_limits as B
H.P=P;H.H.HERE=P/'custody';B.P=P

def gap(groups):
 h=collections.Counter()
 for g in groups:
  for op in g['custody_ops']:
   if op['kind']=='trade':
    e=op['event'];w=op['owner'];h[w]+=e['tokens_raw'] if e['buy'] else -e['tokens_raw']
   else:w=op['from_owner'];h[w]-=op['raw'];h[op['to_owner']]+=op['raw']
   if h[w]<0:return g,w
 return None

def run(mint):
 f=P/'bound_curve_tapes'/(mint+'.json.gz');source=P/'custody/custody_extended'/f.name
 if not source.exists():source=P/'custody_inputs'/f.name
 d=json.load(gzip.open(source,'rt'));original={t['transaction']['signatures'][0]:t for t in d['transactions']};passes=[]
 for _ in range(30):
  t,_=H.B.make(d);t=H.curve_only(t);groups=[J.account_group(g,original[g['signature']],mint) for g in t['groups']];bad=gap(groups)
  if not bad:break
  g,acct=bad;token=None;added=[]
  for _ in range(20):
   cfg=dict(transactionDetails='full',encoding='jsonParsed',maxSupportedTransactionVersion=1,sortOrder='asc',limit=1000,commitment='finalized',filters=dict(status='succeeded',blockTime=dict(gte=t['creation_time']-2,lte=g['block_time']+1)))
   if token:cfg['paginationToken']=token
   r=H.rpc('getTransactionsForAddress',[acct,cfg])
   for tx in r['data']:
    sig=tx['transaction']['signatures'][0]
    if tx['slot']<t['creation_slot'] or tx['blockTime']>d['requested_end_time']:continue
    if sig not in original:original[sig]=tx;added.append(sig)
   nxt=r.get('paginationToken')
   if not nxt:break
   if nxt==token:raise ValueError('account_cursor_cycle')
   token=nxt
  else:raise ValueError('account_history_cap')
  passes.append(dict(signature=g['signature'],account=acct,added=added))
  if not added:raise ValueError(f'account_gap_no_missing_receipt:{acct}')
  d['transactions']=list(original.values())
 else:raise ValueError('account_repair_pass_cap')
 if passes:
  H.C.save(P/'custody/custody_extended'/f.name,d);H.C.save(P/'repaired_curve_tapes'/f.name,t)
 return dict(mint=mint,passes=passes,groups=len(groups))

def main():
 mints={s['mint'] for s in json.loads((P/'SIGNALS.json').read_text())};aud=[];errors=[]
 with concurrent.futures.ThreadPoolExecutor(2) as ex:
  fs={ex.submit(run,m):m for m in mints}
  for f in concurrent.futures.as_completed(fs):
   try:a=f.result();aud.append(a);print('ACCOUNT_SOURCE',len(aud),len(mints),a['mint'][:8],len(a['passes']),flush=True)
   except Exception as e:errors.append(dict(mint=fs[f],error=repr(e)));print('ERROR',errors[-1],flush=True)
 H.C.save(P/'ACCOUNT_CUSTODY_REPAIR.json',dict(audits=aud,errors=errors))
 if errors:raise ValueError('account_source_custody_errors')
 B.main()
 for mint in mints:
  f=P/'bound_curve_tapes'/(mint+'.json.gz');t=json.load(gzip.open(f,'rt'));source=P/'custody/custody_extended'/f.name
  if not source.exists():source=P/'custody_inputs'/f.name
  by={tx['transaction']['signatures'][0]:tx for tx in json.load(gzip.open(source,'rt'))['transactions']};t['groups']=[J.account_group(g,by[g['signature']],mint) for g in t['groups']];t['inventory_key']='token_account';H.C.save(P/'merged_account_tapes'/f.name,t)
if __name__=='__main__':main()
