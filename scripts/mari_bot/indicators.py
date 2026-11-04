# -*- coding: utf-8 -*-
"""شاخص‌های فنی خالص پایتون (بدون وابستگی). هر خروجی هم‌طول ورودی است؛ مقدار i فقط از کندل‌های ≤ i ساخته می‌شود."""
from __future__ import annotations

NaN = float("nan")


def ema(xs: list[float], n: int) -> list[float]:
    out, k, e = [], 2.0 / (n + 1), None
    for i, x in enumerate(xs):
        if i < n - 1:
            out.append(NaN)
            continue
        e = sum(xs[: n]) / n if e is None else x * k + e * (1 - k)
        out.append(e)
    return out


def _wilder(xs: list[float], n: int) -> list[float]:
    out, s = [], None
    for i, x in enumerate(xs):
        if i < n - 1:
            out.append(NaN)
            continue
        s = sum(xs[:n]) / n if s is None else (s * (n - 1) + x) / n
        out.append(s)
    return out


def true_range(bars: list[dict]) -> list[float]:
    tr = []
    for i, b in enumerate(bars):
        if i == 0:
            tr.append(b["h"] - b["l"])
        else:
            pc = bars[i - 1]["c"]
            tr.append(max(b["h"] - b["l"], abs(b["h"] - pc), abs(b["l"] - pc)))
    return tr


def atr(bars: list[dict], n: int = 14) -> list[float]:
    return _wilder(true_range(bars), n)


def rsi(closes: list[float], n: int = 14) -> list[float]:
    gains, losses = [0.0], [0.0]
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    ag, al = _wilder(gains[1:], n), _wilder(losses[1:], n)
    out = [NaN]
    for g, l in zip(ag, al):
        if g != g:
            out.append(NaN)
        elif l == 0:
            out.append(100.0)
        else:
            out.append(100 - 100 / (1 + g / l))
    return out


def adx(bars: list[dict], n: int = 14) -> list[float]:
    pdm, mdm = [0.0], [0.0]
    for i in range(1, len(bars)):
        up = bars[i]["h"] - bars[i - 1]["h"]
        dn = bars[i - 1]["l"] - bars[i]["l"]
        pdm.append(up if up > dn and up > 0 else 0.0)
        mdm.append(dn if dn > up and dn > 0 else 0.0)
    tr = true_range(bars)
    str_, sp, sm = _wilder(tr, n), _wilder(pdm, n), _wilder(mdm, n)
    dx = []
    for t, p, m in zip(str_, sp, sm):
        if t != t or t == 0:
            dx.append(NaN)
            continue
        pdi, mdi = 100 * p / t, 100 * m / t
        dx.append(0.0 if pdi + mdi == 0 else 100 * abs(pdi - mdi) / (pdi + mdi))
    first = next((i for i, v in enumerate(dx) if v == v), None)
    out = [NaN] * len(bars)
    if first is None:
        return out
    sm_dx = _wilder(dx[first:], n)
    for j, v in enumerate(sm_dx):
        out[first + j] = v
    return out


def confirmed_pivots(bars: list[dict], t: int, k: int = 3, lookback: int = 120):
    """پیوت‌های سقف/کف تا اندیس t که با k کندل بعدی (همه ≤ t) تأیید شده‌اند — بدون نگاه به آینده."""
    highs, lows = [], []
    lo = max(k, t - lookback)
    for i in range(lo, t - k + 1):
        h, l = bars[i]["h"], bars[i]["l"]
        win = bars[i - k: i + k + 1]
        if all(h >= w["h"] for w in win) and any(h > w["h"] for w in win):
            highs.append((i, h))
        if all(l <= w["l"] for w in win) and any(l < w["l"] for w in win):
            lows.append((i, l))
    return highs, lows


def median(xs: list[float]) -> float:
    ys = sorted(x for x in xs if x == x)
    if not ys:
        return NaN
    m = len(ys) // 2
    return ys[m] if len(ys) % 2 else (ys[m - 1] + ys[m]) / 2
