#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M144 — دریافت تاریخٔ بلندتر برای همان ۲۹ نماد M143 (فقط endpoint عمومی، بدون کلید)
هدف: افزودن دوره‌های واقعی BEAR پیش از پنجرهٔ ۱۶۰روزهٔ M143.
ورودی: scripts/m143_trend/data/klines_1h.json (خواندنی — دست‌نخورده)
خروجی: scripts/m144_adversarial/data/merged_1h.json
قفل: READ ONLY | PAPER ONLY | NO LIVE ORDERS
"""
import json, os, time, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = "/home/z/my-project/scripts/m143_trend/data/klines_1h.json"
OUT = f"{HERE}/data/merged_1h.json"
BASE = "https://data-api.binance.vision/api/v3"
START_MS = None  # ستون‌بندی پایین: 2024-10-01T00:00Z
SLEEP = 0.30


def http_json(url, retries=4):
    for a in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "m144-audit/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            time.sleep(1.5 * (a + 1))
    raise RuntimeError(f"failed: {url}")


def fetch_range(sym, start_ms, end_ms):
    rows, cur = [], start_ms
    while cur < end_ms:
        url = (f"{BASE}/klines?symbol={sym}&interval=1h&startTime={cur}"
               f"&endTime={end_ms}&limit=1000")
        batch = http_json(url)
        if not batch:
            break
        rows.extend(batch)
        cur = batch[-1][6] + 1
        if len(batch) < 1000:
            break
        time.sleep(SLEEP)
    return rows


def norm(b):
    return {"t": int(b[0]), "o": float(b[1]), "h": float(b[2]), "l": float(b[3]),
            "c": float(b[4]), "v": float(b[5])}


def main():
    os.makedirs(f"{HERE}/data", exist_ok=True)
    src = json.load(open(SRC))
    import datetime
    start = int(datetime.datetime(2024, 10, 1, tzinfo=datetime.timezone.utc).timestamp() * 1000)
    merged, meta = {}, {}
    syms = list(src["symbols"].keys())
    for idx, sym in enumerate(syms):
        old = src["symbols"][sym]
        first_old = old[0]["t"]
        new_bars = []
        try:
            raw = fetch_range(sym, start, first_old - 1)
            new_bars = [norm(b) for b in raw if float(b[4]) > 0]
        except Exception as e:
            print(f"{sym}: EXT-FAIL {e}", flush=True)
        seen, bars = set(), []
        for r in sorted(new_bars + old, key=lambda x: x["t"]):
            if r["t"] not in seen:
                seen.add(r["t"]); bars.append(r)
        merged[sym] = bars
        meta[sym] = {"old_bars": len(old), "ext_bars": len(new_bars),
                     "merged_bars": len(bars),
                     "first": bars[0]["t"] if bars else None,
                     "last": bars[-1]["t"] if bars else None}
        print(f"[{idx+1}/{len(syms)}] {sym}: ext={len(new_bars)} merged={len(bars)} "
              f"first={datetime.datetime.utcfromtimestamp(bars[0]['t']/1000):%Y-%m-%d}", flush=True)
        json.dump({"fetched_at": int(time.time() * 1000), "symbols": merged, "meta": meta},
                  open(OUT, "w"))
    print(f"DONE → {OUT}")


if __name__ == "__main__":
    main()
