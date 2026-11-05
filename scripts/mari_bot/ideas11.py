# -*- coding: utf-8 -*-
"""ideas11 — ثبت پیشاپیش در RESEARCH_LOG (2026-11-05T17:40Z). فقط تمرینی، فقط خرید.

درس ideas10 اعمال شده: شرط قبول روی **بازده مرکب و شارپ** است، نه میانگین سادهٔ هفتگی.

H-MARI-G-053: آیا انتخاب ارز روی دروازهٔ BTC چیزی اضافه می‌کند؟ (سبد دروازه‌دار در برابر وزن برابر دروازه‌دار)
H-MARI-X-054: MAX مومنتوم (Li، Urquhart، Wang، Zhang؛ IRFA 2021) — بیشترین بازده روزانهٔ ۳۰ روز گذشته.
"""
from __future__ import annotations

from .ideas10 import (Panel, btc_gate, curve_stats, is_monday, run_xs, score_high52,
                      universe)

DAY_MS = 86_400_000
MAX_LOOKBACK = 30
DECILE = 0.1
QUINTILE = 0.2

IDEA11_HYPOTHESES = {
    "H-MARI-G-053": "انتخاب ارز روی دروازهٔ BTC: سبد پنجک بالای سقف ۵۲ هفته با دروازهٔ BTC، هم بازده مرکب و هم شارپ بیشتر از وزن برابر با همان دروازه، در کل دوره و در هر دو نیمه.",
    "H-MARI-X-054": "MAX مومنتوم (دهک بالای بیشترین بازده روزانهٔ ۳۰ روز گذشته): هم بازده مرکب و هم شارپ بیشتر از وزن برابر، در کل دوره و در هر دو نیمه.",
}


def score_max(p: Panel, syms, t):
    """بیشترین بازده روزانه در ۳۰ روز گذشته (تا بستهٔ دوشنبه)."""
    out = {}
    for s in syms:
        i = p.i(s, t)
        c = p.sym[s]["c"]
        lo = max(1, i - MAX_LOOKBACK + 1)
        rs = [c[j] / c[j - 1] - 1 for j in range(lo, i + 1) if c[j - 1] > 0]
        if rs:
            out[s] = max(rs)
    return out


def halves(rs: list) -> dict:
    h = len(rs) // 2
    return {"full": curve_stats(rs), "first_half": curve_stats(rs[:h]), "second_half": curve_stats(rs[h:])}


def _beats(a: dict, b: dict) -> bool:
    sa, sb = a.get("sharpe"), b.get("sharpe")
    if sa is None or sb is None:
        return False
    return bool(sa > sb and a.get("total_return_pct", -1e9) > b.get("total_return_pct", 1e9))


def compare(weeks: list) -> dict:
    top, ew = halves([w["top"] for w in weeks]), halves([w["ew"] for w in weeks])
    ok = all(_beats(top[k], ew[k]) for k in ("full", "first_half", "second_half"))
    return {"portfolio": top, "benchmark": ew, "weeks": len(weeks),
            "verdict": "SUPPORTED_IN_TEST_RANGE" if ok else "FALSIFIED"}


def run_ideas11(daily: dict, start_ms: int, end_ms: int) -> dict:
    p = Panel(daily)
    all_t = sorted({t for d in p.sym.values() for t in d["t"]})
    mondays = [t for t in all_t if start_ms <= t <= end_ms - 8 * DAY_MS and is_monday(t)]
    gate = btc_gate(p)

    g_weeks, _ = run_xs(p, mondays, score_high52, gate=gate, frac=QUINTILE)
    # محک G-053: وزن برابر همان جهان با همان دروازه (ستون ew در run_xs بدون دروازه است)
    g_cmp = compare(_gate_benchmark(p, mondays, g_weeks, gate))

    x_weeks, _ = run_xs(p, mondays, score_max, frac=DECILE)
    x_cmp = compare(x_weeks)
    x_low, _ = run_xs(p, mondays, lambda pp, ss, tt: {s: -v for s, v in score_max(pp, ss, tt).items()},
                      frac=DECILE)
    x_cmp["low_max_decile_info"] = halves([w["top"] for w in x_low])["full"]

    return {"by_hypothesis": {"H-MARI-G-053": g_cmp, "H-MARI-X-054": x_cmp},
            "verdict": {"H-MARI-G-053": g_cmp["verdict"], "H-MARI-X-054": x_cmp["verdict"]},
            "mondays": len(mondays)}


def _gate_benchmark(p: Panel, mondays, gated_top_weeks, gate):
    """محک درست برای G-053: وزن برابر همهٔ ارزهای جهان، با همان دروازهٔ BTC.
    با نمرهٔ ثابت و frac=1.0 ساخته می‌شود تا کل جهان انتخاب شود."""
    flat = lambda pp, ss, tt: {s: 0.0 for s in ss}  # noqa: E731
    ew_weeks, _ = run_xs(p, mondays, flat, gate=gate, frac=1.0)
    ew_by_t = {w["t"]: w["top"] for w in ew_weeks}
    out = []
    for w in gated_top_weeks:
        if w["t"] in ew_by_t:
            out.append({"t": w["t"], "top": w["top"], "ew": ew_by_t[w["t"]], "n": w["n"]})
    return out
