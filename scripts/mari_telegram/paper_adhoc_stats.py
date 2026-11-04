#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""تحلیل موردی دفتر تمرینی — فقط‌خواندنی (سفارش رییس):
میانگین حجم پوزیشن برد/باخت جدا + کنترل مرز کارمزد سربه‌سرها. هیچ عدد ساختگی."""
import json

PATH = '/home/z/my-project/data/paper-trades.json'
EPS = 1e-9  # همان تلورانس computeStats (src/lib/paper/stats.ts)

d = json.load(open(PATH, encoding='utf-8'))
closed = [t for t in d.get('trades', []) if t.get('status') == 'CLOSED']
wins   = [t for t in closed if (t.get('realizedPnlPct') or 0) >  EPS]
losses = [t for t in closed if (t.get('realizedPnlPct') or 0) < -EPS]
be     = [t for t in closed if abs(t.get('realizedPnlPct') or 0) <= EPS]

def sz(t): return t.get('sizeUsd') or 0

print(f"closed={len(closed)} wins={len(wins)} losses={len(losses)} breakeven={len(be)}")
print(f"avg_win_size_usd={sum(sz(t) for t in wins)/len(wins):.2f}")
print(f"avg_loss_size_usd={sum(sz(t) for t in losses)/len(losses):.2f}")
print(f"avg_be_size_usd={(sum(sz(t) for t in be)/len(be)):.2f}" if be else "avg_be_size_usd=NA")
print(f"net_usd={sum((t.get('realizedPnlPct') or 0)/100*sz(t) for t in closed):.2f}")
gp = sum((t.get('realizedPnlPct') or 0)/100*sz(t) for t in wins)
gl = sum((t.get('realizedPnlPct') or 0)/100*sz(t) for t in losses)
print(f"pf_usd={gp/abs(gl):.3f}" if abs(gl) > 1e-12 else "pf_usd=NA")

def gross(t):
    ep, xp, side = t.get('entryPrice'), t.get('exitPrice'), t.get('side')
    if not ep or xp is None:
        return None
    return ((ep - xp) / ep if side == 'SHORT' else (xp - ep) / ep) * 100.0

g = [gross(t) for t in be]
g = [x for x in g if x is not None]
if g:
    print(f"be_gross_pct_min={min(g):.8f} max={max(g):.8f}")
print(f"be_exit_equals_entry={sum(1 for t in be if t.get('exitPrice') == t.get('entryPrice'))}/{len(be)}")
from collections import Counter
print(f"be_exit_reasons={dict(Counter((t.get('exitReason') or 'UNKNOWN').upper() for t in be))}")
print(f"wl_exit_reasons= wins:{dict(Counter((t.get('exitReason') or '?').upper() for t in wins))} losses:{dict(Counter((t.get('exitReason') or '?').upper() for t in losses))}")
