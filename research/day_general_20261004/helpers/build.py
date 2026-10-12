import collections
def ops(g):
    return g.get('custody_ops',[dict(kind='trade',event=e,owner=e.get('inventory_owner',e['user'])) for e in g['events']])


def inventory(groups):
    h=collections.Counter()
    for g in groups:
        if g.get('custody_error'):raise ValueError('unverified_custody')
        for op in ops(g):
            if op['kind']=='transfer':
                src,dst,n=op['from_owner'],op['to_owner'],op['raw']
                if src==dst or n==0:continue
                if h[src]<n:raise ValueError('negative_curve_inventory')
                h[src]-=n;h[dst]+=n
            elif op['kind']=='trade':
                e=op['event'];w=op['owner'];h[w]+=e['tokens_raw'] if e['buy'] else -e['tokens_raw']
                if h[w]<0:raise ValueError('negative_curve_inventory')
            else:raise ValueError('unverified_custody')
    return h
