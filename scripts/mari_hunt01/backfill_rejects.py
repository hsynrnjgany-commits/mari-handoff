#!/usr/bin/env python3
"""بازپخت ردشدگان فیلتری چرخهٔ 21:16:41Z از آرشیو (فقط حسابداری — هیچ معامله‌ای ساخته نمی‌شود).
برچسب backfilled_reconstruction=true و قابل‌ممیزی."""
import glob
import json
import statistics
from collections import defaultdict

STALE_TOL = 0.05
SIZE = 100

recs = []
for fp in sorted(glob.glob("data/tick-vault/snapshots-*.jsonl")):
    for line in open(fp, encoding="utf-8"):
        try:
            recs.append(json.loads(line))
        except Exception:
            pass

# همان چرخهٔ سوپ اول مأموریت
target = [r for r in recs if r.get("cycle_ts", "").startswith("2026-10-29T21:16:41")]
assert target, "cycle 21:16 not found"
trec = target[0]

quotes = defaultdict(lambda: defaultdict(list))
for r in recs:
    for t in r.get("top20") or []:
        b = t.get("base")
        if not b:
            continue
        if t.get("buy_ex") and t.get("ask"):
            quotes[b][t["buy_ex"]].append(float(t["ask"]))
        if t.get("sell_ex") and t.get("bid"):
            quotes[b][t["sell_ex"]].append(float(t["bid"]))
stale = {}
for base, venues in quotes.items():
    if len(venues) < 2:
        continue
    med = statistics.median([p for ps in venues.values() for p in ps])
    for venue, ps in venues.items():
        dev = abs(statistics.median(ps) / med - 1) if med > 0 else 0
        if dev > STALE_TOL:
            stale[(base, venue)] = dev

written_bases = set()
for line in open("data/mari-hunt01/decisions.jsonl", encoding="utf-8"):
    d = json.loads(line)
    if d["cycle_ts"].startswith("2026-10-29T21:16:41"):
        written_bases.add(d["base"])

out = []
for t in trec.get("top20") or []:
    base = t.get("base")
    if base in written_bases:
        continue  # رکورد تصمیم دارد؛ قبلاً حساب شده
    g = float(t.get("gross_pct", 0) or 0)
    tob_b = float(t.get("tob_buy_usdt", 0) or 0)
    tob_s = float(t.get("tob_sell_usdt", 0) or 0)
    uid = f"HUNT01-20261029T211641-{base}-{t.get('buy_ex')}-{t.get('sell_ex')}"
    if g > 100:
        out.append({"id": uid, "base": base, "reason": "phantom>100%", "gross_pct": g,
                    "backfilled_reconstruction": True, "cycle_ts": trec["cycle_ts"]}); continue
    bad = [v for (b, v) in stale if b == base and v in (t.get("buy_ex"), t.get("sell_ex"))]
    if bad:
        out.append({"id": uid, "base": base, "reason": f"stale_venue({','.join(bad)})",
                    "gross_pct": g, "backfilled_reconstruction": True,
                    "cycle_ts": trec["cycle_ts"]}); continue
    if g > 10 and min(tob_b, tob_s) < 1000:
        out.append({"id": uid, "base": base, "reason": "phantom_m142(gross>10%,depth<1000)",
                    "gross_pct": g, "backfilled_reconstruction": True,
                    "cycle_ts": trec["cycle_ts"]}); continue
    if tob_b < SIZE or tob_s < SIZE:
        out.append({"id": uid, "base": base,
                    "reason": f"liquidity<${SIZE}(tob ${tob_b:.0f}/${tob_s:.0f})",
                    "gross_pct": g, "backfilled_reconstruction": True,
                    "cycle_ts": trec["cycle_ts"]}); continue
    # باقی‌مانده: L2 نبوده و skip_net نبوده → no l2/no price handled in decision file only;
    # اینجا یعنی candidate بدون رکورد و بدون رد فیلتر روشن → رد حسابداری روشن ثبت کن
    out.append({"id": uid, "base": base, "reason": "unaccounted_replay_gap",
                "gross_pct": g, "backfilled_reconstruction": True,
                "cycle_ts": trec["cycle_ts"]})

with open("data/mari-hunt01/rejects.jsonl", "a", encoding="utf-8") as f:
    for r in out:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
print(f"backfilled_rejects={len(out)}")
for r in out:
    print(f"  {r['base']}: {r['reason']}")
