# -*- coding: utf-8 -*-
"""ideas12 — ثبت پیشاپیش در RESEARCH_LOG (2026-11-05T18:00Z). فقط تمرینی، فقط خرید.

H-MARI-G-055: تکرار سرنخ G-053 روی دورهٔ کنار گذاشته‌شده (۲۰۱۷-۰۹ تا ۲۰۲۰-۰۶).
              سنجهٔ از پیش اعلام‌شده: شارپ و بیشترین افت (بازده مرکب مجاز است کمتر باشد).
H-MARI-B-056: بتای نزولی (Dobrynskaya، IRFA 2024) — پنجک بالای بتا به بازار در هفته‌های ضعیف بازار.
"""
from __future__ import annotations

from .ideas10 import Panel, btc_gate, curve_stats, is_monday, run_xs, score_high52
from .ideas11 import _gate_benchmark, halves

DAY_MS = 86_400_000
QUINTILE = 0.2
BETA_WEEKS = 52
MIN_DOWN_WEEKS = 10

IDEA12_HYPOTHESES = {
    "H-MARI-G-055": "تکرار G-053 روی دورهٔ کنار گذاشته‌شدهٔ ۲۰۱۷-۰۹ تا ۲۰۲۰-۰۶: شارپ بیشتر و بیشترین افت کمتر از وزن برابر با همان دروازهٔ BTC، در کل دوره و در هر دو نیمه. بازده مرکب مجاز است کمتر باشد.",
    "H-MARI-B-056": "بتای نزولی (پنجک بالای بتا به بازار وزن-برابر در هفته‌های زیر میانگین بازار، ۵۲ هفتهٔ گذشته): شارپ بیشتر و بیشترین افت کمتر از وزن برابر، در کل دوره و در هر دو نیمه.",
}


def weekly_returns(p: Panel, s, t, n_weeks=BETA_WEEKS):
    """بازده‌های هفتگی (۷ روزه) تا بستهٔ روز t، از قدیم به جدید."""
    i = p.i(s, t)
    if i is None:
        return []
    c = p.sym[s]["c"]
    out = []
    for k in range(n_weeks, 0, -1):
        a, b = i - 7 * k, i - 7 * (k - 1)
        if a < 0 or c[a] <= 0:
            continue
        out.append((k, c[b] / c[a] - 1))
    return out


def downside_beta(coin_rs, mkt_rs, min_down=MIN_DOWN_WEEKS):
    """بتا فقط روی هفته‌هایی که بازار زیر میانگین خودش بوده."""
    if not mkt_rs:
        return None
    mm = sum(mkt_rs.values()) / len(mkt_rs)
    pairs = [(coin_rs[k], mkt_rs[k]) for k in coin_rs if k in mkt_rs and mkt_rs[k] < mm]
    if len(pairs) < min_down:
        return None
    mx = sum(m for _, m in pairs) / len(pairs)
    my = sum(y for y, _ in pairs) / len(pairs)
    var = sum((m - mx) ** 2 for _, m in pairs)
    if var <= 0:
        return None
    cov = sum((y - my) * (m - mx) for y, m in pairs)
    return cov / var


def score_downside_beta(p: Panel, syms, t):
    per = {s: dict(weekly_returns(p, s, t)) for s in syms}
    keys = set()
    for d in per.values():
        keys |= set(d)
    mkt = {}
    for k in keys:
        vals = [d[k] for d in per.values() if k in d]
        if len(vals) >= max(10, len(syms) // 2):
            mkt[k] = sum(vals) / len(vals)
    out = {}
    for s in syms:
        b = downside_beta(per[s], mkt)
        if b is not None:
            out[s] = b
    return out


def _beats_risk(a: dict, b: dict) -> bool:
    sa, sb = a.get("sharpe"), b.get("sharpe")
    if sa is None or sb is None:
        return False
    return bool(sa > sb and a.get("max_drawdown_pct", 100.0) < b.get("max_drawdown_pct", 0.0))


def compare_risk(weeks: list) -> dict:
    top, ew = halves([w["top"] for w in weeks]), halves([w["ew"] for w in weeks])
    ok = all(_beats_risk(top[k], ew[k]) for k in ("full", "first_half", "second_half"))
    return {"portfolio": top, "benchmark": ew, "weeks": len(weeks),
            "verdict": "SUPPORTED_IN_TEST_RANGE" if ok else "FALSIFIED"}


def run_ideas12(daily: dict, g_start: int, g_end: int, b_start: int, b_end: int) -> dict:
    p = Panel(daily)
    all_t = sorted({t for d in p.sym.values() for t in d["t"]})
    gate = btc_gate(p)

    g_mon = [t for t in all_t if g_start <= t <= g_end - 8 * DAY_MS and is_monday(t)]
    g_top, _ = run_xs(p, g_mon, score_high52, gate=gate, frac=QUINTILE)
    g_cmp = compare_risk(_gate_benchmark(p, g_mon, g_top, gate))
    g_cmp["note"] = "period_held_out_from_ideas10_11"

    b_mon = [t for t in all_t if b_start <= t <= b_end - 8 * DAY_MS and is_monday(t)]
    b_weeks, _ = run_xs(p, b_mon, score_downside_beta, frac=QUINTILE)
    b_cmp = compare_risk(b_weeks)
    b_low, _ = run_xs(p, b_mon, lambda pp, ss, tt: {s: -v for s, v in score_downside_beta(pp, ss, tt).items()},
                      frac=QUINTILE)
    b_cmp["low_beta_quintile_info"] = curve_stats([w["top"] for w in b_low])

    return {"by_hypothesis": {"H-MARI-G-055": g_cmp, "H-MARI-B-056": b_cmp},
            "verdict": {"H-MARI-G-055": g_cmp["verdict"], "H-MARI-B-056": b_cmp["verdict"]},
            "weeks": {"G-055": len(g_mon), "B-056": len(b_mon)}}
