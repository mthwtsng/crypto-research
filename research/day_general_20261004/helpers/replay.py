import build
L=1_000_000_000
def fee(q,bps):return (q*bps+9999)//10000


def buy(st,ticket):
    budget=round(ticket*L);lo,hi=0,budget
    while lo<hi:
        q=(lo+hi+1)//2
        if q+fee(q,st['fee_bps'])+fee(q,st['creator_fee_bps'])<=budget:lo=q
        else:hi=q-1
    n=st['vtokens_raw']*lo//(st['vsol_raw']+lo)
    return (lo,n) if n>0 and n<=st['rtokens_raw'] else None


def sell(st,n):
    q=st['vsol_raw']*n//(st['vtokens_raw']+n)
    if n<=0 or q>st['rsol_raw']:return None
    return q-fee(q,st['fee_bps'])-fee(q,st['creator_fee_bps']),q


def moved(st,q,n,buying=True):
    z=dict(st);d=1 if buying else -1
    z['vsol_raw']+=d*q;z['rsol_raw']+=d*q;z['vtokens_raw']-=d*n;z['rtokens_raw']-=d*n
    return z


def apply(st,group,hist,cf):
    z=dict(st);h=dict(hist);c=dict(cf);adjusted=[]
    adjusted_ops=[]
    if group.get('custody_error'):return st,hist,cf,None,'unverified_custody'
    for op in build.ops(group):
        if op['kind']=='transfer':
            src,dst,raw=op['from_owner'],op['to_owner'],op['raw']
            if src==dst or raw==0:continue
            old,held=h.get(src,0),c.get(src,0)
            if old<=0 or raw>old:return st,hist,cf,None,'unknown_actor_inventory'
            amount=held if raw==old else held*raw//old
            h[src]-=raw;h[dst]=h.get(dst,0)+raw;c[src]-=amount;c[dst]=c.get(dst,0)+amount
            adjusted_ops.append(dict(op,raw=amount));continue
        if op['kind']!='trade':return st,hist,cf,None,'unverified_custody'
        e=op['event'];w=op['owner'];old=h.get(w,0);held=c.get(w,0)
        if e['buy']:
            if e['ix_name'] in ['buy','buy_v2']:
                n=e['tokens_raw']
                if n>=z['vtokens_raw'] or n>z['rtokens_raw']:return st,hist,cf,None,'counterparty_liquidity'
                q=z['vsol_raw']*n//(z['vtokens_raw']-n)+1
            elif e['ix_name'] in ['buy_exact_sol_in','buy_exact_quote_in','buy_exact_quote_in_v2']:
                q=e['sol_raw'];n=z['vtokens_raw']*q//(z['vsol_raw']+q)
                if n<=0 or n>z['rtokens_raw']:return st,hist,cf,None,'counterparty_liquidity'
            else:return st,hist,cf,None,'unsupported_buy_instruction'
            z=moved(z,q,n);h[w]=old+e['tokens_raw'];c[w]=held+n
        else:
            observed=e['tokens_raw']
            if old<=0 or observed>old:return st,hist,cf,None,'unknown_actor_inventory'
            n=held if observed==old else held*observed//old
            quote=sell(z,n)
            if quote is None:return st,hist,cf,None,'counterparty_liquidity'
            q=quote[1];z=moved(z,q,n,False);h[w]=old-observed;c[w]=held-n
        z['fee_bps']=e['fee_bps'];z['creator_fee_bps']=e['creator_fee_bps']
        adjusted.append(dict(e,tokens_raw=n,sol_raw=q,inventory_owner=w))
        adjusted_ops.append(dict(op,event=adjusted[-1]))
    return z,h,c,dict(group,events=adjusted,state=z,custody_ops=adjusted_ops),None
