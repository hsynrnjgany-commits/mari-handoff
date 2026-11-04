# -*- coding: utf-8 -*-
"""پیکربندی ربات ماری — همهٔ پارامترها یک‌جا و قابل هش (برای ردیابی منشأ، بخش ۳۴).

قفل دائمی: READ ONLY | PAPER ONLY | NO LIVE ORDERS
این ماژول هیچ کلید صرافی نمی‌خواند و هیچ مسیر ثبت سفارش در کل بسته وجود ندارد.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

# این سه پرچم ثابت‌اند و در زمان اجرا بررسی می‌شوند؛ تغییرشان اجرای ربات را متوقف می‌کند.
PAPER_ONLY = True
NO_LIVE_ORDERS = True
READ_ONLY_MARKET_DATA = True

CODE_VERSION = "MARI-BOT-1.0.0"
LOCK_LINE = "همه‌چیز تمرینی است — بدون سفارش واقعی"

STABLE_BASES = {
    "USDT", "USDC", "FDUSD", "TUSD", "DAI", "BUSD", "USDP", "USDD", "PYUSD", "USD1", "RLUSD",
    "RWUSD", "BFUSD", "USDE", "EUR", "EURI", "GUSD", "U", "XUSD", "USDS", "FRAX", "LUSD", "PAXG", "XAUT",  # طلا هم قیمت مستقل کریپتویی ندارد
}
# «UP» عمداً نیست: نام‌های واقعی مثل SYRUP یا JUP را به‌اشتباه حذف می‌کرد.
LEVERAGED_SUFFIXES = ("DOWN", "BULL", "BEAR", "3L", "3S", "5L", "5S", "2L", "2S")


@dataclass(frozen=True)
class TrendParams:
    ema_fast: int = 20
    ema_mid: int = 50
    ema_slow: int = 150
    atr_n: int = 14
    adx_n: int = 14
    rsi_n: int = 14
    pivot_k: int = 3            # پیوت فقط پس از k کندل بعدی تأیید می‌شود (بدون نگاه به آینده)
    slope_lookback: int = 10
    adx_strong: float = 25.0
    adx_weak: float = 18.0
    crash_ret_24h: float = -0.12   # افت ۲۴ساعته بدتر از ۱۲٪
    crash_ret_4h: float = -0.07    # افت ۴ساعته بدتر از ۷٪
    crash_atr_mult: float = 3.0    # جهش نوسان نسبت به میانهٔ ۱۰۰ کندل
    min_bars: int = 160


@dataclass(frozen=True)
class EntryParams:
    breakout_n: int = 20        # شکست سقف ۲۰ کندل بسته
    vol_ratio_min: float = 1.2  # حجم ۵ کندل اخیر نسبت به ۵۰ کندل
    rsi_max: float = 78.0       # ورود در اشباع خرید ممنوع
    init_stop_atr: float = 2.5


@dataclass(frozen=True)
class ExitParams:
    trail_atr: dict = field(default_factory=lambda: {"A": 3.0, "B": 2.5, "C": 2.0, "D": 1.8,
                                                      "E": 1.5, "F": 1.2, "G": 1.0, "H": 2.0})
    breakeven_at_r: float = 1.5     # انتقال حد ضرر به نقطهٔ ورود پس از ۱٫۵R
    scale_at_r: float = 3.0         # برداشت جزئی سود در ۳R (فقط وقتی روند A نیست)
    scale_frac: float = 0.25
    weakness_frac: float = 0.33     # مرحلهٔ ۲: فروش یک‌سوم باقی‌مانده
    bearish_frac: float = 0.50      # مرحلهٔ ۳: فروش نیمی از باقی‌مانده
    weakness_bars: int = 3          # چند کندل پیاپی در C تا «ضعف تأییدشده»
    stale_bars: int = 72            # اگر پس از ۷۲ کندل سود بیشینه کمتر از ۰٫۵R بود: خروج زمانی
    stale_min_r: float = 0.5


@dataclass(frozen=True)
class RiskParams:
    start_equity: float = 1000.0
    risk_per_trade: float = 0.01      # ۱٪ سرمایه در هر معامله
    max_position_frac: float = 0.20   # سقف ارزش هر موقعیت
    max_positions: int = 5
    cooldown_bars: int = 6            # فاصلهٔ ۶ساعته پس از بستن هر نماد
    loss_fuse_n: int = 3              # فیوز ۳ ضرر پیاپی
    loss_fuse_bars: int = 24          # توقف ۲۴ساعته ورود جدید
    daily_dd_halt: float = 0.03       # توقف روزانه با افت ۳٪
    min_quote_vol_usdt: float = 50_000.0  # میانهٔ حجم دلاری ۲۰ کندل
    block_btc_states: tuple = ("E", "F", "G")


@dataclass(frozen=True)
class CostParams:
    fee_side: float = 0.001     # کارمزد هر طرف ۰٫۱٪
    slippage: float = 0.0005    # لغزش هر طرف ۰٫۰۵٪


@dataclass(frozen=True)
class BotConfig:
    trend: TrendParams = field(default_factory=TrendParams)
    entry: EntryParams = field(default_factory=EntryParams)
    exit: ExitParams = field(default_factory=ExitParams)
    risk: RiskParams = field(default_factory=RiskParams)
    cost: CostParams = field(default_factory=CostParams)
    interval: str = "1h"
    benchmark: str = "BTCUSDT"

    def to_dict(self) -> dict:
        return asdict(self)

    def sha(self) -> str:
        blob = json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False).encode()
        return hashlib.sha256(blob).hexdigest()[:16]


def assert_locks() -> None:
    """هر ورودی اصلی ربات این تابع را صدا می‌زند."""
    if not (PAPER_ONLY and NO_LIVE_ORDERS and READ_ONLY_MARKET_DATA):
        raise SystemExit("قفل PAPER ONLY شکسته شده — اجرا متوقف شد.")


def tradable_symbol(sym: str) -> bool:
    """حذف‌های فقط «تعریفی» (بخش ۳۳.۵): استیبل‌کوین‌ها و توکن‌های اهرمی."""
    if not sym.endswith("USDT"):
        return False
    base = sym[:-4]
    if not base or not base.isascii():
        return False
    if base in STABLE_BASES:
        return False
    return not any(base.endswith(s) and len(base) > len(s) + 1 for s in LEVERAGED_SUFFIXES)
