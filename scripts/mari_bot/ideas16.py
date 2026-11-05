# -*- coding: utf-8 -*-
"""ideas16 — ثبت پیشاپیش در RESEARCH_LOG (2026-11-05T21:00Z). فقط تمرینی.

اصلاح دو ایراد روشیِ ideas14 (هر دو را خودم در گزارش ideas14 اعلام کردم):
  ایراد ۱: آستانهٔ توان بر پایهٔ «تعداد سیگنال» بود → اینجا بر پایهٔ **تعداد برندهٔ مورد انتظار**.
  ایراد ۲: محک زمان حضور در بازار را کنترل نمی‌کرد → اینجا محک **هم‌نقد** است.

H-MARI-Z-061: نسخهٔ گسترده‌تر قاعده (دو ویژگی به‌جای سه) روی دادهٔ آزمونِ دیده‌نشده:
              نرخ برنده‌شدن بالاتر از نرخ پایه، CI95 بالای صفر، با توان کافی.
H-MARI-Z-062: سبد همان قاعده در برابر **محک هم‌نقد** (همان هفته‌ها در بازار، ارزهای تصادفی
              از همان جهان): هم بازده مرکب و هم شارپ بیشتر.
"""
from __future__ import annotations

import random

from .ideas10 import Panel, curve_stats, is_monday
from .ideas14 import (FEATURES, HOLD_WEEKS, bucket, collect, features, learn_rule)

DAY_MS = 86_400_000
N_PICK_WIDE = 2                # قاعدهٔ گسترده: دو ویژگی برتر (پیش از دیدن نتیجه ثابت شد)
MIN_EXPECTED_WINNERS = 10.0    # آستانهٔ توان: کمتر از این = «آزمون‌ناپذیر»، نه رد
N_SHUFFLE = 200                # تعداد سبد تصادفی برای محک هم‌نقد

IDEA16_HYPOTHESES = {
    "H-MARI-Z-061": "قاعدهٔ گستردهٔ دو-ویژگی‌ای «ارزهای صعودی» روی دادهٔ آزمون دیده‌نشده: نرخ برنده‌شدن بالاتر از نرخ پایه با CI95 بالای صفر. اگر تعداد برندهٔ مورد انتظار زیر ۱۰ باشد، حکم «آزمون‌ناپذیر» است نه رد.",
    "H-MARI-Z-062": "سبد همان قاعده در برابر محک هم‌نقد (همان هفته‌ها در بازار، ارزهای تصادفی از همان جهان، میانگین ۲۰۰ قرعه): هم بازده مرکب و هم شارپ بیشتر.",
}


def wide_rule(train_events: list) -> dict:
    """همان یادگیری مکانیکی ideas14، اما با دو ویژگی برتر تا قاعده بیشتر شلیک کند."""
    r = learn_rule(train_events)
    r["picked"] = sorted(FEATURES, key=lambda n: -r["by_feature"][n]["separation"])[:N_PICK_WIDE]
    r["n_features"] = N_PICK_WIDE
    return r


def fires(rule: dict, f: dict) -> bool:
    t = rule["by_feature"]
    return all(bucket(f[n], t[n]["edges"]) == t[n]["best_bucket"] for n in rule["picked"])


def power_check(events: list, rule: dict) -> dict:
    """تعداد برندهٔ مورد انتظار اگر قاعده هیچ اثری نداشت = تعداد سیگنال × نرخ پایه."""
    fired = [e for e in events if fires(rule, e["f"])]
    base = sum(e["win"] for e in events) / len(events) if events else 0.0
    return {"n_fired": len(fired), "base_win_rate": round(base, 5),
            "expected_winners_if_no_effect": round(len(fired) * base, 2),
            "observed_winners": sum(e["win"] for e in fired),
            "testable": len(fired) * base >= MIN_EXPECTED_WINNERS}


def block_ci(events: list, rule: dict, n_iter=2000, seed=61) -> dict | None:
    by_t = {}
    for e in events:
        by_t.setdefault(e["t"], []).append(e)
    dates = list(by_t)
    if len(dates) < 20:
        return None
    rnd, diffs = random.Random(seed), []
    for _ in range(n_iter):
        hw = tot = allw = alln = 0
        for _ in dates:
            for e in by_t[rnd.choice(dates)]:
                alln += 1
                allw += e["win"]
                if fires(rule, e["f"]):
                    tot += 1
                    hw += e["win"]
        if tot and alln:
            diffs.append(hw / tot - allw / alln)
    if len(diffs) < n_iter // 4:
        return None
    diffs.sort()
    fired = [e for e in events if fires(rule, e["f"])]
    base = sum(e["win"] for e in events) / len(events)
    rate = sum(e["win"] for e in fired) / len(fired) if fired else 0.0
    return {"fired_win_rate": round(rate, 4), "base_win_rate": round(base, 4),
            "diff_pct": round((rate - base) * 100, 2),
            "ci95_low": round(diffs[int(.025 * len(diffs))] * 100, 2),
            "ci95_high": round(diffs[int(.975 * len(diffs))] * 100, 2)}


def _week_returns(p: Panel, syms, t_in, t_out, prev, cost=0.0015):
    def ret(s):
        a = p.sym[s]["c"][p.i(s, t_in)]
        j = p.i(s, t_out)
        if j is not None:
            return p.sym[s]["c"][j] / a - 1
        b = p.close_at_or_before(s, t_out)
        return (b / a - 1) if b else -1.0
    w = {s: 1.0 / len(syms) for s in syms} if syms else {}
    turn = sum(abs(w.get(s, 0) - prev.get(s, 0)) for s in set(w) | set(prev))
    g = sum(w[s] * ret(s) for s in w)
    tot = 1 + g
    drift = {s: w[s] * (1 + ret(s)) / tot for s in w} if tot > 0 else {}
    return g - turn * cost, drift


def cash_matched(p: Panel, rule: dict, start_ms: int, end_ms: int, n_shuffle=N_SHUFFLE,
                 seed=62) -> dict:
    """سبد قاعده در برابر محکی که **در همان هفته‌ها و با همان تعداد ارز** در بازار است،
    اما ارزها تصادفی از همان جهان انتخاب می‌شوند. میانگین n_shuffle قرعه."""
    all_t = sorted({t for d in p.sym.values() for t in d["t"]})
    mondays = [t for t in all_t if start_ms <= t <= end_ms - 8 * DAY_MS and is_monday(t)]
    rnd = random.Random(seed)
    live, port, prev_p = {}, [], {}
    rnd_states = [{"live": {}, "prev": {}, "rets": []} for _ in range(n_shuffle)]
    weeks_in_market = 0
    for k in range(len(mondays) - 1):
        t, t_in, t_out = mondays[k], mondays[k] + DAY_MS, mondays[k + 1] + DAY_MS
        elig, signal = [], []
        for s in p.sym:
            f = features(p, s, t)
            if f is None or any(v is None for v in f.values()) or p.i(s, t_in) is None:
                continue
            elig.append(s)
            if fires(rule, f):
                signal.append(s)
        if len(elig) < 20:
            continue
        for s in signal:
            live[s] = k
        live = {s: kk for s, kk in live.items() if k - kk < HOLD_WEEKS}
        held = [s for s in live if p.i(s, t_in) is not None]
        if held:
            weeks_in_market += 1
        r, prev_p = _week_returns(p, held, t_in, t_out, prev_p)
        port.append(r)
        n_new, n_hold = len(signal), len(held)
        for st in rnd_states:
            for s in rnd.sample(elig, min(n_new, len(elig))):
                st["live"][s] = k
            st["live"] = {s: kk for s, kk in st["live"].items() if k - kk < HOLD_WEEKS}
            rh = [s for s in st["live"] if p.i(s, t_in) is not None][:max(n_hold, 1)] if st["live"] else []
            rr, st["prev"] = _week_returns(p, rh, t_in, t_out, st["prev"])
            st["rets"].append(rr)
    ps = curve_stats(port)
    stats = [curve_stats(st["rets"]) for st in rnd_states]
    stats = [x for x in stats if x.get("sharpe") is not None]
    if not stats:
        return {"portfolio": ps, "benchmark": {}, "weeks": len(port), "verdict": "INSUFFICIENT_DATA"}
    def med(key):
        xs = sorted(x[key] for x in stats)
        return xs[len(xs) // 2]
    bench = {"total_return_pct": round(med("total_return_pct"), 1),
             "max_drawdown_pct": round(med("max_drawdown_pct"), 1),
             "sharpe": round(med("sharpe"), 2), "n_draws": len(stats)}
    beat_sharpe = sum(1 for x in stats if ps.get("sharpe", -9) > x["sharpe"]) / len(stats)
    beat_ret = sum(1 for x in stats if ps.get("total_return_pct", -1e9) > x["total_return_pct"]) / len(stats)
    ok = bool(ps.get("sharpe") is not None and ps["sharpe"] > bench["sharpe"]
              and ps.get("total_return_pct", -1e9) > bench["total_return_pct"])
    return {"portfolio": ps, "benchmark_median_random": bench, "weeks": len(port),
            "weeks_in_market": weeks_in_market,
            "pct_random_draws_beaten_sharpe": round(beat_sharpe * 100, 1),
            "pct_random_draws_beaten_return": round(beat_ret * 100, 1),
            "verdict": "SUPPORTED_IN_TEST_RANGE" if ok else "FALSIFIED"}


def run_ideas16(daily: dict, train_start: int, train_end: int, test_start: int, test_end: int) -> dict:
    p = Panel(daily)
    train = collect(p, train_start, train_end)
    rule = wide_rule(train)
    test = collect(p, test_start, test_end)
    pw = power_check(test, rule)
    ci = block_ci(test, rule)
    if not pw["testable"]:
        z61 = "UNTESTABLE_LOW_POWER"
    elif ci and ci["ci95_low"] > 0:
        z61 = "SUPPORTED_IN_TEST_RANGE"
    else:
        z61 = "FALSIFIED"
    cm = cash_matched(p, rule, test_start, test_end)
    return {"rule": rule, "power": pw, "test": ci, "cash_matched": cm,
            "train_power_info": power_check(train, rule),
            "n_test_events": len(test),
            "verdict": {"H-MARI-Z-061": z61, "H-MARI-Z-062": cm["verdict"]}}
