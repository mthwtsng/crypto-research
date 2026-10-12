"""PumpSwap adapter for approved day_general replay family; historical parity first."""
import pathlib,json,base64,re,struct,sys
P=pathlib.Path(__file__).resolve().parent;R=P.parent.parent
sys.path.insert(0,str(R/'research/day_general_20261004/helpers'));import decoder as D;import replay as APPROVED
AMM='pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA';WSOL='So11111111111111111111111111111111111111112'
IDL=json.loads((P/'official/SOURCE_PUMP_AMM_IDL.json').read_text());TYPES={t['name']:t['type'] for t in IDL['types']};EVENTS={bytes(e['discriminator']):e['name'] for e in IDL['events']}

def decode(raw,name):
 pos=8;out={}
 for f in TYPES[name]['fields']:
  typ=f['type']
  try:
   if typ=='pubkey':
    if pos+32>len(raw):break
    v=D.b58(raw[pos:pos+32]);pos+=32
   elif typ=='string':
    n=struct.unpack_from('<I',raw,pos)[0];pos+=4
    if pos+n>len(raw):break
    v=raw[pos:pos+n].decode();pos+=n
   elif typ in ['u128','i128']:
    if pos+16>len(raw):break
    v=int.from_bytes(raw[pos:pos+16],'little',signed=typ=='i128');pos+=16
   else:
    fmt={'u64':'Q','i64':'q','u32':'I','u16':'H','u8':'B','bool':'?'}[typ];v=struct.unpack_from('<'+fmt,raw,pos)[0];pos+=struct.calcsize(fmt)
   out[f['name']]=v
  except (struct.error,KeyError,UnicodeError):break
 return out

def events(t):
 if t['meta']['err'] is not None:return []
 frames=[];out=[]
 for l in t['meta'].get('logMessages',[]) or []:
  m=re.match(r'^Program (\w+) invoke \[\d+\]$',l)
  if m:frames.append((m[1],[]));continue
  m=re.match(r'^Program (\w+) (success|failed:.*)$',l)
  if m and frames:
   pr,es=frames.pop()
   if pr==m[1] and m[2]=='success':
    if frames:frames[-1][1].extend(es)
    else:out.extend(es)
   continue
  if frames and frames[-1][0]==AMM and l.startswith('Program data: '):
   b=base64.b64decode(l[14:]);name=EVENTS.get(b[:8])
   if name:frames[-1][1].append(dict(decode(b,name),kind=name))
   elif b[:8]==bytes.fromhex('82a42461e48287a5') and len(b)==185:
    # Receipt-derived codec for fee sweeps missing from the published IDL.
    # The entire sample must independently reconcile these vault deltas and
    # subsequent virtual reserves; it is not a private-strategy inference.
    frames[-1][1].append(dict(kind='ObservedFeeSweepEvent',timestamp=int.from_bytes(b[8:16],'little'),pool=D.b58(b[16:48]),base_mint=D.b58(b[48:80]),quote_mint=D.b58(b[80:112]),amount=int.from_bytes(b[176:184],'little'),creator=bool(b[184])))
 return out

_fixture=(P/'official/package_src___tests___feeConfigMainnetFixture.ts').read_text().split('MAINNET_FEE_CONFIG_DATA_BASE64 = [')[1].split(']')[0]
_fbytes=base64.b64decode(''.join(re.findall(r'"([^"\n]+)"',_fixture)))
TIERS=[]
for _i in range(struct.unpack_from('<I',_fbytes,65)[0]):
 _o=69+40*_i;TIERS.append((int.from_bytes(_fbytes[_o:_o+16],'little'),list(struct.unpack_from('<QQQ',_fbytes,_o+16))))
def fees(st):
 if 'historical_rates' in st:return st['historical_rates']
 supply=1000000000000000 if st.get('mayhem') else st.get('supply',1000000000000000)
 cap=(st['quote']+st.get('virtual',0))*supply//st['base']
 return next((f for threshold,f in reversed(TIERS) if cap>=threshold),TIERS[0][1])

def fee(q,b):return APPROVED.fee(q,b)
def exact_buy(st,n):
 if n<=0 or n>=st['base']:return None
 q=(st['quote']+st.get('virtual',0))*n;den=st['base']-n;q=(q+den-1)//den
 fs=[fee(q,b) for b in fees(st)];return dict(n=n,q=q,total=q+sum(fs),lp=fs[0],protocol=fs[1],creator=fs[2])
def buy(st,budget):
 q=budget*10000//(10000+sum(fees(st)))
 fs=[fee(q,b) for b in fees(st)];over=q+sum(fs)-budget
 if over>0:q-=over
 if q<=1:return None
 n=st['base']*(q-1)//(st['quote']+st.get('virtual',0)+q-1)
 return dict(n=n,q=q,total=q+sum(fs),lp=fs[0],protocol=fs[1],creator=fs[2]) if n>0 else None
def sell(st,n):
 if n<=0:return None
 q=(st['quote']+st.get('virtual',0))*n//(st['base']+n);fs=[fee(q,b) for b in fees(st)]
 if q-fs[0]>st['quote']:return None
 return dict(n=n,q=q,total=q-sum(fs),lp=fs[0],protocol=fs[1],creator=fs[2])
def moved(st,r,buying,deferred=False):
 z=dict(st)
 payout=0 if not isinstance(deferred,dict) else r['protocol']*deferred['buyback_bps']//10000+fee(r['q'],deferred['cashback_bps'])
 retained=0
 if buying:z['base']-=r['n'];z['quote']+=r['total']-payout if deferred else r['q']+r['lp']+retained
 else:z['base']+=r['n'];z['quote']-=r['total']+payout if deferred else r['q']-r['lp']-retained
 return z

def state_from_event(e):return dict(base=e['pool_base_token_reserves'],quote=e['pool_quote_token_reserves'],virtual=e.get('virtual_quote_reserves',0),lp=e['lp_fee_basis_points'],protocol=e['protocol_fee_basis_points'],creator=e.get('coin_creator_fee_basis_points',0),supply=e.get('base_supply',1000000000000000),buyback=e.get('buyback_fee_basis_points',0),holder=e.get('holder_rewards_bps',0))
def observed_move(st,e):
 z=dict(st)
 deferred=e.get('protocol_fee_recipient')=='11111111111111111111111111111111'
 if e['kind']=='BuyEvent':z['base']-=e['base_amount_out'];z['quote']+=e['quote_amount_in_with_lp_fee']+(e['protocol_fee']+e.get('coin_creator_fee',0)-e.get('buyback_fee',0)-e.get('cashback',0) if deferred else 0)
 elif e['kind']=='SellEvent':z['base']+=e['base_amount_in'];z['quote']-=e['user_quote_amount_out']+e.get('buyback_fee',0)+e.get('cashback',0) if deferred else e['quote_amount_out']-e['lp_fee']
 return z

def vaults(t,m,side):
 ks=[k['pubkey'] if isinstance(k,dict) else k for k in t['transaction']['message']['accountKeys']];bs={ks[b['accountIndex']]:int(b['uiTokenAmount']['amount']) for b in t['meta'].get(side+'TokenBalances',[]) or []}
 return (bs.get(m['base_vault']),bs.get(m['quote_vault']))
