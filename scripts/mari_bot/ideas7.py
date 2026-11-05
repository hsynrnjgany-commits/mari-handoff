# -*- coding: utf-8 -*-
"""ideas7 — ثبت پیشاپیش در RESEARCH_LOG (2026-11-05T13:55Z). فقط تمرینی.

H-MARI-E-040: روند چندسرعته (Hurst, Ooi, Pedersen 2017) — سهم = تعداد میانگین‌های ۵۰/۱۰۰/۱۵۰/۲۰۰ زیر قیمت ÷ ۴.
H-MARI-M-041: اثر اول ماه (Ariel 1987; Lakonishok & Smidt 1988) — آخرین روز ماه + روزهای ۱ تا ۳.
"""
from __future__ import annotations

import random
from datetime import datetime, timezone

from .ideas import _sma, t006_for

DAY_MS = 86_400_000
SPEEDS = (50, 100, 150, 200)
TOM_FIRST_DAYS = 3

IDEA7_HYPOTHESES = {
    "H-MARI-E-040": "روند چندسرعته (۵۰/۱۰۰/۱۵۰/۲۰۰، سهم = بله‌ها ÷ ۴): شارپ بیشتر و افت کمتر یا برابر T-006، روی BTC و ETH.",
    "H-MARI-M-041": "اثر اول ماه (آخرین روز + روزهای ۱ تا ۳): اختلاف میانگین بازده روزانه با بقیهٔ روزها، CI95 بالای صفر، روی BTC و ETH.",
}


def ensemble_weight(c, k, speeds=SPEEDS):
    if k < max(speeds) - 1:
        return None
    return sum(1 for n in speeds if c[k] > _sma(c, k, n)) / len(speeds)


def ensemble_for(sym, speeds=SPEEDS):
    def fn(k, ctx):
        st = ctx["state"]
        w = ensemble_weight(ctx["c"][sym], k, speeds)
        if w is None or w == st.get("w"):
            return None
        st["w"] = w
        return {sym: w} if w > 0 else {}
    return fn


def is_tom(t_ms: int, first_days: int = TOM_FIRST_DAYS) -> bool:
    """کندلی که تاریخ UTC آن آخرین روز ماه یا یکی از روزهای ۱..first_days است."""
    d = datetime.fromtimestamp(t_ms / 1000, timezone.utc)
    nxt = datetime.fromtimestamp((t_ms + DAY_MS) / 1000, timezone.utc)
    return d.day <= first_days or nxt.month != d.month


def _ci_diff(a, b, n_iter=4000, seed=41):
    if len(a) < 10 or len(b) < 10:
        return None
    rnd = random.Random(seed)
    ds = []
    for _ in range(n_iter):
        ma = sum(rnd.choice(a) for _ in a) / len(a)
        mb = sum(rnd.choice(b) for _ in b) / len(b)
        ds.append(ma - mb)
    ds.sort()
    diff = sum(a) / len(a) - sum(b) / len(b)
    return {"diff_pct": round(diff * 100, 4), "ci95_low": round(ds[int(.025 * n_iter)] * 100, 4),
            "ci95_high": round(ds[int(.975 * n_iter)] * 100, 4)}


def tom_test(bars: list[dict], start_ms: int, end_ms: int) -> dict:
    tom, rest = [], []
    for i in range(1, len(bars)):
        t = bars[i]["t"]
        if not (start_ms <= t <= end_ms):
            continue
        r = bars[i]["c"] / bars[i - 1]["c"] - 1
        (tom if is_tom(t) else rest).append(r)
    return {"n_tom": len(tom), "n_rest": len(rest),
            "tom_mean_pct": round(sum(tom) / max(1, len(tom)) * 100, 4),
            "rest_mean_pct": round(sum(rest) / max(1, len(rest)) * 100, 4),
            "tom_minus_rest": _ci_diff(tom, rest)}


def tom_for(sym):
    """راهبرد اطلاعی: سیگنال در بستهٔ روز k، اجرا در بستهٔ k+1؛ پس برای نگه‌داشتن کندل‌های پنجره،
    یک روز پیش از آن وارد می‌شویم (یعنی وقتی کندل فردا عضو پنجره است)."""
    def fn(k, ctx):
        st, days = ctx["state"], ctx["days"]
        if k + 1 >= len(days):
            return None
        want = is_tom(days[k] + DAY_MS)
        if want != st.get("in"):
            st["in"] = want
            return {sym: 1.0} if want else {}
        return None
    return fn


def run_ideas7(daily: dict, start_ms: int, end_ms: int) -> dict:
    from .classics import run_weights
    out, ok_e, ok_m = {}, True, True
    for sym in ("BTCUSDT", "ETHUSDT"):
        d = {sym: daily[sym]}
        t6, _, _ = run_weights(d, [sym], start_ms, end_ms, t006_for(sym))
        en, _, _ = run_weights(d, [sym], start_ms, end_ms, ensemble_for(sym))
        tm, _, _ = run_weights(d, [sym], start_ms, end_ms, tom_for(sym))
        tt = tom_test(daily[sym], start_ms, end_ms)
        ok_e &= bool((en.get("sharpe") or -9) > (t6.get("sharpe") or 9)
                     and en.get("max_drawdown_pct", 100) <= t6.get("max_drawdown_pct", 0))
        ci = tt["tom_minus_rest"]
        ok_m &= bool(ci and ci["ci95_low"] > 0)
        out[sym] = {"T-006": t6, "H-MARI-E-040": en, "TOM_ONLY_INFO": tm, "H-MARI-M-041": tt}
    return {"by_asset": out,
            "verdict": {"H-MARI-E-040": "SUPPORTED_IN_TEST_RANGE" if ok_e else "FALSIFIED",
                        "H-MARI-M-041": "SUPPORTED_IN_TEST_RANGE" if ok_m else "FALSIFIED"}}
