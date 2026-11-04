# -*- coding: utf-8 -*-
"""استراتژی تمرینی زندهٔ T-006: فقط بیت‌کوین، بالای میانگین ۱۵۰روزه نگه‌دار، وگرنه نقد.

تنها فرضیه‌ای که تا کنون آزمون ثبت‌شدهٔ ماری را گذرانده (RESEARCH_LOG.md). اینجا روی دادهٔ واقعیِ
از-امروز-به‌بعد، روی کاغذ دنبال می‌شود تا شاهد مستقل سوم (پس از آزمون تاریخی و آزمون استحکام) جمع شود.
فقط تمرینی — هیچ سفارش واقعی‌ای وجود ندارد.
"""
from __future__ import annotations

import json
import os

DAY_MS = 86_400_000
SMA_N = 150
FEE = 0.001
SLIP = 0.0005


def _sma(xs, n):
    return sum(xs[-n:]) / n if len(xs) >= n else None


class BtcTrend:
    def __init__(self, path: str, start_equity: float = 1000.0):
        self.path = path
        self.s = {"position": None, "cash": start_equity, "units": 0.0, "start_equity": start_equity,
                  "last_day_ts": 0, "switches": [], "last_close": None, "last_sma": None,
                  "first_price": None}
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

    def equity(self, px: float | None = None) -> float:
        px = px or self.s["last_close"] or 0.0
        return self.s["cash"] + self.s["units"] * px

    def update(self, daily: list[dict]) -> list[dict]:
        """کندل‌های روزانهٔ بستهٔ BTC (قدیمی→جدید). خروجی: رویدادهای تغییر وضعیت."""
        events = []
        closes = [b["c"] for b in daily]
        if self.s["position"] is None and len(daily) > 1 and not self.s["last_day_ts"]:
            # شروع تازه: گذشته بازپخش نمی‌شود — فقط از آخرین کندل بستهٔ روزانه
            self.s["last_day_ts"] = daily[-2]["t"]
        for k, b in enumerate(daily):
            if b["t"] <= self.s["last_day_ts"]:
                continue
            hist = closes[: k + 1]
            sma = _sma(hist, SMA_N)
            if sma is None:
                continue
            c = b["c"]
            want = "BTC" if c > sma else "CASH"
            boot = self.s["position"] is None
            if self.s["first_price"] is None:
                self.s["first_price"] = c
            if want != self.s["position"]:
                if want == "BTC" and self.s["cash"] > 0:
                    px = c * (1 + SLIP)
                    self.s["units"] = self.s["cash"] * (1 - FEE) / px
                    self.s["cash"] = 0.0
                elif want == "CASH" and self.s["units"] > 0:
                    px = c * (1 - SLIP)
                    self.s["cash"] = self.s["units"] * px * (1 - FEE)
                    self.s["units"] = 0.0
                ev = {"t": b["t"], "to": want, "close": c, "sma": round(sma, 2), "boot": boot,
                      "equity": round(self.equity(c), 2)}
                self.s["switches"].append(ev)
                self.s["switches"] = self.s["switches"][-200:]
                events.append(ev)
                self.s["position"] = want
            self.s["last_day_ts"] = b["t"]
            self.s["last_close"], self.s["last_sma"] = c, round(sma, 2)
        self.save()
        return events

    def summary(self) -> dict:
        eq = self.equity()
        fp, lc = self.s["first_price"], self.s["last_close"]
        return {"position": self.s["position"], "equity": round(eq, 2),
                "return_pct": round((eq / self.s["start_equity"] - 1) * 100, 2),
                "btc_hold_return_pct": round((lc / fp - 1) * 100, 2) if fp and lc else None,
                "close": lc, "sma150": self.s["last_sma"], "switches": len(self.s["switches"])}
