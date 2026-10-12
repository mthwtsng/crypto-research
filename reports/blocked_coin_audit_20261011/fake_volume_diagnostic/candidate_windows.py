#!/usr/bin/env python3
"""Descriptive first S2/S4 source candidate windows on the frozen receipt tape."""
import csv, json, math, statistics
from collections import Counter, defaultdict
from pathlib import Path
HERE=Path(__file__).resolve().parent; ROOT=HERE.parent
SRC=ROOT/'observations_slim.jsonl'; CAND=ROOT/'candidate_rows.jsonl'
CUTOFF=int(json.loads((ROOT/'MANIFEST.json').read_text())['cutoff_ms'])
HORIZON=120_000; WINDOW=10_000; SOL='11111111111111111111111111111111'
def spot(e):
    if not e['vsol'] or not e['vtokens']: return None
    return e['vsol']/e['vtokens']
def pct(xs,q):
    if not xs:return None
    xs=sorted(xs); p=(len(xs)-1)*q; lo=int(p); hi=math.ceil(p)
    return xs[lo] if hi==lo else xs[lo]*(hi-p)+xs[hi]*(p-lo)
def med(xs): return statistics.median(xs) if xs else None

def main():
    paths=defaultdict(list); creator_by_mint={}; sig_index={}; receipts=0
    with SRC.open() as fh:
      for seq,line in enumerate(fh):
        o=json.loads(line); receipts+=1; ms=int(o.get('received_at_ms') or 0)
        slot=int(o.get('slot') or 0); txi=int(o.get('transaction_index') or 0); sig=o.get('signature')
        for pair in o.get('creators') or []:
          if isinstance(pair,(list,tuple)) and len(pair)>=2: creator_by_mint.setdefault(str(pair[0]),str(pair[1]))
        receipt_events=o.get('events') or []
        last_event_by_mint={str(e.get('mint')):i for i,e in enumerate(receipt_events) if e.get('mint')}
        for ei,e in enumerate(receipt_events):
          mint=e.get('mint');
          if not mint: continue
          ev={'seq':seq,'ei':ei,'ms':ms,'slot':slot,'txi':txi,'user':str(e.get('user') or ''),'creator':str(e.get('creator') or ''),'buy':bool(e.get('is_buy')),'sol':int(e.get('sol_raw') or 0)/1e9,'tokens':int(e.get('tokens_raw') or 0),'rsol':int(e.get('rsol_raw') or 0),'rtokens':int(e.get('rtokens_raw') or 0),'vsol':int(e.get('vsol_raw') or 0),'vtokens':int(e.get('vtokens_raw') or 0),'supported':bool(e.get('supported_sol_quote')) and e.get('quote_mint')==SOL,'receipt_final_state':ei==last_event_by_mint.get(str(mint))}
          paths[str(mint)].append(ev)
          if sig: sig_index[(str(sig),str(mint))]=ev
    # Predeclare candidate selection before computing descriptive features/outcomes.
    chosen={}; counts=Counter()
    with CAND.open() as fh:
      for line in fh:
        d=json.loads(line); fam=d.get('family'); mint=str(d.get('mint') or '')
        if fam not in ('S2','S4') or d.get('creation_observed') is not True: continue
        counts[fam]+=1
        key=(fam,mint); ms=int(d.get('timestamp_ms') or (d.get('receipt') or {}).get('received_at_ms') or 0)
        if not ms: continue
        if key not in chosen or ms < chosen[key][0]: chosen[key]=(ms,d)
    output=[]
    for (fam,mint),(ms,d) in chosen.items():
      sig=str(d.get('signature') or ((d.get('receipt') or {}).get('signature') or ''))
      anchor=sig_index.get((sig,mint))
      if anchor is None:
        # Match by exact signal slot/index/time when candidate stream omitted signature.
        slot=int(d.get('slot') or 0); txi=int(d.get('transaction_index') or 0)
        anchor=next((e for e in paths.get(mint,[]) if e['ms']==ms and e['slot']==slot and e['txi']==txi and e['receipt_final_state']),None)
      if anchor is None or not anchor['supported'] or not spot(anchor):
        output.append({'family':fam,'mint':mint,'label':'anchor_join_missing'}); continue
      evs=[e for e in paths[mint] if e['supported']]
      anchor_pair=(anchor['seq'],anchor['ei']); prior=[e for e in evs if (e['seq'],e['ei'])<=anchor_pair and ms-WINDOW<=e['ms']<=ms]
      buys=defaultdict(float); buycounts=Counter(); sizecounts=Counter(); sizevol=Counter(); seconds=Counter(); slots=Counter(); grossbuy=grosssell=0.; meaningful=set()
      for e in prior:
        if e['buy']:
          grossbuy+=e['sol']
          if e['user'] and e['user']!=e['creator']:
            buys[e['user']]+=e['sol']; buycounts[e['user']]+=1
            if e['sol']>=.05: meaningful.add(e['user'])
            b=int(math.floor(e['sol']*100+.5)); sizecounts[b]+=1; sizevol[b]+=e['sol']
            seconds[(e['ms']-(ms-WINDOW))//1000]+=e['sol']; slots[e['slot']]+=e['sol']
        else: grosssell+=e['sol']
      outside=sum(buys.values()); repeated={w for w,n in buycounts.items() if n>=2}; top3=sorted(buys.values(),reverse=True)[:3]
      prior_res=[e for e in evs if e['ms']<ms-WINDOW]
      rdelta=(anchor['rsol']-(prior_res[-1]['rsol'] if prior_res else 0))/1e9
      creator=creator_by_mint.get(mint); ct=0
      if creator:
        for e in evs:
          if (e['seq'],e['ei'])>anchor_pair: break
          if e['user']==creator: ct+=(e['tokens'] if e['buy'] else -e['tokens']); ct=max(0,ct)
      f={'family':fam,'mint':mint,'candidate_at_ms':ms,'candidate_age_s':None,'candidate_reserve_sol':anchor['rsol']/1e9,'window_events':len(prior),'window_buy_sol':grossbuy,'window_sell_sol':grosssell,'sell_buy_churn':grosssell/grossbuy if grossbuy else None,'meaningful_buyers_ge_0_05':len(meaningful),'repeat_buyer_volume_share':sum(buys[w] for w in repeated)/outside if outside else None,'top3_buyer_volume_share':sum(top3)/outside if outside else None,'modal_size_event_share':max(sizecounts.values())/sum(sizecounts.values()) if sizecounts else None,'top3_size_bin_event_share':sum(sorted(sizecounts.values(),reverse=True)[:3])/sum(sizecounts.values()) if sizecounts else None,'max_1s_buy_share':max(seconds.values())/outside if outside else None,'max_slot_buy_share':max(slots.values())/outside if outside else None,'reserve_delta_vs_gross_buy':rdelta/grossbuy if grossbuy else None,'creator_observed_residual_supply_pct':ct/1e15*100 if creator else None,'anchor_spot':spot(anchor)}
      if CUTOFF-ms<HORIZON: f['label']='censored_recent'; output.append(f); continue
      fut=[e for e in evs if e['receipt_final_state'] and (e['seq'],e['ei'])>anchor_pair and e['ms']<=ms+HORIZON]
      base=f['anchor_spot']; peak=base; r125=False; r150=False; collapse=None; migration=None; maxdd=0.
      peak_real=anchor['rsol']/1e9; min_after_real_peak=peak_real; max_real_dd=0.
      for e in fut:
        p=spot(e)
        if p:
          peak=max(peak,p); r125|=p>=base*1.25; r150|=p>=base*1.5; maxdd=max(maxdd,1-p/peak if peak else 0)
          if r125 and p<=peak*.2 and collapse is None: collapse=e
        real=e['rsol']/1e9
        if real>=peak_real: peak_real=real; min_after_real_peak=real
        else:
          min_after_real_peak=min(min_after_real_peak,real)
          if peak_real: max_real_dd=max(max_real_dd,1-min_after_real_peak/peak_real)
        if e['rtokens']==0: migration=e; break
      f.update({'followup_trade_events':len(fut),'peak_spot_multiple':peak/base if base else None,'max_observed_drawdown_pct':maxdd*100,'peak_real_reserve_after_anchor_sol':peak_real,'minimum_real_reserve_after_peak_sol':min_after_real_peak,'max_real_reserve_drawdown_pct':max_real_dd*100,'real_reserve_drain_ge_90pct':max_real_dd>=.90,'reached_1_25x':r125,'reached_1_5x':r150,'migrated_ms':migration['ms'] if migration else None})
      if collapse: f['label']='rise_then_80pct_collapse_observed'
      elif migration: f['label']='censored_migration'
      elif r150: f['label']='curve_tape_1_5x_no_observed_80pct_drawdown'
      elif not fut: f['label']='no_postcandidate_receipt_observed'
      else: f['label']='other_observed_path'
      output.append(f)
    fields=sorted({k for r in output for k in r})
    with (HERE/'candidate_windows.csv').open('w',newline='') as fh:
      w=csv.DictWriter(fh,fieldnames=fields);w.writeheader();w.writerows(output)
    labels=Counter(r['label'] for r in output); groups={}
    feats=['window_buy_sol','window_sell_sol','sell_buy_churn','meaningful_buyers_ge_0_05','repeat_buyer_volume_share','top3_buyer_volume_share','modal_size_event_share','top3_size_bin_event_share','max_1s_buy_share','max_slot_buy_share','reserve_delta_vs_gross_buy','creator_observed_residual_supply_pct']
    for label in ('rise_then_80pct_collapse_observed','curve_tape_1_5x_no_observed_80pct_drawdown','other_observed_path'):
      rows=[r for r in output if r.get('label')==label]; groups[label]={'n':len(rows),'features':{}}
      for name in feats:
        vals=[float(r[name]) for r in rows if isinstance(r.get(name),(int,float))]
        groups[label]['features'][name]={'n':len(vals),'p25':pct(vals,.25),'median':med(vals),'p75':pct(vals,.75)}
    drain_labels=Counter(r.get('label') for r in output if r.get('real_reserve_drain_ge_90pct'))
    summary={'frozen_cutoff_utc':'2026-10-11T22:25:33.517242059+00:00','receipt_source':'observations_slim.jsonl','candidate_source':'candidate_rows.jsonl','candidate_selection':'creation_observed=true; families S2/S4; first received timestamp per mint-family, selected before outcome labels','candidate_counts_before_dedup':dict(counts),'selected_anchor_count':len(output),'labels':dict(labels),'observed_real_reserve_drain_ge_90pct_by_label':dict(drain_labels),'groups':groups,'ordering':'live receive/file order; per-mint same-slot index inversions audited absent; fine received timing uncalibrated','limits':['This subset is conditional on source strategy candidate generation and is not a universe sample.','Positive labels are curve-tape descriptors only, not proof of durable paths; sparse per-mint trades do not establish quiet/no-rug intervals.','Graduation within 120s is censored; no post-migration AMM tape.','Patterns cannot identify bots, fake volume, common ownership, or organic participation.','The separate real-reserve drawdown metric is curve reserve-state behavior, not net liquidity available to exit at executable price.','No classifier, threshold tuning, profitability estimate, replay, or live-filter recommendation.']}
    (HERE/'candidate_summary.json').write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'candidate_counts_before_dedup':dict(counts),'selected_anchor_count':len(output),'labels':dict(labels),'groups':groups},indent=2))
if __name__=='__main__': main()
