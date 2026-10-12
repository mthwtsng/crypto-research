"""Recover missing public failed intents for every frozen eligible curve.

These are coverage evidence, not assumed fills or invented private retries.
Failed source orders can change outcome under counterfactual reserves and must
be examined before declaring an unchanged historical migration path feasible.
"""
import concurrent.futures,gzip,json,pathlib
import collect_continuations as C
P=pathlib.Path(__file__).resolve().parent

def run(job):
 out=P/'failed_curve_intents'/(job['mint']+'.json.gz')
 if out.exists():return json.load(gzip.open(out,'rt'))['audit']
 token=None;seen=set();rows=[];end=job['latest_signal_time']+1800
 for page in range(200):
  # Alchemy rejects status="failed". Collect all landed statuses and retain
  # failed receipts locally, with the same provider's pagination cursor.
  cfg=dict(transactionDetails='full',encoding='jsonParsed',maxSupportedTransactionVersion=1,commitment='finalized',sortOrder='asc',limit=1000,filters=dict(blockTime=dict(lte=end)))
  if token:cfg['paginationToken']=token
  r=C.request('getTransactionsForAddress',[job['curve'],cfg]);rows.extend(t for t in r['data'] if t['meta']['err'] is not None);nxt=r.get('paginationToken')
  if not nxt:break
  if nxt in seen:raise ValueError('pagination_cycle')
  token=nxt;seen.add(token)
 else:raise ValueError('history_cap')
 rows=list({t['transaction']['signatures'][0]:t for t in rows}.values())
 if any(t.get('transactionIndex') is None or t['meta']['err'] is None for t in rows):raise ValueError('failed_receipt_order_or_status')
 rows.sort(key=lambda t:(t['slot'],t['transactionIndex']))
 audit=dict(mint=job['mint'],curve=job['curve'],through_time=end,receipts=len(rows),complete=True,pages=page+1,scope='all public landed-failed receipts touching curve; not expired private sends or proof they would fill counterfactually')
 C.RPC.save(out,dict(audit=audit,transactions=rows));return audit

def main():
 jobs=json.loads((P/'CONTINUATION_SELECTION.json').read_text())['jobs'];audits=[];errors=[]
 with concurrent.futures.ThreadPoolExecutor(2) as ex:
  fs={ex.submit(run,j):j for j in jobs}
  for f in concurrent.futures.as_completed(fs):
   try:
    a=f.result();audits.append(a);print('FAILED_INTENTS',a['mint'][:8],a['receipts'],flush=True)
   except Exception as e:errors.append(dict(mint=fs[f]['mint'],error=str(e)));print('ERROR',errors[-1],flush=True)
   C.RPC.save(P/'FAILED_INTENT_PROGRESS.json',dict(total=len(jobs),audits=audits,errors=errors))
 C.RPC.save(P/'FAILED_INTENT_COMPLETE.json',dict(total=len(jobs),audits=audits,errors=errors));print('COMPLETE',len(audits),len(errors),flush=True)
if __name__=='__main__':main()
