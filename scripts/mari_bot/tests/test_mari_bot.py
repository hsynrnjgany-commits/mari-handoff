# -*- coding: utf-8 -*-
"""آزمون‌های ربات ماری — اجرا از پوشهٔ scripts:  python3 -m unittest discover -s mari_bot/tests -t ."""
from __future__ import annotations

import json
import math
import os
import re
import tempfile
import unittest
from unittest import mock

from mari_bot import data as D
from mari_bot import indicators as I
from mari_bot.backtest import run_backtest
from mari_bot.config import LOCK_LINE, BotConfig, CostParams, ExitParams, RiskParams, tradable_symbol
from mari_bot.ledger import Ledger, verify_chain
from mari_bot.position import Position, manage
from mari_bot.risk import RiskGate
from mari_bot.telegram import fa, fmt_event, fmt_hunt, fmt_report, fmt_trades
from mari_bot.trend import SymbolSeries, classify

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL = os.path.join(os.path.dirname(PKG), "mari_megatrend", "data")
H = 3_600_000


def synth(n=400, drift=0.002, vol=0.004, start=100.0, t0=1_700_000_000_000, seed=1):
    import random
    rnd = random.Random(seed)
    bars, px = [], start
    for i in range(n):
        o = px
        c = o * (1 + drift + rnd.uniform(-vol, vol))
        h = max(o, c) * (1 + rnd.uniform(0, vol))
        l = min(o, c) * (1 - rnd.uniform(0, vol))
        v = 1000 + rnd.uniform(0, 200) + (400 if i % 25 == 0 else 0)
        bars.append({"t": t0 + i * H, "o": o, "h": h, "l": l, "c": c, "v": v, "qv": v * c})
        px = c
    return bars


class TestLocks(unittest.TestCase):
    def test_no_order_paths_in_package(self):
        bad = re.compile(r"(spot/order|/order\b|openOrders|X-BB-APIKEY|signature=|hmac|api_secret|newOrder)", re.I)
        for root, _, files in os.walk(PKG):
            if "tests" in root:
                continue
            for f in files:
                if f.endswith(".py"):
                    with open(os.path.join(root, f), encoding="utf-8") as fh:
                        self.assertIsNone(bad.search(fh.read()), f"مسیر سفارش در {f}")

    def test_http_rejects_non_quote_paths(self):
        with self.assertRaises(D.DataError):
            D.http_get_json("/api/v1/spot/order", {"symbol": "BTCUSDT"})

    def test_symbol_filter(self):
        self.assertTrue(tradable_symbol("BTCUSDT"))
        self.assertTrue(tradable_symbol("SYRUPUSDT"))
        self.assertFalse(tradable_symbol("USDCUSDT"))
        self.assertFalse(tradable_symbol("BTC3LUSDT"))
        self.assertFalse(tradable_symbol("牛来USDT"))


class TestIndicators(unittest.TestCase):
    def test_ema_constant(self):
        e = I.ema([5.0] * 30, 10)
        self.assertTrue(math.isnan(e[8]))
        self.assertAlmostEqual(e[-1], 5.0)

    def test_atr_constant_range(self):
        bars = [{"o": 10, "h": 11, "l": 9, "c": 10} for _ in range(30)]
        self.assertAlmostEqual(I.atr(bars, 14)[-1], 2.0)

    def test_rsi_bounds(self):
        r = I.rsi([float(i) for i in range(50)], 14)
        self.assertEqual(r[-1], 100.0)


class TestTrend(unittest.TestCase):
    def test_no_lookahead(self):
        bars = synth(400, drift=0.001)
        full = SymbolSeries("X", bars)
        for t in (200, 280, 350):
            cut = SymbolSeries("X", bars[: t + 1])
            a, b = classify(full, t), classify(cut, t)
            self.assertEqual(a.state, b.state)
            self.assertAlmostEqual(a.score, b.score, places=6)

    def test_states(self):
        self.assertIn(classify(SymbolSeries("U", synth(400, 0.003)), 399).state, ("A", "B"))
        self.assertIn(classify(SymbolSeries("D", synth(400, -0.003)), 399).state, ("E", "F"))
        self.assertEqual(classify(SymbolSeries("S", synth(100)), 99).state, "H")
        crash = synth(400, 0.001)
        for k in range(4):
            b = crash[-4 + k]
            f = 0.97 ** (k + 1)
            for key in ("o", "h", "l", "c"):
                b[key] *= f
        self.assertEqual(classify(SymbolSeries("C", crash), 399).state, "G")


def _pos(entry=100.0, stop=95.0):
    p = Position("X", 0, entry, 10.0, stop, entry - stop, "B", "test")
    return p


class TestPosition(unittest.TestCase):
    ex, cost = ExitParams(), CostParams(fee_side=0.0, slippage=0.0)

    def bar(self, o, h, l, c, t=H):
        return {"t": t, "o": o, "h": h, "l": l, "c": c}

    def test_stop_full_exit(self):
        p = _pos()
        f = manage(p, self.bar(99, 99, 94, 96), "B", 1.0, self.ex, self.cost)
        self.assertEqual(p.qty, 0)
        self.assertEqual(f[0].price, 95.0)
        self.assertEqual(f[0].reason, "STOP_LOSS")

    def test_gap_fill_at_open(self):
        p = _pos()
        f = manage(p, self.bar(90, 91, 89, 90), "B", 1.0, self.ex, self.cost)
        self.assertEqual(f[0].price, 90)

    def test_uptrend_holds_and_trails(self):
        p = _pos()
        manage(p, self.bar(100, 110, 100, 109), "A", 1.0, self.ex, self.cost)
        self.assertEqual(p.qty, 10.0)                  # روند قوی: هیچ فروشی
        self.assertAlmostEqual(p.stop, 110 - 3.0)      # حد ضرر متحرک ۳ATR از اوج
        manage(p, self.bar(109, 109, 108, 108.5, 2 * H), "A", 1.0, self.ex, self.cost)
        self.assertAlmostEqual(p.stop, 107.0)          # فقط بالا می‌رود

    def test_staged_exit(self):
        p = _pos()
        manage(p, self.bar(100, 101, 99.5, 100.5), "E", 1.0, self.ex, self.cost)
        self.assertAlmostEqual(p.qty, 5.0)             # مرحلهٔ ۳: نیمی فروخته شد
        self.assertEqual(p.stage, 3)
        manage(p, self.bar(100.5, 101, 99.6, 100, 2 * H), "E", 1.0, self.ex, self.cost)
        self.assertAlmostEqual(p.qty, 5.0)             # تکرار نمی‌شود
        manage(p, self.bar(100, 100, 99.7, 99.8, 3 * H), "G", 1.0, self.ex, self.cost)
        self.assertEqual(p.qty, 0)
        self.assertEqual(p.max_stage, 5)

    def test_profit_scaling_not_in_strong_trend(self):
        p = _pos()
        manage(p, self.bar(100, 116, 100, 115), "A", 2.0, self.ex, self.cost)
        self.assertEqual(p.qty, 10.0)                  # ۳٫۲R ولی روند A: برداشت نمی‌شود
        manage(p, self.bar(115, 116, 115, 115.5, 2 * H), "B", 2.0, self.ex, self.cost)
        self.assertAlmostEqual(p.qty, 7.5)


class TestRisk(unittest.TestCase):
    def test_gate(self):
        g = RiskGate(RiskParams())
        ok = dict(open_symbols=set(), btc_state="B", data_ok=True, median_qv=1e6)
        self.assertEqual(g.check_entry("SOLUSDT", 0, **ok), [])
        self.assertIn("MAX_POSITIONS", g.check_entry("SOLUSDT", 0, **{**ok, "open_symbols": set("abcde")}))
        self.assertIn("BTC_REGIME_G", g.check_entry("SOLUSDT", 0, **{**ok, "btc_state": "G"}))
        self.assertIn("LOW_LIQUIDITY", g.check_entry("SOLUSDT", 0, **{**ok, "median_qv": 10}))
        g.on_close("SOLUSDT", 0, -1)
        self.assertIn("COOLDOWN", g.check_entry("SOLUSDT", 3 * H, **ok))
        self.assertEqual(g.check_entry("SOLUSDT", 6 * H, **ok), [])
        g.on_close("A", 0, -1)
        self.assertTrue(g.on_close("B", 0, -1))        # سومین ضرر پیاپی → فیوز
        self.assertIn("LOSS_FUSE_ACTIVE", g.check_entry("SOLUSDT", 10 * H, **ok))
        self.assertNotIn("LOSS_FUSE_ACTIVE", g.check_entry("SOLUSDT", 25 * H, **ok))

    def test_require_btc_bullish(self):
        g = RiskGate(RiskParams(require_btc_states=("A", "B")))
        ok = dict(open_symbols=set(), data_ok=True, median_qv=1e6)
        self.assertEqual(g.check_entry("SOLUSDT", 0, btc_state="B", **ok), [])
        self.assertIn("BTC_NOT_IN_AB", g.check_entry("SOLUSDT", 0, btc_state="D", **ok))

    def test_size_respects_caps(self):
        g = RiskGate(RiskParams())
        q = g.size(100, 99, 1000, 0.001)               # ریسک ۱٪ → ۱۰ واحد، اما سقف ۲۰٪ → ۲ واحد
        self.assertAlmostEqual(q, 2.0)


class TestLedger(unittest.TestCase):
    def test_chain_and_tamper(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "l.jsonl")
            led = Ledger(p, "R", "cfg")
            for i in range(5):
                led.write("X", ts=i, v=i)
            self.assertTrue(verify_chain(p)["ok"])
            Ledger(p, "R2", "cfg").write("Y", ts=9)     # ادامهٔ زنجیره پس از راه‌اندازی دوباره
            self.assertTrue(verify_chain(p)["ok"])
            with open(p) as fh:
                lines = fh.read().splitlines()
            rec = json.loads(lines[2])
            rec["v"] = 999
            lines[2] = json.dumps(rec)
            with open(p, "w") as fh:
                fh.write("\n".join(lines) + "\n")
            self.assertFalse(verify_chain(p)["ok"])


class TestQuality(unittest.TestCase):
    def test_detects_issues(self):
        bars = synth(50)
        bad = bars[:10] + [bars[9]] + bars[12:]               # تکرار + شکاف
        bad.append({**bars[-1], "t": bars[-1]["t"] + H, "h": 1, "l": 2})  # کندل ناممکن
        q = D.quality_check(bad)
        self.assertEqual(q["dupes"], 1)
        self.assertEqual(q["gaps"], 2)
        self.assertEqual(q["bad"], 1)

    def test_parse_toobit_rows(self):
        rows = [[1000, "1", "2", "0.5", "1.5", "10", 1999, "15", 3]]
        b = D.parse_toobit_klines(rows)[0]
        self.assertEqual((b["t"], b["c"], b["qv"]), (1000, 1.5, 15.0))

    def test_change_map_formats(self):
        m = D._change_map([{"s": "AUSDT", "o": "100", "c": "110"},
                           {"symbol": "BUSDT", "priceChangePercent": "-3.5", "openPrice": "10", "lastPrice": "9.65"}])
        self.assertAlmostEqual(m["AUSDT"], 10.0)
        self.assertAlmostEqual(m["BUSDT"], -3.5)

    def test_drop_unclosed(self):
        bars = synth(3, t0=0)
        self.assertEqual(len(D.drop_unclosed(bars, now_ms=2 * H + 10)), 2)


@unittest.skipUnless(os.path.isdir(LOCAL), "دادهٔ محلی موجود نیست")
class TestBacktest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = D.load_local_dir(LOCAL)
        cls.r = run_backtest(cls.raw)

    def test_deterministic(self):
        r2 = run_backtest(self.raw)
        self.assertEqual(self.r["metrics"]["end_equity"], r2["metrics"]["end_equity"])
        self.assertEqual(len(self.r["trades"]), len(r2["trades"]))

    def test_cash_accounting(self):
        bot, start = self.r["bot"], BotConfig().risk.start_equity
        expected = (start + sum(t["pnl_usdt"] for t in bot.trades)
                    + sum(p.realized() - p.entry_px * p.qty for p in bot.positions.values()))
        self.assertAlmostEqual(bot.gate.s.cash, expected, delta=0.05)

    def test_risk_limits_never_breached(self):
        bot = self.r["bot"]
        open_count, worst = 0, 0
        for e in bot.ledger.events:
            if e["event"] == "ENTRY":
                open_count += 1
                self.assertLessEqual(e["notional"], e["equity"] * 0.2 + 0.02)
                self.assertLessEqual(e["risk_usdt"], e["equity"] * 0.01 + 0.02)
            elif e["event"] == "CLOSED":
                open_count -= 1
            worst = max(worst, open_count)
        self.assertLessEqual(worst, 5)

    def test_no_stable_entries(self):
        self.assertTrue(all(tradable_symbol(t["symbol"]) for t in self.r["trades"]))


class TestTelegramFormat(unittest.TestCase):
    def test_messages(self):
        r = run_backtest({"BTCUSDT": synth(400, 0.002), "ETHUSDT": synth(400, 0.003, seed=3)})
        bot = r["bot"]
        for msg in (fmt_report(bot), fmt_trades(bot), fmt_hunt(bot)):
            self.assertTrue(msg.rstrip().endswith(LOCK_LINE))
            self.assertNotRegex(msg, r"[0-9]")         # اعداد فارسی
        for e in bot.ledger.events:
            m = fmt_event(e)
            if m:
                self.assertIn(LOCK_LINE, m)
        self.assertEqual(fa(1234.5), "۱،۲۳۴٫۵۰")


class TestTelegramOwnerMode(unittest.TestCase):
    def test_owner_id_never_saved_and_strangers_ignored(self):
        from mari_bot.telegram import Telegram
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.dict(os.environ, {"MARI_TELEGRAM_TOKEN": "x", "MARI_TELEGRAM_CHAT_ID": "12345"}):
            p = os.path.join(d, "tg.json")
            tg = Telegram(p)
            self.assertEqual(tg.store["subscribers"], [12345])
            upd = {"ok": True, "result": [
                {"update_id": 1, "message": {"text": "/report", "chat": {"id": 999}}},
                {"update_id": 2, "message": {"text": "/help", "chat": {"id": 12345}}}]}
            sent = []
            with mock.patch.object(tg, "_call", side_effect=lambda m, prm, **k: (upd, 200) if m == "getUpdates"
                                   else (sent.append(prm["chat_id"]) or ({"ok": True}, 200))):
                tg.handle_updates(bot=None)
            self.assertEqual(sent, [12345])
            with open(p) as fh:
                self.assertNotIn("12345", fh.read())

    def test_hello_and_daily_only_when_enabled(self):
        from mari_bot.telegram import Telegram
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.dict(os.environ, {"MARI_TELEGRAM_TOKEN": "", "TELEGRAM_BOT_TOKEN": "",
                                             "MARI_TELEGRAM_CHAT_ID": ""}):
            tg = Telegram(os.path.join(d, "tg.json"))
            bot = run_backtest({"BTCUSDT": synth(300)})["bot"]
            self.assertFalse(tg.maybe_daily(bot, hour=0))
            self.assertEqual(tg.store["last_daily"], "")       # خاموش: روز مصرف نمی‌شود
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.dict(os.environ, {"MARI_TELEGRAM_TOKEN": "x", "MARI_TELEGRAM_CHAT_ID": "7"}):
            tg = Telegram(os.path.join(d, "tg.json"))
            with mock.patch.object(tg, "_call", return_value=(None, 400)):
                self.assertFalse(tg.maybe_hello(bot))
                self.assertFalse(tg.store["hello_sent"])       # ناموفق: دوباره تلاش می‌شود
                self.assertEqual(tg.diag["fail_codes"], [400])
            with mock.patch.object(tg, "_call", return_value=({"ok": True}, 200)):
                self.assertTrue(tg.maybe_hello(bot))
                self.assertFalse(tg.maybe_hello(bot))          # فقط یک بار

    def test_fallback_source_paths_allowed_only_readonly(self):
        with self.assertRaises(D.DataError):
            D.http_get_json("/api/v3/order", base=D.BINANCE_VISION)
        with self.assertRaises(D.DataError):
            D.http_get_json("/api/v3/klines", base="https://evil.example")


class TestResearch(unittest.TestCase):
    def test_offline_research_pipeline(self):
        from mari_bot import research as R
        t_end = 1_700_000_000_000 + 1500 * H
        data = {"BTCUSDT": synth(1500, 0.0005), "SOLUSDT": synth(1500, 0.001, seed=4),
                "ETHUSDT": synth(1500, -0.0005, seed=9)}
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(R, "pick_universe", return_value=list(data)), \
                mock.patch.object(R, "fetch_history", side_effect=lambda s, a, b: data[s]), \
                mock.patch.object(R.time, "time", return_value=t_end / 1000):
            rep = R.run_research(months=1, top=3, out_dir=d)
            self.assertEqual(set(rep["results"]), set(R.HYPOTHESES))
            for x in rep["results"].values():
                self.assertIn(x["verdict"], ("FALSIFIED", "INCONCLUSIVE", "SUPPORTED_IN_TEST_RANGE"))
                self.assertEqual(len(x["cost_sensitivity"]), 5)
                self.assertTrue(x["folds"])
                nets = [v["net_return_pct"] for v in x["cost_sensitivity"].values()]
                self.assertEqual(nets, sorted(nets, reverse=True))   # هزینهٔ بیشتر هرگز بهتر نیست
            self.assertNotEqual(rep["results"]["H-MARI-B-001"]["config_sha"],
                                rep["results"]["H-MARI-B-002"]["config_sha"])
            self.assertTrue(os.path.exists(os.path.join(d, "report_fa.md")))


class TestMomentum(unittest.TestCase):
    def _daily(self, n, drift, seed, start=1_600_000_000_000 // 86_400_000 * 86_400_000):
        D_ = 86_400_000
        bars = synth(n, drift, 0.02, seed=seed)
        for i, b in enumerate(bars):
            b["t"] = start + i * D_
        return bars

    def test_uptrend_held_downtrend_cash(self):
        from mari_bot.momentum import run_momentum
        up = {"BTCUSDT": self._daily(400, 0.004, 1), "AAAUSDT": self._daily(400, 0.006, 2)}
        r = run_momentum(up, up["BTCUSDT"][100]["t"], up["BTCUSDT"][-1]["t"])
        self.assertGreater(r["strategy"]["total_return_pct"], 0)
        self.assertGreater(r["avg_names_held"], 0)
        dn = {"BTCUSDT": self._daily(400, -0.004, 1), "AAAUSDT": self._daily(400, -0.006, 2)}
        r = run_momentum(dn, dn["BTCUSDT"][100]["t"], dn["BTCUSDT"][-1]["t"])
        self.assertGreater(r["time_in_cash_pct"], 80)              # بازار نزولی: بیشتر نقد
        self.assertGreater(r["strategy"]["total_return_pct"], r["btc_buy_hold"]["total_return_pct"])

    def test_costs_reduce_return(self):
        from mari_bot.momentum import MomParams, run_momentum
        d = {"BTCUSDT": self._daily(500, 0.001, 3), "AAAUSDT": self._daily(500, 0.001, 4),
             "BBBUSDT": self._daily(500, 0.0, 5)}
        a, b = d["BTCUSDT"][100]["t"], d["BTCUSDT"][-1]["t"]
        lo = run_momentum(d, a, b, MomParams(fee_side=0.0, slippage=0.0))["strategy"]["total_return_pct"]
        hi = run_momentum(d, a, b, MomParams(fee_side=0.005))["strategy"]["total_return_pct"]
        self.assertGreater(lo, hi)

    def test_btc_filter_goes_cash_in_bear(self):
        from mari_bot.momentum import MomParams, run_momentum
        btc = self._daily(250, 0.004, 1) + []
        tail = self._daily(200, -0.006, 1, start=btc[-1]["t"] + 86_400_000)
        f = btc[-1]["c"] / tail[0]["o"]
        for b in tail:
            for k in ("o", "h", "l", "c"):
                b[k] *= f
        alt = self._daily(450, 0.003, 7)        # آلت صعودی، BTC نزولی در انتها
        d = {"BTCUSDT": btc + tail, "AAAUSDT": alt}
        a, b = d["BTCUSDT"][300]["t"], d["BTCUSDT"][-1]["t"]
        on = run_momentum(d, a, b, MomParams(btc_sma_filter=200))
        off = run_momentum(d, a, b, MomParams())
        self.assertGreater(on["time_in_cash_pct"], off["time_in_cash_pct"])

    def test_pit_universe_and_delisting(self):
        from mari_bot.momentum import MomParams, run_momentum
        big = self._daily(400, 0.004, 1)
        for b in big:
            b["qv"] = 1e9
        dead = self._daily(250, 0.01, 2)                 # صعود، سپس حذف از صرافی
        for b in dead:
            b["qv"] = 1e9
        tiny = self._daily(400, 0.02, 3)                 # بهترین بازده ولی حجم ناچیز
        for b in tiny:
            b["qv"] = 1.0
        big2 = self._daily(400, 0.003, 4)
        for b in big2:
            b["qv"] = 1e9
        d = {"BTCUSDT": big, "BIGUSDT": big2, "DEADUSDT": dead, "TINYUSDT": tiny}
        a, b = big[100]["t"], big[-1]["t"]
        r0 = run_momentum(d, a, b, MomParams(pit_top=2))
        r5 = run_momentum(d, a, b, MomParams(pit_top=2, delist_haircut=0.5))
        self.assertGreaterEqual(r0["delisted_exits"], 1)
        self.assertGreater(r0["strategy"]["total_return_pct"], r5["strategy"]["total_return_pct"])
        held = run_momentum(d, a, b, MomParams())["symbols_ever_held"]
        self.assertGreater(held, r0["symbols_ever_held"])   # TINY فقط بدون فیلتر حجم نگه داشته می‌شود

    def test_vol_target_reduces_exposure(self):
        from mari_bot.momentum import MomParams, run_momentum
        d = {"BTCUSDT": self._daily(400, 0.004, 1), "AAAUSDT": self._daily(400, 0.006, 2)}
        a, b = d["BTCUSDT"][100]["t"], d["BTCUSDT"][-1]["t"]
        full = run_momentum(d, a, b, MomParams(max_hold=2))
        vt = run_momentum(d, a, b, MomParams(max_hold=2, vol_target=0.05))
        self.assertLess(vt["strategy"]["max_drawdown_pct"], full["strategy"]["max_drawdown_pct"] + 1e-9)
        self.assertLess(abs(vt["strategy"]["total_return_pct"]), abs(full["strategy"]["total_return_pct"]))

    def test_btc_only_daily_trend(self):
        from mari_bot.momentum import MomParams, run_momentum
        d = {"BTCUSDT": self._daily(400, 0.004, 1), "AAAUSDT": self._daily(400, 0.006, 2)}
        a, b = d["BTCUSDT"][160]["t"], d["BTCUSDT"][-1]["t"]
        r = run_momentum(d, a, b, MomParams(only_symbols=("BTCUSDT",), max_hold=1, sma=150,
                                            require_momentum=False, rebalance_weekday=-1, min_age_days=0))
        self.assertEqual(r["symbols_ever_held"], 1)
        self.assertGreater(r["rebalances"], 200)        # تصمیم روزانه
        self.assertGreater(r["strategy"]["total_return_pct"], 0)

    def test_signal_lag_changes_decisions(self):
        from mari_bot.momentum import MomParams, run_momentum
        d = {"BTCUSDT": self._daily(400, 0.0, 9)}
        kw = dict(only_symbols=("BTCUSDT",), max_hold=1, sma=50, require_momentum=False,
                  rebalance_weekday=-1, min_age_days=0)
        a, b = d["BTCUSDT"][100]["t"], d["BTCUSDT"][-1]["t"]
        r0 = run_momentum(d, a, b, MomParams(**kw))
        r1 = run_momentum(d, a, b, MomParams(signal_lag=1, **kw))
        self.assertNotEqual(r0["strategy"]["total_return_pct"], r1["strategy"]["total_return_pct"])

    def test_monday_rebalance(self):
        from mari_bot.momentum import run_momentum
        from datetime import datetime, timezone
        d = {"BTCUSDT": self._daily(300, 0.003, 1)}
        r = run_momentum(d, d["BTCUSDT"][100]["t"], d["BTCUSDT"][-1]["t"])
        t = r["last_picks"]["t"]
        self.assertEqual(datetime.fromtimestamp(t / 1000, timezone.utc).weekday(), 0)


class TestBtcTrendLive(unittest.TestCase):
    def test_boot_no_replay_and_switch(self):
        from mari_bot.btc_trend import BtcTrend
        from mari_bot.telegram import fmt_btc_event
        D_ = 86_400_000
        up = [{"t": i * D_, "o": 100 + i, "h": 101 + i, "l": 99 + i, "c": 100 + i, "v": 1, "qv": 1}
              for i in range(200)]
        with tempfile.TemporaryDirectory() as d:
            bt = BtcTrend(os.path.join(d, "b.json"))
            ev = bt.update(up)
            self.assertEqual(len(ev), 1)                      # فقط آخرین روز، نه بازپخش
            self.assertTrue(ev[0]["boot"])
            self.assertEqual(bt.s["position"], "BTC")
            crash = up + [{"t": 200 * D_, "o": 299, "h": 299, "l": 100, "c": 120, "v": 1, "qv": 1}]
            ev = BtcTrend(os.path.join(d, "b.json")).update(crash)
            self.assertEqual(ev[0]["to"], "CASH")
            self.assertIn(LOCK_LINE, fmt_btc_event(ev[0]))
            self.assertEqual(BtcTrend(os.path.join(d, "b.json")).update(crash), [])   # تکراری نه


class TestChannel(unittest.TestCase):
    def test_channel_posts_only_with_config_and_disclaimer(self):
        from mari_bot.telegram import CHANNEL_DISCLAIMER, Telegram, fmt_channel_event, fmt_channel_weekly
        ev = {"t": 0, "to": "CASH", "close": 70000.0, "sma": 72000.0, "boot": False, "equity": 990.0}
        summ = {"position": "CASH", "equity": 990.0, "return_pct": -1.0, "btc_hold_return_pct": -3.0,
                "close": 70000.0, "sma150": 72000.0, "switches": 2}
        for m in (fmt_channel_event(ev, summ, "u"), fmt_channel_weekly(summ, "u")):
            self.assertIn(CHANNEL_DISCLAIMER, m)
            self.assertIn(LOCK_LINE, m)
            self.assertNotRegex(m, "تضمین(ی)? (سود|می‌کنیم)")
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.dict(os.environ, {"MARI_TELEGRAM_TOKEN": "x", "MARI_TELEGRAM_CHAT_ID": "7",
                                             "MARI_TELEGRAM_CHANNEL_ID": ""}):
            tg = Telegram(os.path.join(d, "t.json"))
            with mock.patch.object(tg, "_call", return_value=({"ok": True}, 200)) as c:
                self.assertFalse(tg.post_channel("x"))
                c.assert_not_called()
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.dict(os.environ, {"MARI_TELEGRAM_TOKEN": "x", "MARI_TELEGRAM_CHAT_ID": "7",
                                             "MARI_TELEGRAM_CHANNEL_ID": "@mari_test"}):
            tg = Telegram(os.path.join(d, "t.json"))
            with mock.patch.object(tg, "_call", return_value=({"ok": True}, 200)) as c:
                self.assertTrue(tg.post_channel("x"))
                self.assertEqual(c.call_args[0][1]["chat_id"], "@mari_test")


class TestClassics(unittest.TestCase):
    def _d(self, n, drift, seed):
        D_ = 86_400_000
        bars = synth(n, drift, 0.02, seed=seed)
        for i, b in enumerate(bars):
            b["t"] = 1_600_000_000_000 // D_ * D_ + i * D_
        return bars

    def test_classics_run_and_dca(self):
        from mari_bot.classics import dca, run_classics
        d = {"BTCUSDT": self._d(700, 0.002, 1), "ETHUSDT": self._d(700, 0.001, 2)}
        a, b = d["BTCUSDT"][260]["t"], d["BTCUSDT"][-1]["t"]
        r = run_classics(d, a, b)
        for k in ("H-MARI-C-007", "H-MARI-C-008", "H-MARI-C-009"):
            self.assertIn(r[k]["verdict"], ("FALSIFIED", "SUPPORTED_IN_TEST_RANGE"))
            self.assertIn("sharpe", r[k])
        x = dca(d, a, b, weekly_usd=10)
        self.assertAlmostEqual(x["invested"], 10 * x["weeks"])
        self.assertGreater(x["final_value"], 0)

    def test_next_day_execution(self):
        from mari_bot.classics import run_weights
        d = {"BTCUSDT": self._d(30, 0.0, 3)}
        calls = []

        def fn(k, ctx):
            calls.append(k)
            return {"BTCUSDT": 1.0} if len(calls) == 1 else None
        st, curve, _ = run_weights(d, ["BTCUSDT"], d["BTCUSDT"][0]["t"], d["BTCUSDT"][-1]["t"], fn)
        self.assertEqual(curve[0], 1.0)          # روز اول هنوز اجرا نشده (اجرا فردا)
        self.assertEqual(st["trades"], 1)


class TestDailyAndHealth(unittest.TestCase):
    def test_daily_simple_and_dca(self):
        from mari_bot.telegram import fmt_daily_simple, fmt_dca
        bot = run_backtest({"BTCUSDT": synth(300)})["bot"]
        bot.btc_summary = {"position": "CASH", "equity": 990.0, "return_pct": -1.0, "btc_hold_return_pct": -3.0,
                           "close": 70000.0, "sma150": 72000.0, "switches": 2}
        m = fmt_daily_simple(bot, monday=True)
        self.assertIn("خرید پله‌ای", m)
        self.assertIn(LOCK_LINE, m)
        self.assertNotIn("خرید پله‌ای", fmt_daily_simple(bot, monday=False))
        self.assertIn("نقد", "\n".join(fmt_dca(bot.btc_summary)))

    def test_health_alert_after_three_failures(self):
        from mari_bot import live
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.dict(os.environ, {"MARI_TELEGRAM_TOKEN": "", "TELEGRAM_BOT_TOKEN": ""}):
            r = live.LiveRunner(d)
            sent = []
            with mock.patch.object(r.tg, "broadcast", side_effect=lambda t: sent.append(t) or 1):
                for _ in range(2):
                    r._health(False, "x")
                self.assertEqual(sent, [])
                r._health(False, "x")
                self.assertEqual(len(sent), 1)
                r._health(False, "x")
                self.assertEqual(len(sent), 1)           # تکرار نمی‌شود
                r._health(True, None)
                self.assertEqual(len(sent), 2)           # پیام بهبود


class TestMacro(unittest.TestCase):
    def test_parse_and_lag(self):
        from mari_bot.macro import Series, net_liquidity, parse_fred_csv
        rows = parse_fred_csv("observation_date,DGS10\n2020-01-01,1.5\n2020-01-02,.\n2020-01-03,1.7\n")
        self.assertEqual(len(rows), 2)
        s = Series(rows, lag_days=1)
        D_ = 86_400_000
        self.assertIsNone(s.at(rows[0][0]))                  # تأخیر: همان روز هنوز منتشر نشده
        self.assertEqual(s.at(rows[0][0] + D_), 1.5)
        self.assertEqual(s.at(rows[1][0] + D_), 1.7)
        liq = net_liquidity([(0, 8_000_000.0)], [(0, 500_000.0)], [(0, 1000.0)])
        self.assertEqual(liq[0][1], 8_000_000 - 500_000 - 1_000_000)

    def test_run_macro_shapes(self):
        from mari_bot.macro import run_macro
        D_ = 86_400_000
        bars = synth(700, 0.002, 0.02, seed=1)
        t0 = 1_600_000_000_000 // D_ * D_
        for i, b in enumerate(bars):
            b["t"] = t0 + i * D_
        rows = [(t0 + i * D_, 100 + (i % 50)) for i in range(700)]
        res = run_macro({"BTCUSDT": bars}, {"DGS10": rows, "DTWEXBGS": rows, "NETLIQ": rows[::7]},
                        bars[260]["t"], bars[-1]["t"])
        for k in ("H-MARI-X-011", "H-MARI-X-012", "H-MARI-X-013", "H-MARI-X-014"):
            self.assertIn(res[k]["verdict"], ("FALSIFIED", "SUPPORTED_IN_TEST_RANGE"))

    def test_fred_only_allowed_path(self):
        with self.assertRaises(D.DataError):
            D.http_get_text("/other", base=D.FRED)


class TestICT(unittest.TestCase):
    def test_events_and_run(self):
        from mari_bot.ict import events, run_ict
        b = [{"t": 0, "o": 10, "h": 11, "l": 9, "c": 10},
             {"t": 1, "o": 10, "h": 10.5, "l": 8.5, "c": 9.5},     # شکار کف
             {"t": 2, "o": 9.5, "h": 11.2, "l": 9.4, "c": 10.0}]   # شکار سقف
        ev = events(b)
        self.assertEqual(ev["bull"], [1])
        self.assertEqual(ev["bear"], [2])
        D_ = 86_400_000
        d = {}
        for sym, seed in (("BTCUSDT", 1), ("ETHUSDT", 2)):
            bars = synth(500, 0.001, 0.02, seed=seed)
            for i, x in enumerate(bars):
                x["t"] = 1_600_000_000_000 // D_ * D_ + i * D_
            d[sym] = bars
        r = run_ict(d, d["BTCUSDT"][30]["t"], d["BTCUSDT"][-1]["t"])
        self.assertIn(r["verdict"]["H-MARI-ICT-015"], ("FALSIFIED", "SUPPORTED_IN_TEST_RANGE"))
        self.assertGreater(r["events"]["BTCUSDT"]["bull"]["n"], 10)


class TestTurtleLive(unittest.TestCase):
    def test_turtle_entry_exit(self):
        from mari_bot.btc_trend import BtcTrend
        D_ = 86_400_000
        flat = [{"t": i * D_, "o": 100, "h": 101, "l": 99, "c": 100, "v": 1, "qv": 1} for i in range(70)]
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.json")
            bt = BtcTrend(p, mode="turtle")
            ev = bt.update(flat)
            self.assertEqual(ev[0]["to"], "CASH")              # شروع: بدون شکست → نقد
            up = flat + [{"t": 70 * D_, "o": 100, "h": 106, "l": 100, "c": 105, "v": 1, "qv": 1}]
            ev = BtcTrend(p, mode="turtle").update(up)
            self.assertEqual(ev[0]["to"], "BTC")               # شکست سقف ۵۵ روزه
            hold = up + [{"t": 71 * D_, "o": 105, "h": 105, "l": 100, "c": 100.5, "v": 1, "qv": 1}]
            self.assertEqual(BtcTrend(p, mode="turtle").update(hold), [])   # هنوز بالای کف ۲۰ روزه
            dn = hold + [{"t": 72 * D_, "o": 100, "h": 100, "l": 97, "c": 98, "v": 1, "qv": 1}]
            self.assertEqual(BtcTrend(p, mode="turtle").update(dn)[0]["to"], "CASH")


class TestLiveBoot(unittest.TestCase):
    def test_first_boot_does_not_replay_history(self):
        from mari_bot import live
        bars = {"BTCUSDT": synth(400, 0.002), "SOLUSDT": synth(400, 0.004, seed=5)}
        now = bars["BTCUSDT"][-1]["t"] + 2 * H
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(live, "fetch_universe", return_value=["SOLUSDT"]), \
                mock.patch.object(live, "fetch_quote_volumes", return_value={}), \
                mock.patch.object(live.SourcePicker, "klines", lambda self, s, *a: bars[s]), \
                mock.patch.object(live.time, "sleep"), \
                mock.patch.object(live.time, "time", return_value=now / 1000), \
                mock.patch.dict(os.environ, {"MARI_TELEGRAM_TOKEN": "", "TELEGRAM_BOT_TOKEN": ""}):
            r = live.LiveRunner(d)
            out = r.cycle()
            self.assertNotIn("subscribers", json.dumps(out))
            self.assertTrue(out["ok"])
            self.assertEqual(len(r.bot.equity_curve), 1)        # فقط آخرین کندل بسته پردازش شد
            self.assertEqual(r.bot.trades, [])
            self.assertTrue(os.path.exists(os.path.join(d, "state.json")))
            r2 = live.LiveRunner(d)                              # بازیابی وضعیت
            self.assertEqual(r2.bot.last_ts, r.bot.last_ts)


if __name__ == "__main__":
    unittest.main()
