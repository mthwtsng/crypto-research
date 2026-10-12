"""Exact observed-state transitions and outcome-independent finalized-order checks."""
import collections,concurrent.futures,hashlib,json,pickle,gzip
import collect as N
import screen as S

def main():
 ts=pickle.load(gzip.open(N.HERE/'TAPES.pkl.gz','rb'));parity=[];slots=collections.defaultdict(list)
 for t in ts:
  if not t['normal']:continue
  bad=[];checked=0;st=t['groups'][0]['state']
  for g in t['groups'][1:]:
   z,why=S.C.T.apply_fixed(st,g)
   if why:bad.append(dict(signature=g['signature'],reason=why));st=g['state'];continue
   errors={k:z[k]-g['state'][k]for k in ['vsol_raw','vtokens_raw','rsol_raw','rtokens_raw']};checked+=1
   if any(abs(errors[k])>1000 if k.endswith('sol_raw')else abs(errors[k])/max(1,g['state'][k])>1e-7 for k in errors):bad.append(dict(signature=g['signature'],error=errors))
   st=g['state']
  parity.append(dict(mint=t['mint'],checked=checked,material_errors=bad))
  for g in t['groups']:slots[g['slot']].append((t['mint'],g))
 selected=sorted(slots,key=lambda s:hashlib.sha256(('recent_order_v1'+str(s)).encode()).hexdigest())[:30];order=[]
 def block(slot):
  b=N.rpc('getBlock',[slot,dict(commitment='finalized',transactionDetails='signatures',rewards=False,maxSupportedTransactionVersion=1)]);pos={s:i for i,s in enumerate(b['signatures'])};missing=[];bad=[]
  grouped=collections.defaultdict(list)
  for mint,g in slots[slot]:grouped[mint].append(g)
  for mint,gs in grouped.items():
   if any(g['signature']not in pos for g in gs):missing.append(mint);continue
   idx=[pos[g['signature']]for g in gs]
   if idx!=sorted(idx):bad.append(mint)
  return dict(slot=slot,groups=len(slots[slot]),missing_mints=missing,reversed_mints=bad)
 with concurrent.futures.ThreadPoolExecutor(3)as ex:
  fs={ex.submit(block,s):s for s in selected}
  for f in concurrent.futures.as_completed(fs):
   try:order.append(f.result())
   except Exception as e:order.append(dict(slot=fs[f],error=str(e)))
 (N.HERE/'AUTHENTICATION.json').write_text(json.dumps(dict(transitions=parity,blocks=order),indent=2));print('AUTH',sum(p['checked']for p in parity),'transition material errors',sum(len(p['material_errors'])for p in parity),'block discrepancies',sum(len(b.get('missing_mints',[]))+len(b.get('reversed_mints',[]))for b in order),'block errors',sum('error'in b for b in order),flush=True)
if __name__=='__main__':main()
