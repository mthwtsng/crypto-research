"""Resumable creation-first 21-day collection; no outcome-based replacements."""
import concurrent.futures,datetime,gzip,hashlib,importlib.util,json,pathlib,sys,time
import rpc_pool as R
P=R.OUT;ROOT=R.ROOT
sys.path.insert(0,str(ROOT/'research/day_general_20261004/helpers'))
spec=importlib.util.spec_from_file_location('validation_curve_prepare',ROOT/'research/day_general_20261004/prepare.py');PREP=importlib.util.module_from_spec(spec);spec.loader.exec_module(PREP)
AUTH='TSLvdd1pWpHVjahSpsvCXUbgwsL3JAcvokwaKt1eokM'
def history(address,start,end,status=None):
 token=None;rows={};seen=set()
 for page in range(500):
  filters=dict(blockTime=dict(gte=start,lt=end))
  if status:filters['status']=status
  cfg=dict(transactionDetails='full',encoding='jsonParsed',maxSupportedTransactionVersion=1,sortOrder='asc',limit=1000,commitment='finalized',filters=filters)
  if token:cfg['paginationToken']=token
  result=R.rpc('getTransactionsForAddress',[address,cfg])
  if not isinstance(result,dict) or not isinstance(result.get('data'),list):raise ValueError('invalid_history_envelope')
  for tx in result['data']:
   if tx.get('transactionIndex') is None:raise ValueError('missing_block_order')
   if not start<=tx['blockTime']<end:raise ValueError('history_time_filter_not_honored')
   rows[tx['transaction']['signatures'][0]]=tx
  token=result.get('paginationToken')
  if not token:return sorted(rows.values(),key=lambda t:(t['slot'],t['transactionIndex']))
  if token in seen:raise ValueError('pagination_cycle')
  seen.add(token)
 raise ValueError('history_page_cap')
def census(start):
 dest=P/'census'/(str(start)+'.json.gz')
 if dest.exists():return json.load(gzip.open(dest,'rt'))
 rows=history(AUTH,start,start+3600,'succeeded');creations={}
 for tx in rows:
  for c in PREP.decoder.creations(tx):creations[c['mint']]=dict(mint=c['mint'],creation=c,creation_time=tx['blockTime'],creation_slot=tx['slot'],signature=tx['transaction']['signatures'][0])
 out=dict(start=start,end=start+3600,complete=True,receipts=len(rows),creations=list(creations.values()));R.save(dest,out);return out

def curve(item):
 path=P/'raw_curves'/(item['mint']+'.json.gz')
 if path.exists():return dict(mint=item['mint'],status='cached')
 end=item['creation_time']+3600
 rows=history(item['creation']['bonding_curve'],item['creation_time'],end)
 if item['signature'] not in {t['transaction']['signatures'][0] for t in rows}:raise ValueError('creation_receipt_missing')
 R.save(path,dict(mint=item['mint'],creation_metadata=item['creation'],requested_end_time=end,decision_end_time=item['creation_time']+1800,transactions=rows))
 return dict(mint=item['mint'],status='collected',receipts=len(rows),failed_receipts=sum(t['meta']['err'] is not None for t in rows))

def main():
 fr=json.load(open(P/'FREEZE.json'));hours=[fr['start']+i*3600 for i in range(21*24)];cs=[];errors=[]
 for name in ['census','raw_curves']:(P/name).mkdir(exist_ok=True)
 with concurrent.futures.ThreadPoolExecutor(6) as ex:
  futures={ex.submit(census,start):start for start in hours}
  for f in concurrent.futures.as_completed(futures):
   try:cs.append(f.result())
   except Exception as e:errors.append(dict(hour=futures[f],error=str(e)))
   R.save(P/'PROGRESS.json',dict(stage='creation_census',completed_hours=len(cs),total_hours=len(hours),errors=errors,at=datetime.datetime.now(datetime.timezone.utc).isoformat()))
   if (len(cs)+len(errors))%12==0:print('CENSUS',len(cs),'/504','errors',len(errors),flush=True)
 if errors:raise RuntimeError('incomplete census; no sample/replay permitted')
 excluded=set(json.load(open(P/'EXCLUDED_PRIOR_MINTS.json')));chosen=[];ordinary=0
 for c in sorted(cs,key=lambda c:c['start']):
  candidates=[x for x in c['creations'] if x['mint'] not in excluded and x['creation'].get('quote_mint') in [None,'11111111111111111111111111111111','So11111111111111111111111111111111111112'] and not x['creation'].get('is_mayhem_mode',False) and not x['creation'].get('is_holder_reward',False)]
  ordinary+=len(candidates);chosen.extend(sorted(candidates,key=lambda x:hashlib.sha256((fr['seed']+x['mint']).encode()).hexdigest())[:20])
 selection=dict(chosen=chosen,total=len(chosen),ordinary_launches=ordinary,hours=504,selection='20fixed-hash ordinary creations per complete hour; no future volume/profit filters',dates=dict(__import__('collections').Counter(datetime.datetime.fromtimestamp(x['creation_time'],datetime.timezone.utc).date().isoformat() for x in chosen)))
 R.save(P/'CREATION_SAMPLE.json',selection);print('SELECTED',len(chosen),flush=True);done=[];errors=[]
 with concurrent.futures.ThreadPoolExecutor(8) as ex:
  futures={ex.submit(curve,item):item for item in chosen}
  for f in concurrent.futures.as_completed(futures):
   try:done.append(f.result())
   except Exception as e:errors.append(dict(mint=futures[f]['mint'],error=str(e)))
   if (len(done)+len(errors))%25==0:
    R.save(P/'PROGRESS.json',dict(stage='curve_receipts',selected=len(chosen),collected=len(done),errors=errors,at=datetime.datetime.now(datetime.timezone.utc).isoformat()));print('CURVES',len(done),'/',len(chosen),'errors',len(errors),flush=True)
 R.save(P/'COLLECTION_COMPLETE.json',dict(selected=len(chosen),done=done,errors=errors));assert not errors,'Repair missing receipts before replay'
 R.save(P/'PROGRESS.json',dict(stage='curve_receipts_complete',selected=len(chosen),collected=len(done),errors=[],next='custody repair, instruction binding, signal detection, migration continuation, then approved replay'))
 print('COLLECTION_COMPLETE',len(done),flush=True)
if __name__=='__main__':main()
