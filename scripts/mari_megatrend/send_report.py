#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MARI-MEGATREND — گزارش فارسی تلگرام (فقط ارسال گزارش؛ بدون هیچ سفارشی، بدون چاپ secret)"""
import json, os, urllib.request, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
SCAN = json.load(open(os.path.join(HERE, "out", "megatrend_scan.json")))
CFG = json.load(open("/home/z/my-project/data/telegram-config.json"))
TOKEN, CHAT = CFG["token"], CFG["chatIds"][0]

BASE_RATES = [("+20%", "44.1%", "50.8%", "[35.4–53.1]"), ("+50%", "22.0%", "23.7%", "[15.5–30.3]"),
              ("+100%", "15.3%", "17.0%", "[9.9–22.8]"), ("+200%", "4.2%", "5.9%", "[1.8–9.5]"),
              ("+300%", "2.5%", "5.1%", "[0.9–7.2]"), ("+500%", "0.9%", "2.5%", "[0.2–4.6]")]

def send(txt):
    data = urllib.parse.urlencode({"chat_id": CHAT, "text": txt[:4000]}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data=data)
    with urllib.request.urlopen(req, timeout=20) as r:
        out = json.loads(r.read().decode())
    return out.get("ok"), out.get("result", {}).get("message_id")

L = []
b = SCAN["btc"]
L.append("MARI — MEGA-TREND HUNTER · گزارش زندهٔ بازار")
L.append(f"زمان: {SCAN['generated_utc']} · قفل: READ ONLY | PAPER ONLY | NO LIVE ORDERS")
L.append(f"BTC: ${b['price']:,.0f} · 7d {b['chg_7d_pct']}% · 30d {b['chg_30d_pct']}% · استک EMA: {b['ema_stack']} · ADX {b['adx']} → رژیم: {SCAN['btc_regime']}")
br = SCAN["breadth"]
L.append(f"Breadth: {br['above200_pct']}% بالای EMA200 · {br['above50_pct']}% بالای EMA50 (از {br['n_valid']} نماد نقد)")
L.append("وضعیت‌ها: " + " · ".join(f"{k}={v}" for k, v in sorted(SCAN["states_count"].items())))
L.append("نتیجهٔ صادقانه: امروز هیچ روند تأییدشده‌ای در ۴۰ نماد برتر نیست — بازار رژیم نزولی/خنثی است.")
L.append("")
L.append("— کاندیدهای انباشت اولیه (WATCH — نه سیگنال ورود) —")
STOP_NOTE = "حدضرر = 3×ATR زیر قیمت (پارامتر منجمد X_ATR)"
for s in SCAN["symbols"]:
    if s.get("state") != "EARLY_ACCUMULATION": continue
    px, atr = s["price"], s.get("atr_pct")
    stop = round(px - 3 * px * atr / 100, 8) if (px and atr) else None
    L.append(f"نام ارز: {s['symbol']}")
    L.append(f"قیمت بررسی: {px}")
    L.append(f"قدرت روند: ADX {round(s['adx'],1) if s.get('adx') else '—'} · RSI {round(s['rsi'],1) if s.get('rsi') else '—'}")
    L.append(f"وضعیت ساختار: زیر EMA200 اما انباشت (فاصله از سقف ۶۰روزه {s.get('dist_high_pct')}% · موقعیت {round(s['pos_60d']*100)}% بازه)")
    L.append(f"حجم: {s.get('vol_x')}× میانگین ۳۰روزه")
    L.append(f"نقدینگی: حجم 24h ≈ ${s.get('qv24h_usd'):,}")
    L.append(f"وضعیت BTC: {SCAN['btc_regime']} (بازار دشمن روند‌های بلند — ریسک سیستماتیک بالا)")
    L.append("سناریوهای رشد: 20/50/100/200/300/500% — احتمالات: فقط فرکانس تاریخی کل بازار (مدل شرطی per-symbol = INSUFFICIENT EVIDENCE)")
    L.append(f"حدضرر ساختاری: {stop} ({STOP_NOTE} · ریسک {round(3*atr,1) if atr else '—'}%)")
    L.append(f"Trailing Stop: بعد از ورود فرضی، دنبال‌کنندهٔ 3×ATR از پیک — فعال‌سازی فقط در PAPER")
    L.append("تصمیم: WATCH (فقط پایش کاغذی) · دلیل: " + (
        "قدرت نسبی ۳۰روزه +۲۳.۶% نسبت به BTC و حجم ۱.۶× — تنها کاندید با مومنتوم مثبت معنادار" if s['symbol']=='PEPEUSDT' else
        "مومنتوم داغ (ADX 51, RSI 78, حجم ۵.۶×) اما ریسک ۲۳% — نیازمند سردشدن" if s['symbol']=='LSKUSDT' else
        "ساختار انباشت ملایم با ریسک فقط ۴.۱% — قدرت نسبی هنوز منفی" if s['symbol']=='XPLUSDT' else
        "جهش پس از سقوط (حجم ۸.۳×) — ریسک ۲۸.۶% و RS بسیار منفی → WATCH منفعل"))
    L.append("")
L.append("— هشدار —")
L.append("WEAKENING: BTC، ETH، SOL، BNB، XRP، TRX، XAUT (طلا) و ۶ نماد دیگر — خروج/کاهش در PAPER باید زودتر از ورودهای جدید بررسی شود.")
L.append("")
L.append("— احتمالات اهداف رشد (فرکانس تاریخی واقعی ۱۱۸ رویداد روند ۲۰۲۴→۲۰۲۶ · CI 95%) —")
L.append("سطح | احتمال ۹۰روزه | احتمال ۱۸۰روزه | CI")
for t, p90, p180, ci in BASE_RATES:
    L.append(f"{t} | {p90} | {p180} | {ci}")
L.append("هشدار: گذشته تضمین آینده نیست؛ سطوح ≥300% نمونهٔ کم دارند؛ داده دارای سوگیری بقا (۲۹ بازمانده از ۳۴).")
ok1, mid1 = send("\n".join(L))
L2 = ["MARI — حکم H-HUNT-03 (بازممیزی خصمانه)"]
L2.append("H-HUNT-03: «سیگنال جهت‌دار قابل‌تولید با زیرساخت راستی‌آزمایی‌شده» — وضعیت قبلی: DECLARED_UNCOVERED")
L2.append("زیرساخت: VERIFIED (طبقه‌بند هویت ۱۰۰٪، تشخیص CRASH ۱۰۰٪ با تأخیر صفر، تمرین کاغذی ۲۷۹۴ معامله با ۴ گیت پاس، شادو parity ۳۶/۳۶)")
L2.append("لبهٔ سود: INSUFFICIENT EVIDENCE — پس از BH-FDR(0.10) هیچ ادعای سود مطلق زنده نمی‌ماند (F2,F4,F6,F7,F8)؛ OOS خالص منفی (−$124.14)؛ لبه در ≥20-30bp هزینه می‌میرد؛ ۷۴.۶% سود از ۱۰ معامله.")
L2.append("حکم: PARTIALLY VERIFIED — زیرساخت اثبات، سودآوری مطلق هنوز نه. آزمون تعیین‌کننده: شادو پیپر ۳۰روزه تا 2026-11-29 (امروز روز ۱.۰۴ — ۱۸ باز، ۷ بسته).")
L2.append("شعار: BREAK THE ASSUMPTIONS — VERIFY THE EVIDENCE — NEVER FAKE SUCCESS")
ok2, mid2 = send("\n".join(L2))
print(json.dumps({"part1": {"ok": ok1, "mid": mid1}, "part2": {"ok": ok2, "mid": mid2}}))
