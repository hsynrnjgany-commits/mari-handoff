# -*- coding: utf-8 -*-
"""خوشهٔ B سند مادر: AMD و سشن‌ها — ثبت پیشاپیش در RESEARCH_LOG (2026-11-05T07:05Z).

سشن‌ها (UTC): آسیا ۰۰-۰۸، لندن ۰۸-۱۳، نیویورک ۱۳-۲۱.
S-036: شکار محدودهٔ آسیا در لندن → جهت بازده نیویورک (CI95، BTC و ETH).
S-037: آسیای آرام (۳۰٪ پایین ۶۰ روز) + شکست یک‌طرفهٔ لندن → نیویورک خلاف جهت (نرخ درستی > ۵۰٪، CI95).
فقط تمرینی.
"""
from __future__ import annotations

import random

HOUR_MS, DAY_MS = 3_600_000, 86_400_000
ASIA, LONDON, NY = (0, 8), (8, 13), (13, 21)

SESSION_HYPOTHESES = {
    "H-MARI-S-036": "شکار کف/سقف آسیا در لندن با بازگشت → بازده نیویورک بیشتر/کمتر از معمول (CI95، BTC و ETH).",
    "H-MARI-S-037": "آسیای آرام + شکست یک‌طرفهٔ لندن → نیویورک خلاف جهت؛ نرخ درستی > ۵۰٪ با CI95 (BTC و ETH).",
}


def daily_sessions(bars: list[dict]) -> list[dict]:
    """برای هر روز UTC که هر سه سشن کامل دارد: سقف/کف/باز/بستهٔ هر سشن."""
    by_day = {}
    for b in bars:
        d = b["t"] // DAY_MS * DAY_MS
        by_day.setdefault(d, {})[(b["t"] - d) // HOUR_MS] = b
    out = []
    for d in sorted(by_day):
        hrs = by_day[d]

        def sess(a, z):
            xs = [hrs[h] for h in range(a, z) if h in hrs]
            if len(xs) != z - a:
                return None
            return {"o": xs[0]["o"], "c": xs[-1]["c"], "h": max(x["h"] for x in xs), "l": min(x["l"] for x in xs)}
        a, lo, ny = sess(*ASIA), sess(*LONDON), sess(*NY)
        if a and lo and ny:
            out.append({"t": d, "asia": a, "london": lo, "ny": ny, "ny_ret": ny["c"] / ny["o"] - 1})
    return out


def _ci_rate(hits: list[int], n_iter=4000, seed=9):
    if len(hits) < 20:
        return None
    rnd = random.Random(seed)
    rs = sorted(sum(rnd.choice(hits) for _ in hits) / len(hits) for _ in range(n_iter))
    return {"rate_pct": round(sum(hits) / len(hits) * 100, 2), "ci95_low": round(rs[int(.025 * n_iter)] * 100, 2),
            "ci95_high": round(rs[int(.975 * n_iter)] * 100, 2), "n": len(hits)}


def s036(days: list[dict]) -> dict:
    from .ict import _diff_ci
    base = [x["ny_ret"] for x in days]
    bull = [x["ny_ret"] for x in days if x["london"]["l"] < x["asia"]["l"] and x["london"]["c"] > x["asia"]["l"]]
    bear = [x["ny_ret"] for x in days if x["london"]["h"] > x["asia"]["h"] and x["london"]["c"] < x["asia"]["h"]]
    return {"n_days": len(base), "mean_ny_pct": round(sum(base) / len(base) * 100, 4) if base else None,
            "bull": {"n": len(bull), "vs_all": _diff_ci(bull, base)},
            "bear": {"n": len(bear), "vs_all": _diff_ci(bear, base)}}


def s037(days: list[dict]) -> dict:
    hits = []
    for k in range(60, len(days)):
        x = days[k]
        rng = x["asia"]["h"] - x["asia"]["l"]
        past = sorted(d["asia"]["h"] - d["asia"]["l"] for d in days[k - 60:k])
        if rng > past[int(0.3 * 60)]:
            continue
        up = x["london"]["h"] > x["asia"]["h"]
        dn = x["london"]["l"] < x["asia"]["l"]
        if up == dn:                       # هیچ یا هر دو طرف → رویداد نیست
            continue
        if x["ny_ret"] == 0:
            continue
        hits.append(1 if (x["ny_ret"] < 0) == up else 0)
    return {"hit": _ci_rate(hits)}


def run_sessions(hourly: dict, start_ms: int, end_ms: int) -> dict:
    out, ok36, ok37 = {}, True, True
    for sym in ("BTCUSDT", "ETHUSDT"):
        days = [d for d in daily_sessions(hourly[sym]) if start_ms <= d["t"] <= end_ms]
        a, b = s036(days), s037(days)
        bu, be = a["bull"]["vs_all"], a["bear"]["vs_all"]
        ok36 &= bool(bu and be and bu["ci95_low"] > 0 and be["ci95_high"] < 0)
        ok37 &= bool(b["hit"] and b["hit"]["ci95_low"] > 50)
        out[sym] = {"S-036": a, "S-037": b, "days": len(days)}
    return {"by_asset": out, "verdict": {"H-MARI-S-036": "SUPPORTED_IN_TEST_RANGE" if ok36 else "FALSIFIED",
                                         "H-MARI-S-037": "SUPPORTED_IN_TEST_RANGE" if ok37 else "FALSIFIED"}}
