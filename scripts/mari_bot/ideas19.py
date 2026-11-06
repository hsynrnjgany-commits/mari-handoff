# -*- coding: utf-8 -*-
"""ideas19 — ثبت پیشاپیش در RESEARCH_LOG (2026-11-06T03:40Z). فقط تمرینی، فقط خرید.

H-MARI-L-066: ناهنجاری کم‌نوسانی («Revisiting the low-volatility anomaly in cryptocurrency
              markets»، Finance Research Letters 2026) — تنها مقالهٔ یافته‌شده که روی همین دادهٔ
              ما (جفت‌های USDT بایننس ۲۰۱۸ تا ۲۰۲۵) آزموده شده.
              نسخهٔ ما: فقط خرید پنجکِ کم‌نوسان (پنجک ۱)، بازتوزیع هر ۴ هفته.

اولین فرضیه‌ای که از ابزار دو-رژیمی (regime.py) می‌گذرد: باید جداگانه در بازار صعودی و نزولی
از ≥۹۵٪ سبدهای تصادفیِ هم‌نقد، هم در شارپ و هم در بازده، بهتر باشد.
"""
from __future__ import annotations

import math

from .ideas10 import Panel, universe
from .regime import overall_verdict, run_two_regime

DAY_MS = 86_400_000
VOL_DAYS = 60                  # J = ۲ ماه (مقاله: J=۲ تا ۳ بهترین؛ پیش از اجرا ۲ انتخاب شد)
QUINTILE = 0.2
REBAL_WEEKS = 4                # «ماهانه» به‌صورت قطعی: هر ۴ هفته
HOLD_WEEKS = 4

IDEA19_HYPOTHESES = {
    "H-MARI-L-066": "کم‌نوسانی (فقط خرید پنجک کم‌نوسان بر پایهٔ انحراف معیار بازده لگاریتمی ۶۰ روز، از ۱۰۰ ارز پرحجم، بازتوزیع هر ۴ هفته): در بازار صعودی و نزولی هر دو جداگانه، از ≥۹۵٪ سبدهای تصادفی هم‌نقد هم در شارپ و هم در بازده بهتر.",
}


def log_vol(p: Panel, s: str, t: int, n: int = VOL_DAYS) -> float | None:
    i = p.i(s, t)
    if i is None or i < n:
        return None
    c = p.sym[s]["c"]
    rs = [math.log(c[j] / c[j - 1]) for j in range(i - n + 1, i + 1) if c[j - 1] > 0 and c[j] > 0]
    if len(rs) < n * 0.9:
        return None
    m = sum(rs) / len(rs)
    return (sum((r - m) ** 2 for r in rs) / (len(rs) - 1)) ** 0.5


def is_rebalance_week(t: int) -> bool:
    return (t // (7 * DAY_MS)) % REBAL_WEEKS == 0


def make_selector(which: str = "low"):
    def select(p: Panel, t: int):
        elig = universe(p, t)
        if not is_rebalance_week(t):
            return elig, []
        vols = {s: v for s in elig if (v := log_vol(p, s, t)) is not None}
        ranked = sorted(vols, key=lambda s: vols[s], reverse=(which == "high"))
        n = max(1, int(len(ranked) * QUINTILE))
        return elig, ranked[:n]
    return select


def run_ideas19(daily: dict, start_ms: int, end_ms: int, n_draws: int = 200) -> dict:
    p = Panel(daily)
    low = run_two_regime(p, start_ms, end_ms, make_selector("low"), HOLD_WEEKS, n_draws=n_draws, seed=66)
    high = run_two_regime(p, start_ms, end_ms, make_selector("high"), HOLD_WEEKS, n_draws=n_draws, seed=67)
    return {"H-MARI-L-066": low, "HIGH_VOL_INFO": high,
            "verdict": {"H-MARI-L-066": overall_verdict(low)}}
