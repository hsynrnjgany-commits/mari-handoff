# -*- coding: utf-8 -*-
"""مدیریت موقعیت تمرینی: PROFIT RUNNER + فروش پله‌ای ۵مرحله‌ای (CORE-DOCTRINE بخش‌های ۴ تا ۷).

اصول:
- روند صعودی معتبر (A/B) = نگه‌دار، حد ضرر متحرک، بدون حد سود ثابت.
- ضعف (C) = هشدار زودهنگام → ضعف تأییدشده (C پیاپی یا D) = فروش بخشی.
- نزولی تأییدشده (E) = کاهش بیشتر. ابطال (F یا خوردن حد ضرر) = خروج کامل. سقوط (G) = خروج اضطراری.
- فروش پله‌ای هرگز به معنی نگه‌داشتن اجباری موقعیت زیان‌ده نیست: حد ضرر همیشه کل باقی‌مانده را می‌بندد.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .config import CostParams, ExitParams

STAGES = {0: "TREND_CONTINUES", 1: "EARLY_WARNING", 2: "TREND_WEAKNESS",
          3: "BEARISH_CONFIRMATION", 4: "INVALIDATION", 5: "EMERGENCY"}
STAGES_FA = {0: "ادامهٔ روند", 1: "هشدار زودهنگام", 2: "ضعف تأییدشده",
             3: "تأیید نزولی", 4: "ابطال فرضیه", 5: "خروج اضطراری"}


@dataclass
class Fill:
    ts: int
    side: str        # BUY / SELL
    qty: float
    price: float     # قیمت پس از لغزش
    fee: float
    reason: str
    stage: int


@dataclass
class Position:
    symbol: str
    entry_ts: int
    entry_px: float          # قیمت پرشده (با لغزش)
    qty0: float
    stop: float
    risk_per_unit: float     # R = فاصلهٔ ورود تا حد ضرر اولیه
    entry_state: str
    entry_reason: str
    qty: float = 0.0
    peak: float = 0.0
    trough: float = 0.0
    stage: int = 0
    max_stage: int = 0
    weak_count: int = 0
    be_done: bool = False
    scaled: bool = False
    weak_done: bool = False
    bear_done: bool = False
    fills: list = field(default_factory=list)

    def __post_init__(self):
        if not self.qty:
            self.qty = self.qty0
        self.peak = self.peak or self.entry_px
        self.trough = self.trough or self.entry_px

    # ---- سنجه‌های PROFIT RUNNER (بخش ۷) ----
    def mfe_pct(self) -> float:
        return (self.peak / self.entry_px - 1) * 100

    def mae_pct(self) -> float:
        return (self.trough / self.entry_px - 1) * 100

    def mfe_r(self) -> float:
        return (self.peak - self.entry_px) / self.risk_per_unit if self.risk_per_unit > 0 else 0.0

    def unrealized(self, px: float) -> float:
        return (px - self.entry_px) * self.qty

    def realized(self) -> float:
        cost = self.entry_px * self.qty0
        got = sum(f.qty * f.price for f in self.fills if f.side == "SELL")
        sold = sum(f.qty for f in self.fills if f.side == "SELL")
        fees = sum(f.fee for f in self.fills)
        return got - cost * (sold / self.qty0) - fees

    def giveback_pct(self, px: float) -> float:
        """سود بازگردانده‌شده از اوج (بر حسب درصد قیمت ورود)."""
        return max(0.0, (self.peak - px) / self.entry_px * 100)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["fills"] = [asdict(f) if isinstance(f, Fill) else f for f in self.fills]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Position":
        d = dict(d)
        fills = [Fill(**f) for f in d.pop("fills", [])]
        p = cls(**d)
        p.fills = fills
        return p


def _sell(pos: Position, ts: int, qty: float, raw_px: float, reason: str, stage: int, cost: CostParams) -> Fill:
    qty = min(qty, pos.qty)
    px = raw_px * (1 - cost.slippage)
    fill = Fill(ts, "SELL", qty, px, qty * px * cost.fee_side, reason, stage)
    pos.qty -= qty
    pos.fills.append(fill)
    pos.max_stage = max(pos.max_stage, stage)
    return fill


def manage(pos: Position, bar: dict, state: str, atr: float, ex: ExitParams, cost: CostParams) -> list[Fill]:
    """یک کندل بسته را روی موقعیت اعمال می‌کند. حد ضرر کندل قبل درون کندل بررسی می‌شود؛ بقیهٔ تصمیم‌ها روی بسته‌شدن."""
    out: list[Fill] = []
    ts = bar["t"]

    # ۱) حد ضرر درون‌کندلی (از کندل قبل تعیین شده — بدون نگاه به آینده)
    if bar["l"] <= pos.stop:
        px = bar["o"] if bar["o"] < pos.stop else pos.stop      # شکاف قیمتی: پر شدن در قیمت باز
        trailing = pos.stop > pos.entry_px
        out.append(_sell(pos, ts, pos.qty, px, "TRAIL_STOP" if trailing else "STOP_LOSS", 4, cost))
        pos.trough = min(pos.trough, bar["l"])
        pos.stage = 4
        return out

    pos.peak = max(pos.peak, bar["h"])
    pos.trough = min(pos.trough, bar["l"])
    c = bar["c"]

    # ۲) وضعیت‌های خروج کامل
    if state == "G":
        pos.stage = 5
        out.append(_sell(pos, ts, pos.qty, c, "EMERGENCY_CRASH", 5, cost))
        return out
    if state == "F":
        pos.stage = 4
        out.append(_sell(pos, ts, pos.qty, c, "INVALIDATION_STRONG_BEARISH", 4, cost))
        return out

    # ۳) ماشین حالت پله‌ای
    if state in ("A", "B"):
        pos.stage, pos.weak_count = 0, 0
    elif state == "C":
        pos.weak_count += 1
        pos.stage = max(pos.stage, 1)
        if pos.weak_count >= ex.weakness_bars:
            pos.stage = max(pos.stage, 2)
    elif state in ("D", "H"):
        pos.weak_count += 1
        pos.stage = max(pos.stage, 2)
    elif state == "E":
        pos.stage = 3

    if pos.stage == 2 and not pos.weak_done:
        pos.weak_done = True
        out.append(_sell(pos, ts, pos.qty * ex.weakness_frac, c, "RISK_REDUCTION_WEAKNESS", 2, cost))
    if pos.stage == 3 and not pos.bear_done:
        pos.bear_done = True
        out.append(_sell(pos, ts, pos.qty * ex.bearish_frac, c, "RISK_REDUCTION_BEARISH", 3, cost))
    pos.max_stage = max(pos.max_stage, pos.stage)

    # ۴) برداشت جزئی سود (PROFIT SCALING) — فقط وقتی روند «قوی» نیست تا برنده زود فروخته نشود
    mfe_r = pos.mfe_r()
    if not pos.scaled and mfe_r >= ex.scale_at_r and state != "A" and c > pos.entry_px:
        pos.scaled = True
        out.append(_sell(pos, ts, pos.qty * ex.scale_frac, c, "PROFIT_SCALING", pos.stage, cost))

    # ۵) خروج زمانی: موقعیتی که هرگز حرکت نکرد
    held = (ts - pos.entry_ts) // 3_600_000
    if pos.qty > 0 and held >= ex.stale_bars and mfe_r < ex.stale_min_r:
        out.append(_sell(pos, ts, pos.qty, c, "TIME_NO_FOLLOW_THROUGH", pos.stage, cost))
        return out

    # ۶) باقی‌ماندهٔ ناچیز بسته می‌شود
    if 0 < pos.qty < 0.05 * pos.qty0:
        out.append(_sell(pos, ts, pos.qty, c, "DUST_CLOSE", pos.stage, cost))
        return out

    # ۷) حد ضرر: سربه‌سر پس از ۱٫۵R، سپس متحرک وابسته به نوسان و وضعیت روند (فقط بالا می‌رود)
    if not pos.be_done and mfe_r >= ex.breakeven_at_r:
        pos.be_done = True
        pos.stop = max(pos.stop, pos.entry_px * (1 + 2 * (cost.fee_side + cost.slippage)))
    k = ex.trail_atr.get(state, 2.0)
    if atr == atr and atr > 0:
        pos.stop = max(pos.stop, pos.peak - k * atr)
    return out


def close_summary(pos: Position) -> dict:
    sells = [f for f in pos.fills if f.side == "SELL"]
    sold = sum(f.qty for f in sells)
    avg_exit = sum(f.qty * f.price for f in sells) / sold if sold else 0.0
    pnl = pos.realized()
    notional = pos.entry_px * pos.qty0
    pnl_pct = pnl / notional * 100 if notional else 0.0
    mfe = pos.mfe_pct()
    return {
        "symbol": pos.symbol, "entry_ts": pos.entry_ts, "exit_ts": sells[-1].ts if sells else None,
        "entry_px": pos.entry_px, "avg_exit_px": avg_exit, "qty": pos.qty0,
        "pnl_usdt": round(pnl, 4), "pnl_pct": round(pnl_pct, 3),
        "r_multiple": round(pnl / (pos.risk_per_unit * pos.qty0), 3) if pos.risk_per_unit else None,
        "mfe_pct": round(mfe, 3), "mae_pct": round(pos.mae_pct(), 3),
        "giveback_pct": round(max(0.0, mfe - pnl_pct), 3),
        "capture_ratio": round(pnl_pct / mfe, 3) if mfe > 0.05 else None,
        "held_h": ((sells[-1].ts - pos.entry_ts) // 3_600_000) if sells else 0,
        "exit_reason": sells[-1].reason if sells else None,
        "max_stage": pos.max_stage, "partials": len(sells) - 1,
        "entry_state": pos.entry_state,
    }
