# -*- coding: utf-8 -*-
"""H-MARI-M-003 — مومنتوم سری‌زمانی روزانه با بازتوزیع هفتگی (فرضیهٔ مستقل از H-001/H-002).

منشأ ایده: ادبیات «time-series momentum» (نه دادهٔ آزمون‌های قبلی ماری). ثبت پیشاپیش:
  - جهان: N نماد پرحجم امروز (سوگیری بقا ثبت می‌شود) + فقط پس از ۶۰ روز از اولین کندل هر نماد.
  - هر دوشنبه (بستهٔ روزانه UTC): نمادهایی که بازده ۲۸روزه > ۰ و قیمت > میانگین ۵۰روزه دارند.
  - حداکثر ۱۰ نماد با بیشترین بازده ۲۸روزه، وزن برابر؛ بقیهٔ سرمایه نقد (تتر).
  - هزینه: کارمزد ۰٫۱٪ + لغزش ۰٫۰۵٪ روی حجم جابه‌جایی هر طرف. بدون اهرم، بدون فروش استقراضی.
  - رد فرضیه اگر: بازده کل ≤ ۰، یا کران پایین بازهٔ اطمینان ۹۵٪ میانگین بازده هفتگی ≤ ۰،
    یا بیشترین افت ≥ بیشترین افت خرید و نگه‌داری BTC در همان دوره.
فقط تمرینی — هیچ سفارش واقعی‌ای وجود ندارد.
"""
from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass

DAY_MS = 86_400_000

HYPOTHESIS_M003 = {
    "id": "H-MARI-M-003",
    "statement": "نگه‌داری هفتگی حداکثر ۱۰ ارز با بازده ۲۸روزهٔ مثبت و قیمت بالای میانگین ۵۰روزه "
                 "(وزن برابر، بقیه نقد) پس از هزینه‌ها سود می‌دهد و افتی کمتر از نگه‌داری BTC دارد.",
    "falsified_if": "بازده کل ≤ ۰ یا کران پایین CI95 میانگین بازده هفتگی ≤ ۰ یا بیشترین افت ≥ افت BTC",
    "origin": "ادبیات مومنتوم سری‌زمانی؛ مستقل از نتایج H-001/H-002",
}

HYPOTHESIS_M004 = {
    "id": "H-MARI-M-004",
    "statement": "همان M-003، به‌علاوهٔ فیلتر رژیم: اگر در روز بازتوزیع، بستهٔ BTC زیر میانگین ۲۰۰روزه باشد، "
                 "کل سبد نقد می‌شود.",
    "falsified_if": "همان قاعدهٔ M-003: بازده کل ≤ ۰ یا کران پایین CI95 میانگین بازده هفتگی ≤ ۰ "
                    "یا بیشترین افت ≥ افت BTC",
    "origin": "ادبیات فیلتر روند ۲۰۰روزه + مشاهدهٔ افت بزرگ M-003؛ فقط روی دورهٔ دیده‌نشدهٔ پیش از 2021-11-05 معتبر است",
}


@dataclass(frozen=True)
class MomParams:
    lookback: int = 28
    sma: int = 50
    max_hold: int = 10
    min_age_days: int = 60
    rebalance_weekday: int = 0       # دوشنبه
    fee_side: float = 0.001
    slippage: float = 0.0005
    btc_sma_filter: int = 0          # ۰ = خاموش (M-003). M-004: ۲۰۰
    pit_top: int = 0                 # >۰: جهان «هم‌زمان» — هر دوشنبه فقط N نماد پرحجم همان زمان (ضد سوگیری بقا)
    pit_window: int = 30             # روزهای حجم برای رتبه‌بندی هم‌زمان
    delist_haircut: float = 0.0      # کسر ارزش موقعیتی که دادهٔ نمادش قطع شده (حذف از صرافی)
    vol_target: float = 0.0          # >۰: نوسان سالانهٔ هدف سبد (M-005: ۰٫۴۰)؛ مواجهه = min(1, هدف/نوسان)
    vol_window: int = 30
    only_symbols: tuple = ()         # T-006: ("BTCUSDT",)
    require_momentum: bool = True    # T-006: فقط شرط میانگین متحرک


def _sma(xs, i, n):
    return sum(xs[i - n + 1: i + 1]) / n if i >= n - 1 else float("nan")


def _max_dd(curve):
    peak, mdd = -math.inf, 0.0
    for v in curve:
        peak = max(peak, v)
        mdd = max(mdd, (peak - v) / peak if peak > 0 else 0)
    return mdd * 100


def _ci_mean(xs, n_iter=4000, seed=11):
    if len(xs) < 10:
        return None
    rnd = random.Random(seed)
    ms = sorted(sum(rnd.choice(xs) for _ in xs) / len(xs) for _ in range(n_iter))
    return {"mean_pct": round(sum(xs) / len(xs) * 100, 3), "ci95_low": round(ms[int(.025 * n_iter)] * 100, 3),
            "ci95_high": round(ms[int(.975 * n_iter)] * 100, 3)}


def _stats(curve, days, weekly):
    if len(curve) < 2:
        return {}
    rets = [curve[i] / curve[i - 1] - 1 for i in range(1, len(curve))]
    mu = sum(rets) / len(rets)
    sd = math.sqrt(sum((r - mu) ** 2 for r in rets) / max(1, len(rets) - 1))
    years = days / 365.0
    total = curve[-1] / curve[0] - 1
    return {"total_return_pct": round(total * 100, 2),
            "cagr_pct": round(((1 + total) ** (1 / years) - 1) * 100, 2) if years > 0 and total > -1 else None,
            "max_drawdown_pct": round(_max_dd(curve), 2),
            "sharpe": round(mu / sd * math.sqrt(365), 2) if sd > 0 else None,
            "weekly_bootstrap": _ci_mean(weekly)}


def run_momentum(daily: dict[str, list[dict]], start_ms: int, end_ms: int, p: MomParams | None = None,
                 benchmark: str = "BTCUSDT") -> dict:
    """daily: نماد → کندل‌های روزانه {"t","o","h","l","c",...}. خروجی شامل منحنی، آمار و پایه‌ها."""
    p = p or MomParams()
    idx = {s: {b["t"]: i for i, b in enumerate(bars)} for s, bars in daily.items()}
    closes = {s: [b["c"] for b in bars] for s, bars in daily.items()}
    qvs = {s: [b.get("qv") or 0.0 for b in bars] for s, bars in daily.items()}
    last_t = {s: bars[-1]["t"] for s, bars in daily.items() if bars}
    stale_exits, stale_value = 0, 0.0
    first = {s: bars[0]["t"] for s, bars in daily.items() if bars}
    days = sorted({t for m in idx.values() for t in m if start_ms <= t <= end_ms})
    cost = p.fee_side + p.slippage
    equity, cash, units = 1.0, 1.0, {}
    curve, curve_t, weekly, last_week_eq = [], [], [], None
    picks_log, turnover_sum, rebalances = [], 0.0, 0

    def px(s, t):
        i = idx[s].get(t)
        return closes[s][i] if i is not None else None

    last_px = {}
    for t in days:
        for s in units:
            v = px(s, t)
            if v is not None:
                last_px[s] = v
        equity = cash + sum(u * last_px.get(s, 0.0) for s, u in units.items())
        weekday = ((t // DAY_MS) + 3) % 7          # 1970-01-01 پنجشنبه بود → دوشنبه = 0
        if p.rebalance_weekday < 0 or weekday == p.rebalance_weekday:
            if last_week_eq and (p.rebalance_weekday >= 0 or weekday == 0):
                weekly.append(equity / last_week_eq - 1)
            # موقعیت‌هایی که نمادشان دیگر داده ندارد (حذف‌شده): با کسر ارزش خارج می‌شوند
            for s in list(units):
                if idx[s].get(t) is None and last_t[s] < t:
                    val = units[s] * last_px.get(s, 0.0)
                    loss = val * p.delist_haircut
                    stale_exits += 1
                    stale_value += val / max(equity, 1e-12)
                    cash += val - loss
                    equity -= loss
                    del units[s]
            eligible = None
            if p.pit_top:
                ranked = []
                for s, m in idx.items():
                    i = m.get(t)
                    if i is None or i < p.pit_window:
                        continue
                    ranked.append((sum(qvs[s][i - p.pit_window + 1: i + 1]), s))
                ranked.sort(reverse=True)
                eligible = {s for _, s in ranked[: p.pit_top]}
            cands = []
            for s, m in idx.items():
                if eligible is not None and s not in eligible:
                    continue
                if p.only_symbols and s not in p.only_symbols:
                    continue
                i = m.get(t)
                if i is None or i < max(p.lookback, p.sma) or t - first[s] < p.min_age_days * DAY_MS:
                    continue
                c = closes[s]
                r = c[i] / c[i - p.lookback] - 1
                if (r > 0 or not p.require_momentum) and c[i] > _sma(c, i, p.sma):
                    cands.append((r, s))
            cands.sort(reverse=True)
            chosen = [s for _, s in cands[: p.max_hold]]
            if p.btc_sma_filter:
                bi = idx.get(benchmark, {}).get(t)
                bc = closes.get(benchmark, [])
                regime_ok = bi is not None and not (bc[bi] <= _sma(bc, bi, p.btc_sma_filter))
                if not regime_ok or _sma(bc, bi, p.btc_sma_filter) != _sma(bc, bi, p.btc_sma_filter):
                    chosen = []                       # BTC زیر میانگین (یا دادهٔ ناکافی): کاملاً نقد
            scale_v = 1.0
            if p.vol_target and chosen:
                rets = []
                for k in range(1, p.vol_window + 1):
                    day_r = []
                    for s in chosen:
                        i = idx[s].get(t)
                        if i is not None and i - k >= 0:
                            day_r.append(closes[s][i - k + 1] / closes[s][i - k] - 1)
                    if day_r:
                        rets.append(sum(day_r) / len(day_r))
                if len(rets) > 5:
                    mu_r = sum(rets) / len(rets)
                    vol = math.sqrt(sum((x - mu_r) ** 2 for x in rets) / (len(rets) - 1)) * math.sqrt(365)
                    port_vol = vol * len(chosen) / p.max_hold
                    if port_vol > 0:
                        scale_v = min(1.0, p.vol_target / port_vol)
            target = {s: equity / p.max_hold * scale_v for s in chosen}   # وزن ۱/حداکثر؛ جای خالی = نقد
            # اجرا روی بستهٔ همان روز (کمی خوش‌بینانه؛ در گزارش ثبت می‌شود). هزینه روی حجم جابه‌جایی.
            cur_val = {s: u * last_px.get(s, 0.0) for s, u in units.items()}
            turnover = sum(abs(target.get(s, 0.0) - cur_val.get(s, 0.0)) for s in set(target) | set(cur_val))
            fee = turnover * cost
            equity -= fee
            scale = equity / (equity + fee) if equity + fee > 0 else 0
            units = {}
            for s, v in target.items():
                pr = px(s, t)
                if pr:
                    units[s] = v * scale / pr
                    last_px[s] = pr
            cash = equity - sum(u * last_px[s] for s, u in units.items())
            turnover_sum += turnover / max(equity, 1e-12)
            rebalances += 1
            picks_log.append({"t": t, "held": chosen})
            if p.rebalance_weekday >= 0 or weekday == 0:
                last_week_eq = equity
        curve.append(equity)
        curve_t.append(t)

    def bh(sym):
        xs = [b["c"] for b in daily.get(sym, []) if start_ms <= b["t"] <= end_ms]
        return xs

    btc = bh(benchmark)
    btc_curve = [x / btc[0] for x in btc] if btc else []
    n_days = (days[-1] - days[0]) / DAY_MS if days else 0
    btc_weekly = [btc_curve[i] / btc_curve[i - 7] - 1 for i in range(7, len(btc_curve), 7)]
    res = {
        "params": asdict(p), "days": len(days), "rebalances": rebalances,
        "avg_weekly_turnover": round(turnover_sum / max(1, rebalances), 3),
        "strategy": _stats(curve, n_days, weekly),
        "btc_buy_hold": _stats(btc_curve, n_days, btc_weekly) if btc_curve else None,
        "avg_names_held": round(sum(len(x["held"]) for x in picks_log) / max(1, len(picks_log)), 2),
        "time_in_cash_pct": round(100 * sum(1 for x in picks_log if not x["held"]) / max(1, len(picks_log)), 1),
        "curve": list(zip(curve_t, [round(v, 5) for v in curve])),
        "last_picks": picks_log[-1] if picks_log else None,
        "delisted_exits": stale_exits, "delisted_exit_value_frac_sum": round(stale_value, 3),
        "symbols_ever_held": len({x for pk in picks_log for x in pk["held"]}),
    }
    # بازده سالانه
    from datetime import datetime, timezone
    years = {}
    for t, v in zip(curve_t, curve):
        y = datetime.fromtimestamp(t / 1000, timezone.utc).year
        years.setdefault(y, [v, v])
        years[y][1] = v
    res["by_year_pct"] = {y: round((b / a - 1) * 100, 2) for y, (a, b) in sorted(years.items())}
    s, b = res["strategy"], res["btc_buy_hold"] or {}
    ci = s.get("weekly_bootstrap") or {}
    falsified = (s.get("total_return_pct", 0) <= 0 or not ci or ci["ci95_low"] <= 0
                 or (b and s.get("max_drawdown_pct", 100) >= b.get("max_drawdown_pct", 0)))
    res["verdict"] = "FALSIFIED" if falsified else "SUPPORTED_IN_TEST_RANGE"
    return res


HYPOTHESIS_M003_PIT = {
    "id": "H-MARI-M-003-PIT",
    "statement": "بازآزمایی همان M-003 با جهان هم‌زمان: هر دوشنبه فقط ۳۰ نماد پرحجم ۳۰ روز گذشتهٔ همان زمان، "
                 "شامل نمادهایی که بعداً حذف شدند.",
    "falsified_if": "همان قاعدهٔ M-003",
    "origin": "اصلاح روش‌شناختی (سوگیری بقا) — فرضیهٔ تازه نیست؛ پارامترها همان M-003",
}

HYPOTHESIS_M005 = {
    "id": "H-MARI-M-005-PIT",
    "statement": "همان M-003-PIT، به‌علاوهٔ هدف‌گیری نوسان: مواجههٔ سبد طوری کوچک می‌شود که نوسان سالانهٔ "
                 "تخمینی (۳۰ روز) از ۴۰٪ بیشتر نشود.",
    "falsified_if": "همان قاعدهٔ M-003",
    "origin": "ادبیات volatility targeting؛ ثبت‌شده پیش از دیدن نتیجهٔ M-003-PIT",
}
HYPOTHESIS_T006 = {
    "id": "H-MARI-T-006",
    "statement": "فقط بیت‌کوین: هر روز اگر بسته بالای میانگین ۱۵۰روزه است نگه‌دار، وگرنه کاملاً نقد.",
    "falsified_if": "همان قاعدهٔ M-003 (بازده کل > ۰، کران پایین CI95 هفتگی > ۰، افت کمتر از نگه‌داری BTC)",
    "origin": "ادبیات دنبال‌کردن روند ساده؛ بدون سوگیری بقا؛ ثبت‌شده پیش از دیدن نتیجه",
}
