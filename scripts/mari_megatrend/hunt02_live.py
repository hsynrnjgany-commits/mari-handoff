#!/usr/bin/env python3
# MARI — HUNT-02 / MEGA-TREND HUNTER — LIVE SCANNER + TREND ENGINE + GROWTH CALIBRATION
# قفل: READ ONLY | PAPER ONLY | NO LIVE ORDERS — فقط داده عمومی، فقط خواندن، فقط PAPER.
# هیچ سفارشی صادر نمی‌شود؛ هیچ فایل محافظت‌شده‌ای لمس نمی‌شود.
# طبقه‌بندی = توصیف وضعیت؛ هیچ شاخصی به‌تنهایی مجوز ورود/خروج نیست.
import json, time, math, sys, os
import urllib.request, urllib.parse
from datetime import datetime, timezone

BASE = "https://api.binance.com"
FAPI = "https://fapi.binance.com"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
STABLES = {"USDC","FDUSD","TUSD","USDP","DAI","AEUR","EUR","USD1","BUSD","USDE","XUSD","EURI","USDS","SUSD"}
LV = [20, 50, 100, 200, 300, 500]

def get(url, timeout=20, tries=4):
    last = None
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "mari-research/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            last = e; time.sleep(0.8 * (k + 1))
    raise last

def ema(vals, n):
    if len(vals) < n: return None
    k = 2.0 / (n + 1); e = sum(vals[:n]) / n
    for v in vals[n:]: e = v * k + e * (1 - k)
    return e

def ema_series(vals, n):
    out = [None] * len(vals)
    if len(vals) < n: return out
    k = 2.0 / (n + 1); e = sum(vals[:n]) / n
    out[n - 1] = e
    for i in range(n, len(vals)):
        e = vals[i] * k + e * (1 - k); out[i] = e
    return out

def rsi(closes, n=14):
    if len(closes) < n + 1: return None
    g = l = 0.0
    for i in range(1, n + 1):
        d = closes[i] - closes[i - 1]
        g += max(d, 0); l += max(-d, 0)
    ag, al = g / n, l / n
    for i in range(n + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        ag = (ag * (n - 1) + max(d, 0)) / n
        al = (al * (n - 1) + max(-d, 0)) / n
    if al == 0: return 100.0
    return 100 - 100 / (1 + ag / al)

def atr(kl, n=14):
    if len(kl) < n + 1: return None
    trs = []
    for i in range(1, len(kl)):
        h, lo, pc = float(kl[i][2]), float(kl[i][3]), float(kl[i - 1][4])
        trs.append(max(h - lo, abs(h - pc), abs(lo - pc)))
    a = sum(trs[:n]) / n
    for t in trs[n:]: a = (a * (n - 1) + t) / n
    return a

def macd(closes):
    if len(closes) < 35: return None
    e12, e26 = ema_series(closes, 12), ema_series(closes, 26)
    line = [a - b for a, b in zip(e12, e26) if a is not None and b is not None]
    sig = ema(line, 9)
    if sig is None: return None
    return {"macd": line[-1], "signal": sig, "hist": line[-1] - sig}

def swings(kl, k=2):
    # پیرو همان قرارداد engine143: سوینگ در i فقط از i+k قابل مشاهده است (تأیید تأخیری)
    sh, sl = [], []
    for i in range(k, len(kl) - k):
        ok_h = all(float(kl[i][2]) > float(kl[j][2]) for j in range(i - k, i + k + 1) if j != i)
        ok_l = all(float(kl[i][3]) < float(kl[j][3]) for j in range(i - k, i + k + 1) if j != i)
        if ok_h: sh.append((i, float(kl[i][2])))
        if ok_l: sl.append((i, float(kl[i][3])))
    return sh, sl

def wilson(hits, n, z=1.96):
    if n == 0: return None
    p = hits / n; d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    hw = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(c - hw, 4), round(c + hw, 4)]

def main():
    ev = {"generated_utc": NOW, "lock": "READ ONLY | PAPER ONLY | NO LIVE ORDERS",
          "note": "طبقه‌بندی توصیفی است؛ هیچ شاخصی به‌تنهایی مجوز ورود/خروج نیست؛ هیچ عددی ساختگی نیست"}
    unav = []
    try:
        info = get(BASE + "/api/v3/exchangeInfo")
        syms = [s for s in info["symbols"] if s.get("quoteAsset") == "USDT" and s.get("status") == "TRADING"]
        bases = {}
        for s in syms:
            b = s["baseAsset"]
            if b in STABLES: continue
            bases.setdefault(b, s["symbol"])
        universe = sorted(bases.values())
    except Exception as e:
        print("EXCHANGE_INFO_FAIL", e); sys.exit(2)
    ev["universe_size"] = len(universe)
    try:
        t24 = get(BASE + "/api/v3/ticker/24hr")
        tm = {t["symbol"]: t for t in t24}
    except Exception as e:
        print("TICKER_FAIL", e); sys.exit(2)
    ranked = []
    for s in universe:
        t = tm.get(s)
        if not t: continue
        qv = float(t["quoteVolume"])
        if qv >= 3_000_000:
            ranked.append((s, qv, float(t["lastPrice"]), float(t["priceChangePercent"])))
    ranked.sort(key=lambda x: -x[1])
    top = ranked[:60]
    ev["ranked_liquid"] = len(ranked)
    try:
        bkl = get(BASE + "/api/v3/klines?symbol=BTCUSDT&interval=1d&limit=400")
        bc = [float(k[4]) for k in bkl]
        b_e200 = ema(bc, 200); b_e50 = ema(bc, 50)
        ev["btc"] = {"close": bc[-1], "ema200": round(b_e200, 1) if b_e200 else None,
                     "above_ema200": bool(bc[-1] > b_e200) if b_e200 else None,
                     "chg_7d_pct": round((bc[-1] / bc[-8] - 1) * 100, 2),
                     "chg_30d_pct": round((bc[-1] / bc[-31] - 1) * 100, 2),
                     "regime": "RISK_ON" if bc[-1] > b_e200 else "RISK_OFF"}
        btc_above_ref = bc[-1] > b_e200
    except Exception as e:
        ev["btc"] = "UNAVAILABLE"; btc_above_ref = None; unav.append("btc_klines")
    btc_chg7 = ev["btc"]["chg_7d_pct"] if isinstance(ev["btc"], dict) else None
    funding = {}
    try:
        pf = get(FAPI + "/fapi/v1/premiumIndex")
        for p in pf:
            if p["symbol"].endswith("USDT"):
                funding[p["symbol"]] = round(float(p["lastFundingRate"]) * 100, 4)
        ev["futures_funding"] = {"source": "binance-fapi", "n": len(funding), "note": "فقط تحلیل، بدون سفارش"}
    except Exception as e:
        ev["futures_funding"] = "UNAVAILABLE"; unav.append("futures_funding")
    oi = {}
    try:
        for s, _, _, _ in top[:10]:
            f = get(FAPI + "/fapi/v1/openInterest?" + urllib.parse.urlencode({"symbol": s}))
            oi[s] = float(f["openInterest"])
            time.sleep(0.1)
        ev["open_interest_top10"] = {"source": "binance-fapi", "n": len(oi)}
    except Exception as e:
        ev["open_interest_top10"] = "UNAVAILABLE"; unav.append("open_interest")
    rows, growth_events = [], []
    for s, qv, lastp, chg24 in top[:40]:
        try:
            kl = get(BASE + "/api/v3/klines?symbol=" + s + "&interval=1d&limit=1000")
            time.sleep(0.12)
        except Exception:
            rows.append({"symbol": s, "state": "INSUFFICIENT DATA", "why": "klines_fetch_fail"}); continue
        if len(kl) < 60:
            rows.append({"symbol": s, "state": "INSUFFICIENT DATA", "why": f"bars={len(kl)}", "recent_listing": True}); continue
        closes = [float(k[4]) for k in kl]; highs = [float(k[2]) for k in kl]; lows = [float(k[3]) for k in kl]
        n = len(closes); c = closes[-1]
        e20 = ema_series(closes, 20)[-1]; e50 = ema_series(closes, 50)[-1]; e200 = ema_series(closes, 200)[-1]
        r = rsi(closes); a = atr(kl)
        sh, sl = swings(kl, 2)
        hh = len(sh) >= 2 and sh[-1][1] > sh[-2][1]
        hl = len(sl) >= 2 and sl[-1][1] > sl[-2][1]
        lh = len(sh) >= 2 and sh[-1][1] < sh[-2][1]
        ll = len(sl) >= 2 and sl[-1][1] < sl[-2][1]
        hi20 = max(highs[-20:]); hi60 = max(highs[-60:]) if n >= 60 else max(highs)
        vols = [float(k[7]) for k in kl]
        vavg30 = sum(vols[-31:-1]) / 30 if len(vols) >= 31 else None
        vanom = round(vols[-1] / vavg30, 2) if vavg30 and vavg30 > 0 else None
        rs7 = round((closes[-1] / closes[-8] - 1) * 100, 2) if n >= 8 else None
        rs30 = round((closes[-1] / closes[-31] - 1) * 100, 2) if n >= 31 else None
        rs7_btc = round(rs7 - btc_chg7, 2) if (rs7 is not None and btc_chg7 is not None) else None
        if n < 210 or e200 is None:
            st = "INSUFFICIENT DATA"
        else:
            dd60 = (c / hi60 - 1) * 100
            if dd60 <= -30 and c < e50 < e200:
                st = "EXIT WARNING"; ist = "CRASH"
            elif c > e20 > e50 > e200 and hh and hl:
                st = "TREND CONFIRMED"; ist = "STRONG_BULLISH"
            elif c > e50 > e200 and (hh or hl):
                if c / hi20 > 0.97 and vanom and vanom >= 1.5 and r and r > 60:
                    st = "TREND RUNNER"; ist = "BULLISH"
                else:
                    st = "TREND CONFIRMED"; ist = "BULLISH"
            elif c < e50 < e200 and (lh or ll):
                st = "WEAKENING" if c > e200 else "EXIT WARNING"; ist = "BEARISH"
            elif c < e20 < e50 < e200 and lh and ll:
                st = "EXIT WARNING"; ist = "STRONG_BEARISH"
            elif hi20 <= c * 1.03 and e50 and e200 and e50 > e200:
                st = "BREAKOUT WATCH"; ist = "NEUTRAL"
            elif c > e200 and hl and r and 45 <= r <= 62:
                st = "EARLY ACCUMULATION"; ist = "NEUTRAL"
            elif c < e200:
                st = "WEAKENING"; ist = "BEARISH"
            else:
                st = "NEUTRAL"; ist = "NEUTRAL"
            if vanom is not None and vanom < 0.8 and rs7_btc is not None and rs7_btc < 0 and st in ("NEUTRAL", "WEAKENING"):
                st = "REJECTED"; ist = "WEAK"
        row = {"symbol": s, "state": st, "state_internal": ist, "close": c,
               "rsi14": round(r, 1) if r is not None else None,
               "atr_pct": round(a / c * 100, 2) if a else None,
               "stack_bull": bool(e20 and e50 and e200 and e20 > e50 > e200),
               "hh": hh, "hl": hl, "lh": lh, "ll": ll,
               "vol_anom_x": vanom, "rs7_vs_btc": rs7_btc, "chg24h_pct": round(chg24, 2),
               "funding_pct": funding.get(s), "oi_tracked": s in oi}
        if isinstance(a, float) and a > 0 and len(sl) and st != "INSUFFICIENT DATA":
            row["structural_stop"] = round(max(sl[-1][1] - 0.25 * a, 0), 6)
            row["trail_stop"] = round(max(hi20 - 3.0 * a, 0), 6)  # پارامتر منجمد X_ATR(3.0)
            row["risk_to_stop_pct"] = round((c - row["structural_stop"]) / c * 100, 2)
            row["targets"] = {f"+{x}%": round(c * (1 + x / 100), 6) for x in LV[:4]}
            row["rr_to_20pct"] = round(20.0 / (c - row["structural_stop"]) * c, 2) if c > row["structural_stop"] else None
        rows.append(row)
        if n >= 300 and e200 is not None:
            e50s = ema_series(closes, 50); e200s = ema_series(closes, 200)
            last_ev = -10**9
            for i in range(220, n - 1):
                if e50s[i] is None or e200s[i] is None: continue
                if not (closes[i] > e200s[i] and e50s[i] > e200s[i]): continue
                if closes[i] < max(highs[i - 20:i]): continue
                if i - last_ev < 30: continue
                last_ev = i
                fwd90 = max(closes[i + 1:min(i + 91, n)]) / closes[i] - 1
                fwd180 = max(closes[i + 1:min(i + 181, n)]) / closes[i] - 1
                growth_events.append({"symbol": s, "i": i, "fwd90": fwd90, "fwd180": fwd180,
                                      "regime": None if btc_above_ref is None else ("ON" if btc_above_ref else "OFF"),
                                      "date": datetime.fromtimestamp(kl[i][0] / 1000, timezone.utc).strftime("%Y-%m-%d")})
    valid = [r for r in rows if isinstance(r.get("close"), (int, float)) and r.get("state") != "INSUFFICIENT DATA"]
    above = sum(1 for r in valid if r["state"] in ("TREND CONFIRMED", "TREND RUNNER", "BREAKOUT WATCH", "EARLY ACCUMULATION", "NEUTRAL"))
    ev["breadth"] = {"watch_state_pct": round(above / max(len(valid), 1) * 100, 1), "n_valid": len(valid),
                     "def": "نسبت نمادهای سالم (غیر CRASH/BEARISH/REJECTED) از ۴۰ نماد برتر"}
    ev["sector_rotation"] = "UNAVAILABLE — بدون دیتاست تأییدشدهٔ سکتور در ورک‌اسپیس (MISSING)"
    ev["new_listings"] = {"method": "بر اساس <60 کندل روزانه در داده", "count": sum(1 for r in rows if r.get("recent_listing"))}
    calib = {}
    for x in LV:
        h90 = sum(1 for e in growth_events if e["fwd90"] >= x / 100)
        h180 = sum(1 for e in growth_events if e["fwd180"] >= x / 100)
        n = len(growth_events)
        calib[f"+{x}%"] = {
            "n_events": n,
            "p90d": round(h90 / n, 4) if n else None, "ci90d": wilson(h90, n),
            "p180d": round(h180 / n, 4) if n else None, "ci180d": wilson(h180, n),
            "verdict": "OK" if n >= 30 else "INSUFFICIENT EVIDENCE"}
    reg = {}
    for k in ("ON", "OFF"):
        sub = [e for e in growth_events if e["regime"] == k]
        reg[k] = {"n": len(sub), "p90d_50": round(sum(1 for e in sub if e["fwd90"] >= .5) / len(sub), 4) if sub else None}
    ev["growth_calibration"] = {"method": "فرکانس تاریخی واقعی پس از رویداد روند تأییدشده (شکست 20-day high با EMA50>EMA200 و فاصلهٔ 30 روز) — توصیفی، نه پیش‌بینی؛ احتمال ساختگی ممنوع",
                                "events_total": len(growth_events), "levels": calib, "by_btc_regime": reg}
    ev["unavailable_feeds"] = unav if unav else "none"
    ev["btc_ref"] = ev["btc"]
    ev["rows"] = rows
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    with open(os.path.join(OUT, f"hunt02_live_{ts}.json"), "w") as f:
        json.dump(ev, f, ensure_ascii=False)
    from collections import Counter
    cnt = Counter(r["state"] for r in rows)
    print(json.dumps({"out": f"hunt02_live_{ts}.json", "states": dict(cnt),
                      "events": len(growth_events), "calib": {k: v["p90d"] for k, v in calib.items()},
                      "btc": ev["btc"]}, ensure_ascii=False))

if __name__ == "__main__":
    main()
