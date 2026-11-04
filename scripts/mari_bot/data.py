# -*- coding: utf-8 -*-
"""دریافت و کنترل کیفیت داده (بخش ۳۴ سند مادر).

فقط درخواست‌های عمومی GET به نشانی‌های quote/* تووبیت — هیچ کلید، امضا یا نشانی ثبت سفارش در این فایل نیست.
قالب استاندارد کندل: {"t": ms, "o", "h", "l", "c", "v", "qv"}
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

TOOBIT = "https://api.toobit.com"
BINANCE_VISION = "https://data-api.binance.vision"   # منبع جایگزین عمومی (سند مادر ۳۳.۵)
HOUR_MS = 3_600_000
UA = {"User-Agent": "mari-paper-bot/1.0 (read-only)"}
# فقط این نشانی‌های عمومی و فقط-خواندنی مجازند؛ هر چیز دیگری رد می‌شود.
_ALLOWED = {
    TOOBIT: ("/quote/v1/klines", "/quote/v1/ticker/24hr", "/api/v1/exchangeInfo"),
    BINANCE_VISION: ("/api/v3/klines", "/api/v3/ticker/24hr", "/api/v3/exchangeInfo"),
}


class DataError(RuntimeError):
    pass


def _ctx():
    ca = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
    return ssl.create_default_context(cafile=ca) if ca and os.path.exists(ca) else ssl.create_default_context()


def http_get_json(path: str, params: dict | None = None, timeout: float = 15.0, retries: int = 3,
                  base: str = TOOBIT):
    """GET فقط-خواندنی با بازگشت نمایی. مسیرهای غیرمجاز رد می‌شوند (حفاظ قفل PAPER ONLY)."""
    if path not in _ALLOWED.get(base, ()):
        raise DataError(f"مسیر غیرمجاز: {base}{path}")
    url = base + path + ("?" + urllib.parse.urlencode(params) if params else "")
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA, method="GET")
            with urllib.request.urlopen(req, timeout=timeout, context=_ctx()) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            last = f"HTTP_{e.code}"
            if e.code in (418, 429):          # محدودیت نرخ: صبر طولانی‌تر
                time.sleep(10 * (i + 1))
                continue
            if 400 <= e.code < 500:
                break
        except Exception as e:  # noqa: BLE001 — شبکه
            last = type(e).__name__
        time.sleep(2 ** i)
    raise DataError(f"دریافت ناموفق {path} ({last})")


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return float("nan")


def parse_toobit_klines(rows) -> list[dict]:
    """خروجی تووبیت: [[openTime, o, h, l, c, v, closeTime, qv, trades, ...], ...] (اعداد رشته‌ای)."""
    out = []
    for r in rows or []:
        if isinstance(r, dict):
            out.append({"t": int(r.get("t") or r.get("openTime")), "o": _f(r.get("o")), "h": _f(r.get("h")),
                        "l": _f(r.get("l")), "c": _f(r.get("c")), "v": _f(r.get("v")),
                        "qv": _f(r.get("qv", r.get("quoteVolume")))})
        elif isinstance(r, (list, tuple)) and len(r) >= 6:
            qv = _f(r[7]) if len(r) > 7 else _f(r[5]) * _f(r[4])
            out.append({"t": int(r[0]), "o": _f(r[1]), "h": _f(r[2]), "l": _f(r[3]), "c": _f(r[4]),
                        "v": _f(r[5]), "qv": qv})
    return out


def fetch_klines(symbol: str, interval: str = "1h", limit: int = 500) -> list[dict]:
    rows = http_get_json("/quote/v1/klines", {"symbol": symbol, "interval": interval, "limit": limit})
    return parse_toobit_klines(rows)


def fetch_klines_binance(symbol: str, interval: str = "1h", limit: int = 500) -> list[dict]:
    rows = http_get_json("/api/v3/klines", {"symbol": symbol, "interval": interval, "limit": min(limit, 1000)},
                         base=BINANCE_VISION, retries=2)
    return parse_toobit_klines(rows)   # قالب ردیف‌ها یکسان است


class SourcePicker:
    """منبع اول تووبیت؛ اگر در دسترس نبود، Binance Vision. منبع هر نماد ثبت می‌شود (ردیابی منشأ)."""

    def __init__(self):
        self.toobit_down = False
        self.used: dict[str, str] = {}

    def klines(self, symbol: str, interval: str = "1h", limit: int = 500) -> list[dict]:
        if not self.toobit_down:
            try:
                bars = fetch_klines(symbol, interval, limit)
                if bars:
                    self.used[symbol] = "toobit"
                    return bars
            except DataError as e:
                if "HTTP_4" not in str(e):        # خطای شبکه/مسدودی: کل چرخه به منبع جایگزین برود
                    self.toobit_down = True
        bars = fetch_klines_binance(symbol, interval, limit)
        self.used[symbol] = "binance_vision"
        return bars

    def counts(self) -> dict:
        c = {}
        for v in self.used.values():
            c[v] = c.get(v, 0) + 1
        return c


def _usdt_trading(d) -> list[str]:
    return sorted({s["symbol"] for s in (d or {}).get("symbols", [])
                   if s.get("quoteAsset") == "USDT" and str(s.get("status", "")).upper() == "TRADING"})


def fetch_universe() -> list[str]:
    try:
        return _usdt_trading(http_get_json("/api/v1/exchangeInfo", timeout=30))
    except DataError:
        return _usdt_trading(http_get_json("/api/v3/exchangeInfo", timeout=30, base=BINANCE_VISION))


def _qv_map(d) -> dict[str, float]:
    out = {}
    for r in d if isinstance(d, list) else []:
        s = r.get("s") or r.get("symbol")
        if s:
            out[s] = _f(r.get("qv") or r.get("quoteVolume"))
    return out


def _change_map(d) -> dict[str, float]:
    """تغییر ۲۴ساعته (٪) — قالب تووبیت (o/c) یا بایننس (priceChangePercent/openPrice/lastPrice)."""
    out = {}
    for r in d if isinstance(d, list) else []:
        s = r.get("s") or r.get("symbol")
        if not s:
            continue
        pcp = r.get("priceChangePercent") or r.get("pcp")
        o = _f(r.get("o") or r.get("openPrice"))
        c = _f(r.get("c") or r.get("lastPrice"))
        if pcp not in (None, ""):
            v = _f(pcp)
            if abs(v) < 1 and o == o and c == c and o > 0 and abs(c / o - 1) > 0.01 and abs(v - (c / o - 1)) < 1e-6:
                v *= 100          # بعضی صرافی‌ها کسر می‌دهند نه درصد
            out[s] = v
        elif o == o and c == c and o > 0:
            out[s] = (c / o - 1) * 100
    return out


LAST_TICKER: dict = {"changes": {}, "source": None}


def fetch_quote_volumes() -> dict[str, float]:
    try:
        d = http_get_json("/quote/v1/ticker/24hr", timeout=30)
        LAST_TICKER.update(changes=_change_map(d), source="toobit")
    except DataError:
        d = http_get_json("/api/v3/ticker/24hr", timeout=30, base=BINANCE_VISION)
        LAST_TICKER.update(changes=_change_map(d), source="binance_vision")
    return _qv_map(d)


def drop_unclosed(bars: list[dict], now_ms: int | None = None, interval_ms: int = HOUR_MS) -> list[dict]:
    """کندلی که هنوز بسته نشده حذف می‌شود — تصمیم فقط روی کندل بسته (ضد نگاه به آینده)."""
    now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    return [b for b in bars if b["t"] + interval_ms <= now_ms]


def load_local_dir(path: str) -> dict[str, list[dict]]:
    """بارگذاری دادهٔ آفلاین: پوشه‌ای از فایل‌های SYMBOL_1h_*.json (مثل scripts/mari_megatrend/data)."""
    out = {}
    for fp in sorted(glob.glob(os.path.join(path, "*.json"))):
        sym = os.path.basename(fp).split("_")[0]
        with open(fp, encoding="utf-8") as fh:
            d = json.load(fh)
        bars = d if isinstance(d, list) else d.get("bars") or d.get("klines") or []
        out[sym] = parse_toobit_klines(bars)
    return out


def bars_sha(bars: list[dict]) -> str:
    """هش رمزنگاری دادهٔ ورودی برای ردیابی (بخش ۳۴.۳)."""
    blob = json.dumps([[b["t"], b["o"], b["h"], b["l"], b["c"], b["v"]] for b in bars],
                      separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


def quality_check(bars: list[dict], interval_ms: int = HOUR_MS, max_gap_frac: float = 0.02) -> dict:
    """کنترل کیفیت بخش ۳۴.۴: تکراری، ترتیب، شکاف، مقدار نامعتبر، کندل ناممکن.

    خروجی: {"ok": bool, "issues": [...], "n": ..., "dupes": ..., "gaps": ..., "bad": ..., "clean": [...]}
    کندل‌های تکراری و نامعتبر از نسخهٔ «clean» حذف می‌شوند؛ دادهٔ خام دست نمی‌خورد.
    """
    issues = []
    seen, clean, dupes, bad, unordered = set(), [], 0, 0, 0
    prev_t = None
    for b in bars:
        if b["t"] in seen:
            dupes += 1
            continue
        vals = (b["o"], b["h"], b["l"], b["c"])
        if any(v != v or v <= 0 for v in vals) or b["v"] != b["v"] or b["v"] < 0:
            bad += 1
            continue
        if b["h"] < max(b["o"], b["c"]) or b["l"] > min(b["o"], b["c"]) or b["h"] < b["l"]:
            bad += 1
            continue
        if prev_t is not None and b["t"] < prev_t:
            unordered += 1
        seen.add(b["t"])
        prev_t = b["t"]
        clean.append(b)
    clean.sort(key=lambda b: b["t"])
    gaps = sum(max(0, (clean[i]["t"] - clean[i - 1]["t"]) // interval_ms - 1) for i in range(1, len(clean)))
    flat = sum(1 for b in clean[-50:] if b["h"] == b["l"] and b["v"] == 0)
    if dupes:
        issues.append(f"DUPLICATES:{dupes}")
    if bad:
        issues.append(f"INVALID_BARS:{bad}")
    if unordered:
        issues.append(f"UNORDERED:{unordered}")
    if gaps:
        issues.append(f"GAPS:{gaps}")
    if flat >= 10:
        issues.append(f"FROZEN_TAIL:{flat}/50")
    n = len(clean)
    ok = n > 0 and gaps <= max_gap_frac * max(n, 1) and flat < 10 and bad <= 0.01 * max(len(bars), 1)
    return {"ok": ok, "issues": issues, "n": n, "dupes": dupes, "gaps": int(gaps), "bad": bad, "clean": clean}
