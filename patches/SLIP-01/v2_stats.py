#!/usr/bin/env python3
"""MARI v2-only stats with cost scenarios. READ ONLY: reads a ledger file, writes nothing."""
import json, sys, math, statistics as st
EPS = 1e-9
path = sys.argv[1]
d = json.load(open(path, encoding="utf-8"))
trades = [t for t in d["trades"] if t.get("status") == "CLOSED"]

def gross(t):
    e, x = t["entryPrice"], t["exitPrice"]
    return (x - e) / e * 100 if t["side"] == "LONG" else (e - x) / e * 100

def summarize(rows, cost, label):
    nets = [gross(t) - cost for t in rows]
    w = [n for n in nets if n > EPS]; l = [n for n in nets if n < -EPS]
    be = len(nets) - len(w) - len(l)
    gp, gl = sum(w), -sum(l)
    pf = gp / gl if gl else float("inf")
    mean = st.mean(nets); sd = st.stdev(nets) if len(nets) > 1 else float("nan")
    t_stat = mean / (sd / math.sqrt(len(nets))) if sd and sd == sd else float("nan")
    wr_dec = 100 * len(w) / (len(w) + len(l)) if (w or l) else float("nan")
    wr_all = 100 * len(w) / len(nets)
    # dollar pnl only where sizeUsd exists
    usd = [(gross(t) - cost) / 100 * t["sizeUsd"] for t in rows if t.get("sizeUsd")]
    ug = sum(x for x in usd if x > 0); ul = -sum(x for x in usd if x < 0)
    print(f"{label:34s} n={len(nets):3d} W/L/BE={len(w)}/{len(l)}/{be}  WR(dec)={wr_dec:5.1f}% WR(all)={wr_all:5.1f}%  "
          f"PF%={pf:5.3f} sum%={sum(nets):+7.2f} mean%={mean:+.3f} t={t_stat:+.2f}  "
          f"USD net={sum(usd):+8.1f} PF$={(ug/ul if ul else float('inf')):5.3f} (usd n={len(usd)})")

v2 = [t for t in trades if t.get("sourceVersion") == "mari-paper-v2"]
v1 = [t for t in trades if t.get("sourceVersion") != "mari-paper-v2"]
print(f"closed total={len(trades)} v2={len(v2)} v1/other={len(v1)}")
import collections
for name, rows in (("v2", v2), ("v1", v1)):
    print(name, "exit reasons:", dict(collections.Counter(t["exitReason"] for t in rows)),
          "| BE-active SL:", sum(1 for t in rows if t["exitReason"]=="SL" and t.get("beActive")))
print()
for label, rows in (("ALL 74", trades), ("v2 only", v2), ("v1 only", v1)):
    for cost, cl in ((0.10, "cost 0.10% (engine now)"), (0.22, "cost 0.22% (realistic-ish)"), (0.30, "cost 0.30% (pessimistic)")):
        summarize(rows, cost, f"{label} | {cl}")
    print()
