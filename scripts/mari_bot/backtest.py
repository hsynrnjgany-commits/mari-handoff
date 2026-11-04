# -*- coding: utf-8 -*-
"""بازپخش تاریخی (Replay) و شاخص‌های عملکرد دائمی (CORE-DOCTRINE بخش ۱۲).

هشدار صادقانه: نتیجهٔ بازپخش روی چند هفته داده «مشاهده» است، نه اثبات لبه.
برای ادعای لبه آزمون‌های بخش ۱۱ (خارج از نمونه، بوت‌استرپ، حذف دُم، حساسیت هزینه) لازم است.
"""
from __future__ import annotations

import math
import random

from .config import BotConfig
from .data import quality_check
from .engine import MariBot
from .ledger import Ledger
from .trend import SymbolSeries


def build_series(raw: dict[str, list[dict]], cfg: BotConfig):
    series, quality = {}, {}
    for sym, bars in raw.items():
        q = quality_check(bars)
        quality[sym] = {"ok": q["ok"], "issues": q["issues"], "n": q["n"]}
        if q["n"] >= cfg.trend.min_bars + 2:
            series[sym] = SymbolSeries(sym, q["clean"], cfg.trend)
    return series, quality


def max_drawdown(curve: list[tuple]) -> float:
    peak, mdd = -math.inf, 0.0
    for _, eq in curve:
        peak = max(peak, eq)
        if peak > 0:
            mdd = max(mdd, (peak - eq) / peak)
    return mdd * 100


def metrics(trades: list[dict], curve: list[tuple], start_equity: float) -> dict:
    n = len(trades)
    wins = [t for t in trades if t["pnl_usdt"] > 0]
    losses = [t for t in trades if t["pnl_usdt"] <= 0]
    gw, gl = sum(t["pnl_usdt"] for t in wins), -sum(t["pnl_usdt"] for t in losses)
    end_eq = curve[-1][1] if curve else start_equity
    caps = [t["capture_ratio"] for t in wins if t.get("capture_ratio") is not None]
    gives = [t["giveback_pct"] for t in wins]
    early = [t for t in trades if t.get("after_exit_24h_pct") is not None and t["after_exit_24h_pct"] > 3.0]
    return {
        "trades": n,
        "win_rate_pct": round(len(wins) / n * 100, 1) if n else None,
        "profit_factor": round(gw / gl, 2) if gl > 0 else (None if not wins else float("inf")),
        "net_return_pct": round((end_eq / start_equity - 1) * 100, 3),
        "max_drawdown_pct": round(max_drawdown(curve), 3),
        "avg_winner_pct": round(sum(t["pnl_pct"] for t in wins) / len(wins), 3) if wins else None,
        "avg_loser_pct": round(sum(t["pnl_pct"] for t in losses) / len(losses), 3) if losses else None,
        "profit_capture_ratio": round(sum(caps) / len(caps), 3) if caps else None,
        "avg_giveback_pct": round(sum(gives) / len(gives), 3) if gives else None,
        "early_exit_rate_pct": round(len(early) / n * 100, 1) if n else None,
        "avg_held_h": round(sum(t["held_h"] for t in trades) / n, 1) if n else None,
        "exit_reasons": _count(t["exit_reason"] for t in trades),
        "end_equity": round(end_eq, 2),
    }


def _count(it):
    d = {}
    for x in it:
        d[x] = d.get(x, 0) + 1
    return dict(sorted(d.items(), key=lambda kv: -kv[1]))


def bootstrap_ci(trades: list[dict], n_iter: int = 2000, seed: int = 7) -> dict | None:
    """بازهٔ اطمینان ۹۵٪ میانگین بازده هر معامله (بوت‌استرپ ساده)."""
    xs = [t["pnl_pct"] for t in trades]
    if len(xs) < 5:
        return None
    rnd = random.Random(seed)
    means = sorted(sum(rnd.choice(xs) for _ in xs) / len(xs) for _ in range(n_iter))
    return {"mean_pct": round(sum(xs) / len(xs), 3), "ci95_low": round(means[int(0.025 * n_iter)], 3),
            "ci95_high": round(means[int(0.975 * n_iter)], 3)}


def add_counterfactuals(trades: list[dict], series: dict[str, SymbolSeries]) -> None:
    """«اگر ۲۴ ساعت دیرتر می‌فروختم؟» (بخش ۱۰) — فقط پس از اجرا و فقط برای گزارش؛ روی تصمیم اثر ندارد."""
    for t in trades:
        s = series.get(t["symbol"])
        if not s or t["exit_ts"] is None:
            continue
        idx = {b["t"]: i for i, b in enumerate(s.bars)}
        i = idx.get(t["exit_ts"])
        if i is not None and i + 24 < len(s):
            t["after_exit_24h_pct"] = round((s.close[i + 24] / t["avg_exit_px"] - 1) * 100, 3)


def run_backtest(raw: dict[str, list[dict]], cfg: BotConfig | None = None, ledger_path: str | None = None,
                 run_id: str = "BACKTEST") -> dict:
    cfg = cfg or BotConfig()
    series, quality = build_series(raw, cfg)
    led = Ledger(ledger_path, run_id, cfg.sha())
    bot = MariBot(cfg, led)
    bot.process(series, quality)
    add_counterfactuals(bot.trades, series)
    m = metrics(bot.trades, bot.equity_curve, cfg.risk.start_equity)
    m["bootstrap"] = bootstrap_ci(bot.trades)
    m["open_positions"] = len(bot.positions)
    m["symbols"] = len(series)
    m["quality_failed"] = sorted(s for s, q in quality.items() if not q["ok"])
    m["config_sha"] = cfg.sha()
    m["events"] = _count(e["event"] for e in led.events)
    return {"metrics": m, "trades": bot.trades, "bot": bot, "series": series}
