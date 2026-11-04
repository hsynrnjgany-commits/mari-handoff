#!/usr/bin/env python3
"""
DERIV-01 گام ۱ — پروب endpointهای عمومی مشتقه (فقط خواندنی، بدون کلید)
خروجی: کد HTTP + شکل پاسخ برای هر کاندید. هیچ حدسی گزارش نمی‌شود؛ فقط پروب زنده.
"""
import json
import ssl
import time
import urllib.request
import urllib.error

CTX = ssl.create_default_context()
UA = {"User-Agent": "MARI-deriv01-probe/1.0 (paper-research)"}

CANDIDATES = [
    # ── تووبیت: نامزدهای فاندینگ/OI/L-S/لیکویید (سبک‌های مختلف) ──
    ("TOOBIT spot 24h(all)",          "https://api.toobit.com/quote/v1/ticker/24hr"),
    ("TOOBIT funding (quote/v1)",     "https://api.toobit.com/quote/v1/fundingRate?symbol=BTCUSDT"),
    ("TOOBIT funding (api/v1)",       "https://api.toobit.com/api/v1/fundingRate?symbol=BTCUSDT"),
    ("TOOBIT premiumIndex (fapi)",    "https://api.toobit.com/fapi/v1/premiumIndex?symbol=BTCUSDT"),
    ("TOOBIT premiumIndex (fapi.+)","https://fapi.toobit.com/fapi/v1/premiumIndex?symbol=BTCUSDT"),
    ("TOOBIT v5 tickers linear",      "https://api.toobit.com/v5/market/tickers?category=linear&symbol=BTCUSDT"),
    ("TOOBIT v5 tickers linear(all)", "https://api.toobit.com/v5/market/tickers?category=linear"),
    ("TOOBIT openInterest (fapi)",    "https://api.toobit.com/fapi/v1/openInterest?symbol=BTCUSDT"),
    ("TOOBIT v5 open-interest",       "https://api.toobit.com/v5/market/open-interest?category=linear&symbol=BTCUSDT&intervalTime=5min"),
    ("TOOBIT long/short (binance-ish)","https://api.toobit.com/futures/data/globalLongShortAccountRatio?symbol=BTCUSDT&period=5m&limit=1"),
    ("TOOBIT v5 account-ratio",       "https://api.toobit.com/v5/market/account-ratio?category=linear&symbol=BTCUSDT&period=5min&limit=1"),
    ("TOOBIT liq allForceOrders",     "https://api.toobit.com/api/v1/allForceOrders?symbol=BTCUSDT&limit=1"),
    ("TOOBIT liq fapi forceOrders",   "https://api.toobit.com/fapi/v1/forceOrders?symbol=BTCUSDT&limit=1"),
    ("TOOBIT contract/api tickers",   "https://api.toobit.com/contract/api/v1/tickers"),
    # ── منابع عمومی دیگر (برای پر کردن شکاف‌های تووبیت) ──
    ("BINANCE fapi premiumIndex(all)","https://fapi.binance.com/fapi/v1/premiumIndex"),
    ("BINANCE fapi openInterest",     "https://fapi.binance.com/fapi/v1/openInterest?symbol=BTCUSDT"),
    ("BINANCE fapi fundingRate",      "https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&limit=1"),
    ("BINANCE long/short global",     "https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol=BTCUSDT&period=5m&limit=1"),
    ("BINANCE liq allForceOrders",    "https://fapi.binance.com/fapi/v1/allForceOrders?symbol=BTCUSDT&limit=1"),
    ("BYBIT v5 tickers linear(all)",  "https://api.bybit.com/v5/market/tickers?category=linear"),
    ("BYBIT v5 account-ratio",        "https://api.bybit.com/v5/market/account-ratio?category=linear&symbol=BTCUSDT&period=5min&limit=1"),
    ("BYBIT v5 open-interest",        "https://api.bybit.com/v5/market/open-interest?category=linear&symbol=BTCUSDT&intervalTime=5min&limit=1"),
    ("OKX funding-rate (all)",        "https://www.okx.com/api/v5/public/funding-rate?instId=BTC-USDT-SWAP"),
    ("OKX open-interest (all)",       "https://www.okx.com/api/v5/public/open-interest?instType=SWAP"),
    ("OKX liq-orders (public)",       "https://www.okx.com/api/v5/public/liquidation-orders?instType=SWAP&state=filled&uly=BTC-USD"),
]


def probe(url):
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=10, context=CTX) as r:
            body = r.read().decode("utf-8", "replace")
            code = r.status
    except urllib.error.HTTPError as e:
        return e.code, f"HTTP_{e.code}"
    except Exception as e:
        return 0, type(e).__name__
    try:
        d = json.loads(body)
    except Exception:
        return code, f"non-json len={len(body)}"
    shape = ""
    if isinstance(d, list):
        shape = f"list[{len(d)}] first={json.dumps(d[0], ensure_ascii=False)[:160]}" if d else "list[]"
    elif isinstance(d, dict):
        keys = list(d.keys())[:6]
        shape = f"dict keys={keys}"
        for k in ("result", "data", "list"):
            if k in d and isinstance(d[k], list) and d[k]:
                shape += f" {k}[{len(d[k])}] first={json.dumps(d[k][0], ensure_ascii=False)[:200]}"
                break
    return code, shape[:280]


def main():
    for name, url in CANDIDATES:
        code, shape = probe(url)
        print(f"{code:>4} | {name:34} | {shape}")
        time.sleep(0.8)


if __name__ == "__main__":
    main()
