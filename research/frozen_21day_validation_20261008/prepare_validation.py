"""Strict instruction-bound, custody-repaired signal preparation for frozen sample."""
import concurrent.futures,gzip,importlib.util,json,pathlib,sys
import rpc_pool as R
import collect_validation as C
P=R.OUT;ROOT=R.ROOT
sys.path.insert(0,str(ROOT/'research/day_general_20261004'));import repair_helpers as H
sys.path.insert(0,str(ROOT/'research/wallet_curve_entry_discovery_20261007'));import bind_curve_limits as LIMIT,merge_curve_receipts as ACCOUNT,curve_adapter as A
sys.path.insert(0,str(ROOT/'research/core_plan_audit_20261007'));import signals as S
H.rpc=R.rpc;H.save=R.save;H.HERE=P/'custody';H.make=C.PREP.make
oldgap=H.gap
def curve_only(t):
 stop=next((i+1 for i,g in enumerate(t['groups']) if g['state']['rtokens_raw']==0),len(t['groups']))
 return dict(t,groups=t['groups'][:stop])
H.gap=lambda t:oldgap(curve_only(t))

def build(path,force=False):
 mint=path.name.split('.')[0];dest=P/'bound_curve_tapes'/path.name;audit=P/'prepare_audits'/(mint+'.json')
 if audit.exists() and not force:return json.load(open(audit))
 d=json.load(gzip.open(path,'rt'));failed=[tx for tx in d['transactions'] if tx['meta']['err'] is not None];d=dict(d,transactions=[tx for tx in d['transactions'] if tx['meta']['err'] is None])
 source=P/'custody_inputs'/path.name;R.save(source,d)
 t,a=C.PREP.make(d)
 if t is None:raise ValueError(a)
 t=curve_only(t)
 custody=dict(status='supported',passes=[])
 if H.gap(t):
  custody=H.one(source);repaired=H.HERE/'custody_extended'/path.name
  if repaired.exists():d=json.load(gzip.open(repaired,'rt'));t,a=C.PREP.make(d);t=curve_only(t)
 if H.gap(t):raise ValueError(dict(reason='source_inventory_gap',mint=mint,custody=custody))
 # Detect on wallet custody, only the predeclared first30minute entry window.
 decision=dict(t,groups=[g for g in t['groups'] if g['block_time']<=d['decision_end_time']],end_time=d['decision_end_time'])
 ss,ee=S.detect(decision)
 if ee:raise ValueError(ee)
 # Replace S3 dip with causal two distinct buy groups, preserving the original
 # one eligible setup per family/mint policy.
 final=[]
 for s in ss:
  if s['rule']!='s3_deadman':final.append(s);continue
  i=s['index'];first=None;groups=0
  for g in decision['groups'][i+1:]:
   if g['slot']>s['slot']+2 or g['state']['rtokens_raw']==0:break
   buyers={e['user'] for e in g['events'] if e['buy'] and e['user']!=t['creator'] and e['sol_raw']>=50_000_000}
   if buyers:
    groups+=1
    if first is None:first=buyers
   if groups>=2 and buyers-first:
    reserve=g['state']['rsol_raw']/1e9
    if 8<=reserve<=18:final.append(dict(s,original_signal_signature=s['signal_signature'],original_signal_slot=s['slot'],signal_signature=g['signature'],slot=g['slot'],time=g['block_time'],reserve=reserve,confirmation_buy_groups=groups))
    break
 # Cashback redirects the creator-equivalent charge to a deferred reward.
 # Preserve the decoded fields and charge its full recorded amount; do not
 # invent a cashback claim or cash credit for our hypothetical wallet.
 effective=None;cashback_events=0
 for g in t['groups']:
  for e in g['events']:
   creator=e['creator_fee_bps'];cashback=e.get('cashback_fee_basis_points',0)
   if creator and cashback:raise ValueError('simultaneous_creator_cashback_requires_separate_rounding')
   e['decoded_creator_fee_bps']=creator;e['creator_fee_bps']=creator+cashback
   effective=creator+cashback;cashback_events+=bool(cashback)
  if effective is not None:g['state']['creator_fee_bps']=effective
 by={tx['transaction']['signatures'][0]:tx for tx in d['transactions']}
 for g in t['groups']:
  limits=LIMIT.bind(by[g['signature']],mint)
  if len(limits)!=len(g['events']):raise ValueError('instruction_event_binding_count')
  for e,b in zip(g['events'],limits):e.update(b['fields']);e['instruction_name']=b['name']
 t['groups']=[ACCOUNT.account_group(g,by[g['signature']],mint) for g in t['groups']];t['inventory_key']='token_account'
 # Baseline replay must match source states before interventions.
 gs=t['groups'];st=dict(gs[0]['state']);hist=A.build.inventory(gs[:1]);cf=dict(hist);checked=0
 for g in gs[1:]:
  z,hh,cc,adjusted,err=A.apply(st,g,hist,cf)
  if err or any(z[k]!=g['state'][k] for k in ['vsol_raw','vtokens_raw','rsol_raw','rtokens_raw']) or hh!=cc or z.get('source_reverts',0):raise ValueError(dict(reason='whole_source_parity',signature=g['signature'],error=err))
  st,hist,cf=z,hh,cc;checked+=1
 R.save(dest,t);R.save(P/'signals_by_mint'/(mint+'.json'),final)
 R.save(P/'failed_curve_intents'/path.name,dict(mint=mint,transactions=failed,interpretation='historical no-op receipts, never credited as successful fills'))
 result=dict(mint=mint,status='prepared',creation_verified=True,source_groups_checked=checked,cashback_events=cashback_events,source_receipts=len(d['transactions']),failed_receipts=len(failed),custody=custody,signals=final)
 R.save(audit,result);return result

def main():
 sample=json.load(open(P/'CREATION_SAMPLE.json'));expected={x['mint'] for x in sample['chosen']};paths=[P/'raw_curves'/(m+'.json.gz') for m in sorted(expected)]
 audits=[];errors=[]
 with concurrent.futures.ThreadPoolExecutor(4) as ex:
  futures={ex.submit(build,f):f for f in paths}
  for f in concurrent.futures.as_completed(futures):
   try:audits.append(f.result())
   except Exception as e:errors.append(dict(mint=futures[f].name.split('.')[0],error=str(e)))
   if (len(audits)+len(errors))%25==0:print('PREPARE',len(audits),len(errors),'/',len(paths),flush=True);R.save(P/'PREPARE_PROGRESS.json',dict(total=len(paths),prepared=len(audits),errors=errors))
 R.save(P/'PREPARE_COMPLETE.json',dict(total=len(paths),prepared=len(audits),errors=errors,audits=audits))
 if errors:raise RuntimeError('Do not omit failed sampled coins; repair prepare errors')
 R.save(P/'SIGNALS.json',[s for a in audits for s in a['signals']]);print('PREPARE_COMPLETE',len(audits),flush=True)
if __name__=='__main__':main()
