# -*- coding: utf-8 -*-
"""صرافی‌های دوم برای تکرار آزمون‌ها. فقط خواندن دادهٔ عمومی، بدون کلید، فقط پژوهش.

- کوین‌بیس: تاریخچهٔ بلند BTC (از ۲۰۱۵) و ETH (از ۲۰۱۶) — پیش از شروع بایننس.
- بای‌بیت: یک صرافی مستقل دوم برای اینکه ببینیم نتیجه‌ها وابسته به بایننس نیستند.

خروجی هر دو همان قالب کندل روزانهٔ پروژه است: {"t","o","h","l","c","v"}.
"""
from __future__ import annotations

import time

from .data import DataError, http_get_json

DAY_MS = 86_400_000
COINBASE = "https://api.exchange.coinbase.com"
BYBIT = "https://api.bybit.com"
COINBASE_PRODUCTS = {"BTCUSDT": "BTC-USD", "ETHUSDT": "ETH-USD"}


def _iso(ms: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ms / 1000))


def parse_coinbase(rows) -> list[dict]:
    """کوین‌بیس: [[زمان ثانیه، low، high، open، close، volume], ...] از جدید به قدیم."""
    out = []
    for r in rows or []:
        try:
            t = int(r[0]) * 1000
            out.append({"t": t // DAY_MS * DAY_MS, "o": float(r[3]), "h": float(r[2]),
                        "l": float(r[1]), "c": float(r[4]), "v": float(r[5])})
        except (TypeError, ValueError, IndexError):
            continue
    return out


def fetch_coinbase_daily(sym: str, start_ms: int, end_ms: int, pause: float = 0.35) -> list[dict]:
    """صفحه‌بندی با پنجره‌های ۳۰۰ روزه (سقف هر درخواست کوین‌بیس ۳۰۰ کندل است)."""
    prod = COINBASE_PRODUCTS[sym]
    path = f"/products/{prod}/candles"
    got, cur = {}, start_ms
    while cur < end_ms:
        nxt = min(end_ms, cur + 299 * DAY_MS)
        rows = http_get_json(path, {"granularity": 86400, "start": _iso(cur), "end": _iso(nxt)},
                             base=COINBASE, timeout=30, retries=4)
        for b in parse_coinbase(rows):
            if start_ms <= b["t"] < end_ms:
                got[b["t"]] = b
        cur = nxt + DAY_MS
        time.sleep(pause)
    return [got[t] for t in sorted(got)]


def parse_bybit(js) -> list[dict]:
    """بای‌بیت v5: result.list = [[startMs، open، high، low، close، volume، turnover], ...] از جدید به قدیم."""
    out = []
    lst = (((js or {}).get("result") or {}).get("list")) or []
    for r in lst:
        try:
            t = int(r[0])
            out.append({"t": t // DAY_MS * DAY_MS, "o": float(r[1]), "h": float(r[2]),
                        "l": float(r[3]), "c": float(r[4]), "v": float(r[5])})
        except (TypeError, ValueError, IndexError):
            continue
    return out


def fetch_bybit_daily(sym: str, start_ms: int, end_ms: int, category: str = "spot",
                      pause: float = 0.2) -> list[dict]:
    got, cur = {}, start_ms
    while cur < end_ms:
        js = http_get_json("/v5/market/kline", {"category": category, "symbol": sym, "interval": "D",
                                                "start": cur, "end": min(end_ms, cur + 999 * DAY_MS),
                                                "limit": 1000}, base=BYBIT, timeout=30, retries=4)
        if (js or {}).get("retCode") not in (0, None):
            raise DataError(f"bybit retCode {js.get('retCode')}: {js.get('retMsg')}")
        bars = parse_bybit(js)
        if not bars:
            cur += 1000 * DAY_MS
            continue
        for b in bars:
            if start_ms <= b["t"] < end_ms:
                got[b["t"]] = b
        cur = max(b["t"] for b in bars) + DAY_MS
        time.sleep(pause)
    return [got[t] for t in sorted(got)]


def compare_closes(a: list[dict], b: list[dict]) -> dict:
    """تفاوت بستهٔ روزانهٔ دو صرافی روی روزهای مشترک — برای اطمینان از سلامت داده."""
    mb = {x["t"]: x["c"] for x in b}
    diffs = sorted(abs(x["c"] / mb[x["t"]] - 1) for x in a if x["t"] in mb and mb[x["t"]] > 0)
    if not diffs:
        return {"common_days": 0}
    return {"common_days": len(diffs), "median_abs_diff_pct": round(diffs[len(diffs) // 2] * 100, 4),
            "p99_abs_diff_pct": round(diffs[int(.99 * (len(diffs) - 1))] * 100, 4),
            "max_abs_diff_pct": round(diffs[-1] * 100, 4)}
