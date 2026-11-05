# -*- coding: utf-8 -*-
"""موتور تصمیم ربات ماری — ENGINE B (شکارچی روند) + Risk Gate + Profit Runner + دفتر شواهد.

جریان هر کندل (Discover → Rank → Filter، سند مادر ۳۳.۵):
  ۱. اجرای سفارش‌های تمرینی در صف در قیمت باز کندل جدید (تصمیم روی کندل بسته، اجرا در کندل بعد).
  ۲. مدیریت موقعیت‌های باز با وضعیت روند همان کندل.
  ۳. کشف سیگنال در همهٔ نمادها، رتبه‌بندی با امتیاز روند، عبور از دروازهٔ ریسک.
همه‌چیز روی کاغذ است؛ هیچ سفارش واقعی‌ای وجود ندارد.
"""
from __future__ import annotations

from .config import BotConfig, assert_locks
from .data import bars_sha
from .ledger import Ledger
from .position import Fill, Position, close_summary, manage
from .risk import RiskGate, RiskState
from .trend import BULLISH, SymbolSeries, TrendResult, classify


class MariBot:
    def __init__(self, cfg: BotConfig, ledger: Ledger, state: dict | None = None):
        assert_locks()
        self.cfg, self.ledger = cfg, ledger
        st = state or {}
        self.gate = RiskGate(cfg.risk, RiskState(**st["risk"]) if st.get("risk") else None)
        self.positions: dict[str, Position] = {k: Position.from_dict(v) for k, v in st.get("positions", {}).items()}
        self.pending: dict[str, dict] = st.get("pending", {})
        self.trades: list[dict] = st.get("trades", [])
        self.equity_curve: list[tuple] = [tuple(x) for x in st.get("equity_curve", [])]
        self.last_ts: int = st.get("last_ts", 0)
        self.last_px: dict[str, float] = st.get("last_px", {})
        self.pos_state: dict[str, str] = st.get("pos_state", {})
        self.snapshot: dict[str, dict] = {}      # آخرین وضعیت روند هر نماد (برای /hunt و گزارش)
        self.btc_state: str | None = st.get("btc_state")
        self.new_events: list[dict] = []          # رویدادهای همین چرخه برای اطلاع‌رسانی تلگرام
        self.blocked = None                       # اختیاری (فقط پژوهش): تابع (sym, ts) → فهرست ممنوعه
        self.btc_summary: dict | None = None      # وضعیت استراتژی تمرینی روند بیت‌کوین (T-006)
        self.turtle_summary: dict | None = None   # وضعیت روش لاک‌پشت‌ها (C-007)
        self.carry_summary: dict | None = None    # کری فاندینگ تمرینی (Y-057)

    # ------------------------------------------------------------------ وضعیت
    def equity(self) -> float:
        return self.gate.s.cash + sum(p.qty * self.last_px.get(s, p.entry_px) for s, p in self.positions.items())

    def to_state(self) -> dict:
        return {
            "risk": self.gate.s.to_dict(),
            "positions": {k: v.to_dict() for k, v in self.positions.items()},
            "pending": self.pending, "trades": self.trades[-500:],
            "equity_curve": self.equity_curve[-2000:], "last_ts": self.last_ts,
            "last_px": self.last_px, "pos_state": self.pos_state, "btc_state": self.btc_state,
            "config_sha": self.cfg.sha(),
        }

    def _emit(self, kind: str, **data) -> None:
        rec = self.ledger.write(kind, **data)
        self.new_events.append(rec)

    # ------------------------------------------------------------------ پردازش
    def process(self, series: dict[str, SymbolSeries], quality: dict[str, dict] | None = None,
                until_ts: int | None = None) -> None:
        """همهٔ کندل‌های بستهٔ جدیدتر از last_ts را به ترتیب زمان پردازش می‌کند."""
        quality = quality or {}
        idx = {sym: {b["t"]: i for i, b in enumerate(s.bars)} for sym, s in series.items()}
        timeline = sorted({t for m in idx.values() for t in m if t > self.last_ts and (until_ts is None or t <= until_ts)})
        bench = self.cfg.benchmark
        for ts in timeline:
            btc: TrendResult | None = None
            if bench in series and ts in idx[bench]:
                btc = classify(series[bench], idx[bench][ts])
                self.btc_state = btc.state
            for sym, s in series.items():
                i = idx[sym].get(ts)
                if i is not None:
                    self.last_px[sym] = s.close[i]
            self._execute_pending(series, idx, ts)
            self._manage_open(series, idx, ts)
            eq = self.equity()
            self.gate.on_bar(ts, eq)
            self.equity_curve.append((ts, round(eq, 4)))
            self._scan(series, idx, ts, quality)
            self.last_ts = ts

    def _execute_pending(self, series, idx, ts):
        c = self.cfg.cost
        for sym in list(self.pending):
            i = idx.get(sym, {}).get(ts)
            if i is None:
                continue
            order = self.pending.pop(sym)
            bar = series[sym].bars[i]
            px = bar["o"] * (1 + c.slippage)
            stop = px - order["stop_dist"]
            eq = self.equity()
            qty = self.gate.size(px, stop, eq, c.fee_side)
            if qty <= 0 or stop <= 0:
                self._emit("REJECT", ts=ts, symbol=sym, reasons=["SIZE_ZERO_OR_INVALID_STOP"])
                continue
            fee = qty * px * c.fee_side
            self.gate.s.cash -= qty * px + fee
            pos = Position(sym, ts, px, qty, stop, px - stop, order["state"], order["reason"])
            pos.fills.append(Fill(ts, "BUY", qty, px, fee, "ENTRY", 0))
            self.positions[sym] = pos
            self.pos_state[sym] = order["state"]
            self._emit("ENTRY", ts=ts, symbol=sym, price=round(px, 8), qty=qty, stop=round(stop, 8),
                       notional=round(qty * px, 2), risk_usdt=round(qty * (px - stop), 2),
                       equity=round(eq, 2), trend=order["trend"], why=order["why"],
                       data_sha=order.get("data_sha"))

    def _manage_open(self, series, idx, ts):
        for sym in list(self.positions):
            i = idx.get(sym, {}).get(ts)
            if i is None:
                continue
            s, pos = series[sym], self.positions[sym]
            tr = classify(s, i, self.btc_state)
            prev_state = self.pos_state.get(sym)
            if tr.state != prev_state:
                self._emit("TREND_CHANGE", ts=ts, symbol=sym, frm=prev_state, to=tr.state, score=round(tr.score, 2))
                self.pos_state[sym] = tr.state
            fills = manage(pos, s.bars[i], tr.state, s.atr[i], self.cfg.exit, self.cfg.cost)
            for f in fills:
                self.gate.s.cash += f.qty * f.price - f.fee
                kind = "EXIT" if pos.qty <= 1e-12 else "PARTIAL"
                self._emit(kind, ts=ts, symbol=sym, price=round(f.price, 8), qty=f.qty, reason=f.reason,
                           stage=f.stage, trend=tr.state, mfe_pct=round(pos.mfe_pct(), 3),
                           giveback_pct=round(pos.giveback_pct(s.close[i]), 3),
                           why=self._exit_why(f.reason, tr))
            if pos.qty <= 1e-12:
                summ = close_summary(pos)
                self.trades.append(summ)
                del self.positions[sym]
                self.pos_state.pop(sym, None)
                fused = self.gate.on_close(sym, ts, summ["pnl_usdt"])
                self._emit("CLOSED", ts=ts, **summ)
                if fused:
                    self._emit("LOSS_FUSE", ts=ts, until_ts=self.gate.s.fuse_until_ts,
                               why=f"{self.cfg.risk.loss_fuse_n} ضرر پیاپی — توقف ورود جدید به‌مدت {self.cfg.risk.loss_fuse_bars} ساعت")

    @staticmethod
    def _exit_why(reason: str, tr: TrendResult) -> str:
        return {
            "STOP_LOSS": "حد ضرر اولیه خورد — فرضیهٔ خرید باطل شد",
            "TRAIL_STOP": "حد ضرر متحرک خورد — سود قفل‌شده محافظت شد",
            "EMERGENCY_CRASH": "شرایط سقوط/ریسک شدید — حفاظت از سرمایه در اولویت",
            "INVALIDATION_STRONG_BEARISH": "روند نزولی قوی تأیید شد — فرضیه باطل",
            "RISK_REDUCTION_WEAKNESS": "ضعف روند تأیید شد — کاهش بخشی از ریسک",
            "RISK_REDUCTION_BEARISH": "ساختار نزولی تأیید شد — کاهش بیشتر موقعیت",
            "PROFIT_SCALING": "برداشت بخشی از سود؛ بخش اصلی برای ادامهٔ روند نگه داشته شد",
            "TIME_NO_FOLLOW_THROUGH": "پس از ۷۲ ساعت حرکتی نداشت — سرمایه آزاد شد",
            "DUST_CLOSE": "باقی‌ماندهٔ ناچیز بسته شد",
        }.get(reason, reason) + f" (روند: {tr.state})"

    def _scan(self, series, idx, ts, quality):
        e = self.cfg.entry
        cands = []
        open_syms = set(self.positions) | set(self.pending)
        for sym, s in series.items():
            i = idx[sym].get(ts)
            if i is None:
                continue
            tr = classify(s, i, self.btc_state) if sym not in self.positions else None
            if tr is None:
                continue
            vr = s.vol_ratio(i)
            prior_high = max(b["h"] for b in s.bars[max(0, i - e.breakout_n): i]) if i >= e.breakout_n else float("inf")
            breakout = s.close[i] > prior_high
            signal = (tr.state in BULLISH and breakout and vr == vr and vr >= e.vol_ratio_min
                      and s.rsi[i] <= e.rsi_max)
            self.snapshot[sym] = {"ts": ts, "state": tr.state, "score": round(tr.score, 2), "close": s.close[i],
                                  "signal": bool(signal), "vol_ratio": round(vr, 2) if vr == vr else None,
                                  "rsi": round(s.rsi[i], 1) if s.rsi[i] == s.rsi[i] else None}
            if not signal:
                continue
            if self.blocked is not None and self.blocked(sym, ts):
                self._emit("REJECT", ts=ts, symbol=sym, trend=tr.state, reasons=["BLACKLIST_Q1"])
                continue
            q = quality.get(sym, {"ok": True, "issues": []})
            reasons = self.gate.check_entry(sym, ts, open_symbols=open_syms, btc_state=self.btc_state,
                                            data_ok=q.get("ok", True), median_qv=s.median_qv(i))
            if reasons:
                if "EXCLUDED_STABLE_OR_LEVERAGED" not in reasons:
                    self._emit("REJECT", ts=ts, symbol=sym, trend=tr.state, score=round(tr.score, 2), reasons=reasons)
                continue
            cands.append((tr.score, vr, sym, tr, i))
        cands.sort(key=lambda x: (x[0], x[1]), reverse=True)
        slots = self.cfg.risk.max_positions - len(open_syms)
        for score, vr, sym, tr, i in cands[: max(0, slots)]:
            s = series[sym]
            self.pending[sym] = {
                "signal_ts": ts, "state": tr.state, "reason": tr.reason,
                "stop_dist": e.init_stop_atr * s.atr[i], "trend": tr.to_dict(),
                "why": (f"روند {tr.state} با امتیاز {score:.1f}، شکست سقف {e.breakout_n} کندل، "
                        f"حجم {vr:.2f} برابر میانگین، RSI={s.rsi[i]:.0f}، BTC={self.btc_state}"),
                "data_sha": bars_sha(s.bars[max(0, i - 200): i + 1]),
            }
            self._emit("SIGNAL", ts=ts, symbol=sym, trend=tr.state, score=round(score, 2),
                       close=s.close[i], note="اجرا در قیمت باز کندل بعد")
        for _, _, sym, tr, _ in cands[max(0, slots):]:
            self._emit("REJECT", ts=ts, symbol=sym, trend=tr.state, reasons=["RANKED_OUT_NO_SLOT"])
