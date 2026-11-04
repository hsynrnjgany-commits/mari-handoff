# -*- coding: utf-8 -*-
"""اجرای زندهٔ تمرینی: هر ساعت دادهٔ عمومی تووبیت را می‌خواند، تصمیم می‌گیرد و فقط روی کاغذ ثبت می‌کند.

گشت سایه‌وار (سند مادر ۳۳.۵): موقعیت‌های باز + BTC + واچ‌لیست + ۴۰ نماد پرحجم + ۶۰ نماد چرخشی از بقیهٔ بازار.
در چند چرخه کل بازار زیر پوشش می‌رود؛ هیچ نمادی به‌خاطر کم‌حجمی از «کشف» حذف نمی‌شود.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

from .config import BotConfig, assert_locks, tradable_symbol
from .data import LAST_TICKER, DataError, SourcePicker, drop_unclosed, fetch_quote_volumes, fetch_universe, quality_check
from .engine import MariBot
from .ledger import Ledger
from .btc_trend import DAY_MS, BtcTrend
from .telegram import Telegram, fmt_btc_event, fmt_channel_event, fmt_event, fmt_health

LEDGER_URL = "https://github.com/hsynrnjgany-commits/mari-handoff/blob/mari-bot-state/ledger.jsonl"
from .trend import SymbolSeries

HOUR_MS = 3_600_000


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def _save(path, obj):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False)
    os.replace(tmp, path)


class LiveRunner:
    def __init__(self, state_dir: str, cfg: BotConfig | None = None, watchlist: list[str] | None = None,
                 top_n: int = 40, rotate_n: int = 60, bars: int = 300):
        assert_locks()
        self.cfg = cfg or BotConfig()
        self.dir = state_dir
        self.state_path = os.path.join(state_dir, "state.json")
        self.meta_path = os.path.join(state_dir, "meta.json")
        self.watchlist, self.top_n, self.rotate_n, self.bars = watchlist or [], top_n, rotate_n, bars
        state = _load(self.state_path, None)
        if state and state.get("config_sha") not in (None, self.cfg.sha()):
            print("⚠️ تنظیمات عوض شده؛ وضعیت قبلی با همان شناسه ادامه می‌یابد اما در دفتر ثبت می‌شود.")
        self.meta = _load(self.meta_path, {"rotate_cursor": 0, "universe": [], "universe_ts": 0, "cycles": 0})
        run_id = "LIVE-PAPER-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.ledger = Ledger(os.path.join(state_dir, "ledger.jsonl"), run_id, self.cfg.sha())
        self.bot = MariBot(self.cfg, self.ledger, state)
        self.tg = Telegram(os.path.join(state_dir, "telegram.json"))
        self.btc = BtcTrend(os.path.join(state_dir, "btc_trend.json"))
        self.bot.btc_summary = self.btc.summary() if self.btc.s["position"] else None

    # ---------------------------------------------------------------- انتخاب نمادها
    def _universe(self) -> list[str]:
        if not self.meta["universe"] or time.time() - self.meta["universe_ts"] > 86_400:
            try:
                self.meta["universe"] = [s for s in fetch_universe() if tradable_symbol(s)]
                self.meta["universe_ts"] = time.time()
            except DataError as e:
                print(f"universe ناموفق ({e}) — از نسخهٔ قبلی/واچ‌لیست استفاده می‌شود")
        return self.meta["universe"]

    def patrol_symbols(self) -> list[str]:
        uni = self._universe()
        try:
            qv = fetch_quote_volumes()
        except DataError:
            qv = {}
        ranked = sorted(uni, key=lambda s: -(qv.get(s) or 0))     # رتبه فقط «اولویت گشت» است
        head = ranked[: self.top_n]
        rest = ranked[self.top_n:]
        cur = self.meta["rotate_cursor"] % max(1, len(rest)) if rest else 0
        rot = (rest[cur:] + rest[:cur])[: self.rotate_n]
        self.meta["rotate_cursor"] = cur + self.rotate_n
        must = [self.cfg.benchmark, *self.bot.positions, *self.bot.pending, *self.watchlist]
        seen, out = set(), []
        for s in must + head + rot:
            if s not in seen:
                seen.add(s)
                out.append(s)
        return out

    # ---------------------------------------------------------------- یک چرخه
    def cycle(self) -> dict:
        t0 = time.time()
        syms = self.patrol_symbols()
        series, quality, failed = {}, {}, []
        now_ms = int(time.time() * 1000)
        src = SourcePicker()
        for sym in syms:
            try:
                bars = drop_unclosed(src.klines(sym, self.cfg.interval, self.bars), now_ms)
            except DataError:
                failed.append(sym)
                continue
            q = quality_check(bars)
            quality[sym] = {"ok": q["ok"], "issues": q["issues"]}
            if q["n"] >= self.cfg.trend.min_bars + 2:
                series[sym] = SymbolSeries(sym, q["clean"], self.cfg.trend)
            time.sleep(0.12)          # رعایت محدودیت نرخ
        if not series:
            self.ledger.write("CYCLE_FAILED", reason="NO_DATA", failed=len(failed))
            self._health(False, "دادهٔ بازار دریافت نشد")
            return {"ok": False, "reason": "NO_DATA", "failed": len(failed)}
        latest = max(s.bars[-1]["t"] for s in series.values())
        if not self.bot.last_ts:
            # شروع تازه: گذشته را بازپخش نکن (معاملهٔ ساختگی از گذشته ممنوع) — فقط از آخرین کندل بسته
            self.bot.last_ts = latest - HOUR_MS
            self.ledger.write("BOOT", ts=latest, note="شروع تازه از آخرین کندل بسته", symbols=len(series))
        self.bot.new_events = []
        self.bot.process(series, quality)
        _save(self.state_path, self.bot.to_state())
        self.meta["cycles"] += 1
        self._health(True, None)
        _save(self.meta_path, self.meta)
        btc_events = []
        try:
            daily = drop_unclosed(src.klines("BTCUSDT", "1d", 220), now_ms, DAY_MS)
            if quality_check(daily, interval_ms=DAY_MS)["ok"]:
                btc_events = self.btc.update(daily)
            self.bot.btc_summary = self.btc.summary()
        except DataError as e:
            self.ledger.write("BTC_TREND_DATA_FAIL", error=str(e)[:200])
        for ev in btc_events:
            self.ledger.write("BTC_TREND_SWITCH", ts=ev["t"], **{k: v for k, v in ev.items() if k != "t"})
        self.tg.check()
        sent = 0
        self.tg.maybe_hello(self.bot)
        for ev in btc_events:
            sent += self.tg.broadcast(fmt_btc_event(ev, self.btc.summary()))
            self.tg.post_channel(fmt_channel_event(ev, self.btc.summary(), LEDGER_URL))
        self.tg.maybe_channel_intro(self.bot.btc_summary, LEDGER_URL)
        self.tg.maybe_weekly_channel(self.bot.btc_summary, LEDGER_URL)
        for rec in self.bot.new_events:
            msg = fmt_event(rec)
            if msg:
                sent += self.tg.broadcast(msg)
        self.tg.maybe_daily(self.bot)
        self.tg.handle_updates(self.bot, wait=0)      # پاسخ به فرمان‌هایی که از چرخهٔ قبل رسیده‌اند
        uni = set(self.meta.get("universe") or [])
        ch = {k: v for k, v in LAST_TICKER["changes"].items() if (not uni or k in uni) and v == v}
        market = {"source": LAST_TICKER["source"], "pairs": len(ch),
                  "up_24h": sum(1 for v in ch.values() if v > 0),
                  "down_24h": sum(1 for v in ch.values() if v < 0),
                  "up_over_5pct": sum(1 for v in ch.values() if v >= 5),
                  "down_over_5pct": sum(1 for v in ch.values() if v <= -5)}
        states = {}
        for v in self.bot.snapshot.values():
            states[v["state"]] = states.get(v["state"], 0) + 1
        market["trend_states_scanned"] = dict(sorted(states.items()))
        summary = {"btc_trend": self.bot.btc_summary, "market": market, "sources": src.counts(), "ok": True, "symbols": len(series), "failed": len(failed), "last_ts": self.bot.last_ts,
                   "open": len(self.bot.positions), "events": len(self.bot.new_events),
                   "equity": round(self.bot.equity(), 2), "btc": self.bot.btc_state,
                   "seconds": round(time.time() - t0, 1), "telegram_sent": sent, "telegram": self.tg.diag}
        self.ledger.write("CYCLE", **summary)
        return summary

    def _health(self, ok: bool, why: str | None) -> None:
        """نگهبان سلامت: بعد از ۳ چرخهٔ ناموفق پیاپی به صاحب ربات خبر می‌دهد؛ بعد از بهبود هم خبر می‌دهد."""
        streak = self.meta.get("fail_streak", 0)
        if ok:
            if self.meta.get("alerted"):
                self.tg.broadcast(fmt_health(True, streak, None))
                self.meta["alerted"] = False
            self.meta["fail_streak"] = 0
        else:
            self.meta["fail_streak"] = streak + 1
            if self.meta["fail_streak"] >= 3 and not self.meta.get("alerted"):
                self.tg.broadcast(fmt_health(False, self.meta["fail_streak"], why))
                self.meta["alerted"] = True
        _save(self.meta_path, self.meta)

    def loop(self, poll_s: int = 5) -> None:
        print("ربات ماری (تمرینی) شروع شد. توقف: Ctrl+C")
        next_run = 0.0
        while True:
            now = time.time()
            if now >= next_run:
                try:
                    print(json.dumps(self.cycle(), ensure_ascii=False))
                except Exception as e:  # noqa: BLE001 — تحمل خطا: چرخهٔ بعد دوباره تلاش می‌کند
                    self.ledger.write("CYCLE_ERROR", error=type(e).__name__, detail=str(e)[:300])
                    print(f"خطای چرخه: {type(e).__name__}: {e}")
                # ۹۰ ثانیه پس از بسته‌شدن هر کندل ساعتی
                next_run = (int(time.time() // 3600) + 1) * 3600 + 90
            self.tg.handle_updates(self.bot, wait=0)
            time.sleep(poll_s)
