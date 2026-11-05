# Forward replay (= engine after FIX-RETRO-01) on 25h candles; compares with recorded ledger. READ ONLY.
import sys,json,collections,statistics as S
sys.path.insert(0,'analysis/REPLAY01')
import replay as R
from replay import gross,H
cd=collections.defaultdict(list)
for l in open('outbox/candles/candles_25h_for_trades.jsonl'):
    r=json.loads(l); cd[r['tradeId']].append(r)
R.cd=cd
rows=R.run()
def st(v):
    g=sum(x for x in v if x>0); l=-sum(x for x in v if x<0)
    return f"n={len(v)} mean={S.mean(v):+.3f}% sum={sum(v):+.2f}pp PF={(g/l if l else float('inf')):.2f} win={sum(1 for x in v if x>1e-9)}/{len(v)}"
match=0; ch=[]
rec=[];cor={0.10:[],0.22:[],0.30:[]}; why=collections.Counter(); short=0
for t,x,w,n in rows:
    if t['sourceVersion']!='mari-paper-v2': continue
    if w=='TIME' and n<24: short+=1
    ok=abs(x-t['exitPrice'])/t['exitPrice']<1e-6 and w==t['exitReason']
    match+=ok
    if not ok: ch.append((t['id'],t['exitReason'],round(t['realizedPnlPct'],2),w,round(gross(t['side'],t['entryPrice'],x)-0.1,2)))
    rec.append(t['realizedPnlPct']); why[w]+=1
    for c in cor: cor[c].append(gross(t['side'],t['entryPrice'],x)-c)
print('v2 forward replay equals ledger:',match,'/58 ; windows too short for TIME:',short)
print('corrected exits:',dict(why))
print('RECORDED  v2 (0.10%):',st(rec))
for c,v in cor.items(): print(f'CORRECTED v2 ({c:.2f}%):',st(v))
print('changed trades (id, recorded reason, recorded net, corrected reason, corrected net @0.10):')
for r in ch: print(' ',r)

# --- approximate counterfactual: a fixed engine would have taken only a SUBSET of these signals
# (max 5 open, one position per symbol, 6h cooldown after close). Greedy in entry order. Signals the
# buggy engine skipped (if any) are unknown, so this is an approximation, not the true counterfactual.
print('\nGREEDY SUBSET (max 5 open, 1 per symbol, 6h cooldown):')
v=[(t,t['entryTime']+n*H,x) for t,x,w,n in rows if t['sourceVersion']=='mari-paper-v2']
from replay import H as _H
v.sort(key=lambda z:z[0]['entryTime'])
taken=[]
for t,ex,x in v:
    e=t['entryTime']
    openn=[u for u in taken if u[0]['entryTime']<=e<u[1]]
    if len(openn)>=5: continue
    if any(u[0]['symbol']==t['symbol'] and e<u[1]+6*_H for u in taken): continue
    taken.append((t,ex,x))
for c in (0.10,0.22,0.30):
    print(f'  ({c:.2f}%):',st([gross(t['side'],t['entryPrice'],x)-c for t,ex,x in taken]))
