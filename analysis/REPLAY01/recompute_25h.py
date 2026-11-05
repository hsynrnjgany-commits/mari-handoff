import sys,json,collections
sys.path.insert(0,'analysis/REPLAY01')
import retro as RT, replay as R
F='outbox/candles/candles_25h_for_trades.jsonl'
cd=collections.defaultdict(list)
for l in open(F):
    r=json.loads(l); cd[r['tradeId']].append(r)
RT.cd=cd; R.cd=cd
tr=RT.tr
def retro24(t):
    x,w,i,m=RT.retro(t)
    if x is None:
        ks=[k for k in sorted(cd[t['id']],key=lambda k:k['t']) if k['t']>=t['entryTime']]
        return ks[23]['c'],'TIME',24
    return x,w,i
c=collections.Counter(); bad=[]
for t in tr:
    x,w,i=retro24(t)
    okp=abs(x-t['exitPrice'])/t['exitPrice']<1e-6 and w==t['exitReason']
    okt=t['entryTime']+i*R.H==t['exitTime']
    c[(t['sourceVersion'][-2:],okp,okt)]+=1
    if not (okp and okt): bad.append((t['id'],t['exitReason'],w,i,(t['exitTime']-t['entryTime'])//R.H))
print('buggy-engine emulation (version, price+reason match, time match):',dict(c))
for b in bad: print('  ',b)
# corrected replay = candle-by-candle, no retroactive stop
def stats(rows):
    nets=[r for r in rows]; w=[x for x in nets if x>0]; l=[x for x in nets if x<=0]
    pf=sum(w)/-sum(l) if sum(l)<0 else float('inf')
    return dict(n=len(nets),wr=round(len(w)/len(nets)*100,1),pf=round(pf,2),sum_net_pct=round(sum(nets),2))
fee=2*R.FEE
for ver in ['v1','v2','all']:
    sel=[t for t in tr if ver=='all' or t['sourceVersion'].endswith(ver)]
    rec=[R.gross(t['side'],t['entryPrice'],t['exitPrice'])-fee for t in sel]
    fix=[]
    reasons=collections.Counter()
    for t in sel:
        x,why,n=R.sim(t); reasons[why]+=1
        fix.append(R.gross(t['side'],t['entryPrice'],x)-fee)
    print(ver,'recorded',stats(rec),'| corrected',stats(fix),dict(reasons))
print('recorded reasons all',collections.Counter(t['exitReason'] for t in tr))
