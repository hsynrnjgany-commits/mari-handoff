#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M144 — STEP 1: data integrity + survivorship audit of scripts/m143_trend/data/klines_1h.json
READ ONLY on source file; writes only to scripts/m144_adversarial/out/.
Checks: duplicate timestamps, gaps, incomplete/zero candles, OHLC violations,
timezone alignment across symbols, venue mixing, universe survivorship (34→29).
"""
import json, os, sys, hashlib
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = "/home/z/my-project/scripts/m143_trend/data/klines_1h.json"
OUTD = f"{HERE}/out"
os.makedirs(OUTD, exist_ok=True)
H = 3_600_000

d = json.load(open(SRC))
syms, meta = d["symbols"], d.get("meta", {})
rows = []

# --- survivorship: universe vs fetched vs used ---
UNIVERSE = ["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","DOGEUSDT","ADAUSDT",
            "AVAXUSDT","LINKUSDT","TRXUSDT","FETUSDT","RSRUSDT","COTIUSDT","PEPEUSDT",
            "BLURUSDT","GMTUSDT","SLPUSDT","SANDUSDT","IMXUSDT","ENJUSDT","PENDLEUSDT",
            "RUNEUSDT","DEXEUSDT","GUSDT","PIXELUSDT","TUSDT","ILVUSDT","AIUSDT",
            "PARTIUSDT","CETUSUSDT","PYUSDUSDT","XAVAUSDT","EDENUSDT","EULUSDT"]
missing = [s for s in UNIVERSE if s not in syms]
used = [s for s, b in syms.items() if len(b) >= 2600]
dropped_by_filter = [s for s, b in syms.items() if len(b) < 2600]
rows.append({"check": "survivorship_universe", "universe_listed": len(UNIVERSE),
             "fetched_ok": len(syms), "missing_from_universe": missing,
             "dropped_by_2600_filter": dropped_by_filter,
             "used_in_backtest": len(used)})

# --- per symbol integrity ---
integ = []
for sym, bars in syms.items():
    ts = [b["t"] for b in bars]
    dup = len(ts) - len(set(ts))
    gaps = sum(1 for a, b2 in zip(ts, ts[1:]) if b2 - a != H)
    zero_vol = sum(1 for b in bars if b["v"] <= 0)
    oops = sum(1 for b in bars if not (b["h"] >= max(b["o"], b["c"]) - 1e-12 and b["l"] <= min(b["o"], b["c"]) + 1e-12 and b["h"] >= b["l"]))
    nonpos = sum(1 for b in bars if b["c"] <= 0 or b["o"] <= 0)
    last_bar_age_h = (d["fetched_at"] - ts[-1]) / H
    integ.append({"sym": sym, "bars": len(bars), "dup_ts": dup, "gap_hours": gaps,
                  "zero_vol_bars": zero_vol, "ohlc_violations": oops, "nonpos": nonpos,
                  "first": ts[0], "last": ts[-1], "last_bar_age_h": round(last_bar_age_h, 1),
                  "src": meta.get(sym, {}).get("source", "?")})
rows.append({"check": "per_symbol_integrity", "symbols": integ})
bad = {r["sym"]: r for r in integ if r["dup_ts"] or r["gap_hours"] or r["zero_vol_bars"] or r["ohlc_violations"] or r["nonpos"] or r["last_bar_age_h"] > 3}
rows.append({"check": "integrity_summary", "symbols_with_issues": bad})

# --- cross-symbol time alignment (t=0 offset + venue mixing) ---
srcs = Counter(r["src"] for r in integ)
rows.append({"check": "venue_mixing", "sources": dict(srcs),
             "hourly_open_offsets_utc": dict(Counter(int(r["first"] % H) for r in integ))})

# --- incomplete candle check: last bar of each symbol vs fetched_at ---
rows.append({"check": "fetched_at_utc", "fetched_at": d["fetched_at"],
             "note": "all timestamps are UTC epoch ms (binance/okx/mexc open time)"})

# --- coverage gap: bars beyond last tested fold (3360) ---
cov = {s: max(0, len(b) - 3360) for s, b in syms.items()}
rows.append({"check": "test_coverage", "wf_tested_upto_bar": 3360,
             "per_symbol_untested_tail": {s: v for s, v in cov.items() if v > 0}})

out = {"mission": "M144-STEP1", "rows": rows}
p = f"{OUTD}/m144_step1_data_audit.json"
json.dump(out, open(p, "w"), ensure_ascii=False, indent=1)
dig = hashlib.sha256(open(p, "rb").read()).hexdigest()
print("WROTE", p, "sha256", dig[:16])
print("missing_from_universe:", missing)
print("symbols_with_issues:", list(bad.keys()) or "NONE")
print("sources:", dict(srcs))
print("gap symbols:", [r["sym"] for r in integ if r["gap_hours"]])
