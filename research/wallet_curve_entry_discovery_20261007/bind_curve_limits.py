"""Bind original instruction budgets/limits to each retained curve trade event."""
import collections,gzip,hashlib,json,pathlib,sys
P=pathlib.Path(__file__).resolve().parent;R=P.parents[1]
sys.path.insert(0,str(R/'research/day_general_20261004/helpers'));import decoder as D
I={bytes(i['discriminator']):i for i in D.IDL['instructions']}
TRADE={'buy','buy_v2','buy_exact_sol_in','buy_exact_quote_in','buy_exact_quote_in_v2','sell','sell_v2','buy_v3','buy_exact_quote_in_v3','sell_v3'}
for name in TRADE:I.setdefault(hashlib.sha256(('global:'+name).encode()).digest()[:8],dict(name=name))
def raw(s):
 n=0
 for c in s:n=n*58+D.ALPHABET.index(c)
 return b'\0'*(len(s)-len(s.lstrip('1')))+n.to_bytes((n.bit_length()+7)//8,'big')
def bind(t,mint):
 top=t['transaction']['message']['instructions'];inner={g['index']:g['instructions'] for g in t['meta'].get('innerInstructions',[]) or []};found=[]
 for k,ix in enumerate(top):
  for a in [ix]+inner.get(k,[]):
   if a.get('programId')!=D.PUMP:continue
   data=raw(a.get('data',''));i=I.get(data[:8]);accounts=a.get('accounts',[])
   if not i or i['name'] not in TRADE or mint not in accounts:continue
   if len(data)<24:raise ValueError('short_trade_instruction')
   vals=[int.from_bytes(data[o:o+8],'little') for o in (8,16)]
   key={'buy':'max_cost_raw','buy_v2':'max_cost_raw','buy_v3':'max_cost_raw','sell':'min_quote_raw','sell_v2':'min_quote_raw','sell_v3':'min_quote_raw'}.get(i['name'])
   fields={key:vals[1]} if key else dict(budget_raw=vals[0],min_tokens_raw=vals[1])
   found.append(dict(name=i['name'],fields=fields,encoded_tokens_or_budget=vals[0]))
 return found

def main():
 audits=[];errors=[]
 for f in sorted((P/'repaired_curve_tapes').glob('*.gz')):
  t=json.load(gzip.open(f,'rt'));mint=t['mint'];source=P/'custody/custody_extended'/f.name
  if not source.exists():source=P/'custody_inputs'/f.name
  d=json.load(gzip.open(source,'rt'));by={r['transaction']['signatures'][0]:r for r in d['transactions']};count=0
  for g in t['groups']:
   if not g['events']:continue
   params=bind(by[g['signature']],mint)
   if len(params)!=len(g['events']):errors.append(dict(mint=mint,signature=g['signature'],events=len(g['events']),instructions=len(params)));continue
   for e,b in zip(g['events'],params):
    if e['buy']!=b['name'].startswith('buy'):raise ValueError('side_bind')
    e.update(b['fields']);e['instruction_name']=b['name'];count+=1
   # custody ops and events were deserialized separately: update both copies.
   queue=iter(g['events'])
   for op in g['custody_ops']:
    if op['kind']=='trade':op['event']=next(queue)
  with gzip.open(P/'bound_curve_tapes'/f.name,'wt',compresslevel=1) as o:json.dump(t,o)
  audits.append(dict(mint=mint,bound_trades=count))
 (P/'CURVE_LIMIT_BINDINGS.json').write_text(json.dumps(dict(audits=audits,errors=errors),indent=2)+'\n');print('BOUND',len(audits),sum(a['bound_trades'] for a in audits),'errors',len(errors));print(errors[:3])
if __name__=='__main__':
 (P/'bound_curve_tapes').mkdir(exist_ok=True);main()
