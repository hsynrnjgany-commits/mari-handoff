# -*- coding: utf-8 -*-
"""ideas14 — ثبت پیشاپیش در RESEARCH_LOG (2026-11-05T20:05Z). فقط تمرینی.

ایدهٔ صاحب پروژه: «فرمول مشترک ارزهای صعودی».
روش درست: مقایسهٔ برندگان با **همهٔ** ارزها (نه نگاه کردن فقط به برندگان).

H-MARI-Z-058: الگو وجود دارد — قاعدهٔ ساخته‌شده روی دادهٔ آموزش، در دورهٔ آزمونِ دیده‌نشده
              نرخ برنده‌شدن بالاتری از نرخ پایه دارد (CI95 بالای صفر، بوت‌استرپ بلوکی روی تاریخ‌ها).
H-MARI-Z-059: الگو سود می‌دهد — سبد وزن-برابر ارزهای سیگنال‌دار در دورهٔ آزمون، هم بازده مرکب و
              هم شارپ بیشتر از وزن برابر کل جهان.

جداکردن این دو، درس P-019 است: الگوی واقعی به‌معنی راهبرد سودده نیست.
"""
from __future__ import annotations

import random

from .ideas10 import Panel, curve_stats, is_monday

DAY_MS = 86_400_000
HOLD_DAYS = 91                 # ۱۳ هفته
WIN_THRESHOLD = 2.0            # برنده = بازده ۹۱ روزهٔ بعدی ≥ +۲۰۰٪
MIN_AGE = 120
MIN_QV = 50_000.0              # نقدشوندگی کمینه (میانگین ۳۰ روزهٔ دلاری)
N_QUINTILES = 5
N_PICK = 3                     # سه ویژگی با بیشترین جداسازی روی دادهٔ آموزش
HOLD_WEEKS = 13

IDEA14_HYPOTHESES = {
    "H-MARI-Z-058": "قاعدهٔ «فرمول ارزهای صعودی» که مکانیکی از دادهٔ آموزش (تا ۲۰۲۳-۰۵) ساخته شد، در دورهٔ آزمونِ دیده‌نشده (از ۲۰۲۳-۰۶) نرخ برنده‌شدن بالاتر از نرخ پایه دارد؛ CI95 اختلاف بالای صفر.",
    "H-MARI-Z-059": "سبد وزن-برابر ارزهای سیگنال‌دار همان قاعده در دورهٔ آزمون: هم بازده مرکب و هم شارپ بیشتر از وزن برابر کل جهان.",
}

FEATURES = ("age_days", "ret_30d", "ret_90d", "vol_30d", "dd_from_ath", "qv_trend",
            "tightness_30d", "log_qv_30d", "px_vs_sma150")


def _vol(c, i, n=30):
    if i < n:
        return None
    rs = [c[j] / c[j - 1] - 1 for j in range(i - n + 1, i + 1) if c[j - 1] > 0]
    if len(rs) < n // 2:
        return None
    m = sum(rs) / len(rs)
    return (sum((r - m) ** 2 for r in rs) / max(1, len(rs) - 1)) ** 0.5


def features(p: Panel, s: str, t: int) -> dict | None:
    """فقط دادهٔ تا بستهٔ روز t. None یعنی واجد شرایط نیست."""
    i = p.i(s, t)
    if i is None or i < MIN_AGE:
        return None
    c, h = p.sym[s]["c"], p.sym[s]["h"]
    if c[i] <= 0:
        return None
    qv30 = p.avg_qv(s, i, 30)
    if qv30 < MIN_QV:
        return None
    v = _vol(c, i)
    if v is None or v <= 0:
        return None
    ath = max(h[: i + 1])
    hi30, lo30 = max(h[i - 29: i + 1]), min(c[i - 29: i + 1])
    sma150 = p.sma(s, i, 150)
    qv7 = p.avg_qv(s, i, 7)
    import math
    return {"age_days": float(i), "ret_30d": c[i] / c[i - 30] - 1 if c[i - 30] > 0 else None,
            "ret_90d": c[i] / c[i - 90] - 1 if i >= 90 and c[i - 90] > 0 else None,
            "vol_30d": v, "dd_from_ath": c[i] / ath - 1 if ath > 0 else None,
            "qv_trend": qv7 / qv30 if qv30 > 0 else None,
            "tightness_30d": (hi30 - lo30) / c[i] if c[i] > 0 else None,
            "log_qv_30d": math.log(qv30), "px_vs_sma150": c[i] / sma150 - 1 if sma150 else None}


def forward_return(p: Panel, s: str, t: int, hold=HOLD_DAYS) -> float | None:
    i = p.i(s, t)
    if i is None:
        return None
    c = p.sym[s]["c"]
    a = c[i]
    j = p.i(s, t + hold * DAY_MS)
    if j is not None:
        return c[j] / a - 1
    last_t = p.sym[s]["ts"][-1]
    if last_t < t + hold * DAY_MS:          # حذف‌شده: با آخرین قیمت موجود بسته می‌شود
        return c[-1] / a - 1
    b = p.close_at_or_before(s, t + hold * DAY_MS)
    return b / a - 1 if b else None


def collect(p: Panel, start_ms: int, end_ms: int, need_forward=True) -> list:
    """رویدادها: هر دوشنبه، هر ارز واجد شرایط → (تاریخ، نماد، ویژگی‌ها، بازده پیش‌رو)."""
    all_t = sorted({t for d in p.sym.values() for t in d["t"]})
    cut = end_ms - (HOLD_DAYS + 1) * DAY_MS if need_forward else end_ms
    out = []
    for t in all_t:
        if not (start_ms <= t <= cut) or not is_monday(t):
            continue
        for s in p.sym:
            f = features(p, s, t)
            if f is None or any(v is None for v in f.values()):
                continue
            fr = forward_return(p, s, t)
            if fr is None:
                continue
            out.append({"t": t, "sym": s, "f": f, "fwd": fr, "win": fr >= WIN_THRESHOLD})
    return out


def quintile_edges(vals: list, k=N_QUINTILES) -> list:
    xs = sorted(vals)
    return [xs[int(len(xs) * j / k)] for j in range(1, k)]


def bucket(x: float, edges: list) -> int:
    b = 0
    for e in edges:
        if x >= e:
            b += 1
    return b


def learn_rule(events: list) -> dict:
    """مکانیکی و بدون چشم: برای هر ویژگی، پنجک با بیشترین نرخ برنده پیدا می‌شود؛
    سه ویژگی با بیشترین جداسازی (نرخ بهترین پنجک منهای نرخ کل) انتخاب می‌شوند."""
    base = sum(e["win"] for e in events) / max(1, len(events))
    table = {}
    for name in FEATURES:
        edges = quintile_edges([e["f"][name] for e in events])
        rates = []
        for b in range(N_QUINTILES):
            grp = [e for e in events if bucket(e["f"][name], edges) == b]
            rates.append({"n": len(grp), "win_rate": (sum(x["win"] for x in grp) / len(grp)) if grp else 0.0})
        best = max(range(N_QUINTILES), key=lambda b: rates[b]["win_rate"] if rates[b]["n"] >= 200 else -1)
        table[name] = {"edges": edges, "rates": rates, "best_bucket": best,
                       "separation": round(rates[best]["win_rate"] - base, 4)}
    picked = sorted(FEATURES, key=lambda n: -table[n]["separation"])[:N_PICK]
    return {"base_win_rate": round(base, 4), "by_feature": table, "picked": list(picked),
            "n_train_events": len(events)}


def fires(rule: dict, f: dict) -> bool:
    t = rule["by_feature"]
    return all(bucket(f[n], t[n]["edges"]) == t[n]["best_bucket"] for n in rule["picked"])


def _block_ci(events: list, rule: dict, n_iter=2000, seed=58) -> dict | None:
    """بوت‌استرپ بلوکی روی تاریخ‌ها (پنجره‌های ۹۱ روزه هم‌پوشانی دارند)."""
    by_t = {}
    for e in events:
        by_t.setdefault(e["t"], []).append(e)
    dates = list(by_t)
    if len(dates) < 20:
        return None
    rnd = random.Random(seed)
    diffs = []
    for _ in range(n_iter):
        hit = tot = hw = 0
        allw = alln = 0
        for _ in dates:
            for e in by_t[rnd.choice(dates)]:
                alln += 1
                allw += e["win"]
                if fires(rule, e["f"]):
                    tot += 1
                    hw += e["win"]
        if tot >= 20 and alln:
            diffs.append(hw / tot - allw / alln)
    if len(diffs) < n_iter // 4:
        return None
    diffs.sort()
    fired = [e for e in events if fires(rule, e["f"])]
    base = sum(e["win"] for e in events) / len(events)
    return {"n_fired": len(fired), "fired_win_rate": round(sum(e["win"] for e in fired) / len(fired), 4) if fired else None,
            "base_win_rate": round(base, 4),
            "diff_pct": round((sum(e["win"] for e in fired) / len(fired) - base) * 100, 2) if fired else None,
            "ci95_low": round(diffs[int(.025 * len(diffs))] * 100, 2),
            "ci95_high": round(diffs[int(.975 * len(diffs))] * 100, 2)}


def tradeable(p: Panel, rule: dict, start_ms: int, end_ms: int, cost=0.0015) -> dict:
    """هر دوشنبه: سبد = وزن برابر ارزهایی که در ۱۳ هفتهٔ گذشته سیگنال داده‌اند. محک: وزن برابر کل جهان."""
    all_t = sorted({t for d in p.sym.values() for t in d["t"]})
    mondays = [t for t in all_t if start_ms <= t <= end_ms - 8 * DAY_MS and is_monday(t)]
    live, port, bench, prev_p, prev_b = {}, [], [], {}, {}
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
        for s in signal:
            live[s] = k
        live = {s: kk for s, kk in live.items() if k - kk < HOLD_WEEKS and s in p.sym}
        held = [s for s in live if p.i(s, t_in) is not None]
        if len(elig) < 20:
            continue

        def ret(s):
            a = p.sym[s]["c"][p.i(s, t_in)]
            j = p.i(s, t_out)
            if j is not None:
                return p.sym[s]["c"][j] / a - 1
            b = p.close_at_or_before(s, t_out)
            return (b / a - 1) if b else -1.0

        def step(syms, prev):
            w = {s: 1.0 / len(syms) for s in syms} if syms else {}
            turn = sum(abs(w.get(s, 0) - prev.get(s, 0)) for s in set(w) | set(prev))
            g = sum(w[s] * ret(s) for s in w)
            tot = 1 + g
            drift = {s: w[s] * (1 + ret(s)) / tot for s in w} if tot > 0 else {}
            return g - turn * cost, drift

        rp, prev_p = step(held, prev_p)
        rb, prev_b = step(elig, prev_b)
        port.append(rp)
        bench.append(rb)
    ps, bs = curve_stats(port), curve_stats(bench)
    ok = bool(ps.get("sharpe") is not None and bs.get("sharpe") is not None
              and ps["sharpe"] > bs["sharpe"]
              and ps.get("total_return_pct", -1e9) > bs.get("total_return_pct", 1e9))
    return {"portfolio": ps, "benchmark": bs, "weeks": len(port),
            "verdict": "SUPPORTED_IN_TEST_RANGE" if ok else "FALSIFIED"}


def run_ideas14(daily: dict, train_start: int, train_end: int, test_start: int, test_end: int) -> dict:
    p = Panel(daily)
    train = collect(p, train_start, train_end)
    rule = learn_rule(train)
    test = collect(p, test_start, test_end)
    ci = _block_ci(test, rule)
    z58 = "FALSIFIED"
    if ci and ci["ci95_low"] > 0 and ci["n_fired"] >= 20:
        z58 = "SUPPORTED_IN_TEST_RANGE"
    elif ci is None or (ci and ci["n_fired"] < 20):
        z58 = "INSUFFICIENT_DATA"
    tr = tradeable(p, rule, test_start, test_end)
    train_ci = _block_ci(train, rule, n_iter=500, seed=1)
    return {"rule": rule, "train_in_sample_info": train_ci, "test": ci, "tradeable": tr,
            "n_test_events": len(test),
            "verdict": {"H-MARI-Z-058": z58, "H-MARI-Z-059": tr["verdict"]}}
