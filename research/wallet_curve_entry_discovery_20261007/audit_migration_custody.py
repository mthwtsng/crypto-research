"""Authenticate atomic source migration deposits, token continuity and freeze.

Historical pool openings are evidence, not permission to force a changed
counterfactual curve into that pool. No invented deposits or timing.
"""
import gzip,json,pathlib,sys
import amm_counterparty as C
import receipt_custody as RC
P=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,'/tmp/amm_research_deps');import ijson

def audit(poolfile):
 t=json.load(gzip.open(poolfile,'rt'));mint=t['mint'];m=dict(t['migration']);curve=json.load(gzip.open(P/'merged_account_tapes'/(mint+'.json.gz'),'rt'));complete=next(g for g in curve['groups'] if g['source_status']=='succeeded' and g['state']['rtokens_raw']==0);genesis=t['groups'][0];errors=[]
 old_signature=m['signature']
 # Repeated successful migrate calls can be idempotent no-ops. The pool's
 # authentic CreatePool/InitBoost receipt establishes its tradable opening.
 m.update(signature=genesis['signature'],slot=genesis['slot'],index=genesis['index'],time=genesis['time'])
 if (complete['slot'],complete['index'])>=(m['slot'],m['index']):errors.append('migration_before_completion')
 tx=None
 with gzip.open(P/'continuation_pools'/poolfile.name,'rb') as src:
  for row in ijson.items(src,'transactions.item'):
   if row['transaction']['signatures'][0]==m['signature']:tx=row;break
 if tx is None:raise ValueError('missing_migration_receipt')
 events=C.A.events(tx)
 if not any(e['kind']=='CreatePoolEvent' and e.get('pool')==t['pool'] and e.get('base_mint')==mint for e in events):errors.append('opening_not_authenticated_pool_creation')
 parsed=RC.parse_receipt(tx,[],mint);balances={ac:r.get('pre_raw',0) for ac,r in parsed['accounts'].items()};pretotal=sum(balances.values())
 # At migration a curve-vault -> temporary -> pool-vault chain must reconcile
 # in instruction order, including accounts created and closed in this group.
 for tr in parsed['transfers']:
  src,dst,n=tr['source_account'],tr['destination_account'],tr['raw'];balances[src]=balances.get(src,0)-n;balances[dst]=balances.get(dst,0)+n
  if balances[src]<0:errors.append('negative_migration_token_account')
 for ac,r in parsed['accounts'].items():
  if balances.get(ac,0)!=r.get('post_raw',0):errors.append('migration_token_post_balance_mismatch:'+ac)
 if sum(balances.values())!=pretotal:errors.append('migration_token_supply_changed')
 if balances.get(m['base_vault'])!=genesis['state']['base']:errors.append('base_deposit_does_not_match_opening')
 effective=genesis['state']['quote']+genesis['state']['virtual']
 if not genesis['trades'] and effective!=genesis['before']['quote']:errors.append('boost_shift_changed_effective_opening_quote')
 # With swaps in the migration transaction, actual deposits are the genesis
 # prestate; its poststate additionally includes those buys/sells and fees.
 deposit=genesis['before']['quote']
 # All non-vault holders keep token custody across this atomic transition.
 moved_accounts={a for tr in parsed['transfers'] for a in (tr['source_account'],tr['destination_account'])}
 historical=__import__('build').inventory([g for g in curve['groups'] if g['source_status']=='succeeded' and (g['slot'],g['index'])<=(complete['slot'],complete['index'])])
 changed_holders=[ac for ac,n in historical.items() if n and ac in moved_accounts]
 if changed_holders:errors.append('market_holder_account_moved_during_migration')
 if not errors:
  t['migration']=m;t['coverage']['migration']=m
  with gzip.open(poolfile,'wt',compresslevel=1) as out:json.dump(t,out)
 return dict(mint=mint,pool=t['pool'],completion_position=[complete['slot'],complete['index']],migration_position=[m['slot'],m['index']],opening_signature=m['signature'],previous_migration_signature=old_signature,late_retry_anchor_corrected=old_signature!=m['signature'],freeze_seconds=m['time']-complete['block_time'],curve_real_SOL=complete['state']['rsol_raw']/1e9,opening_real_SOL=genesis['state']['quote']/1e9,opening_virtual_SOL=genesis['state']['virtual']/1e9,measured_migration_quote_difference_lamports=complete['state']['rsol_raw']-deposit,opening_swap_count=len(genesis['trades']),base_tokens_raw=genesis['state']['base'],transfers_checked=len(parsed['transfers']),holder_accounts_retained=sum(n>0 for n in historical.values()),errors=errors,pass_all=not errors,scope='authenticated historical atomic custody only; counterfactual completion/timing and changed failed routers require separate execution checks')

def main():
 rows=[]
 for f in sorted((P/'normalized_amm_tapes').glob('*.gz')):
  a=audit(f);rows.append(a);print('MIGRATION_CUSTODY',a['mint'][:8],a['pass_all'],a['errors'],flush=True)
 (P/'MIGRATION_CUSTODY_AUDIT.json').write_text(json.dumps(dict(audits=rows),indent=2)+'\n')
if __name__=='__main__':main()
