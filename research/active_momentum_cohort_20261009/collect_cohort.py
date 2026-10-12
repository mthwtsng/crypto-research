"""Filtered historical cohort collection only; never executes strategy simulations.
All outputs, including imported helper caches, are confined to this directory.
"""
import sys
sys.dont_write_bytecode=True
import argparse,collections,concurrent.futures,datetime,gzip,hashlib,importlib.util,json,pathlib,time,traceback
import rpc_pool as R
P=pathlib.Path(__file__).resolve().parent;ROOT=P.parents[1]
START=int(datetime.datetime(2026,8,18,tzinfo=datetime.timezone.utc).timestamp())
END=int(datetime.datetime(2026,10,1,tzinfo=datetime.timezone.utc).timestamp())
VERIFIER_VERSION='creation_account_balance_block_parity_v2'
TARGET=2000;POST_MIGRATION_SECONDS=240;KEYS=('vsol_raw','vtokens_raw','rsol_raw','rtokens_raw')
sys.path.insert(0,str(ROOT/'research/day_general_20261004/helpers'))
sys.path.insert(0,str(ROOT/'research/wallet_curve_entry_discovery_20261007'))
import decoder as D,bind_curve_limits as LIMIT,merge_curve_receipts as ACCOUNT,curve_adapter as A

def loadmodule(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
PREP=loadmodule('cohort_prepare',ROOT/'research/day_general_20261004/prepare.py')
MIG=loadmodule('cohort_migration_decoder',ROOT/'research/amm_multiday_20261006/collect.py')
# Creator fee-sharing changes are not pool migration instructions.
MIG.MIG={k:v for k,v in MIG.MIG.items() if v['name'] in ('migrate','migrate_v2')}

def decoded_migrations(tx):
 rows=MIG.migrations(tx);out={}
 for m in rows:
  for ix in MIG.allix(tx):
   if ix.get('programId')!=D.PUMP:continue
   spec=MIG.MIG.get(MIG.raw(ix.get('data',''))[:8])
   if not spec:continue
   ac=dict(zip([a['name'] for a in spec['accounts']],ix.get('accounts',[])))
   if ac.get('mint',ac.get('base_mint'))==m['mint'] and ac.get('pool')==m['pool']:m['bonding_curve']=ac['bonding_curve']
  if not m.get('bonding_curve'):raise ValueError('migration_curve_binding_missing')
  out[(m['signature'],m['mint'],m['pool'])]=m
 return list(out.values())

def _migration_for_snapshot(d,mint):
 """Return only a migration decoded from a successful, mint-and-curve-bound receipt."""
 curve=d.get('creation_metadata',{}).get('bonding_curve')
 if not curve:return None
 rows=[]
 for tx in d.get('transactions',[]):
  if tx.get('meta',{}).get('err') is not None:continue
  rows.extend(m for m in decoded_migrations(tx) if m.get('mint')==mint and m.get('bonding_curve')==curve)
 unique={(m['signature'],m['mint'],m['pool']):m for m in rows}
 if len(unique)>1:raise ValueError('multiple_migration_bindings')
 actual=next(iter(unique.values()),None)
 recorded=d.get('migration')
 if recorded and actual is None:raise ValueError('migration_receipt_coverage_missing')
 if recorded and actual:
  for key in ('mint','pool','bonding_curve','signature','slot','index','time'):
   if recorded.get(key)!=actual.get(key):raise ValueError('migration_receipt_mismatch')
 return actual

def _coverage_complete_through(coverage,end):
 return bool(coverage.get('exhausted')) and coverage.get('upper_time') is not None and coverage['upper_time']>=end

def _owned_parent(path):
 """A leaf may be a symlink; writing its parent must still stay inside this artifact tree."""
 root=P.resolve();parent=pathlib.Path(path).parent.resolve()
 return parent==root or root in parent.parents

def _archive_original_pool(path,mint):
 """Copy the exact pre-trim bytes into our own archive; never write through a symlink."""
 source=pathlib.Path(path).read_bytes();digest=hashlib.sha256(source).hexdigest()
 folder=P/'archive'/'raw_pools_before_240s';folder.mkdir(parents=True,exist_ok=True)
 if not _owned_parent(folder/'_probe'):
  raise ValueError('pool_archive_path_not_owned')
 archived=folder/(mint+'.'+digest+'.json.gz')
 if not archived.exists():
  temporary=archived.with_name(archived.name+'.'+str(time.time_ns())+'.partial')
  temporary.write_bytes(source);temporary.replace(archived)
 return archived,digest

def retain_pool_horizon(path,mint,migration,pooldata=None):
 """Retain a complete 240-second pool slice, archiving any longer source first."""
 path=pathlib.Path(path);end=migration['time']+POST_MIGRATION_SECONDS
 pooldata=read(path) if pooldata is None else pooldata
 coverage=pooldata.get('coverage',{});transactions=pooldata.get('transactions',[])
 if pooldata.get('mint')!=mint or pooldata.get('migration',{}).get('signature')!=migration['signature']:
  raise ValueError('post_migration_pool_binding_mismatch')
 if not _coverage_complete_through(coverage,end):raise ValueError('incomplete_post_migration_history')
 lower=coverage.get('lower_time')
 if lower is not None and lower>migration['time']:raise ValueError('incomplete_post_migration_history')
 if migration['signature'] not in {sig(z) for z in transactions}:raise ValueError('authenticated_pool_open_missing')
 retained=[z for z in transactions if migration['time']<=z['blockTime']<=end]
 if migration['signature'] not in {sig(z) for z in retained}:raise ValueError('authenticated_pool_open_missing')
 source_upper=coverage.get('source_upper_time',coverage.get('upper_time'))
 source_receipts=coverage.get('source_receipts',coverage.get('receipts',len(transactions)))
 is_superset=source_upper>end or len(retained)!=len(transactions)
 derivation=pooldata.get('coverage_superset_derivation')
 archived=None;source_sha256=None
 if is_superset and not derivation:
  if not _owned_parent(path):raise ValueError('pool_cache_path_not_owned')
  archived,source_sha256=_archive_original_pool(path,mint)
 coverage=dict(coverage)
 coverage.update(source_upper_time=source_upper,source_receipts=source_receipts,
                 receipts=len(retained),retained_receipts=len(retained),
                 upper_time=end,retained_through_time=end)
 pooldata=dict(pooldata,coverage=coverage,transactions=retained)
 if is_superset and not derivation:
  pooldata['coverage_superset_derivation']=dict(
   method='exhausted_source_superset_truncated_to_requested_horizon',
   requested_end_time=end,source_upper_time=source_upper,source_receipts=source_receipts,
   retained_receipts=len(retained),source_sha256=source_sha256,
   source_archive=str(archived.relative_to(P)))
 if not _owned_parent(path):raise ValueError('pool_cache_path_not_owned')
 R.save(path,pooldata)
 return pooldata

def trim_curve_snapshot(d,mint):
 """Cap authenticated migrated curve receipts and custody repair inputs at the same horizon."""
 migration=_migration_for_snapshot(d,mint)
 if migration is None:return d,False
 end=migration['time']+POST_MIGRATION_SECONDS;coverage=d.get('coverage',{})
 if not _coverage_complete_through(coverage,end):raise ValueError('incomplete_curve_history')
 transactions=d.get('transactions',[])
 retained=[z for z in transactions if z['blockTime']<=end]
 if migration['signature'] not in {sig(z) for z in retained}:raise ValueError('migration_receipt_coverage_missing')
 changed=(d.get('requested_end_time')!=end or len(retained)!=len(transactions) or coverage.get('upper_time')!=end)
 if not changed:return d,False
 source_upper=coverage.get('source_upper_time',coverage.get('upper_time'))
 source_receipts=coverage.get('source_receipts',coverage.get('receipts',len(transactions)))
 coverage=dict(coverage)
 coverage.update(source_upper_time=source_upper,source_receipts=source_receipts,
                 receipts=len(retained),retained_receipts=len(retained),
                 upper_time=end,retained_through_time=end)
 d=dict(d,transactions=retained,coverage=coverage,migration=migration,requested_end_time=end)
 d['coverage_superset_derivation']=dict(
  method='exhausted_curve_source_capped_to_post_migration_horizon',
  requested_end_time=end,source_upper_time=source_upper,source_receipts=source_receipts,
  retained_receipts=len(retained))
 return d,True

def _pump_trade_instruction_count(tx,mint,curve=None):
 top=tx.get('transaction',{}).get('message',{}).get('instructions',[])
 inner={g['index']:g.get('instructions',[]) for g in tx.get('meta',{}).get('innerInstructions',[]) or []}
 count=0
 for k,ix in enumerate(top):
  for item in [ix]+inner.get(k,[]):
   if item.get('programId')!=D.PUMP:continue
   raw=LIMIT.raw(item.get('data',''));instruction=LIMIT.I.get(raw[:8])
   accounts=item.get('accounts',[])
   if instruction and instruction['name'] in LIMIT.TRADE and mint in accounts and (curve is None or curve in accounts):count+=1
 return count

def early_curve_metrics(d,mint):
 """Cheap, account-bound source metrics; no custody reconstruction or parity replay."""
 curve=d.get('creation_metadata',{}).get('bonding_curve')
 if not curve:return None
 trade_signatures=set();peak=0;migration=_migration_for_snapshot(d,mint)
 for tx in d.get('transactions',[]):
  if tx.get('meta',{}).get('err') is not None:continue
  events=[e for e in D.events(tx) if e.get('mint')==mint]
  try:
   bindings=LIMIT.bind(tx,mint)
   mint_instruction_count=_pump_trade_instruction_count(tx,mint)
   curve_instruction_count=_pump_trade_instruction_count(tx,mint,curve)
  except (KeyError,TypeError,ValueError):return None
  if not events:
   if mint_instruction_count:return None
   continue
  # A decoded Pump event with no Pump curve instruction can be unrelated AMM
  # traffic. Once a target-mint curve instruction exists, any disagreement in
  # event, instruction, account, side, or quote binding is ambiguous and must
  # fall through to the full verifier instead of proving a low threshold.
  if not bindings and not mint_instruction_count and not curve_instruction_count:continue
  if (len(bindings)!=len(events) or mint_instruction_count!=len(events) or
      curve_instruction_count!=len(events)):
   return None
  if any(e.get('buy')!=b['name'].startswith('buy') or e.get('quote_is_sol') is not True
         or 'rsol_raw' not in e for e,b in zip(events,bindings)):
   return None
  trade_signatures.add(sig(tx));peak=max(peak,max(e['rsol_raw'] for e in events))
 coverage=d.get('coverage',{});end=d.get('requested_end_time',coverage.get('upper_time'))
 complete=end is not None and _coverage_complete_through(coverage,end)
 return dict(successful_curve_trade_transactions=len(trade_signatures),peak_reserve_raw=peak,
             migration=bool(migration),complete_snapshot=complete)

def early_curve_rejection(d,mint):
 metrics=early_curve_metrics(d,mint)
 if not metrics or not metrics['complete_snapshot']:return None
 if metrics['successful_curve_trade_transactions']<50:return 'fewer_than_50_successful_curve_trade_transactions'
 if metrics['peak_reserve_raw']<12_000_000_000 and not metrics['migration']:
  return 'peak_below_12_no_migration'
 return None

def read(f):
 opener=gzip.open if str(f).endswith('.gz') else open
 with opener(f,'rt') as stream:return json.load(stream)
def sig(tx):return tx['transaction']['signatures'][0]
def ordered(txs):
 by={};positions={}
 for t in txs:
  if t.get('transactionIndex') is None or t.get('blockTime') is None:raise ValueError('unverifiable_transaction_order_or_time')
  k=(t['slot'],t['transactionIndex']);s=sig(t)
  if k in positions and positions[k]!=s:raise ValueError('conflicting_transaction_order')
  if s in by and (by[s]['slot'],by[s]['transactionIndex'])!=k:raise ValueError('signature_order_conflict')
  positions[k]=s;by[s]=t
 return sorted(by.values(),key=lambda t:(t['slot'],t['transactionIndex']))

def history(address,lo=None,hi=None):
 rows=[];token=None;seen=set();pages=0
 while True:
  cfg=dict(transactionDetails='full',encoding='jsonParsed',maxSupportedTransactionVersion=1,sortOrder='asc',limit=1000,commitment='finalized')
  times={}
  if lo is not None:times['gte']=lo
  if hi is not None:times['lte']=hi
  if times:cfg['filters']=dict(blockTime=times)
  if token:cfg['paginationToken']=token
  result=R.rpc('getTransactionsForAddress',[address,cfg]);rows.extend(result['data']);pages+=1
  nxt=result.get('paginationToken')
  if not nxt:break
  if nxt in seen:raise ValueError('pagination_cycle')
  seen.add(nxt);token=nxt
 return ordered(rows),dict(address=address,pages=pages,exhausted=True,lower_time=lo,upper_time=hi,receipts=len(rows),order_source='enhanced RPC transactionIndex')

def screen(item):
 """Read-only first-hour shortlist; every final metric is recomputed on full history."""
 mint=item['mint'];f=ROOT/'research/frozen_21day_validation_20261008/raw_curves'/(mint+'.json.gz')
 if not f.exists():return None
 d=read(f);creator=item['creation']['user'];buyers=set();trade_txs=0;peak=0
 for tx in d['transactions']:
  ev=[e for e in D.events(tx) if e['mint']==mint and e['quote_is_sol']]
  if ev:trade_txs+=1;peak=max(peak,max(e['rsol_raw'] for e in ev))
  buyers.update(e['user'] for e in ev if e['buy'] and e['user']!=creator and e['sol_raw']>=50_000_000)
 if trade_txs>=50 and peak>=12_000_000_000 and len(buyers)>=25:
  return dict(mint=mint,creation=item['creation'],creation_time=item['creation_time'],creation_slot=item['creation_slot'],source='cached_creation_sample_prefilter',screen_trade_transactions=trade_txs,screen_peak_sol=peak/1e9,screen_buyers=len(buyers))
 return None

def census(day):
 f=P/'migration_census'/(str(day)+'.json.gz')
 if f.exists():
  cached=read(f)
  if cached.get('decoder_version')=='bound_curve_v1':return cached
 txs,coverage=history(MIG.AUTH,day,day+86399);rows=[]
 for tx in txs:
  if tx['meta']['err'] is None:rows.extend(decoded_migrations(tx))
 z=dict(day=day,decoder_version='bound_curve_v1',coverage=coverage,migrations=list({m['mint']:m for m in rows if m['quote_mint']==MIG.WSOL}.values()))
 R.save(f,z);return z

def find_creation(candidate):
 if 'creation' in candidate:return candidate['creation'],candidate.get('creation_time')
 # The migration receipt binds the actual bonding curve; querying it recovers
 # genuine creation and avoids token-account history polluted by AMM traffic.
 curve=candidate.get('bonding_curve');tx=None
 if not curve:
  try:tx=R.rpc('getTransaction',[candidate['signature'],dict(encoding='jsonParsed',maxSupportedTransactionVersion=1,commitment='finalized')])
  except RuntimeError:tx=None
  if tx is None:
   block=R.rpc('getBlock',[candidate['slot'],dict(transactionDetails='full',encoding='jsonParsed',maxSupportedTransactionVersion=1,rewards=False,commitment='finalized')])
   if block is None:raise ValueError('migration_receipt_coverage_missing')
   tx=block['transactions'][candidate['index']]
   if sig(tx)!=candidate['signature']:raise ValueError('migration_receipt_block_order_mismatch')
 for ix in (MIG.allix(tx) if tx else []):
  if ix.get('programId')!=D.PUMP:continue
  spec=MIG.MIG.get(MIG.raw(ix.get('data',''))[:8])
  if spec and spec['name'] in ('migrate','migrate_v2'):
   ac=dict(zip([a['name'] for a in spec['accounts']],ix.get('accounts',[])))
   if ac.get('mint',ac.get('base_mint'))==candidate['mint']:curve=ac.get('bonding_curve')
 if not curve:raise ValueError('migration_curve_binding_missing')
 # First page only for creation discovery. Full history is separately exhausted.
 cfg=dict(transactionDetails='full',encoding='jsonParsed',maxSupportedTransactionVersion=1,sortOrder='asc',limit=1000,commitment='finalized')
 first=R.rpc('getTransactionsForAddress',[curve,cfg])
 for z in first['data']:
  for c in D.creations(z):
   if c['mint']==candidate['mint']:return c,z['blockTime']
 raise ValueError('genuine_creation_missing')

def bind(d):
 successful=[z for z in d['transactions'] if z['meta']['err'] is None]
 t,a=PREP.make(dict(d,transactions=successful))
 if t is None:raise ValueError(a)
 if not t['normal']:raise ValueError('unsupported_quote_or_token_mode')
 by={sig(z):z for z in successful};groups=[];effective=None
 for g in t['groups']:
  # Curve parity ends at authenticated completion; migration transfers are a
  # different custody venue and preserved separately in raw receipts.
  limits=LIMIT.bind(by[g['signature']],t['mint'])
  if len(limits)!=len(g['events']):raise ValueError('instruction_event_binding_count')
  for e,b in zip(g['events'],limits):
   if not e['quote_is_sol']:raise ValueError('unsupported_quote')
   creator=e['creator_fee_bps'];cashback=e.get('cashback_fee_basis_points',0)
   if creator and cashback:raise ValueError('simultaneous_creator_cashback_rounding_unsupported')
   e['decoded_creator_fee_bps']=creator;e['creator_fee_bps']=creator+cashback;effective=creator+cashback
   e.update(b['fields']);e['instruction_name']=b['name']
  if effective is not None:g['state']['creator_fee_bps']=effective
  groups.append(ACCOUNT.account_group(g,by[g['signature']],t['mint']))
  if g['state']['rtokens_raw']==0:break
 t['groups']=groups;t['inventory_key']='token_account'
 return t

def parity(t):
 gs=t['groups'];first=next((e for g in gs for e in g['events']),None)
 if first is None:raise ValueError('no_curve_trades')
 # Reconstruct initial state before first trade, then validate creation too.
 q,n=first['sol_raw'],first['tokens_raw'];direction=1 if first['buy'] else -1
 st=dict(vsol_raw=first['vsol_raw']-direction*q,vtokens_raw=first['vtokens_raw']+direction*n,rsol_raw=first['rsol_raw']-direction*q,rtokens_raw=first['real_token_reserves']+direction*n,fee_bps=first['fee_bps'],creator_fee_bps=first['creator_fee_bps'])
 c=t['creation_metadata']
 if any(st[k]!=v for k,v in dict(vsol_raw=c['virtual_sol_reserves'],vtokens_raw=c['virtual_token_reserves'],rsol_raw=0,rtokens_raw=c['real_token_reserves']).items()):raise ValueError('creation_initial_reserves_mismatch')
 h={};cf={};owners={};peak=-1;peak_info=None;qualified=set();trade_count=0;checked=0
 devs={c['user'],c.get('creator',c['user'])}
 for g in gs:
  z,hh,cc,adjusted,err=A.apply(st,g,h,cf)
  if g['custody_issues']:raise ValueError('unsupported_receipt_custody:'+str(g['custody_issues'][:3]))
  for ac,pre in g['tokenpre'].items():
   if g['account_owners'].get(ac)==t['curve']:continue
   if h.get(ac,0)!=pre:
    if h.get(ac,0)<pre:return dict(error='source_inventory_gap',group=g,hist=h,missing_account=ac)
    raise ValueError('source_token_prebalance_mismatch')
  if err:return dict(error=err,group=g,hist=h)
  if adjusted.get('counterfactual_revert') or hh!=cc or any(z[k]!=g['state'][k] for k in KEYS):return dict(error='whole_source_parity',signature=g['signature'])
  for ac,post in g['tokenpost'].items():
   if g['account_owners'].get(ac)==t['curve']:continue
   if hh.get(ac,0)!=post:raise ValueError('source_token_postbalance_mismatch')
  st,h,cf=z,hh,cc;checked+=1;owners.update({k:v for k,v in g['account_owners'].items() if v is not None})
  if g['events']:trade_count+=1
  qualified.update(e['user'] for e in g['events'] if e['buy'] and e['user'] not in devs and e['sol_raw']>=50_000_000)
  if z['rsol_raw']>peak:
   peak=z['rsol_raw'];circulating=c['real_token_reserves']-z['rtokens_raw']
   unknown=sum(v for k,v in h.items() if v>0 and not owners.get(k))
   held=sum(v for k,v in h.items() if owners.get(k) in devs)
   peak_info=dict(signature=g['signature'],slot=g['slot'],transactionIndex=g['index'],block_time=g['block_time'],creator_tokens_raw=held,circulating_tokens_raw=circulating,unknown_owner_tokens_raw=unknown,creator_share=(held/circulating if circulating else None))
 return dict(error=None,groups_checked=checked,peak_reserve_sol=peak/1e9,peak=peak_info,qualified_outside_buyers=len(qualified),successful_curve_trade_transactions=trade_count)

def observation_metadata(d):
 coverage=d.get('coverage',{})
 return dict(curve_observation_start_time=d['creation_time'],
             curve_observation_end_time=d['requested_end_time'],
             decision_end_time=d.get('decision_end_time'),
             curve_observation_complete=bool(coverage.get('exhausted')),
             curve_observation_scope=('fixed_first_hour' if d.get('imported_from_local_source') else 'exhausted_address_source_interval'),
             curve_lifetime_complete=coverage.get('curve_lifetime_complete',bool(d.get('migration'))))

def validated_cached_audit(mint):
 """Reuse admissions only after checking their retained source and venue proof."""
 try:
  auditpath=P/'audits'/(mint+'.json');dest=P/'bound_curve_tapes'/(mint+'.json.gz');raw=P/'raw_curves'/(mint+'.json.gz')
  if not all(f.exists() for f in (auditpath,dest,raw)):return None
  r=read(auditpath)
  if r.get('verifier_version')!=VERIFIER_VERSION or r.get('status')!='verified' or r.get('mint')!=mint:return None
  if not START<=r['creation_time']<END:return None
  d=read(raw);t=read(dest)
  if d.get('mint')!=mint or t.get('mint')!=mint or not d.get('coverage',{}).get('exhausted'):return None
  creations=[(z,ev) for z in d['transactions'] for ev in D.creations(z) if ev['mint']==mint]
  if len(creations)!=1:return None
  creation_tx,creation=creations[0]
  if sig(creation_tx)!=r['creation_signature'] or creation_tx['blockTime']!=r['creation_time']:return None
  for key in ('mint','bonding_curve','user','virtual_sol_reserves','virtual_token_reserves','real_token_reserves'):
   if t['creation_metadata'].get(key)!=creation.get(key):return None
  migration_rows=[m for z in d['transactions'] if z['meta']['err'] is None for m in decoded_migrations(z) if m['mint']==mint]
  if len(migration_rows)>1:return None
  if bool(migration_rows)!=bool(d.get('migration')) or bool(migration_rows)!=r.get('migration_status'):return None
  if migration_rows:
   actual=migration_rows[0]
   for key in ('mint','pool','bonding_curve','signature','slot','index','time'):
    if d['migration'].get(key)!=actual.get(key) or r['migration'].get(key)!=actual.get(key):return None
  if t.get('inventory_key')!='token_account' or t.get('parity',{}).get('error') is not None:return None
  if t.get('block_order_verification',{}).get('checked_slots',0)!=r.get('verified_block_slots') or not r.get('verified_block_slots'):return None
  if d.get('migration'):
   m=d['migration'];poolpath=P/'raw_pools'/(mint+'.json.gz')
   if not poolpath.exists():return None
   pool=read(poolpath);coverage=pool.get('coverage',{})
   if pool.get('mint')!=mint or pool.get('migration',{}).get('signature')!=m['signature']:return None
   end=m['time']+POST_MIGRATION_SECONDS
   if not _coverage_complete_through(coverage,end) or (coverage.get('lower_time') is not None and coverage['lower_time']>m['time']):return None
   if m['signature'] not in {sig(z) for z in pool['transactions']}:return None
  else:poolpath=None;pool=None
  groups=[g for g in t['groups'] if g['source_status']=='succeeded']
  proof=parity(dict(t,groups=groups))
  if proof.get('error') is not None or proof['groups_checked']!=r['source_groups_checked']:return None
  if proof['successful_curve_trade_transactions']<50 or proof['qualified_outside_buyers']<25:return None
  if proof['peak_reserve_sol']<12 and not d.get('migration'):return None
  peak=proof['peak']
  if peak['creator_share'] is None or peak['creator_share']>.10 or peak['unknown_owner_tokens_raw']:return None
  if d.get('migration'):
   retain_pool_horizon(poolpath,mint,d['migration'],pool)
   trimmed,changed=trim_curve_snapshot(d,mint)
   if changed:R.save(raw,trimmed)
  return dict(r,required_post_migration_seconds=POST_MIGRATION_SECONDS,**observation_metadata(d))
 except (OSError,ValueError,KeyError,TypeError):return None

def verify(candidate):
 mint=candidate['mint'];auditpath=P/'audits'/(mint+'.json');dest=P/'bound_curve_tapes'/(mint+'.json.gz')
 cached=validated_cached_audit(mint)
 if cached is not None:return cached
 c,ct=find_creation(candidate)
 if not START<=ct<END:raise ValueError('creation_outside_requested_window')
 if c.get('is_mayhem_mode') or c.get('is_holder_reward'):raise ValueError('unsupported_mode')
 rawpath=P/'raw_curves'/(mint+'.json.gz')
 if rawpath.exists():d=read(rawpath)
 elif candidate.get('local_raw_path'):
  import local_active_seed as LOCAL
  try:d=LOCAL.import_source(candidate)
  except LOCAL.LocalSourceCoverageError as exc:
   raise ValueError('local_source_not_eligible:'+str(exc)) from exc
  R.save(rawpath,d)
 else:
  # The user forbids curve history re-queries for the locally covered early
  # interval. Missing early local coverage is explicit, never silently fetched.
  local_end=int(datetime.datetime(2026,9,8,tzinfo=datetime.timezone.utc).timestamp())
  if ct<local_end:raise ValueError('local_source_not_eligible:early_window_no_complete_local_source')
  txs,cov=history(c['bonding_curve'],None,int(time.time()))
  creations=[(z,e) for z in txs for e in D.creations(z) if e['mint']==mint]
  if len(creations)!=1:raise ValueError('creation_count_not_one')
  creation_tx,c=creations[0];ct=creation_tx['blockTime']
  if not START<=ct<END:raise ValueError('creation_outside_requested_window')
  migrations=[m for z in txs if z['meta']['err'] is None for m in decoded_migrations(z) if m['mint']==mint]
  if len(migrations)>1:raise ValueError('multiple_migration_bindings')
  migration=migrations[0] if migrations else None
  if migration:
   end=migration['time']+POST_MIGRATION_SECONDS;txs=[z for z in txs if z['blockTime']<=end]
   cov['retained_through_time']=end
  else:end=cov['upper_time']
  d=dict(mint=mint,creation_metadata=c,creation_signature=sig(creation_tx),creation_time=ct,requested_end_time=end,coverage=cov,migration=migration,transactions=txs,custody_extensions=[])
  R.save(rawpath,d)
 d,curve_changed=trim_curve_snapshot(d,mint)
 if curve_changed:R.save(rawpath,d)
 early_reason=early_curve_rejection(d,mint)
 if early_reason:raise ValueError(early_reason)
 # Resolve missing token-account transfers, never initialize inventory by fiat.
 for attempt in range(30):
  t=bind(d);t['creation_metadata']=d['creation_metadata'];result=parity(t)
  if result['error']!='source_inventory_gap':break
  g=result['group'];h=result['hist'];balances=dict(h);acct=result.get('missing_account')
  for op in ([] if acct else g['custody_ops']):
   if op['kind']=='trade':
    e=op['event'];owner=op['owner'];need=0 if e['buy'] else e['tokens_raw']
    if balances.get(owner,0)<need:acct=owner;break
    balances[owner]=balances.get(owner,0)+(e['tokens_raw'] if e['buy'] else -need)
   else:
    owner=op['from_owner'];need=op['raw']
    if balances.get(owner,0)<need:acct=owner;break
    balances[owner]=balances.get(owner,0)-need;dst=op['to_owner'];balances[dst]=balances.get(dst,0)+need
  if not acct:raise ValueError('inventory_gap_account_not_identified')
  if d.get('imported_from_local_source') and d['creation_time']<int(datetime.datetime(2026,9,8,tzinfo=datetime.timezone.utc).timestamp()):
   raise ValueError('local_source_not_eligible:cached_custody_incomplete')
  extra,ec=history(acct,d['creation_time']-2,g['block_time']+1)
  old={sig(z) for z in d['transactions']};extra=[z for z in extra if sig(z) not in old and z['slot']>=t['creation_slot'] and z['blockTime']<=d['requested_end_time']]
  if not extra:raise ValueError('unresolvable_inventory_gap')
  d['transactions']=ordered(d['transactions']+extra);d['custody_extensions'].append(dict(account=acct,added=len(extra),coverage=ec));R.save(rawpath,d)
 else:raise ValueError('custody_repair_limit')
 if result['error']:raise ValueError(result['error'])
 if result['successful_curve_trade_transactions']<50:raise ValueError('fewer_than_50_successful_curve_trade_transactions')
 if result['peak_reserve_sol']<12 and not d['migration']:raise ValueError('peak_below_12_no_migration')
 if result['qualified_outside_buyers']<25:raise ValueError('fewer_than_25_qualified_buyers')
 peak=result['peak']
 if peak['unknown_owner_tokens_raw'] or peak['creator_share'] is None:raise ValueError('unknown_peak_holder_ownership')
 if peak['creator_share']>0.10:raise ValueError('creator_monopoly_at_peak')
 # Qualify the complete curve before downloading potentially large pool history.
 # Admitted migrated coins retain the frozen post-migration horizon.
 if d['migration']:
  poolpath=P/'raw_pools'/(mint+'.json.gz')
  migration=d['migration'];end=migration['time']+POST_MIGRATION_SECONDS
  if not poolpath.exists():
   pooltx,pc=history(migration['pool'],migration['time'],end)
   if migration['signature'] not in {sig(z) for z in pooltx}:raise ValueError('authenticated_pool_open_missing')
   R.save(poolpath,dict(mint=mint,migration=migration,coverage=pc,transactions=pooltx))
  pooldata=retain_pool_horizon(poolpath,mint,migration)
 # Authenticate every retained receipt's transaction index against the actual
 # finalized block, including failed transactions and pool continuation.
 sources=[d['transactions']]
 if d['migration']:sources.append(read(P/'raw_pools'/(mint+'.json.gz'))['transactions'])
 slot_rows=collections.defaultdict(list)
 for txs in sources:
  for z in txs:slot_rows[z['slot']].append(z)
 def check_block(slot):
  block=R.rpc('getBlock',[slot,dict(transactionDetails='signatures',rewards=False,maxSupportedTransactionVersion=1,commitment='finalized')])
  if not block:raise ValueError('historical_block_unavailable')
  signatures=block['signatures']
  for z in slot_rows[slot]:
   i=z['transactionIndex']
   if i>=len(signatures) or signatures[i]!=sig(z):raise ValueError('block_order_signature_mismatch')
  return slot
 with concurrent.futures.ThreadPoolExecutor(4) as executor:verified_slots=list(executor.map(check_block,sorted(slot_rows)))
 t['block_order_verification']=dict(checked_slots=len(verified_slots),method='finalized getBlock signatures exact index match',rpc_cache_directory='rpc')
 # Preserve failed receipts as canonical no-op groups, never as successful buys.
 failed=[]
 for z in d['transactions']:
  if z['meta']['err'] is not None and (z['slot'],z['transactionIndex']) >= (t['creation_slot'],t['groups'][0]['index']):
   failed.append(dict(signature=sig(z),slot=z['slot'],index=z['transactionIndex'],block_time=z['blockTime'],source_status='failed',source_error=z['meta']['err'],events=[],custody_ops=[],source_network_fee=z['meta']['fee']))
 merged=sorted(t['groups']+failed,key=lambda g:(g['slot'],g['index']));state=None
 for g in merged:
  if g['source_status']=='failed':g['state']=dict(state) if state else None
  else:state=g['state']
 t.update(groups=merged,migration=d['migration'],source_coverage=d['coverage'],parity=result,post_migration_receipts_path=('raw_pools/'+mint+'.json.gz' if d['migration'] else None),custody_extensions=d['custody_extensions'])
 R.save(dest,t)
 r=dict(mint=mint,verifier_version=VERIFIER_VERSION,status='verified',creation_time=ct,creation_slot=t['creation_slot'],creation_signature=d['creation_signature'],peak_reserve_sol=result['peak_reserve_sol'],peak=peak,total_transaction_count=len(d['transactions']),successful_curve_trade_transactions=result['successful_curve_trade_transactions'],unique_qualified_outside_buyers=result['qualified_outside_buyers'],migration_status=bool(d['migration']),migration=d['migration'],required_post_migration_seconds=POST_MIGRATION_SECONDS,source_groups_checked=result['groups_checked'],verified_block_slots=len(verified_slots),raw_path=str(rawpath.relative_to(P)),bound_path=str(dest.relative_to(P)),candidate_source=candidate['source'])
 r.update(observation_metadata(d))
 R.save(auditpath,r);return r

def progress(selected,rejected,state):
 z=dict(state=state,target=TARGET,total_selected=len(selected),total_verified=len(selected),rejected_candidate_count=len(rejected),rejection_reasons=dict(collections.Counter(r['reason'] for r in rejected)),updated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
 R.save(P/'PROGRESS.json',z);R.save(P/'COHORT_MANIFEST.json',dict(complete=len(selected)==TARGET,date_window_UTC=['2026-08-18','2026-09-30'],selection='outcome-filtered active research cohort; not an unbiased launch population',coins=selected));R.save(P/'REJECTED_CANDIDATES.json',rejected)
 (P/'STATUS.md').write_text('# Active momentum cohort collection\n\n'+f"State: {state}. Verified {len(selected):,} / {TARGET:,}; rejected candidates {len(rejected):,}.\n\n"+'Creation window: August 18–September 30, 2026 UTC. Cached creation-sampled candidates are screened; these and authenticated migrations are interleaved across all 44 UTC days in deterministic order. Admission requires complete enhanced-RPC pagination, real creation, transaction indexes independently matched to finalized block signatures, all integer curve groups matching the approved adapter, account-level custody, at least 50 successful curve-trade transactions, 12 SOL peak or authenticated migration, 25 distinct noncreator buyers each with a >=0.05 SOL buy, and creator/deployer holdings <=10% of released circulating supply at the first peak transaction. Unknown ownership is rejected. Post-migration pool receipts cover '+str(POST_MIGRATION_SECONDS)+' seconds.\n\n'+'Creator and configured creator addresses are combined when different. Peak is measured after whole transactions. Failed receipts are preserved as no-ops. Cashback replaces the creator-equivalent charge where mutually exclusive; source fields are preserved. Candidate rejections are replacements, not silently dropped admitted coins. This outcome-filtered cohort is for conditional active-market research and cannot establish all-launch strategy profitability. No strategy simulations or live files are modified.\n\n'+f'RPC telemetry: RPC_EVENTS.jsonl; durable receipts: rpc/. Updated {z["updated_utc"]}.\n')
 print('PROGRESS',state,len(selected),'verified',len(rejected),'rejected',flush=True)

def main():
 args=argparse.ArgumentParser();args.add_argument('--workers',type=int,default=4);args.add_argument('--pilot',type=int,default=0);a=args.parse_args()
 freeze=P/'COLLECTION_SPEC.json'
 if not freeze.exists():R.save(freeze,dict(target=TARGET,start=START,end_exclusive=END,thresholds=dict(successful_curve_trade_transactions=50,peak_real_sol=12,qualified_outside_buyers=25,buy_min_sol=.05,max_creator_fraction_at_peak=.10),required_post_migration_seconds=POST_MIGRATION_SECONDS,provider_order=['alchemy','shyft','solami'],source_adapters={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'research/wallet_curve_entry_discovery_20261007/bind_curve_limits.py',ROOT/'research/wallet_curve_entry_discovery_20261007/curve_adapter.py']},selection_bias='retrospective activity/peak/breadth conditioned; not all-launch profitability validation'))
 selected=read(P/'COHORT_MANIFEST.json')['coins'] if (P/'COHORT_MANIFEST.json').exists() else []
 selected=[r for r in selected if r.get('verifier_version')==VERIFIER_VERSION]
 rejected=read(P/'REJECTED_CANDIDATES.json') if (P/'REJECTED_CANDIDATES.json').exists() else []
 rejected=[r for r in rejected if r.get('verifier_version')==VERIFIER_VERSION]
 seen={r['mint'] for r in selected+rejected};attempts=0;stop=False
 def batch(candidates):
  nonlocal attempts,stop
  pending=[];queued=set(seen)
  for c in candidates:
   if c['mint'] not in queued:pending.append(c);queued.add(c['mint'])
  for offset in range(0,len(pending),a.workers):
   if len(selected)>=TARGET or a.pilot and attempts>=a.pilot:stop=True;return
   chunk=pending[offset:offset+min(a.workers,TARGET-len(selected))]
   if a.pilot:chunk=chunk[:a.pilot-attempts]
   with concurrent.futures.ThreadPoolExecutor(a.workers) as ex:
    futures=[ex.submit(verify,c) for c in chunk]
    for c,f in zip(chunk,futures):
     attempts+=1;seen.add(c['mint'])
     try:selected.append(f.result())
     except Exception as e:
      reason=str(e)[:700];rejected.append(dict(mint=c['mint'],verifier_version=VERIFIER_VERSION,reason=reason,source=c['source']));print('REJECT',c['mint'][:10],reason,flush=True)
     progress(selected,rejected,'collecting')
 shortlist=P/'CACHED_SHORTLIST.json'
 if not shortlist.exists():
  sample=read(ROOT/'research/frozen_21day_validation_20261008/CREATION_SAMPLE.json')['chosen'];items=[x for x in sample if START<=x['creation_time']<END];rows=[]
  with concurrent.futures.ProcessPoolExecutor(a.workers) as ex:
   for i,r in enumerate(ex.map(screen,items,chunksize=20)):
    if r:rows.append(r)
    if (i+1)%500==0:print('SCREEN',i+1,'/',len(items),'shortlisted',len(rows),flush=True)
  rows.sort(key=lambda c:hashlib.sha256(('active_cohort_v1'+c['mint']).encode()).hexdigest());R.save(shortlist,rows)
 if a.pilot:batch(read(shortlist))
 # Daily migration census supplements the finite cached shortlist. Cycling
 # all dates first avoids building the entire sample from one busy day.
 if not stop:
  days=list(range(START,END,86400));daily=[]
  with concurrent.futures.ThreadPoolExecutor(a.workers) as executor:cs=list(executor.map(census,days))
  for day,c in zip(days,cs):
   rows=sorted(c['migrations'],key=lambda m:hashlib.sha256(('active_cohort_v1'+m['mint']).encode()).hexdigest());daily.append([dict(m,source='authenticated_migration_census') for m in rows]);print('CENSUS',day,len(rows),flush=True)
  # Merge cached candidates into their creation-day queues. Every day is
  # visited in each round before taking another candidate from that day.
  for c in read(shortlist):
   day_index=(c['creation_time']-START)//86400
   daily[day_index].insert(0,c)
  combined=[]
  for i in range(max(map(len,daily),default=0)):
   combined.extend(rows[i] for rows in daily if i<len(rows))
  batch(combined)
 state='complete' if len(selected)==TARGET else ('pilot_complete' if a.pilot else 'candidate_pool_exhausted')
 progress(selected,rejected,state)
 if len(selected)==TARGET:
  if len({r['mint'] for r in selected})!=TARGET:raise ValueError('duplicate_admitted_mint')
  R.save(P/'COLLECTION_COMPLETE.json',dict(total_selected=TARGET,total_verified=TARGET,dropped_admitted_coins=0,rejected_candidates_replaced=len(rejected),whole_source_parity_pass_rate=1.0,complete=True))
 elif not a.pilot:raise RuntimeError('Insufficient verified candidates; collection remains incomplete')
if __name__=='__main__':main()
