# -*- coding: utf-8 -*-
"""ideas17 — ثبت پیشاپیش در RESEARCH_LOG (2026-11-05T21:30Z). فقط تمرینی.

آزمون سوم و سخت‌گیر ایدهٔ صاحب پروژه، با **جابه‌جایی زمان**:
قاعده از دادهٔ **تازه** (۲۰۲۱-۰۶ تا امروز) یاد گرفته می‌شود و روی دادهٔ **قدیم**
(۲۰۱۸-۰۱ تا ۲۰۲۱-۰۶) آزموده می‌شود — دوره‌ای که هرگز برای این ایده استفاده نشده.

H-MARI-Z-063: سبد قاعده از **≥۹۵٪** قرعه‌های محک هم‌نقد، هم در شارپ و هم در بازده، بهتر باشد.
H-MARI-Z-064: نرخ برنده‌شدن بالاتر از نرخ پایه با CI95 بالای صفر، به‌شرط توان کافی.
"""
from __future__ import annotations

from .ideas10 import Panel
from .ideas14 import collect
from .ideas16 import block_ci, cash_matched, power_check, wide_rule

DAY_MS = 86_400_000
BEAT_FRAC = 95.0               # شرط سخت‌گیر: بهتر از ۹۵٪ قرعه‌ها

IDEA17_HYPOTHESES = {
    "H-MARI-Z-063": "قاعدهٔ «نزدیک سقف خودش + کم‌حجم» که از دادهٔ ۲۰۲۱-۰۶ به بعد یاد گرفته شد، روی دورهٔ دست‌نخوردهٔ ۲۰۱۸-۰۱ تا ۲۰۲۱-۰۶: سبد از ≥۹۵٪ قرعه‌های محک هم‌نقد، هم در شارپ و هم در بازده، بهتر باشد.",
    "H-MARI-Z-064": "در همان دوره: نرخ برنده‌شدن سیگنال‌ها بالاتر از نرخ پایه با CI95 بالای صفر؛ اگر برندهٔ مورد انتظار زیر ۱۰ باشد، حکم «آزمون‌ناپذیر» است.",
}


def run_ideas17(daily: dict, learn_start: int, learn_end: int,
                test_start: int, test_end: int) -> dict:
    p = Panel(daily)
    learn = collect(p, learn_start, learn_end)
    rule = wide_rule(learn)
    test = collect(p, test_start, test_end)
    pw = power_check(test, rule)
    ci = block_ci(test, rule, seed=63)
    cm = cash_matched(p, rule, test_start, test_end, seed=64)
    beat_s = cm.get("pct_random_draws_beaten_sharpe")
    beat_r = cm.get("pct_random_draws_beaten_return")
    z63 = "FALSIFIED"
    if beat_s is not None and beat_r is not None and beat_s >= BEAT_FRAC and beat_r >= BEAT_FRAC:
        z63 = "SUPPORTED_IN_TEST_RANGE"
    if not pw["testable"]:
        z64 = "UNTESTABLE_LOW_POWER"
    elif ci and ci["ci95_low"] > 0:
        z64 = "SUPPORTED_IN_TEST_RANGE"
    else:
        z64 = "FALSIFIED"
    return {"rule": rule, "learn_power_info": power_check(learn, rule), "power": pw,
            "test": ci, "cash_matched": cm, "n_test_events": len(test),
            "beat_threshold_pct": BEAT_FRAC,
            "verdict": {"H-MARI-Z-063": z63, "H-MARI-Z-064": z64}}
