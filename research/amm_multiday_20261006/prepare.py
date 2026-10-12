"""Whole-transaction historical parity, causal AMM signal definitions, no exits."""
import pathlib,json,gzip,collections,statistics,concurrent.futures,sys,hashlib,bisect
sys.path.insert(0,'/tmp/amm_research_deps')
import ijson
P=pathlib.Path(__file__).resolve().parent;import amm_adapter as A
# Original standalone entry-discovery SPEC was unused by this parser.
METHODS={bytes(i['discriminator']):i['name'] for i in A.IDL['instructions']}
for name in ['buy_v2','buy_exact_quote_in_v2','sell_v2','sweep_protocol_fee','sweep_coin_creator_fee','sweep_creator_fee']:
 METHODS[hashlib.sha256(('global:'+name).encode()).digest()[:8]]=name
def b58decode(s):
 n=0
 for c in s:n=n*58+A.D.ALPHABET.index(c)
 return b'\0'*(len(s)-len(s.lstrip('1')))+n.to_bytes((n.bit_length()+7)//8,'big')
def custody(t,m,tr,g):
 inner={x['index']:x['instructions'] for x in t['meta'].get('innerInstructions',[]) or []};ops=[];ti=0;err=None
 sweeps=collections.deque(e for e in g['events'] if e['kind']=='ObservedFeeSweepEvent')
 for ixindex,outer in enumerate(t['transaction']['message']['instructions']):
  for ix in [outer]+inner.get(ixindex,[]):
   method=METHODS.get(b58decode(ix.get('data',''))[:8]) if ix.get('programId')==A.AMM else None
   if method in ['sweep_protocol_fee','sweep_coin_creator_fee','sweep_creator_fee'] and m['pool'] in ix.get('accounts',[]):
    creator=method!='sweep_protocol_fee';match=next((e for e in sweeps if e['creator']==creator),None)
    # A zero balance sweep emits no event and moves no reserves.
    if match is not None:ops.append(dict(kind='sweep',raw=match['amount']));sweeps.remove(match)
    continue
   if method in ['buy','buy_v2','buy_exact_quote_in','buy_exact_quote_in_v2','sell','sell_v2','boost_buy_and_burn'] and m['pool'] in ix.get('accounts',[]):
    if ti>=len(tr):err='trade_instruction_event_count';continue
    ops.append(dict(kind='trade',event=tr[ti]));ti+=1;continue
   parsed=ix.get('parsed',{})
   if not isinstance(parsed,dict):continue
   info=parsed.get('info',{});kind=parsed.get('type');src=info.get('source',info.get('account'));dst=info.get('destination')
   if kind not in ['transfer','transferChecked','burn','burnChecked']:continue
   if info.get('mint')!=m['mint'] and src not in g['tokenpre'] and src not in g['tokenpost']:continue
   if src==m['base_vault'] or dst==m['base_vault']:continue
   n=int(info.get('amount',info.get('tokenAmount',{}).get('amount',0)))
   ops.append(dict(kind='transfer' if dst else 'burn',source=src,destination=dst,raw=n))
 if ti!=len(tr):err='trade_instruction_event_count'
 if sweeps:err='sweep_instruction_event_count'
 # A separate integer custody identity proves these ordered operations agree
 # with token-account pre/post balances, including router temporary accounts.
 balances=dict(g['tokenpre'])
 for op in ops:
  if op['kind']=='sweep':continue
  if op['kind']=='trade':
   e=op['event'];ac=e['account']
   if e['zero_fee'] and ac=='11111111111111111111111111111111':continue
   balances.setdefault(ac,0)
   if balances[ac]!=e['prehold']:err='custody_prehold_mismatch'
   balances[ac]+=e['n'] if e['buy'] else -e['n']
  else:
   src=op['source'];dst=op['destination'];balances.setdefault(src,0)
   balances[src]-=op['raw']
   if balances[src]<0:err='negative_custody'
   if dst:balances[dst]=balances.get(dst,0)+op['raw']
 for ac,n in g['tokenpost'].items():
  if ac!=m['base_vault'] and balances.get(ac,0)!=n:err='custody_post_mismatch'
 return ops,err

def group(t,m):
 es=[e for e in A.events(t) if e.get('pool')==m['pool']];pre=A.vaults(t,m,'pre');post=A.vaults(t,m,'post');ks=[k['pubkey'] if isinstance(k,dict) else k for k in t['transaction']['message']['accountKeys']]
 tokenpre={ks[b['accountIndex']]:int(b['uiTokenAmount']['amount']) for b in t['meta'].get('preTokenBalances',[]) if b['mint']==m['mint']};tokenpost={ks[b['accountIndex']]:int(b['uiTokenAmount']['amount']) for b in t['meta'].get('postTokenBalances',[]) if b['mint']==m['mint']}
 sweep=any(l in ['Program log: Instruction: SweepProtocolFee','Program log: Instruction: SweepCoinCreatorFee'] for l in t['meta'].get('logMessages',[]) or [])
 return dict(slot=t['slot'],index=t['transactionIndex'],time=t['blockTime'],block_time=t['blockTime'],signature=t['transaction']['signatures'][0],events=es,pre=pre,post=post,tokenpre=tokenpre,tokenpost=tokenpost,fee_sweep=sweep,reserve_shift=0)

def prepare(f):
 with gzip.open(f,'rb') as inp:coverage=next(ijson.items(inp,'coverage'))
 m=coverage['migration'];gs=[];counter=collections.Counter();errors=[];st=None;history=[];signals={};allfeatures=[];lastwithdraw=-10**18;userfirst={}
 inp=gzip.open(f,'rb')
 for t in ijson.items(inp,'transactions.item'):
  g=group(t,m)
  if st is None:
   cre=[e for e in g['events'] if e['kind']=='CreatePoolEvent']
   if not cre:continue
   if len(cre)!=1 or cre[0]['quote_mint']!=A.WSOL or cre[0]['base_mint']!=m['mint']:errors.append('unsupported_genesis');break
   e=cre[0];st=dict(base=e['pool_base_amount'],quote=e['pool_quote_amount'],virtual=0,supply=1000000000000000,mayhem=e.get('is_mayhem_mode',False));m['coin_creator']=e.get('coin_creator');m['is_mayhem_mode']=e.get('is_mayhem_mode',False);m['is_holder_reward']=e.get('is_holder_reward',False)
  # Transactions may not reference the vaults; compare whenever both available.
  if all(v is not None for v in g['pre']) and tuple(g['pre'])!=(st['base'],st['quote']):errors.append(dict(kind='state_chain_gap',signature=g['signature'],expected=[st['base'],st['quote']],observed=g['pre']))
  before=dict(st);tr=[]
  for e in g['events']:
   if e['kind']=='CreatePoolEvent':continue
   if e['kind']=='ObservedFeeSweepEvent':
    st['quote']-=e['amount'];st['virtual']+=e['amount'];g['reserve_shift']+=e['amount'];counter['authenticated_fee_sweeps']+=1;continue
   if e['kind']=='InitBoostEvent':
    st['virtual']=e['virtual_quote_reserves'];st['quote']=e['real_quote_reserves_after'];counter['boost_initializations']+=1;continue
   if e['kind']=='BoostBuyAndBurnEvent':
    if (st['base'],st['quote'])!=(e['base_reserves_after'],e['real_quote_reserves_after']):errors.append(dict(kind='boost_state_mismatch',signature=g['signature']))
    counter['boost_burns']+=1;continue
   if e['kind'] in ['BuyEvent','SellEvent']:
    es=A.state_from_event(e);counter['swaps']+=1
    if (es['base'],es['quote'])!=(st['base'],st['quote']):errors.append(dict(kind='event_state_gap',signature=g['signature']))
    st.update(virtual=es['virtual'],supply=es['supply'],holder=es['holder']);rates=[es[k] for k in ['lp','protocol','creator']];expected=A.fees(st)
    if rates!=expected:
     if rates==[0,0,0]:counter['zero_fee_source_swaps']+=1
     else:errors.append(dict(kind='fee_fixture_mismatch',expected=expected,observed=rates,signature=g['signature']))
    val=dict(st,historical_rates=rates)
    if e['kind']=='BuyEvent':
     gross=e['quote_amount_in_with_lp_fee']+e['protocol_fee']+e.get('coin_creator_fee',0);r=A.buy(val,gross) if e.get('ix_name','').startswith('buy_exact_quote_in') else A.exact_buy(val,e['base_amount_out']);n=e['base_amount_out'];q=e['quote_amount_in_with_lp_fee']-e['lp_fee'];side=True
     if r is None or (r['n'],r['q'],r['total'],r['lp'])!=(n,q,gross,e['lp_fee']):errors.append(dict(kind='buy_quote_mismatch',signature=g['signature'],r=r,n=n,q=q,gross=gross,ix=e.get('ix_name')))
    else:
     r=A.sell(val,e['base_amount_in']);n=e['base_amount_in'];q=e['quote_amount_out'];side=False
     if r is None or (r['q'],r['total'],r['lp'])!=(q,e['user_quote_amount_out'],e['lp_fee']):errors.append(dict(kind='sell_quote_mismatch',signature=g['signature'],r=r,n=n,q=q,net=e['user_quote_amount_out']))
    st=A.observed_move(st,e);ac=e['user_base_token_account'];prehold=e['user_base_token_reserves'];tr.append(dict(buy=side,user=e['user'],account=ac,n=n,q=q,gross=gross if side else None,prehold=prehold,ix=e.get('ix_name','sell'),rates=rates,zero_fee=(rates==[0,0,0]),virtual=es['virtual'],supply=es['supply'],kind=e['kind'],deferred=dict(buyback_bps=e.get('buyback_fee_basis_points',0),cashback_bps=e.get('cashback_fee_basis_points',0),holder_bps=e.get('holder_rewards_bps',0)) if e.get('protocol_fee_recipient')=='11111111111111111111111111111111' else False,max_quote=e.get('max_quote_amount_in',10**30),min_base=e.get('min_base_amount_out',0),min_quote=e.get('min_quote_amount_out',0),time=g['time'],slot=g['slot'],index=g['index']))
   elif e['kind']=='DepositEvent':st['base']+=e['base_amount_in'];st['quote']+=e['quote_amount_in'];counter['deposits']+=1
   elif e['kind']=='WithdrawEvent':st['base']-=e['base_amount_out'];st['quote']-=e['quote_amount_out'];lastwithdraw=g['time'];counter['withdrawals']+=1
   elif e['kind'] not in ['CollectCoinCreatorFeeEvent','CollectProtocolFeeEvent']:
    counter['other_event_'+e['kind']]+=1
  if g['fee_sweep'] and not any(e['kind']=='ObservedFeeSweepEvent' for e in g['events']) and g['pre'][1] is not None and g['post'][1] is not None and not tr:
   delta=g['pre'][1]-g['post'][1]
   if delta<0 or g['pre'][1]!=st['quote']:errors.append(dict(kind='unverified_fee_sweep',signature=g['signature']))
   else:st['quote']-=delta;st['virtual']+=delta;g['reserve_shift']=delta;counter['authenticated_fee_sweeps']+=1
  if all(v is not None for v in g['post']) and tuple(g['post'])!=(st['base'],st['quote']):errors.append(dict(kind='post_vault_mismatch',signature=g['signature'],expected=[st['base'],st['quote']],observed=g['post']))
  g['trades']=tr;g['custody_ops'],g['custody_error']=custody(t,m,tr,g)
  if g['custody_error']:counter['custody_unverified_groups']+=1
  g['state']=dict(st);g['before']=before;g['other_liquidity_events']=[e for e in g['events'] if e['kind'] in ['DepositEvent','WithdrawEvent']];g['events']=tr;gi=len(gs);gs.append(g)
 audit=dict(pool=m['pool'],groups=len(gs),signals=list(signals),counts=dict(counter),errors=errors,good=not errors,genesis=bool(gs),migration=m)
 inp.close()
 tape=dict(pool=m['pool'],mint=m['mint'],migration=m,groups=gs,signals=[],coverage=coverage)
 tape['signals']=extract_signals(tape);audit['signals']=[z['rule'] for z in tape['signals']];return tape,audit

def extract_signals(t):
 """Same frozen rules, incremental windows; no scans of full past history."""
 gs=t['groups'];m=t['migration'];signals={};lastwithdraw=-10**18;recent=collections.deque();burst=collections.deque();buyers=collections.Counter();buyvol=0;sellvol=0;peaks=collections.deque();highs=collections.deque();lows=collections.deque();rangehistory=collections.deque();anchor=None;sales=collections.deque();times=[];cumulative=[0]
 def stats():return len(buyers),buyvol,sellvol,max(buyers.values(),default=0)/buyvol if buyvol else 1
 for gi,g in enumerate(gs):
  tm=g['time'];st=g['state'];spot=(st['quote']+st['virtual'])/st['base'];age=tm-m['time'];outs=[e for e in g['trades'] if e['user']!=m.get('coin_creator') and not e['zero_fee'] and (not e['buy'] or e.get('actor_known',True))]
  times.append(tm);cumulative.append(cumulative[-1]+sum(e['q'] for e in outs if e['buy']))
  for e in outs:
   recent.append(e);burst.append(e)
   if e['buy'] and e['q']>=50_000_000:buyers[e['user']]+=e['q'];buyvol+=e['q']
   elif not e['buy']:sellvol+=e['q']
  while recent and recent[0]['time']<tm-15:recent.popleft()
  while burst and burst[0]['time']<tm-10:
   e=burst.popleft()
   if e['buy'] and e['q']>=50_000_000:
    buyers[e['user']]-=e['q'];buyvol-=e['q']
    if not buyers[e['user']]:del buyers[e['user']]
   elif not e['buy']:sellvol-=e['q']
  while peaks and peaks[0][0]<tm-15:peaks.popleft()
  while peaks and peaks[-1][1]<=spot:peaks.pop()
  peaks.append((tm,spot))
  while rangehistory and rangehistory[0][0]<tm-20:anchor=rangehistory.popleft()
  while highs and highs[0][0]<tm-20:highs.popleft()
  while lows and lows[0][0]<tm-20:lows.popleft()
  while sales and sales[0]['time']<tm-15:sales.popleft()
  if g['other_liquidity_events'] and any(e['kind']=='WithdrawEvent' for e in g['other_liquidity_events']):lastwithdraw=tm
  if 60<=age<=21600 and tm-lastwithdraw>15 and outs:
   quote=A.buy(st,1_000_000_000);impact=quote['q']/(quote['n']*spot)-1 if quote else 1
   if impact<=.02:
    if 'amm_pullback_recovery' not in signals and 1-spot/peaks[0][1]>=.08 and sales:
     sale=sales[-1];later=[e for e in recent if (e['slot'],e['index'])>(sale['slot'],sale['index'])];vol=collections.Counter();groups=set()
     for e in later:
      if e['buy'] and e['q']>=50_000_000:vol[e['user']]+=e['q'];groups.add((e['slot'],e['index']))
     bv=sum(vol.values())
     if len(vol)>=3 and len(groups)>=2 and bv>=sale['q']*.5 and max(vol.values())/bv<=.5:signals['amm_pullback_recovery']=dict(rule='amm_pullback_recovery',index=gi,slot=g['slot'],time=tm,age=age)
    n,bv,sv,share=stats()
    bounds=([highs[0][1],lows[0][1]] if highs else [])+([anchor[1]] if anchor else [])
    if 'amm_second_wave' not in signals and bounds and max(bounds)/min(bounds)-1<=.08 and spot>max(bounds) and outs[-1]['buy'] and n>=3 and share<=.5 and bv and sv/bv<=.5:signals['amm_second_wave']=dict(rule='amm_second_wave',index=gi,slot=g['slot'],time=tm,age=age)
    if 'amm_dormant_revival' not in signals and age>=3600 and n>=5 and bv>=1_000_000_000 and share<=.4:
     bs=next((e['time'] for e in burst if e['buy'] and e['q']>=50_000_000),None)
     if bs is not None:
      quiet=cumulative[bisect.bisect_left(times,bs)]-cumulative[bisect.bisect_left(times,bs-60)]
      if quiet<=250_000_000:signals['amm_dormant_revival']=dict(rule='amm_dormant_revival',index=gi,slot=g['slot'],time=tm,age=age)
  before=g['before'];beforeprice=(before['quote']+st['virtual'])/before['base'];sq=sum(e['q'] for e in outs if not e['buy'])
  if sq and 1-spot/beforeprice>=.05:sales.append(dict(time=tm,slot=g['slot'],index=g['index'],q=sq))
  rangehistory.append((tm,spot))
  while highs and highs[-1][1]<=spot:highs.pop()
  highs.append((tm,spot))
  while lows and lows[-1][1]>=spot:lows.pop()
  lows.append((tm,spot))
  if len(signals)==3:break
 return list(signals.values())

def main():
 audits=[];signals=[]
 (P/'tapes').mkdir(exist_ok=True)
 (P/'prepared_audits').mkdir(exist_ok=True)
 version=hashlib.sha256(pathlib.Path(__file__).read_bytes()+pathlib.Path(A.__file__).read_bytes()).hexdigest()
 for f in sorted((P/'pools').glob('*.gz')):
  af=P/'prepared_audits'/f.name.replace('.json.gz','.json');tf=P/'tapes'/f.name
  a=json.loads(af.read_text()) if af.exists() else {}
  stamp=[f.stat().st_size,f.stat().st_mtime_ns]
  if a.get('version')==version and a.get('input_stamp')==stamp and tf.exists():
   tape_signals=a['signal_records'];tape_pool=a['pool'];tape_mint=a['migration']['mint']
  else:
   tape,a=prepare(f);a.update(version=version,input_stamp=stamp,signal_records=tape['signals'])
   tmp=tf.with_suffix('.partial')
   with gzip.open(tmp,'wt',compresslevel=1) as z:json.dump(tape,z)
   tmp.replace(tf);af.write_text(json.dumps(a,indent=2));tape_signals=tape['signals'];tape_pool=tape['pool'];tape_mint=tape['mint']
  audits.append(a)
  signals +=[dict(s,pool=tape_pool,mint=tape_mint) for s in tape_signals]
  print('PREP',a['pool'][:8],a['groups'],a['signals'],'errors',len(a['errors']),flush=True)
  (P/'PREPARE_CHECKS.json').write_text(json.dumps(audits,indent=2));(P/'SIGNALS.json').write_text(json.dumps(signals,indent=2))
 print('PREP DONE',len(audits),'signals',len(signals),'errors',sum(len(a['errors']) for a in audits),flush=True)
if __name__=='__main__':main()
