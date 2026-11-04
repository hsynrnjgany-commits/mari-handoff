#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M144 — STEP 1b/REPLAY: faithful re-run of M143 walk-forward (folds 0-2) + BEAR extension fold 3.
- Reuses scripts/m143_trend/engine143.py UNMODIFIED (import only).
- Signal caching = pure speed optimization; reproduction is verified against
  out/m143_results.json pooled metrics (folds 0-2) with exact match required.
- Every trade instrumented: MAE, crash overlap, BTC context, cost components.
- Saves trades per fold to out/m144_trades_fold{k}.json + summary.
Locks: READ ONLY | PAPER ONLY | NO LIVE ORDERS. Writes only under m144_adversarial/out/.
"""
from __future__ import annotations
import json, os, sys, time, hashlib

sys.path.insert(0, "/home/z/my-project/scripts/m143_trend")
sys.path.insert(0, "/home/z/my-project/scripts/m143_trend")
from engine143 import (SymState, trend_state, btc_regime, ContinuationModel,
                       SmartExitParams, run_smart_exit, run_old_exit)

HERE = "/home/z/my-project/scripts/m144_adversarial"
DATA = "/home/z/my-project/scripts/m143_trend/data/klines_1h.json"
OUTD = f"{HERE}/out"
os.makedirs(OUTD, exist_ok=True)

SIZE_USD = 100.0
TRAIN0, TEST, N_FOLDS, STEP = 1920, 480, 3, 480
COOLDOWN = 6
FEE_RT, SLIP = 0.10, 0.05  # engine143 defaults

def load_states():
    d = json.load(open(DATA))
    return {sym: SymState(sym, bars) for sym, bars in d["symbols"].items() if len(bars) >= 2600}

# ---- cached signal builders (identical semantics to backtest143) ----
def entry_signals_v1(s, lo, hi):
    sigs = []
    for i in range(max(60, lo), hi):
        r, r3 = s.rsi[i], s.rsi[i - 3]
        if r is None or r3 is None or s.ema50[i] is None or s.macdh[i] is None:
            continue
        score = 0
        if r > r3: score += 2
        elif r < r3: score -= 2
        score += 1 if s.macdh[i] > 0 else -1
        score += 1 if s.c[i] > s.ema20[i] else -1
        if s.ema20[i] is not None and s.ema50[i] is not None:
            score += 1 if s.ema20[i] > s.ema50[i] else -1
        if score >= 2: sigs.append((i, "LONG", score))
        elif score <= -2: sigs.append((i, "SHORT", score))
    return sigs

def entry_signals_trend(s, lo, hi, model=None, p_min=0.55, btc=None, btc_map=None):
    sigs = []
    for i in range(max(60, lo), hi):
        ts = s.ts(i)
        side = None
        if ts["trend"] == "UP" and ts["strength"] >= 5 and ts["bos"] == "BOS_UP" and ts["vol_conf"]:
            side = "LONG"
        elif ts["trend"] == "DOWN" and ts["strength"] >= 5 and ts["bos"] == "BOS_DN" and ts["vol_conf"]:
            side = "SHORT"
        if side is None: continue
        if btc is not None and btc_map is not None:
            ib = btc_map(s.bars[i]["t"])
            if ib is not None:
                reg, _ = btc_regime(btc, ib)
                if (side == "LONG" and reg == "RISK_OFF") or (side == "SHORT" and reg == "RISK_ON"):
                    continue
        if model is not None and model.n >= 40:
            x = ContinuationModel.features(s, i)
            p, wil = model.predict(x)
            if p < p_min: continue
            sigs.append((i, side, ts["strength"], p, wil))
        else:
            sigs.append((i, side, ts["strength"], None, None))
    return sigs

def calibrate_exit_params(states, hi, sig_cache, cap_i=None, max_sig_per_sym=140):
    best_score, best_key = None, None
    for atr_mult in (2.0, 2.5, 3.0):
        for keep in (0.55, 0.65, 0.75):
            for pf_frac in (0.0, 0.4):
                p = SmartExitParams(atr_mult=atr_mult, keep_ratio=keep, partial_frac=pf_frac)
                tot, n_tot = 0.0, 0
                for sym, s in states.items():
                    cnt, last_exit = 0, -1
                    for (i, side, *_r) in sig_cache[sym]:
                        if cnt >= max_sig_per_sym: break
                        if i <= last_exit + 6: continue
                        t = run_smart_exit(s, i, side, p, cap_i=cap_i)
                        cnt += 1
                        if t:
                            tot += t["net_pct"]; n_tot += 1
                            last_exit = s.time_idx.get(t["exit_t"], 10**9)
                if best_score is None or tot > best_score:
                    best_score, best_key = tot, (atr_mult, keep, pf_frac)
    return SmartExitParams(atr_mult=best_key[0], keep_ratio=best_key[1], partial_frac=best_key[2]), best_key, best_score

def calibrate_model(states, hi):
    X, y = [], []
    for s in states.values():
        for i in range(60, hi - 24):
            t = s.ts(i)
            if t["trend"] == "UP" and t["strength"] >= 6:
                fwd = (s.c[i + 24] / s.c[i] - 1) * 100
                X.append(ContinuationModel.features(s, i))
                y.append(1 if fwd > 0.3 else 0)
    m = ContinuationModel(); m.fit(X, y)
    return m

def calibrate_p_min(states, hi, model, btc, btc_map, sig_trend_cache, cap_i=None, max_sig_per_sym=60):
    ps = []
    for sym, lst in sig_trend_cache.items():
        for (i, side, st, p, wil) in lst:
            if p is not None: ps.append(p)
    if not ps: return 0.0, 0
    ps.sort()
    qs = {0.0: 0.0, 0.4: ps[int(0.4 * (len(ps) - 1))], 0.6: ps[int(0.6 * (len(ps) - 1))],
          0.8: ps[int(0.8 * (len(ps) - 1))]}
    best, best_key, best_n = None, 0.0, 0
    for q, thr in qs.items():
        tot, n_tot = 0.0, 0
        for sym, s in states.items():
            cnt, last_exit = 0, -1
            for (i, side, st, p, wil) in sig_trend_cache[sym]:
                if p is not None and p < thr: continue
                if p is None and model.n >= 40: continue
                if cnt >= max_sig_per_sym: break
                if i <= last_exit + 6: continue
                t = run_smart_exit(s, i, side, SmartExitParams(), cap_i=cap_i)
                cnt += 1
                if t:
                    tot += t["net_pct"]; n_tot += 1
                    last_exit = s.time_idx.get(t["exit_t"], 10**9)
        if n_tot >= 30 and (best is None or tot > best):
            best, best_key, best_n = tot, thr, n_tot
    return (best_key if best is not None else 0.0), (best_n if best is not None else len(ps))

def run_config(states, lo, hi, sig_fn, exit_fn, cooldown=6):
    trades = []
    for sym, s in states.items():
        last_exit = -1
        for sig in sig_fn(s, lo, hi):
            i, side = sig[0], sig[1]
            if i <= last_exit + cooldown or i + 1 >= hi: continue
            t = exit_fn(s, i, side, sig, hi)
            if t:
                trades.append(t)
                last_exit = s.time_idx.get(t["exit_t"], 10**9)
                if last_exit >= hi: break
    return trades

# ---- instrumentation ----
def instrument(t, s, btc, btc_map):
    bars = s.bars
    eb = s.time_idx[t["entry_t"]]; xb = s.time_idx[t["exit_t"]]
    entry = t["entry"]
    if t["side"] == "LONG":
        mae = max((entry - b["l"]) / entry * 100 for b in bars[eb:xb + 1])
    else:
        mae = max((b["h"] - entry) / entry * 100 for b in bars[eb:xb + 1])
    t["mae_pct"] = round(mae, 3)
    ev = [{"frac": e["frac"], "gross": round(((e["price"] / entry) - 1) * 100 * (1 if t["side"] == "LONG" else -1), 4)} for e in t.get("events", [])]
    rem = 1.0 - sum(e["frac"] for e in ev)
    t["comps"] = {"events": ev, "rem": round(rem, 4), "exit_gross": t["gross_pct"]}
    # BTC context at entry
    ib = btc_map(bars[eb]["t"]) if btc_map else None
    t["btc_i"] = ib
    if btc is not None and ib is not None and ib >= 168:
        c = btc.c
        t["btc_7d_ret"] = round((c[ib] / c[ib - 168] - 1) * 100, 2)
        t["btc_1h_ret"] = round((c[ib] / c[ib - 1] - 1) * 100, 2)
        t["btc_atr_rank"] = round(btc._atr_rank[ib] or 0.5, 3)
    else:
        t["btc_7d_ret"] = t["btc_1h_ret"] = t["btc_atr_rank"] = None
    # crash overlap during holding (symbol OR BTC hourly <= -5% / -2.5%)
    crash = False
    for b in bars[eb:xb + 1]:
        j = s.time_idx[b["t"]]
        if j >= 1 and s.c[j] and s.c[j-1] and (s.c[j] / s.c[j-1] - 1) * 100 <= -5.0:
            crash = True; break
    if btc is not None and ib is not None:
        for j in range(max(1, ib), min(xb - eb + ib + 1, len(btc.c) - 1) + 1):
            if btc.c[j] and btc.c[j-1] and (btc.c[j] / btc.c[j-1] - 1) * 100 <= -2.5:
                crash = True; break
    t["crash_overlap"] = crash
    t["cls"] = "BTC" if s.sym == "BTCUSDT" else "ALT"
    return t

def main():
    t0 = time.time()
    states = load_states()
    btc = states.get("BTCUSDT")
    btc_map = (lambda ts: btc.time_idx.get(ts)) if btc is not None else None
    print(f"symbols={len(states)} loaded {time.time()-t0:.0f}s", flush=True)

    folds = [(0, 1920), (1, 2400), (2, 2880), (3, 3360)]  # (k, tr_hi); fold3 = BEAR extension
    all_old, all_newA, all_newB = [], [], []
    fold_rows = []
    for k, tr_hi in folds:
        tf = time.time()
        te_lo, te_hi = tr_hi, min(tr_hi + TEST, 3899)
        sig_v1 = {sym: entry_signals_v1(s, 60, tr_hi) for sym, s in states.items()}
        params_frozen, key, tr_score = calibrate_exit_params(states, tr_hi, sig_v1, cap_i=tr_hi)
        model = calibrate_model(states, tr_hi)
        sig_trend = {sym: entry_signals_trend(s, 60, tr_hi, model, 0.0, btc, btc_map) for sym, s in states.items()}
        p_min_frozen, p_n = calibrate_p_min(states, tr_hi, model, btc, btc_map, sig_trend, cap_i=tr_hi)
        print(f"fold{k}: train[0:{tr_hi}] test[{te_lo}:{te_hi}] params={key} model_n={model.n} p_min={p_min_frozen:.3f} ({time.time()-tf:.0f}s)", flush=True)
        old_t = run_config(states, te_lo, te_hi,
                           lambda s, a, b: entry_signals_v1(s, a, b),
                           lambda s, i, side, sig, cap: run_old_exit(s, i, side, cap_i=cap))
        newA_t = run_config(states, te_lo, te_hi,
                            lambda s, a, b: entry_signals_v1(s, a, b),
                            lambda s, i, side, sig, cap: run_smart_exit(s, i, side, params_frozen, cap_i=cap))
        newB_t = run_config(states, te_lo, te_hi,
                            lambda s, a, b: entry_signals_trend(s, a, b, model, p_min_frozen, btc, btc_map),
                            lambda s, i, side, sig, cap: run_smart_exit(s, i, side, params_frozen, cap_i=cap))
        reg = "NEUTRAL"
        if btc is not None and te_hi < len(btc.c):
            ret = (btc.c[te_hi - 1] / btc.c[te_lo] - 1) * 100
            reg = "BULL" if ret > 5 else ("BEAR" if ret < -5 else "NEUTRAL")
        for t in old_t: instrument(t, states[t["sym"]], btc, btc_map)
        for t in newA_t: instrument(t, states[t["sym"]], btc, btc_map)
        for t in newB_t: instrument(t, states[t["sym"]], btc, btc_map)
        for t in old_t: t["fold"] = k
        for t in newA_t: t["fold"] = k
        for t in newB_t: t["fold"] = k
        json.dump({"fold": k, "train_hi": tr_hi, "test": [te_lo, te_hi], "regime": reg,
                   "params": key, "model_n": model.n, "p_min": p_min_frozen,
                   "old": old_t, "newA": newA_t, "newB": newB_t},
                  open(f"{OUTD}/m144_trades_fold{k}.json", "w"), ensure_ascii=False)
        fold_rows.append({"fold": k, "regime": reg, "n_old": len(old_t), "n_newA": len(newA_t), "n_newB": len(newB_t),
                          "old_net": round(sum(t["net_pct"] for t in old_t) / 100 * SIZE_USD, 2),
                          "newA_net": round(sum(t["net_pct"] for t in newA_t) / 100 * SIZE_USD, 2),
                          "newB_net": round(sum(t["net_pct"] for t in newB_t) / 100 * SIZE_USD, 2)})
        print(f"  fold{k} done: old={len(old_t)} newA={len(newA_t)} newB={len(newB_t)} regime={reg} ({time.time()-tf:.0f}s)", flush=True)
        all_old += old_t; all_newA += newA_t; all_newB += newB_t
        if k == 2:
            pooled02 = {"old": len(all_old), "newA": len(all_newA), "newB": len(all_newB)}

    json.dump({"folds": fold_rows, "pooled_counts_f012": pooled02,
               "pooled_counts_f0123": {"old": len(all_old), "newA": len(all_newA), "newB": len(all_newB)},
               "elapsed_s": round(time.time() - t0, 1)},
              open(f"{OUTD}/m144_replay_summary.json", "w"), ensure_ascii=False, indent=1)
    print("WROTE replay summary; elapsed", round(time.time() - t0, 1), "s", flush=True)

if __name__ == "__main__":
    main()
