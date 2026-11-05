# -*- coding: utf-8 -*-
"""فیلترهای اقتصاد کلان آمریکا برای بیت‌کوین — دادهٔ رسمی FRED (فدرال رزرو سنت‌لوئیس)، ثبت پیشاپیش.

سری‌ها (CSV عمومی، بدون کلید):
  DGS10      بازده اوراق خزانهٔ ۱۰سالهٔ آمریکا (روزانه)
  DTWEXBGS   شاخص گستردهٔ ارزش دلار آمریکا (روزانه، انتشار هفتگی)
  WALCL      کل دارایی‌های فدرال رزرو (هفتگی)
  WTREGEN    حساب عمومی خزانه‌داری نزد فدرال رزرو — TGA (هفتگی)
  RRPONTSYD  ریورس‌ریپوی شبانه (روزانه)
  «نقدینگی خالص» = WALCL − WTREGEN − RRPONTSYD   (میلیون دلار؛ RRP میلیارد → ×۱۰۰۰)

ضد نگاه به آینده: هر مقدار فقط پس از «تأخیر انتشار» ثبت‌شده قابل استفاده است:
  DGS10: ۱ روز · DTWEXBGS: ۷ روز · نقدینگی خالص: ۷ روز.

H-MARI-X-011  BTC فقط وقتی شاخص دلار زیر میانگین ۱۰۰روزه‌اش است (دلار ضعیف)؛ وگرنه نقد.
H-MARI-X-012  BTC فقط وقتی نقدینگی خالص فدرال بالای میانگین ۹۰روزه‌اش است (نقدینگی رو به افزایش)؛ وگرنه نقد.
H-MARI-X-013  BTC فقط وقتی بازده ۱۰ساله زیر میانگین ۱۰۰روزه‌اش است (نرخ‌ها رو به کاهش)؛ وگرنه نقد.
H-MARI-X-014  ترکیب: T-006 (BTC بالای SMA150) و X-012 هر دو برقرار؛ وگرنه نقد.
              معیار اضافه برای X-014: شارپ باید از T-006 تنها بیشتر باشد (وگرنه پیچیدگی بی‌فایده است).
معیار رد مشترک: شارپ ≤ شارپ BTC یا بیشترین افت ≥ افت BTC یا کران پایین CI95 هفتگی ≤ ۰.
"""
from __future__ import annotations

import bisect
from datetime import datetime, timezone

from .data import DataError, http_get_text

DAY_MS = 86_400_000
LAGS = {"DGS10": 1, "DTWEXBGS": 7, "NETLIQ": 7}
MACRO_HYPOTHESES = {
    "H-MARI-X-011": "BTC فقط وقتی شاخص دلار (DTWEXBGS) زیر میانگین ۱۰۰روزه است؛ وگرنه نقد. تأخیر ۷ روز.",
    "H-MARI-X-012": "BTC فقط وقتی نقدینگی خالص فدرال بالای میانگین ۹۰روزه است؛ وگرنه نقد. تأخیر ۷ روز.",
    "H-MARI-X-013": "BTC فقط وقتی بازده ۱۰سالهٔ خزانه زیر میانگین ۱۰۰روزه است؛ وگرنه نقد. تأخیر ۱ روز.",
    "H-MARI-X-014": "BTC بالای SMA150 و نقدینگی خالص بالای میانگین ۹۰روزه؛ وگرنه نقد. باید شارپ T-006 را هم بزند.",
}


def parse_fred_csv(text: str) -> list[tuple[int, float]]:
    out = []
    for line in text.strip().splitlines()[1:]:
        parts = line.split(",")
        if len(parts) < 2 or parts[1].strip() in (".", ""):
            continue
        try:
            t = int(datetime.strptime(parts[0].strip(), "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
            out.append((t, float(parts[1])))
        except ValueError:
            continue
    return out


def fetch_fred(series_id: str) -> list[tuple[int, float]]:
    rows = parse_fred_csv(http_get_text("/graph/fredgraph.csv", {"id": series_id}))
    if not rows:
        raise DataError(f"FRED {series_id} خالی")
    return rows


class Series:
    """سری با ارزش «آخرین مقدار منتشرشده تا لحظهٔ t با تأخیر lag روز»."""

    def __init__(self, rows: list[tuple[int, float]], lag_days: int):
        self.t = [r[0] for r in rows]
        self.v = [r[1] for r in rows]
        self.lag = lag_days * DAY_MS

    def at(self, t: int):
        i = bisect.bisect_right(self.t, t - self.lag) - 1
        return self.v[i] if i >= 0 else None

    def daily_values(self, days: list[int]) -> list:
        return [self.at(t) for t in days]


def net_liquidity(walcl, tga, rrp) -> list[tuple[int, float]]:
    """WALCL و WTREGEN میلیون دلار؛ RRPONTSYD میلیارد دلار. روی تاریخ‌های WALCL (هفتگی)."""
    tga_s, rrp_s = Series(tga, 0), Series(rrp, 0)
    out = []
    for t, w in walcl:
        g, r = tga_s.at(t), rrp_s.at(t)
        if g is not None and r is not None:
            out.append((t, w - g - r * 1000))
    return out


def _sma_list(vals, k, n):
    xs = [x for x in vals[max(0, k - n + 1): k + 1] if x is not None]
    return sum(xs) / len(xs) if len(xs) >= n * 0.8 else None


def make_filter(series: Series, n: int, want_below: bool):
    """تابع وزن برای run_weights: BTC وقتی سری (با تأخیر) زیر/بالای میانگین n روزه‌اش است."""
    def fn(k, ctx, extra=None):
        st = ctx["state"]
        if "vals" not in st:
            st["vals"] = series.daily_values(ctx["days"])
        vals = st["vals"]
        v, m = vals[k], _sma_list(vals, k, n)
        if v is None or m is None:
            return None
        ok = v < m if want_below else v > m
        if extra is not None:
            ok = ok and extra(k, ctx)
        if ok != st.get("in"):
            st["in"] = ok
            return {"BTCUSDT": 1.0} if ok else {}
        return None
    return fn


def btc_above_sma(n=150):
    def ok(k, ctx):
        c = ctx["c"]["BTCUSDT"]
        return k >= n - 1 and c[k] > sum(c[k - n + 1: k + 1]) / n
    return ok


def t006_fn(k, ctx):
    st = ctx["state"]
    if k < 149:
        return None
    ok = btc_above_sma(150)(k, ctx)
    if ok != st.get("in"):
        st["in"] = ok
        return {"BTCUSDT": 1.0} if ok else {}
    return None


def run_macro(daily: dict, macro: dict, start_ms: int, end_ms: int) -> dict:
    """macro: {"DGS10": rows, "DTWEXBGS": rows, "NETLIQ": rows}"""
    from .classics import hold_btc, run_weights
    s_dxy = Series(macro["DTWEXBGS"], LAGS["DTWEXBGS"])
    s_liq = Series(macro["NETLIQ"], LAGS["NETLIQ"])
    s_10y = Series(macro["DGS10"], LAGS["DGS10"])
    strategies = {
        "H-MARI-X-011": make_filter(s_dxy, 100, want_below=True),
        "H-MARI-X-012": make_filter(s_liq, 90, want_below=False),
        "H-MARI-X-013": make_filter(s_10y, 100, want_below=True),
    }
    liq_and_trend = make_filter(s_liq, 90, want_below=False)
    strategies["H-MARI-X-014"] = lambda k, ctx: liq_and_trend(k, ctx, extra=btc_above_sma(150))
    base, _, _ = run_weights(daily, ["BTCUSDT"], start_ms, end_ms, hold_btc)
    t6, _, _ = run_weights(daily, ["BTCUSDT"], start_ms, end_ms, t006_fn)
    out = {"BTC_BUY_HOLD": base, "T-006_REFERENCE": t6}
    for hid, fn in strategies.items():
        st, _, _ = run_weights(daily, ["BTCUSDT"], start_ms, end_ms, fn)
        ci = st.get("weekly_bootstrap") or {}
        ok = ((st.get("sharpe") or -9) > (base.get("sharpe") or 9)
              and st.get("max_drawdown_pct", 100) < base.get("max_drawdown_pct", 0) and ci and ci["ci95_low"] > 0)
        if hid == "H-MARI-X-014":
            ok = ok and (st.get("sharpe") or -9) > (t6.get("sharpe") or 9)
        out[hid] = {"statement": MACRO_HYPOTHESES[hid], "verdict": "SUPPORTED_IN_TEST_RANGE" if ok else "FALSIFIED",
                    **st}
    return out
