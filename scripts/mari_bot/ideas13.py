# -*- coding: utf-8 -*-
"""ideas13 — ثبت پیشاپیش در RESEARCH_LOG (2026-11-05T20:00Z). فقط تمرینی، بدون سفارش واقعی.

H-MARI-Y-057: کری دلتا-نیوترال فاندینگ (He، Manela، Ross، von Wachter ۲۰۲۴؛ پس‌زمینه: BIS WP 1087).
خرید اسپات + فروش قرارداد دائمی به اندازهٔ برابر؛ درآمد = نرخ فاندینگ دریافتی.

هشدار ثبت‌شده: این مدل **پوشش کامل** را فرض می‌کند (اختلاف قیمت اسپات و دائمی، هزینهٔ مارجین و
خطر لیکویید شدن در آن نیست). پس نتیجه **خوش‌بینانه** است و حتی اگر بگذرد، سقف است نه واقعیت.
"""
from __future__ import annotations

DAY_MS = 86_400_000
LOOKBACK = 7
ENTER_APR = 0.10
EXIT_APR = 0.0
COST_PER_SIDE = 0.003          # ۴ پا (اسپات + دائمی، ورود + خروج) × ۰٫۱۵٪ ÷ ۲
MIN_DAYS = 200

IDEA13_HYPOTHESES = {
    "H-MARI-Y-057": "کری دلتا-نیوترال فاندینگ (ورود وقتی میانگین ۷ روزهٔ فاندینگ سالانه‌شده > ۱۰٪، خروج زیر ۰٪): شارپ بیشتر از ۱٫۰، بیشترین افت کمتر از ۱۰٪ و بازده کل مثبت پس از هزینه — روی BTC و ETH هر دو.",
}


def annualized(window: list) -> float | None:
    """میانگین فاندینگ روزانهٔ پنجره، سالانه‌شده. روزهای بدون تسویه نادیده گرفته می‌شوند."""
    vals = [v for v in window if v is not None]
    if len(vals) < LOOKBACK // 2:
        return None
    return sum(vals) / len(vals) * 365


def run_carry(days: list, fund_daily: list, enter=ENTER_APR, exit_=EXIT_APR,
              cost=COST_PER_SIDE, always_on=False) -> dict:
    """سیگنال با پنجرهٔ تا روز k، اجرا از روز k+1. درآمد روز = فاندینگ تسویه‌شدهٔ همان روز."""
    eq, peak, dd, rets, cycles = 1.0, 1.0, 0.0, [], 0
    in_pos, pend = False, None
    for k in range(len(days)):
        if pend is not None and pend != in_pos:           # اجرای تصمیم دیروز
            eq *= 1 - cost
            if pend:
                cycles += 1
            in_pos = pend
        pend = None
        r = fund_daily[k] if in_pos and fund_daily[k] is not None else 0.0
        if in_pos:
            eq *= 1 + r
        rets.append(r if in_pos else 0.0)
        peak = max(peak, eq)
        dd = max(dd, 1 - eq / peak)
        if always_on:
            pend = True
            continue
        a = annualized(fund_daily[max(0, k - LOOKBACK + 1): k + 1])
        if a is None:
            continue
        if not in_pos and a > enter:
            pend = True
        elif in_pos and a < exit_:
            pend = False
    n = len(rets)
    if n < MIN_DAYS:
        return {"n_days": n, "insufficient": True}
    m = sum(rets) / n
    sd = (sum((x - m) ** 2 for x in rets) / (n - 1)) ** 0.5 if n > 1 else 0.0
    return {"n_days": n, "cycles": cycles, "total_return_pct": round((eq - 1) * 100, 2),
            "max_drawdown_pct": round(dd * 100, 2),
            "sharpe": round(m / sd * 365 ** 0.5, 2) if sd else None,
            "days_in_position_pct": round(sum(1 for x in rets if x) / n * 100, 1)}


def passes(st: dict) -> bool:
    if st.get("insufficient"):
        return False
    s = st.get("sharpe")
    return bool(s is not None and s > 1.0 and st.get("max_drawdown_pct", 100) < 10.0
                and st.get("total_return_pct", -1) > 0)


def run_ideas13(fund_by_sym: dict, days: list) -> dict:
    """fund_by_sym: {sym: [فاندینگ روزانه هم‌تراز با days]}"""
    out, ok = {}, True
    for sym in ("BTCUSDT", "ETHUSDT"):
        fd = fund_by_sym.get(sym)
        if not fd:
            out[sym] = {"insufficient": True}
            ok = False
            continue
        gated = run_carry(days, fd)
        out[sym] = {"H-MARI-Y-057": gated, "ALWAYS_ON_INFO": run_carry(days, fd, always_on=True)}
        ok &= passes(gated)
    return {"by_asset": out,
            "verdict": {"H-MARI-Y-057": "SUPPORTED_IN_TEST_RANGE" if ok else "FALSIFIED"}}
