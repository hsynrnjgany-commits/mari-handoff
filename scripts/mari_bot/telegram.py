# -*- coding: utf-8 -*-
"""کانال تلگرام ماری (سند مادر بخش ۳۳) — گزارش فارسی، راست‌به‌چپ، با اعداد فارسی.

- توکن فقط از متغیر محیطی MARI_TELEGRAM_TOKEN (یا TELEGRAM_BOT_TOKEN) خوانده می‌شود و هرگز چاپ نمی‌شود.
- هر پیام با «همه‌چیز تمرینی است — بدون سفارش واقعی» تمام می‌شود.
- چت‌هایی که خطای 403 می‌دهند خودکار حذف می‌شوند؛ ثبت‌نام فقط با /start.
- اگر MARI_TELEGRAM_CHAT_ID تنظیم شده باشد، ربات فقط به همان چت پیام می‌دهد و فرمان دیگران را
  نادیده می‌گیرد (حالت شخصی — مناسب اجرای خودکار در گیت‌هاب، چون شناسهٔ چت در فایل عمومی ذخیره نمی‌شود).
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
    lines += _btc_lines(getattr(bot, "btc_summary", None))
    return _end(lines)


def _btc_lines(b: dict | None) -> list[str]:
    if not b or not b.get("position"):
        return []
    pos = "نگه‌داری بیت‌کوین 🟢" if b["position"] == "BTC" else "نقد (بیرون از بازار) ⚪"
    return ["", "₿ <b>استراتژی روند بیت‌کوین (T-006)</b>",
            f"وضعیت: {pos}",
            f"قیمت: {fa(b['close'], 0)} — میانگین ۱۵۰روزه: {fa(b['sma150'], 0)}",
            f"سرمایهٔ فرضی: {fa(b['equity'])} تتر ({fa(b['return_pct'], sign=True)}٪) — "
            f"نگه‌داری سادهٔ BTC در همین مدت: {fa(b['btc_hold_return_pct'], sign=True)}٪"]


def fmt_btc_event(ev: dict, summ: dict | None = None) -> str:
    if ev["to"] == "BTC":
        head = "🟢 <b>روند بیت‌کوین: خرید تمرینی</b>"
        why = "قیمت بستهٔ روزانه بالای میانگین ۱۵۰روزه رفت."
    else:
        head = "⚪ <b>روند بیت‌کوین: فروش تمرینی و نقد شدن</b>"
        why = "قیمت بستهٔ روزانه زیر میانگین ۱۵۰روزه آمد."
    if ev.get("boot"):
        head += " (شروع پیگیری)"
    lines = [head, f"قیمت: {fa(ev['close'], 0)} — میانگین ۱۵۰روزه: {fa(ev['sma'], 0)}", f"چرا: {why}"]
    if summ:
        lines += [f"سرمایهٔ فرضی این استراتژی: {fa(summ['equity'])} تتر"]
    lines += ["این تنها روشی است که آزمون ۸سالهٔ ماری را گذرانده؛ هنوز در حال اثبات روی دادهٔ زنده است."]
    return _end(lines)


def fmt_dca(b: dict | None) -> list[str]:
    if not b or not b.get("position"):
        return ["💰 یادآور خرید پله‌ای: دادهٔ روند بیت‌کوین هنوز آماده نیست."]
    if b["position"] == "BTC":
        act = "بیت‌کوین بالای میانگین ۱۵۰روزه است → طبق قانون، مبلغ ثابت این هفته‌ات را می‌شد بیت‌کوین خرید."
    else:
        act = ("بیت‌کوین زیر میانگین ۱۵۰روزه است → طبق قانون، مبلغ این هفته را نقد کنار بگذار "
               "(و دارایی بیت‌کوین قبلی هم طبق قانون نقد می‌شد).")
    return ["💰 <b>یادآور خرید پله‌ای هفتگی</b>", act,
            "این فقط یادآوری قانون آزموده‌شده است، نه دستور خرید. فقط با پولی که از دست دادنش زندگی‌ات را تغییر نمی‌دهد."]


def fmt_health(ok: bool, streak: int, why: str | None) -> str:
    if ok:
        return _end(["✅ <b>ربات ماری دوباره سالم است</b>", "دریافت داده و پردازش به حالت عادی برگشت."])
    return _end(["🚨 <b>هشدار سلامت ربات ماری</b>",
                 f"{fa(streak)} چرخهٔ پیاپی ناموفق بود — علت: {why or 'نامشخص'}.",
                 "اگر تا چند ساعت دیگر پیام «دوباره سالم است» نیامد، زبانهٔ Actions گیت‌هاب را ببین یا به Claude بگو."])


def fmt_turtle_event(ev: dict, summ: dict | None = None) -> str:
    if ev["to"] == "BTC":
        head, why = "🐢🟢 <b>روش لاک‌پشت‌ها: خرید تمرینی بیت‌کوین</b>", "قیمت بسته سقف ۵۵ روز گذشته را شکست."
    else:
        head, why = "🐢⚪ <b>روش لاک‌پشت‌ها: نقد شدن تمرینی</b>", "قیمت بسته کف ۲۰ روز گذشته را شکست."
    if ev.get("boot"):
        head += " (شروع پیگیری)"
        why = "وضعیت فعلی در شروع پیگیری."
    lines = [head, f"قیمت: {fa(ev['close'], 0)}", f"چرا: {why}"]
    if summ:
        lines.append(f"سرمایهٔ فرضی این روش: {fa(summ['equity'])} تتر")
    return _end(lines)


def fmt_daily_simple(bot, monday: bool = False) -> str:
    """گزارش روزانهٔ ساده: فقط آنچه مهم است."""
    b = getattr(bot, "btc_summary", None)
    lines = ["☀️ <b>خلاصهٔ روزانهٔ ماری</b>", ""]
    if b and b.get("position"):
        pos = "🟢 نگه‌داری" if b["position"] == "BTC" else "⚪ نقد"
        lines += ["₿ <b>روند بیت‌کوین (روش قبول‌شده)</b>",
                  f"وضعیت: {pos} — قیمت {fa(b['close'], 0)} — میانگین ۱۵۰روزه {fa(b['sma150'], 0)}",
                  f"نتیجهٔ تمرینی از شروع: {fa(b['return_pct'], sign=True)}٪ "
                  f"(نگه‌داری سادهٔ BTC: {fa(b['btc_hold_return_pct'], sign=True)}٪)", ""]
    tt = getattr(bot, "turtle_summary", None)
    if tt and tt.get("position"):
        lines += ["🐢 <b>روش لاک‌پشت‌ها (دومین روش قبول‌شده)</b>",
                  f"وضعیت: {'🟢 نگه‌داری' if tt['position'] == 'BTC' else '⚪ نقد'} — "
                  f"نتیجهٔ تمرینی از شروع: {fa(tt['return_pct'], sign=True)}٪", ""]
    snap = bot.snapshot or {}
    if snap:
        counts = {}
        for v in snap.values():
            counts[v["state"]] = counts.get(v["state"], 0) + 1
        up = counts.get("A", 0) + counts.get("B", 0)
        lines += ["📡 <b>رادار بازار</b>",
                  f"{fa(len(snap))} ارز بررسی شد — روند صعودی: {fa(up)} — نزولی یا سقوط: "
                  f"{fa(counts.get('E', 0) + counts.get('F', 0) + counts.get('G', 0))}"]
        best = sorted((kv for kv in snap.items() if kv[1]["state"] == "A"), key=lambda kv: -kv[1]["score"])[:5]
        if best:
            lines.append("قوی‌ترین‌ها: " + "، ".join(s.replace("USDT", "") for s, _ in best))
        lines.append("(فقط برای آگاهی — شکار آلت‌کوین در آزمون ۸ساله ضررده بود)")
        lines.append("")
    eq = bot.equity()
    lines.append(f"🤖 ربات شکار تمرینی: {fa(eq)} تتر — موقعیت باز {fa(len(bot.positions))}")
    if monday:
        lines += [""] + fmt_dca(b)
    return _end(lines)


CHANNEL_DISCLAIMER = ("این کانال آموزشی است، نه توصیهٔ مالی. هیچ سودی تضمین نمی‌شود و ممکن است ضرر کنید. "
                      "فقط با پولی کار کنید که از دست دادنش زندگی‌تان را تغییر نمی‌دهد. "
                      "ما هرگز پول کسی را مدیریت نمی‌کنیم و هیچ سیگنال پولی نمی‌فروشیم.")


def fmt_channel_event(ev: dict, summ: dict | None, ledger_url: str) -> str:
    if ev["to"] == "BTC":
        head = "🟢 <b>روند بیت‌کوین: وضعیت «نگه‌داری»</b>"
        why = "قیمت بستهٔ روزانه بالای میانگین ۱۵۰روزه است."
    else:
        head = "⚪ <b>روند بیت‌کوین: وضعیت «نقد»</b>"
        why = "قیمت بستهٔ روزانه زیر میانگین ۱۵۰روزه آمد."
    lines = [head, f"قیمت: {fa(ev['close'], 0)} دلار — میانگین ۱۵۰روزه: {fa(ev['sma'], 0)}", f"قانون: {why}"]
    if summ and summ.get("return_pct") is not None:
        lines.append(f"نتیجهٔ تمرینی از شروع پیگیری: {fa(summ['return_pct'], sign=True)}٪ "
                     f"(نگه‌داری سادهٔ BTC: {fa(summ['btc_hold_return_pct'], sign=True)}٪)")
    lines += ["", f"🔍 دفتر ثبت قابل‌بررسی (همهٔ تصمیم‌ها، حتی ضررها): {ledger_url}",
              "", f"ℹ️ {CHANNEL_DISCLAIMER}"]
    return _end(lines)


def fmt_channel_weekly(b: dict, ledger_url: str) -> str:
    pos = "نگه‌داری بیت‌کوین" if b["position"] == "BTC" else "نقد"
    lines = ["📅 <b>گزارش شفاف هفتگی — روند بیت‌کوین</b>",
             f"وضعیت فعلی: {pos}",
             f"قیمت: {fa(b['close'], 0)} — میانگین ۱۵۰روزه: {fa(b['sma150'], 0)}",
             f"نتیجهٔ تمرینی از شروع: {fa(b['return_pct'], sign=True)}٪ — "
             f"نگه‌داری سادهٔ BTC در همین مدت: {fa(b['btc_hold_return_pct'], sign=True)}٪",
             f"تعداد تغییر وضعیت تا امروز: {fa(b['switches'])}",
             "",
             "این روش در آزمون ۸ساله (۲۰۱۸ تا ۲۰۲۶) ریزش‌های کوچک‌تری از نگه‌داری BTC داشت؛ "
             "حالا روی دادهٔ زنده در حال سنجش است. نتیجه هر چه باشد، همین‌جا منتشر می‌شود.",
             "", f"🔍 دفتر ثبت: {ledger_url}", "", f"ℹ️ {CHANNEL_DISCLAIMER}"]
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
    lines = [f"🔭 <b>گشت سایه‌وار بازار</b> — {fa(len(bot.snapshot))} ارز بررسی شد (فقط مشاهده)"]
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
    lines.append("یادآوری: شکار آلت‌کوین در آزمون منصفانهٔ ۸ساله ضررده بود؛ این فهرست فقط برای آگاهی است.")
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
    "/btc — استراتژی روند بیت‌کوین",
    "/dca — یادآور خرید پله‌ای",
    "/daily — خلاصهٔ روزانه",
    "/council — شورای هوش مصنوعی",
    "/help — همین راهنما",
])

COUNCIL = _end(["🧠 شورای هوش مصنوعی هنوز وصل نیست (وضعیت: NOT_TESTED).",
                "طبق بخش ۳۳ سند، هیچ مدلی اجازهٔ صدور سفارش ندارد و تصمیم‌ها با کد قابل بازبینی گرفته می‌شوند."])


# ---------------------------------------------------------------- ارتباط با تلگرام
class Telegram:
    def __init__(self, store_path: str):
        self.token = (os.environ.get("MARI_TELEGRAM_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
        owner = (os.environ.get("MARI_TELEGRAM_CHAT_ID") or "").strip()
        self.owner = int(owner) if owner.lstrip("-").isdigit() else None
        # کانال عمومی (اختیاری): مثل @mari_honest یا -100xxxxxxxxxx. فقط روش قبول‌شده آنجا منتشر می‌شود.
        self.channel = (os.environ.get("MARI_TELEGRAM_CHANNEL_ID") or "").strip() or None
        self.path = store_path
        self.store = {"subscribers": [], "offset": 0, "last_daily": "", "hello_sent": False}
        self.diag = {"enabled": False, "token_ok": None, "sent_ok": 0, "sent_fail": 0, "fail_codes": [],
                     "commands": 0, "ignored_other_chats": 0}
        if os.path.exists(store_path):
            try:
                with open(store_path, encoding="utf-8") as fh:
                    self.store.update(json.load(fh))
            except (OSError, ValueError):
                pass
        if self.owner is not None:
            self.store["subscribers"] = [self.owner]

    @property
    def enabled(self) -> bool:
        return bool(self.token)

    def save(self) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        tmp = self.path + ".tmp"
        data = dict(self.store)
        if self.owner is not None:
            data["subscribers"] = []      # شناسهٔ چت شخصی هرگز در فایل ذخیره نمی‌شود
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)
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
            print(f"[تلگرام خاموش]\n{text}\n")
            return False
        res, code = self._call("sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                                               "disable_web_page_preview": "true"})
        if code == 200:
            self.diag["sent_ok"] += 1
        else:
            self.diag["sent_fail"] += 1
            self.diag["fail_codes"].append(code)    # فقط کد خطا؛ توکن و شناسه هرگز ثبت نمی‌شوند
        if code == 403 and self.owner is None and chat_id in self.store["subscribers"]:
            self.store["subscribers"].remove(chat_id)   # چت مرده
            self.save()
        return code == 200

    def broadcast(self, text: str) -> int:
        if not self.store["subscribers"]:
            if not self.enabled:
                print(text + "\n")
            return 0
        return sum(self.send(c, text) for c in list(self.store["subscribers"]))

    def post_channel(self, text: str) -> bool:
        if not self.enabled or not self.channel:
            return False
        ok = self.send(self.channel, text)
        self.diag["channel_posts"] = self.diag.get("channel_posts", 0) + int(ok)
        return ok

    def maybe_channel_intro(self, btc_summary: dict | None, ledger_url: str) -> bool:
        """اولین بار که کانال تنظیم شد: معرفی کانال + وضعیت فعلی."""
        if not self.enabled or not self.channel or self.store.get("channel_intro") or not btc_summary:
            return False
        pos = "نگه‌داری بیت‌کوین" if btc_summary.get("position") == "BTC" else "نقد"
        text = _end([
            "👋 <b>به کانال صادق ماری خوش آمدید</b>",
            "اینجا فقط یک قانون ساده و آزموده‌شده دنبال می‌شود:",
            "بیت‌کوین بالای میانگین ۱۵۰روزه → نگه‌داری؛ زیر آن → نقد.",
            "",
            "این قانون در آزمون ۸ساله ریزش‌های کوچک‌تری از نگه‌داری سادهٔ بیت‌کوین داشت. ۶ ایدهٔ دیگر ما رد شدند "
            "و منتشر نمی‌شوند. هر تغییر وضعیت و یک گزارش هفتگی اینجا می‌آید، با برد و باخت.",
            "",
            f"وضعیت فعلی: {pos} — قیمت {fa(btc_summary.get('close'), 0)} — میانگین ۱۵۰روزه "
            f"{fa(btc_summary.get('sma150'), 0)}",
            "", f"🔍 دفتر ثبت: {ledger_url}", "", f"ℹ️ {CHANNEL_DISCLAIMER}"])
        if self.post_channel(text):
            self.store["channel_intro"] = True
            self.save()
            return True
        return False

    def maybe_weekly_channel(self, btc_summary: dict | None, ledger_url: str) -> bool:
        """هر دوشنبه بعد از ساعت ۱۰ تهران: گزارش شفاف هفتگی در کانال."""
        if not self.enabled or not self.channel or not btc_summary or not btc_summary.get("position"):
            return False
        now = datetime.now(TEHRAN)
        week = now.strftime("%G-W%V")
        if now.weekday() == 0 and now.hour >= 10 and self.store.get("last_weekly") != week:
            if self.post_channel(fmt_channel_weekly(btc_summary, ledger_url)):
                self.store["last_weekly"] = week
                self.save()
                return True
        return False

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
            if self.owner is not None and chat != self.owner:
                self.diag["ignored_other_chats"] += 1
                continue                  # حالت شخصی: فرمان غریبه‌ها پاسخ داده نمی‌شود
            cmd = text.split()[0].split("@")[0].lower()
            n += 1
            self.diag["commands"] += 1
            if cmd == "/start":
                if self.owner is None and chat not in self.store["subscribers"]:
                    self.store["subscribers"].append(chat)
                self.send(chat, "✅ این چت برای گزارش‌های خودکار ثبت شد.\n\n" + HELP)
            elif cmd == "/stop":
                if self.owner is None and chat in self.store["subscribers"]:
                    self.store["subscribers"].remove(chat)
                self.send(chat, _end(["دریافت گزارش خودکار لغو شد."]))
            elif cmd == "/report":
                self.send(chat, fmt_report(bot))
            elif cmd == "/trades":
                self.send(chat, fmt_trades(bot))
            elif cmd == "/hunt":
                self.send(chat, fmt_hunt(bot))
            elif cmd == "/btc":
                b = getattr(bot, "btc_summary", None)
                self.send(chat, _end(_btc_lines(b)[1:] or ["هنوز داده‌ای برای روند بیت‌کوین ثبت نشده."]))
            elif cmd == "/dca":
                self.send(chat, _end(fmt_dca(getattr(bot, "btc_summary", None))))
            elif cmd == "/daily":
                self.send(chat, fmt_daily_simple(bot))
            elif cmd == "/council":
                self.send(chat, COUNCIL)
            else:
                self.send(chat, HELP)
        self.save()
        return n

    def check(self) -> None:
        """تشخیص سلامت اتصال (برای گزارش اجرا) — بدون چاپ توکن یا شناسه."""
        self.diag["enabled"] = self.enabled
        self.diag["owner_mode"] = self.owner is not None
        if not self.enabled:
            return
        res, code = self._call("getMe", {})
        self.diag["token_ok"] = bool(code == 200 and res and res.get("ok"))
        if code != 200:
            self.diag["getme_code"] = code

    def maybe_hello(self, bot) -> bool:
        """اولین اجرای موفق پس از وصل‌شدن تلگرام: پیام تأیید اتصال + گزارش فعلی."""
        if not self.enabled or self.store.get("hello_sent") or not self.store["subscribers"]:
            return False
        if self.broadcast("✅ <b>ربات ماری به تلگرام شما وصل شد.</b>\n"
                          "از این به بعد هر ساعت بازار را بررسی می‌کند و رویدادها را همین‌جا می‌فرستد.\n\n"
                          + fmt_report(bot)) > 0:
            self.store["hello_sent"] = True
            self.save()
            return True
        return False

    def maybe_daily(self, bot, hour: int = 9) -> bool:
        if not self.enabled:
            return False                  # روز را «ارسال‌شده» علامت نزن وقتی تلگرام خاموش است
        now = datetime.now(TEHRAN)
        day = now.strftime("%Y-%m-%d")
        if now.hour >= hour and self.store.get("last_daily") != day:
            if self.broadcast(fmt_daily_simple(bot, monday=now.weekday() == 0)) > 0:
                self.store["last_daily"] = day
                self.save()
                return True
        return False
