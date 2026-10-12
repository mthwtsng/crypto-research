"""Recover reviewed historical AMM parser edits without launching old studies.
Run from the repository root. Source history is local; exact IDL/SDK provenance
is stored in grace_verification_cycle/RESTORATION.json.
"""
import json,pathlib,re
ROOT=pathlib.Path.cwd();DEST=ROOT/'research/amm_multiday_20261006';p=DEST/'prepare.py'
H='/home/mthwt/.codex/sessions/2026/10/03/rollout-2026-10-03T11-34-59-01a1030c-49d3-7f00-8d62-633d7e9be6ec.jsonl'
def patch(z):
 for c in z.split('*** Update File: ')[1:]:
  if c.splitlines()[0]!=str(p):continue
  s=p.read_text()
  for h in c.split('\n@@')[1:]:
   old=[];new=[]
   for l in h.splitlines()[1:]:
    if l.startswith('***'):break
    if l.startswith((' ','-')):old.append(l[1:])
    if l.startswith((' ','+')):new.append(l[1:])
   a='\n'.join(old)+'\n';b='\n'.join(new)+'\n'
   if a not in s:
    lines=s.splitlines(keepends=True);n=len(old);start=next((k for k in range(len(lines)-n+1) if [z.strip() for z in lines[k:k+n]]==[z.strip() for z in old]),None)
    assert start is not None,('missing patch',a[:70])
    a=''.join(lines[start:start+n])
   s=s.replace(a,b,1)
  p.write_text(s)
for i,line in enumerate(open(H)):
 if i>4700:break
 x=json.loads(line).get('payload',{});text=x.get('input','')
 if x.get('type')!='custom_tool_call':continue
 for m in re.finditer(r'(cmd:|apply_patch\()\s*(")',text):
  cmd=json.JSONDecoder().raw_decode(text[m.start(2):])[0]
  if m[1]=='apply_patch(':
   if i!=4034:patch(cmd)
   continue
  if i==3763:
   a=re.search(r"cat > research/amm_multiday_20261006/prepare.py <<'PY'\n(.*?)\nPY",cmd,re.S);p.write_text(a[1]+'\n')
  if i in [3789,3835,3981,3990,4176,4292,4301]:
   a=re.search(r"python3 - <<'PY'\n(.*?)\nPY",cmd,re.S)
   if not a:continue
   code=a[1]
   if i in [3789,3835,3981,4176,4292,4301] and not code.startswith(("p='research/amm_multiday_20261006/prepare.py'",'from pathlib import Path')):continue
   if i==3981:code=code.split("p='research/amm_multiday_20261006/opportunity.py'")[0]
   if i==3990 and "p='research/amm_multiday_20261006/prepare.py'" not in code:continue
   if i==3990:code="p='research/amm_multiday_20261006/prepare.py'"+code.split("p='research/amm_multiday_20261006/prepare.py'")[1]
   if i==4176:code=code.split('\nimport sys')[0]
   if i==4301:code=code.split('\nimport sys,pathlib,json,gzip')[0]
   exec(compile(code,f'history-{i}','exec'),{})
s=p.read_text().replace("SPEC=json.loads((P.parent/'amm_strategy_discovery_20261006/EXPERIMENT_SPEC.json').read_text())","# Original standalone entry-discovery SPEC was unused by this parser.")
p.write_text(s)
print('prepare restored',len(s),'bytes')
