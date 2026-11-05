# -*- coding: utf-8 -*-
"""«صندوق پس‌انداز هوشمند» تمرینی — همان D-010 (خرید پله‌ای هفتگی + فیلتر روند ۱۵۰روزه)، از امروز به بعد.

هر دوشنبه (کندل روزانهٔ بستهٔ UTC) مبلغ ثابت فرضی کنار گذاشته می‌شود.
اگر BTC بالای میانگین ۱۵۰روزه باشد: همهٔ نقد (این هفته و هفته‌های قبل) با قیمت بسته به BTC تبدیل می‌شود.
اگر زیر باشد: پول نقد می‌ماند و BTC موجود هم نقد می‌شود (همان قانون آزمون).
کارمزد ۰٫۱٪ + لغزش ۰٫۰۵٪. فقط تمرینی — هیچ پولی جابه‌جا نمی‌شود.
"""
from __future__ import annotations

import json
import os

DAY_MS = 86_400_000
SMA_N = 150
FEE, SLIP = 0.001, 0.0005


def weekly_amount() -> float:
    try:
        v = float(os.environ.get("MARI_SAVINGS_WEEKLY_USD", "5"))
        return v if 0 < v <= 10_000 else 5.0
    except ValueError:
        return 5.0


class SavingsPlan:
    def __init__(self, path: str, weekly_usd: float | None = None):
        self.path = path
        self.weekly = weekly_usd if weekly_usd is not None else weekly_amount()
        self.s = {"invested": 0.0, "cash": 0.0, "units": 0.0, "weeks": 0, "last_day_ts": 0,
                  "last_close": None, "position": None, "started_day": None, "peak": 0.0, "max_dd": 0.0}
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    self.s.update(json.load(fh))
            except (OSError, ValueError):
                pass

    def save(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.s, fh, ensure_ascii=False)
        os.replace(tmp, self.path)

    def value(self, px: float | None = None) -> float:
        px = px or self.s["last_close"] or 0.0
        return self.s["cash"] + self.s["units"] * px

    def update(self, daily: list[dict]) -> list[dict]:
        """کندل‌های روزانهٔ بستهٔ BTC. خروجی: رویدادهای هفتگی (برای پیام دوشنبه)."""
        events = []
        closes = [b["c"] for b in daily]
        if not self.s["last_day_ts"] and len(daily) > 1:
            self.s["last_day_ts"] = daily[-2]["t"]              # شروع از امروز، بدون بازپخش گذشته
            self.s["started_day"] = daily[-1]["t"]
        for k, b in enumerate(daily):
            if b["t"] <= self.s["last_day_ts"] or k < SMA_N - 1:
                continue
            c = b["c"]
            above = c > sum(closes[k - SMA_N + 1: k + 1]) / SMA_N
            monday = ((b["t"] // DAY_MS) + 3) % 7 == 0
            if monday:
                self.s["invested"] += self.weekly
                self.s["cash"] += self.weekly
                self.s["weeks"] += 1
            if above and self.s["cash"] > 0:
                self.s["units"] += self.s["cash"] * (1 - FEE) / (c * (1 + SLIP))
                self.s["cash"] = 0.0
            elif not above and self.s["units"] > 0:
                self.s["cash"] += self.s["units"] * c * (1 - SLIP) * (1 - FEE)
                self.s["units"] = 0.0
            self.s["position"] = "BTC" if above else "CASH"
            self.s["last_close"] = c
            v = self.value(c)
            self.s["peak"] = max(self.s["peak"], v)
            if self.s["peak"] > 0:
                self.s["max_dd"] = max(self.s["max_dd"], 1 - v / self.s["peak"])
            if monday:
                events.append({"t": b["t"], **self.summary()})
            self.s["last_day_ts"] = b["t"]
        self.save()
        return events

    def summary(self) -> dict:
        v, inv = self.value(), self.s["invested"]
        return {"weekly_usd": self.weekly, "weeks": self.s["weeks"], "invested": round(inv, 2),
                "value": round(v, 2), "gain_pct": round((v / inv - 1) * 100, 2) if inv else None,
                "position": self.s["position"], "max_dd_pct": round(self.s["max_dd"] * 100, 2)}
