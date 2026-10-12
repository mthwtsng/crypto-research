"""Count causal signal availability only; no PnL or winner labels."""
import gzip,json,pathlib
import collect as N
import screen as S
count=0;rules={};files=list((N.HERE/'extended').glob('*.json.gz'))
for f in files:
 t,a=N.P.make(json.load(gzip.open(f,'rt')))
 if not t or not t['normal']:continue
 sigs=S.detect(t)
 if sigs:
  count+=1
  for rule in {s['rule']for s in sigs}:rules[rule]=rules.get(rule,0)+1
print('cached sources',len(files),'causally screened trigger coins',count,'rules',rules,flush=True)
