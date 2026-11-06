# -*- coding: utf-8 -*-
"""ابزار مشترک آزمون دو-رژیمی با محک هم‌نقد. فقط تمرینی.

درس شمارهٔ ۹ دفتر پژوهش (۲۰۲۶-۱۱-۰۵): «شارپ بهتر همراه با بازده بدتر» نشانهٔ
«کمتر در بازار بودن» است، نه مهارت انتخاب. در هر ۸ روش انتخاب ارز همین امضا دیده شد:
در بازار نزولی خوب و در بازار صعودی فاجعه.

پس از این، هر فرضیهٔ انتخاب ارز باید **جداگانه در بازار صعودی و نزولی** سنجیده شود،
و محک آن باید **به همان اندازه در بازار باشد** (هم‌نقد).

رژیم به‌صورت مکانیکی تعریف می‌شود: هفته‌ای «صعودی» است که در تاریخ سیگنال،
بستهٔ BTC بالای میانگین ۱۵۰ روزهٔ خودش باشد؛ وگرنه «نزولی». هیچ اختیاری در کار نیست.
"""
from __future__ import annotations

import random

from .ideas10 import Panel, curve_stats, is_monday

DAY_MS = 86_400_000
REGIME_SMA = 150
N_DRAWS = 200
BEAT_FRAC = 95.0
MIN_WEEKS_PER_REGIME = 30


def regime_of(p: Panel, t: int, n: int = REGIME_SMA, gate: str = "BTCUSDT") -> str | None:
    i = p.i(gate, t)
    if i is None:
        return None
    m = p.sma(gate, i, n)
    if m is None:
        return None
    return "bull" if p.sym[gate]["c"][i] > m else "bear"


def _ret(p: Panel, s: str, t_in: int, t_out: int) -> float:
    a = p.sym[s]["c"][p.i(s, t_in)]
    j = p.i(s, t_out)
    if j is not None:
        return p.sym[s]["c"][j] / a - 1
    b = p.close_at_or_before(s, t_out)
    return (b / a - 1) if b else -1.0


def _step(p: Panel, syms, t_in, t_out, prev, cost=0.0015):
    w = {s: 1.0 / len(syms) for s in syms} if syms else {}
    turn = sum(abs(w.get(s, 0) - prev.get(s, 0)) for s in set(w) | set(prev))
    rs = {s: _ret(p, s, t_in, t_out) for s in w}
    g = sum(w[s] * rs[s] for s in w)
    tot = 1 + g
    drift = {s: w[s] * (1 + rs[s]) / tot for s in w} if tot > 0 else {}
    return g - turn * cost, drift


def run_two_regime(p: Panel, start_ms: int, end_ms: int, select_fn, hold_weeks: int,
                   n_draws: int = N_DRAWS, seed: int = 90, cost: float = 0.0015) -> dict:
    """select_fn(p, t) → (فهرست واجدان شرایط، فهرست انتخاب‌شده‌ها) با دادهٔ تا بستهٔ t.

    سبد و n_draws سبد تصادفیِ هم‌نقد هم‌زمان ساخته می‌شوند؛ سپس بازده هفتگی هر کدام
    به دو رژیم تقسیم و جدا سنجیده می‌شود.
    """
    all_t = sorted({t for d in p.sym.values() for t in d["t"]})
    mondays = [t for t in all_t if start_ms <= t <= end_ms - 8 * DAY_MS and is_monday(t)]
    rnd = random.Random(seed)
    live, prev_p = {}, {}
    draws = [{"live": {}, "prev": {}, "rets": []} for _ in range(n_draws)]
    weeks, regimes, port = [], [], []
    in_market = {"bull": 0, "bear": 0}
    for k in range(len(mondays) - 1):
        t, t_in, t_out = mondays[k], mondays[k] + DAY_MS, mondays[k + 1] + DAY_MS
        reg = regime_of(p, t)
        if reg is None:
            continue
        elig, picked = select_fn(p, t)
        elig = [s for s in elig if p.i(s, t_in) is not None]
        if len(elig) < 20:
            continue
        for s in picked:
            live[s] = k
        live = {s: kk for s, kk in live.items() if k - kk < hold_weeks}
        held = [s for s in live if p.i(s, t_in) is not None]
        if held:
            in_market[reg] += 1
        r, prev_p = _step(p, held, t_in, t_out, prev_p, cost)
        port.append(r)
        weeks.append(t)
        regimes.append(reg)
        n_new, n_hold = len(picked), len(held)
        for st in draws:
            for s in rnd.sample(elig, min(n_new, len(elig))):
                st["live"][s] = k
            st["live"] = {s: kk for s, kk in st["live"].items() if k - kk < hold_weeks}
            rh = [s for s in st["live"] if p.i(s, t_in) is not None][:max(n_hold, 1)] if st["live"] else []
            rr, st["prev"] = _step(p, rh, t_in, t_out, st["prev"], cost)
            st["rets"].append(rr)
    out = {"weeks_total": len(port), "weeks_in_market": in_market}
    for reg in ("bull", "bear", "all"):
        idx = [i for i, g in enumerate(regimes) if reg == "all" or g == reg]
        ps = curve_stats([port[i] for i in idx])
        draw_stats = [curve_stats([st["rets"][i] for i in idx]) for st in draws]
        draw_stats = [x for x in draw_stats if x.get("sharpe") is not None]
        if len(idx) < MIN_WEEKS_PER_REGIME or not draw_stats or ps.get("sharpe") is None:
            out[reg] = {"weeks": len(idx), "portfolio": ps, "verdict": "INSUFFICIENT_DATA"}
            continue
        def med(key):
            xs = sorted(x[key] for x in draw_stats)
            return xs[len(xs) // 2]
        beat_s = sum(1 for x in draw_stats if ps["sharpe"] > x["sharpe"]) / len(draw_stats) * 100
        beat_r = sum(1 for x in draw_stats
                     if ps.get("total_return_pct", -1e9) > x["total_return_pct"]) / len(draw_stats) * 100
        out[reg] = {"weeks": len(idx), "portfolio": ps,
                    "benchmark_median_random": {"total_return_pct": round(med("total_return_pct"), 1),
                                                "max_drawdown_pct": round(med("max_drawdown_pct"), 1),
                                                "sharpe": round(med("sharpe"), 2),
                                                "n_draws": len(draw_stats)},
                    "pct_draws_beaten_sharpe": round(beat_s, 1),
                    "pct_draws_beaten_return": round(beat_r, 1),
                    "verdict": ("SUPPORTED_IN_TEST_RANGE"
                                if beat_s >= BEAT_FRAC and beat_r >= BEAT_FRAC else "FALSIFIED")}
    return out


def overall_verdict(res: dict) -> str:
    """قبولی فقط وقتی که در **هر دو** رژیم از ≥۹۵٪ قرعه‌ها بهتر باشد."""
    vs = [res.get(r, {}).get("verdict") for r in ("bull", "bear")]
    if any(v == "INSUFFICIENT_DATA" for v in vs):
        return "INSUFFICIENT_DATA"
    return "SUPPORTED_IN_TEST_RANGE" if all(v == "SUPPORTED_IN_TEST_RANGE" for v in vs) else "FALSIFIED"
