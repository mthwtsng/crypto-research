"""Stop on target signal count, never on PnL; completed deterministic hash batches."""
import gzip,json,pickle,time,datetime,hashlib
import collect as N
import screen as S
fr=json.loads((N.HERE/'FREEZE.json').read_text());sample=json.loads((N.HERE/'CREATION_SAMPLE.json').read_text())['chosen'];aud=[];out=[];pos=0
for limit in range(100,len(sample)+100,100):
 limit=min(limit,len(sample))
 for c in sample[pos:limit]:
  fp=N.HERE/'extended'/(c['mint']+'.json.gz')
  while not fp.exists():time.sleep(2)
  try:
   for attempt in range(30):
    try:
     d=json.load(gzip.open(fp,'rt'));break
    except (EOFError,OSError,ValueError):
     if attempt==29:raise
     time.sleep(.25)
   t,a=N.P.make(d)
  except Exception as e:
   print('source exception',c['mint'],str(e),flush=True);t=None;a=dict(mint=c['mint'],error=str(e))
  if t:t['source']='independent_recent_mint_authority_census';t['creation_metadata']=c['creation'];out.append(t)
  aud.append(a)
 pos=limit;triggered=sum(bool(S.detect(t))for t in out if t['normal']);print('PREFIX',limit,'triggered',triggered,flush=True)
 if triggered>=fr['target_triggered_coins']or limit==len(sample):
  with gzip.open(N.HERE/'TAPES.pkl.gz','wb')as f:pickle.dump(out,f)
  (N.HERE/'PREFIX_PREPARE_AUDIT.json').write_text(json.dumps(aud,indent=2));(N.HERE/'PREFIX_FREEZE.json').write_text(json.dumps(dict(time=datetime.datetime.now(datetime.timezone.utc).isoformat(),source_prefix=limit,prepared=len(out),triggered_before_pnl=triggered,sampling='Earliest completed100source hash batch reaching40causallyscreenedtriggercoins; atmost1000sources, no PnLread',source_sha256=hashlib.sha256((N.HERE/'TAPES.pkl.gz').read_bytes()).hexdigest(),mints=[c['mint']for c in sample[:limit]]),indent=2));print('PREFIX SEALED',limit,triggered,flush=True);break
