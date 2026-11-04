# -*- coding: utf-8 -*-
"""روش‌های کلاسیک بزرگان بازار روی BTC/ETH روزانه — همه ثبت‌شده پیش از دیدن نتیجه.

H-MARI-C-007  Turtle (Richard Dennis / Donchian): ورود با شکست سقف ۵۵روزه، خروج با شکست کف ۲۰روزه (BTC).
H-MARI-C-008  Dual Momentum (Gary Antonacci): هر ماه، از BTC و ETH آن‌که بازده ۹۰روزه‌اش بیشتر است، به شرط
              بازده مثبت؛ وگرنه نقد.
H-MARI-C-009  RSI(2) Mean Reversion (Larry Connors): BTC بالای میانگین ۲۰۰روزه و RSI(2) < ۱۰ → خرید؛
              خروج وقتی بسته بالای میانگین ۵روزه رفت.
D-010 (توصیفی، فرضیه نیست) خرید پله‌ای هفتگی (DCA) BTC در برابر DCA با فیلتر روند ۱۵۰روزه.

معیار رد (همان استحکام T-006): شارپ ≤ شارپ نگه‌داری BTC یا بیشترین افت ≥ افت BTC یا کران پایین CI95
میانگین بازده هفتگی ≤ ۰. تصمیم روی بستهٔ روز t، اجرا روی بستهٔ روز t+1 (محافظه‌کارانه). فقط تمرینی.
"""
from __future__ import annotations

from .indicators import rsi
from .momentum import DAY_MS, _stats

CLASSIC_HYPOTHESES = {
    "H-MARI-C-007": "Turtle: شکست سقف ۵۵روزه → خرید BTC؛ شکست کف ۲۰روزه → نقد.",
    "H-MARI-C-008": "Dual Momentum: ماهانه، قوی‌ترِ BTC/ETH در ۹۰ روز اگر بازده مثبت؛ وگرنه نقد.",
    "H-MARI-C-009": "RSI(2) Connors: BTC بالای SMA200 و RSI2<10 → خرید؛ بسته > SMA5 → فروش.",
}
FALSIFIED_IF = "شارپ ≤ شارپ BTC یا بیشترین افت ≥ افت BTC یا کران پایین CI95 هفتگی ≤ ۰"


def _align(daily: dict, syms, start_ms, end_ms):
    maps = {s: {b["t"]: b for b in daily[s]} for s in syms}
    days = sorted(set.intersection(*[set(m) for m in maps.values()]))
    return [t for t in days if t <= end_ms], maps, [i for i, t in enumerate(days) if start_ms <= t <= end_ms]


def run_weights(daily: dict, syms: list, start_ms: int, end_ms: int, weight_fn, fee=0.001, slip=0.0005):
    """weight_fn(k, ctx) → {sym: وزن} بر اساس دادهٔ تا روز k. اجرا در بستهٔ روز k+1."""
    days, maps, idx = _align(daily, syms, start_ms, end_ms)
    closes = {s: [maps[s][t]["c"] for t in days] for s in syms}
    highs = {s: [maps[s][t]["h"] for t in days] for s in syms}
    lows = {s: [maps[s][t]["l"] for t in days] for s in syms}
    ctx = {"c": closes, "h": highs, "l": lows, "state": {}, "days": days}
    eq, units, cash = 1.0, {s: 0.0 for s in syms}, 1.0
    curve, weekly, last_w, pending, trades, cash_days = [], [], None, None, 0, 0
    for n, k in enumerate(idx):
        if pending is not None:                          # اجرای تصمیم دیروز با قیمت امروز
            eq = cash + sum(units[s] * closes[s][k] for s in syms)
            cur = {s: units[s] * closes[s][k] for s in syms}
            tgt = {s: eq * pending.get(s, 0.0) for s in syms}
            turnover = sum(abs(tgt[s] - cur[s]) for s in syms)
            if turnover > 1e-9:
                trades += 1
            eq -= turnover * (fee + slip)
            scale = eq / (eq + turnover * (fee + slip)) if eq > 0 else 0
            for s in syms:
                units[s] = tgt[s] * scale / closes[s][k]
            cash = eq - sum(units[s] * closes[s][k] for s in syms)
            pending = None
        eq = cash + sum(units[s] * closes[s][k] for s in syms)
        if all(u == 0 for u in units.values()):
            cash_days += 1
        curve.append(eq)
        if n % 7 == 0:
            if last_w:
                weekly.append(eq / last_w - 1)
            last_w = eq
        w = weight_fn(k, ctx)
        if w is not None:
            pending = w
    n_days = (days[idx[-1]] - days[idx[0]]) / DAY_MS if idx else 0
    st = _stats(curve, n_days, weekly)
    st["trades"] = trades
    st["time_in_cash_pct"] = round(cash_days / max(1, len(idx)) * 100, 1)
    return st, curve, [days[k] for k in idx]


def _sma(xs, k, n):
    return sum(xs[k - n + 1: k + 1]) / n if k >= n - 1 else None


def turtle(k, ctx, entry=55, exit_=20, sym="BTCUSDT"):
    c, h, l = ctx["c"][sym], ctx["h"][sym], ctx["l"][sym]
    if k < entry:
        return None
    st = ctx["state"]
    inpos = st.get("in", False)
    if not inpos and c[k] > max(h[k - entry: k]):
        st["in"] = True
        return {sym: 1.0}
    if inpos and c[k] < min(l[k - exit_: k]):
        st["in"] = False
        return {}
    return None


def dual_momentum(k, ctx, lookback=90, syms=("BTCUSDT", "ETHUSDT")):
    if k < lookback:
        return None
    st = ctx["state"]
    if k - st.get("last", -999) < 30:               # بازبینی ماهانه
        return None
    st["last"] = k
    rets = {s: ctx["c"][s][k] / ctx["c"][s][k - lookback] - 1 for s in syms}
    best = max(rets, key=rets.get)
    return {best: 1.0} if rets[best] > 0 else {}


def connors_rsi2(k, ctx, sym="BTCUSDT"):
    c = ctx["c"][sym]
    st = ctx["state"]
    if "rsi2" not in st:
        st["rsi2"] = rsi(c, 2)
    if k < 200:
        return None
    r = st["rsi2"][k]
    if not st.get("in") and c[k] > _sma(c, k, 200) and r == r and r < 10:
        st["in"] = True
        return {sym: 1.0}
    if st.get("in") and c[k] > _sma(c, k, 5):
        st["in"] = False
        return {}
    return None


def hold_btc(k, ctx):
    if not ctx["state"].get("done"):
        ctx["state"]["done"] = True
        return {"BTCUSDT": 1.0}
    return None


def dca(daily: dict, start_ms: int, end_ms: int, weekly_usd: float = 10.0, trend_filter: int = 0,
        fee=0.001, slip=0.0005) -> dict:
    """خرید پله‌ای هفتگی. با trend_filter>0: پول هفته‌هایی که BTC زیر میانگین است نقد جمع می‌شود و
    کل دارایی BTC هم در آن حالت نقد می‌شود؛ وقتی بالای میانگین برگشت، همه وارد BTC می‌شود."""
    bars = [b for b in daily["BTCUSDT"] if b["t"] <= end_ms]
    c = [b["c"] for b in bars]
    invested, cash, units, vals, peak, mdd = 0.0, 0.0, 0.0, [], 0.0, 0.0
    weeks = 0
    for k, b in enumerate(bars):
        if b["t"] < start_ms:
            continue
        above = True
        if trend_filter:
            s = _sma(c, k, trend_filter)
            above = s is not None and c[k] > s
        if ((b["t"] // DAY_MS) + 3) % 7 == 0:            # دوشنبه‌ها
            invested += weekly_usd
            cash += weekly_usd
            weeks += 1
        if above and cash > 0:
            units += cash * (1 - fee) / (c[k] * (1 + slip))
            cash = 0.0
        elif not above and units > 0:
            cash += units * c[k] * (1 - slip) * (1 - fee)
            units = 0.0
        v = cash + units * c[k]
        vals.append(v)
        peak = max(peak, v)
        if peak > 0:
            mdd = max(mdd, (peak - v) / peak)
    final = vals[-1] if vals else 0.0
    return {"weeks": weeks, "weekly_usd": weekly_usd, "invested": round(invested, 2), "final_value": round(final, 2),
            "multiple": round(final / invested, 3) if invested else None,
            "max_drawdown_of_value_pct": round(mdd * 100, 2)}


STRATEGIES = {
    "H-MARI-C-007": (["BTCUSDT"], turtle),
    "H-MARI-C-008": (["BTCUSDT", "ETHUSDT"], dual_momentum),
    "H-MARI-C-009": (["BTCUSDT"], connors_rsi2),
}


def run_classics(daily: dict, start_ms: int, end_ms: int) -> dict:
    out = {}
    base, _, _ = run_weights(daily, ["BTCUSDT"], start_ms, end_ms, hold_btc)
    out["BTC_BUY_HOLD"] = base
    for hid, (syms, fn) in STRATEGIES.items():
        st, _, _ = run_weights(daily, syms, start_ms, end_ms, fn)
        ci = st.get("weekly_bootstrap") or {}
        ok = (st.get("sharpe") or -9) > (base.get("sharpe") or 9) and \
            st.get("max_drawdown_pct", 100) < base.get("max_drawdown_pct", 0) and ci and ci["ci95_low"] > 0
        out[hid] = {"statement": CLASSIC_HYPOTHESES[hid], "verdict": "SUPPORTED_IN_TEST_RANGE" if ok else "FALSIFIED",
                    **st}
    out["D-010"] = {"dca_plain": dca(daily, start_ms, end_ms),
                    "dca_trend150": dca(daily, start_ms, end_ms, trend_filter=150)}
    return out
