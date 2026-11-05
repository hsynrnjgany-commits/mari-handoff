# Emulates the live engine: every cycle re-scans ALL closed candles since entry with the CURRENT (possibly already promoted) stop.
import sys,json,collections
sys.path.insert(0,'analysis/REPLAY01')
import replay as R
from replay import gross,H,BE,TR,GAP,FEE
tr=json.load(open('outbox/engine_snapshot/data/paper-trades.json'))['trades']
cd=collections.defaultdict(list)
for l in open(sys.argv[1] if len(sys.argv)>1 else 'outbox/candles/candles_ext_for_trades.jsonl'):
    r=json.loads(l); cd[r['tradeId']].append(r)
def init(t):
    L=t['side']=='LONG'; e=t['entryPrice']; tp=t['tpPrice']
    if t.get('slBasis')=='ATR':
        d=abs(tp-e)/e/2; return (e*(1-d) if L else e*(1+d)),tp
    return t['slPrice'],tp
def retro(t):
    L=t['side']=='LONG'; e=t['entryPrice']; sl,tp=init(t); atr=t.get('slBasis')=='ATR'; be=False
    ks=[k for k in sorted(cd[t['id']],key=lambda k:k['t']) if k['t']>=t['entryTime']]
    for m in range(1,min(len(ks),24)+1):          # cycle m: candles 1..m are closed
        for i,k in enumerate(ks[:m],1):
            hi,lo=k['h'],k['l']
            if (L and lo<=sl) or ((not L) and hi>=sl): return sl,'SL',i,m
            if (L and hi>=tp) or ((not L) and lo<=tp): return tp,'TP',i,m
            fav=((hi-e)/e if L else (e-lo)/e)*100
            if atr:
                if not be and fav>=BE:
                    p=e*(1+FEE/100) if L else e*(1-FEE/100)
                    if (L and p>sl) or ((not L) and p<sl): sl=p
                    be=True
                if fav>=TR:
                    p=hi*(1-GAP/100) if L else lo*(1+GAP/100)
                    if (L and p>sl) or ((not L) and p<sl): sl=p
    return None,'OPEN_AT_WINDOW_END',None,None
if __name__=='__main__':
    c=collections.Counter()
    for t in tr:
        x,w,i,m=retro(t)
        ok=x is not None and abs(x-t['exitPrice'])/t['exitPrice']<1e-6 and w==t['exitReason'] and t['entryTime']+i*H==t['exitTime']
        c[(t['sourceVersion'][-2:],ok)]+=1
        if not ok: print('NO',t['id'],t['exitReason'],t['exitPrice'],'retro',w,x,i,m)
    print(c)
