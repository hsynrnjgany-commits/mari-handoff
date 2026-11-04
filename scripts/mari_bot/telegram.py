# -*- coding: utf-8 -*-
"""کانال تلگرام ماری (سند مادر بخش ۳۳) — گزارش فارسی، راست‌به‌چپ، با اعداد فارسی.

- توکن فقط از متغیر محیطی MARI_TELEGRAM_TOKEN (یا TELEGRAM_BOT_TOKEN) خوانده می‌شود و هرگز چاپ نمی‌شود.
- هر پیام با «همه‌چیز تمرینی است — بدون سفارش واقعی» تمام می‌شود.
- چت‌هایی که خطای 403 می‌دهند خودکار حذف می‌شوند؛ ثبت‌نام فقط با /start.
- اگر توکن نباشد، پیام‌ها فقط در خروجی چاپ می‌شوند (حالت خشک).
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from .config import LOCK_LINE
from .position import STAGES_FA
from .trend import STATES_FA

API = "https://api.telegram.org"
TEHRAN = timezone(timedelta(hours=3, minutes=30))
_FA_DIGITS = str.maketrans("0123456789,.-", "۰۱۲۳۴۵۶۷۸۹،٫−")


def fa(x, digits: int = 2, sign: bool = False) -> str:
    if x is None or (isinstance(x, float) and x != x):
        return "نامشخص"
    if isinstance(x, int):
        s = f"{x:,}"
    else:
        s = f"{x:+,.{digits}f}" if sign else f"{x:,.{digits}f}"
    return s.translate(_FA_DIGITS)


def fa_time(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, TEHRAN).strftime("%Y/%m/%d %H:%M").translate(_FA_DIGITS) + " تهران"


def _end(lines: list[str]) -> str:
    return "\n".join(lines + ["", f"⚠️ {LOCK_LINE}"])


# ---------------------------------------------------------------- قالب پیام‌ها (خالص، قابل آزمون)
def fmt_report(bot) -> str:
    tr = bot.trades
    n = len(tr)
    eq, start = bot.equity(), bot.cfg.risk.start_equity
    lines = ["📊 <b>کارنامهٔ تمرینی ماری</b>", ""]
    lines.append(f"سرمایهٔ فرضی: {fa(eq)} تتر (شروع {fa(start)}، تغییر {fa((eq / start - 1) * 100, sign=True)}٪)")
    if not n:
        lines.append("هنوز هیچ معاملهٔ بسته‌شده‌ای ثبت نشده.")
    else:
        wins = [t for t in tr if t["pnl_usdt"] > 0]
        gl = -sum(t["pnl_usdt"] for t in tr if t["pnl_usdt"] <= 0)
        gw = sum(t["pnl_usdt"] for t in wins)
        lines += [
            f"تعداد معاملهٔ بسته: {fa(n)}",
            f"نرخ برد: {fa(len(wins) / n * 100, 1)}٪",
            f"ضریب سود: {fa(gw / gl) if gl > 0 else 'بدون ضرر'}",
            f"میانگین بازده هر معامله: {fa(sum(t['pnl_pct'] for t in tr) / n, sign=True)}٪",
        ]
    lines.append(f"موقعیت باز: {fa(len(bot.positions))} از {fa(bot.cfg.risk.max_positions)}")
    if bot.gate.s.fuse_until_ts and bot.last_ts < bot.gate.s.fuse_until_ts:
        lines.append(f"🧯 فیوز ضرر فعال است تا {fa_time(bot.gate.s.fuse_until_ts)}")
    if bot.btc_state:
        lines.append(f"وضعیت بیت‌کوین: {STATES_FA.get(bot.btc_state, bot.btc_state)}")
    return _end(lines)


def fmt_trades(bot) -> str:
    lines = ["📒 <b>موقعیت‌های باز</b>"]
    if not bot.positions:
        lines.append("موقعیت بازی وجود ندارد.")
    for sym, p in bot.positions.items():
        px = bot.last_px.get(sym, p.entry_px)
        upct = (px / p.entry_px - 1) * 100
        lines.append(f"• {sym}: ورود {fa(p.entry_px, 6)} ← اکنون {fa(px, 6)} ({fa(upct, sign=True)}٪) — "
                     f"مرحله: {STAGES_FA.get(p.stage)}، حد ضرر {fa(p.stop, 6)}")
    lines += ["", "🧾 <b>۵ نتیجهٔ آخر</b>"]
    if not bot.trades:
        lines.append("هنوز ثبت نشده.")
    for t in bot.trades[-5:][::-1]:
        icon = "✅" if t["pnl_usdt"] > 0 else "❌"
        lines.append(f"{icon} {t['symbol']}: {fa(t['pnl_pct'], sign=True)}٪ — بیشینهٔ سود در مسیر "
                     f"{fa(t['mfe_pct'])}٪ — {fa(t['held_h'])} ساعت")
    return _end(lines)


def fmt_hunt(bot, top: int = 8) -> str:
    snap = bot.snapshot
    lines = ["🔭 <b>گشت سایه‌وار بازار</b> (فقط مشاهده — در دفتر ثبت نمی‌شود)"]
    if not snap:
        lines.append("هنوز اسکنی انجام نشده.")
        return _end(lines)
    counts = {}
    for v in snap.values():
        counts[v["state"]] = counts.get(v["state"], 0) + 1
    lines.append("پراکندگی وضعیت‌ها: " + "، ".join(f"{STATES_FA[k]} {fa(c)}" for k, c in sorted(counts.items())))
    best = sorted((kv for kv in snap.items() if kv[1]["state"] in ("A", "B")), key=lambda kv: -kv[1]["score"])[:top]
    lines.append("")
    lines.append("برترین روندهای صعودی:" if best else "در این لحظه روند صعودی معتبری دیده نشد.")
    for sym, v in best:
        tag = " 🎯 سیگنال" if v["signal"] else ""
        lines.append(f"• {sym}: {STATES_FA[v['state']]} (امتیاز {fa(v['score'], 1)}، RSI {fa(v['rsi'], 0)}){tag}")
    lines.append("")
    lines.append("«سیگنال مشاهده‌شده» با «معامله» یکی نیست؛ ورود فقط با موتور خودکار و دروازهٔ ریسک.")
    return _end(lines)


def fmt_event(rec: dict) -> str | None:
    e, sym = rec.get("event"), rec.get("symbol", "")
    if e == "ENTRY":
        return _end([f"🟢 <b>ورود تمرینی: {sym}</b>", f"قیمت: {fa(rec['price'], 6)} — حد ضرر: {fa(rec['stop'], 6)}",
                     f"ارزش: {fa(rec['notional'])} تتر — ریسک: {fa(rec['risk_usdt'])} تتر", f"چرا: {rec.get('why', '')}"])
    if e == "PARTIAL":
        return _end([f"🟡 <b>فروش بخشی: {sym}</b>", f"قیمت: {fa(rec['price'], 6)}", f"چرا: {rec.get('why', '')}"])
    if e == "CLOSED":
        icon = "✅" if rec["pnl_usdt"] > 0 else "🔴"
        return _end([f"{icon} <b>بسته شد: {sym}</b>",
                     f"نتیجهٔ خالص (پس از کارمزد فرضی): {fa(rec['pnl_pct'], sign=True)}٪ ({fa(rec['pnl_usdt'], sign=True)} تتر)",
                     f"بیشینهٔ سود در مسیر: {fa(rec['mfe_pct'])}٪ — مدت: {fa(rec['held_h'])} ساعت",
                     f"علت خروج: {rec.get('exit_reason')}"])
    if e == "LOSS_FUSE":
        return _end(["🧯 <b>فیوز ضرر پیاپی فعال شد</b>", rec.get("why", ""), f"تا {fa_time(rec['until_ts'])}"])
    return None


HELP = _end([
    "🤖 <b>ربات ماری — راهنما</b>",
    "/start — ثبت این چت برای گزارش‌های خودکار",
    "/stop — لغو دریافت گزارش",
    "/report — کارنامهٔ تمرینی",
    "/trades — موقعیت‌های باز و ۵ نتیجهٔ آخر",
    "/hunt — برترین روندهای بازار (فقط مشاهده)",
    "/council — شورای هوش مصنوعی",
    "/help — همین راهنما",
])

COUNCIL = _end(["🧠 شورای هوش مصنوعی هنوز وصل نیست (وضعیت: NOT_TESTED).",
                "طبق بخش ۳۳ سند، هیچ مدلی اجازهٔ صدور سفارش ندارد و تصمیم‌ها با کد قابل بازبینی گرفته می‌شوند."])


# ---------------------------------------------------------------- ارتباط با تلگرام
class Telegram:
    def __init__(self, store_path: str):
        self.token = (os.environ.get("MARI_TELEGRAM_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
        self.path = store_path
        self.store = {"subscribers": [], "offset": 0, "last_daily": ""}
        if os.path.exists(store_path):
            try:
                with open(store_path, encoding="utf-8") as fh:
                    self.store.update(json.load(fh))
            except (OSError, ValueError):
                pass

    @property
    def enabled(self) -> bool:
        return bool(self.token)

    def save(self) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.store, fh, ensure_ascii=False)
        os.replace(tmp, self.path)

    def _call(self, method: str, params: dict, timeout: float = 20):
        url = f"{API}/bot{self.token}/{method}"
        data = urllib.parse.urlencode(params).encode()
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=timeout) as r:
                return json.loads(r.read().decode()), 200
        except urllib.error.HTTPError as e:
            return None, e.code
        except Exception:  # noqa: BLE001 — شبکه؛ توکن در پیام خطا چاپ نمی‌شود
            return None, 0

    def send(self, chat_id, text: str) -> bool:
        if not self.enabled:
            print(f"[تلگرام خاموش → {chat_id}]\n{text}\n")
            return False
        _, code = self._call("sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                                             "disable_web_page_preview": "true"})
        if code == 403 and chat_id in self.store["subscribers"]:
            self.store["subscribers"].remove(chat_id)   # چت مرده
            self.save()
        return code == 200

    def broadcast(self, text: str) -> int:
        if not self.store["subscribers"]:
            if not self.enabled:
                print(text + "\n")
            return 0
        return sum(self.send(c, text) for c in list(self.store["subscribers"]))

    def handle_updates(self, bot, wait: int = 0) -> int:
        if not self.enabled:
            return 0
        res, code = self._call("getUpdates", {"offset": self.store["offset"], "timeout": wait}, timeout=wait + 15)
        if code != 200 or not res or not res.get("ok"):
            return 0
        n = 0
        for u in res.get("result", []):
            self.store["offset"] = u["update_id"] + 1
            msg = u.get("message") or u.get("channel_post") or {}
            text = (msg.get("text") or "").strip()
            chat = (msg.get("chat") or {}).get("id")
            if not chat or not text.startswith("/"):
                continue
            cmd = text.split()[0].split("@")[0].lower()
            n += 1
            if cmd == "/start":
                if chat not in self.store["subscribers"]:
                    self.store["subscribers"].append(chat)
                self.send(chat, "✅ این چت برای گزارش‌های خودکار ثبت شد.\n\n" + HELP)
            elif cmd == "/stop":
                if chat in self.store["subscribers"]:
                    self.store["subscribers"].remove(chat)
                self.send(chat, _end(["دریافت گزارش خودکار لغو شد."]))
            elif cmd == "/report":
                self.send(chat, fmt_report(bot))
            elif cmd == "/trades":
                self.send(chat, fmt_trades(bot))
            elif cmd == "/hunt":
                self.send(chat, fmt_hunt(bot))
            elif cmd == "/council":
                self.send(chat, COUNCIL)
            else:
                self.send(chat, HELP)
        self.save()
        return n

    def maybe_daily(self, bot, hour: int = 9) -> bool:
        now = datetime.now(TEHRAN)
        day = now.strftime("%Y-%m-%d")
        if now.hour >= hour and self.store.get("last_daily") != day:
            self.store["last_daily"] = day
            self.save()
            self.broadcast("☀️ <b>گزارش روزانه</b>\n\n" + fmt_report(bot))
            return True
        return False
