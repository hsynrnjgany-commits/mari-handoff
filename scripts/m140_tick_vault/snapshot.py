#!/usr/bin/env python3
# M140-TICKVAULT — انبار تیک محلی برای بازشدن گیت G5 (بک‌تست واقعی آربیتراژ)
# READ ONLY بازار: فقط endpointهای عمومی بدون کلید · صفر سفارش · صفر دست‌زدن به paper-trades
# خروجی: data/tick-vault/snapshots-YYYYMMDD.jsonl (یک خط JSONL در هر چرخه) + پاک‌سازی فایل‌های >45 روز
import json, os, re, ssl, sys, time, glob, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta

BASE = "/home/z/my-project"
VAULT = f"{BASE}/data/tick-vault"
STATUS = f"{BASE}/scripts/m140_tick_vault/last_cycle.json"
ERRLOG = f"{BASE}/scripts/m140_tick_vault/errors.log"
SCHEMA = "m140-tickvault-v1"
RETENTION_DAYS = 45
CTX = ssl.create_default_context()
UA = {"User-Agent": "MARI-tickvault/1.0 (paper-research)"}
LEV_RE = re.compile(r"(UP|DOWN|3L|3S|5L|5S|BULL|BEAR)$")
STABLES = {"USDC", "USDS", "TUSD", "FDUSD", "DAI", "EUR", "USDP", "AEUR", "USD1", "USDE"}

def http_json(url, timeout=10):
    t0 = time.time()
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        payload = json.loads(r.read().decode("utf-8", "replace"))
    return payload, round((time.time() - t0) * 1000, 1)

def fnum(x):
    try:
        v = float(x)
        return v if v == v and v not in (float("inf"), float("-inf")) else None
    except Exception:
        return None

# ── آداپترهای بولک (سرب‌دفتر) — همان ۸ منبع اثبات‌شدهٔ M77-P2 ──
def bulk(ex):
    if ex == "binance":
        d, lat = http_json("https://api.binance.com/api/v3/ticker/bookTicker")
        rows = [{"sym": r["symbol"], "bid": fnum(r.get("bidPrice")), "ask": fnum(r.get("askPrice")),
                 "bidSz": fnum(r.get("bidQty")), "askSz": fnum(r.get("askQty"))} for r in d]
    elif ex == "mexc":
        d, lat = http_json("https://api.mexc.com/api/v3/ticker/bookTicker")
        rows = [{"sym": r["symbol"], "bid": fnum(r.get("bidPrice")), "ask": fnum(r.get("askPrice")),
                 "bidSz": fnum(r.get("bidQty")), "askSz": fnum(r.get("askQty"))} for r in d]
    elif ex == "okx":
        d, lat = http_json("https://www.okx.com/api/v5/market/tickers?instType=SPOT")
        rows = [{"sym": r["instId"], "bid": fnum(r.get("bidPx")), "ask": fnum(r.get("askPx")),
                 "bidSz": fnum(r.get("bidSz")), "askSz": fnum(r.get("askSz"))} for r in d.get("data", [])]
    elif ex == "bybit":
        d, lat = http_json("https://api.bybit.com/v5/market/tickers?category=spot")
        rows = [{"sym": r["symbol"], "bid": fnum(r.get("bid1Price")), "ask": fnum(r.get("ask1Price")),
                 "bidSz": fnum(r.get("bid1Size")), "askSz": fnum(r.get("ask1Size"))} for r in d.get("result", {}).get("list", [])]
    elif ex == "kucoin":
        d, lat = http_json("https://api.kucoin.com/api/v1/market/allTickers")
        rows = [{"sym": r["symbol"], "bid": fnum(r.get("buy")), "ask": fnum(r.get("sell")),
                 "bidSz": fnum(r.get("bestBidSize")), "askSz": fnum(r.get("bestAskSize"))} for r in d.get("data", {}).get("ticker", [])]
    elif ex == "gate":
        d, lat = http_json("https://api.gateio.ws/api/v4/spot/tickers")
        rows = [{"sym": r["currency_pair"], "bid": fnum(r.get("highest_bid")), "ask": fnum(r.get("lowest_ask")),
                 "bidSz": fnum(r.get("bid_size")), "askSz": fnum(r.get("ask_size"))} for r in d]
    elif ex == "bitget":
        d, lat = http_json("https://api.bitget.com/api/v2/spot/market/tickers")
        rows = [{"sym": r["symbol"], "bid": fnum(r.get("bidPr")), "ask": fnum(r.get("askPr")),
                 "bidSz": fnum(r.get("bidSz")), "askSz": fnum(r.get("askSz"))} for r in d.get("data", [])]
    elif ex == "htx":
        d, lat = http_json("https://api.huobi.pro/market/tickers")
        rows = [{"sym": r["symbol"], "bid": fnum(r.get("bid")), "ask": fnum(r.get("ask")),
                 "bidSz": fnum(r.get("bidSize")), "askSz": fnum(r.get("askSize"))} for r in d.get("data", [])]
    else:
        return [], 0.0
    return rows, lat

def norm_base(sym):
    s = sym.replace("-", "").replace("_", "")
    if not s.endswith("USDT"):
        return None
    b = s[:-4]
    if not b or LEV_RE.search(b) or b in STABLES:
        return None
    return b

# ── آداپترهای عمق L2 — همان نشانی‌های اثبات‌شدهٔ M77-P3 ──
def depth(ex, sym):
    try:
        if ex == "binance":
            d, lat = http_json(f"https://api.binance.com/api/v3/depth?symbol={sym}&limit=100")
            return [[fnum(p), fnum(s)] for p, s in d.get("asks", [])], [[fnum(p), fnum(s)] for p, s in d.get("bids", [])], lat
        if ex == "mexc":
            d, lat = http_json(f"https://api.mexc.com/api/v3/depth?symbol={sym}&limit=100")
            return [[fnum(p), fnum(s)] for p, s in d.get("asks", [])], [[fnum(p), fnum(s)] for p, s in d.get("bids", [])], lat
        if ex == "okx":
            d, lat = http_json(f"https://www.okx.com/api/v5/market/books?instId={sym}&sz=100")
            arr = d.get("data", [{}])[0]
            return [[fnum(a[0]), fnum(a[1])] for a in arr.get("asks", [])], [[fnum(b[0]), fnum(b[1])] for b in arr.get("bids", [])], lat
        if ex == "bybit":
            d, lat = http_json(f"https://api.bybit.com/v5/market/orderbook?category=spot&symbol={sym}&limit=50")
            r = d.get("result", {})
            return [[fnum(p), fnum(s)] for p, s in r.get("a", [])], [[fnum(p), fnum(s)] for p, s in r.get("b", [])], lat
        if ex == "kucoin":
            # نکتهٔ M140: مسیر فعلی کوکوین level2_100?symbol= است (الگوی {coin}?level= توسط API رد شد — پروب زندهٔ 2026-10-29)
            d, lat = http_json(f"https://api.kucoin.com/api/v1/market/orderbook/level2_100?symbol={sym}")
            dd = d.get("data", {})
            return [[fnum(p), fnum(s)] for p, s in dd.get("asks", [])], [[fnum(p), fnum(s)] for p, s in dd.get("bids", [])], lat
        if ex == "gate":
            d, lat = http_json(f"https://api.gateio.ws/api/v4/spot/order_book?currency_pair={sym}&limit=50")
            return [[fnum(a.get("p")), fnum(a.get("s"))] for a in d.get("asks", [])], [[fnum(b.get("p")), fnum(b.get("s"))] for b in d.get("bids", [])], lat
        if ex == "bitget":
            # نکتهٔ M140: مفرد orderbook (جمع بست) و data یک شیء است نه آرایه (پروب زندهٔ 2026-10-29)
            d, lat = http_json(f"https://api.bitget.com/api/v2/spot/market/orderbook?symbol={sym}&limit=50")
            dd = d.get("data") or {}
            if isinstance(dd, list):
                dd = dd[0] if dd else {}
            return [[fnum(p), fnum(s)] for p, s in dd.get("asks", [])], [[fnum(p), fnum(s)] for p, s in dd.get("bids", [])], lat
        if ex == "htx":
            d, lat = http_json(f"https://api.huobi.pro/market/depth?symbol={sym.lower()}&type=step0&depth=20")
            t = d.get("tick", {})
            return [[fnum(p), fnum(s)] for p, s in t.get("asks", [])], [[fnum(p), fnum(s)] for p, s in t.get("bids", [])], lat
    except Exception:
        return None, None, None
    return None, None, None

def tob_notional(price, size):
    if price is None or size is None:
        return None
    return round(price * size, 2)

def median(vals):
    s = sorted(vals)
    n = len(s)
    return None if n == 0 else s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2

def main():
    now = datetime.now(timezone.utc)
    rec = {"schema": SCHEMA, "cycle_ts": now.isoformat(), "recv_epoch_ms": int(now.timestamp() * 1000)}
    sources, all_rows = {}, []
    for ex in ["binance", "mexc", "okx", "bybit", "kucoin", "gate", "bitget", "htx"]:
        try:
            rows, lat = bulk(ex)
            for r in rows:
                r["ex"] = ex
            sources[ex] = {"http": 200, "latency_ms": lat, "rows": len(rows)}
            all_rows.extend(rows)
        except urllib.error.HTTPError as e:
            sources[ex] = {"http": e.code, "rows": 0}
        except Exception as e:
            sources[ex] = {"http": 0, "error": type(e).__name__}
        time.sleep(0.15)
    rec["sources"] = sources
    rec["normalized_rows"] = len(all_rows)

    by_base = {}
    for r in all_rows:
        b = norm_base(r["sym"])
        if b:
            r["base"] = b
            by_base.setdefault(b, []).append(r)
    rec["matched_bases"] = len(by_base)

    spreads, pos_tob50, suspect, top = [], 0, 0, []
    for b, rows in by_base.items():
        asks = [r for r in rows if r["ask"] and r["ask"] > 0]
        bids = [r for r in rows if r["bid"] and r["bid"] > 0]
        if not asks or not bids:
            continue
        buy = min(asks, key=lambda r: r["ask"])
        sell = max(bids, key=lambda r: r["bid"])
        if buy["ex"] == sell["ex"]:
            continue
        gross = (sell["bid"] / buy["ask"] - 1) * 100
        spreads.append(gross)
        tb, ts_ = tob_notional(buy["ask"], buy["askSz"]), tob_notional(sell["bid"], sell["bidSz"])
        if gross >= 5.0:
            suspect += 1
        if gross > 0 and (tb or 0) >= 50 and (ts_ or 0) >= 50:
            pos_tob50 += 1
            top.append({"base": b, "buy_ex": buy["ex"], "ask": buy["ask"], "sell_ex": sell["ex"],
                        "bid": sell["bid"], "gross_pct": round(gross, 4), "tob_buy_usdt": tb, "tob_sell_usdt": ts_,
                        "buy_sym": buy["sym"], "sell_sym": sell["sym"]})
    top.sort(key=lambda x: -x["gross_pct"])
    rec["stats"] = {"spread_p50": round(median(spreads), 4) if spreads else None,
                    "n_positive_tob50": pos_tob50, "n_suspect_ge5": suspect}
    rec["top20"] = top[:20]

    # ── آرشیو L2 برای حداکثر ۳ کاندید سالم (0.3–5٪، سرب‌دفتر ≥50 USDT) ──
    l2, l2_fail = [], []
    for c in [x for x in top if 0.3 <= x["gross_pct"] <= 5.0][:3]:
        asks, bids, lat = depth(c["buy_ex"], c["buy_sym"])
        time.sleep(0.15)
        asks2, bids2, lat2 = depth(c["sell_ex"], c["sell_sym"])
        if asks is None or asks2 is None or not asks or not bids2:
            l2_fail.append({"base": c["base"], "buy_ex": c["buy_ex"], "sell_ex": c["sell_ex"],
                            "reason": "depth_unavailable"})
            continue
        l2.append({"base": c["base"], "buy_ex": c["buy_ex"], "buy_sym": c["buy_sym"],
                   "sell_ex": c["sell_ex"], "sell_sym": c["sell_sym"],
                   "gross_pct": c["gross_pct"],
                   "buy_ask_top": c["ask"], "sell_bid_top": c["bid"],
                   "asks_buy_venue": asks[:50], "bids_sell_venue": bids2[:50],
                   "latency_ms": {"buy": lat, "sell": lat2},
                   "recv_ts": datetime.now(timezone.utc).isoformat()})
        time.sleep(0.15)
    rec["l2"] = l2
    rec["l2_fail"] = l2_fail

    os.makedirs(VAULT, exist_ok=True)
    day = now.strftime("%Y%m%d")
    path = f"{VAULT}/snapshots-{day}.jsonl"
    with open(path, "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")
    rec["vault_file"] = f"data/tick-vault/snapshots-{day}.jsonl"
    rec["vault_bytes"] = os.path.getsize(path)

    # ── نگهداشت ۴۵ روز ──
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
    pruned = []
    for p in glob.glob(f"{VAULT}/snapshots-*.jsonl"):
        m = re.search(r"snapshots-(\d{8})\.jsonl$", p)
        if m:
            try:
                d = datetime.strptime(m.group(1), "%Y%m%d").replace(tzinfo=timezone.utc)
                if d < cutoff:
                    os.remove(p)
                    pruned.append(os.path.basename(p))
            except ValueError:
                pass
    rec["pruned_files"] = pruned
    rec["ok"] = True
    with open(STATUS, "w") as f:
        json.dump(rec, f, ensure_ascii=False, indent=1)
    print(json.dumps({"ok": True, "cycle_ts": rec["cycle_ts"], "sources_ok": sum(1 for s in sources.values() if s.get("http") == 200),
                      "normalized_rows": rec["normalized_rows"], "matched_bases": rec["matched_bases"],
                      "p50": rec["stats"]["spread_p50"], "pos_tob50": pos_tob50, "suspect": suspect,
                      "l2_archived": len(l2), "file": rec["vault_file"]}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        os.makedirs(f"{BASE}/scripts/m140_tick_vault", exist_ok=True)
        with open(ERRLOG, "a") as f:
            f.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(),
                                "error": f"{type(e).__name__}: {e}"}, ensure_ascii=False) + "\n")
        print(json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"}, ensure_ascii=False))
        sys.exit(2)
