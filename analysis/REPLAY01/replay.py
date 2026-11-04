import json,sys,collections
H=3600000
tr=json.load(open('outbox/engine_snapshot/data/paper-trades.json'))['trades']
cd=collections.defaultdict(list)
for l in open('outbox/candles/candles_for_trades.jsonl'):
    r=json.loads(l); cd[r['tradeId']].append(r)
BE=1.0;TR=2.0;GAP=1.2;FEE=0.1;MAXH=24
def gross(side,e,x): return (x-e)/e*100 if side=='LONG' else (e-x)/e*100
def sim(t,use_be=True,use_trail=True,use_tp=True):
    L=t['side']=='LONG'; e=t['entryPrice']; tp=t['tpPrice']
    # slPrice in the JSON is the FINAL (mutated) stop for v2; rebuild the INITIAL stop: v2 TP distance = 2 x SL distance
    if t.get('slBasis')=='ATR':
        d=abs(tp-e)/e/2; sl=e*(1-d) if L else e*(1+d)
    else: sl=t['slPrice']
    atr=t.get('slBasis')=='ATR'; be=False; n=0
    ks=[k for k in sorted(cd[t['id']],key=lambda k:k['t']) if k['t']>=t['entryTime']]
    last=None
    for k in ks:
        n+=1; last=k
        hi,lo,c=k['h'],k['l'],k['c']
        if L:
            if lo<=sl: return sl,'SL',n
            if use_tp and hi>=tp: return tp,'TP',n
            fav=(hi-e)/e*100
        else:
            if hi>=sl: return sl,'SL',n
            if use_tp and lo<=tp: return tp,'TP',n
            fav=(e-lo)/e*100
        if atr:
            if use_be and not be and fav>=BE:
                p=e*(1+FEE/100) if L else e*(1-FEE/100)
                if (L and p>sl) or ((not L) and p<sl): sl=p
                be=True
            if use_trail and fav>=TR:
                p=hi*(1-GAP/100) if L else lo*(1+GAP/100)
                if (L and p>sl) or ((not L) and p<sl): sl=p
        if n>=MAXH: return c,'TIME',n
    return (last['c'],'TIME',n) if last else (None,'NOC',0)
def run(**kw):
    out=[]
    for t in tr:
        x,why,n=sim(t,**kw)
        out.append((t,x,why,n))
    return out
if __name__=='__main__':
    # validation of baseline vs recorded
    res=run(); bad=0
    for t,x,why,n in res:
        ok=(abs(x-t['exitPrice'])/t['exitPrice']<1e-6) and why==t['exitReason']
        if not ok:
            bad+=1; print('MISMATCH',t['id'],t['sourceVersion'],'rec',t['exitReason'],t['exitPrice'],'sim',why,x,n)
    print('baseline replay matches',len(res)-bad,'/',len(res))
