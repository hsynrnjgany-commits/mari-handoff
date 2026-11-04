# -*- coding: utf-8 -*-
"""پژوهش خارج از نمونه روی تاریخچهٔ طولانی (CORE-DOCTRINE بخش ۱۱، سند مادر ۳۴ و ۳۵).

ثبت پیشاپیش (پیش از دیدن نتیجه): فرضیهٔ H-MARI-B-001 با پارامترهای پیش‌فرض نسخهٔ فعلی
(شناسهٔ تنظیمات در گزارش). هیچ پارامتری روی این داده تنظیم نمی‌شود؛ تمام این داده برای
این پارامترها «خارج از نمونه» است، چون پارامترها پیش از دریافت آن ثابت شده‌اند.

آزمون‌ها: فولدهای ماهانه (پایداری در زمان + سطل‌بندی رژیم BTC)، حساسیت هزینه،
حذف دُم سود، بوت‌استرپ، مقایسه با خرید و نگه‌داری.
منبع تاریخچه: Binance Vision عمومی (تووبیت صفحه‌بندی تاریخی مستند ندارد) — در گزارش ثبت می‌شود.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import replace
from datetime import datetime, timezone

from .backtest import add_counterfactuals, bootstrap_ci, metrics
from .config import CODE_VERSION, BotConfig, CostParams, tradable_symbol
from .data import BINANCE_VISION, DataError, bars_sha, http_get_json, parse_toobit_klines, quality_check
from .engine import MariBot
from .ledger import Ledger
from .trend import SymbolSeries

HOUR_MS = 3_600_000
DAY_MS = 86_400_000
HYPOTHESES = {
    "H-MARI-B-001": {
        "statement": "ورود در شکست سقف ۲۰ کندل در روند A/B با حجم بالا، همراه با مدیریت خروج پله‌ای "
                     "دکترین، پس از هزینه‌های فرضی بازده مثبت دارد.",
        "risk_overrides": {},
        "status_before": "FALSIFIED on 2026-05-08..2026-11-04 (run 20261104T2009Z) — اینجا فقط گروه کنترل است",
    },
    "H-MARI-B-002": {
        "statement": "همان H-001، اما ورود فقط وقتی BTC در وضعیت A یا B (صعودی) است.",
        "risk_overrides": {"require_btc_states": ("A", "B")},
        "status_before": "ایده از نتایج ماهانهٔ H-001 آمد؛ پیش از دیدن این دوره ثبت شد. "
                         "فقط روی دورهٔ دست‌نخوردهٔ قبل از 2026-05-08 معتبر است.",
    },
}
FALSIFIED_IF = ("بازده خالص کل ≤ ۰ یا کران پایین بازهٔ اطمینان ۹۵٪ میانگین هر معامله < ۰ "
                "یا ضریب سود < ۱ در هزینهٔ پایه")


def fetch_history(symbol: str, start_ms: int, end_ms: int, interval: str = "1h") -> list[dict]:
    out, cur = [], start_ms
    while cur < end_ms:
        rows = http_get_json("/api/v3/klines", {"symbol": symbol, "interval": interval, "startTime": cur,
                                                "limit": 1000}, base=BINANCE_VISION, retries=4, timeout=30)
        bars = parse_toobit_klines(rows)
        if not bars:
            break
        out.extend(b for b in bars if b["t"] + HOUR_MS <= end_ms)
        nxt = bars[-1]["t"] + HOUR_MS
        if nxt <= cur:
            break
        cur = nxt
        time.sleep(0.05)
    return out


def pick_universe(top: int) -> list[str]:
    d = http_get_json("/api/v3/ticker/24hr", base=BINANCE_VISION, timeout=30)
    rows = [r for r in d if tradable_symbol(r.get("symbol", ""))]
    rows.sort(key=lambda r: -float(r.get("quoteVolume") or 0))
    syms = [r["symbol"] for r in rows[:top]]
    return ["BTCUSDT"] + [s for s in syms if s != "BTCUSDT"]


def _run(series, quality, cfg, start_ts, end_ts, run_id):
    led = Ledger(None, run_id, cfg.sha())
    bot = MariBot(cfg, led)
    bot.last_ts = start_ts - 1
    bot.process(series, quality, until_ts=end_ts)
    add_counterfactuals(bot.trades, series)
    m = metrics(bot.trades, bot.equity_curve, cfg.risk.start_equity)
    m["bootstrap"] = bootstrap_ci(bot.trades)
    m["open_at_end"] = len(bot.positions)
    return m, bot.trades


def _tail_removed(trades, frac=0.05, start=1000.0):
    if not trades:
        return None
    srt = sorted(trades, key=lambda t: -t["pnl_usdt"])
    k = max(1, int(len(srt) * frac))
    return {"removed": k, "net_pnl_all": round(sum(t["pnl_usdt"] for t in trades), 2),
            "net_pnl_without_top": round(sum(t["pnl_usdt"] for t in srt[k:]), 2),
            "net_pct_without_top": round(sum(t["pnl_usdt"] for t in srt[k:]) / start * 100, 2)}


def _bh(series, sym, a, b):
    s = series.get(sym)
    if not s:
        return None
    xs = [x for x in s.bars if a <= x["t"] <= b]
    return round((xs[-1]["c"] / xs[0]["o"] - 1) * 100, 2) if len(xs) > 1 else None


def _verdict(full):
    ci = full.get("bootstrap") or {}
    if full["net_return_pct"] > 0 and (full["profit_factor"] or 0) >= 1 and ci and ci["ci95_low"] > 0:
        return "SUPPORTED_IN_TEST_RANGE"
    if full["net_return_pct"] > 0 and (full["profit_factor"] or 0) >= 1:
        return "INCONCLUSIVE"
    return "FALSIFIED"


def _evaluate(series, quality, cfg, start, end, tag):
    full, trades = _run(series, quality, cfg, start, end, f"{tag}-FULL")
    costs = {}
    for fee in (0.0, 0.0005, 0.001, 0.002, 0.003):
        c = replace(cfg, cost=CostParams(fee_side=fee, slippage=cfg.cost.slippage))
        m, _ = _run(series, quality, c, start, end, f"{tag}-FEE{fee}")
        costs[f"fee_side_{fee * 100:.2f}pct"] = {k: m[k] for k in ("trades", "net_return_pct", "profit_factor",
                                                                    "win_rate_pct", "max_drawdown_pct")}
    folds, a = [], start
    while a < end:
        b = min(a + 30 * DAY_MS, end)
        m, _ = _run(series, quality, cfg, a, b, f"{tag}-FOLD{len(folds)}")
        btc = _bh(series, "BTCUSDT", a, b)
        regime = "BULL" if btc is not None and btc > 10 else "BEAR" if btc is not None and btc < -10 else "FLAT"
        folds.append({"from": datetime.fromtimestamp(a / 1000, timezone.utc).strftime("%Y-%m-%d"),
                      "to": datetime.fromtimestamp(b / 1000, timezone.utc).strftime("%Y-%m-%d"),
                      "btc_return_pct": btc, "regime": regime,
                      **{k: m[k] for k in ("trades", "net_return_pct", "profit_factor", "win_rate_pct",
                                           "max_drawdown_pct")}})
        a = b
    return {"config_sha": cfg.sha(), "verdict": _verdict(full), "full_period": full, "cost_sensitivity": costs,
            "folds": folds, "tail_removal_top5pct": _tail_removed(trades, 0.05, cfg.risk.start_equity)}, trades


def run_research(months: int = 6, top: int = 60, out_dir: str = "research_out", end_ms: int | None = None,
                 hypotheses: list[str] | None = None) -> dict:
    base = BotConfig()
    hyps = hypotheses or list(HYPOTHESES)
    t_fetch = datetime.now(timezone.utc).isoformat(timespec="seconds")
    end = (end_ms or int(time.time() * 1000)) // HOUR_MS * HOUR_MS
    warm = (base.trend.min_bars + 40) * HOUR_MS
    start = end - months * 30 * DAY_MS
    syms = pick_universe(top)
    raw, failed, lineage = {}, [], {}
    for s in syms:
        try:
            bars = fetch_history(s, start - warm, end)
        except DataError as e:
            failed.append(f"{s}:{e}")
            continue
        raw[s] = bars
        lineage[s] = {"bars": len(bars), "sha": bars_sha(bars),
                      "first": bars[0]["t"] if bars else None, "last": bars[-1]["t"] if bars else None}
    series, quality = {}, {}
    for s, bars in raw.items():
        q = quality_check(bars)
        quality[s] = {"ok": q["ok"], "issues": q["issues"]}
        if q["n"] >= base.trend.min_bars + 2:
            series[s] = SymbolSeries(s, q["clean"], base.trend)

    results, all_trades = {}, {}
    for hid in hyps:
        h = HYPOTHESES[hid]
        cfg = replace(base, risk=replace(base.risk, **h["risk_overrides"]))
        res, trades = _evaluate(series, quality, cfg, start, end, hid)
        results[hid] = {"statement": h["statement"], "status_before": h["status_before"], **res}
        all_trades[hid] = trades
    bh_all = [r for r in (_bh(series, s, start, end) for s in series if s != "BTCUSDT") if r is not None]
    report = {
        "falsified_if": FALSIFIED_IF, "registered_before_results": True,
        "code": CODE_VERSION, "fetched_utc": t_fetch,
        "period": {"from": datetime.fromtimestamp(start / 1000, timezone.utc).isoformat(),
                   "to": datetime.fromtimestamp(end / 1000, timezone.utc).isoformat(), "months": months},
        "source": BINANCE_VISION + "/api/v3/klines (public, read-only)",
        "universe": {"requested_top": top, "used": len(series), "failed": failed,
                     "quality_failed": sorted(s for s, q in quality.items() if not q["ok"])},
        "known_biases": [
            "SURVIVORSHIP: نمادها با حجم امروز انتخاب شدند؛ نمادهای حذف‌شده در گذشته غایب‌اند (به نفع نتیجه).",
            "VENUE: تاریخچه از بایننس است، اجرای زنده از تووبیت؛ قیمت‌ها نزدیک‌اند اما یکسان نیستند.",
            f"MULTIPLE_TESTS: تعداد فرضیه‌های آزموده‌شده تا این اجرا: {len(HYPOTHESES)}.",
        ],
        "baseline": {"btc_buy_hold_pct": _bh(series, "BTCUSDT", start, end),
                     "equal_weight_buy_hold_pct": round(sum(bh_all) / len(bh_all), 2) if bh_all else None},
        "results": results, "lineage": lineage,
    }
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(out_dir, "trades.json"), "w", encoding="utf-8") as fh:
        json.dump(all_trades, fh, ensure_ascii=False)
    with open(os.path.join(out_dir, "report_fa.md"), "w", encoding="utf-8") as fh:
        fh.write(render_fa(report))
    return report


def render_fa(r: dict) -> str:
    L = ["# گزارش پژوهش خارج از نمونه", "",
         f"- دوره: {r['period']['from'][:10]} تا {r['period']['to'][:10]} ({r['period']['months']} ماه)",
         f"- نمادها: {r['universe']['used']} — منبع: {r['source']} — نسخهٔ کد: {r['code']}",
         f"- شرط رد فرضیه (ثبت پیشاپیش): {r['falsified_if']}",
         f"- پایه: خرید و نگه‌داری BTC {r['baseline']['btc_buy_hold_pct']}٪ — سبد برابر "
         f"{r['baseline']['equal_weight_buy_hold_pct']}٪", ""]
    for hid, x in r["results"].items():
        f = x["full_period"]
        L += [f"## {hid} — حکم: **{x['verdict']}**", "", x["statement"], "",
              f"- معامله: {f['trades']} — نرخ برد: {f['win_rate_pct']}٪ — ضریب سود: {f['profit_factor']}",
              f"- بازده خالص: {f['net_return_pct']}٪ — بیشترین افت: {f['max_drawdown_pct']}٪",
              f"- بوت‌استرپ میانگین هر معامله: {f.get('bootstrap')}",
              f"- حذف ۵٪ برترین معامله‌ها: {x['tail_removal_top5pct']}", "",
              "| کارمزد هر طرف | معامله | بازده ٪ | ضریب سود |", "|---|---|---|---|"]
        for k, v in x["cost_sensitivity"].items():
            L.append(f"| {k} | {v['trades']} | {v['net_return_pct']} | {v['profit_factor']} |")
        L += ["", "| از | تا | رژیم BTC | BTC ٪ | معامله | بازده ٪ | ضریب سود |", "|---|---|---|---|---|---|---|"]
        for y in x["folds"]:
            L.append(f"| {y['from']} | {y['to']} | {y['regime']} | {y['btc_return_pct']} | {y['trades']} | "
                     f"{y['net_return_pct']} | {y['profit_factor']} |")
        L.append("")
    L += ["## سوگیری‌های شناخته‌شده", ""] + [f"- {b}" for b in r["known_biases"]]
    L += ["", "> همه‌چیز تمرینی است — بدون سفارش واقعی"]
    return "\n".join(L) + "\n"
