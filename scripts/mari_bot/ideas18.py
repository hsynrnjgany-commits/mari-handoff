# -*- coding: utf-8 -*-
"""ideas18 — ثبت پیشاپیش در RESEARCH_LOG (2026-11-06T03:00Z). فقط تمرینی.

H-MARI-T-065: تنها روش برنده (T-006: نگه‌داری وقتی قیمت بالای میانگین ۱۵۰ روزه است) روی
              **دادهٔ کوین‌بیس پیش از شروع بایننس** (۲۰۱۵-۰۷ تا ۲۰۱۸-۰۵) — دوره‌ای که هیچ آزمونی
              در این پروژه تاکنون آن را ندیده است.

اطلاعی (بدون شمارش به‌عنوان فرضیه): همان قاعده روی بای‌بیت، فقط برای اطمینان از اینکه
نتیجه‌ها وابسته به دادهٔ یک صرافی نیستند.
"""
from __future__ import annotations

from .ideas import t006_for
from .ideas9 import LENGTHS, hold_for, trend_n_for

DAY_MS = 86_400_000

IDEA18_HYPOTHESES = {
    "H-MARI-T-065": "T-006 روی دادهٔ کوین‌بیس در دورهٔ دیده‌نشدهٔ پیش از بایننس (BTC از ۲۰۱۵-۰۷، ETH از ۲۰۱۶-۱۱، تا ۲۰۱۸-۰۵): شارپ بیشتر و بیشترین افت کمتر از خرید-و-نگه‌داری، روی BTC و ETH هر دو.",
}


def _sh(x):
    return x.get("sharpe") if x.get("sharpe") is not None else -9.0


def beats_hold(t6: dict, bh: dict) -> bool:
    return bool(_sh(t6) > _sh(bh) and t6.get("max_drawdown_pct", 100) < bh.get("max_drawdown_pct", 0))


def run_period(bars: list, sym: str, start_ms: int, end_ms: int) -> dict:
    from .classics import run_weights
    d = {sym: bars}
    t6, _, _ = run_weights(d, [sym], start_ms, end_ms, t006_for(sym))
    bh, _, _ = run_weights(d, [sym], start_ms, end_ms, hold_for(sym))
    lengths = {f"SMA{n}": run_weights(d, [sym], start_ms, end_ms, trend_n_for(sym, n))[0] for n in LENGTHS}
    return {"T-006": t6, "BUY_HOLD": bh, "lengths_info": lengths, "beats_hold": beats_hold(t6, bh)}


def run_ideas18(coinbase: dict, windows: dict, full_end: int, bybit: dict | None = None,
                binance: dict | None = None, bybit_window: tuple | None = None) -> dict:
    """coinbase/bybit/binance: {sym: کندل‌های روزانه}. windows: {sym: (شروع، پایان)} دورهٔ دیده‌نشده."""
    out, ok = {}, True
    for sym in ("BTCUSDT", "ETHUSDT"):
        bars = coinbase.get(sym) or []
        if len(bars) < 300 or sym not in windows:
            out[sym] = {"insufficient": True, "bars": len(bars)}
            ok = False
            continue
        s, e = windows[sym]
        held_out = run_period(bars, sym, s, e)
        full = run_period(bars, sym, s, full_end)
        out[sym] = {"held_out": held_out, "full_period_info": full,
                    "bars": len(bars), "first_day": bars[0]["t"]}
        ok &= held_out["beats_hold"]
    rep = {"by_asset": out,
           "verdict": {"H-MARI-T-065": "SUPPORTED_IN_TEST_RANGE" if ok else "FALSIFIED"}}
    if bybit is not None and bybit_window:
        from .venues import compare_closes
        cmp_ = {}
        for sym in ("BTCUSDT", "ETHUSDT"):
            by, bn = (bybit or {}).get(sym) or [], (binance or {}).get(sym) or []
            if len(by) < 300 or len(bn) < 300:
                cmp_[sym] = {"available": False, "bybit_bars": len(by)}
                continue
            s, e = bybit_window
            r_by, r_bn = run_period(by, sym, s, e), run_period(bn, sym, s, e)
            cmp_[sym] = {"available": True, "data_check": compare_closes(by, bn),
                         "bybit_T006": r_by["T-006"], "binance_T006": r_bn["T-006"],
                         "bybit_beats_hold": r_by["beats_hold"], "binance_beats_hold": r_bn["beats_hold"],
                         "same_conclusion": r_by["beats_hold"] == r_bn["beats_hold"]}
        rep["bybit_replication_info"] = cmp_
    return rep
