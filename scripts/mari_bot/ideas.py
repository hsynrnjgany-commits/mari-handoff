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
