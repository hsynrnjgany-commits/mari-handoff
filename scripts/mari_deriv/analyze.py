#!/usr/bin/env python3
"""
MARI DERIV-01 گام ۵ — تحلیل: جفت‌کردن تصمیم‌های شکار با دادهٔ مشتقهٔ همان زمان
===============================================================================
READ ONLY | PAPER ONLY | روی هیچ تصمیمی اثر ندارد — فقط پژوهش.
ورودی: store/decisions.jsonl (تصمیم‌ها) + store/deriv.jsonl (لایهٔ مشتقه).
تطبیق: هر تصمیم با نزدیک‌ترین اجرای مشتقهٔ همان نماد در پنجرهٔ ±۴۰ دقیقه.
چهار حالت (فرمان رییس):
  oi_up   : oi_delta > 0           (OI رو به افزایش)
  oi_down : oi_delta < 0           (OI رو به کاهش)
  fund_pos: funding ≥ +0.05٪ در هر بازهٔ فاندینگ (افراطی مثبت)
  fund_neg: funding ≤ −0.05٪ در هر بازهٔ فاندینگ (افراطی منفی)
خروجی هر حالت: تعداد تصمیم + نتیجهٔ کاغذی بعدی (تعقیب: همان مسیر بعداً به
WOULD_TRADE رسید یا نه) + میانگین gross/net (فقط ردیف‌های L2).
هر حالت با نمونهٔ <۳۰ → «نمونه ناکافی» و هیچ نتیجه‌ای ادعا نمی‌شود.
"""
import json
import os
import sys
from datetime import datetime, timezone

STORE = "/home/z/my-project/scripts/mari_hunt01/store"
DERIV = "/home/z/my-project/scripts/mari_deriv/store/deriv.jsonl"
TOL_MIN = 40.0
FUND_EXTREME = 0.0005   # ±0.05٪ در هر بازهٔ فاندینگ
MIN_SAMPLE = 30


def load_jsonl(p):
    out = []
    if not os.path.exists(p):
        return out
    for line in open(p, encoding="utf-8"):
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def ts(x):
    try:
        return datetime.fromisoformat(str(x).replace("Z", "+00:00"))
    except Exception:
        return None


def main():
    decisions = [d for d in load_jsonl(f"{STORE}/decisions.jsonl")
                 if not str(d.get("type", "decision")).startswith("aggregate")
                 and d.get("decision") in ("WOULD_TRADE", "SKIP_NET", "UNVERIFIED")]
    deriv = load_jsonl(DERIV)
    runs = {}
    for r in deriv:
        runs.setdefault(r.get("run_id"), []).append(r)
    run_meta = []
    for rid, rows in runs.items():
        t = ts(rows[0].get("ts_utc"))
        if t:
            run_meta.append((t, rid, {r["symbol"]: r for r in rows}))
    run_meta.sort(key=lambda x: x[0])

    # سه‌گانه‌های مسیر برای تعقیب (follow-through)
    trip_wt_later = {}
    dts = [(ts(d.get("decision_ts_utc")), d) for d in decisions]
    dts = [(a, d) for a, d in dts if a]
    for i, (a, d) in enumerate(dts):
        k = (d.get("base"), d.get("buy_ex"), d.get("sell_ex"))
        trip_wt_later[(id(d))] = any(
            dd.get("decision") == "WOULD_TRADE" and b > a and
            (dd.get("base"), dd.get("buy_ex"), dd.get("sell_ex")) == k
            for b, dd in dts[i + 1:])

    matched, unmatched = [], 0
    for a, d in dts:
        best = None
        for rt, rid, symmap in run_meta:
            if abs((rt - a).total_seconds()) <= TOL_MIN * 60:
                r = symmap.get(d.get("universe_sym") or
                               (str(d.get("base")) + "USDT"))
                if r:
                    best = r
                    break
        if best:
            matched.append((d, best))
        else:
            unmatched += 1

    conds = {
        "oi_up":    lambda r: (r.get("oi_delta") or 0) > 0,
        "oi_down":  lambda r: (r.get("oi_delta") or 0) < 0,
        "fund_pos": lambda r: (r.get("funding") is not None
                               and r["funding"] >= FUND_EXTREME),
        "fund_neg": lambda r: (r.get("funding") is not None
                               and r["funding"] <= -FUND_EXTREME),
    }
    out = {"ok": True, "decisions_total": len(decisions),
           "deriv_runs": len(run_meta), "matched": len(matched),
           "unmatched_no_deriv_near": unmatched,
           "tol_min": TOL_MIN, "fund_extreme": FUND_EXTREME,
           "min_sample": MIN_SAMPLE, "conditions": {}}

    for name, fn in conds.items():
        sel = [(d, r) for d, r in matched if fn(r)]
        n = len(sel)
        c = {"n": n}
        if n < MIN_SAMPLE:
            c["verdict"] = "نمونه ناکافی — هیچ نتیجه‌ای ادعا نمی‌شود"
            c["decision_counts"] = {}
        else:
            dc = {"WOULD_TRADE": 0, "SKIP_NET": 0, "UNVERIFIED": 0}
            for d, _ in sel:
                dc[d["decision"]] = dc.get(d["decision"], 0) + 1
            l2 = [d for d, _ in sel if d.get("method") == "l2_vwap_100"
                  and d.get("net_pct") is not None]
            c["decision_counts"] = dc
            c["follow_up_would_trade"] = sum(1 for d, _ in sel
                                             if trip_wt_later.get(id(d)))
            c["mean_gross_pct"] = round(sum(d["gross_pct"] or 0 for d in sel) / n, 4)
            c["mean_net_pct_l2"] = round(sum(d["net_pct"] for d in l2) / len(l2), 4) if l2 else None
            c["verdict"] = "ok"
        out["conditions"][name] = c

    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
