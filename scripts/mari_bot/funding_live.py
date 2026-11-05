# -*- coding: utf-8 -*-
"""پیگیری تمرینی زندهٔ کری دلتا-نیوترال فاندینگ (H-MARI-Y-057) روی BTC و ETH.

همان قاعدهٔ آزمون: ورود وقتی میانگین ۷ روزهٔ فاندینگ سالانه‌شده > ۱۰٪، خروج وقتی < ۰٪؛
تصمیم روی روز کامل k، اجرا از روز k+1؛ هزینهٔ هر تغییر وضعیت ۰٫۳٪. درآمد روز = جمع فاندینگ تسویه‌شده.
مثل آزمون، «پوشش کامل» فرض می‌شود؛ پس این هم سقف خوش‌بینانه است، نه سود واقعی.
فقط خواندن دادهٔ عمومی — هیچ موقعیت یا سفارشی وجود ندارد.
"""
from __future__ import annotations

import json
import os

from .data import DataError
from .funding import _FETCHERS, _SYMS, daily_funding
from .ideas13 import COST_PER_SIDE, ENTER_APR, EXIT_APR, LOOKBACK, annualized

DAY_MS = 86_400_000


def fetch_recent(sym: str, now_ms: int, days: int = 20) -> tuple[str, list]:
    """اولین منبعی که فاندینگ تا دیروز را داشته باشد (بایگانی ماهانه معمولاً ماه جاری را ندارد)."""
    start = now_ms - days * DAY_MS
    need_until = now_ms // DAY_MS * DAY_MS - DAY_MS
    tried = {}
    for name, fn in _FETCHERS:
        try:
            rows = sorted(set(fn(_SYMS[name][sym], start, now_ms)))
        except DataError as e:
            tried[name] = str(e)[:80]
            continue
        if rows and rows[-1][0] >= need_until:
            return name, rows
        tried[name] = "داده تا دیروز نرسیده"
    raise DataError(f"فاندینگ تازه برای {sym} در دسترس نیست: {tried}")


class FundingCarry:
    def __init__(self, path: str, start_equity: float = 1000.0):
        self.path = path
        self.s = {"assets": {}}
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    self.s.update(json.load(fh))
            except (OSError, ValueError):
                pass
        self.start_equity = start_equity

    def save(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.s, fh, ensure_ascii=False)
        os.replace(tmp, self.path)

    def update(self, sym: str, rows: list, source: str, now_ms: int) -> list[dict]:
        """rows: [(t, rate)]. فقط روزهای کامل (پیش از امروز UTC) پردازش می‌شوند."""
        a = self.s["assets"].setdefault(sym, {"in_pos": False, "pending": None, "equity": self.start_equity,
                                              "last_day": 0, "funding_earned": 0.0, "switches": 0,
                                              "started_day": None, "sources": {}})
        today = now_ms // DAY_MS * DAY_MS
        days = sorted({t // DAY_MS * DAY_MS for t, _ in rows if t // DAY_MS * DAY_MS < today})
        if not days:
            return []
        daily = daily_funding(rows, days)
        events = []
        if not a["last_day"]:
            a["last_day"] = days[-2] if len(days) > 1 else days[-1] - DAY_MS   # شروع تازه: بدون بازپخش
            a["started_day"] = days[-1]
        for k, d in enumerate(days):
            if d <= a["last_day"]:
                continue
            if a["pending"] is not None and a["pending"] != a["in_pos"]:
                a["equity"] *= 1 - COST_PER_SIDE
                a["in_pos"] = a["pending"]
                a["switches"] += 1
                events.append({"sym": sym, "day": d, "to": "ON" if a["in_pos"] else "OFF",
                               "equity": round(a["equity"], 2)})
            a["pending"] = None
            r = daily[k]
            if a["in_pos"] and r is not None:
                a["equity"] *= 1 + r
                a["funding_earned"] += r
            apr = annualized(daily[max(0, k - LOOKBACK + 1): k + 1])
            a["last_apr"] = round(apr * 100, 2) if apr is not None else None
            if apr is not None:
                if not a["in_pos"] and apr > ENTER_APR:
                    a["pending"] = True
                elif a["in_pos"] and apr < EXIT_APR:
                    a["pending"] = False
            a["sources"][source] = a["sources"].get(source, 0) + 1
            a["peak"] = max(a.get("peak") or a["equity"], a["equity"])
            a["max_dd"] = max(a.get("max_dd") or 0.0, 1 - a["equity"] / a["peak"])
            a["days"] = a.get("days", 0) + 1
            a["last_day"] = d
        self.save()
        return events

    def summary(self) -> dict:
        out = {}
        for sym, a in self.s["assets"].items():
            out[sym] = {"in_position": a["in_pos"], "pending": a["pending"], "equity": round(a["equity"], 2),
                        "return_pct": round((a["equity"] / self.start_equity - 1) * 100, 3),
                        "apr7_pct": a.get("last_apr"), "switches": a["switches"],
                        "sources": a["sources"], "max_dd_pct": round((a.get("max_dd") or 0.0) * 100, 2),
                        "days": a.get("days", 0)}
        return out
