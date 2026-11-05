# -*- coding: utf-8 -*-
"""O-042 — ثبت پیشاپیش در RESEARCH_LOG (2026-11-05T14:10Z). فقط تمرینی.

آیا جهش موقعیت‌های باز آتی (OI) در ۲۴ ساعت پیش از ورود، معامله‌های شکارچی ساعتی (B-001) را بدتر می‌کند؟
داده: بایگانی عمومی بایننس futures/um/daily/metrics (sum_open_interest هر ۵ دقیقه).
"""
from __future__ import annotations

import bisect
import csv
import io
import random
import time
import zipfile
from datetime import datetime, timezone

DAY_MS = 86_400_000
SURGE = 0.25
MIN_GROUP = 20
METRICS_PREFIX = "/data/futures/um/daily/metrics/"

OI_HYPOTHESES = {
    "H-MARI-O-042": "جهش OI ≥ ۲۵٪ در ۲۴ ساعت پیش از ورود: میانگین بازدهٔ معامله کمتر از بقیه، CI95 بالای صفر، در هر دو نمونه، با دست‌کم ۲۰ معامله در گروه جهش.",
}


def parse_metrics(text: str) -> list[tuple[int, float]]:
    """CSV بایننس: create_time,symbol,sum_open_interest,... → [(ms, oi)]."""
    out = []
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 3 or not row[0][:1].isdigit():
            continue
        try:
            t = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            oi = float(row[2])
        except ValueError:
            continue
        if oi > 0:
            out.append((int(t.timestamp() * 1000), oi))
    return out


def fetch_day(sym: str, day_ms: int, getter=None) -> list[tuple[int, float]] | None:
    """None = فایل وجود ندارد (ارز قرارداد آتی ندارد یا روز منتشر نشده)."""
    if getter is None:
        from .data import http_get_bytes as getter
    d = datetime.fromtimestamp(day_ms / 1000, timezone.utc).strftime("%Y-%m-%d")
    blob = getter(f"{METRICS_PREFIX}{sym}/{sym}-metrics-{d}.zip")
    if not blob:
        return None
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        return parse_metrics(z.read(z.namelist()[0]).decode("utf-8", "replace"))


def oi_at(series: list[tuple[int, float]], t_ms: int) -> float | None:
    """آخرین OI با زمان ≤ t_ms (فقط گذشته)، به شرط اینکه کهنه‌تر از ۳۰ دقیقه نباشد."""
    i = bisect.bisect_right(series, (t_ms, float("inf"))) - 1
    if i < 0 or t_ms - series[i][0] > 30 * 60_000:
        return None
    return series[i][1]


def oi_change(series, entry_ts: int) -> float | None:
    now, then = oi_at(series, entry_ts), oi_at(series, entry_ts - DAY_MS)
    if now is None or then is None:
        return None
    return now / then - 1


def collect(trades: list[dict], getter=None, pause: float = 0.05) -> tuple[list[dict], dict]:
    """برای هر معامله جهش OI را حساب می‌کند. خروجی: معامله‌های دارای OI + آمار پوشش."""
    cache: dict[tuple[str, int], list | None] = {}
    no_fut: set[str] = set()
    out, missing = [], 0
    for tr in trades:
        sym, ts = tr["symbol"], int(tr["entry_ts"])
        if sym in no_fut:
            missing += 1
            continue
        day = ts // DAY_MS * DAY_MS
        rows = []
        for d in (day - DAY_MS, day):
            if (sym, d) not in cache:
                cache[(sym, d)] = fetch_day(sym, d, getter)
                time.sleep(pause)
            rows += cache[(sym, d)] or []
        if not rows:
            if cache.get((sym, day)) is None and cache.get((sym, day - DAY_MS)) is None:
                no_fut.add(sym)
            missing += 1
            continue
        rows.sort()
        ch = oi_change(rows, ts)
        if ch is None:
            missing += 1
            continue
        out.append({**tr, "oi_change_24h": round(ch, 4)})
    return out, {"trades_total": len(trades), "with_oi": len(out), "missing": missing,
                 "symbols_without_futures": sorted(no_fut), "files_fetched": len(cache)}


def _ci_diff(a, b, n_iter=4000, seed=42):
    if len(a) < 2 or len(b) < 2:
        return None
    rnd = random.Random(seed)
    ds = sorted(sum(rnd.choice(a) for _ in a) / len(a) - sum(rnd.choice(b) for _ in b) / len(b)
                for _ in range(n_iter))
    return {"diff_pct": round(sum(a) / len(a) - sum(b) / len(b), 4),
            "ci95_low": round(ds[int(.025 * n_iter)], 4), "ci95_high": round(ds[int(.975 * n_iter)], 4)}


def evaluate(trades_oi: list[dict], surge: float = SURGE) -> dict:
    s = [t for t in trades_oi if t["oi_change_24h"] >= surge]
    r = [t for t in trades_oi if t["oi_change_24h"] < surge]

    def summ(g):
        return {"n": len(g),
                "mean_pnl_pct": round(sum(t["pnl_pct"] for t in g) / len(g), 3) if g else None,
                "win_rate_pct": round(sum(t["pnl_pct"] > 0 for t in g) / len(g) * 100, 1) if g else None,
                "stop_loss_pct": round(sum(t["exit_reason"] == "STOP_LOSS" for t in g) / len(g) * 100, 1) if g else None,
                "net_pnl_usdt": round(sum(t["pnl_usdt"] for t in g), 2)}
    diff = _ci_diff([t["pnl_pct"] for t in r], [t["pnl_pct"] for t in s])
    if len(s) < MIN_GROUP:
        verdict = "INSUFFICIENT_DATA"
    else:
        verdict = "SUPPORTED_IN_TEST_RANGE" if diff and diff["ci95_low"] > 0 else "FALSIFIED"
    qs = sorted(t["oi_change_24h"] for t in trades_oi)
    pct = {p: round(qs[int(p / 100 * (len(qs) - 1))] * 100, 1) for p in (10, 50, 90, 99)} if qs else {}
    return {"surge": summ(s), "rest": summ(r), "rest_minus_surge": diff, "verdict": verdict,
            "oi_change_percentiles_pct": pct,
            "info_net_pnl_without_surge_usdt": summ(r)["net_pnl_usdt"],
            "info_net_pnl_all_usdt": round(sum(t["pnl_usdt"] for t in trades_oi), 2)}


def combine(per_sample: dict) -> str:
    vs = [x["verdict"] for x in per_sample.values()]
    if any(v == "INSUFFICIENT_DATA" for v in vs):
        return "INSUFFICIENT_DATA"
    return "SUPPORTED_IN_TEST_RANGE" if all(v.startswith("SUPPORTED") for v in vs) else "FALSIFIED"
