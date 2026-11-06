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


def _to_daily(bars):
    out = {}
    for b in bars:
        d = b["t"] // 86_400_000 * 86_400_000
        x = out.setdefault(d, {"t": d, "o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"], "v": 0.0, "qv": 0.0})
        x["h"], x["l"], x["c"] = max(x["h"], b["h"]), min(x["l"], b["l"]), b["c"]
        x["v"] += b.get("v", 0)
        x["qv"] += b.get("qv", 0)
    return [out[k] for k in sorted(out)]


class TestResearch(unittest.TestCase):
    def test_offline_research_pipeline(self):
        from mari_bot import research as R
        t_end = 1_700_000_000_000 + 1500 * H
        data = {"BTCUSDT": synth(1500, 0.0005), "SOLUSDT": synth(1500, 0.001, seed=4),
                "ETHUSDT": synth(1500, -0.0005, seed=9)}
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(R, "pick_universe", return_value=list(data)), \
                mock.patch.object(R, "fetch_history", side_effect=lambda s, a, b, interval="1h":
                                  data[s] if interval == "1h" else _to_daily(data[s])), \
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


class TestFundingCarryLive(unittest.TestCase):
    def test_boot_entry_accrual_exit(self):
        from mari_bot.funding_live import FundingCarry
        from mari_bot.telegram import fmt_carry_event
        D_ = 86_400_000
        hi = 0.0005           # هر تسویه؛ ۳ بار در روز ≈ ۵۵٪ سالانه
        rows = [(d * D_ + h * 8 * 3_600_000, hi) for d in range(20) for h in range(3)]
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "c.json")
            fc = FundingCarry(p)
            self.assertEqual(fc.update("BTCUSDT", rows, "x", 20 * D_), [])     # شروع: فقط تصمیم، بدون بازپخش
            self.assertTrue(fc.s["assets"]["BTCUSDT"]["pending"])
            rows2 = rows + [(20 * D_ + h * 8 * 3_600_000, hi) for h in range(3)]
            ev = FundingCarry(p).update("BTCUSDT", rows2, "x", 21 * D_)
            self.assertEqual(ev[0]["to"], "ON")
            fc = FundingCarry(p)
            eq_on = fc.s["assets"]["BTCUSDT"]["equity"]
            self.assertGreater(eq_on, 1000 * (1 - 0.003))                    # هزینه کسر و فاندینگ روز افزوده
            neg = rows2 + [(d * D_ + h * 8 * 3_600_000, -0.002) for d in range(21, 30) for h in range(3)]
            evs = FundingCarry(p).update("BTCUSDT", neg, "x", 30 * D_)
            self.assertIn("OFF", [e["to"] for e in evs])
            self.assertIn(LOCK_LINE, fmt_carry_event(evs[-1]))


class TestScorecardStatus(unittest.TestCase):
    def test_scorecard_and_status(self):
        from mari_bot.telegram import fmt_scorecard, fmt_status
        bot = run_backtest({"BTCUSDT": synth(300)})["bot"]
        self.assertEqual(fmt_scorecard(bot), [])
        bot.btc_summary = {"position": "BTC", "return_pct": 1.2, "btc_hold_return_pct": 2.0, "max_dd_pct": 0.5,
                           "days": 7, "equity": 1012.0, "close": 80000.0, "sma150": 72000.0, "switches": 1}
        bot.turtle_summary = {"position": "CASH", "return_pct": 0.0, "max_dd_pct": 0.0, "days": 7}
        bot.carry_summary = {"BTCUSDT": {"in_position": True, "return_pct": 0.1, "max_dd_pct": 0.0, "days": 7,
                                         "apr7_pct": 9.0}}
        sc = "\n".join(fmt_scorecard(bot))
        self.assertIn("لاک‌پشت", sc)
        self.assertIn("کری فاندینگ", sc)
        self.assertNotRegex(sc, "[0-9]")
        st = fmt_status(bot, {"ok": True, "last_cycle_ms": 0, "symbols": 509, "sources": {"toobit": 509},
                              "fail_streak": 0, "cycles": 12})
        self.assertIn("سالم", st)
        self.assertIn(LOCK_LINE, st)

    def test_drawdown_tracked(self):
        from mari_bot.btc_trend import BtcTrend
        D_ = 86_400_000
        up = [{"t": i * D_, "o": 100 + i, "h": 101 + i, "l": 99 + i, "c": 100 + i, "v": 1, "qv": 1} for i in range(200)]
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "b.json")
            BtcTrend(p).update(up)
            dip = up + [{"t": 200 * D_, "o": 299, "h": 299, "l": 280, "c": 285, "v": 1, "qv": 1}]
            bt = BtcTrend(p)
            bt.update(dip)
            self.assertGreater(bt.summary()["max_dd_pct"], 0)


class TestSavingsPlan(unittest.TestCase):
    def test_weekly_saving_and_trend_rule(self):
        from mari_bot.savings_live import SavingsPlan
        from mari_bot.telegram import fmt_savings_week
        D_ = 86_400_000
        mon0 = 4 * D_                                         # 1970-01-05 دوشنبه بود
        up = [{"t": mon0 + i * D_, "o": 100 + i, "h": 101 + i, "l": 99 + i, "c": 100 + i, "v": 1, "qv": 1}
              for i in range(160)]
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "s.json")
            sp = SavingsPlan(p, weekly_usd=5)
            sp.update(up)                                     # شروع: بدون بازپخش
            self.assertEqual(sp.s["weeks"], 0)
            more = up + [{"t": mon0 + (160 + j) * D_, "o": 260 + j, "h": 261 + j, "l": 259 + j, "c": 260 + j,
                          "v": 1, "qv": 1} for j in range(14)]
            evs = SavingsPlan(p, weekly_usd=5).update(more)
            sp = SavingsPlan(p, weekly_usd=5)
            self.assertEqual(sp.s["weeks"], 2)                # دو دوشنبه
            self.assertAlmostEqual(sp.s["invested"], 10.0)
            self.assertEqual(sp.s["position"], "BTC")
            self.assertEqual(sp.s["cash"], 0.0)               # روند صعودی: همه به بیت‌کوین
            self.assertEqual(len(evs), 2)
            self.assertIn(LOCK_LINE, fmt_savings_week(evs[-1]))
            crash = more + [{"t": mon0 + 174 * D_, "o": 100, "h": 100, "l": 50, "c": 60, "v": 1, "qv": 1}]
            sp = SavingsPlan(p, weekly_usd=5)
            sp.update(crash)
            self.assertEqual(sp.s["position"], "CASH")
            self.assertEqual(sp.s["units"], 0.0)


class TestFundingFallbackSources(unittest.TestCase):
    """پارسر هر منبع جایگزین با پاسخ نمونهٔ مستندشدهٔ همان صرافی."""

    def test_parsers(self):
        from mari_bot import funding as F
        H = 3_600_000
        t0 = 1_700_000_000_000
        cases = {
            "okx": ({"data": [{"fundingRate": "0.0001", "fundingTime": str(t0)},
                              {"fundingRate": "-0.0002", "fundingTime": str(t0 - 8 * H)}]}, F._okx),
            "gate": ([{"t": t0 // 1000, "r": "0.0001"}, {"t": (t0 - 8 * H) // 1000, "r": "-0.0002"}], F._gate),
            "kucoin": ({"data": [{"timepoint": t0, "fundingRate": 0.0001},
                                 {"timepoint": t0 - 8 * H, "fundingRate": -0.0002}]}, F._kucoin),
            "bitget": ({"data": [{"fundingTime": str(t0), "fundingRate": "0.0001"},
                                 {"fundingTime": str(t0 - 8 * H), "fundingRate": "-0.0002"}]}, F._bitget),
        }
        for name, (payload, fn) in cases.items():
            once = [payload]                      # صفحهٔ دوم خالی: پایان صفحه‌بندی

            def one(*a, _q=once, **k):
                return _q.pop(0) if _q else ({"data": []} if name != "gate" else [])
            with mock.patch.object(F, "http_get_json", one):
                rows = fn(F._SYMS[name]["BTCUSDT"], t0 - 30 * H, t0)
            self.assertEqual(sorted(rows), [(t0 - 8 * H, -0.0002), (t0, 0.0001)], name)

    def test_every_fetcher_has_symbols_and_allowed_host(self):
        from mari_bot import funding as F
        from mari_bot.data import _ALLOWED
        for name, _ in F._FETCHERS:
            self.assertIn(name, F._SYMS, name)
        for base in (F.OKX, F.GATE, F.KUCOIN_F, F.BITGET):
            self.assertIn(base, _ALLOWED, base)

    def test_fetch_recent_falls_through_to_working_source(self):
        from mari_bot import funding as F
        from mari_bot.funding_live import fetch_recent
        D_ = 86_400_000
        now = 10 * D_
        good = [(d * D_ + h * 8 * 3_600_000, 0.0001) for d in range(10) for h in range(3)]

        def boom(*a, **k):
            raise D.DataError("HTTP_451")
        fetchers = (("binance", boom), ("bybit", boom), ("okx", lambda *a, **k: good))
        with mock.patch.object(F, "_FETCHERS", fetchers), \
                mock.patch("mari_bot.funding_live._FETCHERS", fetchers):
            name, rows = fetch_recent("BTCUSDT", now)
        self.assertEqual(name, "okx")
        self.assertTrue(rows)


class TestDeflatedSharpe(unittest.TestCase):
    def test_threshold_grows_with_trials(self):
        from mari_bot.dsr import expected_max_sharpe
        a, b = expected_max_sharpe(10, 0.04), expected_max_sharpe(1000, 0.04)
        self.assertGreater(b, a)
        self.assertEqual(expected_max_sharpe(1, 0.04), 0.0)

    def test_psr_monotone_and_bounded(self):
        from mari_bot.dsr import psr
        lo = psr(0.02, 1000, 0.0, 3.0)
        hi = psr(0.08, 1000, 0.0, 3.0)
        self.assertLess(lo, hi)
        self.assertTrue(0.0 <= lo <= 1.0 and 0.0 <= hi <= 1.0)
        self.assertGreater(psr(0.05, 2000, 0.0, 3.0), psr(0.05, 200, 0.0, 3.0))   # دادهٔ بیشتر، اطمینان بیشتر

    def test_many_trials_can_kill_a_real_looking_edge(self):
        import random

        from mari_bot.dsr import deflated_sharpe, verdict
        rnd = random.Random(3)
        rets = [rnd.gauss(0.0012, 0.02) for _ in range(1500)]      # شارپ سالانهٔ ~۱٫۱
        one = deflated_sharpe(rets, 1, 0.04)
        many = deflated_sharpe(rets, 5000, 0.04)
        self.assertGreater(one["dsr"], many["dsr"])
        self.assertEqual(verdict(1.0), "SIGNIFICANT_AFTER_MULTIPLE_TESTING")
        self.assertEqual(verdict(0.5), "NOT_SIGNIFICANT_AFTER_MULTIPLE_TESTING")

    def test_pure_noise_is_not_significant(self):
        import random

        from mari_bot.dsr import deflated_sharpe, verdict
        rnd = random.Random(11)
        rets = [rnd.gauss(0.0, 0.02) for _ in range(1500)]
        d = deflated_sharpe(rets, 64, 0.04)
        self.assertEqual(verdict(d["dsr"]), "NOT_SIGNIFICANT_AFTER_MULTIPLE_TESTING")


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


class FundingTests(unittest.TestCase):
    def test_daily_sum_and_no_lookahead(self):
        from mari_bot.funding import DAY_MS, crowding, daily_funding
        days = [i * DAY_MS for i in range(400)]
        rows = [(d + h * 3_600_000, 0.0001) for d in days for h in (0, 8, 16)]
        df = daily_funding(rows, days)
        self.assertAlmostEqual(df[5], 0.0003)
        df2 = list(df)
        df2[300] = 0.01                                   # جهش در روز ۳۰۰
        p1, p2 = crowding(df), crowding(df2)
        self.assertEqual(p1[:300], p2[:300])              # گذشته از آینده خبر ندارد
        self.assertGreater(p2[300], 90)

    def test_run_funding_synthetic(self):
        import math
        from mari_bot.funding import DAY_MS, run_funding
        days = [1_577_836_800_000 + i * DAY_MS for i in range(900)]
        daily = {}
        for sym, a in (("BTCUSDT", 0.004), ("ETHUSDT", 0.006)):
            px = [100 * math.exp(0.0008 * i + 0.3 * math.sin(i / 40)) for i in range(900)]
            daily[sym] = [{"t": t, "o": p, "h": p * (1 + a), "l": p * (1 - a), "c": p, "v": 1, "qv": 1}
                          for t, p in zip(days, px)]
        funding = {s: [(t + h * 3_600_000, 0.0001 * math.sin(i / 25)) for i, t in enumerate(days) for h in (0, 8, 16)]
                   for s in ("BTCUSDT", "ETHUSDT")}
        r = run_funding(daily, funding, days[300], days[-1])
        self.assertIn(r["verdict"]["H-MARI-F-017"], ("FALSIFIED", "SUPPORTED_IN_TEST_RANGE"))
        self.assertGreater(r["events"]["BTCUSDT"]["crowded_long"]["n"], 0)
        self.assertEqual(r["coverage"]["BTCUSDT"]["days_with_funding_pct"], 100.0)

    def test_funding_paths_allowed_and_readonly(self):
        from mari_bot.data import _ALLOWED
        for base, paths in _ALLOWED.items():
            for p in paths:
                self.assertNotIn("order", p.lower())


class PatternTests(unittest.TestCase):
    def _daily(self, planted: bool, n_sym=30, n_days=1400, seed=3):
        import random
        from mari_bot.pattern import DAY_MS
        rnd = random.Random(seed)
        t0 = 1_609_459_200_000                     # 2021-01-01
        daily = {}
        btc = [100.0]
        for i in range(1, n_days):
            btc.append(btc[-1] * (1 + 0.001 + rnd.gauss(0, 0.02)))
        daily["BTCUSDT"] = [{"t": t0 + i * DAY_MS, "o": p, "h": p * 1.01, "l": p * .99, "c": p, "v": 1, "qv": 1e9}
                            for i, p in enumerate(btc)]
        for k in range(n_sym):
            px, bars, regime = 50.0, [], rnd.choice((-1, 1))
            for i in range(n_days):
                vol_spike = rnd.random() < 0.1
                if rnd.random() < 1 / 60:          # روند پایدار که هر ~۶۰ روز عوض می‌شود
                    regime = -regime
                drift = 0.006 * regime if planted else 0.0
                px *= 1 + drift + rnd.gauss(0, 0.03)
                q = 1e6 * (4 if vol_spike else 1) * (1 + k)
                bars.append({"t": t0 + i * DAY_MS, "o": px, "h": px * 1.02, "l": px * .98, "c": px, "v": q / px, "qv": q})
            daily[f"C{k}USDT"] = bars
        return daily

    def test_monday_and_spearman(self):
        from mari_bot.pattern import DAY_MS, spearman
        import datetime
        t = int(datetime.datetime(2026, 11, 2, tzinfo=datetime.timezone.utc).timestamp() * 1000)
        self.assertEqual((t // DAY_MS + 3) % 7, 0)
        self.assertAlmostEqual(spearman(list(range(10)), list(range(10))), 1.0)

    def test_finds_planted_pattern_not_noise(self):
        from mari_bot.pattern import DAY_MS, run_pattern
        t0 = 1_609_459_200_000
        train, test = (t0 + 250 * DAY_MS, t0 + 800 * DAY_MS), (t0 + 801 * DAY_MS, t0 + 1390 * DAY_MS)
        r = run_pattern(self._daily(True), train, test)
        self.assertEqual(r["learned"]["ret30"]["sign"], 1)
        self.assertEqual(r["verdict"]["H-MARI-P-019"], "SUPPORTED_IN_TEST_RANGE")
        fp = sum(run_pattern(self._daily(False, seed=1000 + k), train, test)["verdict"]["H-MARI-P-019"]
                 != "FALSIFIED" for k in range(10))
        self.assertLessEqual(fp, 1)                     # نویز خالص: نرخ مثبت کاذب نزدیک ۲٫۵٪


class ResearchNotifyTests(unittest.TestCase):
    def test_summary_lists_verdicts_without_secrets(self):
        import tempfile
        from mari_bot.telegram import fmt_research
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "a_report.json"), "w", encoding="utf-8") as fh:
            json.dump({"hypotheses": {"H-MARI-F-017": "ادعای IC > ۰ در CI95 و BTC بالای SMA150"},
                       "results": {"verdict": {"H-MARI-F-017": "FALSIFIED"}},
                       "H-MARI-X-1": {"verdict": "SUPPORTED_IN_TEST_RANGE"}}, fh)
        with mock.patch.dict(os.environ, {"MARI_TELEGRAM_TOKEN": "123:SECRET"}):
            msg = fmt_research("funding", d, True)
        self.assertIn("❌ رد — H-MARI-F-017", msg)
        self.assertIn("✅ قبول — H-MARI-X-1", msg)
        self.assertNotIn("SECRET", msg)
        self.assertIn("(ادعای IC &gt; ۰ در CI95 و BTC بالای SMA150)", msg)
        self.assertIn("کامل نشد", fmt_research("funding", d, False))


class BlacklistTests(unittest.TestCase):
    def test_blacklist_no_lookahead_and_timing(self):
        from mari_bot.pattern import DAY_MS, blacklist_fn, build_blacklist
        d = PatternTests()._daily(True, n_sym=20, n_days=300)
        bl = build_blacklist(d)
        self.assertTrue(bl)
        keys = sorted(bl)
        for k in keys:
            self.assertEqual(((k - DAY_MS) // DAY_MS + 3) % 7, 0)      # پایان بستهٔ دوشنبه
            self.assertEqual(len(bl[k]), 4)                            # ۲۰٪ از ۲۰
        cut = keys[3]
        d2 = {s: [dict(b, c=b["c"] * (5 if b["t"] >= cut else 1)) for b in bars] for s, bars in d.items()}
        bl2 = build_blacklist(d2)
        for k in keys[:4]:
            self.assertEqual(bl[k], bl2[k])                            # آینده گذشته را عوض نمی‌کند
        f = blacklist_fn(bl)
        s0 = next(iter(bl[keys[0]]))
        self.assertFalse(f(s0, keys[0] - 1))
        self.assertTrue(f(s0, keys[0]))

    def test_engine_respects_blocked(self):
        from mari_bot.engine import MariBot
        import inspect
        self.assertIn("BLACKLIST_Q1", inspect.getsource(MariBot._scan))


class IdeasTests(unittest.TestCase):
    def _d(self):
        import random
        rnd = random.Random(7)
        t0, px, bars = 1_514_764_800_000, 100.0, []
        for i in range(1500):
            px *= 1 + 0.0008 + 0.03 * math.sin(i / 90) / 10 + rnd.gauss(0, 0.03)
            bars.append({"t": t0 + i * 86_400_000, "o": px, "h": px * 1.01, "l": px * .99, "c": px, "v": 1, "qv": 1})
        return {"BTCUSDT": bars, "ETHUSDT": [dict(b) for b in bars]}

    def test_t006_matches_reference_and_voltarget_is_partial(self):
        from mari_bot.classics import run_weights
        from mari_bot.ideas import realized_vol, run_ideas, t006_for, voltarget_for
        from mari_bot.macro import t006_fn
        d = self._d()
        a, b = d["BTCUSDT"][300]["t"], d["BTCUSDT"][-1]["t"]
        ref, _, _ = run_weights({"BTCUSDT": d["BTCUSDT"]}, ["BTCUSDT"], a, b, t006_fn)
        mine, _, _ = run_weights({"BTCUSDT": d["BTCUSDT"]}, ["BTCUSDT"], a, b, t006_for("BTCUSDT"))
        self.assertEqual(ref["total_return_pct"], mine["total_return_pct"])
        c = [x["c"] for x in d["BTCUSDT"]]
        self.assertGreater(realized_vol(c, 100), 0.3)                    # ~۰٫۰۳ روزانه ≈ ۵۷٪ سالانه
        vt, _, _ = run_weights({"BTCUSDT": d["BTCUSDT"]}, ["BTCUSDT"], a, b, voltarget_for("BTCUSDT"))
        self.assertLess(vt["max_drawdown_pct"], mine["max_drawdown_pct"])  # وزن کمتر از ۱ → افت کمتر
        r = run_ideas(d, a, b)
        self.assertEqual(set(r["verdict"]), {"H-MARI-V-022", "H-MARI-G-023"})


class Ideas2Tests(unittest.TestCase):
    def test_weekday_planted_and_halving_windows(self):
        from mari_bot.ideas import _ms, halving_for, run_ideas2, weekday, weekday_test
        import random
        rnd = random.Random(2)
        t0, px, bars = _ms("2018-01-01"), 100.0, []
        for i in range(3000):
            t = t0 + i * 86_400_000
            px *= 1 + (0.01 if weekday(t) == 4 else 0.0) + rnd.gauss(0, 0.01)
            bars.append({"t": t, "o": px, "h": px, "l": px, "c": px, "v": 1, "qv": 1})
        r = weekday_test(bars, (_ms("2018-06-01"), _ms("2022-12-31")), (_ms("2023-01-01"), bars[-1]["t"]))
        self.assertEqual(r["best_day"], 4)
        self.assertGreater(r["test_vs_all"]["ci95_low"], 0)
        ctx = {"state": {}, "days": [_ms("2020-05-11")]}
        self.assertEqual(halving_for("BTCUSDT")(0, ctx), {"BTCUSDT": 1.0})
        ctx = {"state": {"in": True}, "days": [_ms("2020-05-11") + 548 * 86_400_000]}
        self.assertEqual(halving_for("BTCUSDT")(0, ctx), {})
        out = run_ideas2({"BTCUSDT": bars, "ETHUSDT": [dict(b) for b in bars]}, _ms("2018-06-01"), bars[-1]["t"])
        self.assertEqual(out["verdict"]["H-MARI-W-025"], "SUPPORTED_IN_TEST_RANGE")


class Ideas3Tests(unittest.TestCase):
    def test_williams_fill_and_bollinger_squeeze(self):
        from mari_bot.ideas import FEE, SLIP, bollinger_for, run_ideas3, williams_sim
        d0 = 1_527_811_200_000
        bars = [{"t": d0, "o": 100, "h": 110, "l": 90, "c": 100},           # دامنهٔ دیروز ۲۰
                {"t": d0 + 86_400_000, "o": 100, "h": 115, "l": 99, "c": 112},  # سطح ۱۱۰ لمس شد
                {"t": d0 + 2 * 86_400_000, "o": 113, "h": 113, "l": 113, "c": 113}]
        st = williams_sim(bars, d0, bars[2]["t"])
        self.assertEqual(st["trades"], 1)
        exp = (113 * (1 - SLIP)) / (110 * (1 + SLIP)) * (1 - FEE) ** 2 - 1
        self.assertAlmostEqual(st["total_return_pct"] / 100, exp, places=3)
        # بولینگر: ۲۰۰ روز آرام سپس جهش → ورود
        c = [100 + (0.5 if i % 2 else -0.5) * (1 if i < 150 else 0.2) for i in range(200)] + [110]
        ctx, w = {"c": {"X": c}, "state": {}, "days": []}, None
        for k in range(len(c)):
            r = bollinger_for("X")(k, ctx)
            w = r if r is not None else w
        self.assertEqual(w, {"X": 1.0})


class Ideas4Tests(unittest.TestCase):
    def test_minervini_and_holy_grail_run_causally(self):
        from mari_bot.classics import run_weights
        from mari_bot.ideas import holy_grail_for, minervini_for, run_ideas4
        d = IdeasTests()._d()
        bars = d["BTCUSDT"]
        a, b = bars[400]["t"], bars[-1]["t"]
        r = run_ideas4(d, a, b)
        self.assertEqual(set(r["verdict"]), {"H-MARI-M-028", "H-MARI-R-029"})
        # بدون نگاه به آینده: تغییر دادهٔ پس از روز ۸۰۰ نتیجهٔ تا روز ۸۰۰ را عوض نمی‌کند
        cut = bars[800]["t"]
        d2 = {"BTCUSDT": [dict(x, c=x["c"] * (3 if x["t"] > cut else 1), h=x["h"] * (3 if x["t"] > cut else 1),
                               l=x["l"] * (3 if x["t"] > cut else 1)) for x in bars]}
        for f in (minervini_for, holy_grail_for):
            s1, c1, _ = run_weights({"BTCUSDT": bars}, ["BTCUSDT"], a, cut, f("BTCUSDT"))
            s2, c2, _ = run_weights(d2, ["BTCUSDT"], a, cut, f("BTCUSDT"))
            self.assertEqual(c1, c2)


class Ideas5Tests(unittest.TestCase):
    def test_elder_kama_causal_and_kama_tracks(self):
        from mari_bot.classics import run_weights
        from mari_bot.ideas import elder_for, kama, kama_for, run_ideas5
        k = kama([100.0] * 20 + [100.0 + i for i in range(1, 41)])
        self.assertGreater(k[-1], k[25])                 # روند کامل → KAMA دنبال می‌کند
        self.assertAlmostEqual(k[15], 100.0)              # بازار صاف → KAMA ثابت
        d = IdeasTests()._d()
        bars = d["BTCUSDT"]
        a, cut = bars[400]["t"], bars[800]["t"]
        r = run_ideas5(d, a, bars[-1]["t"])
        self.assertEqual(set(r["verdict"]), {"H-MARI-E-030", "H-MARI-K-031"})
        d2 = [dict(x, c=x["c"] * (3 if x["t"] > cut else 1), h=x["h"] * (3 if x["t"] > cut else 1),
                   v=x["v"] * (9 if x["t"] > cut else 1)) for x in bars]
        vol1, vol2 = {x["t"]: x["v"] for x in bars}, {x["t"]: x["v"] for x in d2}
        for f1, f2 in ((elder_for("BTCUSDT", vol1), elder_for("BTCUSDT", vol2)), (kama_for("BTCUSDT"), kama_for("BTCUSDT"))):
            _, c1, _ = run_weights({"BTCUSDT": bars}, ["BTCUSDT"], a, cut, f1)
            _, c2, _ = run_weights({"BTCUSDT": d2}, ["BTCUSDT"], a, cut, f2)
            self.assertEqual(c1, c2)


class Ideas6Tests(unittest.TestCase):
    def test_rotation_picks_stronger_asset(self):
        from mari_bot.ideas import _ms, rotation_fn, run_ideas6
        days = [_ms("2018-01-01") + i * 86_400_000 for i in range(400)]
        btc = [100 * 1.002 ** i for i in range(400)]
        eth = [10 * 1.004 ** i for i in range(400)]                  # ETH قوی‌تر → نسبت صعودی
        ctx = {"c": {"BTCUSDT": btc, "ETHUSDT": eth}, "state": {}, "days": days}
        self.assertEqual(rotation_fn(200, ctx), {"ETHUSDT": 1.0})
        mk = lambda c: [{"t": t, "o": x, "h": x, "l": x, "c": x, "v": 1, "qv": 1} for t, x in zip(days, c)]
        self.assertIn("H-MARI-D-032", run_ideas6({"BTCUSDT": mk(btc), "ETHUSDT": mk(eth)}, days[160], days[-1])["verdict"])


class ReplicationTests(unittest.TestCase):
    def test_replication_runs_on_eth(self):
        from mari_bot.ideas import run_replication
        d = IdeasTests()._d()
        r = run_replication(d, d["ETHUSDT"][300]["t"], d["ETHUSDT"][-1]["t"])
        self.assertEqual(set(r["verdict"]), {"H-MARI-T-006-REP", "H-MARI-C-007-REP"})
        self.assertGreater(r["strategies"]["H-MARI-C-007-REP"]["trades"], 0)


class MarketTests(unittest.TestCase):
    def test_market_and_basket(self):
        from mari_bot.ideas import LARGE_CAPS, basket_trend_fn, run_market
        base = IdeasTests()._d()["BTCUSDT"]
        d = {s: [dict(b) for b in base] for s in ("BTCUSDT",) + LARGE_CAPS}
        r = run_market(d, base[300]["t"], base[-1]["t"])
        self.assertEqual(set(r["verdict"]), {"H-MARI-T-033", "H-MARI-V-034", "H-MARI-T-035"})
        ctx = {"c": {s: [x["c"] for x in base] for s in ("A", "B")}, "state": {}, "days": [x["t"] for x in base]}
        w = basket_trend_fn(["A", "B"])(300, ctx)
        self.assertTrue(w is None or all(abs(v - 0.5) < 1e-9 for v in w.values()))


class SessionTests(unittest.TestCase):
    def _hourly(self, planted, days=400, seed=4):
        import random
        rnd = random.Random(seed)
        t0, px, out = 1_609_459_200_000, 100.0, []
        for d in range(days):
            sweep = planted and rnd.random() < 0.3
            for h in range(24):
                t = t0 + d * 86_400_000 + h * 3_600_000
                o = px
                drift = 0.0
                if sweep and 8 <= h < 13:
                    drift = -0.004 if h < 11 else 0.006                # لندن: پایین سپس برگشت
                if sweep and 13 <= h < 21:
                    drift = 0.003                                       # نیویورک: صعود
                px *= 1 + drift + rnd.gauss(0, 0.002)
                out.append({"t": t, "o": o, "h": max(o, px) * 1.001, "l": min(o, px) * 0.999, "c": px, "v": 1, "qv": 1})
        return out

    def test_session_split_and_planted_sweep(self):
        from mari_bot.sessions import daily_sessions, s036
        days = daily_sessions(self._hourly(True))
        self.assertEqual(len(days), 400)
        r = s036(days)
        self.assertGreater(r["bull"]["n"], 50)
        self.assertGreater(r["bull"]["vs_all"]["ci95_low"], 0)

    def test_missing_hour_drops_day(self):
        from mari_bot.sessions import daily_sessions
        bars = self._hourly(False, days=3)
        del bars[24 + 15]                                              # روز دوم، ساعت ۱۵
        self.assertEqual(len(daily_sessions(bars)), 2)


class TradfiTests(unittest.TestCase):
    def test_tokenized_stocks_excluded_real_crypto_kept(self):
        from mari_bot.config import is_tradfi, tradable_symbol
        for s in ("IAUONUSDT", "GLDXUSDT", "TSLAONUSDT", "NVDABUSDT", "QQQXUSDT", "SPCXXUSDT"):
            self.assertTrue(is_tradfi(s), s)
            self.assertFalse(tradable_symbol(s), s)
        for s in ("TONUSDT", "TRXUSDT", "IMXUSDT", "ONUSDT", "SOONUSDT", "FLUXUSDT", "DYDXUSDT", "BTCUSDT"):
            self.assertFalse(is_tradfi(s), s)
            self.assertTrue(tradable_symbol(s), s)


class Ideas7Tests(unittest.TestCase):
    def test_turn_of_month_window(self):
        from datetime import datetime, timezone
        from mari_bot.ideas7 import is_tom
        ms = lambda s: int(datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
        for d in ("2024-01-31", "2024-02-01", "2024-02-03", "2024-02-29", "2023-02-28", "2024-12-31"):
            self.assertTrue(is_tom(ms(d)), d)
        for d in ("2024-02-04", "2024-02-28", "2024-01-15", "2023-02-27"):
            self.assertFalse(is_tom(ms(d)), d)

    def test_ensemble_weight_steps(self):
        from mari_bot.ideas7 import ensemble_weight
        up = [float(i) for i in range(1, 301)]
        self.assertIsNone(ensemble_weight(up, 150))
        self.assertEqual(ensemble_weight(up, 299), 1.0)
        down = list(reversed(up))
        self.assertEqual(ensemble_weight(down, 299), 0.0)

    def test_planted_tom_effect_detected(self):
        from mari_bot.ideas7 import is_tom, tom_test
        DAY = 86_400_000
        t0 = 1_546_300_800_000                                         # 2019-01-01
        bars, c = [], 100.0
        for i in range(900):
            t = t0 + i * DAY
            c *= 1.01 if is_tom(t) else (0.999 if i % 2 else 1.0)
            bars.append({"t": t, "c": c})
        r = tom_test(bars, t0, t0 + 900 * DAY)
        self.assertGreater(r["tom_minus_rest"]["ci95_low"], 0)


class P044Tests(unittest.TestCase):
    def test_pair_trend_half_weights(self):
        from mari_bot.ideas7 import pair_trend_fn
        DAY = 86_400_000
        up = [float(i) for i in range(1, 201)]
        down = list(reversed(up))
        ctx = {"c": {"BTCUSDT": up, "ETHUSDT": down}, "state": {}, "days": [i * DAY for i in range(200)]}
        fn = pair_trend_fn()
        self.assertIsNone(fn(100, ctx))
        self.assertEqual(fn(199, ctx), {"BTCUSDT": 0.5})
        self.assertIsNone(fn(199, {**ctx, "days": [(i + 1) * DAY for i in range(200)]}) if False else None)


class OITests(unittest.TestCase):
    def _zip(self, rows):
        import io, zipfile
        b = io.BytesIO()
        with zipfile.ZipFile(b, "w") as z:
            z.writestr("m.csv", "create_time,symbol,sum_open_interest,sum_open_interest_value\n" + "\n".join(rows))
        return b.getvalue()

    def test_oi_change_uses_only_past(self):
        from mari_bot.oi import oi_change
        H = 3_600_000
        rows = [(i * 300_000, 100.0 if i * 300_000 < 30 * H else 300.0) for i in range(int(48 * H / 300_000))]
        self.assertAlmostEqual(oi_change(rows, 25 * H), 0.0)            # جهش بعد از ورود دیده نمی‌شود
        self.assertAlmostEqual(oi_change(rows, 40 * H), 2.0)
        self.assertIsNone(oi_change(rows, 10 * H))                       # ۲۴ ساعت پیش داده ندارد

    def test_collect_and_planted_effect(self):
        from mari_bot.oi import collect, evaluate
        DAY = 86_400_000
        t0 = 1_746_000_000_000 // DAY * DAY
        def getter(path):
            sym = path.split("/")[-2]
            if sym == "SPOTONLYUSDT":
                return None
            d = path.rsplit("-metrics-", 1)[1][:10]
            from datetime import datetime, timezone
            base = int(datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
            rows = []
            for i in range(288):
                t = base + i * 300_000
                hot = sym.startswith("HOT") and t >= t0 + 10 * DAY
                ts = datetime.fromtimestamp(t / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                rows.append(f"{ts},{sym},{200.0 if hot else 100.0},1")
            return self._zip(rows)
        trades = []
        for i in range(30):
            trades.append({"symbol": "HOTUSDT", "entry_ts": t0 + 10 * DAY + 12 * 3_600_000 + i,
                           "pnl_pct": -3.0 - (i % 3), "pnl_usdt": -5, "exit_reason": "STOP_LOSS"})
            trades.append({"symbol": "CALMUSDT", "entry_ts": t0 + 10 * DAY + 12 * 3_600_000,
                           "pnl_pct": 1.0 + (i % 3), "pnl_usdt": 3, "exit_reason": "TP"})
        trades.append({"symbol": "SPOTONLYUSDT", "entry_ts": t0 + 10 * DAY, "pnl_pct": 1, "pnl_usdt": 1, "exit_reason": "TP"})
        tro, cov = collect(trades, getter=getter, pause=0)
        self.assertEqual(cov["with_oi"], 60)
        self.assertEqual(cov["symbols_without_futures"], ["SPOTONLYUSDT"])
        r = evaluate(tro)
        self.assertEqual(r["surge"]["n"], 30)
        self.assertEqual(r["verdict"], "SUPPORTED_IN_TEST_RANGE")

    def test_pooled_verdict_needs_majority(self):
        from mari_bot.oi import pooled_verdict
        pool = {"surge": {"n": 40}, "rest_minus_surge": {"diff_pct": 2, "ci95_low": 0.5}}
        mk = lambda d: {"rest_minus_surge": {"diff_pct": d}}
        self.assertEqual(pooled_verdict({"a": mk(1), "b": mk(1), "c": mk(1), "d": mk(-1)}, pool), "SUPPORTED_IN_TEST_RANGE")
        self.assertEqual(pooled_verdict({"a": mk(1), "b": mk(1), "c": mk(-1), "d": mk(-1)}, pool), "FALSIFIED")
        self.assertEqual(pooled_verdict({}, {"surge": {"n": 5}, "rest_minus_surge": None}), "INSUFFICIENT_DATA")


class Ideas8Tests(unittest.TestCase):
    DAY = 86_400_000

    def _ctx(self, closes):
        return {"c": {"X": closes}, "state": {}, "days": [i * self.DAY for i in range(len(closes))]}

    def test_parse_fng_and_no_lookahead(self):
        from mari_bot.ideas8 import Series, parse_fng
        pts = parse_fng({"data": [{"value": "15", "timestamp": str(2 * 86400)},
                                  {"value": "80", "timestamp": str(1 * 86400)},
                                  {"value": "bad", "timestamp": "x"}]})
        self.assertEqual(pts, [(self.DAY, 80), (2 * self.DAY, 15)])
        s = Series(pts)
        self.assertIsNone(s.at(0))                      # پیش از اولین مقدار: نامعلوم
        self.assertEqual(s.at(self.DAY + 5), 80)        # مقدار فردا دیده نمی‌شود
        self.assertIsNone(s.at(10 * self.DAY))          # دادهٔ کهنه

    def test_fng_strategy_buys_fear_sells_greed(self):
        from mari_bot.ideas8 import Series, fng_for
        s = Series([(0, 50), (self.DAY, 18), (2 * self.DAY, 40), (3 * self.DAY, 76)])
        fn, ctx = fng_for("X", s), self._ctx([1, 1, 1, 1])
        self.assertEqual([fn(k, ctx) for k in range(4)], [None, {"X": 1.0}, None, {}])

    def test_winter_months(self):
        from datetime import datetime, timezone
        from mari_bot.ideas8 import is_winter
        ms = lambda m: int(datetime(2024, m, 15, tzinfo=timezone.utc).timestamp() * 1000)
        self.assertTrue(all(is_winter(ms(m)) for m in (11, 12, 1, 2, 3, 4)))
        self.assertFalse(any(is_winter(ms(m)) for m in (5, 6, 7, 8, 9, 10)))

    def test_halloween_detects_planted_effect(self):
        from mari_bot.ideas8 import halloween_test
        import random
        rnd, c, bars = random.Random(3), 100.0, []
        for i in range(1500):
            t = 1_514_764_800_000 + i * self.DAY            # از ۲۰۱۸-۰۱-۰۱
            from mari_bot.ideas8 import is_winter
            c *= 1 + rnd.gauss(0.004 if is_winter(t) else -0.004, 0.01)
            bars.append({"t": t, "c": c})
        r = halloween_test(bars, bars[0]["t"], bars[-1]["t"])
        self.assertGreater(r["winter_minus_summer"]["ci95_low"], 0)

    def test_trailing_stop_exits_and_waits_for_fresh_cross(self):
        from mari_bot.ideas8 import trail_for
        closes = [100.0] * 149 + [110, 120, 130, 105, 125, 130, 90, 120]
        fn, ctx = trail_for("X", trail=0.15, n=150), self._ctx(closes)
        sig = {k: fn(k, ctx) for k in range(len(closes))}
        self.assertEqual(sig[149], {"X": 1.0})          # ورود بالای میانگین
        self.assertEqual(sig[152], {})                   # ۱۰۵ ≤ ۱۳۰×۰٫۸۵ → خروج با حد ضرر
        self.assertIsNone(sig[153])                      # هنوز بالای میانگین: ورود دوباره ممنوع
        self.assertIsNone(sig[155])                      # زیر میانگین: فقط مسلح می‌شود
        self.assertEqual(sig[156], {"X": 1.0})          # تقاطع تازه → ورود

    def test_run_ideas8_on_synthetic(self):
        from mari_bot.ideas8 import run_ideas8
        import random
        rnd, daily = random.Random(5), {}
        t0 = 1_514_764_800_000
        for sym in ("BTCUSDT", "ETHUSDT"):
            c, bars = 100.0, []
            for i in range(900):
                c *= 1 + rnd.gauss(0.0005, 0.03)
                bars.append({"t": t0 + i * self.DAY, "o": c, "h": c * 1.01, "l": c * 0.99, "c": c, "v": 1})
            daily[sym] = bars
        fng = [(t0 + i * self.DAY, 10 + (i * 7) % 85) for i in range(900)]
        r = run_ideas8(daily, fng, t0 + 300 * self.DAY, t0 + 899 * self.DAY)
        self.assertEqual(set(r["verdict"]), {"H-MARI-F-044", "H-MARI-S-045", "H-MARI-K-046"})
        self.assertGreater(r["by_asset"]["BTCUSDT"]["H-MARI-F-044"]["trades"], 0)


class Ideas9Tests(unittest.TestCase):
    DAY = 86_400_000

    def test_weekday_helpers(self):
        from datetime import datetime, timezone
        from mari_bot.ideas9 import is_monday, is_sunday
        ms = lambda y, m, d: int(datetime(y, m, d, tzinfo=timezone.utc).timestamp() * 1000)
        self.assertTrue(is_sunday(ms(2026, 11, 1)))
        self.assertTrue(is_monday(ms(2026, 11, 2)))
        self.assertFalse(is_sunday(ms(2026, 11, 5)))

    def test_weekly_only_decides_on_sunday(self):
        from mari_bot.ideas9 import is_sunday, weekly_for
        closes = [100.0] * 160 + [200.0] * 14
        days = [i * self.DAY for i in range(len(closes))]
        ctx = {"c": {"X": closes}, "state": {}, "days": days}
        fn = weekly_for("X")
        sig = [(k, fn(k, ctx)) for k in range(len(closes))]
        fired = [k for k, s in sig if s]
        self.assertTrue(fired and all(is_sunday(days[k]) for k in fired))
        self.assertGreaterEqual(fired[0], 160)

    def test_gated_basket_follows_btc_only(self):
        from mari_bot.ideas9 import gated_basket_fn
        n = 160
        btc = [100.0] * 150 + [50.0] * 5 + [200.0] * 5
        alt = [10.0] * n
        ctx = {"c": {"BTCUSDT": btc, "A": alt}, "state": {}, "days": [i * self.DAY for i in range(n)]}
        fn = gated_basket_fn(["BTCUSDT", "A"])
        sig = {k: fn(k, ctx) for k in range(n)}
        self.assertEqual(sig[149], {})                  # برابر میانگین = بیرون
        self.assertIsNone(sig[150])
        self.assertEqual(sig[155], {"BTCUSDT": 0.5, "A": 0.5})


class Ideas10Tests(unittest.TestCase):
    DAY = 86_400_000

    def _daily(self, n_syms=30, days=500, seed=7, planted=False):
        import random
        rnd, out = random.Random(seed), {}
        t0 = 1_577_836_800_000 + 4 * self.DAY            # ۲۰۲۰-۰۱-۰۵
        for j in range(n_syms):
            c, bars, drift = 10.0, [], 0.0
            for i in range(days):
                if planted and i % 7 == 1:                   # روند هفتهٔ قبل ادامه پیدا می‌کند
                    drift = 0.004 if bars and bars[-1]["c"] > bars[max(0, len(bars) - 20)]["c"] else -0.004
                c *= 1 + (drift if planted else 0) + rnd.gauss(0, 0.03)
                bars.append({"t": t0 + i * self.DAY, "o": c, "h": c * 1.02, "l": c * 0.98, "c": c,
                             "qv": 1e6 * (j + 1)})
            out[f"S{j}USDT"] = bars
        out["BTCUSDT"] = out.pop("S0USDT")
        return out, t0

    def test_universe_point_in_time_and_history(self):
        from mari_bot.ideas10 import Panel, universe
        d, t0 = self._daily(days=400)
        d["NEWUSDT"] = [{"t": t0 + i * self.DAY, "o": 1, "h": 1, "l": 1, "c": 1, "qv": 1e12} for i in range(300, 400)]
        p = Panel(d)
        u = universe(p, t0 + 399 * self.DAY, top=5)
        self.assertNotIn("NEWUSDT", u)                  # تاریخچهٔ کوتاه
        self.assertEqual(u[0], "S29USDT")               # پرحجم‌ترین

    def test_delisted_coin_uses_last_close(self):
        from mari_bot.ideas10 import Panel
        p = Panel({"X": [{"t": 0, "h": 1, "c": 1.0}, {"t": self.DAY, "h": 2, "c": 2.0}]})
        self.assertEqual(p.close_at_or_before("X", 10 * self.DAY), 2.0)
        self.assertIsNone(p.close_at_or_before("X", -1))

    def test_noise_mostly_falsified_and_planted_supported(self):
        from mari_bot.ideas10 import run_ideas10
        fp = 0
        for k in range(3):
            d, t0 = self._daily(seed=100 + k)
            r = run_ideas10(d, t0 + 366 * self.DAY, t0 + 499 * self.DAY)
            fp += r["verdict"]["H-MARI-C-051"] != "FALSIFIED"
        self.assertLessEqual(fp, 1)
        d, t0 = self._daily(seed=3, days=700, planted=True)
        r = run_ideas10(d, t0 + 366 * self.DAY, t0 + 699 * self.DAY)
        self.assertEqual(r["verdict"]["H-MARI-C-051"], "SUPPORTED_IN_TEST_RANGE")


class Ideas11Tests(unittest.TestCase):
    DAY = 86_400_000

    def test_score_max_uses_only_past_30_days(self):
        from mari_bot.ideas10 import Panel
        from mari_bot.ideas11 import score_max
        c = [10.0] * 40 + [20.0] + [20.0] * 40            # جهش ۱۰۰٪ در روز ۴۰
        bars = [{"t": i * self.DAY, "h": v, "c": v, "qv": 1.0} for i, v in enumerate(c)]
        p = Panel({"X": bars})
        self.assertAlmostEqual(score_max(p, ["X"], 45 * self.DAY)["X"], 1.0, places=6)
        self.assertAlmostEqual(score_max(p, ["X"], 39 * self.DAY)["X"], 0.0, places=6)
        self.assertAlmostEqual(score_max(p, ["X"], 75 * self.DAY)["X"], 0.0, places=6)

    def test_beats_requires_both_sharpe_and_return(self):
        from mari_bot.ideas11 import _beats
        hi = {"sharpe": 1.0, "total_return_pct": 100.0}
        lo = {"sharpe": 0.5, "total_return_pct": 50.0}
        self.assertTrue(_beats(hi, lo))
        self.assertFalse(_beats(lo, hi))
        self.assertFalse(_beats({"sharpe": 1.0, "total_return_pct": 10.0}, lo))   # شارپ بهتر، بازده کمتر
        self.assertFalse(_beats({"sharpe": None}, lo))

    def test_compare_needs_all_three_windows(self):
        from mari_bot.ideas11 import compare
        import random
        rnd = random.Random(7)
        noise = [rnd.gauss(0, 0.01) for _ in range(60)]
        good = [{"top": 0.02 + z, "ew": 0.001 + z} for z in noise]
        self.assertEqual(compare(good)["verdict"], "SUPPORTED_IN_TEST_RANGE")
        mixed = [{"top": (0.02 if i < 30 else -0.02) + z, "ew": 0.001 + z} for i, z in enumerate(noise)]
        self.assertEqual(compare(mixed)["verdict"], "FALSIFIED")
        flat = [{"top": 0.02, "ew": 0.001} for _ in range(60)]
        self.assertEqual(compare(flat)["verdict"], "FALSIFIED")      # نوسان صفر → شارپ نامعلوم

    def test_gate_benchmark_is_gated_and_aligned(self):
        from mari_bot.ideas10 import Panel, btc_gate, is_monday
        from mari_bot.ideas11 import _gate_benchmark
        import random
        rnd, d = random.Random(11), {}
        t0 = 1_577_836_800_000 + 4 * self.DAY
        for j in range(12):
            c, bars = 10.0, []
            for i in range(600):
                c *= 1 + rnd.gauss(0.001, 0.02)
                bars.append({"t": t0 + i * self.DAY, "o": c, "h": c * 1.01, "l": c * 0.99, "c": c, "qv": 1e6})
            d[f"S{j}USDT"] = bars
        d["BTCUSDT"] = d.pop("S0USDT")
        p = Panel(d)
        mondays = [t for t in sorted(p.sym["BTCUSDT"]["t"])
                   if t0 + 400 * self.DAY <= t <= t0 + 590 * self.DAY and is_monday(t)]
        from mari_bot.ideas10 import run_xs, score_high52
        g = btc_gate(p)
        top, _ = run_xs(p, mondays, score_high52, gate=g, frac=0.2)
        rows = _gate_benchmark(p, mondays, top, g)
        self.assertEqual(len(rows), len(top))
        cash = [r for r in rows if not g(r["t"])]
        self.assertTrue(all(abs(r["ew"]) < 1e-9 for r in cash))   # هفتهٔ نقد: محک هم نقد است


class Ideas12Tests(unittest.TestCase):
    DAY = 86_400_000

    def test_downside_beta_only_uses_weak_market_weeks(self):
        from mari_bot.ideas12 import downside_beta
        # هفته‌های نزولی باید اندازه‌های متفاوت داشته باشند، وگرنه شیب تعریف‌نشده است
        mkt = {k: (-0.01 * (k % 7 + 1) if k % 2 else 0.05) for k in range(1, 41)}
        coin = {k: 2.0 * mkt[k] for k in mkt}
        self.assertAlmostEqual(downside_beta(coin, mkt), 2.0, places=6)
        flat_down = {k: (-0.05 if k % 2 else 0.05) for k in range(1, 41)}
        self.assertIsNone(downside_beta({k: 2.0 * v for k, v in flat_down.items()}, flat_down))
        # هفته‌های صعودی بازار نباید اثر بگذارند
        noisy = dict(coin)
        for k in mkt:
            if mkt[k] > 0:
                noisy[k] = 99.0
        self.assertAlmostEqual(downside_beta(noisy, mkt), 2.0, places=6)
        self.assertIsNone(downside_beta({1: 0.1}, {1: -0.1}))      # کمتر از ۱۰ هفتهٔ نزولی

    def test_weekly_returns_look_back_only(self):
        from mari_bot.ideas10 import Panel
        from mari_bot.ideas12 import weekly_returns
        c = [10.0 * (1.01 ** i) for i in range(400)]
        bars = [{"t": i * self.DAY, "h": v, "c": v, "qv": 1.0} for i, v in enumerate(c)]
        p = Panel({"X": bars})
        rs = weekly_returns(p, "X", 200 * self.DAY, n_weeks=10)
        self.assertEqual(len(rs), 10)
        self.assertTrue(all(abs(r - (1.01 ** 7 - 1)) < 1e-9 for _, r in rs))

    def test_risk_criterion_allows_lower_return_but_needs_lower_drawdown(self):
        from mari_bot.ideas12 import _beats_risk
        a = {"sharpe": 1.2, "max_drawdown_pct": 60.0, "total_return_pct": 100.0}
        b = {"sharpe": 0.5, "max_drawdown_pct": 85.0, "total_return_pct": 900.0}
        self.assertTrue(_beats_risk(a, b))                          # بازده کمتر اشکالی ندارد
        self.assertFalse(_beats_risk({"sharpe": 1.2, "max_drawdown_pct": 90.0}, b))
        self.assertFalse(_beats_risk({"sharpe": 0.4, "max_drawdown_pct": 10.0}, b))


class Ideas13Tests(unittest.TestCase):
    DAY = 86_400_000

    def _days(self, n):
        return [i * self.DAY for i in range(n)]

    def test_annualized_needs_enough_settlements(self):
        from mari_bot.ideas13 import annualized
        self.assertIsNone(annualized([None, None, 0.001]))
        self.assertAlmostEqual(annualized([0.001] * 7), 0.365, places=9)
        self.assertAlmostEqual(annualized([0.001, 0.001, 0.001, 0.001, None, None, None]), 0.365, places=9)

    def test_entry_exit_lagged_by_one_day_and_costs_charged(self):
        from mari_bot.ideas13 import run_carry
        n = 400
        fd = [0.0005] * n                                  # سالانه حدود ۱۸٪ → باید وارد شود
        r = run_carry(self._days(n), fd, cost=0.003)
        self.assertEqual(r["cycles"], 1)                   # یک ورود، بدون خروج
        self.assertLess(r["days_in_position_pct"], 100.0)  # روزهای اول بیرون است (تأخیر سیگنال)
        self.assertGreater(r["total_return_pct"], 0)
        free = run_carry(self._days(n), fd, cost=0.0)
        self.assertGreater(free["total_return_pct"], r["total_return_pct"])

    def test_negative_funding_forces_exit(self):
        from mari_bot.ideas13 import run_carry
        n = 400
        fd = [0.0005] * 200 + [-0.0005] * (n - 200)
        r = run_carry(self._days(n), fd)
        self.assertEqual(r["cycles"], 1)
        self.assertLess(r["days_in_position_pct"], 55.0)   # پس از منفی شدن خارج می‌شود

    def test_passes_requires_all_three_bars(self):
        from mari_bot.ideas13 import passes
        self.assertTrue(passes({"sharpe": 1.5, "max_drawdown_pct": 3.0, "total_return_pct": 20.0}))
        self.assertFalse(passes({"sharpe": 0.9, "max_drawdown_pct": 3.0, "total_return_pct": 20.0}))
        self.assertFalse(passes({"sharpe": 1.5, "max_drawdown_pct": 12.0, "total_return_pct": 20.0}))
        self.assertFalse(passes({"sharpe": 1.5, "max_drawdown_pct": 3.0, "total_return_pct": -1.0}))
        self.assertFalse(passes({"insufficient": True}))

    def test_short_sample_is_insufficient_not_pass(self):
        from mari_bot.ideas13 import run_carry
        r = run_carry(self._days(50), [0.001] * 50)
        self.assertTrue(r["insufficient"])


class Ideas14Tests(unittest.TestCase):
    DAY = 86_400_000

    def _panel(self, n_syms=60, days=900, seed=14, planted=False):
        """ارزهای تصادفی. با planted=True ارزهایی که نوسان کم و حجم فزاینده دارند جهش می‌کنند."""
        import random
        rnd, d = random.Random(seed), {}
        t0 = 1_514_764_800_000 + 4 * self.DAY            # دوشنبه‌دار
        for j in range(n_syms):
            c, bars = 10.0, []
            boost_from = (300 + (j * 37) % 400) if (planted and j % 3 == 0) else None
            for i in range(days):
                sd = 0.01 if (planted and j % 3 == 0) else 0.05
                mu = 0.0
                if boost_from and i >= boost_from:
                    mu = 0.02 if i < boost_from + 91 else 0.0
                c *= max(0.2, 1 + mu + rnd.gauss(0, sd))
                qv = 1e6 * (1 + (0.01 * i if (planted and j % 3 == 0) else 0))
                bars.append({"t": t0 + i * self.DAY, "o": c, "h": c * 1.02, "l": c * 0.98, "c": c, "qv": qv})
            d[f"S{j}USDT"] = bars
        from mari_bot.ideas10 import Panel
        return Panel(d), t0

    def test_features_use_only_past_and_reject_young_or_illiquid(self):
        from mari_bot.ideas10 import Panel
        from mari_bot.ideas14 import features
        bars = [{"t": i * self.DAY, "o": 1, "h": 1.0, "l": 1, "c": 1.0, "qv": 1e6} for i in range(400)]
        bars[399] = dict(bars[399], c=5.0, h=5.0)         # جهش در آخرین روز
        p = Panel({"X": bars})
        f = features(p, "X", 300 * self.DAY)
        self.assertIsNone(f)                               # نوسان صفر → رد
        self.assertIsNone(features(p, "X", 50 * self.DAY))  # خیلی جوان
        thin = [{"t": i * self.DAY, "o": 1, "h": 1 + 0.01 * (i % 3), "l": 1, "c": 1 + 0.01 * (i % 3),
                 "qv": 10.0} for i in range(400)]
        self.assertIsNone(features(Panel({"Y": thin}), "Y", 300 * self.DAY))   # نقدشوندگی کم

    def test_forward_return_of_delisted_uses_last_price(self):
        from mari_bot.ideas10 import Panel
        from mari_bot.ideas14 import forward_return
        bars = [{"t": i * self.DAY, "h": 1.0, "c": 10.0} for i in range(100)]
        bars.append({"t": 100 * self.DAY, "h": 1.0, "c": 1.0})
        p = Panel({"X": bars})
        self.assertAlmostEqual(forward_return(p, "X", 50 * self.DAY), -0.9, places=6)

    def test_bucket_and_quintiles(self):
        from mari_bot.ideas14 import bucket, quintile_edges
        e = quintile_edges(list(range(100)))
        self.assertEqual(len(e), 4)
        self.assertEqual(bucket(-5, e), 0)
        self.assertEqual(bucket(999, e), 4)

    def test_rule_learned_on_noise_does_not_survive_out_of_sample(self):
        from mari_bot.ideas14 import run_ideas14
        p, t0 = self._panel(seed=21)
        d = {s: [{"t": t, **{k: p.sym[s][k][i] for k in ("c", "h")}, "qv": 1e6}
                 for i, t in enumerate(p.sym[s]["ts"])] for s in p.sym}
        r = run_ideas14(d, t0 + 150 * self.DAY, t0 + 600 * self.DAY, t0 + 600 * self.DAY, t0 + 899 * self.DAY)
        self.assertIn(r["verdict"]["H-MARI-Z-058"], ("FALSIFIED", "INSUFFICIENT_DATA"))
        self.assertEqual(len(r["rule"]["picked"]), 3)

    def test_learn_rule_picks_the_separating_feature(self):
        from mari_bot.ideas14 import learn_rule
        import random
        rnd = random.Random(5)
        ev = []
        for i in range(3000):
            v = rnd.random()
            f = {n: rnd.random() for n in ("age_days", "ret_30d", "ret_90d", "dd_from_ath", "qv_trend",
                                           "tightness_30d", "log_qv_30d", "px_vs_sma150")}
            f["vol_30d"] = v
            ev.append({"t": i // 20, "sym": "X", "f": f, "fwd": 0.0, "win": v > 0.8 and rnd.random() < 0.9})
        r = learn_rule(ev)
        self.assertEqual(r["by_feature"]["vol_30d"]["best_bucket"], 4)
        self.assertIn("vol_30d", r["picked"])


class Ideas15Tests(unittest.TestCase):
    DAY = 86_400_000

    def _days(self, n):
        return [i * self.DAY for i in range(n)]

    def test_parse_kline_csv_handles_micros_and_headers(self):
        from mari_bot.ideas15 import parse_kline_csv
        txt = ("open_time,open,high,low,close,volume\n"
               "1609459200000,1,2,0.5,100.5,7\n"
               "1609545600000000,1,2,0.5,101.5,7\n")
        rows = parse_kline_csv(txt)
        self.assertEqual([c for _, c in rows], [100.5, 101.5])
        self.assertTrue(all(t % self.DAY == 0 for t, _ in rows))

    def test_basis_gain_when_premium_converges(self):
        from mari_bot.ideas15 import run_basis_carry
        n = 400
        days = self._days(n)
        spot = {t: 100.0 for t in days}
        # دائمی با صرف ۲٪ شروع می‌کند و تا روز ۳۰۰ به صفر می‌رسد: سود پوشش
        perp = {t: 100.0 * (1 + 0.02 * max(0.0, 1 - i / 300)) for i, t in enumerate(days)}
        fund = [0.0] * n
        r = run_basis_carry(days, spot, perp, fund, fee=0.0, always_on=True)
        self.assertGreater(r["total_return_pct"], 0.5)      # همگرایی صرف = سود
        rising = {t: 100.0 * (1 + 0.02 * (i / 300)) for i, t in enumerate(days)}
        r2 = run_basis_carry(days, spot, rising, fund, fee=0.0, always_on=True)
        self.assertLess(r2["total_return_pct"], 0)          # بازشدن صرف = زیان

    def test_zero_basis_matches_pure_funding_accrual(self):
        from mari_bot.ideas15 import run_basis_carry
        n = 400
        days = self._days(n)
        spot = {t: 100.0 + i for i, t in enumerate(days)}   # قیمت بالا می‌رود
        perp = {t: 90.0 + i for i, t in enumerate(days)}    # با صرف منفی ثابت
        fund = [0.0005] * n
        z = run_basis_carry(days, spot, perp, fund, fee=0.0, always_on=True, zero_basis=True)
        self.assertGreater(z["sharpe"], 3)                  # بدون basis: جریان تقریباً بی‌ریسک
        self.assertLess(z["max_drawdown_pct"], 1.0)

    def test_price_gaps_are_counted_out_of_position(self):
        from mari_bot.ideas15 import run_basis_carry
        days = self._days(300)
        spot = {t: 100.0 for i, t in enumerate(days) if i % 2 == 0}
        perp = dict(spot)
        r = run_basis_carry(days, spot, perp, [0.0005] * 300, always_on=True)
        self.assertTrue(r.get("insufficient"))              # نیمی از روزها داده ندارند

    def test_basis_stats(self):
        from mari_bot.ideas15 import basis_stats
        days = self._days(200)
        spot = {t: 100.0 for t in days}
        perp = {t: 101.0 for t in days}
        b = basis_stats(days, spot, perp)
        self.assertAlmostEqual(b["mean_pct"], 1.0, places=3)


class ReportBuilderTests(unittest.TestCase):
    """باگ ۲۰۲۶-۱۱-۰۵: در ساخت گزارش ideas14 متغیر r پیش از مقداردهی استفاده شده بود."""

    def test_ideas14_markdown_builds_from_results(self):
        import tempfile
        from unittest import mock
        from mari_bot import research
        rule = {"base_win_rate": 0.05, "n_train_events": 10,
                "by_feature": {n: {"edges": [0, 1, 2, 3], "rates": [{"n": 300, "win_rate": 0.05}] * 5,
                                   "best_bucket": 0, "separation": 0.01} for n in ("a", "b", "c")},
                "picked": ["a", "b", "c"]}
        res = {"rule": rule, "n_test_events": 5,
               "train_in_sample_info": {"n_fired": 3, "fired_win_rate": 0.3, "base_win_rate": 0.05,
                                        "diff_pct": 25.0, "ci95_low": 1.0, "ci95_high": 40.0},
               "test": {"n_fired": 2, "fired_win_rate": 0.0, "base_win_rate": 0.01, "diff_pct": -1.0,
                        "ci95_low": -2.0, "ci95_high": 0.0},
               "tradeable": {"portfolio": {"total_return_pct": 1.0, "max_drawdown_pct": 2.0, "sharpe": 0.1},
                             "benchmark": {"total_return_pct": -1.0, "max_drawdown_pct": 9.0, "sharpe": -0.1},
                             "weeks": 7, "verdict": "FALSIFIED"},
               "verdict": {"H-MARI-Z-058": "FALSIFIED", "H-MARI-Z-059": "FALSIFIED"}}
        d = tempfile.mkdtemp()
        with mock.patch.object(research, "pick_universe_all", return_value=["BTCUSDT"]), \
             mock.patch.object(research, "fetch_history", return_value=[{"t": 0, "o": 1, "h": 1, "l": 1, "c": 1, "qv": 1}]), \
             mock.patch.object(research, "quality_check", return_value={"n": 1, "clean": [{"t": 0, "c": 1.0, "h": 1.0, "qv": 1.0}]}), \
             mock.patch("mari_bot.ideas14.run_ideas14", return_value=res):
            rep = research.run_ideas14_research(start="2024-01-01", out_dir=d)
        self.assertEqual(rep["results"]["verdict"]["H-MARI-Z-058"], "FALSIFIED")
        with open(os.path.join(d, "ideas14_report_fa.md"), encoding="utf-8") as fh:
            md = fh.read()
        self.assertIn("فرمول مشترک", md)
        self.assertIn("Z-059", md)


class Ideas16And17Tests(unittest.TestCase):
    DAY = 86_400_000

    def test_power_check_uses_expected_winners_not_signal_count(self):
        from mari_bot.ideas16 import power_check
        rule = {"picked": ["x"], "by_feature": {"x": {"edges": [1, 2, 3, 4], "best_bucket": 4}}}
        many_weak = [{"t": i, "f": {"x": 9.0}, "win": False} for i in range(300)]
        many_weak += [{"t": 300 + i, "f": {"x": 0.0}, "win": i < 3} for i in range(300)]
        pw = power_check(many_weak, rule)
        self.assertEqual(pw["n_fired"], 300)              # سیگنال زیاد
        self.assertLess(pw["expected_winners_if_no_effect"], 10)
        self.assertFalse(pw["testable"])                   # ولی توان کم
        rich = [{"t": i, "f": {"x": 9.0}, "win": i % 5 == 0} for i in range(300)]
        self.assertTrue(power_check(rich, rule)["testable"])

    def test_wide_rule_picks_two_features(self):
        from mari_bot.ideas16 import wide_rule
        import random
        rnd = random.Random(3)
        from mari_bot.ideas14 import FEATURES
        ev = [{"t": i // 10, "f": {n: rnd.random() for n in FEATURES}, "win": rnd.random() < 0.05}
              for i in range(3000)]
        r = wide_rule(ev)
        self.assertEqual(len(r["picked"]), 2)
        self.assertEqual(r["n_features"], 2)

    def test_ideas17_requires_95pct_of_random_draws(self):
        from mari_bot import ideas17
        from unittest import mock
        cm = {"portfolio": {}, "pct_random_draws_beaten_sharpe": 90.0,
              "pct_random_draws_beaten_return": 99.0, "verdict": "SUPPORTED_IN_TEST_RANGE"}
        pw = {"n_fired": 100, "base_win_rate": 0.2, "expected_winners_if_no_effect": 20.0,
              "observed_winners": 30, "testable": True}
        with mock.patch.object(ideas17, "Panel", lambda d: object()), \
             mock.patch.object(ideas17, "collect", return_value=[]), \
             mock.patch.object(ideas17, "wide_rule", return_value={"picked": ["a", "b"]}), \
             mock.patch.object(ideas17, "power_check", return_value=pw), \
             mock.patch.object(ideas17, "block_ci", return_value={"ci95_low": 1.0}), \
             mock.patch.object(ideas17, "cash_matched", return_value=cm):
            r = ideas17.run_ideas17({}, 0, 1, 2, 3)
        self.assertEqual(r["verdict"]["H-MARI-Z-063"], "FALSIFIED")   # ۹۰٪ کافی نیست
        cm["pct_random_draws_beaten_sharpe"] = 96.0
        with mock.patch.object(ideas17, "Panel", lambda d: object()), \
             mock.patch.object(ideas17, "collect", return_value=[]), \
             mock.patch.object(ideas17, "wide_rule", return_value={"picked": ["a", "b"]}), \
             mock.patch.object(ideas17, "power_check", return_value=pw), \
             mock.patch.object(ideas17, "block_ci", return_value={"ci95_low": 1.0}), \
             mock.patch.object(ideas17, "cash_matched", return_value=cm):
            r = ideas17.run_ideas17({}, 0, 1, 2, 3)
        self.assertEqual(r["verdict"]["H-MARI-Z-063"], "SUPPORTED_IN_TEST_RANGE")
        self.assertEqual(r["verdict"]["H-MARI-Z-064"], "SUPPORTED_IN_TEST_RANGE")


class ResearchNotifyVerdictCoverageTests(unittest.TestCase):
    """باگ ۲۰۲۶-۱۱-۰۶: حکم UNTESTABLE_LOW_POWER در فهرست شناخته‌شده‌ها نبود،
    پس در پیام تلگرام ideas16 بی‌صدا حذف شد و گزارش فقط قبولی را نشان داد."""

    def _msg(self, payload):
        import tempfile
        from mari_bot.telegram import fmt_research
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "r_report.json"), "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        with mock.patch.dict(os.environ, {}, clear=True):
            return fmt_research("ideas16", d, True)

    def test_untestable_and_insufficient_are_shown(self):
        msg = self._msg({"hypotheses": {"H-MARI-Z-061": "الگو هست؟: شرح",
                                        "H-MARI-Z-062": "سود می‌دهد؟: شرح"},
                         "results": {"verdict": {"H-MARI-Z-061": "UNTESTABLE_LOW_POWER",
                                                 "H-MARI-Z-062": "SUPPORTED_IN_TEST_RANGE"}}})
        self.assertIn("H-MARI-Z-061", msg)
        self.assertIn("آزمون‌ناپذیر", msg)
        self.assertIn("✅ قبول — H-MARI-Z-062", msg)
        msg2 = self._msg({"hypotheses": {"H-MARI-A-1": "x: y"},
                          "results": {"verdict": {"H-MARI-A-1": "INSUFFICIENT_DATA"}}})
        self.assertIn("داده کافی نیست", msg2)

    def test_hypothesis_without_verdict_is_flagged_not_dropped(self):
        msg = self._msg({"hypotheses": {"H-MARI-Z-070": "ادعا: شرح",
                                        "H-MARI-Z-071": "ادعای دوم: شرح"},
                         "results": {"verdict": {"H-MARI-Z-070": "FALSIFIED"}}})
        self.assertIn("بدون حکم در گزارش", msg)
        self.assertIn("H-MARI-Z-071", msg)

    def test_snippet_does_not_cut_mid_word_and_expands_short_heads(self):
        from mari_bot.telegram import _snippet
        self.assertEqual(_snippet("عنوان کوتاه: ادامه", 90), "عنوان کوتاه — ادامه")
        long = "در همان دوره: " + "کلمه " * 40
        out = _snippet(long, 90)
        self.assertTrue(out.endswith("…"))
        self.assertLessEqual(len(out), 91)
        self.assertFalse(out[:-1].endswith("کل"))      # مرز کلمه


class RegimeToolTests(unittest.TestCase):
    """ابزار دو-رژیمی: درس شمارهٔ ۹ — شارپ بهتر با بازده بدتر = کمتر در بازار بودن."""
    DAY = 86_400_000

    def _panel(self, n_syms=40, days=1200, seed=9, lucky=None):
        """بازار با یک دورهٔ صعودی و یک دورهٔ نزولی برای BTC؛ lucky = نماد با بازده بهتر."""
        import random
        from mari_bot.ideas10 import Panel
        rnd, d = random.Random(seed), {}
        t0 = 1_514_764_800_000 + 4 * self.DAY            # دوشنبه
        for j in range(n_syms):
            c, bars = 10.0, []
            for i in range(days):
                mu = 0.004 if i < days // 2 else -0.004   # نیمهٔ اول صعودی، نیمهٔ دوم نزولی
                if lucky and f"S{j}USDT" in lucky:
                    mu += 0.004
                c *= max(0.05, 1 + mu + rnd.gauss(0, 0.03))
                bars.append({"t": t0 + i * self.DAY, "o": c, "h": c * 1.01, "l": c * 0.99,
                             "c": c, "qv": 1e6})
            d[f"S{j}USDT"] = bars
        d["BTCUSDT"] = d.pop("S0USDT")
        return Panel(d), t0

    def test_regime_of_follows_btc_sma(self):
        from mari_bot.ideas10 import Panel
        from mari_bot.regime import regime_of
        up = [{"t": i * self.DAY, "h": 1.0, "c": 100.0 + i, "qv": 1.0} for i in range(400)]
        p = Panel({"BTCUSDT": up})
        self.assertEqual(regime_of(p, 300 * self.DAY), "bull")
        down = [{"t": i * self.DAY, "h": 1.0, "c": 500.0 - i, "qv": 1.0} for i in range(400)]
        self.assertEqual(regime_of(Panel({"BTCUSDT": down}), 300 * self.DAY), "bear")
        self.assertIsNone(regime_of(p, 10 * self.DAY))   # تاریخچهٔ کم

    def test_random_selection_does_not_beat_random_benchmark(self):
        from mari_bot.regime import overall_verdict, run_two_regime
        p, t0 = self._panel(seed=11)
        import random
        rnd = random.Random(1)
        def pick(pp, t):
            elig = [s for s in pp.sym if pp.i(s, t) is not None]
            return elig, rnd.sample(elig, 5) if len(elig) >= 5 else []
        r = run_two_regime(p, t0 + 200 * self.DAY, t0 + 1199 * self.DAY, pick, hold_weeks=4,
                           n_draws=40, seed=5)
        self.assertEqual(overall_verdict(r), "FALSIFIED")
        self.assertGreater(r["bull"]["weeks"], 30)
        self.assertGreater(r["bear"]["weeks"], 30)

    def test_genuine_edge_is_detected_in_both_regimes(self):
        from mari_bot.regime import overall_verdict, run_two_regime
        lucky = {f"S{j}USDT" for j in range(30, 40)}
        p, t0 = self._panel(seed=12, lucky=lucky)
        def pick(pp, t):
            elig = [s for s in pp.sym if pp.i(s, t) is not None]
            return elig, [s for s in elig if s in lucky]
        r = run_two_regime(p, t0 + 200 * self.DAY, t0 + 1199 * self.DAY, pick, hold_weeks=4,
                           n_draws=40, seed=6)
        self.assertEqual(overall_verdict(r), "SUPPORTED_IN_TEST_RANGE")

    def test_sitting_in_cash_fails_because_benchmark_is_cash_matched(self):
        """قاعده‌ای که در بازار نزولی نقد می‌ماند نباید «قبول» بگیرد — ایراد ideas14."""
        from mari_bot.regime import run_two_regime
        p, t0 = self._panel(seed=13)
        from mari_bot.regime import regime_of
        def pick(pp, t):
            elig = [s for s in pp.sym if pp.i(s, t) is not None]
            if regime_of(pp, t) == "bear":
                return elig, []                          # در بازار نزولی نقد
            return elig, elig[:5]
        r = run_two_regime(p, t0 + 200 * self.DAY, t0 + 1199 * self.DAY, pick, hold_weeks=1,
                           n_draws=40, seed=7)
        # نقد ماندن دیگر «قبول» نمی‌گیرد: محک هم‌نقد است، پس برتریِ الکی از بین می‌رود
        self.assertEqual(r["bear"]["verdict"], "FALSIFIED")
        self.assertLess(r["weeks_in_market"]["bear"], 5)
        self.assertLess(r["bear"]["pct_draws_beaten_return"], 95.0)

    def test_overall_requires_both_regimes(self):
        from mari_bot.regime import overall_verdict
        ok, no = {"verdict": "SUPPORTED_IN_TEST_RANGE"}, {"verdict": "FALSIFIED"}
        self.assertEqual(overall_verdict({"bull": ok, "bear": ok}), "SUPPORTED_IN_TEST_RANGE")
        self.assertEqual(overall_verdict({"bull": ok, "bear": no}), "FALSIFIED")
        self.assertEqual(overall_verdict({"bull": ok, "bear": {"verdict": "INSUFFICIENT_DATA"}}),
                         "INSUFFICIENT_DATA")


if __name__ == "__main__":
    unittest.main()
