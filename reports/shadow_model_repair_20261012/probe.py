from pathlib import Path
import os, re, json, subprocess, collections
root=Path(__file__).resolve().parents[2]
folder=Path(__file__).resolve().parent/'feed_probe_final'
folder.mkdir(exist_ok=True)
a=(root/'AGENTS.md').read_text()
env=os.environ.copy()
for k in ('SOL_USD_PRICE','GHOST_FAKE_HISTORY_BOOTSTRAP_PATH','GRPC_SOURCES','TRITON_GRPC_URL','TRITON_API_KEY'):
    env.pop(k,None)
env.update(SOLANA_RPC_URL=re.search(r'https://solana-mainnet.g.alchemy.com/v2/[^`\s]+',a).group(),SOLAMI_GRPC_URL='https://grpc.solami.dev',SOLAMI_API_KEY=re.search(r'sk_[A-Za-z0-9_-]+',a).group(),VM_ID='ghost-calc-fix-final-readonly-probe',PAPER_BANKROLL_SOL='15',DISABLE_STRATEGIES='S1,S2,S3,S4,S5',ENABLE_CIRCUIT_BREAKERS='false',WHITELIST_KOL_WALLETS='false')
paths={'STATE':'state.json','SUMMARY':'summary.json','TRADES':'trades.jsonl','OBSERVATIONS':'observations.jsonl','INTENTS':'intents.jsonl','HOLDER_SCREEN':'holders.jsonl','SHIELDED':'shielded.jsonl','VARIANT_SIGNALS':'variant.jsonl','FORCE_SELLS':'force.jsonl','SESSION_RESET':'reset.json','CIRCUIT_BREAKER_CONFIG':'breaker.json','AMM_EVIDENCE':'amm.jsonl','FAILED_ACTIVITY':'failed.jsonl','FAKE_DETECTOR':'fake.jsonl'}
for key,name in paths.items(): env['GHOST_'+key+'_PATH']=str(folder/name)
with (folder/'runtime.log').open('w') as f:
    result=subprocess.run(['timeout','30s',str(root/'target/release/curve_detector')],cwd=root,env=env,stdout=f,stderr=subprocess.STDOUT)
summary=json.loads((folder/'summary.json').read_text()) if (folder/'summary.json').exists() else {}
checkpoint=json.loads((folder/'state.json').read_text()) if (folder/'state.json').exists() else {}
rows=[json.loads(line) for line in (folder/'observations.jsonl').read_text().splitlines()] if (folder/'observations.jsonl').exists() else []
curves=checkpoint.get('curves',{})
if not isinstance(curves,dict): curves={}
reasons=collections.Counter(c.get('tracking_error') or ('eligible' if c.get('creation_receipt_seen') and c.get('fee_policy_known') else 'unsupported_or_missing_creation') for c in curves.values())
checks={'exit_code':result.returncode,'observations':len(rows),'creations':sum(len(r.get('creators',[])) for r in rows),'trade_events':sum(len(r.get('events',[])) for r in rows),'complete_instruction_events':sum(e.get('pump_instruction',{}).get('unknown_reason') is None for r in rows for e in r.get('events',[]) if e.get('pump_instruction')),'tracking_counts':summary.get('tracking_coverage_counts'),'checkpoint_tracking_reasons':dict(reasons),'sol_usd_price':summary.get('sol_usd_price'),'sol_usd_price_source':summary.get('sol_usd_price_source'),'sol_usd_price_source_at_ms':summary.get('sol_usd_price_source_at_ms'),'active_positions':summary.get('active_positions_count'),'closed_trades':summary.get('total_closed_trades'),'calculation_model_revision':summary.get('calculation_model_revision'),'paper_entries_disabled':True}
(folder/'CHECKS.json').write_text(json.dumps(checks,indent=2)+'\n')
print(json.dumps(checks,indent=2))
