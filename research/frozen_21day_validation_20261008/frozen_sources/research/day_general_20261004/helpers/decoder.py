"""Pump event decoder: successful invocation ancestry, official IDL, older tails allowed."""
import base64,json,pathlib,re,struct,hashlib
P=pathlib.Path(__file__).resolve().parent
IDL=json.loads((P/'OFFICIAL_PUMP_IDL.json').read_text());TYPES={t['name']:t['type'] for t in IDL['types']};PUMP=IDL['address'];ALPHABET='123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
def b58(raw):
 n=int.from_bytes(raw,'big');s=''
 while n:n,k=divmod(n,58);s=ALPHABET[k]+s
 return '1'*(len(raw)-len(raw.lstrip(b'\0')))+s
def decode(raw,name):
 pos=8
 def read(typ):
  nonlocal pos
  if typ=='pubkey':
   if pos+32>len(raw):raise ValueError('short pubkey')
   v=b58(raw[pos:pos+32]);pos+=32;return v
  if typ=='string':
   n=read('u32');v=raw[pos:pos+n].decode();pos+=n;return v
  if isinstance(typ,str) and typ in ['u64','i64','u32','u16','u8','bool']:
   fmt={'u64':'Q','i64':'q','u32':'I','u16':'H','u8':'B','bool':'?'}[typ];v=struct.unpack_from('<'+fmt,raw,pos)[0];pos+=struct.calcsize(fmt);return v
  if isinstance(typ,dict) and 'vec'in typ:return [read(typ['vec']) for _ in range(read('u32'))]
  if isinstance(typ,dict) and 'defined'in typ:return {f['name']:read(f['type']) for f in TYPES[typ['defined']['name']]['fields']}
  raise ValueError(str(typ))
 values={}
 for f in TYPES[name]['fields']:
  try:values[f['name']]=read(f['type'])
  except (ValueError,struct.error,UnicodeDecodeError):break
 return values
def decoded_events(t):
 if t['meta']['err']:return []
 frames=[];out=[]
 for l in t['meta'].get('logMessages',[])or[]:
  m=re.match(r'^Program (\w+) invoke \[\d+\]$',l)
  if m:frames.append((m[1],[]));continue
  m=re.match(r'^Program (\w+) (success|failed:.*)$',l)
  if m and frames:
   p,es=frames.pop()
   if p==m[1] and m[2]=='success':
    if frames:frames[-1][1].extend(es)
    else:out.extend(es)
   continue
  if frames and frames[-1][0]==PUMP and l.startswith('Program data: '):
   raw=base64.b64decode(l[14:])
   for name in ['TradeEvent','CreateEvent']:
    if raw[:8]==hashlib.sha256(('event:'+name).encode()).digest()[:8]:frames[-1][1].append((name,decode(raw,name)))
 return out
def events(t):
 out=[]
 for name,v in decoded_events(t):
  if name!='TradeEvent':continue
  sol=v.get('quote_mint') in [None,'11111111111111111111111111111111','So11111111111111111111111111111111111111112']
  out.append(dict(v,mint=v['mint'],user=v['user'],buy=v['is_buy'],tokens_raw=v['token_amount'],sol_raw=v['sol_amount'],vsol_raw=v['virtual_sol_reserves'],vtokens_raw=v['virtual_token_reserves'],rsol_raw=v['real_sol_reserves'],quote_is_sol=sol,quote_raw=v.get('quote_amount',v['sol_amount']),vquote_raw=v.get('virtual_quote_reserves',v['virtual_sol_reserves']),rquote_raw=v.get('real_quote_reserves',v['real_sol_reserves'])))
 return out
def creations(t):return [dict(v,curve=v['bonding_curve'],deployer=v['user']) for name,v in decoded_events(t) if name=='CreateEvent']
