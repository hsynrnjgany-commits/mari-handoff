# -*- coding: utf-8 -*-
"""ideas9 — ثبت پیشاپیش در RESEARCH_LOG (2026-11-05T17:20Z). فقط تمرینی.

H-MARI-R-048: استحکام T-006 — میانگین‌های ۱۰۰/۱۲۵/۱۷۵/۲۰۰ هم باید کار کنند (آیا ۱۵۰ شانسی انتخاب شده؟).
H-MARI-W-049: T-006 هفتگی — تصمیم فقط با بستهٔ یکشنبه، برای معاملهٔ کمتر.
H-MARI-A-047: سبد BTC + ۱۰ ارز بزرگ با یک دروازهٔ مشترک: فقط وقتی BTC بالای میانگین ۱۵۰ است.
"""
from __future__ import annotations

from .ideas import LARGE_CAPS, _sma

DAY_MS = 86_400_000
LENGTHS = (100, 125, 150, 175, 200)
ROBUST_FRAC = 0.8

IDEA9_HYPOTHESES = {
    "H-MARI-R-048": "استحکام T-006: با میانگین ۱۰۰، ۱۲۵، ۱۷۵ و ۲۰۰ هم شارپ بیشتر از خرید-و-نگه‌داری، و بدترین شارپ دست‌کم ۸۰٪ شارپ ۱۵۰، روی BTC و ETH.",
    "H-MARI-W-049": "T-006 هفتگی (تصمیم فقط یکشنبه‌ها): شارپ برابر یا بیشتر از T-006 روزانه با معاملهٔ کمتر، روی BTC و ETH.",
    "H-MARI-A-047": "سبد BTC + ۱۰ ارز بزرگ با دروازهٔ BTC بالای میانگین ۱۵۰: شارپ بیشتر و افت کمتر یا برابر T-006 روی BTC.",
}


def is_sunday(day_ms: int) -> bool:
    return (day_ms // DAY_MS + 4) % 7 == 0       # ۱۹۷۰-۰۱-۰۱ پنجشنبه بود


def is_monday(day_ms: int) -> bool:
    return (day_ms // DAY_MS + 3) % 7 == 0


def trend_n_for(sym, n):
    def fn(k, ctx):
        st, c = ctx["state"], ctx["c"][sym]
        if k < n - 1:
            return None
        ok = c[k] > _sma(c, k, n)
        if ok != st.get("in"):
            st["in"] = ok
            return {sym: 1.0} if ok else {}
        return None
    return fn


def weekly_for(sym, n=150):
    def fn(k, ctx):
        st, c = ctx["state"], ctx["c"][sym]
        if k < n - 1 or not is_sunday(ctx["days"][k]):
            return None
        ok = c[k] > _sma(c, k, n)
        if ok != st.get("in"):
            st["in"] = ok
            return {sym: 1.0} if ok else {}
        return None
    return fn


def hold_for(sym):
    def fn(k, ctx):
        if not ctx["state"].get("in"):
            ctx["state"]["in"] = True
            return {sym: 1.0}
        return None
    return fn


def gated_basket_fn(syms, gate="BTCUSDT", n=150):
    """همه با وزن برابر وقتی BTC بالای میانگین است؛ وگرنه نقد. توازن دوباره دوشنبه‌ها."""
    w = 1.0 / len(syms)

    def fn(k, ctx):
        st, c = ctx["state"], ctx["c"][gate]
        if k < n - 1:
            return None
        on = c[k] > _sma(c, k, n)
        if on != st.get("on") or (on and is_monday(ctx["days"][k])):
            st["on"] = on
            return {s: w for s in syms} if on else {}
        return None
    return fn


def _sh(x):
    return x.get("sharpe") if x.get("sharpe") is not None else -9


def run_r_w(daily: dict, start_ms: int, end_ms: int) -> dict:
    from .classics import run_weights
    out, ok_r, ok_w = {}, True, True
    for sym in ("BTCUSDT", "ETHUSDT"):
        d = {sym: daily[sym]}
        bh, _, _ = run_weights(d, [sym], start_ms, end_ms, hold_for(sym))
        by_n = {n: run_weights(d, [sym], start_ms, end_ms, trend_n_for(sym, n))[0] for n in LENGTHS}
        wk, _, _ = run_weights(d, [sym], start_ms, end_ms, weekly_for(sym))
        ref = _sh(by_n[150])
        others = [_sh(by_n[n]) for n in LENGTHS if n != 150]
        ok_r &= bool(all(s > _sh(bh) for s in others) and min(others) >= ROBUST_FRAC * ref)
        ok_w &= bool(_sh(wk) >= ref and wk.get("trades", 9e9) < by_n[150].get("trades", 0))
        out[sym] = {"BUY_HOLD": bh, "H-MARI-W-049": wk, **{f"SMA{n}": by_n[n] for n in LENGTHS}}
    return {"by_asset": out, "ok_r": ok_r, "ok_w": ok_w}


def run_a(daily: dict, start_ms: int, end_ms: int) -> dict:
    from .classics import run_weights
    syms = ["BTCUSDT"] + list(LARGE_CAPS)
    bk, _, _ = run_weights({s: daily[s] for s in syms}, syms, start_ms, end_ms, gated_basket_fn(syms))
    bt, _, _ = run_weights({"BTCUSDT": daily["BTCUSDT"]}, ["BTCUSDT"], start_ms, end_ms,
                           trend_n_for("BTCUSDT", 150))
    ok = bool(_sh(bk) > _sh(bt) and bk.get("max_drawdown_pct", 100) <= bt.get("max_drawdown_pct", 0))
    return {"basket": bk, "btc_t006": bt, "ok": ok}


def verdicts(rw: dict, a: dict) -> dict:
    v = lambda ok: "SUPPORTED_IN_TEST_RANGE" if ok else "FALSIFIED"  # noqa: E731
    return {"H-MARI-R-048": v(rw["ok_r"]), "H-MARI-W-049": v(rw["ok_w"]), "H-MARI-A-047": v(a["ok"])}
