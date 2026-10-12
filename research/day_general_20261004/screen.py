"""Frozen causal activity screen plus existing four strategy predicates."""
import collections,inspect,sys,pathlib
ROOT=pathlib.Path(__file__).resolve().parents[2]
import base_engine as C
src=inspect.getsource(C.O.detect_signals).replace('for g_r in gs if','for g_r in gs[:i + 1] if')
src=src.replace('signals = []','signals = []\n    volumes = collections.Counter()\n    recent = collections.deque()')
needle='        # 1. Dislocation (Post-dump dip)'
insert='''        now = g['block_time']
        for e in ev:
            if e['buy'] and e['user'] != dev:
                volumes[e['user']] += e['sol_raw']/1e9
                recent.append((now,e['sol_raw']/1e9))
        while recent and recent[0][0] <= now-30:
            recent.popleft()
        gross = sum(volumes.values())
        meaningful = sum(v >= .05 for v in volumes.values())
        bins = [sum(v for bt,v in recent if k*10 <= now-bt < (k+1)*10) for k in range(3)]
        eligible = now-t['creation_time'] >= 30 and meaningful >= 8 and gross >= 2 and max(volumes.values(),default=0) <= .5*gross and all(v >= .05 for v in bins) and g['state']['rtokens_raw'] > 0
'''
src=src.replace(needle,insert+'\n'+needle).replace('if bool(ev) and not is_buy','if eligible and bool(ev) and not is_buy').replace("if 'velocity' not in seen_rules_for_coin","if eligible and 'velocity' not in seen_rules_for_coin").replace("if 'liquidity' not in seen_rules_for_coin","if eligible and 'liquidity' not in seen_rules_for_coin").replace("if 'mature_fresh' not in seen_rules_for_coin","if eligible and 'mature_fresh' not in seen_rules_for_coin")
ns=dict(C.O.__dict__);ns["collections"]=collections;exec(src,ns);_detect=ns['detect_signals']

def detect(t):
 end=t.get('decision_end_time',t['end_time'])
 return[s for s in _detect(t)if t['groups'][s['index']]['block_time']<=end]
