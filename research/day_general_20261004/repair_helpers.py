import collections,gzip,json,pathlib
from collect import rpc,save
from prepare import make,group,C
HERE=pathlib.Path(__file__).resolve().parent
def gap(t):
 h=collections.Counter()
 for g in t['groups']:
  for op in g['custody_ops']:
   if op['kind']=='trade':
    e=op['event'];w=op['owner'];need=0 if e['buy'] else e['tokens_raw']
    if h[w]<need:return g,w,op
    h[w]+=e['tokens_raw'] if e['buy'] else -need
   else:
    w=op['from_owner']
    if h[w]<op['raw']:return g,w,op
    h[w]-=op['raw'];h[op['to_owner']]+=op['raw']
 return None


def one(fp):
 d=json.load(gzip.open(fp,'rt'));mint=d['mint'];dst=HERE/'custody_extended'/fp.name;audit=dict(mint=mint,passes=[],status='unchanged');t,a=make(d)
 if not t or not t['normal']:return audit
 originals={x['transaction']['signatures'][0]:x for x in d['transactions']}
 for _ in range(30):
  bad=gap(t)
  if not bad:audit['status']='supported';break
  g,w,op=bad;tx=originals[g['signature']];parsed=C.parse_receipt(tx,g['events'],mint)
  accts={k for k,a in parsed['accounts'].items() if a.get('owner')==w and a.get('mint')==mint}
  accts.update(b['trader_token_account'] for b in parsed['trade_bindings'] if b['inventory_owner']==w)
  if not accts:audit['status']='partial';audit['issue']='no bound token account';break
  added=[]
  for acct in accts:
   token=None
   for page in range(10):
    cfg=dict(transactionDetails='full',encoding='jsonParsed',maxSupportedTransactionVersion=1,sortOrder='asc',limit=1000,filters={'status':'succeeded','blockTime':{'gte':t['creation_time']-2,'lte':g['block_time']+1}})
    if token:cfg['paginationToken']=token
    r=rpc('getTransactionsForAddress',[acct,cfg])
    for z in r['data']:
     sig=z['transaction']['signatures'][0]
     if z['slot']<t['creation_slot'] or z.get('blockTime',0)>d['requested_end_time']:continue
     if sig not in originals:originals[sig]=z;added.append(sig)
    new=r.get('paginationToken')
    if not new:break
    if new==token:raise ValueError('pagination loop')
    token=new
   else:raise ValueError('account history cap')
  audit['passes'].append(dict(signature=g['signature'],owner=w,accounts=sorted(accts),added=added))
  if not added:audit['status']='partial';break
  d['transactions']=list(originals.values());t,a=make(d)
  if t is None:audit['status']='partial';break
 else:audit['status']='partial'
 if audit['passes']:save(dst,d)
 return audit
