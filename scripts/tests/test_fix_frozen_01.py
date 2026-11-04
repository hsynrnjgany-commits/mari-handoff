#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FIX-FROZEN-01 — تست frozen_keys اصلاح‌شده (فقط‌خواندنی؛ هیچ فایل داده‌ای دست نمی‌خورد).
(الف) ۱ مشاهده → آزاد · (ب) ۳ مشاهدهٔ یکسان پشت‌سرهم → frozen · (ج) ۳ مشاهده با کوت متفاوت → آزاد
اجرای رییس: python3 tests/test_fix_frozen_01.py — خروجی PASS/FAIL هر حالت."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts", "mari_hunt01"))
from hunt_sweep import frozen_keys  # noqa: E402

KEY = ("ONE", "mexc", "kucoin")


def cyc(ts, base, ask, bid, bex="mexc", sex="kucoin"):
    return {"cycle_ts": ts,
            "top20": [{"base": base, "buy_ex": bex, "sell_ex": sex, "ask": ask, "bid": bid}]}


cases = []
# (الف) ۱ مشاهده → آزاد (حتی با تاریخچهٔ بلندِ کلیدهای دیگر؛ کلیدهای دیگر هرکدام یک بار با کوت متفاوت)
hist_a = [cyc(f"2026-11-01T0{i}:00:00Z", f"S{i}", 1.0 + i, 1.01 + i) for i in range(6)]
hist_a.append(cyc("2026-11-01T09:00:00Z", "ONE", 2.0, 2.01))
cases.append(("الف: ۱ مشاهده → آزاد", hist_a, KEY, False))
# (ب) ۳ مشاهدهٔ یکسان پشت‌سرهم → frozen
hist_b = [cyc(f"2026-11-02T0{i}:00:00Z", "ONE", 2.0, 2.01) for i in range(3)]
cases.append(("ب: ۳ مشاهدهٔ یکسان پشت‌سرهم → frozen", hist_b, KEY, True))
# (ج) ۳ مشاهده با کوت متفاوت → آزاد
hist_c = [cyc("2026-11-03T01:00:00Z", "ONE", 2.0, 2.01),
          cyc("2026-11-03T02:00:00Z", "ONE", 2.05, 2.06),
          cyc("2026-11-03T03:00:00Z", "ONE", 2.10, 2.11)]
cases.append(("ج: ۳ مشاهده با کوت متفاوت → آزاد", hist_c, KEY, False))

fails = 0
for name, cycles, key, expect in cases:
    got = key in frozen_keys(cycles)
    ok = (got == expect)
    fails += 0 if ok else 1
    print(f"{'PASS' if ok else 'FAIL'} — {name} (frozen={got})")
print(f"نتیجه: {len(cases) - fails}/{len(cases)} PASS")
sys.exit(1 if fails else 0)
