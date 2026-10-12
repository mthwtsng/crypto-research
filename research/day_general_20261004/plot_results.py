import json,pathlib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
P=pathlib.Path(__file__).resolve().parent
r=json.loads((P/'FIRST_ENTRY_LEDGER.json').read_text())
cases=[('mature_fresh','full_timer','Mature · timer'),('mature_fresh','staged_ladder','Mature · staged'),('dislocation','full_timer','Dip · first entry'),('velocity','full_timer','Velocity · timer'),('liquidity','full_timer','Liquidity · timer')]
fig,ax=plt.subplots(figsize=(9,5));ys=list(range(len(cases)))
for dx,sn,col,label in [(-.17,'same_slot_one','#28759c','Same slot · ≤1 curve group'),(.17,'next_slot_tail','#dd8541','Next-slot tail')]:
 vals=[next(x for x in r if x['rule']==rule and x['mode']==mode and x['scenario']==sn)['funded5']['net_zero_recovery_sol']for rule,mode,_ in cases]
 ax.barh([y+dx for y in ys],vals,height=.3,color=col,label=label)
 for y,v in zip(ys,vals):ax.text(v+(.025 if v>=0 else -.025),y+dx,f'{v:+.2f}',ha='left'if v>=0 else'right',va='center',fontsize=9)
ax.set_yticks(ys,[c[2]for c in cases]);ax.invert_yaxis();ax.axvline(0,color='#777',linewidth=.8);ax.set_xlim(-1.6,1.3);ax.set_xlabel('Modeled net SOL · separate 5-SOL bankrolls');ax.set_title('Fixed 24-hour launch sample · 600 launches, 57 trigger coins');ax.legend(loc='lower right',fontsize=9);ax.grid(axis='x',alpha=.15);ax.set_axisbelow(True);fig.text(.02,.01,'Synthetic placements; actual landing distribution uncalibrated. First entry per rule/mint. Standalone profits cannot be added.',fontsize=8);fig.tight_layout(rect=[0,.04,1,1]);fig.savefig(P/'RESULTS.png',dpi=170);fig.savefig(P/'RESULTS.svg');print('Plot written')
