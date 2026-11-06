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
    "H-MARI-B-003": {
        "statement": "همان H-001، اما ارزهای ۲۰٪ پایین امتیاز الگوی P-019 (علامت‌های منجمد، دوشنبه‌ها) خریده نمی‌شوند.",
        "risk_overrides": {},
        "blacklist": True,
        "status_before": "ثبت پیشاپیش 2026-11-05T05:20Z؛ دورهٔ دست‌نخورده 2025-05-09..2025-11-08. "
                         "قبول فقط اگر معیار H-001 برقرار باشد و بازده خالص از گروه کنترل H-001 بیشتر باشد.",
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
    step = {"1h": HOUR_MS, "4h": 4 * HOUR_MS, "1d": DAY_MS}[interval]
    out, cur = [], start_ms
    while cur < end_ms:
        rows = http_get_json("/api/v3/klines", {"symbol": symbol, "interval": interval, "startTime": cur,
                                                "limit": 1000}, base=BINANCE_VISION, retries=4, timeout=30)
        bars = parse_toobit_klines(rows)
        if not bars:
            break
        out.extend(b for b in bars if b["t"] + step <= end_ms)
        nxt = bars[-1]["t"] + step
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


def pick_universe_all() -> list[str]:
    """همهٔ جفت‌های USDT که تاکنون فهرست شده‌اند، شامل حذف‌شده‌ها (status=BREAK)."""
    d = http_get_json("/api/v3/exchangeInfo", base=BINANCE_VISION, timeout=60)
    out = {s["symbol"] for s in d.get("symbols", [])
           if s.get("quoteAsset") == "USDT" and str(s.get("status", "")).upper() in ("TRADING", "BREAK")
           and tradable_symbol(s["symbol"])}
    return ["BTCUSDT"] + sorted(out - {"BTCUSDT"})


def _run(series, quality, cfg, start_ts, end_ts, run_id, blocked=None):
    led = Ledger(None, run_id, cfg.sha())
    bot = MariBot(cfg, led)
    bot.blocked = blocked
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


def _evaluate(series, quality, cfg, start, end, tag, blocked=None):
    full, trades = _run(series, quality, cfg, start, end, f"{tag}-FULL", blocked)
    costs = {}
    for fee in (0.0, 0.0005, 0.001, 0.002, 0.003):
        c = replace(cfg, cost=CostParams(fee_side=fee, slippage=cfg.cost.slippage))
        m, _ = _run(series, quality, c, start, end, f"{tag}-FEE{fee}", blocked)
        costs[f"fee_side_{fee * 100:.2f}pct"] = {k: m[k] for k in ("trades", "net_return_pct", "profit_factor",
                                                                    "win_rate_pct", "max_drawdown_pct")}
    folds, a = [], start
    while a < end:
        b = min(a + 30 * DAY_MS, end)
        m, _ = _run(series, quality, cfg, a, b, f"{tag}-FOLD{len(folds)}", blocked)
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
    hyps = sorted(hyps, key=lambda h: bool(HYPOTHESES[h].get("blacklist")))   # گروه کنترل پیش از فهرست ممنوعه
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

    blocked, bl_info = None, None
    if any(HYPOTHESES[h].get("blacklist") for h in hyps):
        from .pattern import blacklist_fn, build_blacklist
        daily = {}
        for s in series:
            try:
                daily[s] = quality_check(fetch_history(s, start - 120 * DAY_MS, end, interval="1d"),
                                         interval_ms=DAY_MS)["clean"]
            except DataError:
                continue
        bl = build_blacklist({k: v for k, v in daily.items() if v})
        blocked = blacklist_fn(bl)
        bl_info = {"weeks": len(bl), "avg_blocked": round(sum(len(v) for v in bl.values()) / max(1, len(bl)), 1)}
    results, all_trades = {}, {}
    for hid in hyps:
        h = HYPOTHESES[hid]
        cfg = replace(base, risk=replace(base.risk, **h["risk_overrides"]))
        res, trades = _evaluate(series, quality, cfg, start, end, hid, blocked if h.get("blacklist") else None)
        if h.get("blacklist"):
            res["blacklist"] = bl_info
            ctrl = results.get("H-MARI-B-001", {}).get("full_period", {}).get("net_return_pct")
            if res["verdict"] == "SUPPORTED_IN_TEST_RANGE" and ctrl is not None \
                    and res["full_period"]["net_return_pct"] <= ctrl:
                res["verdict"] = "FALSIFIED"
                res["verdict_note"] = "معیار H-001 برقرار بود اما از گروه کنترل بهتر نبود."
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


def run_momentum_research(years: int = 5, top: int = 30, out_dir: str = "research_out",
                          start_ms: int | None = None, end_ms: int | None = None,
                          variants: tuple = ("H-MARI-M-003", "H-MARI-M-004")) -> dict:
    """فرضیه‌های مومنتوم روزانه روی یک دادهٔ مشترک."""
    from .momentum import (HYPOTHESIS_M003, HYPOTHESIS_M003_PIT, HYPOTHESIS_M004, HYPOTHESIS_M005,
                           HYPOTHESIS_T006, HYPOTHESIS_T006_ROBUST, MomParams, run_momentum)
    t6 = dict(only_symbols=("BTCUSDT",), max_hold=1, require_momentum=False, rebalance_weekday=-1, min_age_days=0)
    hyp = {"H-MARI-M-003": (HYPOTHESIS_M003, MomParams()),
           "H-MARI-M-004": (HYPOTHESIS_M004, MomParams(btc_sma_filter=200)),
           "H-MARI-M-003-PIT": (HYPOTHESIS_M003_PIT, MomParams(pit_top=30)),
           "H-MARI-M-003-PIT-H50": (HYPOTHESIS_M003_PIT, MomParams(pit_top=30, delist_haircut=0.5)),
           "H-MARI-M-004-PIT": (HYPOTHESIS_M004, MomParams(pit_top=30, btc_sma_filter=200)),
           "H-MARI-M-005-PIT": (HYPOTHESIS_M005, MomParams(pit_top=30, vol_target=0.40)),
           "H-MARI-T-006": (HYPOTHESIS_T006, MomParams(only_symbols=("BTCUSDT",), max_hold=1, sma=150,
                                                       require_momentum=False, rebalance_weekday=-1,
                                                       min_age_days=0)),
           "T006-SMA100": (HYPOTHESIS_T006_ROBUST, MomParams(sma=100, **t6)),
           "T006-SMA200": (HYPOTHESIS_T006_ROBUST, MomParams(sma=200, **t6)),
           "T006-LAG1": (HYPOTHESIS_T006_ROBUST, MomParams(sma=150, signal_lag=1, **t6)),
           "T006-FEE2X": (HYPOTHESIS_T006_ROBUST, MomParams(sma=150, fee_side=0.002, slippage=0.001, **t6)),
           "T006-LAG1-FEE2X-SMA200": (HYPOTHESIS_T006_ROBUST,
                                      MomParams(sma=200, signal_lag=1, fee_side=0.002, slippage=0.001, **t6))}
    end = (end_ms or int(time.time() * 1000)) // DAY_MS * DAY_MS
    start = (start_ms // DAY_MS * DAY_MS) if start_ms else end - years * 365 * DAY_MS
    warm = 260 * DAY_MS
    pit = any("PIT" in v for v in variants)
    btc_only = all(v.startswith(("H-MARI-T-006", "T006")) for v in variants)
    syms = ["BTCUSDT"] if btc_only else (pick_universe_all() if pit else pick_universe(top))
    daily, failed, lineage = {}, [], {}
    for s in syms:
        try:
            bars = fetch_history(s, start - warm, end, interval="1d")
            if not bars:
                continue
        except DataError as e:
            failed.append(f"{s}:{e}")
            continue
        q = quality_check(bars, interval_ms=DAY_MS)
        if q["n"] > 0:
            daily[s] = q["clean"]
            lineage[s] = {"bars": q["n"], "sha": bars_sha(q["clean"]), "first": q["clean"][0]["t"],
                          "issues": q["issues"]}
    results, curves = {}, {}
    for vid in variants:
        h, p = hyp[vid]
        res = run_momentum(daily, start, end, p)
        curves[vid] = res.pop("curve")
        results[vid] = {"hypothesis": h, **res}
    report = {
        "registered_before_results": True,
        "code": CODE_VERSION, "fetched_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "period": {"from": datetime.fromtimestamp(start / 1000, timezone.utc).isoformat(),
                   "to": datetime.fromtimestamp(end / 1000, timezone.utc).isoformat()},
        "source": BINANCE_VISION + "/api/v3/klines interval=1d (public, read-only)",
        "universe": {"requested_top": top, "used": len(daily),
                     "active_in_period": sum(1 for v in lineage.values() if v["first"] <= end - 60 * DAY_MS),
                     "failed": failed},
        "known_biases": [
            "SURVIVORSHIP (قوی): نمادها با حجم امروز انتخاب شدند؛ ارزهای مرده غایب‌اند — به نفع نتیجه.",
            "SAME_CLOSE_EXECUTION: تصمیم و اجرا با قیمت بستهٔ همان روز — کمی خوش‌بینانه.",
            "VENUE: تاریخچه از بایننس؛ اجرای احتمالی آینده در تووبیت.",
            "MULTIPLE_TESTS: تا این اجرا ۴ فرضیه آزموده شده.",
        ],
        "results": results, "lineage": lineage,
    }
    if btc_only:
        report["known_biases"][0] = ("SELECTION: فقط BTC — بزرگ‌ترین ارز در ۲۰۱۸ هم بود (انتخاب پیشاپیش ممکن)، "
                                     "اما بقای BTC تا امروز خودش یک واقعیت پس‌نگر است.")
    if pit:
        report["known_biases"][0] = ("SURVIVORSHIP (کاهش‌یافته): جهان هم‌زمان از همهٔ جفت‌های فهرست‌شده/حذف‌شدهٔ "
                                     "بایننس؛ نمادهایی که پیش از ثبت در exchangeInfo پاک شده‌اند هنوز غایب‌اند.")
        report["universe"]["listed_or_delisted_considered"] = len(syms)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "momentum_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(out_dir, "momentum_curve.json"), "w", encoding="utf-8") as fh:
        json.dump(curves, fh)
    md = ["# گزارش مومنتوم روزانه", "",
          f"- دوره: {report['period']['from'][:10]} تا {report['period']['to'][:10]} — نمادها: {len(daily)} "
          f"(فعال در دوره: {report['universe']['active_in_period']})", ""]
    for vid, r in results.items():
        st, bt = r["strategy"], r["btc_buy_hold"] or {}
        md += [f"## {vid} — حکم: **{r['verdict']}**", "", r["hypothesis"]["statement"], "",
               f"- شرط رد: {r['hypothesis']['falsified_if']}", "",
               "| شاخص | استراتژی | نگه‌داری BTC |", "|---|---|---|"]
        for k, label in (("total_return_pct", "بازده کل ٪"), ("cagr_pct", "بازده سالانه ٪"),
                         ("max_drawdown_pct", "بیشترین افت ٪"), ("sharpe", "شارپ")):
            md.append(f"| {label} | {st.get(k)} | {bt.get(k)} |")
        md += ["", f"- بوت‌استرپ میانگین بازده هفتگی: {st.get('weekly_bootstrap')}",
               f"- میانگین تعداد ارز: {r['avg_names_held']} — زمان کامل نقد: {r['time_in_cash_pct']}٪ — "
               f"نمادهای نگه‌داشته‌شده: {r['symbols_ever_held']} — خروج از نماد حذف‌شده: {r['delisted_exits']}",
               "", "| سال | بازده ٪ |", "|---|---|"]
        md += [f"| {y} | {v} |" for y, v in r["by_year_pct"].items()]
        md.append("")
    md += ["## سوگیری‌های شناخته‌شده", ""] + [f"- {b}" for b in report["known_biases"]]
    md += ["", "> همه‌چیز تمرینی است — بدون سفارش واقعی"]
    with open(os.path.join(out_dir, "momentum_report_fa.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    return report


def run_classics_research(start: str = "2018-06-01", out_dir: str = "research_out") -> dict:
    """روش‌های کلاسیک (C-007..C-009) + خرید پله‌ای (D-010) روی BTC/ETH روزانه."""
    from .classics import CLASSIC_HYPOTHESES, FALSIFIED_IF, run_classics
    start_ms = int(datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    end = int(time.time() * 1000) // DAY_MS * DAY_MS
    daily, lineage = {}, {}
    for s in ("BTCUSDT", "ETHUSDT"):
        bars = fetch_history(s, start_ms - 260 * DAY_MS, end, interval="1d")
        q = quality_check(bars, interval_ms=DAY_MS)
        daily[s] = q["clean"]
        lineage[s] = {"bars": q["n"], "sha": bars_sha(q["clean"]), "issues": q["issues"]}
    res = run_classics(daily, start_ms, end)
    report = {"registered_before_results": True, "falsified_if": FALSIFIED_IF, "hypotheses": CLASSIC_HYPOTHESES,
              "code": CODE_VERSION, "period": {"from": start, "to": datetime.fromtimestamp(end / 1000, timezone.utc)
                                               .strftime("%Y-%m-%d")},
              "execution": "تصمیم روی بستهٔ روز t، اجرا روی بستهٔ روز t+1؛ کارمزد ۰٫۱٪ + لغزش ۰٫۰۵٪",
              "known_biases": ["SELECTION: BTC و ETH بزرگ‌ترین ارزهای ۲۰۱۸ هم بودند، اما بقایشان پس‌نگر است.",
                               "MULTIPLE_TESTS: با این اجرا شمار فرضیه‌ها به ۱۰ می‌رسد."],
              "results": res, "lineage": lineage}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "classics_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    b = res["BTC_BUY_HOLD"]
    md = ["# روش‌های کلاسیک بزرگان بازار", "",
          f"- دوره: {report['period']['from']} تا {report['period']['to']} — {report['execution']}",
          f"- شرط رد (ثبت پیشاپیش): {FALSIFIED_IF}", "",
          "| روش | حکم | بازده کل ٪ | سالانه ٪ | بیشترین افت ٪ | شارپ | معامله | زمان نقد ٪ |",
          "|---|---|---|---|---|---|---|---|",
          f"| نگه‌داری BTC | — | {b['total_return_pct']} | {b['cagr_pct']} | {b['max_drawdown_pct']} | {b['sharpe']} "
          f"| {b['trades']} | {b['time_in_cash_pct']} |"]
    for hid in CLASSIC_HYPOTHESES:
        x = res[hid]
        md.append(f"| {hid} | **{x['verdict']}** | {x['total_return_pct']} | {x['cagr_pct']} | {x['max_drawdown_pct']} "
                  f"| {x['sharpe']} | {x['trades']} | {x['time_in_cash_pct']} |")
    md += ["", "## خرید پله‌ای هفتگی (توصیفی — ۱۰ دلار در هفته)", "",
           "| روش | هفته | سرمایه‌گذاری کل $ | ارزش نهایی $ | چند برابر | بیشترین افت ارزش ٪ |", "|---|---|---|---|---|---|"]
    for name, x in (("DCA ساده", res["D-010"]["dca_plain"]), ("DCA + فیلتر ۱۵۰روزه", res["D-010"]["dca_trend150"])):
        md.append(f"| {name} | {x['weeks']} | {x['invested']} | {x['final_value']} | {x['multiple']} | "
                  f"{x['max_drawdown_of_value_pct']} |")
    md += ["", "## سوگیری‌های شناخته‌شده", ""] + [f"- {k}" for k in report["known_biases"]]
    md += ["", "> همه‌چیز تمرینی است — بدون سفارش واقعی"]
    with open(os.path.join(out_dir, "classics_report_fa.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    return report


def run_macro_research(start: str = "2018-06-01", out_dir: str = "research_out") -> dict:
    """فیلترهای اقتصاد کلان آمریکا (X-011..X-014) روی BTC روزانه."""
    from .macro import LAGS, MACRO_HYPOTHESES, fetch_fred, net_liquidity, run_macro
    start_ms = int(datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    end = int(time.time() * 1000) // DAY_MS * DAY_MS
    bars = fetch_history("BTCUSDT", start_ms - 260 * DAY_MS, end, interval="1d")
    daily = {"BTCUSDT": quality_check(bars, interval_ms=DAY_MS)["clean"]}
    raw = {sid: fetch_fred(sid) for sid in ("DGS10", "DTWEXBGS", "WALCL", "WTREGEN", "RRPONTSYD")}
    macro = {"DGS10": raw["DGS10"], "DTWEXBGS": raw["DTWEXBGS"],
             "NETLIQ": net_liquidity(raw["WALCL"], raw["WTREGEN"], raw["RRPONTSYD"])}
    res = run_macro(daily, macro, start_ms, end)
    report = {"registered_before_results": True, "hypotheses": MACRO_HYPOTHESES, "publication_lags_days": LAGS,
              "source": "https://fred.stlouisfed.org/graph/fredgraph.csv (official, public)",
              "fred_last_obs": {k: datetime.fromtimestamp(v[-1][0] / 1000, timezone.utc).strftime("%Y-%m-%d")
                                for k, v in raw.items()},
              "period": {"from": start, "to": datetime.fromtimestamp(end / 1000, timezone.utc).strftime("%Y-%m-%d")},
              "known_biases": ["تاریخچهٔ FRED ممکن است بازنگری‌شده باشد (نه دقیقاً عدد منتشرشدهٔ همان روز).",
                               "MULTIPLE_TESTS: با این اجرا شمار فرضیه‌ها به ۱۴ می‌رسد."],
              "results": res}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "macro_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    md = ["# فیلترهای اقتصاد کلان آمریکا برای بیت‌کوین", "",
          f"- دوره: {report['period']['from']} تا {report['period']['to']} — منبع: FRED (رسمی)",
          f"- تأخیر انتشار اعمال‌شده (روز): {LAGS}", "",
          "| روش | حکم | بازده کل ٪ | سالانه ٪ | بیشترین افت ٪ | شارپ | معامله | زمان نقد ٪ |",
          "|---|---|---|---|---|---|---|---|"]
    for k in ["BTC_BUY_HOLD", "T-006_REFERENCE"] + list(MACRO_HYPOTHESES):
        x = res[k]
        md.append(f"| {k} | {x.get('verdict', '—')} | {x['total_return_pct']} | {x['cagr_pct']} | "
                  f"{x['max_drawdown_pct']} | {x['sharpe']} | {x['trades']} | {x['time_in_cash_pct']} |")
    md += ["", "## سوگیری‌های شناخته‌شده", ""] + [f"- {b}" for b in report["known_biases"]]
    md += ["", "> همه‌چیز تمرینی است — بدون سفارش واقعی"]
    with open(os.path.join(out_dir, "macro_report_fa.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    return report


def run_ict_research(start: str = "2018-06-01", out_dir: str = "research_out") -> dict:
    """ایدهٔ شکار نقدینگی ICT (ICT-015 مطالعهٔ رویداد، ICT-016 استراتژی) روی BTC و ETH روزانه."""
    from .ict import ICT_HYPOTHESES, run_ict
    start_ms = int(datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    end = int(time.time() * 1000) // DAY_MS * DAY_MS
    daily = {}
    for s in ("BTCUSDT", "ETHUSDT"):
        bars = fetch_history(s, start_ms - 30 * DAY_MS, end, interval="1d")
        daily[s] = quality_check(bars, interval_ms=DAY_MS)["clean"]
    res = run_ict(daily, start_ms, end)
    report = {"registered_before_results": True, "hypotheses": ICT_HYPOTHESES,
              "period": {"from": start, "to": datetime.fromtimestamp(end / 1000, timezone.utc).strftime("%Y-%m-%d")},
              "known_biases": ["MULTIPLE_TESTS: با این اجرا شمار فرضیه‌ها به ۱۶ می‌رسد.",
                               "بازده ۵روزهٔ رویدادها هم‌پوشانی دارند؛ بازهٔ اطمینان کمی خوش‌بینانه است."],
              "results": res}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "ict_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    md = ["# آزمون شکار نقدینگی (ICT)", "", f"- دوره: {report['period']['from']} تا {report['period']['to']}", ""]
    for hid, v in res["verdict"].items():
        md.append(f"- {hid}: **{v}** — {ICT_HYPOTHESES[hid]}")
    md += ["", "## مطالعهٔ رویداد (بازده ۵ روز بعد، اجرا یک روز دیرتر)", "",
           "| دارایی | همهٔ روزها ٪ | شکار کف: تعداد / میانگین ٪ / اختلاف [CI95] | شکار سقف: تعداد / میانگین ٪ / اختلاف [CI95] |",
           "|---|---|---|---|"]
    for sym, e in res["events"].items():
        def cell(x):
            v = x["vs_all"] or {}
            return f"{x['n']} / {x['mean_fwd5_pct']} / {v.get('diff_pct')} [{v.get('ci95_low')}, {v.get('ci95_high')}]"
        md.append(f"| {sym} | {e['mean_fwd5_all_pct']} | {cell(e['bull'])} | {cell(e['bear'])} |")
    md += ["", "## استراتژی خرید پس از شکار کف", "",
           "| دارایی | روش | بازده کل ٪ | بیشترین افت ٪ | شارپ | معامله | زمان نقد ٪ |", "|---|---|---|---|---|---|---|"]
    for sym, x in res["strategy"].items():
        for name, st in (("نگه‌داری", x["buy_hold"]), ("ICT خرید", x["ict_long"])):
            md.append(f"| {sym} | {name} | {st['total_return_pct']} | {st['max_drawdown_pct']} | {st['sharpe']} | "
                      f"{st['trades']} | {st['time_in_cash_pct']} |")
    md += ["", "> همه‌چیز تمرینی است — بدون سفارش واقعی"]
    with open(os.path.join(out_dir, "ict_report_fa.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    return report


def run_funding_research(start: str = "2020-06-01", out_dir: str = "research_out") -> dict:
    """نرخ فاندینگ (F-017 مطالعهٔ رویداد، F-018 فیلتر روی T-006) روی BTC و ETH روزانه."""
    from .funding import FUNDING_HYPOTHESES, WINDOW, fetch_funding, run_funding
    start_ms = int(datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    end = int(time.time() * 1000) // DAY_MS * DAY_MS
    pre = start_ms - (WINDOW + 30) * DAY_MS
    daily, funding, sources = {}, {}, {}
    for s in ("BTCUSDT", "ETHUSDT"):
        bars = fetch_history(s, min(pre, start_ms - 200 * DAY_MS), end, interval="1d")
        daily[s] = quality_check(bars, interval_ms=DAY_MS)["clean"]
        name, rows, tried = fetch_funding(s, pre - 10 * DAY_MS, end, need_from_ms=start_ms)
        funding[s], sources[s] = rows, {"used": name, "rows": len(rows), "failed_before": tried}
    res = run_funding(daily, funding, start_ms, end)
    report = {"registered_before_results": True, "registered_at": "2026-11-05T04:20Z",
              "hypotheses": FUNDING_HYPOTHESES, "sources": sources,
              "period": {"from": start, "to": datetime.fromtimestamp(end / 1000, timezone.utc).strftime("%Y-%m-%d")},
              "known_biases": ["MULTIPLE_TESTS: با این اجرا شمار فرضیه‌ها به ۱۸ می‌رسد.",
                               "بازده ۵روزه هم‌پوشانی دارد و روزهای شلوغ پشت‌سرهم‌اند؛ CI خوش‌بینانه است.",
                               "فاندینگ از صرافی فیوچرز و قیمت از اسپات است.",
                               "انحراف از ثبت: بایگانی بایننس از ۲۰۲۰-۰۱ شروع می‌شود؛ صدک ۱۸۰روزه تا حدود ۲۰۲۰-۰۷ آماده نیست، پس روزهای اول دوره بدون سیگنال‌اند."],
              "results": res}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "funding_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    md = ["# آزمون نرخ فاندینگ", "", f"- دوره: {report['period']['from']} تا {report['period']['to']}",
          f"- منبع: " + "، ".join(f"{k}: {v['used']} ({v['rows']} ردیف)" for k, v in sources.items()), ""]
    for hid, v in res["verdict"].items():
        md.append(f"- {hid}: **{v}** — {FUNDING_HYPOTHESES[hid]}")
    md += ["", "## مطالعهٔ رویداد (بازده ۵ روز بعد، اجرا یک روز دیرتر)", "",
           "| دارایی | همهٔ روزها ٪ | شلوغی خرید: تعداد / میانگین ٪ / اختلاف [CI95] | شلوغی فروش: تعداد / میانگین ٪ / اختلاف [CI95] |",
           "|---|---|---|---|"]
    for sym, e in res["events"].items():
        def cell(x):
            v = x["vs_all"] or {}
            return f"{x['n']} / {x['mean_fwd5_pct']} / {v.get('diff_pct')} [{v.get('ci95_low')}, {v.get('ci95_high')}]"
        md.append(f"| {sym} | {e['mean_fwd5_all_pct']} | {cell(e['crowded_long'])} | {cell(e['crowded_short'])} |")
    md += ["", "## راهبرد روی BTC", "", "| روش | بازده کل ٪ | بیشترین افت ٪ | شارپ | معامله | زمان نقد ٪ |",
           "|---|---|---|---|---|---|"]
    for name, st in res["strategy"].items():
        md.append(f"| {name} | {st['total_return_pct']} | {st['max_drawdown_pct']} | {st['sharpe']} | "
                  f"{st['trades']} | {st['time_in_cash_pct']} |")
    md += ["", "> همه‌چیز تمرینی است — بدون سفارش واقعی"]
    with open(os.path.join(out_dir, "funding_report_fa.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    return report


def run_pattern_research(out_dir: str = "research_out") -> dict:
    """الگوی مشترک پنهان (P-019، P-020): یادگیری ۲۰۲۱-۰۶..۲۰۲۳-۱۲، آزمون ۲۰۲۴-۰۱..اکنون."""
    from .pattern import PATTERN_HYPOTHESES, run_pattern

    def ms(d):
        return int(datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    end = int(time.time() * 1000) // DAY_MS * DAY_MS
    train, test = (ms("2021-06-01"), ms("2023-12-31")), (ms("2024-01-01"), end)
    syms = pick_universe_all()
    daily, failed = {}, []
    for s in syms:
        try:
            bars = fetch_history(s, train[0] - 220 * DAY_MS, end, interval="1d")
        except DataError as e:
            failed.append(f"{s}:{e}")
            continue
        if bars:
            q = quality_check(bars, interval_ms=DAY_MS)
            if q["n"] > 0:
                daily[s] = q["clean"]
    res = run_pattern(daily, train, test)
    report = {"registered_before_results": True, "registered_at": "2026-11-05T04:25Z",
              "hypotheses": PATTERN_HYPOTHESES,
              "period": {"train": "2021-06-01..2023-12-31",
                         "test": "2024-01-01.." + datetime.fromtimestamp(end / 1000, timezone.utc).strftime("%Y-%m-%d")},
              "universe": {"symbols_listed_ever": len(syms), "with_data": len(daily), "failed": len(failed)},
              "known_biases": ["SURVIVORSHIP: ارزهایی که پیش از دسترس‌پذیری بایگانی حذف شده‌اند در داده نیستند.",
                               "MULTIPLE_TESTS: شمار فرضیه‌ها به ۲۰ می‌رسد.",
                               "ارزی که وسط هفته بی‌داده شود با آخرین قیمت معلوم نقد فرض می‌شود (خوش‌بینانه)."],
              "results": res}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "pattern_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    md = ["# الگوی مشترک پنهان ارزهای صعودی", "",
          f"- یادگیری: {report['period']['train']} ({res['train_weeks']} هفته)",
          f"- آزمون دست‌نخورده: {report['period']['test']} ({res['test_weeks']} هفته، "
          f"میانگین {res['avg_universe_test']} ارز در هفته)", ""]
    for hid, v in res["verdict"].items():
        md.append(f"- {hid}: **{v}** — {PATTERN_HYPOTHESES[hid]}")
    md += ["", "## آنچه از دورهٔ یادگیری آموخته شد", "", "| ویژگی | IC میانگین | علامت | CI95 ٪ |", "|---|---|---|---|"]
    for f, x in res["learned"].items():
        ci = x["ci"] or {}
        md.append(f"| {f} | {x['mean_ic']} | {x['sign']:+d} | [{ci.get('ci95_low')}, {ci.get('ci95_high')}] |")
    ic = res["test_ic"]
    ci = ic["ci"] or {}
    md += ["", f"## آزمون: IC میانگین {ic['mean_ic']}، CI95٪ [{ci.get('ci95_low')}, {ci.get('ci95_high')}], "
           f"هفته‌های مثبت {ic['hit_weeks_pct']}٪", "",
           "| روش (دورهٔ آزمون) | بازده کل ٪ | بیشترین افت ٪ | شارپ | معامله |", "|---|---|---|---|---|"]
    for name, st in (("۵ ارز برتر + فیلتر BTC", res["strategy_test"]), ("T-006", res["t006_test"])):
        md.append(f"| {name} | {st.get('total_return_pct')} | {st.get('max_drawdown_pct')} | {st.get('sharpe')} | "
                  f"{st.get('trades')} |")
    dg = res["diagnostics_post_hoc"]
    md += ["", "## تشخیص پس از نتیجه (حکم را تغییر نمی‌دهد)", "",
           "بازده میانگین ۷ روز بعد هر پنجک امتیاز (Q1 بدترین، Q5 بهترین): " +
           "، ".join(f"{k}: {v}٪" for k, v in dg["quintile_mean_fwd7_pct"].items()),
           f"۵ ارز برتر: میانگین {dg['top5_mean_fwd7_pct']}٪، میانه {dg['top5_median_fwd7_pct']}٪", "",
           "| ارز پرتکرار در ۵ برتر | هفته | بازده میانگین ٪ |", "|---|---|---|"]
    md += [f"| {x['sym']} | {x['weeks']} | {x['mean_fwd7_pct']} |" for x in dg["most_picked"]]
    md += ["", "> همه‌چیز تمرینی است — بدون سفارش واقعی"]
    with open(os.path.join(out_dir, "pattern_report_fa.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    return report


def run_ideas_research(start: str = "2018-06-01", out_dir: str = "research_out") -> dict:
    """صف ایده‌ها ۱ و ۲: کنترل نوسان روی T-006 و تقاطع طلایی، روی BTC و ETH."""
    from .ideas import IDEA_HYPOTHESES, run_ideas
    start_ms = int(datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    end = int(time.time() * 1000) // DAY_MS * DAY_MS
    daily = {}
    for s in ("BTCUSDT", "ETHUSDT"):
        bars = fetch_history(s, start_ms - 260 * DAY_MS, end, interval="1d")
        daily[s] = quality_check(bars, interval_ms=DAY_MS)["clean"]
    res = run_ideas(daily, start_ms, end)
    report = {"registered_before_results": True, "registered_at": "2026-11-05T05:35Z",
              "hypotheses": IDEA_HYPOTHESES,
              "period": {"from": start, "to": datetime.fromtimestamp(end / 1000, timezone.utc).strftime("%Y-%m-%d")},
              "known_biases": ["MULTIPLE_TESTS: شمار فرضیه‌ها به ۲۳ می‌رسد؛ قاعدهٔ تکرار روی ETH اعمال شد."],
              "results": res}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "ideas_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    md = ["# صف ایده‌ها: کنترل نوسان و تقاطع طلایی", "", f"- دوره: {report['period']['from']} تا {report['period']['to']}", ""]
    for hid, v in res["verdict"].items():
        md.append(f"- {hid}: **{v}** — {IDEA_HYPOTHESES[hid]}")
    md += ["", "| دارایی | روش | بازده کل ٪ | CAGR ٪ | بیشترین افت ٪ | شارپ | معامله | زمان نقد ٪ |",
           "|---|---|---|---|---|---|---|---|"]
    for sym, x in res["by_asset"].items():
        for name, st in x.items():
            md.append(f"| {sym} | {name} | {st['total_return_pct']} | {st['cagr_pct']} | {st['max_drawdown_pct']} | "
                      f"{st['sharpe']} | {st['trades']} | {st['time_in_cash_pct']} |")
    md += ["", "> همه‌چیز تمرینی است — بدون سفارش واقعی"]
    with open(os.path.join(out_dir, "ideas_report_fa.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    return report


def run_ideas2_research(start: str = "2018-06-01", out_dir: str = "research_out") -> dict:
    """صف ایده‌ها ۳ و ۴: چرخهٔ هاوینگ و اثر روز هفته، روی BTC و ETH."""
    from .ideas import IDEA2_HYPOTHESES, run_ideas2
    start_ms = int(datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    end = int(time.time() * 1000) // DAY_MS * DAY_MS
    daily = {}
    for s in ("BTCUSDT", "ETHUSDT"):
        bars = fetch_history(s, start_ms - 260 * DAY_MS, end, interval="1d")
        daily[s] = quality_check(bars, interval_ms=DAY_MS)["clean"]
    res = run_ideas2(daily, start_ms, end)
    report = {"registered_before_results": True, "registered_at": "2026-11-05T05:45Z",
              "hypotheses": IDEA2_HYPOTHESES,
              "period": {"from": start, "to": datetime.fromtimestamp(end / 1000, timezone.utc).strftime("%Y-%m-%d")},
              "known_biases": ["MULTIPLE_TESTS: شمار فرضیه‌ها به ۲۵ می‌رسد.",
                               "هاوینگ: فقط دو رویداد در دوره؛ توان آماری کم."],
              "results": res}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "ideas2_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    days_fa = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"]
    md = ["# صف ایده‌ها: چرخهٔ هاوینگ و روز هفته", "", f"- دوره: {report['period']['from']} تا {report['period']['to']}", ""]
    for hid, v in res["verdict"].items():
        md.append(f"- {hid}: **{v}** — {IDEA2_HYPOTHESES[hid]}")
    md += ["", "## هاوینگ", "", "| دارایی | روش | بازده کل ٪ | بیشترین افت ٪ | شارپ | زمان نقد ٪ |", "|---|---|---|---|---|---|"]
    for sym, x in res["halving"].items():
        for name, st in x.items():
            md.append(f"| {sym} | {name} | {st['total_return_pct']} | {st['max_drawdown_pct']} | {st['sharpe']} | "
                      f"{st['time_in_cash_pct']} |")
    wb = res["weekday"]["BTCUSDT"]
    md += ["", f"## روز هفته — روز برتر دورهٔ کشف: {days_fa[wb['best_day']]}", "",
           "میانگین بازده روزانهٔ BTC در دورهٔ کشف: " +
           "، ".join(f"{days_fa[int(w)]} {m}٪" for w, m in wb["discovery_means_pct"].items()), "",
           "| دارایی | تعداد روز آزمون | اختلاف با میانگین ٪ [CI95] |", "|---|---|---|"]
    for sym, w in res["weekday"].items():
        v = w["test_vs_all"] or {}
        md.append(f"| {sym} | {w['test_n']} | {v.get('diff_pct')} [{v.get('ci95_low')}, {v.get('ci95_high')}] |")
    md += ["", "> همه‌چیز تمرینی است — بدون سفارش واقعی"]
    with open(os.path.join(out_dir, "ideas2_report_fa.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    return report


def run_ideas3_research(start: str = "2018-06-01", out_dir: str = "research_out") -> dict:
    """صف ایده‌ها ۵ و ۶: شکست نوسانی ویلیامز و فشردگی بولینگر، روی BTC و ETH."""
    from .ideas import IDEA3_HYPOTHESES, run_ideas3
    start_ms = int(datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    end = int(time.time() * 1000) // DAY_MS * DAY_MS
    daily = {}
    for s in ("BTCUSDT", "ETHUSDT"):
        bars = fetch_history(s, start_ms - 260 * DAY_MS, end, interval="1d")
        daily[s] = quality_check(bars, interval_ms=DAY_MS)["clean"]
    res = run_ideas3(daily, start_ms, end)
    report = {"registered_before_results": True, "registered_at": "2026-11-05T06:00Z",
              "hypotheses": IDEA3_HYPOTHESES,
              "period": {"from": start, "to": datetime.fromtimestamp(end / 1000, timezone.utc).strftime("%Y-%m-%d")},
              "known_biases": ["MULTIPLE_TESTS: شمار فرضیه‌ها به ۲۷ می‌رسد.",
                               "L-026: پر شدن دقیق در سطح شکست با دادهٔ روزانه خوش‌بینانه است."],
              "results": res}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "ideas3_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    md = ["# صف ایده‌ها: لری ویلیامز و فشردگی بولینگر", "",
          f"- دوره: {report['period']['from']} تا {report['period']['to']}", ""]
    for hid, v in res["verdict"].items():
        md.append(f"- {hid}: **{v}** — {IDEA3_HYPOTHESES[hid]}")
    md += ["", "| دارایی | روش | بازده کل ٪ | CAGR ٪ | بیشترین افت ٪ | شارپ | معامله |", "|---|---|---|---|---|---|---|"]
    for sym, x in res["by_asset"].items():
        for name, st in x.items():
            md.append(f"| {sym} | {name} | {st.get('total_return_pct')} | {st.get('cagr_pct')} | "
                      f"{st.get('max_drawdown_pct')} | {st.get('sharpe')} | {st.get('trades')} |")
    md += ["", "> همه‌چیز تمرینی است — بدون سفارش واقعی"]
    with open(os.path.join(out_dir, "ideas3_report_fa.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    return report


def run_ideas4_research(start: str = "2018-06-01", out_dir: str = "research_out") -> dict:
    """صف ایده‌ها ۷ و ۸: قالب روند مینروینی و جام مقدس راشکی، روی BTC و ETH."""
    from .ideas import IDEA4_HYPOTHESES, run_ideas4
    start_ms = int(datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    end = int(time.time() * 1000) // DAY_MS * DAY_MS
    daily = {}
    for s in ("BTCUSDT", "ETHUSDT"):
        bars = fetch_history(s, start_ms - 420 * DAY_MS, end, interval="1d")
        daily[s] = quality_check(bars, interval_ms=DAY_MS)["clean"]
    res = run_ideas4(daily, start_ms, end)
    report = {"registered_before_results": True, "registered_at": "2026-11-05T06:10Z",
              "hypotheses": IDEA4_HYPOTHESES,
              "period": {"from": start, "to": datetime.fromtimestamp(end / 1000, timezone.utc).strftime("%Y-%m-%d")},
              "known_biases": ["MULTIPLE_TESTS: شمار فرضیه‌ها به ۲۹ می‌رسد."],
              "results": res}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "ideas4_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    md = ["# صف ایده‌ها: مینروینی و راشکی", "", f"- دوره: {report['period']['from']} تا {report['period']['to']}", ""]
    for hid, v in res["verdict"].items():
        md.append(f"- {hid}: **{v}** — {IDEA4_HYPOTHESES[hid]}")
    md += ["", "| دارایی | روش | بازده کل ٪ | CAGR ٪ | بیشترین افت ٪ | شارپ | معامله | زمان نقد ٪ |",
           "|---|---|---|---|---|---|---|---|"]
    for sym, x in res["by_asset"].items():
        for name, st in x.items():
            md.append(f"| {sym} | {name} | {st.get('total_return_pct')} | {st.get('cagr_pct')} | "
                      f"{st.get('max_drawdown_pct')} | {st.get('sharpe')} | {st.get('trades')} | {st.get('time_in_cash_pct')} |")
    md += ["", "> همه‌چیز تمرینی است — بدون سفارش واقعی"]
    with open(os.path.join(out_dir, "ideas4_report_fa.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    return report


def run_ideas5_research(start: str = "2018-06-01", out_dir: str = "research_out") -> dict:
    """صف ایده‌ها ۹ و ۱۰: صفحهٔ سه‌گانهٔ الدر و KAMA کافمن، روی BTC و ETH."""
    from .ideas import IDEA5_HYPOTHESES, run_ideas5
    start_ms = int(datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    end = int(time.time() * 1000) // DAY_MS * DAY_MS
    daily = {}
    for s in ("BTCUSDT", "ETHUSDT"):
        bars = fetch_history(s, start_ms - 420 * DAY_MS, end, interval="1d")
        daily[s] = quality_check(bars, interval_ms=DAY_MS)["clean"]
    res = run_ideas5(daily, start_ms, end)
    report = {"registered_before_results": True, "registered_at": "2026-11-05T06:20Z",
              "hypotheses": IDEA5_HYPOTHESES,
              "period": {"from": start, "to": datetime.fromtimestamp(end / 1000, timezone.utc).strftime("%Y-%m-%d")},
              "known_biases": ["MULTIPLE_TESTS: شمار فرضیه‌ها به ۳۱ می‌رسد."],
              "results": res}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "ideas5_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    md = ["# صف ایده‌ها: الدر و کافمن", "", f"- دوره: {report['period']['from']} تا {report['period']['to']}", ""]
    for hid, v in res["verdict"].items():
        md.append(f"- {hid}: **{v}** — {IDEA5_HYPOTHESES[hid]}")
    md += ["", "| دارایی | روش | بازده کل ٪ | CAGR ٪ | بیشترین افت ٪ | شارپ | معامله | زمان نقد ٪ |",
           "|---|---|---|---|---|---|---|---|"]
    for sym, x in res["by_asset"].items():
        for name, st in x.items():
            md.append(f"| {sym} | {name} | {st.get('total_return_pct')} | {st.get('cagr_pct')} | "
                      f"{st.get('max_drawdown_pct')} | {st.get('sharpe')} | {st.get('trades')} | {st.get('time_in_cash_pct')} |")
    md += ["", "> همه‌چیز تمرینی است — بدون سفارش واقعی"]
    with open(os.path.join(out_dir, "ideas5_report_fa.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    return report


def run_ideas6_research(start: str = "2018-06-01", out_dir: str = "research_out") -> dict:
    """صف ایده‌ها ۱۱: چرخش BTC/ETH با نسبت ETH/BTC، در دو دورهٔ جدا."""
    from .ideas import IDEA6_HYPOTHESES, run_ideas6
    start_ms = int(datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    end = int(time.time() * 1000) // DAY_MS * DAY_MS
    daily = {}
    for s in ("BTCUSDT", "ETHUSDT"):
        bars = fetch_history(s, start_ms - 260 * DAY_MS, end, interval="1d")
        daily[s] = quality_check(bars, interval_ms=DAY_MS)["clean"]
    res = run_ideas6(daily, start_ms, end)
    report = {"registered_before_results": True, "registered_at": "2026-11-05T06:30Z",
              "hypotheses": IDEA6_HYPOTHESES,
              "period": {"from": start, "to": datetime.fromtimestamp(end / 1000, timezone.utc).strftime("%Y-%m-%d")},
              "known_biases": ["MULTIPLE_TESTS: شمار فرضیه‌ها به ۳۲ می‌رسد.",
                               "نسبت ETH/BTC جانشین دامیننس است، نه خود آن."],
              "results": res}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "ideas6_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    md = ["# صف ایده‌ها: چرخش بیت‌کوین و آلت‌کوین", ""]
    for hid, v in res["verdict"].items():
        md.append(f"- {hid}: **{v}** — {IDEA6_HYPOTHESES[hid]}")
    md += ["", "| دوره | روش | بازده کل ٪ | CAGR ٪ | بیشترین افت ٪ | شارپ | معامله | زمان نقد ٪ |",
           "|---|---|---|---|---|---|---|---|"]
    for per, x in res["by_period"].items():
        for name, st in x.items():
            md.append(f"| {per} | {name} | {st.get('total_return_pct')} | {st.get('cagr_pct')} | "
                      f"{st.get('max_drawdown_pct')} | {st.get('sharpe')} | {st.get('trades')} | {st.get('time_in_cash_pct')} |")
    md += ["", "> همه‌چیز تمرینی است — بدون سفارش واقعی"]
    with open(os.path.join(out_dir, "ideas6_report_fa.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    return report


def run_replication_research(start: str = "2018-06-01", out_dir: str = "research_out") -> dict:
    """آزمون تکرار T-006 و لاک‌پشت روی ETH (قاعدهٔ تکرار برای روش‌های قبول‌شده)."""
    from .ideas import REP_HYPOTHESES, run_replication
    start_ms = int(datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    end = int(time.time() * 1000) // DAY_MS * DAY_MS
    bars = fetch_history("ETHUSDT", start_ms - 260 * DAY_MS, end, interval="1d")
    daily = {"ETHUSDT": quality_check(bars, interval_ms=DAY_MS)["clean"]}
    res = run_replication(daily, start_ms, end)
    report = {"registered_before_results": True, "registered_at": "2026-11-05T06:45Z",
              "hypotheses": REP_HYPOTHESES,
              "period": {"from": start, "to": datetime.fromtimestamp(end / 1000, timezone.utc).strftime("%Y-%m-%d")},
              "results": res}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "replication_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    md = ["# آزمون تکرار روش‌های قبول‌شده روی ETH", ""]
    for hid, v in res["verdict"].items():
        md.append(f"- {hid}: **{v}** — {REP_HYPOTHESES[hid]}")
    md += ["", "| روش | بازده کل ٪ | بیشترین افت ٪ | شارپ | CI95 هفتگی ٪ | معامله |", "|---|---|---|---|---|---|"]
    for name, st in res["strategies"].items():
        ci = st.get("weekly_bootstrap") or {}
        md.append(f"| {name} | {st['total_return_pct']} | {st['max_drawdown_pct']} | {st['sharpe']} | "
                  f"[{ci.get('ci95_low')}, {ci.get('ci95_high')}] | {st['trades']} |")
    md += ["", "> همه‌چیز تمرینی است — بدون سفارش واقعی"]
    with open(os.path.join(out_dir, "replication_report_fa.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    return report


def run_market_research(start: str = "2021-01-01", out_dir: str = "research_out") -> dict:
    """روند بلندمدت روی ۱۰ ارز بزرگ: T-033، V-034، T-035."""
    from .ideas import LARGE_CAPS, MARKET_HYPOTHESES, run_market
    start_ms = int(datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    end = int(time.time() * 1000) // DAY_MS * DAY_MS
    daily = {}
    for s in ("BTCUSDT",) + LARGE_CAPS:
        bars = fetch_history(s, start_ms - 200 * DAY_MS, end, interval="1d")
        daily[s] = quality_check(bars, interval_ms=DAY_MS)["clean"]
    res = run_market(daily, start_ms, end)
    report = {"registered_before_results": True, "registered_at": "2026-11-05T06:55Z",
              "hypotheses": MARKET_HYPOTHESES,
              "period": {"from": start, "to": datetime.fromtimestamp(end / 1000, timezone.utc).strftime("%Y-%m-%d")},
              "known_biases": ["SURVIVORSHIP: ارزهای بزرگ امروز انتخاب شدند (به نفع نتیجه).",
                               "MULTIPLE_TESTS: شمار فرضیه‌ها به ۳۷ می‌رسد."],
              "results": res}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "market_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    md = ["# روند بلندمدت روی ۱۰ ارز بزرگ", "", f"- دوره: {report['period']['from']} تا {report['period']['to']}",
          f"- T-006 بهتر از نگه‌داری: {res['wins']['T-033']} از ۱۰؛ کنترل نوسان بهتر از T-006: {res['wins']['V-034']} از ۱۰", ""]
    for hid, v in res["verdict"].items():
        md.append(f"- {hid}: **{v}** — {MARKET_HYPOTHESES[hid]}")
    md += ["", "| ارز | نگه‌داری: بازده ٪ / افت ٪ / شارپ | T-006: بازده ٪ / افت ٪ / شارپ | کنترل نوسان: بازده ٪ / افت ٪ / شارپ |",
           "|---|---|---|---|"]
    def c(st):
        return f"{st['total_return_pct']} / {st['max_drawdown_pct']} / {st['sharpe']}"
    for sym, x in res["per_coin"].items():
        md.append(f"| {sym} | {c(x['hold'])} | {c(x['T-006'])} | {c(x['voltarget'])} |")
    md += ["", f"**سبد روند (۱۱ ارز):** {c(res['basket'])}", f"**T-006 روی BTC:** {c(res['btc_t006'])}",
           "", "> همه‌چیز تمرینی است — بدون سفارش واقعی"]
    with open(os.path.join(out_dir, "market_report_fa.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    return report


def run_sessions_research(start: str = "2021-01-01", out_dir: str = "research_out") -> dict:
    """خوشهٔ B سند مادر: AMD و سشن‌ها روی کندل ساعتی BTC و ETH."""
    from .sessions import SESSION_HYPOTHESES, run_sessions
    start_ms = int(datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    end = int(time.time() * 1000) // DAY_MS * DAY_MS
    hourly = {}
    for s in ("BTCUSDT", "ETHUSDT"):
        bars = fetch_history(s, start_ms - 70 * DAY_MS, end, interval="1h")
        hourly[s] = quality_check(bars)["clean"]
    res = run_sessions(hourly, start_ms, end)
    report = {"registered_before_results": True, "registered_at": "2026-11-05T07:05Z",
              "hypotheses": SESSION_HYPOTHESES,
              "period": {"from": start, "to": datetime.fromtimestamp(end / 1000, timezone.utc).strftime("%Y-%m-%d")},
              "known_biases": ["MULTIPLE_TESTS: شمار فرضیه‌ها به ۳۹ می‌رسد.",
                               "روزهایی که یکی از سشن‌ها ساعت گمشده دارد کنار گذاشته می‌شوند."],
              "results": res}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "sessions_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    md = ["# خوشهٔ B: AMD و سشن‌ها", "", f"- دوره: {report['period']['from']} تا {report['period']['to']}", ""]
    for hid, v in res["verdict"].items():
        md.append(f"- {hid}: **{v}** — {SESSION_HYPOTHESES[hid]}")
    md += ["", "## S-036: بازده نیویورک پس از شکار محدودهٔ آسیا", "",
           "| دارایی | روز | میانگین نیویورک ٪ | شکار کف: تعداد / اختلاف ٪ [CI95] | شکار سقف: تعداد / اختلاف ٪ [CI95] |",
           "|---|---|---|---|---|"]
    for sym, x in res["by_asset"].items():
        a = x["S-036"]
        def cell(e):
            v = e["vs_all"] or {}
            return f"{e['n']} / {v.get('diff_pct')} [{v.get('ci95_low')}, {v.get('ci95_high')}]"
        md.append(f"| {sym} | {a['n_days']} | {a['mean_ny_pct']} | {cell(a['bull'])} | {cell(a['bear'])} |")
    md += ["", "## S-037: نرخ درستی «نیویورک خلاف لندن» پس از آسیای آرام", "",
           "| دارایی | تعداد | نرخ درستی ٪ | CI95 ٪ |", "|---|---|---|---|"]
    for sym, x in res["by_asset"].items():
        h = x["S-037"]["hit"] or {}
        md.append(f"| {sym} | {h.get('n')} | {h.get('rate_pct')} | [{h.get('ci95_low')}, {h.get('ci95_high')}] |")
    md += ["", "> همه‌چیز تمرینی است — بدون سفارش واقعی"]
    with open(os.path.join(out_dir, "sessions_report_fa.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    return report


def run_ideas7_research(start: str = "2018-06-01", out_dir: str = "research_out") -> dict:
    """ideas7: روند چندسرعته (E-040) و اثر اول ماه (M-041) روی BTC و ETH."""
    from .ideas7 import IDEA7_HYPOTHESES, run_ideas7
    start_ms = int(datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    end = int(time.time() * 1000) // DAY_MS * DAY_MS
    daily = {}
    for s in ("BTCUSDT", "ETHUSDT"):
        bars = fetch_history(s, start_ms - 260 * DAY_MS, end, interval="1d")
        daily[s] = quality_check(bars, interval_ms=DAY_MS)["clean"]
    res = run_ideas7(daily, start_ms, end)
    report = {"registered_before_results": True, "registered_at": "2026-11-05T13:55Z",
              "hypotheses": IDEA7_HYPOTHESES,
              "period": {"from": start, "to": datetime.fromtimestamp(end / 1000, timezone.utc).strftime("%Y-%m-%d")},
              "known_biases": ["MULTIPLE_TESTS: شمار فرضیه‌ها به ۴۱ می‌رسد.",
                               "E-040 میانگین ۱۵۰ را به‌عنوان یکی از چهار داور دارد؛ به T-006 وابسته است."],
              "results": res}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "ideas7_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    md = ["# ideas7: روند چندسرعته و اثر اول ماه", "", f"- دوره: {report['period']['from']} تا {report['period']['to']}", ""]
    for hid, v in res["verdict"].items():
        md.append(f"- {hid}: **{v}** — {IDEA7_HYPOTHESES[hid]}")
    md += ["", "| دارایی | روش | بازده کل ٪ | بیشترین افت ٪ | شارپ | معامله | روز نقد ٪ |", "|---|---|---|---|---|---|---|"]
    for sym, x in res["by_asset"].items():
        for name in ("T-006", "H-MARI-E-040", "TOM_ONLY_INFO"):
            st = x[name]
            md.append(f"| {sym} | {name} | {st.get('total_return_pct')} | {st.get('max_drawdown_pct')} | "
                      f"{st.get('sharpe')} | {st.get('trades')} | {st.get('time_in_cash_pct')} |")
    md += ["", "## M-041: بازده روزانه در پنجرهٔ اول ماه", "",
           "| دارایی | روز پنجره | روز دیگر | میانگین پنجره ٪ | میانگین بقیه ٪ | اختلاف ٪ [CI95] |", "|---|---|---|---|---|---|"]
    for sym, x in res["by_asset"].items():
        t = x["H-MARI-M-041"]
        ci = t["tom_minus_rest"] or {}
        md.append(f"| {sym} | {t['n_tom']} | {t['n_rest']} | {t['tom_mean_pct']} | {t['rest_mean_pct']} | "
                  f"{ci.get('diff_pct')} [{ci.get('ci95_low')}, {ci.get('ci95_high')}] |")
    md += ["", "> همه‌چیز تمرینی است — بدون سفارش واقعی"]
    with open(os.path.join(out_dir, "ideas7_report_fa.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    return report


def run_ideas8_research(start: str = "2018-06-01", out_dir: str = "research_out") -> dict:
    """ideas8: ترس و طمع (F-044)، اثر هالووین (S-045)، حد ضرر متحرک روی T-006 (K-046)."""
    from .ideas8 import IDEA8_HYPOTHESES, fetch_fng, run_ideas8
    start_ms = int(datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    end = int(time.time() * 1000) // DAY_MS * DAY_MS
    daily = {}
    for s in ("BTCUSDT", "ETHUSDT"):
        bars = fetch_history(s, start_ms - 260 * DAY_MS, end, interval="1d")
        daily[s] = quality_check(bars, interval_ms=DAY_MS)["clean"]
    fng = fetch_fng()
    res = run_ideas8(daily, fng, start_ms, end)
    report = {"registered_before_results": True, "registered_at": "2026-11-05T17:05Z",
              "hypotheses": IDEA8_HYPOTHESES,
              "period": {"from": start, "to": datetime.fromtimestamp(end / 1000, timezone.utc).strftime("%Y-%m-%d")},
              "known_biases": ["MULTIPLE_TESTS: شمار فرضیه‌ها به ۴۶ می‌رسد.",
                               "شاخص ترس و طمع یک شاخص برای کل بازار است (بیشتر بر پایهٔ BTC)؛ ETH تکرار مستقل کامل نیست.",
                               "K-046 به T-006 وابسته است."],
              "results": res}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "ideas8_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    md = ["# ideas8: ترس و طمع، اثر هالووین، حد ضرر متحرک", "",
          f"- دوره: {report['period']['from']} تا {report['period']['to']}",
          f"- دادهٔ ترس و طمع: {res['fng_points']} روز از {res['fng_first']}", ""]
    for hid, v in res["verdict"].items():
        md.append(f"- {hid}: **{v}** — {IDEA8_HYPOTHESES[hid]}")
    md += ["", "| دارایی | روش | بازده کل ٪ | بیشترین افت ٪ | شارپ | معامله | روز نقد ٪ |", "|---|---|---|---|---|---|---|"]
    for sym, x in res["by_asset"].items():
        for name in ("BUY_HOLD", "T-006", "H-MARI-F-044", "H-MARI-K-046", "WINTER_ONLY_INFO"):
            st = x[name]
            md.append(f"| {sym} | {name} | {st.get('total_return_pct')} | {st.get('max_drawdown_pct')} | "
                      f"{st.get('sharpe')} | {st.get('trades')} | {st.get('time_in_cash_pct')} |")
    md += ["", "## S-045: بازده روزانه، زمستان (نوامبر-آوریل) در برابر تابستان", "",
           "| دارایی | روز زمستان | روز تابستان | میانگین زمستان ٪ | میانگین تابستان ٪ | اختلاف ٪ [CI95] |", "|---|---|---|---|---|---|"]
    for sym, x in res["by_asset"].items():
        t = x["H-MARI-S-045"]
        ci = t["winter_minus_summer"] or {}
        md.append(f"| {sym} | {t['n_winter']} | {t['n_summer']} | {t['winter_mean_pct']} | {t['summer_mean_pct']} | "
                  f"{ci.get('diff_pct')} [{ci.get('ci95_low')}, {ci.get('ci95_high')}] |")
    md += ["", "> همه‌چیز تمرینی است — بدون سفارش واقعی"]
    with open(os.path.join(out_dir, "ideas8_report_fa.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    return report


def run_ideas9_research(start: str = "2018-06-01", alt_start: str = "2021-01-01", out_dir: str = "research_out") -> dict:
    """ideas9: استحکام T-006 (R-048)، T-006 هفتگی (W-049)، سبد ۱۱ ارزی با دروازهٔ BTC (A-047)."""
    from .ideas import LARGE_CAPS
    from .ideas9 import IDEA9_HYPOTHESES, run_a, run_r_w, verdicts
    ms = lambda d: int(datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)  # noqa: E731
    start_ms, alt_ms = ms(start), ms(alt_start)
    end = int(time.time() * 1000) // DAY_MS * DAY_MS
    daily = {}
    for s in ("BTCUSDT", "ETHUSDT") + LARGE_CAPS:
        s0 = start_ms if s in ("BTCUSDT", "ETHUSDT") else alt_ms
        bars = fetch_history(s, s0 - 260 * DAY_MS, end, interval="1d")
        daily[s] = quality_check(bars, interval_ms=DAY_MS)["clean"]
    rw = run_r_w(daily, start_ms, end)
    a = run_a(daily, alt_ms, end)
    res = {"by_asset": rw["by_asset"], "basket": a["basket"], "btc_t006_alt_period": a["btc_t006"],
           "verdict": verdicts(rw, a)}
    report = {"registered_before_results": True, "registered_at": "2026-11-05T17:20Z",
              "hypotheses": IDEA9_HYPOTHESES,
              "period": {"from": start, "alt_from": alt_start,
                         "to": datetime.fromtimestamp(end / 1000, timezone.utc).strftime("%Y-%m-%d")},
              "known_biases": ["MULTIPLE_TESTS: شمار فرضیه‌ها به ۵۰ می‌رسد.",
                               "SURVIVORSHIP در A-047: ارزهای بزرگ امروز انتخاب شدند (به نفع نتیجه)."],
              "results": res}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "ideas9_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    md = ["# ideas9: استحکام روش روند، نسخهٔ هفتگی، سبد ۱۱ ارزی", "",
          f"- دوره: {start} تا {report['period']['to']} (سبد از {alt_start})", ""]
    for hid, v in res["verdict"].items():
        md.append(f"- {hid}: **{v}** — {IDEA9_HYPOTHESES[hid]}")
    md += ["", "| دارایی | روش | بازده کل ٪ | بیشترین افت ٪ | شارپ | معامله | روز نقد ٪ |", "|---|---|---|---|---|---|---|"]
    rows = [(sym, name, st) for sym, x in res["by_asset"].items() for name, st in x.items()]
    rows += [("BTC+10", "A-047 سبد", res["basket"]), ("BTCUSDT", "T-006 (از ۲۰۲۱)", res["btc_t006_alt_period"])]
    for sym, name, st in rows:
        md.append(f"| {sym} | {name} | {st.get('total_return_pct')} | {st.get('max_drawdown_pct')} | "
                  f"{st.get('sharpe')} | {st.get('trades')} | {st.get('time_in_cash_pct')} |")
    md += ["", "> همه‌چیز تمرینی است — بدون سفارش واقعی"]
    with open(os.path.join(out_dir, "ideas9_report_fa.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    return report


def run_ideas10_research(start: str = "2020-06-01", out_dir: str = "research_out") -> dict:
    """ideas10: عامل روند کریپتو (C-051) و نزدیکی به سقف ۵۲ هفته (N-052)، بین‌مقطعی، شامل ارزهای حذف‌شده."""
    from .ideas10 import IDEA10_HYPOTHESES, run_ideas10
    start_ms = int(datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    end = int(time.time() * 1000) // DAY_MS * DAY_MS
    syms = pick_universe_all()
    daily, failed = {}, []
    for s in syms:
        try:
            bars = fetch_history(s, start_ms - 400 * DAY_MS, end, interval="1d")
        except DataError as e:
            failed.append(f"{s}:{e}")
            continue
        if bars:
            q = quality_check(bars, interval_ms=DAY_MS)
            if q["n"] > 0:
                daily[s] = q["clean"]
    res = run_ideas10(daily, start_ms, end)
    report = {"registered_before_results": True, "registered_at": "2026-11-05T17:22Z",
              "hypotheses": IDEA10_HYPOTHESES,
              "period": {"from": start, "to": datetime.fromtimestamp(end / 1000, timezone.utc).strftime("%Y-%m-%d")},
              "data": {"symbols_listed_incl_delisted": len(syms), "symbols_with_data": len(daily),
                       "failed": len(failed), "failed_sample": failed[:10]},
              "known_biases": ["MULTIPLE_TESTS: شمار فرضیه‌ها به ۵۲ می‌رسد.",
                               "C-051 نسخهٔ ساده‌شدهٔ مقاله است (۷ میانگین قیمت به جای ۲۸ سیگنال و elastic net).",
                               "فقط خرید؛ مقاله‌ها بازده خرید-فروش را گزارش می‌کنند.",
                               "ارزهایی که پیش از حذف هیچ داده‌ای در API عمومی ندارند، دیده نمی‌شوند."],
              "results": res}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "ideas10_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    md = ["# ideas10: عامل روند کریپتو و سقف ۵۲ هفته", "",
          f"- دوره: {start} تا {report['period']['to']} — {res['mondays']} هفته",
          f"- نمادها: {len(syms)} فهرست‌شده (شامل حذف‌شده)، {len(daily)} با داده", ""]
    for hid, v in res["verdict"].items():
        md.append(f"- {hid}: **{v}** — {IDEA10_HYPOTHESES[hid]}")
    md += ["", "| فرضیه | اضافهٔ هفتگی ٪ [CI95] | نیمهٔ اول ٪ | نیمهٔ دوم ٪ | با ضرر ۵۰٪ حذف ٪ | سبد: بازده / افت / شارپ | وزن برابر: بازده / افت / شارپ | با دروازهٔ BTC: بازده / افت / شارپ |",
           "|---|---|---|---|---|---|---|---|"]
    f = lambda c: f"{c.get('total_return_pct')} / {c.get('max_drawdown_pct')} / {c.get('sharpe')}"  # noqa: E731
    for hid, e in res["by_hypothesis"].items():
        a = e["excess_all"] or {}
        md.append(f"| {hid} | {a.get('mean_pct')} [{a.get('ci95_low')}, {a.get('ci95_high')}] | "
                  f"{(e['excess_first_half'] or {}).get('mean_pct')} | {(e['excess_second_half'] or {}).get('mean_pct')} | "
                  f"{(e['haircut50_excess_all'] or {}).get('mean_pct')} | {f(e['top'])} | {f(e['ew'])} | {f(e['btc_gated_info'])} |")
    md += ["", "> همه‌چیز تمرینی است — بدون سفارش واقعی"]
    with open(os.path.join(out_dir, "ideas10_report_fa.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    return report


def run_ideas11_research(start: str = "2020-06-01", out_dir: str = "research_out") -> dict:
    """ideas11: دروازهٔ BTC در برابر انتخاب ارز (G-053) و MAX مومنتوم (X-054)."""
    from .ideas11 import IDEA11_HYPOTHESES, run_ideas11
    start_ms = int(datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    end = int(time.time() * 1000) // DAY_MS * DAY_MS
    syms = pick_universe_all()
    daily, failed = {}, []
    for s in syms:
        try:
            bars = fetch_history(s, start_ms - 400 * DAY_MS, end, interval="1d")
        except DataError as e:
            failed.append(f"{s}:{e}")
            continue
        if bars:
            q = quality_check(bars, interval_ms=DAY_MS)
            if q["n"] > 0:
                daily[s] = q["clean"]
    res = run_ideas11(daily, start_ms, end)
    report = {"registered_before_results": True, "registered_at": "2026-11-05T17:40Z",
              "hypotheses": IDEA11_HYPOTHESES,
              "period": {"from": start, "to": datetime.fromtimestamp(end / 1000, timezone.utc).strftime("%Y-%m-%d")},
              "data": {"symbols_listed_incl_delisted": len(syms), "symbols_with_data": len(daily),
                       "failed": len(failed)},
              "known_biases": ["MULTIPLE_TESTS: شمار فرضیه‌ها به ۵۴ می‌رسد.",
                               "G-053 از سرنخی آمد که در ideas10 پس از دیدن نتیجه دیده شد؛ پرسش اینجا عوض شده"
                               " (آیا انتخاب ارز روی دروازه چیزی اضافه می‌کند؟) اما همان دوره است، پس قبولی"
                               " آن نیاز به تکرار روی دورهٔ تازه دارد.",
                               "فقط خرید؛ مقالهٔ MAX بازده خرید-فروش گزارش می‌کند."],
              "results": res}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "ideas11_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    md = ["# ideas11: دروازهٔ BTC در برابر انتخاب ارز، و MAX مومنتوم", "",
          f"- دوره: {start} تا {report['period']['to']} — {res['mondays']} هفته",
          f"- نمادها: {len(syms)} فهرست‌شده (شامل حذف‌شده)، {len(daily)} با داده", ""]
    for hid, v in res["verdict"].items():
        md.append(f"- {hid}: **{v}** — {IDEA11_HYPOTHESES[hid]}")
    md += ["", "| فرضیه | دوره | سبد: بازده ٪ / افت ٪ / شارپ | محک: بازده ٪ / افت ٪ / شارپ |", "|---|---|---|---|"]
    f = lambda c: f"{c.get('total_return_pct')} / {c.get('max_drawdown_pct')} / {c.get('sharpe')}"  # noqa: E731
    names = {"full": "کل", "first_half": "نیمهٔ اول", "second_half": "نیمهٔ دوم"}
    for hid, e in res["by_hypothesis"].items():
        for k, fa in names.items():
            md.append(f"| {hid} | {fa} | {f(e['portfolio'][k])} | {f(e['benchmark'][k])} |")
    lm = res["by_hypothesis"]["H-MARI-X-054"].get("low_max_decile_info") or {}
    md += ["", f"- اطلاعی: دهک **پایین** MAX (خلاف مقاله): {f(lm)}",
           "", "> همه‌چیز تمرینی است — بدون سفارش واقعی"]
    with open(os.path.join(out_dir, "ideas11_report_fa.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    return report


def run_ideas12_research(start: str = "2017-09-01", out_dir: str = "research_out") -> dict:
    """ideas12: تکرار G-055 روی دورهٔ کنار گذاشته‌شده، و بتای نزولی B-056."""
    from .ideas12 import IDEA12_HYPOTHESES, run_ideas12
    ms = lambda d: int(datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)  # noqa: E731
    g_start, g_end = ms(start), ms("2020-06-01")
    b_start = ms("2020-06-01")
    end = int(time.time() * 1000) // DAY_MS * DAY_MS
    syms = pick_universe_all()
    daily, failed = {}, []
    for s in syms:
        try:
            bars = fetch_history(s, g_start - 400 * DAY_MS, end, interval="1d")
        except DataError as e:
            failed.append(f"{s}:{e}")
            continue
        if bars:
            q = quality_check(bars, interval_ms=DAY_MS)
            if q["n"] > 0:
                daily[s] = q["clean"]
    res = run_ideas12(daily, g_start, g_end, b_start, end)
    report = {"registered_before_results": True, "registered_at": "2026-11-05T18:00Z",
              "hypotheses": IDEA12_HYPOTHESES,
              "period": {"G-055": f"{start} تا 2020-06-01 (کنار گذاشته‌شده)",
                         "B-056": f"2020-06-01 تا {datetime.fromtimestamp(end / 1000, timezone.utc).strftime('%Y-%m-%d')}"},
              "data": {"symbols_listed_incl_delisted": len(syms), "symbols_with_data": len(daily),
                       "failed": len(failed)},
              "known_biases": ["MULTIPLE_TESTS: شمار فرضیه‌ها به ۵۶ می‌رسد.",
                               "G-055: دورهٔ ۲۰۱۷-۲۰۲۰ ارزهای کمتری دارد؛ جهان کوچک‌تر است.",
                               "سنجهٔ G-055 (شارپ و افت) پیش از دیدن نتیجهٔ این دوره اعلام شد،"
                               " اما پس از دیدن الگوی G-053 در دورهٔ دیگر انتخاب شد — همین دلیلِ"
                               " آزمون روی دورهٔ کنار گذاشته‌شده است.",
                               "B-056: مقاله بازده خرید-فروش گزارش می‌کند؛ اینجا فقط خرید."],
              "results": res}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "ideas12_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    md = ["# ideas12: تکرار سرنخ دروازه روی دورهٔ تازه، و بتای نزولی", "",
          f"- G-055: {report['period']['G-055']} — {res['weeks']['G-055']} هفته",
          f"- B-056: {report['period']['B-056']} — {res['weeks']['B-056']} هفته",
          f"- نمادها: {len(syms)} فهرست‌شده (شامل حذف‌شده)، {len(daily)} با داده", ""]
    for hid, v in res["verdict"].items():
        md.append(f"- {hid}: **{v}** — {IDEA12_HYPOTHESES[hid]}")
    md += ["", "| فرضیه | دوره | سبد: بازده ٪ / افت ٪ / شارپ | محک: بازده ٪ / افت ٪ / شارپ |", "|---|---|---|---|"]
    f = lambda c: f"{c.get('total_return_pct')} / {c.get('max_drawdown_pct')} / {c.get('sharpe')}"  # noqa: E731
    names = {"full": "کل", "first_half": "نیمهٔ اول", "second_half": "نیمهٔ دوم"}
    for hid, e in res["by_hypothesis"].items():
        for k, fa in names.items():
            md.append(f"| {hid} | {fa} | {f(e['portfolio'][k])} | {f(e['benchmark'][k])} |")
    lb = res["by_hypothesis"]["H-MARI-B-056"].get("low_beta_quintile_info") or {}
    md += ["", f"- اطلاعی: پنجک **پایین** بتای نزولی: {f(lb)}", "", "> همه‌چیز تمرینی است — بدون سفارش واقعی"]
    with open(os.path.join(out_dir, "ideas12_report_fa.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    return report


def run_ideas13_research(start: str = "2020-06-01", out_dir: str = "research_out") -> dict:
    """ideas13: کری دلتا-نیوترال فاندینگ (Y-057) روی BTC و ETH."""
    from .funding import daily_funding, fetch_funding
    from .ideas13 import IDEA13_HYPOTHESES, run_ideas13
    start_ms = int(datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    end = int(time.time() * 1000) // DAY_MS * DAY_MS
    days = list(range(start_ms, end, DAY_MS))
    fund, sources = {}, {}
    for s in ("BTCUSDT", "ETHUSDT"):
        name, rows, tried = fetch_funding(s, start_ms - 20 * DAY_MS, end, need_from_ms=start_ms)
        fund[s] = daily_funding(rows, days)
        settled = sum(1 for v in fund[s] if v is not None)
        sources[s] = {"used": name, "rows": len(rows), "settled_days": settled, "failed_before": tried}
    res = run_ideas13(fund, days)
    report = {"registered_before_results": True, "registered_at": "2026-11-05T20:00Z",
              "hypotheses": IDEA13_HYPOTHESES, "sources": sources,
              "period": {"from": start, "to": datetime.fromtimestamp(end / 1000, timezone.utc).strftime("%Y-%m-%d")},
              "known_biases": ["MULTIPLE_TESTS: شمار فرضیه‌ها به ۵۷ می‌رسد.",
                               "پوشش کامل فرض شده: اختلاف قیمت اسپات و دائمی (basis)، هزینهٔ مارجین و"
                               " خطر لیکویید شدن مدل نشده‌اند. نتیجه سقف خوش‌بینانه است، نه بازده واقعی.",
                               "بدون اهرم: درآمد روی همان سرمایه حساب شده (مقاله‌ها معمولاً اهرم دارند).",
                               "هزینه: ۴ پا در هر چرخه، مجموعاً ۰٫۶٪ (۰٫۳٪ ورود + ۰٫۳٪ خروج).",
                               "فاندینگ تاریخی بایننس از ۲۰۲۰-۰۱؛ پیش از آن داده نیست."],
              "results": res}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "ideas13_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    md = ["# ideas13: کری دلتا-نیوترال فاندینگ", "",
          f"- دوره: {start} تا {report['period']['to']}",
          "- منبع: " + "، ".join(f"{k}: {v['used']} ({v['settled_days']} روز تسویه)" for k, v in sources.items()),
          "", "**هشدار:** پوشش کامل فرض شده؛ اختلاف قیمت اسپات/دائمی و خطر لیکویید در مدل نیست."
          " عددها سقف خوش‌بینانه‌اند.", ""]
    for hid, v in res["verdict"].items():
        md.append(f"- {hid}: **{v}** — {IDEA13_HYPOTHESES[hid]}")
    md += ["", "| دارایی | نسخه | بازده کل ٪ | بیشترین افت ٪ | شارپ | چرخه | روز در موقعیت ٪ |",
           "|---|---|---|---|---|---|---|"]
    for sym, x in res["by_asset"].items():
        for name in ("H-MARI-Y-057", "ALWAYS_ON_INFO"):
            st = (x or {}).get(name) or {}
            md.append(f"| {sym} | {name} | {st.get('total_return_pct')} | {st.get('max_drawdown_pct')} | "
                      f"{st.get('sharpe')} | {st.get('cycles')} | {st.get('days_in_position_pct')} |")
    md += ["", "> همه‌چیز تمرینی است — بدون سفارش واقعی"]
    with open(os.path.join(out_dir, "ideas13_report_fa.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    return report


def run_ideas14_research(start: str = "2018-01-01", out_dir: str = "research_out") -> dict:
    """ideas14: «فرمول مشترک ارزهای صعودی» — یادگیری روی دادهٔ تا ۲۰۲۳-۰۵، آزمون روی دادهٔ بعد از آن."""
    from .ideas14 import IDEA14_HYPOTHESES, run_ideas14
    ms = lambda d: int(datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)  # noqa: E731
    tr_s, tr_e, te_s = ms(start), ms("2023-06-01"), ms("2023-06-01")
    end = int(time.time() * 1000) // DAY_MS * DAY_MS
    syms = pick_universe_all()
    daily, failed = {}, []
    for s in syms:
        try:
            bars = fetch_history(s, tr_s - 400 * DAY_MS, end, interval="1d")
        except DataError as e:
            failed.append(f"{s}:{e}")
            continue
        if bars:
            q = quality_check(bars, interval_ms=DAY_MS)
            if q["n"] > 0:
                daily[s] = q["clean"]
    res = run_ideas14(daily, tr_s, tr_e, te_s, end)
    report = {"registered_before_results": True, "registered_at": "2026-11-05T20:05Z",
              "hypotheses": IDEA14_HYPOTHESES,
              "period": {"train": f"{start} تا 2023-06-01", "test": f"2023-06-01 تا {datetime.fromtimestamp(end / 1000, timezone.utc).strftime('%Y-%m-%d')}"},
              "data": {"symbols_listed_incl_delisted": len(syms), "symbols_with_data": len(daily),
                       "failed": len(failed)},
              "known_biases": ["MULTIPLE_TESTS: شمار فرضیه‌ها به ۵۹ می‌رسد.",
                               "پنجره‌های ۹۱ روزه هم‌پوشانی دارند؛ به همین دلیل بوت‌استرپ بلوکی روی تاریخ‌ها استفاده شده.",
                               "ارزهایی که پیش از حذف هیچ داده‌ای در API عمومی ندارند دیده نمی‌شوند؛ پس بخشی از"
                               " بازندگان واقعی غایب‌اند و نرخ برنده‌شدن کمی خوش‌بینانه است.",
                               "دادهٔ ارزش بازار و زنجیره در دسترس نیست؛ ویژگی‌ها فقط قیمت و حجم‌اند.",
                               "دورهٔ آزمون بیشتر بازار نزولی/خنثی بوده؛ نرخ برنده‌شدن پایه در آن کم است."],
              "results": res}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "ideas14_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    r = res["rule"]
    md = ["# ideas14: فرمول مشترک ارزهای صعودی", "",
                          f"- آموزش: {report['period']['train']} — {r['n_train_events']} رویداد",
                          f"- آزمون: {report['period']['test']} — {res['n_test_events']} رویداد",
                          f"- برنده = بازده ۹۱ روزهٔ بعدی ≥ +۲۰۰٪. نرخ پایه در آموزش: {r['base_win_rate'] * 100:.2f}٪",
                          f"- نمادها: {len(syms)} فهرست‌شده (شامل حذف‌شده)، {len(daily)} با داده", ""]
    for hid, v in res["verdict"].items():
        md.append(f"- {hid}: **{v}** — {IDEA14_HYPOTHESES[hid]}")
    md += ["", "## جداسازی هر ویژگی روی دادهٔ آموزش (نرخ بهترین پنجک منهای نرخ پایه)", "",
           "| ویژگی | جداسازی (واحد درصد) | بهترین پنجک | نرخ برنده در آن پنجک ٪ | تعداد |", "|---|---|---|---|---|"]
    for name in sorted(r["by_feature"], key=lambda n: -r["by_feature"][n]["separation"]):
        x = r["by_feature"][name]
        b = x["rates"][x["best_bucket"]]
        md.append(f"| {name} | {x['separation'] * 100:.2f} | {x['best_bucket'] + 1} از ۵ | "
                  f"{b['win_rate'] * 100:.2f} | {b['n']} |")
    md += ["", f"**سه ویژگی انتخاب‌شده (مکانیکی):** {'، '.join(r['picked'])}", ""]
    ti, te = res["train_in_sample_info"] or {}, res["test"] or {}
    md += ["## Z-058: نرخ برنده‌شدن قاعده", "",
           "| دوره | سیگنال | نرخ برنده سیگنال ٪ | نرخ پایه ٪ | اختلاف ٪ [CI95] |", "|---|---|---|---|---|",
           f"| آموزش (درون‌نمونه، اطلاعی) | {ti.get('n_fired')} | {(ti.get('fired_win_rate') or 0) * 100:.2f} | "
           f"{(ti.get('base_win_rate') or 0) * 100:.2f} | {ti.get('diff_pct')} [{ti.get('ci95_low')}, {ti.get('ci95_high')}] |",
           f"| **آزمون (دیده‌نشده)** | {te.get('n_fired')} | {(te.get('fired_win_rate') or 0) * 100:.2f} | "
           f"{(te.get('base_win_rate') or 0) * 100:.2f} | {te.get('diff_pct')} [{te.get('ci95_low')}, {te.get('ci95_high')}] |"]
    t = res["tradeable"]
    f = lambda c: f"{c.get('total_return_pct')} / {c.get('max_drawdown_pct')} / {c.get('sharpe')}"  # noqa: E731
    md += ["", "## Z-059: سبد قابل معامله در دورهٔ آزمون", "",
           "| سبد: بازده ٪ / افت ٪ / شارپ | محک وزن برابر: بازده ٪ / افت ٪ / شارپ | هفته |", "|---|---|---|",
           f"| {f(t['portfolio'])} | {f(t['benchmark'])} | {t['weeks']} |",
           "", "> همه‌چیز تمرینی است — بدون سفارش واقعی"]
    with open(os.path.join(out_dir, "ideas14_report_fa.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    return report


def run_ideas15_research(start: str = "2020-06-01", out_dir: str = "research_out") -> dict:
    """ideas15: کری دلتا-نیوترال با قیمت واقعی قرارداد دائمی (Y-060)."""
    from .funding import daily_funding, fetch_funding
    from .ideas15 import IDEA15_HYPOTHESES, fetch_perp_daily, run_ideas15
    start_ms = int(datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    end = int(time.time() * 1000) // DAY_MS * DAY_MS
    days = list(range(start_ms, end, DAY_MS))
    spot, perp, fund, sources = {}, {}, {}, {}
    for s in ("BTCUSDT", "ETHUSDT"):
        bars = fetch_history(s, start_ms - 10 * DAY_MS, end, interval="1d")
        clean = quality_check(bars, interval_ms=DAY_MS)["clean"]
        spot[s] = {b["t"]: b["c"] for b in clean}
        perp[s] = fetch_perp_daily(s, start_ms, end)
        name, rows, tried = fetch_funding(s, start_ms - 20 * DAY_MS, end, need_from_ms=start_ms)
        fund[s] = daily_funding(rows, days)
        sources[s] = {"funding": name, "spot_days": len(spot[s]), "perp_days": len(perp[s]),
                      "settled_days": sum(1 for v in fund[s] if v is not None)}
    res = run_ideas15(days, spot, perp, fund)
    report = {"registered_before_results": True, "registered_at": "2026-11-05T20:30Z",
              "hypotheses": IDEA15_HYPOTHESES, "sources": sources,
              "period": {"from": start, "to": datetime.fromtimestamp(end / 1000, timezone.utc).strftime("%Y-%m-%d")},
              "known_biases": ["MULTIPLE_TESTS: شمار فرضیه‌ها به ۶۰ می‌رسد.",
                               "قیمت بستهٔ روزانه استفاده می‌شود؛ نوسان basis درون‌روز و خطر لیکویید"
                               " شدن لحظه‌ای دیده نمی‌شود. پس حتی این نسخه هم کمی خوش‌بینانه است.",
                               "مارجین کامل فرض شده (بدون اهرم)؛ بازده واقعی با اهرم بیشتر و ریسک لیکویید"
                               " شدن هم بیشتر است.",
                               "هزینهٔ تأمین مارجین و نرخ بهرهٔ وام مدل نشده است.",
                               "روزهایی که دادهٔ اسپات یا دائمی نیست، بیرون از موقعیت شمرده می‌شوند."],
              "results": res}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "ideas15_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    md = ["# ideas15: کری دلتا-نیوترال با قیمت واقعی قرارداد دائمی", "",
          f"- دوره: {start} تا {report['period']['to']}",
          "- داده: " + "، ".join(f"{k}: اسپات {v['spot_days']} روز، دائمی {v['perp_days']} روز، تسویه {v['settled_days']}"
                                 for k, v in sources.items()), ""]
    for hid, v in res["verdict"].items():
        md.append(f"- {hid}: **{v}** — {IDEA15_HYPOTHESES[hid]}")
    md += ["", "| دارایی | نسخه | بازده کل ٪ | بیشترین افت ٪ | شارپ | بدترین روز ٪ | چرخه |",
           "|---|---|---|---|---|---|---|"]
    for sym, x in res["by_asset"].items():
        for name in ("H-MARI-Y-060", "ZERO_BASIS_INFO", "ALWAYS_ON_INFO"):
            st = (x or {}).get(name) or {}
            md.append(f"| {sym} | {name} | {st.get('total_return_pct')} | {st.get('max_drawdown_pct')} | "
                      f"{st.get('sharpe')} | {st.get('worst_day_pct')} | {st.get('cycles')} |")
    md += ["", "## اختلاف قیمت دائمی و اسپات (basis)", "",
           "| دارایی | میانگین ٪ | صدک ۱ ٪ | صدک ۹۹ ٪ | کمینه ٪ | بیشینه ٪ |", "|---|---|---|---|---|---|"]
    for sym, x in res["by_asset"].items():
        b = (x or {}).get("BASIS_INFO") or {}
        md.append(f"| {sym} | {b.get('mean_pct')} | {b.get('p01_pct')} | {b.get('p99_pct')} | "
                  f"{b.get('min_pct')} | {b.get('max_pct')} |")
    md += ["", "> همه‌چیز تمرینی است — بدون سفارش واقعی"]
    with open(os.path.join(out_dir, "ideas15_report_fa.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    return report


def run_ideas16_research(start: str = "2018-01-01", out_dir: str = "research_out") -> dict:
    """ideas16: نسخهٔ اصلاح‌شدهٔ «فرمول ارزهای صعودی» — آستانهٔ توان و محک هم‌نقد."""
    from .ideas16 import IDEA16_HYPOTHESES, MIN_EXPECTED_WINNERS, run_ideas16
    ms = lambda d: int(datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)  # noqa: E731
    tr_s, tr_e = ms(start), ms("2023-06-01")
    end = int(time.time() * 1000) // DAY_MS * DAY_MS
    syms = pick_universe_all()
    daily, failed = {}, []
    for s in syms:
        try:
            bars = fetch_history(s, tr_s - 400 * DAY_MS, end, interval="1d")
        except DataError as e:
            failed.append(f"{s}:{e}")
            continue
        if bars:
            q = quality_check(bars, interval_ms=DAY_MS)
            if q["n"] > 0:
                daily[s] = q["clean"]
    res = run_ideas16(daily, tr_s, tr_e, tr_e, end)
    report = {"registered_before_results": True, "registered_at": "2026-11-05T21:00Z",
              "hypotheses": IDEA16_HYPOTHESES,
              "period": {"train": f"{start} تا 2023-06-01",
                         "test": f"2023-06-01 تا {datetime.fromtimestamp(end / 1000, timezone.utc).strftime('%Y-%m-%d')}"},
              "fixes_from_ideas14": [
                  f"آستانهٔ توان بر پایهٔ تعداد برندهٔ مورد انتظار (≥{MIN_EXPECTED_WINNERS}) است، نه تعداد سیگنال.",
                  "محک هم‌نقد: در همان هفته‌ها و با همان تعداد ارز در بازار، ارزها تصادفی از همان جهان.",
                  "قاعدهٔ گسترده با دو ویژگی (به‌جای سه) تا سیگنال کافی تولید شود."],
              "data": {"symbols_listed_incl_delisted": len(syms), "symbols_with_data": len(daily),
                       "failed": len(failed)},
              "known_biases": ["MULTIPLE_TESTS: شمار فرضیه‌ها به ۶۲ می‌رسد.",
                               "قاعدهٔ دو-ویژگی‌ای از همان دادهٔ آموزش ideas14 آمده؛ دورهٔ آزمون همان دورهٔ"
                               " آزمون ideas14 است و یک بار دیده شده. پس قبولی اینجا هم به تکرار نیاز دارد.",
                               "پنجره‌های ۹۱ روزه هم‌پوشانی دارند؛ بوت‌استرپ بلوکی روی تاریخ‌ها.",
                               "دادهٔ ارزش بازار و زنجیره در دسترس نیست."],
              "results": res}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "ideas16_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    r = res["rule"]
    pw, ci, cm = res["power"], res["test"] or {}, res["cash_matched"]
    md = ["# ideas16: فرمول ارزهای صعودی — نسخهٔ اصلاح‌شده", "",
          f"- آموزش: {report['period']['train']}؛ آزمون: {report['period']['test']}",
          f"- دو ویژگی انتخاب‌شده: {'، '.join(r['picked'])}",
          f"- نمادها: {len(syms)} فهرست‌شده (شامل حذف‌شده)، {len(daily)} با داده", ""]
    for hid, v in res["verdict"].items():
        md.append(f"- {hid}: **{v}** — {IDEA16_HYPOTHESES[hid]}")
    md += ["", "## آزمون توان (ایراد ۱ که اصلاح شد)", "",
           "| دوره | سیگنال | نرخ پایه ٪ | برندهٔ مورد انتظار بی‌اثر | برندهٔ واقعی | قابل آزمون؟ |",
           "|---|---|---|---|---|---|"]
    for lbl, x in (("آموزش", res["train_power_info"]), ("**آزمون**", pw)):
        md.append(f"| {lbl} | {x['n_fired']} | {x['base_win_rate'] * 100:.2f} | "
                  f"{x['expected_winners_if_no_effect']} | {x['observed_winners']} | "
                  f"{'بله' if x['testable'] else '**نه**'} |")
    md += ["", "## Z-061: نرخ برنده‌شدن روی دادهٔ آزمون", "",
           f"- نرخ سیگنال: {(ci.get('fired_win_rate') or 0) * 100:.2f}٪ | نرخ پایه: {(ci.get('base_win_rate') or 0) * 100:.2f}٪",
           f"- اختلاف: {ci.get('diff_pct')}٪ [CI95: {ci.get('ci95_low')} تا {ci.get('ci95_high')}]", ""]
    f = lambda c: f"{c.get('total_return_pct')} / {c.get('max_drawdown_pct')} / {c.get('sharpe')}"  # noqa: E731
    md += ["## Z-062: در برابر محک هم‌نقد (ایراد ۲ که اصلاح شد)", "",
           "| | بازده ٪ / افت ٪ / شارپ |", "|---|---|",
           f"| سبد قاعده | {f(cm['portfolio'])} |",
           f"| میانهٔ {(cm.get('benchmark_median_random') or {}).get('n_draws')} سبد تصادفی هم‌نقد | {f(cm.get('benchmark_median_random') or {})} |",
           "",
           f"- هفته‌های در بازار: {cm.get('weeks_in_market')} از {cm.get('weeks')}",
           f"- درصد قرعه‌های تصادفی که سبد از آن‌ها بهتر بود: شارپ {cm.get('pct_random_draws_beaten_sharpe')}٪، بازده {cm.get('pct_random_draws_beaten_return')}٪",
           "", "> همه‌چیز تمرینی است — بدون سفارش واقعی"]
    with open(os.path.join(out_dir, "ideas16_report_fa.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    return report


def run_ideas17_research(start: str = "2018-01-01", out_dir: str = "research_out") -> dict:
    """ideas17: آزمون سوم ایدهٔ صاحب پروژه با جابه‌جایی زمان (یادگیری از داده تازه، آزمون روی قدیم)."""
    from .ideas17 import BEAT_FRAC, IDEA17_HYPOTHESES, run_ideas17
    ms = lambda d: int(datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)  # noqa: E731
    te_s, te_e = ms(start), ms("2021-06-01")
    le_s = ms("2021-06-01")
    end = int(time.time() * 1000) // DAY_MS * DAY_MS
    syms = pick_universe_all()
    daily, failed = {}, []
    for s in syms:
        try:
            bars = fetch_history(s, te_s - 400 * DAY_MS, end, interval="1d")
        except DataError as e:
            failed.append(f"{s}:{e}")
            continue
        if bars:
            q = quality_check(bars, interval_ms=DAY_MS)
            if q["n"] > 0:
                daily[s] = q["clean"]
    res = run_ideas17(daily, le_s, end, te_s, te_e)
    report = {"registered_before_results": True, "registered_at": "2026-11-05T21:30Z",
              "hypotheses": IDEA17_HYPOTHESES,
              "period": {"learn": f"2021-06-01 تا {datetime.fromtimestamp(end / 1000, timezone.utc).strftime('%Y-%m-%d')}",
                         "test": f"{start} تا 2021-06-01 (دست‌نخورده برای این ایده)"},
              "design": [f"شرط سخت‌گیر: بهتر از ≥{BEAT_FRAC}٪ قرعه‌های محک هم‌نقد، هم شارپ و هم بازده.",
                         "جابه‌جایی زمان: یادگیری از دادهٔ تازه، آزمون روی دادهٔ قدیم.",
                         "آستانهٔ توان: برندهٔ مورد انتظار ≥۱۰، وگرنه «آزمون‌ناپذیر»."],
              "data": {"symbols_listed_incl_delisted": len(syms), "symbols_with_data": len(daily),
                       "failed": len(failed)},
              "known_biases": ["MULTIPLE_TESTS: شمار فرضیه‌ها به ۶۴ می‌رسد.",
                               "دورهٔ ۲۰۱۸-۲۰۲۱ ارزهای کمتری دارد؛ جهان کوچک‌تر و نرخ پایه متفاوت است.",
                               "دورهٔ ۲۰۲۰-۲۰۲۱ یک بازار صعودی تاریخی بود؛ نرخ برنده‌شدن پایه در آن بالاست"
                               " و محک هم‌نقد تصادفی هم قوی است — این آزمون سخت‌تر از دورهٔ نزولی است.",
                               "یادگیری روی دادهٔ تازه‌ای انجام می‌شود که در ideas14/16 دیده شده بود؛ اما"
                               " دورهٔ آزمون برای این ایده کاملاً تازه است."],
              "results": res}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "ideas17_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    r = res["rule"]
    pw, ci, cm = res["power"], res["test"] or {}, res["cash_matched"]
    md = ["# ideas17: آزمون سوم ایدهٔ صاحب پروژه (جابه‌جایی زمان، شرط ۹۵٪)", "",
          f"- یادگیری: {report['period']['learn']}",
          f"- **آزمون: {report['period']['test']}**",
          f"- دو ویژگی انتخاب‌شده: {'، '.join(r['picked'])}",
          f"- نمادها: {len(syms)} فهرست‌شده (شامل حذف‌شده)، {len(daily)} با داده", ""]
    for hid, v in res["verdict"].items():
        md.append(f"- {hid}: **{v}** — {IDEA17_HYPOTHESES[hid]}")
    md += ["", "## آزمون توان", "",
           "| دوره | سیگنال | نرخ پایه ٪ | برندهٔ مورد انتظار بی‌اثر | برندهٔ واقعی | قابل آزمون؟ |",
           "|---|---|---|---|---|---|"]
    for lbl, x in (("یادگیری", res["learn_power_info"]), ("**آزمون**", pw)):
        md.append(f"| {lbl} | {x['n_fired']} | {x['base_win_rate'] * 100:.2f} | "
                  f"{x['expected_winners_if_no_effect']} | {x['observed_winners']} | "
                  f"{'بله' if x['testable'] else '**نه**'} |")
    md += ["", "## Z-064: نرخ برنده‌شدن", "",
           f"- نرخ سیگنال: {(ci.get('fired_win_rate') or 0) * 100:.2f}٪ | نرخ پایه: {(ci.get('base_win_rate') or 0) * 100:.2f}٪",
           f"- اختلاف: {ci.get('diff_pct')}٪ [CI95: {ci.get('ci95_low')} تا {ci.get('ci95_high')}]", ""]
    f = lambda c: f"{c.get('total_return_pct')} / {c.get('max_drawdown_pct')} / {c.get('sharpe')}"  # noqa: E731
    md += ["## Z-063: در برابر محک هم‌نقد، با شرط ۹۵٪", "",
           "| | بازده ٪ / افت ٪ / شارپ |", "|---|---|",
           f"| سبد قاعده | {f(cm['portfolio'])} |",
           f"| میانهٔ {(cm.get('benchmark_median_random') or {}).get('n_draws')} قرعهٔ تصادفی | {f(cm.get('benchmark_median_random') or {})} |",
           "",
           f"- هفته‌های در بازار: {cm.get('weeks_in_market')} از {cm.get('weeks')}",
           f"- **بهتر از قرعه‌ها: شارپ {cm.get('pct_random_draws_beaten_sharpe')}٪، بازده {cm.get('pct_random_draws_beaten_return')}٪** (شرط: ≥{res['beat_threshold_pct']}٪)",
           "", "> همه‌چیز تمرینی است — بدون سفارش واقعی"]
    with open(os.path.join(out_dir, "ideas17_report_fa.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    return report


def run_ideas18_research(out_dir: str = "research_out") -> dict:
    """ideas18: T-006 روی دادهٔ کوین‌بیس پیش از بایننس (T-065)، و تکرار اطلاعی روی بای‌بیت."""
    from .ideas18 import IDEA18_HYPOTHESES, run_ideas18
    from .venues import fetch_bybit_daily, fetch_coinbase_daily
    ms = lambda d: int(datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)  # noqa: E731
    end = int(time.time() * 1000) // DAY_MS * DAY_MS
    held_end = ms("2018-06-01")
    windows = {"BTCUSDT": (ms("2015-07-01"), held_end), "ETHUSDT": (ms("2016-11-01"), held_end)}
    cb, sources = {}, {}
    for sym, fetch_from in (("BTCUSDT", "2015-01-01"), ("ETHUSDT", "2016-05-01")):
        try:
            bars = fetch_coinbase_daily(sym, ms(fetch_from), end)
            cb[sym] = quality_check(bars, interval_ms=DAY_MS)["clean"] if bars else []
            sources[f"coinbase_{sym}"] = {"bars": len(cb[sym]),
                                          "first": datetime.fromtimestamp(cb[sym][0]["t"] / 1000, timezone.utc).strftime("%Y-%m-%d") if cb[sym] else None}
        except DataError as e:
            cb[sym] = []
            sources[f"coinbase_{sym}"] = {"error": str(e)}
    by_window = (ms("2022-01-01"), end)
    by, bn = {}, {}
    for sym in ("BTCUSDT", "ETHUSDT"):
        try:
            b = fetch_bybit_daily(sym, by_window[0] - 200 * DAY_MS, end)
            by[sym] = quality_check(b, interval_ms=DAY_MS)["clean"] if b else []
            sources[f"bybit_{sym}"] = {"bars": len(by[sym])}
        except DataError as e:
            by[sym] = []
            sources[f"bybit_{sym}"] = {"error": str(e)}
        bars = fetch_history(sym, by_window[0] - 200 * DAY_MS, end, interval="1d")
        bn[sym] = quality_check(bars, interval_ms=DAY_MS)["clean"]
    res = run_ideas18(cb, windows, end, bybit=by, binance=bn, bybit_window=by_window)
    report = {"registered_before_results": True, "registered_at": "2026-11-06T02:50Z",
              "hypotheses": IDEA18_HYPOTHESES, "sources": sources,
              "period": {"held_out_BTC": "2015-07-01 تا 2018-06-01", "held_out_ETH": "2016-11-01 تا 2018-06-01",
                         "bybit_info": f"2022-01-01 تا {datetime.fromtimestamp(end / 1000, timezone.utc).strftime('%Y-%m-%d')}"},
              "known_biases": ["MULTIPLE_TESTS: شمار فرضیه‌ها به ۶۵ می‌رسد.",
                               "کوین‌بیس به دلار آمریکا قیمت می‌دهد، نه تتر؛ برای روند بلندمدت اختلاف ناچیز است.",
                               "دورهٔ دیده‌نشدهٔ ETH فقط حدود ۱۹ ماه است؛ توان آماری محدود.",
                               "دورهٔ دیده‌نشده شامل حباب ۲۰۱۷ و ریزش ۲۰۱۸ است؛ یک چرخهٔ کامل، نه چند چرخه.",
                               "بای‌بیت روی همان بازه‌ای که بایننس دیده شده اجرا می‌شود؛ پس فقط آزمون سلامت داده است، نه تکرار مستقل فرضیه."],
              "results": res}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "ideas18_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    f = lambda c: f"{c.get('total_return_pct')} / {c.get('max_drawdown_pct')} / {c.get('sharpe')} / {c.get('trades')}"  # noqa: E731
    md = ["# ideas18: روش برنده روی داده‌ای که هرگز دیده نشده (کوین‌بیس ۲۰۱۵ تا ۲۰۱۸)", "",
          "- منابع: " + "، ".join(f"{k}: {v}" for k, v in sources.items()), ""]
    for hid, v in res["verdict"].items():
        md.append(f"- {hid}: **{v}** — {IDEA18_HYPOTHESES[hid]}")
    md += ["", "| دارایی | دوره | روش | بازده ٪ / افت ٪ / شارپ / معامله |", "|---|---|---|---|"]
    for sym, x in res["by_asset"].items():
        if x.get("insufficient"):
            md.append(f"| {sym} | — | داده کافی نیست ({x.get('bars')} کندل) | — |")
            continue
        for per, key in (("**دیده‌نشده**", "held_out"), ("کل (اطلاعی)", "full_period_info")):
            for name in ("BUY_HOLD", "T-006"):
                md.append(f"| {sym} | {per} | {name} | {f(x[key][name])} |")
    md += ["", "## استحکام طول میانگین روی دورهٔ دیده‌نشده (اطلاعی)", "",
           "| دارایی | SMA100 | SMA125 | SMA150 | SMA175 | SMA200 |", "|---|---|---|---|---|---|"]
    for sym, x in res["by_asset"].items():
        if x.get("insufficient"):
            continue
        L = x["held_out"]["lengths_info"]
        md.append(f"| {sym} شارپ | " + " | ".join(str(L[f'SMA{n}'].get('sharpe')) for n in (100, 125, 150, 175, 200)) + " |")
    md += ["", "## بای‌بیت در برابر بایننس (فقط سلامت داده)", ""]
    for sym, c in (res.get("bybit_replication_info") or {}).items():
        if not c.get("available"):
            md.append(f"- {sym}: در دسترس نبود ({c.get('bybit_bars')} کندل)")
            continue
        dc = c["data_check"]
        md.append(f"- {sym}: {dc.get('common_days')} روز مشترک، میانهٔ اختلاف بسته {dc.get('median_abs_diff_pct')}٪، "
                  f"بیشینه {dc.get('max_abs_diff_pct')}٪ — شارپ T-006 بای‌بیت {c['bybit_T006'].get('sharpe')} "
                  f"در برابر بایننس {c['binance_T006'].get('sharpe')} — نتیجهٔ یکسان: {'بله' if c['same_conclusion'] else '**نه**'}")
    md += ["", "> همه‌چیز تمرینی است — بدون سفارش واقعی"]
    with open(os.path.join(out_dir, "ideas18_report_fa.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    return report


def run_ideas19_research(start: str = "2020-06-01", out_dir: str = "research_out") -> dict:
    """ideas19: کم‌نوسانی (L-066) با آزمون دو-رژیمی و محک هم‌نقد."""
    from .ideas19 import IDEA19_HYPOTHESES, run_ideas19
    start_ms = int(datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    end = int(time.time() * 1000) // DAY_MS * DAY_MS
    syms = pick_universe_all()
    daily, failed = {}, []
    for s in syms:
        try:
            bars = fetch_history(s, start_ms - 400 * DAY_MS, end, interval="1d")
        except DataError as e:
            failed.append(f"{s}:{e}")
            continue
        if bars:
            q = quality_check(bars, interval_ms=DAY_MS)
            if q["n"] > 0:
                daily[s] = q["clean"]
    res = run_ideas19(daily, start_ms, end)
    report = {"registered_before_results": True, "registered_at": "2026-11-06T02:55Z",
              "hypotheses": IDEA19_HYPOTHESES,
              "period": {"from": start, "to": datetime.fromtimestamp(end / 1000, timezone.utc).strftime("%Y-%m-%d")},
              "data": {"symbols_listed_incl_delisted": len(syms), "symbols_with_data": len(daily),
                       "failed": len(failed)},
              "known_biases": ["MULTIPLE_TESTS: شمار فرضیه‌ها به ۶۶ می‌رسد.",
                               "مقاله خرید-فروش است؛ اینجا فقط خرید (فروش استقراضی از ایران در دسترس نیست).",
                               "مقاله دورهٔ نگه‌داری ۱ ماه دارد؛ اینجا ۴ هفته.",
                               "مقاله اثر را در سال‌های اخیر قوی‌تر و در سال‌های اول ضعیف‌تر گزارش می‌کند."],
              "results": res}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "ideas19_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    f = lambda c: f"{(c or {}).get('total_return_pct')} / {(c or {}).get('max_drawdown_pct')} / {(c or {}).get('sharpe')}"  # noqa: E731
    md = ["# ideas19: کم‌نوسانی، آزمون دو-رژیمی", "",
          f"- دوره: {start} تا {report['period']['to']}",
          f"- نمادها: {len(syms)} فهرست‌شده (شامل حذف‌شده)، {len(daily)} با داده", ""]
    for hid, v in res["verdict"].items():
        md.append(f"- {hid}: **{v}** — {IDEA19_HYPOTHESES[hid]}")
    md += ["", "| سبد | رژیم | هفته | سبد: بازده ٪ / افت ٪ / شارپ | میانهٔ تصادفی: بازده ٪ / افت ٪ / شارپ | بهتر از قرعه‌ها (شارپ / بازده) | حکم |",
           "|---|---|---|---|---|---|---|"]
    for name, key in (("کم‌نوسان (L-066)", "H-MARI-L-066"), ("پرنوسان (اطلاعی)", "HIGH_VOL_INFO")):
        r = res[key]
        for reg, fa in (("bull", "صعودی"), ("bear", "نزولی"), ("all", "کل")):
            x = r.get(reg) or {}
            md.append(f"| {name} | {fa} | {x.get('weeks')} | {f(x.get('portfolio'))} | "
                      f"{f(x.get('benchmark_median_random'))} | {x.get('pct_draws_beaten_sharpe')}٪ / "
                      f"{x.get('pct_draws_beaten_return')}٪ | {x.get('verdict')} |")
    md += ["", f"- هفته‌های در بازار (کم‌نوسان): {res['H-MARI-L-066'].get('weeks_in_market')}",
           "", "> همه‌چیز تمرینی است — بدون سفارش واقعی"]
    with open(os.path.join(out_dir, "ideas19_report_fa.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    return report


def run_diag19(start: str = "2020-06-01", out_dir: str = "research_out") -> dict:
    """تشخیص (فرضیه نیست): کدام ارز و کدام هفته عدد ناممکن ideas19 را ساخت؟"""
    from .ideas10 import Panel
    from .ideas19 import HOLD_WEEKS, make_selector
    from .regime import run_two_regime
    start_ms = int(datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    end = int(time.time() * 1000) // DAY_MS * DAY_MS
    syms = pick_universe_all()
    daily = {}
    for s in syms:
        try:
            bars = fetch_history(s, start_ms - 400 * DAY_MS, end, interval="1d")
        except DataError:
            continue
        if bars:
            q = quality_check(bars, interval_ms=DAY_MS)
            if q["n"] > 0:
                daily[s] = q["clean"]
    p = Panel(daily)
    res = run_two_regime(p, start_ms, end, make_selector("low"), HOLD_WEEKS, n_draws=5, seed=66, trace=True)
    # پرش‌های روزانهٔ بزرگ در کل جهان (بدون توجه به انتخاب)
    jumps = []
    for s_, d in p.sym.items():
        c, ts = d["c"], d["ts"]
        for j in range(1, len(c)):
            if c[j - 1] > 0 and (c[j] / c[j - 1] > 5 or c[j] / c[j - 1] < 0.2) and ts[j] >= start_ms:
                raw = c[j] / c[j - 1]
                jumps.append({"sym": s_, "day": datetime.fromtimestamp(ts[j] / 1000, timezone.utc).strftime("%Y-%m-%d"),
                              "ratio": round(raw, 6), "size": max(raw, 1 / raw), "prev": c[j - 1], "close": c[j]})
    jumps.sort(key=lambda x: -x["size"])          # بزرگی پرش، بدون تقسیم بر عدد گردشده
    report = {"diagnostic": True, "not_a_hypothesis": True, "trace": res.get("trace"),
              "daily_jumps_over_5x": {"count": len(jumps), "top": jumps[:40]}}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "diag19_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    tr = res.get("trace") or {}
    md = ["# تشخیص ideas19: منبع عدد ناممکن (فرضیه نیست)", "",
          f"- ارز-هفته‌های نگه‌داشته: {tr.get('coin_weeks')} — بالای +۱۰۰٪: {tr.get('n_over_100pct')}، "
          f"بالای +۳۰۰٪: {tr.get('n_over_300pct')}، زیر منفی ۹۰٪: {tr.get('n_below_minus90pct')}",
          f"- پرش‌های روزانهٔ بیش از ۵ برابر (یا کمتر از یک‌پنجم) در کل جهان از {start}: {len(jumps)}", "",
          "## بزرگ‌ترین بازده‌های هفتگی ارزهای نگه‌داشته", "",
          "| بازده ٪ | نماد | هفته | رژیم | تعداد در سبد | سهم در بازده هفته ٪ |", "|---|---|---|---|---|---|"]
    for x in tr.get("top", [])[:25]:
        md.append(f"| {x['ret_pct']} | {x['sym']} | {x['week']} | {x['regime']} | {x['n_held']} | {x['contrib_to_week_pct']} |")
    md += ["", "## بهترین هفته‌های سبد", "", "| بازده سبد ٪ | هفته | رژیم |", "|---|---|---|"]
    for r_, w, g in tr.get("weekly_port_top", []):
        md.append(f"| {r_} | {w} | {g} |")
    md += ["", "## بزرگ‌ترین پرش‌های روزانه در کل جهان", "", "| نماد | روز | نسبت | بستهٔ قبل | بسته |", "|---|---|---|---|---|"]
    for x in jumps[:30]:
        md.append(f"| {x['sym']} | {x['day']} | {x['ratio']} | {x['prev']} | {x['close']} |")
    with open(os.path.join(out_dir, "diag19_report_fa.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    return report


def run_oi_research(samples: str, out_dir: str = "research_out", pooled: bool = False) -> dict:
    """O-042 (هر نمونه جدا) یا O-043 (ادغام نمونه‌های تازه): جهش OI پیش از ورود شکارچی ساعتی."""
    from .oi import OI_HYPOTHESES, SURGE, collect, combine, evaluate, pooled_verdict
    per, cov, all_tro = {}, {}, []
    for path in [p for p in samples.split(",") if p]:
        with open(path, encoding="utf-8") as fh:
            trades = json.load(fh)["H-MARI-B-001"]
        name = os.path.basename(os.path.dirname(path))
        tro, cov[name] = collect(trades)
        all_tro += tro
        per[name] = evaluate(tro, SURGE)
        cov[name]["period"] = [datetime.fromtimestamp(min(t["entry_ts"] for t in trades) / 1000, timezone.utc).strftime("%Y-%m-%d"),
                               datetime.fromtimestamp(max(t["entry_ts"] for t in trades) / 1000, timezone.utc).strftime("%Y-%m-%d")]
    hid = "H-MARI-O-043" if pooled else "H-MARI-O-042"
    pool = evaluate(all_tro, SURGE) if pooled else None
    if pooled:
        per["ادغام"] = pool
        cov["ادغام"] = {"trades_total": sum(c["trades_total"] for c in cov.values()), "with_oi": len(all_tro),
                         "period": [min(c["period"][0] for c in cov.values()), max(c["period"][1] for c in cov.values())]}
        verdict = {hid: pooled_verdict({k: v for k, v in per.items() if k != "ادغام"}, pool)}
    else:
        verdict = {hid: combine(per)}
    report = {"registered_before_results": True, "registered_at": "2026-11-05T15:05Z" if pooled else "2026-11-05T14:10Z",
              "hypotheses": {hid: OI_HYPOTHESES[hid]},
              "surge_threshold": SURGE, "coverage": cov,
              "known_biases": ["MULTIPLE_TESTS: شمار فرضیه‌ها به ۴۲ می‌رسد.",
                               "فقط ارزهای دارای قرارداد آتی بایننس پوشش داده می‌شوند."],
              "results": {"per_sample": per, "verdict": verdict}}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "oi_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    md = ["# O-042: جهش موقعیت‌های باز (OI) پیش از ورود شکارچی ساعتی", "",
          f"- {hid}: **{verdict[hid]}** — {OI_HYPOTHESES[hid]}", "",
          "| نمونه | دوره | معامله / با OI | گروه جهش: تعداد / میانگین ٪ / برد ٪ / حد ضرر ٪ | بقیه: تعداد / میانگین ٪ / برد ٪ / حد ضرر ٪ | بقیه منهای جهش ٪ [CI95] | حکم |",
          "|---|---|---|---|---|---|---|"]
    for name, x in per.items():
        c = cov[name]
        def g(e):
            return f"{e['n']} / {e['mean_pnl_pct']} / {e['win_rate_pct']} / {e['stop_loss_pct']}"
        d = x["rest_minus_surge"] or {}
        v = verdict[hid] if name == "ادغام" else ("—" if pooled else x["verdict"])
        md.append(f"| {name} | {c['period'][0]} تا {c['period'][1]} | {c['trades_total']} / {c['with_oi']} | {g(x['surge'])} | "
                  f"{g(x['rest'])} | {d.get('diff_pct')} [{d.get('ci95_low')}, {d.get('ci95_high')}] | {v} |")
    md += ["", "| نمونه | سود خالص همه (تتر) | بدون گروه جهش (تتر) | صدک‌های جهش OI ٪ (۱۰/۵۰/۹۰/۹۹) |", "|---|---|---|---|"]
    for name, x in per.items():
        md.append(f"| {name} | {x['info_net_pnl_all_usdt']} | {x['info_net_pnl_without_surge_usdt']} | {x['oi_change_percentiles_pct']} |")
    md += ["", "> همه‌چیز تمرینی است — بدون سفارش واقعی"]
    with open(os.path.join(out_dir, "oi_report_fa.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    return report


def run_p044_research(out_dir: str = "research_out") -> dict:
    """P-044: سبد روند BTC + ETH در برابر T-006 تنهای BTC، در دو دوره."""
    from .ideas7 import P044_HYPOTHESES, run_p044
    start_ms = int(datetime(2018, 6, 1, tzinfo=timezone.utc).timestamp() * 1000)
    end = int(time.time() * 1000) // DAY_MS * DAY_MS
    daily = {}
    for s in ("BTCUSDT", "ETHUSDT"):
        bars = fetch_history(s, start_ms - 260 * DAY_MS, end, interval="1d")
        daily[s] = quality_check(bars, interval_ms=DAY_MS)["clean"]
    res = run_p044(daily, end)
    report = {"registered_before_results": True, "registered_at": "2026-11-05T17:20Z", "hypotheses": P044_HYPOTHESES,
              "known_biases": ["MULTIPLE_TESTS: شمار فرضیه‌ها به ۴۴ می‌رسد."], "results": res}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "p044_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    md = ["# P-044: سبد روند BTC + ETH", "",
          f"- H-MARI-P-044: **{res['verdict']['H-MARI-P-044']}** — {P044_HYPOTHESES['H-MARI-P-044']}", "",
          "| دوره | روش | بازده کل ٪ | بیشترین افت ٪ | شارپ | معامله | روز نقد ٪ |", "|---|---|---|---|---|---|---|"]
    for per, x in res["by_period"].items():
        for name, st in x.items():
            md.append(f"| {per} | {name} | {st.get('total_return_pct')} | {st.get('max_drawdown_pct')} | {st.get('sharpe')} | "
                      f"{st.get('trades')} | {st.get('time_in_cash_pct')} |")
    md += ["", "> همه‌چیز تمرینی است — بدون سفارش واقعی"]
    with open(os.path.join(out_dir, "p044_report_fa.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    return report


def run_dsr_audit(start: str = "2018-06-01", n_trials: int = 64, out_dir: str = "research_out") -> dict:
    """شارپ تعدیل‌شده برای روش‌های قبول‌شده: آیا لبه پس از تصحیح چندآزمونی می‌ماند؟

    سری بازده روزانهٔ هر روش از نو ساخته می‌شود (تصمیم روی بستهٔ t، اجرا روی بستهٔ t+1).
    پراکندگی شارپ آزمون‌ها ناشناخته است، پس DSR برای چند مقدار گزارش می‌شود (تحلیل حساسیت).
    """
    from .classics import hold_btc, run_weights, turtle
    from .dsr import deflated_sharpe, verdict
    from .macro import t006_fn
    start_ms = int(datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    end = int(time.time() * 1000) // DAY_MS * DAY_MS
    bars = fetch_history("BTCUSDT", start_ms - 260 * DAY_MS, end, interval="1d")
    daily = {"BTCUSDT": quality_check(bars, interval_ms=DAY_MS)["clean"]}
    strategies = {"T-006 (BTC بالای SMA150)": t006_fn,
                  "C-007 (لاک‌پشت ۵۵/۲۰)": turtle,
                  "BTC_BUY_HOLD (مرجع)": hold_btc}
    out = {}
    for name, fn in strategies.items():
        st, curve, _ = run_weights(daily, ["BTCUSDT"], start_ms, end, fn)
        rets = [curve[i] / curve[i - 1] - 1 for i in range(1, len(curve)) if curve[i - 1] > 0]
        row = {"backtest": {k: st.get(k) for k in ("total_return_pct", "max_drawdown_pct", "sharpe", "trades")},
               "sensitivity": {}}
        for sd in (0.02, 0.04, 0.06, 0.08):      # پراکندگی شارپ روزانهٔ آزمون‌ها (فرض‌های محافظه‌کارانه تا سخت‌گیرانه)
            d = deflated_sharpe(rets, n_trials, sd)
            d["verdict"] = verdict(d["dsr"])
            row["sensitivity"][f"sd_trial_sharpes={sd}"] = d
        out[name] = row
    report = {
        "method": "Deflated Sharpe Ratio — Bailey و López de Prado (۲۰۱۴)",
        "why": "با ۶۰+ فرضیهٔ آزموده‌شده، «بهترین» نتیجه حتی روی دادهٔ تصادفی هم شارپ بالا نشان می‌دهد.",
        "n_trials_assumed": n_trials,
        "period": {"from": start, "to": datetime.fromtimestamp(end / 1000, timezone.utc).strftime("%Y-%m-%d")},
        "note": "پراکندگی شارپِ آزمون‌ها ثبت نشده بود؛ به‌جای یک عدد، چهار فرض گزارش می‌شود.",
        "results": out,
    }
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "dsr_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    md = ["# شارپ تعدیل‌شده: آیا لبه پس از ۶۰+ آزمون می‌ماند؟", "",
          f"- روش: {report['method']}", f"- دوره: {start} تا {report['period']['to']}",
          f"- تعداد آزمون فرض‌شده: {n_trials}", f"- {report['note']}", "",
          "| روش | شارپ سالانه | چولگی | کشیدگی | آستانهٔ شانس (sd=۰٫۰۴) | DSR (sd=۰٫۰۴) | حکم |",
          "|---|---|---|---|---|---|---|"]
    for name, row in out.items():
        d = row["sensitivity"]["sd_trial_sharpes=0.04"]
        ok = "✅ معنادار" if d["verdict"].startswith("SIGNIFICANT") else "❌ معنادار نیست"
        md.append(f"| {name} | {d['sharpe_annual']} | {d['skew']} | {d['kurtosis']} | "
                  f"{d['threshold_sharpe_annual']} | {d['dsr']} | {ok} |")
    md += ["", "## حساسیت به پراکندگی شارپ آزمون‌ها", "", "| روش | sd=۰٫۰۲ | sd=۰٫۰۴ | sd=۰٫۰۶ | sd=۰٫۰۸ |",
           "|---|---|---|---|---|"]
    for name, row in out.items():
        cells = " | ".join(str(row["sensitivity"][f"sd_trial_sharpes={sd}"]["dsr"]) for sd in (0.02, 0.04, 0.06, 0.08))
        md.append(f"| {name} | {cells} |")
    md += ["", "DSR یعنی احتمال اینکه لبه واقعی باشد و صرفاً از «بهترین‌چینی میان ده‌ها آزمون» نیامده باشد.",
           "قاعدهٔ متعارف: DSR ≥ ۰٫۹۵ لازم است.", "", "> همه‌چیز تمرینی است — بدون سفارش واقعی"]
    with open(os.path.join(out_dir, "dsr_report_fa.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    return report
