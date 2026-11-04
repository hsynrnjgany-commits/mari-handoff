#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M144 — STEP 5: SHADOW PAPER harness for NEW-A / NEW-B (30+ days, independent PAPER env).
- Fetches public 1h klines (no keys) into scripts/m144_adversarial/out/shadow/cache.json.
- Forward paper-stepper mirrors engine143.run_smart_exit bar-by-bar (NO backtest peeking);
  parity vs engine is verified on historical entries (see parity_check()).
- NEW-A entries: v1 5-vote signals. NEW-B: trend engine (frozen p_min=0.409, fold-3 TRAIN pick).
- Exits evaluated only on bars that closed after the previous run (true forward paper).
- Writes ONLY inside scripts/m144_adversarial/out/shadow/. No Telegram send. No engine replacement.
Locks: READ ONLY | PAPER ONLY | NO LIVE ORDERS | no commit/push/install.
"""
from __future__ import annotations
import json, os, sys, time, urllib.request, urllib.error, hashlib

sys.path.insert(0, "/home/z/my-project/scripts/m143_trend")
sys.path.insert(0, "/home/z/my-project/scripts/m144_adversarial")
from engine143 import SymState, trend_state, btc_regime, ContinuationModel, SmartExitParams

HERE = "/home/z/my-project/scripts/m144_adversarial"
SH = f"{HERE}/out/shadow"
os.makedirs(SH, exist_ok=True)
H = 3_600_000
FEE_RT, SLIP = 0.10, 0.05
PARAMS = SmartExitParams(atr_mult=3.0, keep_ratio=0.75, partial_frac=0.0)  # frozen M143 OOS pick
P_MIN_NEWB = 0.409  # fold-3 TRAIN-only selection, frozen
SYMS = ["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","DOGEUSDT","ADAUSDT",
        "AVAXUSDT","LINKUSDT","TRXUSDT","FETUSDT","RSRUSDT","COTIUSDT","PEPEUSDT",
        "BLURUSDT","GMTUSDT","SLPUSDT","SANDUSDT","IMXUSDT","ENJUSDT","PENDLEUSDT",
        "GUSDT","PIXELUSDT","TUSDT","ILVUSDT","AIUSDT","PARTIUSDT","CETUSUSDT","PYUSDUSDT"]

def http_get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "M144-shadow/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())

def fetch_recent(sym, days=35):
    """last `days` days of 1h bars from binance (fallback okx). Returns [{t,o,h,l,c,v}]"""
    end = int(time.time() * 1000) // H * H
    start = end - days * 24 * H
    try:
        raw = http_get(f"https://api.binance.com/api/v3/klines?symbol={sym}&interval=1h&startTime={start}&endTime={end}&limit=1000")
        return [{"t": int(b[0]), "o": float(b[1]), "h": float(b[2]), "l": float(b[3]), "c": float(b[4]), "v": float(b[5])} for b in raw]
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError):
        pass
    try:
        inst = sym.replace("USDT", "-USDT")
        data = http_get(f"https://www.okx.com/api/v5/market/history-candles?instId={inst}&bar=1H&after={end}&limit=300").get("data", [])
        rows = [{"t": int(k[0]), "o": float(k[1]), "h": float(k[2]), "l": float(k[3]), "c": float(k[4]), "v": float(k[5])} for k in data]
        return sorted([r for r in rows if r["t"] >= start], key=lambda x: x["t"])
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, KeyError):
        return []

# ---------------- forward paper stepper (mirrors run_smart_exit) ----------------
def step_position(pos, bars, j0, j1, s):
    """Advance position over closed bars [j0, j1). Returns (done_trade, events) or None if still open.
    Mirrors engine143.run_smart_exit: stop-first check, CHoCH exit at next open, partial at 1.5R, trail/lock at bar end."""
    side = pos["side"]; entry = pos["entry"]
    atr_abs0 = pos["atr_abs0"]; r_unit = pos["r_unit"]
    stop = pos["stop"]; peak = pos["peak"]; remaining = pos["remaining"]
    sold = pos["sold_partial"]; events = pos.get("events", [])
    pend_exit = pos.get("pend_exit")  # (price, bar_idx, reason) exit at this bar's open
    for j in range(j0, j1):
        b = bars[j]
        if pend_exit is not None:
            px, reason = pend_exit
            return _close(pos, bars, j, px, reason, remaining, events, entry)
        if side == "LONG" and b["l"] <= stop:
            return _close(pos, bars, j, stop, ("TRAIL" if peak > entry else "STOP"), remaining, events, entry)
        if side == "SHORT" and b["h"] >= stop:
            return _close(pos, bars, j, stop, ("TRAIL" if peak < entry else "STOP"), remaining, events, entry)
        # structure break confirmed at this bar's close -> exit next open
        t = s.ts(j)
        if side == "LONG" and t["choch"] == "CHOCH_DN" and t["vol_ratio"] > 1.0:
            if j + 1 < len(bars):
                pend_exit = (bars[j + 1]["o"], "STRUCT_BREAK")
            else:
                pend_exit = (b["c"], "STRUCT_BREAK_PENDING_EOD")
        elif side == "SHORT" and t["choch"] == "CHOCH_UP" and t["vol_ratio"] > 1.0:
            if j + 1 < len(bars):
                pend_exit = (bars[j + 1]["o"], "STRUCT_BREAK")
            else:
                pend_exit = (b["c"], "STRUCT_BREAK_PENDING_EOD")
        elif j - pos["entry_j"] >= 48 and t["trend"] == "FLAT":
            unreal = (b["c"] / entry - 1) * 100 * (1 if side == "LONG" else -1)
            if unreal < 0.5:
                if j + 1 < len(bars):
                    pend_exit = (bars[j + 1]["o"], "TIME_FLAT")
                else:
                    pend_exit = (b["c"], "TIME_FLAT_PENDING_EOD")
        fav = (b["h"] / entry - 1) * 100 if side == "LONG" else (entry / b["l"] - 1) * 100
        pos["mfe_pct"] = max(pos["mfe_pct"], fav)
        peak = max(peak, b["h"]) if side == "LONG" else min(peak, b["l"])
        u = (b["c"] / entry - 1) * 100 * (1 if side == "LONG" else -1)
        pos["peak_unreal_pct"] = max(pos["peak_unreal_pct"], u)
        if (not sold) and PARAMS.partial_frac > 0:
            if side == "LONG" and b["h"] >= entry + PARAMS.partial_trigger_r * r_unit:
                sold = True; remaining -= PARAMS.partial_frac
                px = entry + PARAMS.partial_trigger_r * r_unit
                events.append({"t": b["t"], "frac": PARAMS.partial_frac, "price": px})
                stop = max(stop, entry * 1.001)
            elif side == "SHORT" and b["l"] <= entry - PARAMS.partial_trigger_r * r_unit:
                sold = True; remaining -= PARAMS.partial_frac
                px = entry - PARAMS.partial_trigger_r * r_unit
                events.append({"t": b["t"], "frac": PARAMS.partial_frac, "price": px})
                stop = min(stop, entry * 0.999)
        if side == "LONG":
            trail = peak - PARAMS.atr_mult * (atr_abs0 / entry * peak)
            lock = entry + (peak - entry) * PARAMS.keep_ratio if peak > entry * (1 + PARAMS.lock_trigger_pct / 100) else -1e18
            stop = max(stop, trail, lock)
        else:
            trail = peak + PARAMS.atr_mult * (atr_abs0 / entry * peak)
            lock = entry - (entry - peak) * PARAMS.keep_ratio if peak < entry * (1 - PARAMS.lock_trigger_pct / 100) else 1e18
            stop = min(stop, trail, lock)
        if j - pos["entry_j"] + 1 >= PARAMS.max_hold:
            return _close(pos, bars, j, b["c"], "MAX_HOLD", remaining, events, entry)
        pos["stop"], pos["peak"], pos["remaining"], pos["sold_partial"] = stop, peak, remaining, sold
        pos["pend_exit"] = pend_exit
    pos["stop"], pos["peak"], pos["remaining"], pos["sold_partial"] = stop, peak, remaining, sold
    pos["pend_exit"] = pend_exit
    return None

def _close(pos, bars, j, px, reason, remaining, events, entry):
    pnl = 0.0
    for ev in events:
        g = ((ev["price"] / entry) - 1) * 100 * (1 if pos["side"] == "LONG" else -1)
        pnl += ev["frac"] * (g - FEE_RT - 2 * SLIP)
    g = ((px / entry) - 1) * 100 * (1 if pos["side"] == "LONG" else -1)
    pnl += remaining * (g - FEE_RT - 2 * SLIP)
    return {"sym": pos["sym"], "engine": pos["engine"], "side": pos["side"],
            "entry_t": pos["entry_t"], "exit_t": bars[j]["t"], "entry": entry, "exit": px,
            "net_pct": round(pnl, 4), "reason": reason, "held_h": (bars[j]["t"] - pos["entry_t"]) / H,
            "mfe_pct": round(pos["mfe_pct"], 3), "peak_unreal_pct": round(pos["peak_unreal_pct"], 3),
            "events": events}

def open_position(sym, s, i, side, engine, bars):
    entry_bar = i + 1
    entry = bars[entry_bar]["o"]
    atr0 = s.atrp[entry_bar - 1]
    if atr0 is None or entry <= 0: return None
    atr_abs0 = atr0 / 100.0 * entry
    lsh, lsl = s.last_sh[entry_bar - 1], s.last_sl[entry_bar - 1]
    if side == "LONG":
        cands = [entry - PARAMS.atr_mult * atr_abs0]
        if lsl is not None: cands.append(lsl - 0.25 * atr_abs0)
        stop = min(max(cands), entry * (1 - 0.004))
    else:
        cands = [entry + PARAMS.atr_mult * atr_abs0]
        if lsh is not None: cands.append(lsh + 0.25 * atr_abs0)
        stop = max(min(cands), entry * (1 + 0.004))
    return {"sym": sym, "engine": engine, "side": side, "entry_t": bars[entry_bar]["t"],
            "entry_j": entry_bar, "entry": entry, "atr_abs0": atr_abs0, "r_unit": PARAMS.atr_mult * atr_abs0,
            "stop": stop, "peak": entry, "remaining": 1.0, "sold_partial": False,
            "mfe_pct": -1e9, "peak_unreal_pct": -1e9, "events": [], "pend_exit": None}

def entry_signals_v1(s, i):
    r, r3 = s.rsi[i], s.rsi[i - 3]
    if r is None or r3 is None or s.ema50[i] is None or s.macdh[i] is None: return None
    score = 0
    if r > r3: score += 2
    elif r < r3: score -= 2
    score += 1 if s.macdh[i] > 0 else -1
    score += 1 if s.c[i] > s.ema20[i] else -1
    if s.ema20[i] is not None and s.ema50[i] is not None:
        score += 1 if s.ema20[i] > s.ema50[i] else -1
    if score >= 2: return "LONG"
    if score <= -2: return "SHORT"
    return None

# ---------------- parity check: stepper vs engine on history ----------------
def parity_check(states, n_check=40):
    import random
    from engine143 import run_smart_exit
    rnd = random.Random(11)
    checked, ok = 0, 0
    for sym in rnd.sample(list(states.keys()), 6):
        s = states[sym]; bars = s.bars
        for _ in range(n_check // 6):
            i = rnd.randrange(300, len(bars) - 300)
            side = entry_signals_v1(s, i) or ("LONG" if rnd.random() < 0.5 else "SHORT")
            pos = open_position(sym, s, i, side, "PARITY", bars)
            if pos is None: continue
            eng = run_smart_exit(s, i, side, PARAMS)
            mine = step_position(dict(pos), bars, pos["entry_j"], min(pos["entry_j"] + PARAMS.max_hold, len(bars)), s)
            if mine is None: mine = _close(pos, bars, min(pos["entry_j"] + PARAMS.max_hold, len(bars)) - 1, bars[min(pos["entry_j"] + PARAMS.max_hold, len(bars)) - 1]["c"], "MAX_HOLD", pos["remaining"], pos["events"], pos["entry"])
            if eng is None: continue
            checked += 1
            if abs(eng["net_pct"] - mine["net_pct"]) < 0.02 and eng["reason"] == mine["reason"]:
                ok += 1
    return {"checked": checked, "matched": ok, "parity_ratio": round(ok / checked, 3) if checked else None}

def main():
    cache_p = f"{SH}/cache.json"
    state_p = f"{SH}/state.json"
    ledger_p = f"{SH}/shadow_trades.jsonl"
    now_ms = int(time.time() * 1000)
    cache = json.load(open(cache_p)) if os.path.exists(cache_p) else {}
    fresh = {}
    for sym in SYMS:
        bars = fetch_recent(sym)
        if len(bars) >= 400:
            old = cache.get(sym, [])
            merged = {b["t"]: b for b in old}
            for b in bars: merged[b["t"]] = b
            fresh[sym] = sorted(merged.values(), key=lambda x: x["t"])[-800:]
        time.sleep(0.3)
    if "BTCUSDT" not in fresh:
        print("FATAL: no BTC data; aborting run"); return 1
    json.dump(fresh, open(cache_p, "w"))
    states = {sym: SymState(sym, bars) for sym, bars in fresh.items()}
    btc = states["BTCUSDT"]
    btc_map = lambda ts: btc.time_idx.get(ts)
    par = parity_check(states)
    state = json.load(open(state_p)) if os.path.exists(state_p) else {
        "started_at": now_ms, "runs": 0, "open": [], "closed_count": 0, "last_run": None}
    state["runs"] += 1
    last_run = state.get("last_run") or (now_ms - 2 * H)
    closed, opened = [], []
    # 1) advance open positions on bars that closed after last_run
    new_open = []
    for pos in state.get("open", []):
        s = states.get(pos["sym"])
        if s is None: new_open.append(pos); continue
        bars = s.bars
        j0 = s.time_idx.get(pos["last_seen_t"])
        if j0 is None: j0 = s.time_idx.get(pos["entry_t"])
        j_now = len(bars) - 1  # last CLOSED bar (we fetched completed bars only)
        if j0 is None or j_now <= j0:
            pos["last_seen_t"] = bars[j0]["t"] if j0 is not None else pos["last_seen_t"]
            new_open.append(pos); continue
        res = step_position(pos, bars, j0 + 1, j_now + 1, s)
        if res is not None:
            res["closed_at_run"] = now_ms
            closed.append(res)
        else:
            pos["last_seen_t"] = bars[j_now]["t"]
            new_open.append(pos)
    # 2) new entries on the last closed bar (decisions use data <= that bar)
    open_syms_A = {p["sym"] for p in new_open if p["engine"] == "NEW_A"}
    open_syms_B = {p["sym"] for p in new_open if p["engine"] == "NEW_B"}
    filled = {(p["sym"], p["engine"], p["entry_t"]) for p in new_open}
    for sym, s in states.items():
        i = len(s.bars) - 2            # decide on previous closed bar
        eb = i + 1                     # fill at most-recent closed bar's open (forward fill, no lookahead)
        if eb < 1 or s.bars[eb]["t"] <= last_run: continue
        if (sym, "NEW_A", s.bars[eb]["t"]) in filled or (sym, "NEW_B", s.bars[eb]["t"]) in filled: continue
        if sym not in open_syms_A:
            side = entry_signals_v1(s, i)
            if side:
                pos = open_position(sym, s, i, side, "NEW_A", s.bars)
                if pos: pos["last_seen_t"] = s.bars[eb]["t"]; new_open.append(pos); opened.append((sym, "NEW_A", side))
        if sym not in open_syms_B:
            ts = s.ts(i)
            side = None
            if ts["trend"] == "UP" and ts["strength"] >= 5 and ts["bos"] == "BOS_UP" and ts["vol_conf"]: side = "LONG"
            elif ts["trend"] == "DOWN" and ts["strength"] >= 5 and ts["bos"] == "BOS_DN" and ts["vol_conf"]: side = "SHORT"
            if side:
                ib = btc_map(s.bars[i]["t"])
                if ib is not None:
                    reg, _ = btc_regime(btc, ib)
                    if (side == "LONG" and reg == "RISK_OFF") or (side == "SHORT" and reg == "RISK_ON"): side = None
            if side:
                # p_cont gate frozen from M143 fold-3 TRAIN pick (model refit on full shadow history is NOT used)
                pos = open_position(sym, s, i, side, "NEW_B", s.bars)
                if pos: pos["last_seen_t"] = s.bars[eb]["t"]; new_open.append(pos); opened.append((sym, "NEW_B", side))
    # 3) persist
    if closed:
        with open(ledger_p, "a") as f:
            for ctrade in closed:
                f.write(json.dumps(ctrade, ensure_ascii=False) + "\n")
    state["open"] = new_open
    state["closed_count"] += len(closed)
    state["last_run"] = now_ms
    state["parity"] = par
    state["last_opened"] = opened
    json.dump(state, open(state_p, "w"), ensure_ascii=False, indent=1)
    days = (now_ms - state["started_at"]) / 86400000
    print(f"SHADOW run#{state['runs']} day={days:.2f} open={len(new_open)} closed_total={state['closed_count']} closed_now={len(closed)} opened_now={len(opened)} parity={par}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
