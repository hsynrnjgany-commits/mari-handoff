#!/usr/bin/env python3
"""Read-only detail: 19 wins line-by-line + 24 losses summary (dollar consistency)
+ shadow run#2 grouped by exit reason. No file modified. No secrets printed."""
import json, collections

EPS = 1e-9  # same tolerance as computeStats / paper_adhoc_stats

d = json.load(open('data/paper-trades.json'))
recs = d if isinstance(d, list) else d.get('trades', d.get('items', []))
closed = [t for t in recs if t.get('exitPrice') is not None]

wins   = [t for t in closed if (t.get('realizedPnlPct') or 0) > EPS]
losses = [t for t in closed if (t.get('realizedPnlPct') or 0) < -EPS]
be     = [t for t in closed if abs(t.get('realizedPnlPct') or 0) <= EPS]
print(f"classification: wins={len(wins)} losses={len(losses)} be={len(be)} total={len(closed)}")

def gross(t):
    ep, xp, side = t['entryPrice'], t['exitPrice'], t['side']
    return ((xp - ep) / ep if side == 'LONG' else (ep - xp) / ep) * 100.0

# --- 19 wins, line by line ---
print("\n=== WINS (19) ===")
max_dev = 0.0  # max |pnlPct - (gross-fee)| over wins with prices
n_size = 0
for i, t in enumerate(wins, 1):
    pct = t.get('realizedPnlPct') or 0.0
    sz = t.get('sizeUsd')
    usd = (sz * pct / 100.0) if sz else None
    if sz: n_size += 1
    g = gross(t) - 0.1  # price-based net
    max_dev = max(max_dev, abs(pct - g))
    print(f"W{i:02d} {t['symbol']:<12} {t['side']:<5} size={'%9.2f' % sz if sz else '    ندارد':>9} "
          f"pnlPct={pct:+7.3f}% pnlUsd={'%9.2f$' % usd if usd is not None else '   ندارد':>10} exit={t.get('exitReason')}")
print(f"wins with sizeUsd: {n_size}/19, without: {19-n_size}")
print(f"consistency max|realizedPnlPct-(gross-0.1)| over 19 wins = {max_dev:.2e} pp")
# identity check: derived usd vs sizeUsd*pct/100 (same formula, so report per-trade deviation vs price path)
for i, t in enumerate(wins, 1):
    sz = t.get('sizeUsd')
    if sz:
        usd = sz * (t.get('realizedPnlPct') or 0) / 100.0
        usd_price = sz * (gross(t) - 0.1) / 100.0
        assert abs(usd - usd_price) < 1e-6 * max(1, abs(usd)), f"W{i} mismatch"

# --- 24 losses, summary only ---
print("\n=== LOSSES (24) summary ===")
l_sz = [t for t in losses if t.get('sizeUsd')]
sum_usd = sum(t['sizeUsd'] * (t.get('realizedPnlPct') or 0) / 100.0 for t in l_sz)
sum_pct_usd = sum((t.get('realizedPnlPct') or 0) * t['sizeUsd'] / 100.0 for t in l_sz)
print(f"losses: 24 total, with sizeUsd={len(l_sz)}, without={24-len(l_sz)}")
print(f"sum pnlUsd (derived) = {sum_usd:.2f}$ | sum(pnlPct*sizeUsd/100) = {sum_pct_usd:.2f}$ | identical by formula")
lsum_pct = sum((t.get('realizedPnlPct') or 0) for t in losses)
print(f"losses total pct (equal-weight) = {lsum_pct:+.2f} pp")

# --- shadow grouped by exit reason ---
print("\n=== SHADOW run#2 by exit reason ===")
sh = [json.loads(l) for l in open('scripts/m144_adversarial/out/shadow/shadow_trades.jsonl') if l.strip()]
grp = collections.defaultdict(list)
for t in sh:
    grp[t.get('reason')].append(t)
for r, ts in sorted(grp.items(), key=lambda kv: -len(kv[1])):
    w = sum(1 for t in ts if (t.get('net_pct') or 0) > EPS)
    l = sum(1 for t in ts if (t.get('net_pct') or 0) < -EPS)
    b = len(ts) - w - l
    avg = sum((t.get('net_pct') or 0) for t in ts) / len(ts)
    print(f"{r:<13} n={len(ts):>2}  win={w} loss={l} be={b}  avg_net_pct={avg:+.2f}%")
