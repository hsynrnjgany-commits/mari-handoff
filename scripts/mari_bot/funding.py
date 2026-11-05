# -*- coding: utf-8 -*-
"""آزمون نرخ فاندینگ قراردادهای دائمی — ثبت پیشاپیش در RESEARCH_LOG (2026-11-05T04:20Z).

فاندینگ روزانه = جمع نرخ‌های تسویه‌شده در روز UTC [t, t+1d).
F7 = میانگین فاندینگ روزانهٔ ۷ روز آخر (تا خود روز t).
صدک = سهم روزهای ۱۸۰ روز قبل (بدون خود t) که F7شان کمتر از F7 امروز است.
شلوغی خرید: صدک > ۹۰ ؛ شلوغی فروش: صدک < ۱۰.

H-MARI-F-017: پس از شلوغی خرید بازده ۵روزه کمتر از معمول، پس از شلوغی فروش بیشتر (BTC و ETH، CI95).
H-MARI-F-018: T-006 (BTC بالای SMA150) و نبودِ شلوغی خرید؛ باید شارپ T-006 را بزند و افتش بدتر نباشد.
فقط تمرینی — فقط خواندن دادهٔ عمومی.
"""
from __future__ import annotations

import time

from .data import DataError, http_get_json

DAY_MS = 86_400_000
WINDOW, F_LEN, HI, LO = 180, 7, 90.0, 10.0

FUNDING_HYPOTHESES = {
    "H-MARI-F-017": "پس از شلوغی خرید (F7 در صدک >۹۰)، بازده ۵روزه کمتر از معمول؛ پس از شلوغی فروش (<۱۰) بیشتر (BTC و ETH).",
    "H-MARI-F-018": "BTC بالای SMA150 و نبودِ شلوغی خرید؛ وگرنه نقد. باید شارپ T-006 را بزند و افتش بدتر نباشد.",
}

BINANCE_FAPI = "https://fapi.binance.com"
BYBIT = "https://api.bybit.com"
BITMEX = "https://www.bitmex.com"
# نماد هر منبع برای BTC و ETH
_SYMS = {
    "binance": {"BTCUSDT": "BTCUSDT", "ETHUSDT": "ETHUSDT"},
    "bybit": {"BTCUSDT": "BTCUSDT", "ETHUSDT": "ETHUSDT"},
    "bitmex": {"BTCUSDT": "XBTUSD", "ETHUSDT": "ETHUSD"},
}


def _binance(sym, start_ms, end_ms):
    out, cur = [], start_ms
    while cur < end_ms:
        rows = http_get_json("/fapi/v1/fundingRate", {"symbol": sym, "startTime": cur, "limit": 1000},
                             base=BINANCE_FAPI, retries=3, timeout=30)
        if not rows:
            break
        out += [(int(r["fundingTime"]), float(r["fundingRate"])) for r in rows]
        nxt = int(rows[-1]["fundingTime"]) + 1
        if nxt <= cur or len(rows) < 1000:
            break
        cur = nxt
        time.sleep(0.2)
    return out


def _bybit(sym, start_ms, end_ms):
    out, end = [], end_ms
    while end > start_ms:                   # بای‌بیت از آخر به اول صفحه می‌دهد
        r = http_get_json("/v5/market/funding/history", {"category": "linear", "symbol": sym,
                          "startTime": start_ms, "endTime": end, "limit": 200}, base=BYBIT, retries=3, timeout=30)
        rows = (r.get("result") or {}).get("list") or []
        if not rows:
            break
        out += [(int(x["fundingRateTimestamp"]), float(x["fundingRate"])) for x in rows]
        oldest = min(int(x["fundingRateTimestamp"]) for x in rows)
        if oldest >= end or len(rows) < 200:
            break
        end = oldest - 1
        time.sleep(0.2)
    return out


def _bitmex(sym, start_ms, end_ms):
    from datetime import datetime, timezone
    out, start = [], 0
    iso = datetime.fromtimestamp(start_ms / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    while True:
        rows = http_get_json("/api/v1/funding", {"symbol": sym, "startTime": iso, "count": 500, "start": start},
                             base=BITMEX, retries=3, timeout=30)
        if not rows:
            break
        for x in rows:
            t = int(datetime.strptime(x["timestamp"][:19], "%Y-%m-%dT%H:%M:%S")
                    .replace(tzinfo=timezone.utc).timestamp() * 1000)
            if t < end_ms:
                out.append((t, float(x["fundingRate"])))
        if len(rows) < 500:
            break
        start += 500
        time.sleep(1.1)                     # بیت‌مکس: محدودیت نرخ سخت‌گیرانه
    return out


def _archive(sym, start_ms, end_ms):
    """بایگانی ماهانهٔ بایننس: CSV داخل zip با ستون‌های calc_time, funding_interval_hours, last_funding_rate."""
    import csv
    import io
    import zipfile
    from datetime import datetime, timezone
    from .data import _ARCHIVE_PREFIX, http_get_bytes
    out = []
    d = datetime.fromtimestamp(start_ms / 1000, timezone.utc).replace(day=1)
    last = datetime.fromtimestamp(end_ms / 1000, timezone.utc)
    while d <= last:
        name = f"{sym}-fundingRate-{d:%Y-%m}"
        blob = http_get_bytes(f"{_ARCHIVE_PREFIX}{sym}/{name}.zip")
        if blob:
            with zipfile.ZipFile(io.BytesIO(blob)) as z:
                text = z.read(z.namelist()[0]).decode("utf-8", "replace")
            for row in csv.reader(io.StringIO(text)):
                if row and row[0].isdigit():
                    t = int(row[0])
                    if start_ms <= t < end_ms:
                        out.append((t, float(row[-1])))
        d = d.replace(year=d.year + (d.month == 12), month=d.month % 12 + 1)
        time.sleep(0.1)
    return out


_SYMS["binance_archive"] = {"BTCUSDT": "BTCUSDT", "ETHUSDT": "ETHUSDT"}
_FETCHERS = (("binance", _binance), ("binance_archive", _archive), ("bybit", _bybit), ("bitmex", _bitmex))


def fetch_funding(sym: str, start_ms: int, end_ms: int, need_from_ms: int) -> tuple[str, list, dict]:
    """اولین منبعی که دادهٔ کافی (از need_from_ms) بدهد. خروجی: (نام منبع، [(t, rate)], تلاش‌ها)."""
    tried = {}
    for name, fn in _FETCHERS:
        try:
            rows = sorted(set(fn(_SYMS[name][sym], start_ms, end_ms)))
        except DataError as e:
            tried[name] = str(e)
            continue
        if rows and rows[0][0] <= need_from_ms:
            return name, rows, tried
        tried[name] = f"داده ناکافی: {len(rows)} ردیف، از {rows[0][0] if rows else None}"
    raise DataError(f"هیچ منبع فاندینگی برای {sym} کار نکرد: {tried}")


def daily_funding(rows: list, days: list[int]) -> list:
    """جمع نرخ‌های تسویه‌شده در هر روز UTC؛ روز بدون تسویه = None."""
    acc = {}
    for t, r in rows:
        d = t // DAY_MS * DAY_MS
        acc[d] = acc.get(d, 0.0) + r
    return [acc.get(d) for d in days]


def crowding(daily_f: list) -> list:
    """صدک F7 هر روز در برابر ۱۸۰ روز قبل. None تا وقتی داده کافی نیست."""
    f7 = [None] * len(daily_f)
    for k in range(F_LEN - 1, len(daily_f)):
        w = daily_f[k - F_LEN + 1: k + 1]
        if all(x is not None for x in w):
            f7[k] = sum(w) / F_LEN
    pct = [None] * len(daily_f)
    for k in range(WINDOW, len(daily_f)):
        hist = [x for x in f7[k - WINDOW: k] if x is not None]
        if f7[k] is not None and len(hist) >= WINDOW * 0.9:
            pct[k] = sum(1 for x in hist if x < f7[k]) / len(hist) * 100
    return pct


def event_study_f(bars: list[dict], pct: list, start_idx: int) -> dict:
    from .ict import _diff_ci, _fwd
    base = [r for t in range(start_idx, len(bars)) if (r := _fwd(bars, t)) is not None]
    out = {"n_days": len(base), "mean_fwd5_all_pct": round(sum(base) / len(base) * 100, 3) if base else None}
    groups = {"crowded_long": lambda p: p > HI, "crowded_short": lambda p: p < LO}
    for k, cond in groups.items():
        s = [r for t in range(start_idx, len(bars))
             if pct[t] is not None and cond(pct[t]) and (r := _fwd(bars, t)) is not None]
        out[k] = {"n": len(s), "mean_fwd5_pct": round(sum(s) / len(s) * 100, 3) if s else None,
                  "vs_all": _diff_ci(s, base)}
    return out


def f018_fn(pct_by_day: dict):
    from .macro import btc_above_sma

    def fn(k, ctx):
        st = ctx["state"]
        if k < 149:
            return None
        p = pct_by_day.get(ctx["days"][k])
        ok = btc_above_sma(150)(k, ctx) and not (p is not None and p > HI)
        if ok != st.get("in"):
            st["in"] = ok
            return {"BTCUSDT": 1.0} if ok else {}
        return None
    return fn


def run_funding(daily: dict, funding: dict, start_ms: int, end_ms: int) -> dict:
    """daily: کندل روزانهٔ اسپات؛ funding: {sym: [(t, rate)]}."""
    from .classics import hold_btc, run_weights
    from .macro import t006_fn
    out = {"events": {}, "coverage": {}}
    ok017 = True
    pct_btc = {}
    for sym in ("BTCUSDT", "ETHUSDT"):
        bars = [b for b in daily[sym] if b["t"] <= end_ms]
        days = [b["t"] for b in bars]
        df = daily_funding(funding[sym], days)
        pct = crowding(df)
        si = next(i for i, b in enumerate(bars) if b["t"] >= start_ms)
        es = event_study_f(bars, pct, si)
        out["events"][sym] = es
        out["coverage"][sym] = {"days_with_funding_pct": round(sum(1 for x in df[si:] if x is not None)
                                                               / max(1, len(df) - si) * 100, 1),
                                "days_crowded_long": sum(1 for p in pct[si:] if p is not None and p > HI),
                                "days_crowded_short": sum(1 for p in pct[si:] if p is not None and p < LO)}
        lo, sh = es["crowded_long"]["vs_all"], es["crowded_short"]["vs_all"]
        ok017 = ok017 and bool(lo and sh and lo["ci95_high"] < 0 and sh["ci95_low"] > 0)
        if sym == "BTCUSDT":
            pct_btc = dict(zip(days, pct))
    base, _, _ = run_weights(daily, ["BTCUSDT"], start_ms, end_ms, hold_btc)
    t6, _, _ = run_weights(daily, ["BTCUSDT"], start_ms, end_ms, t006_fn)
    st, _, _ = run_weights(daily, ["BTCUSDT"], start_ms, end_ms, f018_fn(pct_btc))
    ci = st.get("weekly_bootstrap") or {}
    ok018 = bool((st.get("sharpe") or -9) > (t6.get("sharpe") or 9)
                 and st.get("max_drawdown_pct", 100) <= t6.get("max_drawdown_pct", 0) and ci and ci["ci95_low"] > 0)
    out["strategy"] = {"BTC_BUY_HOLD": base, "T-006_REFERENCE": t6, "H-MARI-F-018": st}
    out["verdict"] = {"H-MARI-F-017": "SUPPORTED_IN_TEST_RANGE" if ok017 else "FALSIFIED",
                      "H-MARI-F-018": "SUPPORTED_IN_TEST_RANGE" if ok018 else "FALSIFIED"}
    return out
