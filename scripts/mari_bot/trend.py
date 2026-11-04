# -*- coding: utf-8 -*-
"""طبقه‌بند ۸حالتهٔ روند (سند CORE-DOCTRINE-001، بخش ۳).

A STRONG_BULLISH · B BULLISH · C WEAKENING · D NEUTRAL · E BEARISH · F STRONG_BEARISH · G CRASH · H UNKNOWN

قانون: «هیچ اندیکاتور واحدی اجازهٔ تصمیم‌گیری مستقل ندارد» — امتیاز نهایی جمع ۶ عامل است و
هر عامل فقط سهم محدودی دارد. همهٔ عامل‌ها در خروجی برمی‌گردند تا در دفتر شواهد ثبت شوند.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import indicators as ind
from .config import TrendParams

STATES = {
    "A": "STRONG_BULLISH", "B": "BULLISH", "C": "WEAKENING", "D": "NEUTRAL",
    "E": "BEARISH", "F": "STRONG_BEARISH", "G": "CRASH", "H": "UNKNOWN",
}
STATES_FA = {
    "A": "صعودی قوی", "B": "صعودی", "C": "ضعیف‌شدن صعود", "D": "خنثی",
    "E": "نزولی", "F": "نزولی قوی", "G": "سقوط / ریسک شدید", "H": "نامعلوم",
}
BULLISH = ("A", "B")


@dataclass
class TrendResult:
    state: str
    score: float
    factors: dict
    reason: str

    @property
    def name(self) -> str:
        return STATES[self.state]

    def to_dict(self) -> dict:
        return {"state": self.state, "name": self.name, "score": round(self.score, 2),
                "factors": self.factors, "reason": self.reason}


def _clip(x: float, lo: float = -2.0, hi: float = 2.0) -> float:
    return max(lo, min(hi, x))


class SymbolSeries:
    """سری‌های پیش‌محاسبه‌شدهٔ یک نماد. اندیس i فقط به کندل‌های ≤ i وابسته است."""

    def __init__(self, symbol: str, bars: list[dict], p: TrendParams | None = None):
        self.symbol, self.bars, self.p = symbol, bars, p or TrendParams()
        c = [b["c"] for b in bars]
        self.close = c
        self.ema_f = ind.ema(c, self.p.ema_fast)
        self.ema_m = ind.ema(c, self.p.ema_mid)
        self.ema_s = ind.ema(c, self.p.ema_slow)
        self.atr = ind.atr(bars, self.p.atr_n)
        self.adx = ind.adx(bars, self.p.adx_n)
        self.rsi = ind.rsi(c, self.p.rsi_n)

    def __len__(self):
        return len(self.bars)

    def vol_ratio(self, t: int, short: int = 5, long: int = 50) -> float:
        if t < long:
            return ind.NaN
        s = sum(b["qv"] for b in self.bars[t - short + 1: t + 1]) / short
        lg = sum(b["qv"] for b in self.bars[t - long + 1: t + 1]) / long
        return s / lg if lg > 0 else ind.NaN

    def median_qv(self, t: int, n: int = 20) -> float:
        return ind.median([b["qv"] for b in self.bars[max(0, t - n + 1): t + 1]])

    def ret(self, t: int, n: int) -> float:
        return self.close[t] / self.close[t - n] - 1 if t >= n else ind.NaN


def classify(s: SymbolSeries, t: int, btc_state: str | None = None) -> TrendResult:
    p = s.p
    if t < p.min_bars or t >= len(s):
        return TrendResult("H", 0.0, {}, "INSUFFICIENT_BARS")
    c, ef, em, es = s.close[t], s.ema_f[t], s.ema_m[t], s.ema_s[t]
    a, dx, r = s.atr[t], s.adx[t], s.rsi[t]
    if any(v != v for v in (ef, em, es, a, dx, r)) or a <= 0:
        return TrendResult("H", 0.0, {}, "INDICATOR_NAN")

    # --- G: سقوط / ریسک شدید (پیش از همه) ---
    r24, r4 = s.ret(t, 24), s.ret(t, 4)
    atr_med = ind.median(s.atr[max(0, t - 100): t + 1])
    vol_spike = atr_med == atr_med and atr_med > 0 and a / atr_med >= p.crash_atr_mult
    if r24 <= p.crash_ret_24h or r4 <= p.crash_ret_4h or (vol_spike and r4 < 0):
        return TrendResult("G", -10.0, {"ret_24h": round(r24, 4), "ret_4h": round(r4, 4),
                                        "atr_spike": round(a / atr_med, 2) if atr_med else None},
                           "CRASH_OR_EXTREME_RISK")

    f = {}
    # ۱) چیدمان میانگین‌ها
    stack = (1 if c > ef else -1) + (1 if ef > em else -1) + (1 if em > es else -1)
    f["ema_stack"] = round(stack * 2 / 3, 2)
    # ۲) شیب میانگین میانی نرمال‌شده با ATR
    j = t - p.slope_lookback
    slope = (em - s.ema_m[j]) / a if s.ema_m[j] == s.ema_m[j] else 0.0
    f["ema_slope"] = round(_clip(slope / 1.5), 2)
    # ۳) ساختار سقف/کف (پیوت‌های تأییدشده)
    highs, lows = ind.confirmed_pivots(s.bars, t, p.pivot_k)
    st = 0.0
    if len(highs) >= 2:
        st += 1 if highs[-1][1] > highs[-2][1] else -1
    if len(lows) >= 2:
        st += 1 if lows[-1][1] > lows[-2][1] else -1
    if lows and c < lows[-1][1]:
        st -= 1          # شکست آخرین کف معتبر
    if highs and c > highs[-1][1]:
        st += 1          # شکست آخرین سقف معتبر
    f["structure"] = round(_clip(st), 2)
    # ۴) شتاب (RSI حول ۵۰)
    f["momentum"] = round(_clip((r - 50) / 12.5), 2)
    # ۵) حجم هم‌جهت با حرکت
    vr = s.vol_ratio(t)
    r5 = s.ret(t, 5)
    vol_f = 0.0
    if vr == vr and r5 == r5:
        vol_f = _clip((vr - 1.0) * 2) * (1 if r5 > 0 else -1) if vr > 1 else 0.0
    f["volume"] = round(_clip(vol_f, -1, 1), 2)
    # ۶) بافت بازار کل (BTC)
    btc_f = {"A": 1.0, "B": 0.5, "C": 0.0, "D": 0.0, "E": -1.0, "F": -1.5, "G": -2.0}.get(btc_state or "", 0.0)
    f["btc"] = btc_f

    score = sum(f.values())
    f["adx"] = round(dx, 1)
    f["rsi"] = round(r, 1)
    f["atr_pct"] = round(a / c * 100, 3)

    strong, weak = dx >= p.adx_strong, dx < p.adx_weak
    if score >= 6.0 and strong and stack == 3:
        return TrendResult("A", score, f, "ALL_FACTORS_BULLISH_STRONG_ADX")
    if score <= -6.0 and strong and stack == -3:
        return TrendResult("F", score, f, "ALL_FACTORS_BEARISH_STRONG_ADX")
    if score >= 3.0 and not weak:
        return TrendResult("B", score, f, "BULLISH_CONFIRMED")
    if score <= -3.0 and not weak:
        return TrendResult("E", score, f, "BEARISH_CONFIRMED")
    if ef > em and c > es and score < 3.0 and (f["momentum"] < 0.5 or f["structure"] <= 0):
        return TrendResult("C", score, f, "UPTREND_LOSING_STRENGTH")
    return TrendResult("D", score, f, "NO_VALID_DIRECTION" if weak else "MIXED_EVIDENCE")
