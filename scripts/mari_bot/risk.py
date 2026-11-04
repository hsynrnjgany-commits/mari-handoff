# -*- coding: utf-8 -*-
"""دروازهٔ مرکزی ریسک و سرمایه (CORE-DOCTRINE بخش ۹) — «هیچ فرصت جذابی اجازهٔ عبور از محدودیت‌های ریسک را ندارد»."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .config import RiskParams, tradable_symbol

DAY_MS = 86_400_000
HOUR_MS = 3_600_000


@dataclass
class RiskState:
    cash: float
    last_close_ts: dict = field(default_factory=dict)
    consec_losses: int = 0
    fuse_until_ts: int = 0
    day: int = -1
    day_start_equity: float = 0.0
    day_halted: bool = False
    fuse_events: int = 0

    def to_dict(self):
        return asdict(self)


class RiskGate:
    def __init__(self, p: RiskParams, state: RiskState | None = None):
        self.p = p
        self.s = state or RiskState(cash=p.start_equity)

    # ---- چرخهٔ روزانه ----
    def on_bar(self, ts: int, equity: float) -> None:
        d = ts // DAY_MS
        if d != self.s.day:
            self.s.day, self.s.day_start_equity, self.s.day_halted = d, equity, False
        elif self.s.day_start_equity > 0 and equity <= self.s.day_start_equity * (1 - self.p.daily_dd_halt):
            self.s.day_halted = True

    def on_close(self, symbol: str, ts: int, pnl: float) -> bool:
        """ثبت بستن معامله. خروجی True یعنی فیوز ضرر پیاپی همین الان فعال شد."""
        self.s.last_close_ts[symbol] = ts
        if pnl < 0:
            self.s.consec_losses += 1
            if self.s.consec_losses >= self.p.loss_fuse_n:
                self.s.fuse_until_ts = ts + self.p.loss_fuse_bars * HOUR_MS
                self.s.consec_losses = 0
                self.s.fuse_events += 1
                return True
        else:
            self.s.consec_losses = 0
        return False

    # ---- بررسی ورود ----
    def check_entry(self, symbol: str, ts: int, *, open_symbols: set, btc_state: str | None,
                    data_ok: bool, median_qv: float) -> list[str]:
        """فهرست دلایل رد؛ فهرست خالی = مجاز."""
        r = []
        if not tradable_symbol(symbol):
            r.append("EXCLUDED_STABLE_OR_LEVERAGED")
        if not data_ok:
            r.append("DATA_QUALITY_FAIL")
        if symbol in open_symbols:
            r.append("ALREADY_OPEN")
        if len(open_symbols) >= self.p.max_positions:
            r.append("MAX_POSITIONS")
        last = self.s.last_close_ts.get(symbol)
        if last is not None and ts - last < self.p.cooldown_bars * HOUR_MS:
            r.append("COOLDOWN")
        if ts < self.s.fuse_until_ts:
            r.append("LOSS_FUSE_ACTIVE")
        if self.s.day_halted:
            r.append("DAILY_DRAWDOWN_HALT")
        if btc_state in self.p.block_btc_states:
            r.append(f"BTC_REGIME_{btc_state}")
        elif self.p.require_btc_states and btc_state not in self.p.require_btc_states:
            r.append(f"BTC_NOT_IN_{''.join(self.p.require_btc_states)}")
        if not (median_qv == median_qv) or median_qv < self.p.min_quote_vol_usdt:
            r.append("LOW_LIQUIDITY")
        return r

    def size(self, entry_px: float, stop_px: float, equity: float, fee_side: float) -> float:
        """اندازهٔ موقعیت: ریسک ثابت ۱٪ تا حد ضرر، با سقف ارزش هر موقعیت و نقدینگی آزاد."""
        per_unit = entry_px - stop_px
        if per_unit <= 0 or entry_px <= 0:
            return 0.0
        q_risk = equity * self.p.risk_per_trade / per_unit
        q_cap = equity * self.p.max_position_frac / entry_px
        q_cash = self.s.cash / (entry_px * (1 + fee_side))
        return max(0.0, min(q_risk, q_cap, q_cash))
