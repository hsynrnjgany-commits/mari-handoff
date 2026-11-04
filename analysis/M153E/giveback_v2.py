#!/usr/bin/env python3
"""M153-E style read-only analysis: MFE / MAE / Giveback / exit efficiency on v2 trades. Writes nothing."""
import json, sys, statistics as st, collections
d = json.load(open(sys.argv[1], encoding="utf-8"))
v2 = [t for t in d["trades"] if t.get("status") == "CLOSED" and t.get("sourceVersion") == "mari-paper-v2"]
def r(t):  # planned risk in % (stop distance)
    e, s = t["entryPrice"], t["slPrice"]
    return None
# planned risk: use plannedRiskPct field
have_r = [t for t in v2 if t.get("plannedRiskPct")]
print(f"v2 closed={len(v2)} | with plannedRiskPct={len(have_r)}")
def q(xs, p):
    xs = sorted(xs); 
    return xs[min(len(xs)-1, int(p*(len(xs)-1)+0.5))] if xs else float("nan")
def row(name, ts):
    if not ts: return
    mfe=[t["mfePct"] for t in ts]; mae=[t["maePct"] for t in ts]; real=[t["realizedPnlPct"] for t in ts]
    gb=[m-x for m,x in zip(mfe,real)]
    print(f"{name:22s} n={len(ts):2d} MFE med={st.median(mfe):5.2f} p75={q(mfe,.75):5.2f} max={max(mfe):5.2f} | MAE med={st.median(mae):5.2f} | realized med={st.median(real):+5.2f} | giveback med={st.median(gb):5.2f} mean={st.mean(gb):5.2f}")
print()
row("ALL v2", v2)
for reason in ("SL","TP","TIME"): row(f"exit={reason}", [t for t in v2 if t["exitReason"]==reason])
be=[t for t in v2 if t["exitReason"]=="SL" and t.get("beActive")]
nobe=[t for t in v2 if t["exitReason"]=="SL" and not t.get("beActive")]
row("SL via BE-stop", be); row("SL plain (no BE)", nobe)
print()
# how far did trades travel in units of planned risk (R)?
rs=[(t["mfePct"]/t["plannedRiskPct"], t["maePct"]/t["plannedRiskPct"]) for t in have_r]
for k in (0.5,1,1.5,2):
    print(f"reached MFE >= {k}R: {sum(1 for m,_ in rs if m>=k):2d}/{len(rs)}   |  reached MAE <= -{k}R: {sum(1 for _,a in rs if a<=-k):2d}/{len(rs)}")
print()
# BE trades: how high did they get before returning?
if be:
    m=[t['mfePct'] for t in be]; pr=[t['plannedRiskPct'] for t in be if t.get('plannedRiskPct')]
    print(f"BE-stop trades n={len(be)}: MFE range {min(m):.2f}..{max(m):.2f}%  (BE triggers at 1.00%; TP at 2x planned risk ~ median {st.median([2*p for p in pr]):.2f}%)")
    print("   MFE buckets:", dict(collections.Counter("1.0-1.5" if x<1.5 else "1.5-2.0" if x<2.0 else ">=2.0" for x in m)))
# exit efficiency for winners
wins=[t for t in v2 if t["realizedPnlPct"]>1e-9 and t["mfePct"]>0]
if wins: print(f"\nwinners n={len(wins)} exit efficiency (realized/MFE) median={st.median([t['realizedPnlPct']/t['mfePct'] for t in wins]):.2f}")
# side split (descriptive only; post-hoc, NOT a hypothesis test)
for side in ("LONG","SHORT"):
    ts=[t for t in v2 if t["side"]==side]; print(f"[descriptive, post-hoc] {side}: n={len(ts)} reached MFE>=1%: {sum(1 for t in ts if t['mfePct']>=1.0)}/{len(ts)}")
print("\nNOTE: mfePct/maePct in the engine are updated with the high/low of the candle in which the stop was hit, so MFE can be overstated for SL exits (upper bound).")
