"""Receipt-parity-gated curve-only v3 dispatch for the approved adapter.

Official instruction binding supplies budgets and guards. This extends the
same integer execution paths, without changing older instructions. A v3
completion with a post-completion pool leg remains explicitly unresolved in
the approved engine. Source parity is mandatory before reporting outcomes.
"""
import hashlib, inspect, pathlib, sys
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'research/wallet_curve_entry_discovery_20261007'))
import curve_adapter as A
SOURCE_SHA256=hashlib.sha256(inspect.getsource(A.apply).encode()).hexdigest()

def install():
 if getattr(A.apply,'_curve_v3_dispatch',False):return A.apply
 source=inspect.getsource(A.apply)
 replacements=[
  ("if name in ('buy','buy_v2'):","if name in ('buy','buy_v2','buy_v3'):"),
  ("elif name in ('buy_exact_sol_in','buy_exact_quote_in','buy_exact_quote_in_v2'):","elif name in ('buy_exact_sol_in','buy_exact_quote_in','buy_exact_quote_in_v2','buy_exact_quote_in_v3'):"),
  ("name=e['ix_name']", "name=e['ix_name']\n   if name.endswith('_v3') and (e.get('real_token_reserves')==0 or (name=='buy_v3' and e['tokens_raw']>=z['rtokens_raw'])):return st,hist,cf,None,'v3_completion_pool_leg_coverage_required'"),
  ("if not r:return revert('unquotable_exact_input')", "if name.endswith('_v3') and r and r[1]>=z['rtokens_raw']:return st,hist,cf,None,'v3_counterfactual_completion_pool_leg_coverage_required'\n    if not r:return revert('unquotable_exact_input')")]
 for old,new in replacements:
  assert source.count(old)==1,'approved v3 dispatch anchor changed'
  source=source.replace(old,new)
 namespace=dict(A.__dict__);exec(compile(source,'<approved receipt-bound curve v3 dispatch>','exec'),namespace)
 extended=namespace['apply'];extended._curve_v3_dispatch=True
 A.apply=extended
 return extended
