"""Restore exact historical dependency source, without running historical studies.

Only whitelisted source heredocs, source-edit statements and patches are applied.
RPC collection, experiment runs and unrelated historical commands are excluded.
"""
import ast,hashlib,json,pathlib,re
ROOT=pathlib.Path(__file__).resolve().parents[2]
HISTORY=pathlib.Path('/home/mthwt/.codex/sessions/2026/10/03/rollout-2026-10-03T11-34-59-01a1030c-49d3-7f00-8d62-633d7e9be6ec.jsonl')
TARGETS={'amm_adapter.py','opportunity.py','collect.py'}
DEST=ROOT/'research/amm_multiday_20261006';DEST.mkdir(exist_ok=True)
records=[]
def record(i,p):records.append(dict(history_line_0based=i,file=str(p.relative_to(ROOT))))
def patch(s,i):
 for chunk in s.split('*** Update File: ')[1:]:
  name=chunk.split('\n',1)[0];p=pathlib.Path(name)
  if p.parent!=DEST or p.name not in TARGETS:continue
  text=p.read_text()
  for h in chunk.split('\n@@')[1:]:
   lines=h.splitlines()[1:];old=[];new=[]
   for l in lines:
    if l.startswith('***'):break
    if l.startswith((' ','-')):old.append(l[1:])
    if l.startswith((' ','+')):new.append(l[1:])
   a='\n'.join(old)+'\n';b='\n'.join(new)+'\n'
   if a not in text:raise ValueError(('patch context absent',i,p.name,a))
   text=text.replace(a,b,1)
  p.write_text(text);record(i,p)
for i,line in enumerate(HISTORY.open()):
 if i>4700:break
 x=json.loads(line).get('payload',{});s=x.get('input','')
 if x.get('type')!='custom_tool_call':continue
 m=re.search(r'(?:cmd:|apply_patch\()\s*(")',s)
 if not m:continue
 cmd=json.JSONDecoder().raw_decode(s[m.start(1):])[0]
 if 'apply_patch(' in s:patch(cmd,i);continue
 for m in re.finditer(r"cat > (research/amm_multiday_20261006/[^\s]+) <<'PY'\n(.*?)\nPY(?:\n|$)",cmd,re.S):
  p=ROOT/m[1]
  if p.name in TARGETS:p.write_text(m[2]+'\n');record(i,p)
 if i in [3691,3700,3735,3763,3817,3990,4109,4184]:
  code=re.search(r"python3 - <<'PY'\n(.*?)\nPY",cmd,re.S)[1]
  if i==3990:code=code.split("p='research/amm_multiday_20261006/prepare.py'")[0]
  # These reviewed blocks only edit whitelisted source files. No imports of
  # restored files or historical experiment/RPC calls are executed.
  exec(compile(code,f'history-line-{i}','exec'),{})
  record(i,DEST/('collect.py' if i in [3700,3817] else 'opportunity.py' if i in [4109,4184] else 'amm_adapter.py'))
 if i==4471:
  p=DEST/'amm_adapter.py';p.write_text(p.read_text().replace("R/'research/automated_wallet_expansion_20261006/OFFICIAL_PUMP_AMM_IDL.json'","P/'official/SOURCE_PUMP_AMM_IDL.json'"));record(i,p)
out=ROOT/'research/core_gap_refinement_20261007/grace_verification_cycle/RESTORATION.json'
out.write_text(json.dumps(dict(history=str(HISTORY),edits=records,hashes={str((DEST/n).relative_to(ROOT)):hashlib.sha256((DEST/n).read_bytes()).hexdigest() for n in TARGETS}),indent=2)+'\n')
print('Restored',sorted(TARGETS),'from',len(records),'source-history edits')
