# -*- coding: utf-8 -*-
"""ideas8 — ثبت پیشاپیش در RESEARCH_LOG (2026-11-05T17:05Z). فقط تمرینی.

H-MARI-F-044: ترس و طمع خلاف جمع (alternative.me) — خرید وقتی شاخص ≤ ۲۰، فروش وقتی ≥ ۷۵.
H-MARI-S-045: اثر هالووین (Bouman & Jacobsen 2002) — بازده روزانهٔ نوامبر تا آوریل منهای مه تا اکتبر.
H-MARI-K-046: حد ضرر متحرک ۱۵٪ روی T-006 (Kaminski & Lo 2014) — بعد از خروج، فقط با تقاطع تازه برمی‌گردد.
"""
from __future__ import annotations

import bisect
from datetime import datetime, timezone

from .ideas import _sma, t006_for
from .ideas7 import _ci_diff

DAY_MS = 86_400_000
FEAR_BUY = 20
GREED_SELL = 75
TRAIL = 0.15
WINTER = (11, 12, 1, 2, 3, 4)

IDEA8_HYPOTHESES = {
    "H-MARI-F-044": "ترس و طمع خلاف جمع (خرید ≤ ۲۰، فروش ≥ ۷۵): شارپ بیشتر از T-006 و از خرید-و-نگه‌داری، روی BTC و ETH.",
    "H-MARI-S-045": "اثر هالووین: میانگین بازده روزانهٔ نوامبر-آوریل منهای مه-اکتبر، CI95 بالای صفر، روی BTC و ETH.",
    "H-MARI-K-046": "حد ضرر متحرک ۱۵٪ روی T-006: شارپ بیشتر و بیشترین افت کمتر از T-006، روی BTC و ETH.",
}


# ---------- داده ----------

def parse_fng(js) -> list[tuple[int, int]]:
    """پاسخ alternative.me → [(زمان ms روز UTC، مقدار)] به ترتیب زمان."""
    out = []
    for row in (js or {}).get("data", []):
        try:
            t = int(row["timestamp"]) * 1000 // DAY_MS * DAY_MS
            out.append((t, int(row["value"])))
        except (KeyError, TypeError, ValueError):
            continue
    out.sort()
    return out


def fetch_fng() -> list[tuple[int, int]]:
    from .data import http_get_json
    js = http_get_json("/fng/", {"limit": 0, "format": "json"}, timeout=30.0,
                       base="https://api.alternative.me")
    return parse_fng(js)


class Series:
    """آخرین مقدار با زمان ≤ t (فقط دادهٔ گذشته)."""

    def __init__(self, pts):
        self.t = [p[0] for p in pts]
        self.v = [p[1] for p in pts]

    def at(self, t):
        i = bisect.bisect_right(self.t, t) - 1
        if i < 0 or t - self.t[i] > 3 * DAY_MS:   # دادهٔ کهنه‌تر از ۳ روز = نامعلوم
            return None
        return self.v[i]


# ---------- F-044 ----------

def fng_for(sym, fng: Series, buy=FEAR_BUY, sell=GREED_SELL):
    """سیگنال در بستهٔ روز k با مقدار شاخص منتشرشده در ابتدای همان روز؛ اجرا در بستهٔ k+1."""
    def fn(k, ctx):
        st = ctx["state"]
        v = fng.at(ctx["days"][k])
        if v is None:
            return None
        if not st.get("in") and v <= buy:
            st["in"] = True
            return {sym: 1.0}
        if st.get("in") and v >= sell:
            st["in"] = False
            return {}
        return None
    return fn


def hold_for(sym):
    def fn(k, ctx):
        if not ctx["state"].get("in"):
            ctx["state"]["in"] = True
            return {sym: 1.0}
        return None
    return fn


# ---------- S-045 ----------

def is_winter(t_ms: int) -> bool:
    return datetime.fromtimestamp(t_ms / 1000, timezone.utc).month in WINTER


def halloween_test(bars, start_ms, end_ms) -> dict:
    w, s = [], []
    for i in range(1, len(bars)):
        t = bars[i]["t"]
        if start_ms <= t <= end_ms:
            r = bars[i]["c"] / bars[i - 1]["c"] - 1
            (w if is_winter(t) else s).append(r)
    return {"n_winter": len(w), "n_summer": len(s),
            "winter_mean_pct": round(sum(w) / max(1, len(w)) * 100, 4),
            "summer_mean_pct": round(sum(s) / max(1, len(s)) * 100, 4),
            "winter_minus_summer": _ci_diff(w, s, seed=45)}


def winter_for(sym):
    """اطلاعی: فقط در ماه‌های زمستانی بازار؛ تصمیم یک روز زودتر تا اجرا در کندل اول ماه باشد."""
    def fn(k, ctx):
        st, days = ctx["state"], ctx["days"]
        want = is_winter(days[k] + DAY_MS)
        if want != st.get("in"):
            st["in"] = want
            return {sym: 1.0} if want else {}
        return None
    return fn


# ---------- K-046 ----------

def trail_for(sym, trail=TRAIL, n=150):
    """T-006 + حد ضرر متحرک روی بسته‌ها. پس از خروج با حد ضرر، تا وقتی قیمت زیر میانگین نرود
    و دوباره بالای آن نیاید، ورود نمی‌کند."""
    def fn(k, ctx):
        st, c = ctx["state"], ctx["c"][sym]
        if k < n - 1:
            return None
        above = c[k] > _sma(c, k, n)
        if not above:
            st["armed"] = True              # پایین میانگین: اجازهٔ ورود بعدی
        if st.get("in"):
            st["peak"] = max(st["peak"], c[k])
            if not above or c[k] <= st["peak"] * (1 - trail):
                st["in"] = False
                st["armed"] = not above
                return {}
            return None
        if above and st.get("armed", True):
            st["in"], st["peak"], st["armed"] = True, c[k], False
            return {sym: 1.0}
        return None
    return fn


# ---------- اجرا ----------

def run_ideas8(daily: dict, fng_pts, start_ms: int, end_ms: int) -> dict:
    from .classics import run_weights
    fng = Series(fng_pts)
    out, ok_f, ok_s, ok_k = {}, True, True, True
    for sym in ("BTCUSDT", "ETHUSDT"):
        d = {sym: daily[sym]}
        t6, _, _ = run_weights(d, [sym], start_ms, end_ms, t006_for(sym))
        bh, _, _ = run_weights(d, [sym], start_ms, end_ms, hold_for(sym))
        fg, _, _ = run_weights(d, [sym], start_ms, end_ms, fng_for(sym, fng))
        wi, _, _ = run_weights(d, [sym], start_ms, end_ms, winter_for(sym))
        tr, _, _ = run_weights(d, [sym], start_ms, end_ms, trail_for(sym))
        hw = halloween_test(daily[sym], start_ms, end_ms)
        sh = lambda x: x.get("sharpe") if x.get("sharpe") is not None else -9  # noqa: E731
        ok_f &= bool(sh(fg) > sh(t6) and sh(fg) > sh(bh))
        ci = hw["winter_minus_summer"]
        ok_s &= bool(ci and ci["ci95_low"] > 0)
        ok_k &= bool(sh(tr) > sh(t6) and tr.get("max_drawdown_pct", 100) < t6.get("max_drawdown_pct", 0))
        out[sym] = {"T-006": t6, "BUY_HOLD": bh, "H-MARI-F-044": fg, "WINTER_ONLY_INFO": wi,
                    "H-MARI-K-046": tr, "H-MARI-S-045": hw}
    v = lambda ok: "SUPPORTED_IN_TEST_RANGE" if ok else "FALSIFIED"  # noqa: E731
    return {"by_asset": out, "fng_points": len(fng_pts),
            "fng_first": datetime.fromtimestamp(fng_pts[0][0] / 1000, timezone.utc).strftime("%Y-%m-%d") if fng_pts else None,
            "verdict": {"H-MARI-F-044": v(ok_f), "H-MARI-S-045": v(ok_s), "H-MARI-K-046": v(ok_k)}}
