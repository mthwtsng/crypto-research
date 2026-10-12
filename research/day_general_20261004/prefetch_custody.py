"""Recover every gap in a completed source-audit batch, without replay outcomes."""
import concurrent.futures,json
import collect as N
import repair_helpers as R
R.HERE=N.HERE/'custody_repair';R.HERE.mkdir(exist_ok=True);R.rpc=N.rpc;R.save=N.save
au=json.loads((N.HERE/'PREPARE_AUDIT.json').read_text());wanted=[a['mint']for a in au if a.get('custody_gap')and a.get('normal')]
old=json.loads((N.HERE/'PREFETCH_CUSTODY.json').read_text())if(N.HERE/'PREFETCH_CUSTODY.json').exists()else[]
wanted=[m for m in wanted if m not in {x['mint']for x in old}]
print('gap recovery batch',len(au),'sources',len(wanted),'gaps',flush=True);out=list(old)
with concurrent.futures.ThreadPoolExecutor(3)as ex:
 fs={ex.submit(R.one,N.HERE/'extended'/(m+'.json.gz')):m for m in wanted}
 for f in concurrent.futures.as_completed(fs):
  try:a=f.result()
  except Exception as e:a=dict(mint=fs[f],error=str(e))
  out.append(a);print('recovered',len(out),'/',len(wanted),a.get('status',a.get('error')),flush=True)
(N.HERE/'PREFETCH_CUSTODY.json').write_text(json.dumps(out,indent=2))
