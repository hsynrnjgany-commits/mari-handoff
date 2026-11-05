# -*- coding: utf-8 -*-
"""صف ایده‌ها — ثبت پیشاپیش در RESEARCH_LOG (2026-11-05T05:35Z).

H-MARI-V-022: T-006 با کنترل نوسان (هدف ۵۰٪ سالانه، بازتوزیع دوشنبه یا تغییر روند).
H-MARI-G-023: تقاطع طلایی ۵۰/۲۰۰.
هر دو باید روی BTC و ETH هر دو، T-006 همان دارایی را بزنند. فقط تمرینی.
"""
from __future__ import annotations

import math

DAY_MS = 86_400_000
VOL_TARGET, VOL_N = 0.50, 20

IDEA_HYPOTHESES = {
    "H-MARI-V-022": "T-006 با کنترل نوسان (هدف ۵۰٪): شارپ بیشتر و افت کمتر از T-006، روی BTC و ETH.",
    "H-MARI-G-023": "تقاطع طلایی ۵۰/۲۰۰: شارپ بیشتر و افت کمتر یا برابر T-006، روی BTC و ETH.",
}


def _sma(c, k, n):
    return sum(c[k - n + 1: k + 1]) / n if k >= n - 1 else None


def realized_vol(c, k, n=VOL_N):
    if k < n:
        return None
    r = [math.log(c[i] / c[i - 1]) for i in range(k - n + 1, k + 1)]
    m = sum(r) / n
    return math.sqrt(sum((x - m) ** 2 for x in r) / (n - 1)) * math.sqrt(365)


def t006_for(sym):
    def fn(k, ctx):
        st, c = ctx["state"], ctx["c"][sym]
        if k < 149:
            return None
        ok = c[k] > _sma(c, k, 150)
        if ok != st.get("in"):
            st["in"] = ok
            return {sym: 1.0} if ok else {}
        return None
    return fn


def voltarget_for(sym, target=VOL_TARGET):
    def fn(k, ctx):
        st, c = ctx["state"], ctx["c"][sym]
        if k < 149:
            return None
        ok = c[k] > _sma(c, k, 150)
        monday = (ctx["days"][k] // DAY_MS + 3) % 7 == 0
        if ok != st.get("in") or (ok and monday):
            st["in"] = ok
            if not ok:
                return {}
            v = realized_vol(c, k)
            return {sym: min(1.0, target / v) if v else 1.0}
        return None
    return fn


def golden_for(sym):
    def fn(k, ctx):
        st, c = ctx["state"], ctx["c"][sym]
        if k < 199:
            return None
        ok = _sma(c, k, 50) > _sma(c, k, 200)
        if ok != st.get("in"):
            st["in"] = ok
            return {sym: 1.0} if ok else {}
        return None
    return fn


def run_ideas(daily: dict, start_ms: int, end_ms: int) -> dict:
    from .classics import run_weights
    out, ok = {}, {"H-MARI-V-022": True, "H-MARI-G-023": True}
    for sym in ("BTCUSDT", "ETHUSDT"):
        d = {sym: daily[sym]}
        t6, _, _ = run_weights(d, [sym], start_ms, end_ms, t006_for(sym))
        vt, _, _ = run_weights(d, [sym], start_ms, end_ms, voltarget_for(sym))
        gc, _, _ = run_weights(d, [sym], start_ms, end_ms, golden_for(sym))
        s6, m6 = t6.get("sharpe") or 9, t6.get("max_drawdown_pct", 0)
        ok["H-MARI-V-022"] &= bool((vt.get("sharpe") or -9) > s6 and vt.get("max_drawdown_pct", 100) < m6)
        ok["H-MARI-G-023"] &= bool((gc.get("sharpe") or -9) > s6 and gc.get("max_drawdown_pct", 100) <= m6)
        out[sym] = {"T-006": t6, "H-MARI-V-022": vt, "H-MARI-G-023": gc}
    return {"by_asset": out, "verdict": {k: "SUPPORTED_IN_TEST_RANGE" if v else "FALSIFIED" for k, v in ok.items()}}


# ---------------------------------------------------------------- ایده‌های ۳ و ۴ (ثبت 2026-11-05T05:45Z)
HALVINGS = ("2016-07-09", "2020-05-11", "2024-04-20")
HALVING_HOLD_DAYS = 548
IDEA2_HYPOTHESES = {
    "H-MARI-H-024": "نگه‌داری از هاوینگ تا ۱۸ ماه بعد: شارپ بیشتر و افت کمتر یا برابر T-006، روی BTC و ETH.",
    "H-MARI-W-025": "روز برتر هفته (کشف ۲۰۱۸-۲۰۲۲) در ۲۰۲۳ تا اکنون هم بالاتر از میانگین است (CI95)، روی BTC و ETH.",
}


def _ms(d):
    from datetime import datetime, timezone
    return int(datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)


def halving_for(sym):
    windows = [(_ms(h), _ms(h) + HALVING_HOLD_DAYS * DAY_MS) for h in HALVINGS]

    def fn(k, ctx):
        st, t = ctx["state"], ctx["days"][k]
        ok = any(a <= t < b for a, b in windows)
        if ok != st.get("in"):
            st["in"] = ok
            return {sym: 1.0} if ok else {}
        return None
    return fn


def weekday(t):
    return (t // DAY_MS + 3) % 7          # ۰=دوشنبه … ۶=یکشنبه


def day_returns(bars):
    """بازده روز d = بستهٔ d / بستهٔ d-1 − ۱، با برچسب روز هفتهٔ d."""
    return [(bars[i]["t"], weekday(bars[i]["t"]), bars[i]["c"] / bars[i - 1]["c"] - 1) for i in range(1, len(bars))]


def weekday_test(bars, disc: tuple, test: tuple, day: int | None = None) -> dict:
    from .ict import _diff_ci
    rs = day_returns(bars)
    d_rows = [r for r in rs if disc[0] <= r[0] <= disc[1]]
    means = {}
    for w in range(7):
        xs = [r[2] for r in d_rows if r[1] == w]
        means[w] = sum(xs) / len(xs) if xs else float("-inf")
    best = day if day is not None else max(means, key=means.get)
    t_rows = [r for r in rs if test[0] <= r[0] <= test[1]]
    sample = [r[2] for r in t_rows if r[1] == best]
    base = [r[2] for r in t_rows]
    return {"best_day": best, "discovery_means_pct": {w: round(m * 100, 3) for w, m in means.items()},
            "test_vs_all": _diff_ci(sample, base), "test_n": len(sample)}


def run_ideas2(daily: dict, start_ms: int, end_ms: int) -> dict:
    from .classics import run_weights
    out, ok_h = {}, True
    for sym in ("BTCUSDT", "ETHUSDT"):
        d = {sym: daily[sym]}
        t6, _, _ = run_weights(d, [sym], start_ms, end_ms, t006_for(sym))
        hv, _, _ = run_weights(d, [sym], start_ms, end_ms, halving_for(sym))
        ok_h &= bool((hv.get("sharpe") or -9) > (t6.get("sharpe") or 9)
                     and hv.get("max_drawdown_pct", 100) <= t6.get("max_drawdown_pct", 0))
        out[sym] = {"T-006": t6, "H-MARI-H-024": hv}
    disc, test = (start_ms, _ms("2022-12-31")), (_ms("2023-01-01"), end_ms)
    wb = weekday_test(daily["BTCUSDT"], disc, test)
    we = weekday_test(daily["ETHUSDT"], disc, test, day=wb["best_day"])
    ok_w = bool(wb["test_vs_all"] and we["test_vs_all"] and wb["test_vs_all"]["ci95_low"] > 0
                and we["test_vs_all"]["ci95_low"] > 0)
    return {"halving": out, "weekday": {"BTCUSDT": wb, "ETHUSDT": we},
            "verdict": {"H-MARI-H-024": "SUPPORTED_IN_TEST_RANGE" if ok_h else "FALSIFIED",
                        "H-MARI-W-025": "SUPPORTED_IN_TEST_RANGE" if ok_w else "FALSIFIED"}}
