# -*- coding: utf-8 -*-
"""الگوی مشترک پنهان ارزهای صعودی — ثبت پیشاپیش در RESEARCH_LOG (2026-11-05T04:25Z).

هر دوشنبه (بستهٔ روزانه UTC، روز t): جهانِ همان روز = ۴۰ ارز با بیشترین حجم دلاری ۳۰ روز اخیر
که دست‌کم ۶۰ روز داده دارند (شامل ارزهای بعداً حذف‌شده، تا حد امکان).
ویژگی‌ها فقط با دادهٔ ≤ t. هدف: بازده از بستهٔ t+1 تا بستهٔ t+8 (۷ روز، اجرا یک روز دیرتر).
یادگیری: علامت IC هر ویژگی در دورهٔ یادگیری. امتیاز = Σ علامت × رتبهٔ ویژگی.
P-019: میانگین IC هفتگی امتیاز در دورهٔ آزمون > ۰ با CI95 بالای صفر.
P-020: هر هفته ۵ ارز برتر، فقط وقتی BTC بالای SMA150؛ شارپ > T-006 و CI95 هفتگی > ۰ در دورهٔ آزمون.
فقط تمرینی.
"""
from __future__ import annotations

import math

from .momentum import _ci_mean, _stats

DAY_MS = 86_400_000
UNIVERSE, MIN_AGE, TOP_K = 40, 60, 5
FEE, SLIP = 0.001, 0.0005
FEATURES = ("ret7", "ret30", "vol_ratio", "dist_high60", "rs_btc30", "volat20")

PATTERN_HYPOTHESES = {
    "H-MARI-P-019": "امتیاز ترکیبی ۶ ویژگی، رتبهٔ بازده ۷ روز بعد را در دورهٔ دست‌نخورده پیش‌بینی می‌کند (IC > ۰، CI95).",
    "H-MARI-P-020": "۵ ارز برتر هفتگی، فقط وقتی BTC بالای SMA150؛ در دورهٔ آزمون شارپ > T-006 و CI95 هفتگی > ۰.",
}


def _rank(xs: list[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):                       # رتبهٔ میانگین برای مقادیر برابر
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2
        i = j + 1
    return r


def spearman(a: list[float], b: list[float]) -> float | None:
    if len(a) < 8:
        return None
    ra, rb = _rank(a), _rank(b)
    ma, mb = sum(ra) / len(ra), sum(rb) / len(rb)
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    va = math.sqrt(sum((x - ma) ** 2 for x in ra))
    vb = math.sqrt(sum((y - mb) ** 2 for y in rb))
    return cov / (va * vb) if va > 0 and vb > 0 else None


class Panel:
    """کندل‌های روزانه هم‌تراز روی تقویم مشترک؛ None برای روزهای بدون داده."""

    def __init__(self, daily: dict[str, list[dict]]):
        self.days = sorted({b["t"] for bars in daily.values() for b in bars})
        pos = {t: i for i, t in enumerate(self.days)}
        n = len(self.days)
        self.c, self.h, self.qv, self.first = {}, {}, {}, {}
        for s, bars in daily.items():
            c, h, q = [None] * n, [None] * n, [None] * n
            for b in bars:
                i = pos[b["t"]]
                c[i], h[i], q[i] = b["c"], b["h"], b.get("qv") or b["c"] * b.get("v", 0)
            self.c[s], self.h[s], self.qv[s] = c, h, q
            self.first[s] = pos[bars[0]["t"]] if bars else n

    def ok(self, s, i, back):
        c = self.c[s]
        return i - back >= 0 and all(c[k] is not None for k in range(i - back, i + 1))

    def universe(self, i: int) -> list[str]:
        cand = []
        for s in self.c:
            if s == "BTCUSDT" or i - self.first[s] < MIN_AGE or not self.ok(s, i, 60):
                continue
            cand.append((sum(self.qv[s][i - 29: i + 1]), s))
        cand.sort(reverse=True)
        return [s for _, s in cand[:UNIVERSE]]

    def features(self, s: str, i: int) -> dict | None:
        c, h, q = self.c[s], self.h[s], self.qv[s]
        b = self.c.get("BTCUSDT")
        if b is None or b[i] is None or b[i - 30] is None:
            return None
        rets = [c[k] / c[k - 1] - 1 for k in range(i - 19, i + 1)]
        mu = sum(rets) / 20
        v30 = sum(q[i - 29: i + 1]) / 30
        return {"ret7": c[i] / c[i - 7] - 1, "ret30": c[i] / c[i - 30] - 1,
                "vol_ratio": (sum(q[i - 6: i + 1]) / 7) / v30 if v30 > 0 else 1.0,
                "dist_high60": c[i] / max(h[i - 59: i + 1]) - 1,
                "rs_btc30": (c[i] / c[i - 30]) / (b[i] / b[i - 30]) - 1,
                "volat20": math.sqrt(sum((r - mu) ** 2 for r in rets) / 19)}

    def fwd(self, s: str, i: int, h: int = 7):
        c = self.c[s]
        if i + 1 + h >= len(c) or c[i + 1] is None or c[i + 1 + h] is None:
            return None             # ارز حذف‌شده در میانهٔ راه: از نمونهٔ IC بیرون، در راهبرد زیان کامل فرض نمی‌شود
        return c[i + 1 + h] / c[i + 1] - 1


def cross_sections(p: Panel, start_ms: int, end_ms: int) -> list[dict]:
    out = []
    for i, t in enumerate(p.days):
        if t < start_ms or t > end_ms or (t // DAY_MS + 3) % 7 != 0:     # فقط دوشنبه‌ها
            continue
        rows = []
        for s in p.universe(i):
            f = p.features(s, i)
            y = p.fwd(s, i)
            if f is not None and y is not None:
                rows.append((s, f, y))
        if len(rows) >= 15:
            out.append({"i": i, "t": t, "rows": rows})
    return out


def learn_signs(train: list[dict]) -> dict:
    res = {}
    for f in FEATURES:
        ics = [x for cs in train if (x := spearman([r[1][f] for r in cs["rows"]], [r[2] for r in cs["rows"]]))
               is not None]
        m = sum(ics) / len(ics) if ics else 0.0
        res[f] = {"mean_ic": round(m, 4), "sign": 1 if m > 0 else -1, "weeks": len(ics),
                  "ci": _ci_mean(ics)}
    return res


def score(rows, signs) -> list[float]:
    tot = [0.0] * len(rows)
    for f in FEATURES:
        r = _rank([x[1][f] for x in rows])
        for k in range(len(rows)):
            tot[k] += signs[f]["sign"] * r[k]
    return tot


def test_ic(test: list[dict], signs) -> dict:
    ics = [x for cs in test if (x := spearman(score(cs["rows"], signs), [r[2] for r in cs["rows"]])) is not None]
    return {"weeks": len(ics), "mean_ic": round(sum(ics) / len(ics), 4) if ics else None, "ci": _ci_mean(ics),
            "hit_weeks_pct": round(sum(1 for x in ics if x > 0) / len(ics) * 100, 1) if ics else None}


def run_strategy(p: Panel, signs, start_ms: int, end_ms: int) -> dict:
    """بازتوزیع هفتگی ۵ ارز برتر (وزن برابر)، تصمیم در بستهٔ دوشنبه، اجرا در بستهٔ سه‌شنبه."""
    b = p.c["BTCUSDT"]
    idx = [i for i, t in enumerate(p.days) if start_ms <= t <= end_ms]
    eq, hold, pending = 1.0, {}, None          # hold: {sym: units}
    curve, weekly, last_w, trades = [], [], None, 0
    for n, i in enumerate(idx):
        def px(s):
            return p.c[s][i]
        if pending is not None:
            val = sum(u * (px(s) or 0) for s, u in hold.items()) + eq
            tgt = {s: val * w for s, w in pending.items() if px(s)}
            cur = {s: u * (px(s) or 0) for s, u in hold.items()}
            turn = sum(abs(tgt.get(s, 0) - cur.get(s, 0)) for s in set(tgt) | set(cur))
            if turn > 1e-9:
                trades += 1
            val -= turn * (FEE + SLIP)
            hold = {s: v / px(s) for s, v in tgt.items()}
            eq = val - sum(tgt.values())
            pending = None
        for s in list(hold):                     # ارز بی‌داده (حذف/توقف): با آخرین قیمت معلوم نقد می‌شود
            if px(s) is None:
                last = next((p.c[s][k] for k in range(i, -1, -1) if p.c[s][k] is not None), 0)
                eq += hold.pop(s) * last
        val = eq + sum(u * px(s) for s, u in hold.items())
        curve.append(val)
        if n % 7 == 0:
            if last_w:
                weekly.append(val / last_w - 1)
            last_w = val
        if (p.days[i] // DAY_MS + 3) % 7 == 0 and i >= 149 and b[i] is not None:
            trend = b[i] > sum(b[i - 149: i + 1]) / 150
            if not trend:
                pending = {}
            else:
                rows = [(s, f, 0.0) for s in p.universe(i) if (f := p.features(s, i)) is not None]
                if len(rows) >= 15:
                    sc = score(rows, signs)
                    top = sorted(range(len(rows)), key=lambda k: -sc[k])[:TOP_K]
                    pending = {rows[k][0]: 1.0 / TOP_K for k in top}
    days = (p.days[idx[-1]] - p.days[idx[0]]) / DAY_MS if idx else 0
    st = _stats(curve, days, weekly)
    st["trades"] = trades
    return st


def diagnostics(test: list[dict], signs) -> dict:
    """تشخیص پس از نتیجه (حکم را تغییر نمی‌دهد): بازده پنجک‌ها و ارزهای پرتکرار در پنجک بالا."""
    q = {k: [] for k in range(5)}
    top_count, top_ret, top5 = {}, {}, []
    for cs in test:
        rows = cs["rows"]
        sc = score(rows, signs)
        order = sorted(range(len(rows)), key=lambda k: sc[k])
        n = len(order)
        for qi in range(5):
            part = order[qi * n // 5:(qi + 1) * n // 5]
            q[qi].append(sum(rows[k][2] for k in part) / len(part))
        best = order[-TOP_K:]
        top5.append(sum(rows[k][2] for k in best) / len(best))
        for k in best:
            s = rows[k][0]
            top_count[s] = top_count.get(s, 0) + 1
            top_ret.setdefault(s, []).append(rows[k][2])
    freq = sorted(top_count.items(), key=lambda x: -x[1])[:12]
    return {"quintile_mean_fwd7_pct": {f"Q{k + 1}": round(sum(v) / len(v) * 100, 3) for k, v in q.items() if v},
            "top5_mean_fwd7_pct": round(sum(top5) / len(top5) * 100, 3) if top5 else None,
            "top5_median_fwd7_pct": round(sorted(top5)[len(top5) // 2] * 100, 3) if top5 else None,
            "most_picked": [{"sym": s, "weeks": c, "mean_fwd7_pct": round(sum(top_ret[s]) / c * 100, 2)}
                            for s, c in freq]}


def run_pattern(daily: dict, train: tuple, test: tuple) -> dict:
    from .classics import run_weights
    from .macro import t006_fn
    p = Panel(daily)
    tr, te = cross_sections(p, *train), cross_sections(p, *test)
    signs = learn_signs(tr)
    ic = test_ic(te, signs)
    strat = run_strategy(p, signs, *test)
    t6, _, _ = run_weights({"BTCUSDT": daily["BTCUSDT"]}, ["BTCUSDT"], test[0], test[1], t006_fn)
    ci = strat.get("weekly_bootstrap") or {}
    ok19 = bool(ic["ci"] and ic["ci"]["ci95_low"] > 0)
    ok20 = bool((strat.get("sharpe") or -9) > (t6.get("sharpe") or 9) and ci and ci["ci95_low"] > 0)
    return {"train_weeks": len(tr), "test_weeks": len(te), "learned": signs, "test_ic": ic,
            "diagnostics_post_hoc": diagnostics(te, signs),
            "strategy_test": strat, "t006_test": t6,
            "avg_universe_test": round(sum(len(cs["rows"]) for cs in te) / max(1, len(te)), 1),
            "verdict": {"H-MARI-P-019": "SUPPORTED_IN_TEST_RANGE" if ok19 else "FALSIFIED",
                        "H-MARI-P-020": "SUPPORTED_IN_TEST_RANGE" if ok20 else "FALSIFIED"}}
