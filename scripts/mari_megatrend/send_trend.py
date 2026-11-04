#!/usr/bin/env python3
# HUNT-02 — ارسال گزارش فارسی تلگرام (فقط ارسال گزارش؛ بدون هیچ سفارشی)
import json, sys, urllib.request, urllib.parse, os

HERE = os.path.dirname(os.path.abspath(__file__))
LIVE = sorted([f for f in os.listdir(os.path.join(HERE, "out")) if f.startswith("hunt02_live_")])[-1]
D = json.load(open(os.path.join(HERE, "out", LIVE)))
CFG = json.load(open("/home/z/my-project/data/telegram-config.json"))
TOKEN = CFG["token"]
CHAT = CFG["chatIds"][0]

def api(method, **kw):
    data = urllib.parse.urlencode(kw).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/{method}", data=data)
    with urllib.request.urlopen(req, timeout=20) as r:
        out = json.loads(r.read().decode())
    assert out.get("ok") is True, out
    return out

def build():
    b = D["btc"]; c = D["growth_calibration"]; lv = c["levels"]
    from collections import Counter
    cnt = Counter(r["state"] for r in D["rows"])
    L = []
    L.append("MARI — MEGA-TREND HUNTER (HUNT-02) — گزارش زنده")
    L.append(f"زمان: {D['generated_utc']} · قفل: READ ONLY | PAPER ONLY | NO LIVE ORDERS")
    L.append(f"داده: Binance عمومی · یونیورس {D['universe_size']} جفت USDT · نقدشونده بررسی‌شده: {D['ranked_liquid']} · تحلیل عمق: 40 نماد برتر")
    L.append(f"BTC: ${b['close']:,.0f} · {'بالای' if b['above_ema200'] else 'زیر'} EMA200 (${b['ema200']:,.0f}) · 7d {b['chg_7d_pct']}% · 30d {b['chg_30d_pct']}% · رژیم: {b['regime']}")
    L.append(f"ساختار بازار: سهم وضعیت‌های سالم {D['breadth']['watch_state_pct']}% از {D['breadth']['n_valid']} نماد معتبر")
    L.append("وضعیت‌ها: " + " · ".join(f"{k}={v}" for k, v in sorted(cnt.items())))
    L.append("")
    L.append("— کاندیدهای روند (توصیف، نه مجوز ورود) —")
    for r in D["rows"]:
        if r["state"] in ("TREND CONFIRMED", "TREND RUNNER", "EARLY ACCUMULATION", "BREAKOUT WATCH"):
            peg = r["symbol"] in ("RLUSDUSDT", "UUSDT")
            note = " ⚠ دارایی پگ‌شده — طبقه‌بندی روند برای آن بی‌معناست" if peg else ""
            L.append(f"{r['symbol']}: {r['state']}{note}")
            L.append(f"  قیمت ${r['close']:,.6g} · قدرت روند: RS7 vs BTC {r.get('rs7_vs_btc')}% · RSI {r.get('rsi14')} · حجم {r.get('vol_anom_x')}× میانگین 30d")
            L.append(f"  ساختار: HH={r['hh']} HL={r['hl']} · استاپ ساختاری {r.get('structural_stop')} · Trailing(3×ATR) {r.get('trail_stop')} · ریسک تا استاپ {r.get('risk_to_stop_pct')}%")
            L.append(f"  اهداف فاصله: +20%=${r['targets']['+20%']:,.6g} · +50%=${r['targets']['+50%']:,.6g} · +100%=${r['targets']['+100%']:,.6g} · +200%=${r['targets']['+200%']:,.6g}")
            L.append(f"  فاندینگ فیوچرز: {r.get('funding_pct')}% · تصمیم: WATCH (فقط پایش کاغذی)")
    L.append("")
    L.append("— هشدار خروج —")
    L.append(", ".join(r["symbol"] for r in D["rows"] if r["state"] == "EXIT WARNING"))
    L.append("")
    L.append("— احتمالات اهداف رشد (فرکانس تاریخی واقعی 118 رویداد روند تأییدشده، 2024→2026، CI وایلسون 95%) —")
    L.append("سطح · احتمال رسیدن در 90 روز [CI] · در 180 روز [CI]")
    for k in ("+20%", "+50%", "+100%", "+200%", "+300%", "+500%"):
        v = lv[k]
        L.append(f"{k}: {v['p90d']*100:.1f}% {tuple(x*100 for x in v['ci90d'])} · {v['p180d']*100:.1f}% {tuple(x*100 for x in v['ci180d'])}")
    L.append("هشدار: توصیف فرکانس گذشته است، نه پیش‌بینی تضمینی؛ نمونهٔ سطح +300/+500 کم است و CI پهن دارد.")
    L.append(f"تفکیک رژیم BTC: رویداد OFF=0 → مقایسهٔ بین‌رژیمی برای رویدادها ناممکن (فقط RISK_ON).")
    L.append("")
    L.append("— شواهد منفی ثبت‌شده (ممیزی M143→M153) —")
    L.append("1) هیچ مدل خروجی هر ۳ گیت ارتقا را نگذراند (X_R و X_ST هر ۳ گیت را رد شدند)")
    L.append("2) لبه در هزینهٔ 25→30bp می‌میرد (NEW-A در 30bp منفی می‌شود)")
    L.append("3) 74.6% سود NEW-A از 10 معاملهٔ برتر → تمرکز شدید ریسک")
    L.append("4) OOS خالص M152: پایه −$124.14 (PF 0.927) — منفی")
    L.append("5) خروج پله‌ای (Partial+Runner) بدتر از ATR Trail — FDR-تأیید (F5)")
    L.append("6) هیچ ادعای «سود مطلق» پس از BH-FDR(0.10) زنده نمی‌ماند (F2,F4,F6,F7,F8)")
    L.append("7) Open Interest زنده: UNAVAILABLE (endpoint در دسترس نبود)")
    L.append("8) Sector rotation: UNAVAILABLE (دیتاست سکتور MISSING)")
    L.append("")
    L.append("— حکم H-HUNT-03 —")
    L.append("PARTIALLY VERIFIED: زیرساخت تشخیص روند راستی‌آزمایی‌شده و اکنون زنده اجرا شد؛")
    L.append("اما «سیگنال جهت‌دار سودآور OOS» هنوز اثبات نشده (صفر ادعای مطلق زنده پس از FDR).")
    L.append("شعار: BREAK THE ASSUMPTIONS — VERIFY THE EVIDENCE — NEVER FAKE SUCCESS")
    return "\n".join(L)

txt = build()
ok = 0
for i in range(0, len(txt), 3500):
    part = txt[i:i + 3500]
    out = api("sendMessage", chat_id=CHAT, text=part)
    ok += 1
print(json.dumps({"sent_parts": ok, "len": len(txt), "source": LIVE}, ensure_ascii=False))
