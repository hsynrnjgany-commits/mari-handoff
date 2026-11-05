# -*- coding: utf-8 -*-
"""ideas15 — ثبت پیشاپیش در RESEARCH_LOG (2026-11-05T20:30Z). فقط تمرینی.

H-MARI-Y-060: همان کری دلتا-نیوترال Y-057، اما این بار با **قیمت واقعی قرارداد دائمی**.
شارپ ۹ در Y-057 از آنجا آمد که مدل اختلاف قیمت اسپات و دائمی (basis) را صفر فرض کرده بود.
اینجا سود و زیان هر دو پا با قیمت واقعی خودشان حساب می‌شود و سرمایه = اسپات + مارجین (بدون اهرم).
"""
from __future__ import annotations

import csv
import io
import zipfile
from datetime import datetime, timedelta, timezone

DAY_MS = 86_400_000
LOOKBACK = 7
ENTER_APR = 0.10
EXIT_APR = 0.0
FEE_SIDE = 0.0015              # کارمزد + لغزش روی ارزش اسمی هر پا
MIN_DAYS = 200

IDEA15_HYPOTHESES = {
    "H-MARI-Y-060": "کری دلتا-نیوترال با قیمت واقعی قرارداد دائمی و سرمایهٔ اسپات+مارجین (بدون اهرم): شارپ بیشتر از ۱٫۰، بیشترین افت کمتر از ۱۰٪ و بازده کل مثبت — روی BTC و ETH هر دو.",
}


def parse_kline_csv(text: str) -> list:
    out = []
    for row in csv.reader(io.StringIO(text)):
        if not row or not row[0].split(".")[0].isdigit():
            continue
        try:
            t, c = int(float(row[0])), float(row[4])
        except (ValueError, IndexError):
            continue
        if t > 10 ** 14:                       # میکروثانیه در فایل‌های تازه
            t //= 1000
        out.append((t // DAY_MS * DAY_MS, c))
    return out


def fetch_perp_daily(sym: str, start_ms: int, end_ms: int) -> dict:
    """بستهٔ روزانهٔ قرارداد دائمی از بایگانی عمومی بایننس. خروجی: {روز: قیمت}."""
    from .data import _PERP_KLINES_PREFIX, http_get_bytes
    out = {}
    d = datetime.fromtimestamp(start_ms / 1000, timezone.utc).replace(day=1)
    last = datetime.fromtimestamp(end_ms / 1000, timezone.utc)
    while d <= last:
        name = f"{sym}-1d-{d:%Y-%m}"
        blob = http_get_bytes(f"{_PERP_KLINES_PREFIX}{sym}/1d/{name}.zip")
        if blob:
            try:
                with zipfile.ZipFile(io.BytesIO(blob)) as z:
                    text = z.read(z.namelist()[0]).decode("utf-8", "replace")
                out.update(dict(parse_kline_csv(text)))
            except (zipfile.BadZipFile, KeyError, IndexError):
                pass
        d = (d.replace(day=28) + timedelta(days=7)).replace(day=1)
    return out


def annualized(window: list) -> float | None:
    vals = [v for v in window if v is not None]
    if len(vals) < LOOKBACK // 2:
        return None
    return sum(vals) / len(vals) * 365


def run_basis_carry(days: list, spot: dict, perp: dict, fund: list, fee=FEE_SIDE,
                    always_on=False, zero_basis=False) -> dict:
    """یک واحد اسپات خرید + یک واحد دائمی فروش.
    سود روز = (تغییر اسپات) − (تغییر دائمی) + فاندینگ × ارزش دائمی.
    سرمایه = اسپات + مارجین کامل دائمی (بدون اهرم). zero_basis=True فرض Y-057 را بازمی‌سازد."""
    eq, peak, dd, rets, cycles, worst = 1.0, 1.0, 0.0, [], 0, 0.0
    qty, cap0 = 0.0, 0.0
    in_pos, pend, skipped = False, None, 0
    prev_s = prev_p = None
    for k, t in enumerate(days):
        s = spot.get(t)
        pp = perp.get(t) if not zero_basis else s
        if s is None or pp is None or s <= 0 or pp <= 0:
            skipped += 1
            prev_s = prev_p = None
            rets.append(0.0)
            continue
        if pend is not None and pend != in_pos:
            if pend:
                # سرمایهٔ یک واحد = اسپات + مارجین کامل دائمی. ارزش اسمی دو پا = همان سرمایه،
                # پس کارمزد ۰٫۱۵٪ روی ارزش اسمی هر پا = ۰٫۱۵٪ از سرمایه.
                cap0 = s + pp
                qty = eq / cap0
                eq -= fee * qty * cap0
                qty = eq / cap0
                cycles += 1
            else:
                eq -= fee * qty * (s + pp)
                qty, cap0 = 0.0, 0.0
            in_pos = pend
        pend = None
        r = 0.0
        if in_pos and prev_s is not None and prev_p is not None:
            f = fund[k] if fund[k] is not None else 0.0
            pnl = qty * ((s - prev_s) - (pp - prev_p) + f * pp)
            r = pnl / eq if eq > 0 else 0.0
            eq += pnl
        rets.append(r)
        worst = min(worst, r)
        peak = max(peak, eq)
        dd = max(dd, 1 - eq / peak)
        prev_s, prev_p = s, pp
        if always_on:
            pend = True
            continue
        a = annualized(fund[max(0, k - LOOKBACK + 1): k + 1])
        if a is None:
            continue
        if not in_pos and a > ENTER_APR:
            pend = True
        elif in_pos and a < EXIT_APR:
            pend = False
    n = len(rets)
    if n - skipped < MIN_DAYS:
        return {"n_days": n, "skipped_days": skipped, "insufficient": True}
    m = sum(rets) / n
    sd = (sum((x - m) ** 2 for x in rets) / (n - 1)) ** 0.5 if n > 1 else 0.0
    return {"n_days": n, "skipped_days": skipped, "cycles": cycles,
            "total_return_pct": round((eq - 1) * 100, 2), "max_drawdown_pct": round(dd * 100, 2),
            "sharpe": round(m / sd * 365 ** 0.5, 2) if sd else None,
            "worst_day_pct": round(worst * 100, 3),
            "days_in_position_pct": round(sum(1 for x in rets if x) / n * 100, 1)}


def passes(st: dict) -> bool:
    if st.get("insufficient"):
        return False
    s = st.get("sharpe")
    return bool(s is not None and s > 1.0 and st.get("max_drawdown_pct", 100) < 10.0
                and st.get("total_return_pct", -1) > 0)


def basis_stats(days: list, spot: dict, perp: dict) -> dict:
    bs = [(perp[t] / spot[t] - 1) for t in days if spot.get(t) and perp.get(t)]
    if not bs:
        return {}
    bs_sorted = sorted(bs)
    return {"n": len(bs), "mean_pct": round(sum(bs) / len(bs) * 100, 4),
            "p01_pct": round(bs_sorted[int(.01 * len(bs))] * 100, 3),
            "p99_pct": round(bs_sorted[int(.99 * len(bs))] * 100, 3),
            "min_pct": round(bs_sorted[0] * 100, 3), "max_pct": round(bs_sorted[-1] * 100, 3)}


def run_ideas15(days: list, spot: dict, perp: dict, fund: dict) -> dict:
    out, ok = {}, True
    for sym in ("BTCUSDT", "ETHUSDT"):
        sp, pe, fd = spot.get(sym) or {}, perp.get(sym) or {}, fund.get(sym) or []
        if not sp or not pe or not fd:
            out[sym] = {"insufficient": True}
            ok = False
            continue
        real = run_basis_carry(days, sp, pe, fd)
        out[sym] = {"H-MARI-Y-060": real,
                    "ZERO_BASIS_INFO": run_basis_carry(days, sp, pe, fd, zero_basis=True),
                    "ALWAYS_ON_INFO": run_basis_carry(days, sp, pe, fd, always_on=True),
                    "BASIS_INFO": basis_stats(days, sp, pe)}
        ok &= passes(real)
    return {"by_asset": out,
            "verdict": {"H-MARI-Y-060": "SUPPORTED_IN_TEST_RANGE" if ok else "FALSIFIED"}}
