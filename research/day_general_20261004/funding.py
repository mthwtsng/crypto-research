"""Limited causal funding flags, not a certification of independent beneficial owners."""
import collections,concurrent.futures,json,datetime
import collect as N

def wallet(item):
 w,bt=item;cfg=dict(transactionDetails='full',encoding='jsonParsed',maxSupportedTransactionVersion=1,sortOrder='desc',limit=40,commitment='finalized',filters=dict(status='succeeded',blockTime=dict(gte=bt-600,lt=bt)));r=N.rpc('getTransactionsForAddress',[w,cfg]);inflows=[]
 for tx in r['data']:
  if tx['blockTime']>=bt:continue
  ixs=tx['transaction']['message']['instructions']+[ix for g in tx['meta'].get('innerInstructions',[])or[] for ix in g['instructions']]
  for ix in ixs:
   parsed=ix.get('parsed')
   if ix.get('programId')!='11111111111111111111111111111111'or not isinstance(parsed,dict)or parsed.get('type')not in['transfer','transferWithSeed']:continue
   a=parsed.get('info',{})
   if a.get('destination')==w and int(a.get('lamports',0))>=30_000_000:inflows.append(dict(source=a.get('source'),sol=int(a['lamports'])/1e9,seconds_before_first_buy=bt-tx['blockTime'],signature=tx['transaction']['signatures'][0]))
 return dict(wallet=w,first_buy_time=bt,prior10min_receipts=len(r['data']),truncated=bool(r.get('paginationToken')),inflows=inflows)
def main():
 cs=json.loads((N.HERE/'COIN_MANIFEST.json').read_text());jobs={}
 for c in cs:
  q=min(c['signals'],key=lambda s:s['slot'])['quality']
  for w in q['top_buyers'][:8]:jobs[w['wallet']]=min(jobs.get(w['wallet'],w['first_buy_time']),w['first_buy_time'])
 (N.HERE/'FUNDING_FREEZE.json').write_text(json.dumps(dict(time=datetime.datetime.now(datetime.timezone.utc).isoformat(),addresses=len(jobs),method='Top8grossoutsidebuyersatfirstscreeneddecision; availableprior10minuteSOLtransfers>=.03SOL, strictblockTimebeforefirstbuy; mostrecent40successfulreceipts. Flagsnotexclusions,nofake-labelclaims,noPnlselection.'),indent=2))
 out=[]
 with concurrent.futures.ThreadPoolExecutor(4)as ex:
  fs={ex.submit(wallet,x):x for x in jobs.items()}
  for k,f in enumerate(concurrent.futures.as_completed(fs),1):
   try:z=f.result()
   except Exception as e:z=dict(wallet=fs[f][0],error=str(e),inflows=[])
   out.append(z)
   if k%40==0:print('funding',k,'/',len(jobs),flush=True)
 by={x['wallet']:x for x in out};cases=[]
 for c in cs:
  q=min(c['signals'],key=lambda s:s['slot'])['quality'];sources=collections.defaultdict(set)
  for w in q['top_buyers'][:8]:
   for tx in by[w['wallet']]['inflows']:
    if tx['seconds_before_first_buy']<=120:sources[tx['source']].add(w['wallet'])
  common=[dict(funder=f,buyers=sorted(ws),count=len(ws))for f,ws in sources.items()if len(ws)>=3];cases.append(dict(mint=c['mint'],shared_recent_funder_flags=common,checked_buyers=len(q['top_buyers'][:8]),caveat='Sharedsourcecanbeanexchange/relay; absenceofobservedfundingdoesnotprovenaturalvolume. Historicalqueriesonlyandreceiptcapgapsremain.'))
 (N.HERE/'FUNDING_AUDIT.json').write_text(json.dumps(dict(wallets=out,coins=cases),indent=2));print('funding done',len(out),'coinflags',sum(bool(c['shared_recent_funder_flags'])for c in cases),flush=True)
if __name__=='__main__':main()
