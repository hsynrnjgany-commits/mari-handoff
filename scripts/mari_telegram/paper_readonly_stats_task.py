#!/usr/bin/env python3
"""Read-only stats for data/paper-trades.json — reproduces every report number
(26% / 39.2% / 1.05 / -1010$) and shows exactly which formula produces which.
No file modified. No secrets."""
import json, collections

EPS = 1e-9  # tolerance used by src/lib/paper/stats.ts computeStats

d = json.load(open('data/paper-trades.json'))
tr = d if isinstance(d, list) else d.get('trades', [])
closed = [t for t in tr if t.get('exitPrice') is not None]
open_tr = [t for t in tr if t.get('exitPrice') is None]

def gross(t):
    ep, xp, s = t['entryPrice'], t['exitPrice'], t['side']
    return ((xp - ep) / ep if s == 'LONG' else (ep - xp) / ep) * 100.0

print(f"total={len(tr)} closed={len(closed)} open/incomplete={len(open_tr)}")

# --- canonical (with tolerance) ---
wins = [t for t in closed if (t.get('realizedPnlPct') or 0) > EPS]
losses = [t for t in closed if (t.get('realizedPnlPct') or 0) < -EPS]
be = [t for t in closed if abs(t.get('realizedPnlPct') or 0) <= EPS]
print(f"[tolerance 1e-9] wins={len(wins)} losses={len(losses)} be={len(be)}")
print(f"  WR over all closed  = {100*len(wins)/len(closed):.2f}%   (stats.ts:163 style)")
print(f"  WR wins/(wins+loss) = {100*len(wins)/(len(wins)+len(losses)):.2f}%")

# --- no-tolerance reproduction (float-noise BE residuals) ---
w0 = [t for t in closed if (t.get('realizedPnlPct') or 0) > 0]
l0 = [t for t in closed if (t.get('realizedPnlPct') or 0) < 0]
z0 = [t for t in closed if (t.get('realizedPnlPct') or 0) == 0]
print(f"[no tolerance  ] wins={len(w0)} losses={len(l0)} exactly0={len(z0)}")
print(f"  WR over all closed  = {100*len(w0)/len(closed):.2f}%   <-- 39.2%?")
res_signs = collections.Counter('+' if (t.get('realizedPnlPct') or 0) > 0 else ('-' if (t.get('realizedPnlPct') or 0) < 0 else '0') for t in be)
print(f"  BE residual signs: {dict(res_signs)}  max_res={max(abs(t.get('realizedPnlPct') or 0) for t in be):.2e}")

# --- sums / PF (equal-weight, net basis) ---
sp = sum(t['realizedPnlPct'] for t in wins); sl = sum(t['realizedPnlPct'] for t in losses)
print(f"gross_profit(net%)={sp:.2f}pp  gross_loss(net%)={sl:.2f}pp  PF%(equal-weight)={sp/abs(sl):.3f}")
spg = sum(gross(t) for t in wins); slg = sum(gross(t) for t in losses)
print(f"gross_profit(pre-fee%)={spg:.2f}pp gross_loss(pre-fee%)={slg:.2f}pp PF%(pre-fee)={spg/abs(slg):.3f}")

# --- dollar (sized only) ---
sz = [t for t in closed if t.get('sizeUsd')]
wz = [t for t in sz if (t.get('realizedPnlPct') or 0) > EPS]
lz = [t for t in sz if (t.get('realizedPnlPct') or 0) < -EPS]
gp = sum(t['sizeUsd']*t['realizedPnlPct']/100 for t in wz)
gl = sum(t['sizeUsd']*t['realizedPnlPct']/100 for t in lz)
fee = sum(0.001*t['sizeUsd'] for t in sz)
gp_pre = sum(t['sizeUsd']*gross(t)/100 for t in wz)
gl_pre = sum(t['sizeUsd']*gross(t)/100 for t in lz)
print(f"sized={len(sz)}/{len(closed)}  gross_win$={gp:.2f}  gross_loss$={gl:.2f}")
print(f"PF$={gp/abs(gl):.3f}  net_with_fee$={gp+gl:.2f}  fee_total$={fee:.2f}  net_without_fee$={gp+gl+fee:.2f}")
print(f"[pre-fee check] gross_win$={gp_pre:.2f} gross_loss$={gl_pre:.2f} PF$pre={gp_pre/abs(gl_pre):.3f} net$={gp_pre+gl_pre:.2f}")
