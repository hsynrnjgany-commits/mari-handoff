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


# ---------------------------------------------------------------- ایده‌های ۵ و ۶ (ثبت 2026-11-05T06:00Z)
WILLIAMS_K = 0.5
BB_N, BB_K, SQUEEZE_LOOKBACK, SQUEEZE_VALID = 20, 2.0, 125, 10
FEE, SLIP = 0.001, 0.0005
IDEA3_HYPOTHESES = {
    "H-MARI-L-026": "شکست نوسانی ویلیامز (باز + ۰٫۵×دامنهٔ دیروز، خروج در باز فردا): شارپ بیشتر و افت کمتر یا برابر T-006، روی BTC و ETH.",
    "H-MARI-B-027": "فشردگی بولینگر (پهنای کمینهٔ ۱۲۵روزه، ورود با بسته بالای باند در ۱۰ روز، خروج زیر SMA20): شارپ بیشتر و افت کمتر یا برابر T-006، روی BTC و ETH.",
}


def williams_sim(bars: list[dict], start_ms: int, end_ms: int, k: float = WILLIAMS_K) -> dict:
    """شبیه‌سازی روزانه: ورود درون‌روزی در سطح شکست، خروج در باز روز بعد. سرمایه کامل در هر معامله."""
    from .momentum import _stats
    idx = [i for i, b in enumerate(bars) if start_ms <= b["t"] <= end_ms and i >= 1]
    eq, curve, weekly, last_w, trades = 1.0, [1.0], [], 1.0, 0     # سرمایهٔ آغازین پیش از اولین روز
    for n, i in enumerate(idx, start=1):
        b, p = bars[i], bars[i - 1]
        level = b["o"] + k * (p["h"] - p["l"])
        if b["h"] >= level and i + 1 < len(bars):
            entry = max(b["o"], level) * (1 + SLIP)
            exit_ = bars[i + 1]["o"] * (1 - SLIP)
            eq *= (exit_ / entry) * (1 - FEE) ** 2
            trades += 1
        curve.append(eq)
        if n % 7 == 0:
            if last_w:
                weekly.append(eq / last_w - 1)
            last_w = eq
    days = (bars[idx[-1]]["t"] - bars[idx[0]]["t"]) / DAY_MS + 1 if idx else 0
    st = _stats(curve, days, weekly)
    st["trades"] = trades
    st["time_in_cash_pct"] = None
    return st


def _bands(c, k):
    if k < BB_N - 1:
        return None
    w = c[k - BB_N + 1: k + 1]
    m = sum(w) / BB_N
    sd = math.sqrt(sum((x - m) ** 2 for x in w) / BB_N)
    return m, m + BB_K * sd, (2 * BB_K * sd) / m


def bollinger_for(sym):
    def fn(k, ctx):
        st, c = ctx["state"], ctx["c"][sym]
        bw = st.setdefault("bw", [])
        b = _bands(c, k)
        bw.append(b[2] if b else None)
        if b is None:
            return None
        hist = [x for x in bw[-SQUEEZE_LOOKBACK:] if x is not None]
        if len(hist) >= SQUEEZE_LOOKBACK and b[2] <= min(hist):
            st["squeeze_k"] = k
        if st.get("in"):
            if c[k] < b[0]:
                st["in"] = False
                return {}
            return None
        sk = st.get("squeeze_k")
        if sk is not None and 0 <= k - sk <= SQUEEZE_VALID and c[k] > b[1]:
            st["in"] = True
            return {sym: 1.0}
        return None
    return fn


def run_ideas3(daily: dict, start_ms: int, end_ms: int) -> dict:
    from .classics import run_weights
    out, ok = {}, {"H-MARI-L-026": True, "H-MARI-B-027": True}
    for sym in ("BTCUSDT", "ETHUSDT"):
        d = {sym: daily[sym]}
        t6, _, _ = run_weights(d, [sym], start_ms, end_ms, t006_for(sym))
        lw = williams_sim(daily[sym], start_ms, end_ms)
        bb, _, _ = run_weights(d, [sym], start_ms, end_ms, bollinger_for(sym))
        s6, m6 = t6.get("sharpe") or 9, t6.get("max_drawdown_pct", 0)
        for hid, st in (("H-MARI-L-026", lw), ("H-MARI-B-027", bb)):
            ok[hid] &= bool((st.get("sharpe") or -9) > s6 and st.get("max_drawdown_pct", 100) <= m6)
        out[sym] = {"T-006": t6, "H-MARI-L-026": lw, "H-MARI-B-027": bb}
    return {"by_asset": out, "verdict": {k: "SUPPORTED_IN_TEST_RANGE" if v else "FALSIFIED" for k, v in ok.items()}}


# ---------------------------------------------------------------- ایده‌های ۷ و ۸ (ثبت 2026-11-05T06:10Z)
IDEA4_HYPOTHESES = {
    "H-MARI-M-028": "قالب روند مینروینی (SMA50>150>200، SMA200 صعودی، ≥۲۵٪ بالای کف و ≤۲۵٪ زیر سقف سالانه): شارپ بیشتر و افت کمتر یا برابر T-006، روی BTC و ETH.",
    "H-MARI-R-029": "جام مقدس راشکی (ADX>30 صعودی، پولبک به EMA20، ورود با بستهٔ بالای سقف پولبک): شارپ بیشتر و افت کمتر یا برابر T-006، روی BTC و ETH.",
}


def minervini_for(sym):
    def fn(k, ctx):
        st, c = ctx["state"], ctx["c"][sym]
        if k < 365:
            return None
        s50, s150, s200 = _sma(c, k, 50), _sma(c, k, 150), _sma(c, k, 200)
        s200_ago = _sma(c, k - 20, 200)
        lo, hi = min(ctx["l"][sym][k - 364: k + 1]), max(ctx["h"][sym][k - 364: k + 1])
        ok = (c[k] > s50 > s150 > s200 and s200 > s200_ago and c[k] >= 1.25 * lo and c[k] >= 0.75 * hi)
        if ok != st.get("in"):
            st["in"] = ok
            return {sym: 1.0} if ok else {}
        return None
    return fn


def holy_grail_for(sym):
    from .indicators import adx, ema

    def fn(k, ctx):
        st, c, h, l = ctx["state"], ctx["c"][sym], ctx["h"][sym], ctx["l"][sym]
        if "adx" not in st:                       # هر دو شاخص بازگشتی‌اند: مقدار k فقط به دادهٔ ≤ k بستگی دارد
            bars = [{"h": h[i], "l": l[i], "c": c[i]} for i in range(len(c))]
            st["adx"], st["ema"] = adx(bars, 14), ema(c, 20)
        a, e = st["adx"], st["ema"]
        if k < 40 or a[k] != a[k] or e[k] != e[k]:
            return None
        if st.get("in"):
            if c[k] < st["stop"] or c[k] > st["target"]:
                st["in"] = False
                return {}
            return None
        strong = a[k] > 30 and a[k - 5] == a[k - 5] and a[k] > a[k - 5]
        if strong and l[k] <= e[k] and c[k - 1] > e[k - 1]:
            st["pb"] = {"k": k, "high": h[k], "low": l[k]}
        pb = st.get("pb")
        if pb and 0 < k - pb["k"] <= 5 and c[k] > pb["high"]:
            st.update({"in": True, "stop": pb["low"], "target": max(h[k - 20: k])})
            st["pb"] = None
            return {sym: 1.0}
        return None
    return fn


def run_ideas4(daily: dict, start_ms: int, end_ms: int) -> dict:
    from .classics import run_weights
    out, ok = {}, {"H-MARI-M-028": True, "H-MARI-R-029": True}
    for sym in ("BTCUSDT", "ETHUSDT"):
        d = {sym: daily[sym]}
        t6, _, _ = run_weights(d, [sym], start_ms, end_ms, t006_for(sym))
        mv, _, _ = run_weights(d, [sym], start_ms, end_ms, minervini_for(sym))
        hg, _, _ = run_weights(d, [sym], start_ms, end_ms, holy_grail_for(sym))
        s6, m6 = t6.get("sharpe") or 9, t6.get("max_drawdown_pct", 0)
        for hid, st in (("H-MARI-M-028", mv), ("H-MARI-R-029", hg)):
            ok[hid] &= bool((st.get("sharpe") or -9) > s6 and st.get("max_drawdown_pct", 100) <= m6)
        out[sym] = {"T-006": t6, "H-MARI-M-028": mv, "H-MARI-R-029": hg}
    return {"by_asset": out, "verdict": {k: "SUPPORTED_IN_TEST_RANGE" if v else "FALSIFIED" for k, v in ok.items()}}


# ---------------------------------------------------------------- ایده‌های ۹ و ۱۰ (ثبت 2026-11-05T06:20Z)
IDEA5_HYPOTHESES = {
    "H-MARI-E-030": "صفحهٔ سه‌گانهٔ الدر (EMA13 هفتگی صعودی، شاخص نیروی منفی، ورود با شکست سقف دیروز): شارپ بیشتر و افت کمتر یا برابر T-006، روی BTC و ETH.",
    "H-MARI-K-031": "KAMA کافمن (۱۰، ۲، ۳۰): نگه‌داری بالای KAMA. شارپ بیشتر و افت کمتر یا برابر T-006، روی BTC و ETH.",
}


def _ema_list(xs, n):
    k, e, out = 2 / (n + 1), None, []
    for x in xs:
        e = x if e is None else x * k + e * (1 - k)
        out.append(e)
    return out


def weekly_ema(c, k, n=13, weeks=60):
    """EMA13 روی بسته‌های هر ۷ روز که به روز k ختم می‌شوند (فقط دادهٔ ≤ k)."""
    idx = list(range(k, max(-1, k - 7 * weeks), -7))[::-1]
    if len(idx) < n + 5:
        return None
    return _ema_list([c[i] for i in idx], n)[-1]


def kama(c, er_n=10, fast=2, slow=30):
    out = [None] * len(c)
    fs, ss = 2 / (fast + 1), 2 / (slow + 1)
    for i in range(len(c)):
        if i < er_n:
            continue
        if out[i - 1] is None:
            out[i] = c[i]
            continue
        change = abs(c[i] - c[i - er_n])
        vol = sum(abs(c[j] - c[j - 1]) for j in range(i - er_n + 1, i + 1))
        er = change / vol if vol > 0 else 0
        sc = (er * (fs - ss) + ss) ** 2
        out[i] = out[i - 1] + sc * (c[i] - out[i - 1])
    return out


def elder_for(sym, volumes: dict):
    def fn(k, ctx):
        st, c, h = ctx["state"], ctx["c"][sym], ctx["h"][sym]
        if k < 7 * 20:
            return None
        w_now, w_prev = weekly_ema(c, k), weekly_ema(c, k - 7)
        if w_now is None or w_prev is None:
            return None
        up = w_now > w_prev
        if st.get("in"):
            if not up:
                st["in"] = False
                return {}
            return None
        if "fi" not in st:
            days = ctx["days"]
            raw = [0.0] + [(c[i] - c[i - 1]) * volumes.get(days[i], 0.0) for i in range(1, len(c))]
            st["fi"] = _ema_list(raw, 2)            # بازگشتی: مقدار i فقط به دادهٔ ≤ i بستگی دارد
        if up and st["fi"][k] < 0:
            st["pb_k"] = k
        pk = st.get("pb_k")
        if up and pk is not None and 0 < k - pk <= 5 and c[k] > h[k - 1]:
            st["in"], st["pb_k"] = True, None
            return {sym: 1.0}
        return None
    return fn


def kama_for(sym):
    def fn(k, ctx):
        st, c = ctx["state"], ctx["c"][sym]
        if "kama" not in st:
            st["kama"] = kama(c)
        km = st["kama"][k]
        if km is None or k < 30:
            return None
        ok = c[k] > km
        if ok != st.get("in"):
            st["in"] = ok
            return {sym: 1.0} if ok else {}
        return None
    return fn


def run_ideas5(daily: dict, start_ms: int, end_ms: int) -> dict:
    from .classics import run_weights
    out, ok = {}, {"H-MARI-E-030": True, "H-MARI-K-031": True}
    for sym in ("BTCUSDT", "ETHUSDT"):
        d = {sym: daily[sym]}
        vol = {b["t"]: b.get("v", 0.0) for b in daily[sym]}
        t6, _, _ = run_weights(d, [sym], start_ms, end_ms, t006_for(sym))
        el, _, _ = run_weights(d, [sym], start_ms, end_ms, elder_for(sym, vol))
        ka, _, _ = run_weights(d, [sym], start_ms, end_ms, kama_for(sym))
        s6, m6 = t6.get("sharpe") or 9, t6.get("max_drawdown_pct", 0)
        for hid, st in (("H-MARI-E-030", el), ("H-MARI-K-031", ka)):
            ok[hid] &= bool((st.get("sharpe") or -9) > s6 and st.get("max_drawdown_pct", 100) <= m6)
        out[sym] = {"T-006": t6, "H-MARI-E-030": el, "H-MARI-K-031": ka}
    return {"by_asset": out, "verdict": {k: "SUPPORTED_IN_TEST_RANGE" if v else "FALSIFIED" for k, v in ok.items()}}
