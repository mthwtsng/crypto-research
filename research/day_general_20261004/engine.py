"""Current fee-tier interpretation: short timers urgent, mature timer passive."""
import inspect
import screen as S
C=S.C
src=inspect.getsource(C.replay)
src=src.replace("hold=HOLDS[sig['rule']];ticket=", "urgent=sig['rule']!='mature_fresh'\n hold=HOLDS[sig['rule']];ticket=")
src=src.replace("exit_slot,xt=W.time_at(fire+cost['delay'])", "exit_slot,xt=W.time_at(fire+(1 if urgent else cost['delay']))")
src=src.replace("pending=dict(kind='timer',n=n,slot=exit_slot,fast=False)","pending=dict(kind='timer',n=n,slot=exit_slot,fast=urgent)")
ns=dict(C.__dict__);exec(src,ns);replay=ns['replay']
