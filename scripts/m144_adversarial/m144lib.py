#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M144 — کتابخانهٔ ممیزی خصمانه (فقط-خواندنی نسبت به M143)
موتورهای M143 بدون هیچ تغییری import می‌شوند؛ variant های خصمانه در همین فایل و با برچسب ساخته می‌شوند.
قفل: READ ONLY | PAPER ONLY | NO LIVE ORDERS
"""
from __future__ import annotations
import json, math, os, random, sys

HERE = os.path.dirname(os.path.abspath(__file__))
M143 = "/home/z/my-project/scripts/m143_trend"
sys.path.insert(0, M143)
from engine143 import (SymState, trend_state, btc_regime, ContinuationModel,      # noqa: E402
                       SmartExitParams, run_smart_exit, run_old_exit,
                       COST_RT_PCT, SLIP_PCT, HOUR_MS)
import backtest143 as BT                                                           # noqa: E402
from backtest143 import (entry_signals_v1, entry_signals_trend, calibrate_model,   # noqa: E402
                         calibrate_exit_params, calibrate_p_min, run_config, metrics,
                         TRAIN0, TEST, STEP, SIZE_USD)

ORIG_DATA = f"{M143}/data/klines_1h.json"
EXT_DATA = f"{HERE}/data/merged_1h.json"
OUTD = f"{HERE}/out"
os.makedirs(OUTD, exist_ok=True)


# --------------------------- بارگذاری داده ---------------------------
def load_states(path=ORIG_DATA, min_bars=2600):
    d = json.load(open(path))
    states = {}
    for sym, bars in d["symbols"].items():
        if len(bars) >= min_bars:
            states[sym] = SymState(sym, bars)
    return states


def load_bars(path):
    return json.load(open(path))["symbols"]


# --------------------------- پروتکل فولد M143 (بازتولید وفادار) ---------------------------
def run_fold(states, k, btc=None, btc_map=None, fee_rt=COST_RT_PCT, fee_newA=None,
             gap_fill=False, keep_override=None, verbose=False):
    """یک فولد دقیقاً با پروتکل backtest143.main — خروجی: ردیف خلاصه + معاملات کامل."""
    tr_hi = TRAIN0 + k * STEP
    te_lo, te_hi = tr_hi, min(tr_hi + TEST, 3899 if len(next(iter(states.values())).bars) <= 3900 else 10 ** 9)
    params_frozen, key, tr_score = calibrate_exit_params(states, tr_hi, cap_i=tr_hi)
    if keep_override is not None:
        # فقط keep_ratio روی TRAIN دوباره انتخاب می‌شود؛ atr_mult و partial_frac هم روی TRAIN
        best_score, best_key = None, None
        for atr_mult in (2.0, 2.5, 3.0):
            for pf_frac in (0.0, 0.4):
                p = SmartExitParams(atr_mult=atr_mult, keep_ratio=keep_override, partial_frac=pf_frac)
                tot = 0.0
                for sym, s in states.items():
                    cnt, last_exit = 0, -1
                    for (i, side, *_r) in entry_signals_v1(s, 60, tr_hi):
                        if cnt >= 140:
                            break
                        if i <= last_exit + 6:
                            continue
                        t = run_smart_exit(s, i, side, p, cap_i=tr_hi)
                        cnt += 1
                        if t:
                            tot += t["net_pct"]
                            last_exit = s.time_idx.get(t["exit_t"], 10 ** 9)
                if best_score is None or tot > best_score:
                    best_score, best_key = tot, (atr_mult, pf_frac)
        params_frozen = SmartExitParams(atr_mult=best_key[0], keep_ratio=keep_override,
                                        partial_frac=best_key[1])
        key = (best_key[0], keep_override, best_key[1])
    model = calibrate_model(states, tr_hi)
    p_min_frozen, p_n = calibrate_p_min(states, tr_hi, model, btc, btc_map, cap_i=tr_hi)
    fn = (gap_fill_run_old if gap_fill else run_old_exit)
    fs = (gap_fill_run_smart if gap_fill else run_smart_exit)
    feeA = fee_rt if fee_newA is None else fee_newA
    old_t = run_config(states, te_lo, te_hi,
                       lambda s, a, b: entry_signals_v1(s, a, b),
                       lambda s, i, side, sig, cap: fn(s, i, side, fee_rt=fee_rt, cap_i=cap))
    newA_t = run_config(states, te_lo, te_hi,
                        lambda s, a, b: entry_signals_v1(s, a, b),
                        lambda s, i, side, sig, cap: fs(s, i, side, params_frozen, fee_rt=feeA, cap_i=cap))
    newB_t = run_config(states, te_lo, te_hi,
                        lambda s, a, b: entry_signals_trend(s, a, b, model, p_min_frozen, btc, btc_map),
                        lambda s, i, side, sig, cap: fs(s, i, side, params_frozen, fee_rt=feeA, cap_i=cap))
    reg = "NEUTRAL"
    if btc is not None and te_hi < len(btc.c):
        ret = (btc.c[te_hi - 1] / btc.c[te_lo] - 1) * 100
        reg = "BULL" if ret > 5 else ("BEAR" if ret < -5 else "NEUTRAL")
    row = {"fold": k, "train_hi": tr_hi, "test_lo": te_lo, "test_hi": te_hi, "regime": reg,
           "params": list(key), "model_n": model.n, "p_min": round(p_min_frozen, 4),
           "old": metrics(old_t), "newA": metrics(newA_t), "newB": metrics(newB_t)}
    return row, old_t, newA_t, newB_t


def fold_count(n_bars):
    """تعداد فولدها برای سری به طول n_bars با همان TRAIN0/TEST/STEP."""
    ks = []
    k = 0
    while True:
        tr_hi = TRAIN0 + k * STEP
        if tr_hi + TEST > n_bars - 1:
            break
        ks.append(k)
        k += 1
    return ks


# --------------------------- Variant خصمانه: پر شدن گپ روی استاپ ---------------------------
def gap_fill_run_old(s, entry_i, side, tp_pct=2.0, sl_pct=1.0, fee_rt=COST_RT_PCT,
                     max_hold=96, cap_i=None):
    """کپی همان run_old_exit با یک تغییر خصمانه: اگر کندل با گپ از استاپ رد شد،
    پرش در قیمت Open (بدتر) ثبت می‌شود نه در قیمت استاپ."""
    bars = s.bars
    entry_bar = entry_i + 1
    if entry_bar >= len(bars):
        return None
    hard_end = min(entry_bar + max_hold, len(bars)) if cap_i is None else min(entry_bar + max_hold, len(bars), cap_i)
    entry = bars[entry_bar]["o"]
    tp = entry * (1 + tp_pct / 100) if side == "LONG" else entry * (1 - tp_pct / 100)
    sl = entry * (1 - sl_pct / 100) if side == "LONG" else entry * (1 + sl_pct / 100)
    mfe_pct, max_unreal = -1e9, -1e9
    for i in range(entry_bar, hard_end):
        b = bars[i]
        fav = (b["h"] / entry - 1) * 100 if side == "LONG" else (entry / b["l"] - 1) * 100
        mfe_pct = max(mfe_pct, fav)
        u = (b["c"] / entry - 1) * 100 * (1 if side == "LONG" else -1)
        max_unreal = max(max_unreal, u)
        hit_sl = b["l"] <= sl if side == "LONG" else b["h"] >= sl
        hit_tp = b["h"] >= tp if side == "LONG" else b["l"] <= tp
        if hit_sl:
            if side == "LONG":
                px = min(sl, b["o"])   # ← خصمانه: گپ
            else:
                px = max(sl, b["o"])   # ← خصمانه: گپ
            xr = "SL"
        elif hit_tp:
            px, xr = tp, "TP"
        else:
            continue
        g = ((px / entry) - 1) * 100 * (1 if side == "LONG" else -1)
        return {"sym": s.sym, "side": side, "entry_t": bars[entry_bar]["t"], "exit_t": b["t"],
                "entry": entry, "exit": px, "net_pct": round(g - fee_rt - 2 * SLIP_PCT, 4),
                "gross_pct": round(g, 4), "reason": xr, "held_h": (b["t"] - bars[entry_bar]["t"]) / HOUR_MS,
                "mfe_pct": round(mfe_pct, 3), "peak_unreal_pct": round(max_unreal, 3),
                "partial": False, "events": []}
    i = hard_end - 1
    g = ((bars[i]["c"] / entry) - 1) * 100 * (1 if side == "LONG" else -1)
    return {"sym": s.sym, "side": side, "entry_t": bars[entry_bar]["t"], "exit_t": bars[i]["t"],
            "entry": entry, "exit": bars[i]["c"], "net_pct": round(g - fee_rt - 2 * SLIP_PCT, 4),
            "gross_pct": round(g, 4), "reason": ("MAX_HOLD" if cap_i is None else "FOLD_END"),
            "held_h": (bars[i]["t"] - bars[entry_bar]["t"]) / HOUR_MS,
            "mfe_pct": round(mfe_pct, 3), "peak_unreal_pct": round(max_unreal, 3),
            "partial": False, "events": []}


def gap_fill_run_smart(s, entry_i, side, params: SmartExitParams, fee_rt=COST_RT_PCT, cap_i=None):
    """کپی run_smart_exit با تغییر خصمانهٔ گپ روی استاپ/تریل؛ بقیهٔ منطق مو به مو."""
    bars = s.bars
    entry_bar = entry_i + 1
    if entry_bar >= len(bars):
        return None
    hard_end = min(entry_bar + params.max_hold, len(bars)) if cap_i is None else min(entry_bar + params.max_hold, len(bars), cap_i)
    entry = bars[entry_bar]["o"]
    atr0 = s.atrp[entry_bar - 1]
    if atr0 is None or entry <= 0:
        return None
    atr_abs0 = atr0 / 100.0 * entry
    lsh, lsl = s.last_sh[entry_bar - 1], s.last_sl[entry_bar - 1]
    if side == "LONG":
        cands = [entry - params.atr_mult * atr_abs0]
        if lsl is not None:
            cands.append(lsl - 0.25 * atr_abs0)
        stop = max(cands)
        stop = min(stop, entry * (1 - 0.004))
        r_unit = params.atr_mult * atr_abs0
    else:
        cands = [entry + params.atr_mult * atr_abs0]
        if lsh is not None:
            cands.append(lsh + 0.25 * atr_abs0)
        stop = min(cands)
        stop = max(stop, entry * (1 + 0.004))
        r_unit = params.atr_mult * atr_abs0

    remaining, sold_partial = 1.0, False
    peak, max_unreal_pct, mfe_pct = entry, -1e9, -1e9
    events = []
    exit_reason = exit_price = exit_bar = None
    for i in range(entry_bar, hard_end):
        b = bars[i]
        if side == "LONG" and b["l"] <= stop:
            px = min(stop, b["o"])   # ← خصمانه: گپ
            exit_price, exit_bar, exit_reason = px, i, ("TRAIL" if peak > entry else "STOP")
            break
        if side == "SHORT" and b["h"] >= stop:
            px = max(stop, b["o"])   # ← خصمانه: گپ
            exit_price, exit_bar, exit_reason = px, i, ("TRAIL" if peak < entry else "STOP")
            break
        if i + 1 < len(bars):
            t = s.ts(i)
            if side == "LONG" and t["choch"] == "CHOCH_DN" and t["vol_ratio"] > 1.0:
                exit_price, exit_bar, exit_reason = bars[i + 1]["o"], i + 1, "STRUCT_BREAK"
                break
            if side == "SHORT" and t["choch"] == "CHOCH_UP" and t["vol_ratio"] > 1.0:
                exit_price, exit_bar, exit_reason = bars[i + 1]["o"], i + 1, "STRUCT_BREAK"
                break
            if i - entry_bar >= 48 and t["trend"] == "FLAT":
                unreal = (b["c"] / entry - 1) * 100 * (1 if side == "LONG" else -1)
                if unreal < 0.5:
                    exit_price, exit_bar, exit_reason = bars[i + 1]["o"], i + 1, "TIME_FLAT"
                    break
        fav = (b["h"] / entry - 1) * 100 if side == "LONG" else (entry / b["l"] - 1) * 100
        mfe_pct = max(mfe_pct, fav)
        peak = max(peak, b["h"]) if side == "LONG" else min(peak, b["l"])
        u = (b["c"] / entry - 1) * 100 * (1 if side == "LONG" else -1)
        max_unreal_pct = max(max_unreal_pct, u)
        if (not sold_partial) and params.partial_frac > 0:
            if side == "LONG" and b["h"] >= entry + params.partial_trigger_r * r_unit:
                sold_partial = True
                remaining -= params.partial_frac
                px = entry + params.partial_trigger_r * r_unit
                events.append({"t": b["t"], "type": "PARTIAL", "frac": params.partial_frac, "price": px})
                stop = max(stop, entry * 1.001)
            elif side == "SHORT" and b["l"] <= entry - params.partial_trigger_r * r_unit:
                sold_partial = True
                remaining -= params.partial_frac
                px = entry - params.partial_trigger_r * r_unit
                events.append({"t": b["t"], "type": "PARTIAL", "frac": params.partial_frac, "price": px})
                stop = min(stop, entry * 0.999)
        if side == "LONG":
            trail = peak - params.atr_mult * (atr0 / 100.0 * peak)
            lock = entry + (peak - entry) * params.keep_ratio if peak > entry * (1 + params.lock_trigger_pct / 100) else -1e18
            stop = max(stop, trail, lock)
        else:
            trail = peak + params.atr_mult * (atr0 / 100.0 * peak)
            lock = entry - (entry - peak) * params.keep_ratio if peak < entry * (1 - params.lock_trigger_pct / 100) else 1e18
            stop = min(stop, trail, lock)
    else:
        i = hard_end - 1
        exit_price, exit_bar, exit_reason = bars[i]["c"], i, ("MAX_HOLD" if cap_i is None else "FOLD_END")
    if exit_price is None:
        return None
    pnl = 0.0
    for ev in events:
        g = ((ev["price"] / entry) - 1) * 100 * (1 if side == "LONG" else -1)
        pnl += ev["frac"] * (g - fee_rt - 2 * SLIP_PCT)
    g_exit = ((exit_price / entry) - 1) * 100 * (1 if side == "LONG" else -1)
    pnl += remaining * (g_exit - fee_rt - 2 * SLIP_PCT)
    held_h = (bars[exit_bar]["t"] - bars[entry_bar]["t"]) / HOUR_MS
    return {"sym": s.sym, "side": side, "entry_t": bars[entry_bar]["t"], "exit_t": bars[exit_bar]["t"],
            "entry": entry, "exit": exit_price, "net_pct": round(pnl, 4),
            "gross_pct": round(g_exit, 4), "reason": exit_reason, "held_h": held_h,
            "mfe_pct": round(mfe_pct, 3), "peak_unreal_pct": round(max_unreal_pct, 3),
            "partial": sold_partial, "events": events}


# --------------------------- آمار خصمانه ---------------------------
def equity_curve(trades, size=SIZE_USD):
    seq = sorted(trades, key=lambda t: t["entry_t"])
    eq, peak, maxdd = 0.0, 0.0, 0.0
    pts = []
    for t in seq:
        eq += t["net_pct"] / 100 * size
        peak = max(peak, eq)
        maxdd = min(maxdd, eq - peak)
        pts.append((t["entry_t"], eq))
    return pts, maxdd


def pf_of(trades, size=SIZE_USD):
    gw = sum(t["net_pct"] for t in trades if t["net_pct"] > 0) / 100 * size
    gl = abs(sum(t["net_pct"] for t in trades if t["net_pct"] < 0) / 100 * size)
    return (gw / gl) if gl > 0 else None


def block_bootstrap(trades, block_len=48, iters=3000, seed=144, size=SIZE_USD):
    """بوت‌استرپ بلوکی زمانی روی معاملات مرتب بر اساس entry_t — برخلاف M143 که iid بود."""
    if not trades:
        return None
    seq = sorted(trades, key=lambda t: (t["entry_t"], t["sym"]))
    n = len(seq)
    nb = max(1, math.ceil(n / block_len))
    rng = random.Random(seed)
    nets, pfs, dds = [], [], []
    for _ in range(iters):
        sample = []
        for _b in range(nb):
            j = rng.randrange(max(1, n - block_len + 1))
            sample.extend(seq[j:j + block_len])
        sample = sample[:n]
        net = sum(t["net_pct"] for t in sample) / 100 * size
        pts, dd = equity_curve(sample, size)
        nets.append(net)
        p = pf_of(sample, size)
        pfs.append(p if p is not None else 999.0)
        dds.append(dd)
    nets.sort(); dds.sort()
    pfs_ok = sorted(p for p in pfs if p < 900)
    def ci(a):
        return [round(a[int(0.025 * len(a))], 2), round(a[min(len(a) - 1, int(0.975 * len(a)))], 2)]
    net0 = sum(t["net_pct"] for t in seq) / 100 * size
    _, dd0 = equity_curve(seq, size)
    p0 = pf_of(seq, size)
    return {"n": n, "block_len": block_len, "iters": iters,
            "net_usd": round(net0, 2), "net_ci95": ci(nets),
            "pf": round(p0, 3) if p0 else None,
            "pf_ci95": [round(pfs_ok[int(0.025 * len(pfs_ok))], 3),
                        round(pfs_ok[min(len(pfs_ok) - 1, int(0.975 * len(pfs_ok)))], 3)] if pfs_ok else None,
            "maxdd_usd": round(dd0, 2), "maxdd_ci95": ci(dds),
            "p_net_gt0": round(sum(1 for x in nets if x > 0) / len(nets), 4),
            "p_pf_gt1": round(sum(1 for x in pfs if x > 1) / len(pfs), 4)}


def paired_block_bootstrap(a_map, b_map, block_len=48, iters=3000, seed=145):
    """diff = a − b روی ورودهای مشترک (sym, entry_t) — بلوکی."""
    common = sorted(set(a_map) & set(b_map))
    if not common:
        return None
    diffs = [a_map[k] - b_map[k] for k in common]
    n = len(diffs)
    nb = max(1, math.ceil(n / block_len))
    rng = random.Random(seed)
    means = []
    for _ in range(iters):
        s = []
        for _b in range(nb):
            j = rng.randrange(max(1, n - block_len + 1))
            s.extend(diffs[j:j + block_len])
        means.append(sum(s[:n]) / n)
    means.sort()
    return {"n_common": n, "mean_diff_pct": round(sum(diffs) / n, 4),
            "ci95": [round(means[int(0.025 * len(means))], 4),
                     round(means[min(len(means) - 1, int(0.975 * len(means)))], 4)]}


def drop_topk(trades, k, size=SIZE_USD):
    seq = sorted(trades, key=lambda t: t["net_pct"], reverse=True)
    rest = seq[k:]
    net = sum(t["net_pct"] for t in rest) / 100 * size
    _, dd = equity_curve(rest, size)
    p = pf_of(rest, size)
    return {"k_removed": k, "n": len(rest), "net_usd": round(net, 2),
            "pf": round(p, 3) if p else None, "maxdd_usd": round(dd, 2)}


def concurrency(trades):
    """تعداد پوزیشن‌های باز هم‌زمان (سطح نماد‌ها ترکیبی) — وابستگی معاملات هم‌پوشان."""
    evs = []
    idx = {b["t"]: i for i, b in enumerate(sorted({t["entry_t"] for t in trades}))}  # نه — از bar index استفاده می‌کنیم
    for t in trades:
        evs.append((t["entry_t"], 1))
        evs.append((t["exit_t"], -1))
    evs.sort(key=lambda x: (x[0], x[1]))
    cur, mx, tot, samples = 0, 0, 0, 0
    for _, d in evs:
        cur += d
        if d > 0:
            tot += cur; samples += 1
        mx = max(mx, cur)
    return {"max_concurrent": mx, "avg_concurrent": round(tot / max(1, samples), 2)}


# --------------------------- رژیم داده‌محور ---------------------------
def btc_regimes_data(bars, dd_thresh=-20.0):
    """رژیم داده‌محور: افت از سقف ۹۰روزهٔ BTC. BULL: نزدیک سقف؛ BEAR: افت ≥ dd_thresh؛ NEUTRAL بین."""
    out = {}
    cs = [b["c"] for b in bars]
    ts = [b["t"] for b in bars]
    hi = cs[0]
    hi_t = ts[0]
    for i, (c, t) in enumerate(zip(cs, ts)):
        if c >= hi:
            hi, hi_t = c, t
        # سقف ۹۰روزهٔ متحرک (۲۱۶۰ کندل)
        lo0 = max(0, i - 2160)
        win_hi = max(cs[lo0:i + 1])
        dd = (c / win_hi - 1) * 100
        out[t] = ("BULL" if dd > -10 else ("BEAR" if dd < dd_thresh else "NEUTRAL"))
    return out


def crash_bars(btc_bars, ret_thresh=-4.0, atr_rank_thresh=0.97):
    """کندل‌های ریزش شدید/جهش نوسان BTC: بازده ساعتی ≤ ret_thresh یا atr_rank بالا."""
    s = SymState("BTCUSDT", btc_bars)
    out = []
    for i in range(1, len(btc_bars)):
        r = (btc_bars[i]["c"] / btc_bars[i - 1]["c"] - 1) * 100
        rank = s._atr_rank[i] or 0.5
        if r <= ret_thresh or rank >= atr_rank_thresh:
            out.append({"i": i, "t": btc_bars[i]["t"], "ret_pct": round(r, 2), "atr_rank": round(rank, 3)})
    return out
