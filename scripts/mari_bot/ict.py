# -*- coding: utf-8 -*-
"""آزمون ایدهٔ «شکار نقدینگی» سبک ICT (مایکل هادلستون) — ثبت پیشاپیش، روی BTC و ETH روزانه.

تعریف رویداد روی کندل روزانهٔ بستهٔ t (فقط دادهٔ ≤ t):
  شکار کف (صعودی):  low[t] < low[t-1]  و  close[t] > low[t-1]
  شکار سقف (نزولی): high[t] > high[t-1] و close[t] < high[t-1]

H-MARI-ICT-015 (مطالعهٔ رویداد): میانگین بازده ۵ روز بعد (از بستهٔ t+1 تا t+6، یعنی با یک روز تأخیر اجرا)
  پس از شکار کف > میانگین همهٔ روزها، و پس از شکار سقف < میانگین همهٔ روزها.
  قبول فقط اگر CI95 بوت‌استرپِ اختلاف برای هر دو جهت، روی BTC و ETH هر دو، صفر را دربر نگیرد و جهتش درست باشد.
H-MARI-ICT-016 (استراتژی فقط خرید): پس از شکار کف، خرید در بستهٔ روز بعد؛ خروج در اولین بسته‌ای که
  بالای سقفِ روز قبل از شکار (هدف نقدینگی خرید) باشد، یا زیر کفِ شکار (ابطال)، یا پس از ۵ روز.
  معیار رد: همان معیار C-007 (شارپ و افت در برابر نگه‌داری، CI95 هفتگی > ۰) روی هر دو دارایی.
فقط تمرینی.
"""
from __future__ import annotations

import random

ICT_HYPOTHESES = {
    "H-MARI-ICT-015": "پس از شکار کف، بازده ۵روزه بیشتر از معمول؛ پس از شکار سقف، کمتر از معمول (BTC و ETH).",
    "H-MARI-ICT-016": "خرید پس از شکار کف، هدف سقف دیروز، ابطال زیر کف شکار، حداکثر ۵ روز (BTC و ETH).",
}
HORIZON = 5


def events(bars: list[dict]) -> dict:
    bull, bear = [], []
    for t in range(1, len(bars)):
        p, b = bars[t - 1], bars[t]
        if b["l"] < p["l"] and b["c"] > p["l"]:
            bull.append(t)
        if b["h"] > p["h"] and b["c"] < p["h"]:
            bear.append(t)
    return {"bull": bull, "bear": bear}


def _fwd(bars, t, h=HORIZON):
    """بازده از بستهٔ t+1 (اجرای یک روز دیرتر) تا بستهٔ t+1+h."""
    if t + 1 + h >= len(bars):
        return None
    return bars[t + 1 + h]["c"] / bars[t + 1]["c"] - 1


def _diff_ci(sample, base, n_iter=4000, seed=5):
    if len(sample) < 20 or len(base) < 50:
        return None
    rnd = random.Random(seed)
    diffs = []
    for _ in range(n_iter):
        a = [rnd.choice(sample) for _ in sample]
        b = [rnd.choice(base) for _ in range(len(sample))]
        diffs.append(sum(a) / len(a) - sum(b) / len(b))
    diffs.sort()
    m = sum(sample) / len(sample) - sum(base) / len(base)
    return {"diff_pct": round(m * 100, 3), "ci95_low": round(diffs[int(.025 * n_iter)] * 100, 3),
            "ci95_high": round(diffs[int(.975 * n_iter)] * 100, 3)}


def event_study(bars: list[dict], start_idx: int) -> dict:
    ev = events(bars)
    base = [r for t in range(start_idx, len(bars)) if (r := _fwd(bars, t)) is not None]
    out = {"n_days": len(base), "mean_fwd5_all_pct": round(sum(base) / len(base) * 100, 3) if base else None}
    for k in ("bull", "bear"):
        s = [r for t in ev[k] if t >= start_idx and (r := _fwd(bars, t)) is not None]
        out[k] = {"n": len(s), "mean_fwd5_pct": round(sum(s) / len(s) * 100, 3) if s else None,
                  "hit_rate_pct": round(sum(1 for x in s if (x > 0 if k == "bull" else x < 0)) / len(s) * 100, 1)
                  if s else None,
                  "vs_all": _diff_ci(s, base)}
    return out


def ict_long_fn(sym: str):
    def fn(k, ctx):
        st = ctx["state"]
        c, h, l = ctx["c"][sym], ctx["h"][sym], ctx["l"][sym]
        if k < 1:
            return None
        if st.get("in"):
            st["held"] += 1
            if c[k] > st["target"] or c[k] < st["stop"] or st["held"] >= HORIZON:
                st["in"] = False
                return {}
            return None
        if l[k] < l[k - 1] and c[k] > l[k - 1]:
            st.update({"in": True, "target": h[k - 1], "stop": l[k], "held": 0})
            return {sym: 1.0}
        return None
    return fn


def run_ict(daily: dict, start_ms: int, end_ms: int) -> dict:
    from .classics import hold_btc, run_weights
    out = {"events": {}, "strategy": {}}
    ok015, ok016 = True, True
    for sym in ("BTCUSDT", "ETHUSDT"):
        bars = [b for b in daily[sym] if b["t"] <= end_ms]
        si = next(i for i, b in enumerate(bars) if b["t"] >= start_ms)
        es = event_study(bars, si)
        out["events"][sym] = es
        bu, be = es["bull"]["vs_all"], es["bear"]["vs_all"]
        ok015 = ok015 and bool(bu and be and bu["ci95_low"] > 0 and be["ci95_high"] < 0)

        def hold(k, ctx, s=sym):
            if not ctx["state"].get("done"):
                ctx["state"]["done"] = True
                return {s: 1.0}
            return None
        base, _, _ = run_weights(daily, [sym], start_ms, end_ms, hold if sym != "BTCUSDT" else hold_btc)
        st, _, _ = run_weights(daily, [sym], start_ms, end_ms, ict_long_fn(sym))
        ci = st.get("weekly_bootstrap") or {}
        passed = ((st.get("sharpe") or -9) > (base.get("sharpe") or 9)
                  and st.get("max_drawdown_pct", 100) < base.get("max_drawdown_pct", 0) and ci and ci["ci95_low"] > 0)
        ok016 = ok016 and passed
        out["strategy"][sym] = {"buy_hold": base, "ict_long": st, "passed": passed}
    out["verdict"] = {"H-MARI-ICT-015": "SUPPORTED_IN_TEST_RANGE" if ok015 else "FALSIFIED",
                      "H-MARI-ICT-016": "SUPPORTED_IN_TEST_RANGE" if ok016 else "FALSIFIED"}
    return out
