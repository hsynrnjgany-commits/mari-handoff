# -*- coding: utf-8 -*-
"""ideas10 — ثبت پیشاپیش در RESEARCH_LOG (2026-11-05T17:22Z). فقط تمرینی، فقط خرید (بدون فروش استقراضی).

دو ایده از مقاله‌های کریپتو که یک دستیار پژوهشی پیدا کرد:
H-MARI-C-051: عامل روند کریپتو (Fieberg و همکاران، JFQA 2024)، نسخهٔ ساده‌شده.
H-MARI-N-052: نزدیکی به سقف ۵۲ هفته (Jia، Simkins، Yan و همکاران؛ Quantpedia).

هر دو: هر دوشنبه، ۱۰۰ ارز پرحجم همان روز (شامل ارزهایی که بعداً حذف شدند)، خرید پنجک بالا با وزن برابر.
محک: وزن برابر همهٔ همان ۱۰۰ ارز (همان هزینه‌ها). سنجه: بازده هفتگی اضافه = سبد − محک.
"""
from __future__ import annotations

import random

DAY_MS = 86_400_000
TOP_N = 100
QUINTILE = 0.2
MIN_HISTORY = 365
VOL_DAYS = 30
CTREND_N = (3, 5, 10, 20, 50, 100, 200)
COST = 0.0015                                  # کارمزد ۰٫۱٪ + لغزش ۰٫۰۵٪ در هر سمت

IDEA10_HYPOTHESES = {
    "H-MARI-C-051": "عامل روند کریپتو (میانگین رتبهٔ قیمت/میانگین ۳ تا ۲۰۰ روزه، پنجک بالا از ۱۰۰ ارز پرحجم): بازده هفتگی اضافه بر وزن برابر، CI95 بالای صفر و مثبت در هر دو نیمهٔ دوره.",
    "H-MARI-N-052": "نزدیکی به سقف ۵۲ هفته (پنجک بالا از ۱۰۰ ارز پرحجم): بازده هفتگی اضافه بر وزن برابر، CI95 بالای صفر و مثبت در هر دو نیمهٔ دوره.",
}


def is_monday(t: int) -> bool:
    return (t // DAY_MS + 3) % 7 == 0


class Panel:
    """دادهٔ روزانهٔ همهٔ نمادها با دسترسی سریع؛ فقط گذشته تا روز داده‌شده خوانده می‌شود."""

    def __init__(self, daily: dict):
        self.sym = {}
        for s, bars in daily.items():
            if not bars:
                continue
            c = [b["c"] for b in bars]
            cs = [0.0]
            for x in c:
                cs.append(cs[-1] + x)
            qv = [b.get("qv") or 0.0 for b in bars]
            qs = [0.0]
            for x in qv:
                qs.append(qs[-1] + x)
            self.sym[s] = {"t": {b["t"]: i for i, b in enumerate(bars)}, "c": c, "h": [b["h"] for b in bars],
                           "cs": cs, "qs": qs, "ts": [b["t"] for b in bars]}

    def i(self, s, t):
        return self.sym[s]["t"].get(t)

    def sma(self, s, i, n):
        d = self.sym[s]["cs"]
        return (d[i + 1] - d[i + 1 - n]) / n if i >= n - 1 else None

    def avg_qv(self, s, i, n=VOL_DAYS):
        d = self.sym[s]["qs"]
        return (d[i + 1] - d[max(0, i + 1 - n)]) / min(n, i + 1)

    def close_at_or_before(self, s, t):
        """آخرین بسته تا زمان t (برای ارزی که وسط هفته حذف شد)."""
        ts = self.sym[s]["ts"]
        lo, hi = 0, len(ts)
        while lo < hi:
            m = (lo + hi) // 2
            if ts[m] <= t:
                lo = m + 1
            else:
                hi = m
        return self.sym[s]["c"][lo - 1] if lo else None


def universe(p: Panel, t: int, top=TOP_N, min_hist=MIN_HISTORY):
    rows = []
    for s, d in p.sym.items():
        i = d["t"].get(t)
        if i is None or i < min_hist - 1:
            continue
        rows.append((p.avg_qv(s, i), s))
    rows.sort(reverse=True)
    return [s for _, s in rows[:top]]


def _pct_ranks(vals: dict) -> dict:
    order = sorted(vals, key=lambda s: vals[s])
    n = len(order)
    return {s: (k + 0.5) / n for k, s in enumerate(order)}


def score_ctrend(p: Panel, syms, t):
    per_n = []
    for n in CTREND_N:
        raw = {}
        for s in syms:
            i = p.i(s, t)
            m = p.sma(s, i, n)
            if m:
                raw[s] = p.sym[s]["c"][i] / m
        if raw:
            per_n.append(_pct_ranks(raw))
    out = {}
    for s in syms:
        r = [x[s] for x in per_n if s in x]
        if len(r) == len(per_n) and r:
            out[s] = sum(r) / len(r)
    return out


def score_high52(p: Panel, syms, t):
    out = {}
    for s in syms:
        i = p.i(s, t)
        h = p.sym[s]["h"][max(0, i - 364): i + 1]
        mx = max(h) if h else 0
        if mx > 0:
            out[s] = p.sym[s]["c"][i] / mx
    return out


def run_xs(p: Panel, mondays: list, score_fn, haircut=0.0, gate=None):
    """سیگنال با بستهٔ دوشنبه، اجرا با بستهٔ سه‌شنبه، نگه‌داری تا بستهٔ سه‌شنبهٔ بعد.
    gate(t) → False یعنی آن هفته نقد (فقط برای نسخهٔ اطلاعی با دروازهٔ BTC)."""
    weeks, prev_top, prev_ew = [], {}, {}
    delisted = 0
    for k in range(len(mondays) - 1):
        t = mondays[k]
        t_in, t_out = t + DAY_MS, mondays[k + 1] + DAY_MS
        syms = [s for s in universe(p, t) if p.i(s, t_in) is not None]
        if len(syms) < 20:
            continue
        sc = score_fn(p, syms, t)
        ranked = sorted(sc, key=lambda s: -sc[s])
        top = ranked[:max(1, int(len(ranked) * QUINTILE))]
        on = gate(t) if gate else True
        w_top = {s: 1.0 / len(top) for s in top} if on else {}
        w_ew = {s: 1.0 / len(syms) for s in syms}

        def ret(s):
            nonlocal delisted
            a = p.sym[s]["c"][p.i(s, t_in)]
            j = p.i(s, t_out)
            if j is not None:
                return p.sym[s]["c"][j] / a - 1
            delisted += 1
            b = p.close_at_or_before(s, t_out) or a
            return (b * (1 - haircut)) / a - 1

        rs = {s: ret(s) for s in set(w_top) | set(w_ew)}

        def port(w, prev):
            turn = sum(abs(w.get(s, 0) - prev.get(s, 0)) for s in set(w) | set(prev))
            gross = sum(w[s] * rs[s] for s in w)
            # وزن‌های پس از حرکت هفته، برای محاسبهٔ گردش هفتهٔ بعد
            tot = 1 + gross
            drift = {s: w[s] * (1 + rs[s]) / tot for s in w} if tot > 0 else {}
            return gross - turn * COST, drift

        r_top, prev_top = port(w_top, prev_top)
        r_ew, prev_ew = port(w_ew, prev_ew)
        weeks.append({"t": t, "top": r_top, "ew": r_ew, "n": len(syms)})
    return weeks, delisted


def _ci_mean(xs, n_iter=4000, seed=51):
    if len(xs) < 20:
        return None
    rnd = random.Random(seed)
    ms = sorted(sum(rnd.choice(xs) for _ in xs) / len(xs) for _ in range(n_iter))
    m = sum(xs) / len(xs)
    return {"mean_pct": round(m * 100, 3), "ci95_low": round(ms[int(.025 * n_iter)] * 100, 3),
            "ci95_high": round(ms[int(.975 * n_iter)] * 100, 3), "n_weeks": len(xs)}


def curve_stats(rs):
    eq, peak, dd = 1.0, 1.0, 0.0
    for r in rs:
        eq *= 1 + r
        peak = max(peak, eq)
        dd = max(dd, 1 - eq / peak)
    if len(rs) < 2:
        return {}
    m = sum(rs) / len(rs)
    sd = (sum((r - m) ** 2 for r in rs) / (len(rs) - 1)) ** 0.5
    return {"total_return_pct": round((eq - 1) * 100, 1), "max_drawdown_pct": round(dd * 100, 1),
            "sharpe": round(m / sd * 52 ** 0.5, 2) if sd else None, "weeks": len(rs)}


def evaluate(weeks):
    ex = [w["top"] - w["ew"] for w in weeks]
    half = len(ex) // 2
    h1, h2 = _ci_mean(ex[:half]), _ci_mean(ex[half:])
    allc = _ci_mean(ex)
    ok = bool(allc and allc["ci95_low"] > 0 and h1 and h2 and h1["mean_pct"] > 0 and h2["mean_pct"] > 0)
    return {"excess_all": allc, "excess_first_half": h1, "excess_second_half": h2,
            "top": curve_stats([w["top"] for w in weeks]), "ew": curve_stats([w["ew"] for w in weeks]),
            "avg_universe": round(sum(w["n"] for w in weeks) / max(1, len(weeks)), 1),
            "verdict": "SUPPORTED_IN_TEST_RANGE" if ok else "FALSIFIED"}


def btc_gate(p: Panel, n=150):
    def g(t):
        i = p.i("BTCUSDT", t)
        m = p.sma("BTCUSDT", i, n) if i is not None else None
        return bool(m and p.sym["BTCUSDT"]["c"][i] > m)
    return g


def run_ideas10(daily: dict, start_ms: int, end_ms: int) -> dict:
    p = Panel(daily)
    all_t = sorted({t for d in p.sym.values() for t in d["t"]})
    mondays = [t for t in all_t if start_ms <= t <= end_ms - 8 * DAY_MS and is_monday(t)]
    res, verdict = {}, {}
    for hid, fn in (("H-MARI-C-051", score_ctrend), ("H-MARI-N-052", score_high52)):
        weeks, dl = run_xs(p, mondays, fn)
        ev = evaluate(weeks)
        ev["delisted_exits"] = dl
        weeks50, _ = run_xs(p, mondays, fn, haircut=0.5)
        ev["haircut50_excess_all"] = evaluate(weeks50)["excess_all"]
        gw, _ = run_xs(p, mondays, fn, gate=btc_gate(p))
        ev["btc_gated_info"] = curve_stats([w["top"] for w in gw])
        res[hid], verdict[hid] = ev, ev["verdict"]
    return {"by_hypothesis": res, "verdict": verdict, "mondays": len(mondays)}
