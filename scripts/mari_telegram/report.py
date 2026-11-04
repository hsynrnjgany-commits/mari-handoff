#!/usr/bin/env python3
"""
MARI — گزارش‌ساز سادهٔ فارسی برای تلگرام (فرمان رسمی §۱-§۴)
همهٔ اعداد از فایل‌های واقعی همین لحظه خوانده می‌شوند؛ هیچ عدد ثابت/ساختگی نیست.
موارد بدون دادهٔ معتبر صریحاً «ثبت نشده» اعلام می‌شوند — هرگز حدس زده نمی‌شود.
اجرا: python3 scripts/mari_telegram/report.py --type short|hunt|paper|daily [--send]
READ ONLY | PAPER ONLY | NO LIVE ORDERS — توکن هرگز چاپ نمی‌شود.
"""
import argparse
import glob
import json
import os
import statistics
import sys
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone, timedelta

CFG = "data/telegram-config.json"
SENDLOG = "scripts/mari_telegram/send-log.jsonl"


def load_telegram_config():
    """کانفیگ تلگرام: فایل مرجع است؛ در نبودِ توکن، پشتیبان MARI_TELEGRAM_TOKEN از env یا .env.
    درس CRON-INCIDENT (2026-10-31): فایل gitignored در ریست ساندباکس حذف می‌شود — env زنده می‌ماند.
    توکن هرگز چاپ/لاگ نمی‌شود."""
    cfg = {}
    if os.path.exists(CFG):
        try:
            cfg = json.load(open(CFG))
        except Exception:
            cfg = {}
    if not cfg.get("token"):
        tok = os.environ.get("MARI_TELEGRAM_TOKEN", "").strip()
        if not tok:
            envp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".env")
            try:
                with open(envp, encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if line.startswith("MARI_TELEGRAM_TOKEN="):
                            tok = line.split("=", 1)[1].strip().strip('"').strip("'")
                            break
            except OSError:
                pass
        if tok:
            cfg["token"] = tok
    return cfg


LAST = "scripts/m140_tick_vault/last_cycle.json"
DEC = "scripts/mari_hunt01/store/decisions.jsonl"
REJ = "scripts/mari_hunt01/store/rejects.jsonl"
UNIVERSE = "scripts/mari_hunt01/universe.json"
COV_STATE = "scripts/mari_hunt01/store/toobit_sweep_state.json"
DERIV = "scripts/mari_deriv/store/deriv.jsonl"   # لایهٔ مشتقهٔ پژوهشی (DERIV-01) — بر تصمیم اثر ندارد
PAPER = "data/paper-trades.json"
BREAKEVEN_EPS = 1e-9  # همان تلورانس computeStats (src/lib/paper/stats.ts) — سربه‌سر مهندسی‌شده جدا می‌شود
TEHRAN = timezone(timedelta(hours=3, minutes=30))  # UTC+3:30 (ایران، بدون DST از 2022)
API = "https://api.telegram.org"


def fa(n, digits=2):
    if n is None or (isinstance(n, float) and not n == n):
        return "نامشخص"
    if isinstance(n, int) or (isinstance(n, float) and n == int(n) and digits == 0):
        return f"{int(n):,}".translate(str.maketrans("0123456789,", "۰۱۲۳۴۵۶۷۸۹،"))
    return f"{n:,.{digits}f}".translate(str.maketrans("0123456789,.", "۰۱۲۳۴۵۶۷۸۹،٫"))


def now_utc():
    return datetime.now(timezone.utc)


def tehran_today():
    return now_utc().astimezone(TEHRAN).strftime("%Y-%m-%d")


def load_jsonl(path):
    out = []
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
    return out


def api_call(token, method, payload, timeout=20):
    url = f"{API}/bot{token}/{method}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, {"raw": e.read().decode(errors="replace").replace(token, "***")[:200]}
    except Exception as e:
        return None, {"raw": f"{type(e).__name__}: {e}"[:200]}


def log_send(row):
    os.makedirs(os.path.dirname(SENDLOG), exist_ok=True)
    with open(SENDLOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def last_success():
    rows = load_jsonl(SENDLOG)
    ok = [r for r in rows if r.get("delivered")]
    return ok[-1] if ok else None


def chunk_text(text, limit=3800):
    """قطعه‌بندی در مرز خط — سقف تلگرام ۴۰۹۶ نویسه."""
    if len(text) <= limit:
        return [text]
    out, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > limit:
            out.append(cur)
            cur = line
        else:
            cur = f"{cur}\n{line}" if cur else line
    if cur:
        out.append(cur)
    return out


def send_all(title, text, rtype):
    """ارسال با تکه‌بندی؛ دیکشنری نتیجه برمی‌گرداند (چاپ با تصمیم caller)."""
    cfg = load_telegram_config()
    tok = cfg.get("token", "")
    chats = cfg.get("chatIds", [])
    if not tok or not chats:
        return {"ok": False, "results": [], "message_ids": [],
                "why": "کانفیگ تلگرام ناقص"}
    parts = chunk_text(f"{title}\n{text}")
    results, all_ok = [], True
    for cid in chats:
        for i, part in enumerate(parts, 1):
            suffix = f"\n(بخش {fa(i, 0)} از {fa(len(parts), 0)})" if len(parts) > 1 else ""
            st, resp = api_call(tok, "sendMessage", {"chat_id": cid, "text": part + suffix})
            mid = resp.get("result", {}).get("message_id") if st == 200 else None
            ok = st == 200 and resp.get("ok") and mid
            all_ok = all_ok and bool(ok)
            results.append({"chat_id": cid, "part": i, "http": st, "message_id": mid,
                            "why": None if ok else str(resp.get("raw", ""))[:150]})
            log_send({"ts_utc": now_utc().isoformat(), "type": rtype, "chat_id": cid,
                      "part": f"{i}/{len(parts)}", "http": st, "api_ok": resp.get("ok"),
                      "message_id": mid, "delivered": bool(ok),
                      "error": None if ok else str(resp.get("raw", ""))[:150]})
    return {"ok": all_ok, "results": results,
            "message_ids": [r["message_id"] for r in results if r["message_id"]]}


# ---------- بخش ۱: اسکن جهانی (اعداد واقعی از vault و hunt store) ----------
def toobit_coverage_numbers(now=None):
    """پوشش تووبیت (COVERAGE-01 بند ۸): «X از N» + گارد کهنگی universe.
    universe قدیمی‌تر از 25 ساعت → نامعتبر — داده کهنه. نبودِ داده → UNAVAILABLE (هرگز حدس)."""
    try:
        u = json.load(open(UNIVERSE, encoding="utf-8"))
        n = u.get("count") or len(u.get("symbols") or [])
        age_h = ((now or now_utc()) - datetime.fromisoformat(u["refreshed_utc"])).total_seconds() / 3600
        covered = cur = None
        if os.path.exists(COV_STATE):
            st = json.load(open(COV_STATE, encoding="utf-8"))
            covered = st.get("covered_count", len(st.get("covered_symbols") or []))
            cur = st.get("cursor")
        return {"n": n, "covered": covered, "cursor": cur,
                "stale": age_h > 25.0, "available": True}
    except Exception:
        return {"available": False}


def deriv_research_numbers(now=None):
    """مشتقه (پژوهشی) — DERIV-01 بند ۶: سن داده، پوشش نماد، ۳ نماد با بیشترین تغییر OI.
    دادهٔ قدیمی‌تر از ۳ ساعت → نامعتبر — داده کهنه (همان الگوی گارد گزارش‌ها).
    فقط آخرین اجرای موجود در deriv.jsonl ملاک است؛ نبودِ داده → UNAVAILABLE (هرگز حدس)."""
    try:
        rows = load_jsonl(DERIV)
        if not rows:
            return {"available": False}
        last_run = rows[-1].get("run_id")
        cur = [r for r in rows if r.get("run_id") == last_run]
        t0 = ts_of(cur[0].get("ts_utc"))
        if t0 is None:
            return {"available": False}
        age_h = ((now or now_utc()) - t0).total_seconds() / 3600.0
        top = sorted((r for r in cur if r.get("oi_delta_pct") is not None),
                     key=lambda r: -abs(r["oi_delta_pct"]))[:3]
        return {"available": True, "age_h": round(age_h, 1),
                "stale": age_h > 3.0, "run_id": last_run,
                "n_symbols": len(cur),
                "covered": sum(1 for r in cur if r.get("oi") is not None),
                "top3": [(r.get("base"), r["oi_delta_pct"]) for r in top]}
    except Exception:
        return {"available": False}


def ts_of(x):
    try:
        return datetime.fromisoformat(str(x).replace("Z", "+00:00"))
    except Exception:
        return None


def scan_numbers():
    """اعداد واقعی اسکن — نمادهای یکتا، بدون شمارش تکراری."""
    cyc = json.load(open(LAST)) if os.path.exists(LAST) else {}
    scanned = cyc.get("matched_bases")            # نمادهای یکتای تطبیق‌یافته در همین چرخه
    rows_n = cyc.get("normalized_rows")
    movers = sorted({t.get("base") for t in (cyc.get("top20") or []) if t.get("base")})
    pos_tob = (cyc.get("stats") or {}).get("n_positive_tob50")
    today = tehran_today()
    dec = [d for d in load_jsonl(DEC)
           if d.get("type", "decision") == "decision"
           and d.get("decision_ts_utc", "")[:10] == now_utc().strftime("%Y-%m-%d")]
    wt = [d for d in dec if d.get("decision") == "WOULD_TRADE"]
    rej_today = [r for r in load_jsonl(REJ)
                 if r.get("cycle_ts", "")[:10] == now_utc().strftime("%Y-%m-%d")]
    return {
        "cycle_ts": cyc.get("cycle_ts"), "scanned": scanned, "rows": rows_n,
        "movers": movers, "pos_tob": pos_tob,
        "eagle_evaluated": len(dec), "ready": wt,
        "unfit": len(rej_today),
        "unfit_reasons": dict(Counter(r.get("reason", "?").split("(")[0] for r in rej_today)),
        "toobit": toobit_coverage_numbers(),
    }


def fmt_deriv_line():
    """یک خط کوتاه مشتقه (پژوهشی) برای گزارش شکار جهانی — DERIV-01 بند ۶."""
    dv = deriv_research_numbers()
    if not dv.get("available"):
        return "• مشتقه (پژوهشی): UNAVAILABLE"
    mark = " ⚠️ نامعتبر — داده کهنه (>۳h)" if dv.get("stale") else " ✓ تازه"
    top = "، ".join(
        f"{b} {('+' if p >= 0 else '')}{fa(p, 2)}٪" for b, p in (dv.get("top3") or [])
    ) or "هنوز دو اجرا برای ΔOI نیست"
    return (f"• مشتقه (پژوهشی): سن داده {fa(dv['age_h'], 1)}h{mark} · "
            f"پوشش {fa(dv.get('covered', 0), 0)} از {fa(dv.get('n_symbols', 0), 0)} نماد · "
            f"بیشترین |ΔOI| بین دو اجرا: {top}")


def fmt_scan(s):
    cyc = s["cycle_ts"] or "؟"
    tb = s.get("toobit") or {}
    if tb.get("available") and tb.get("covered") is not None:
        tb_mark = " ⚠️ نامعتبر — داده کهنه" if tb.get("stale") else ""
        tb_line = f"• پوشش تووبیت (COVERAGE-01): {fa(tb['covered'], 0)} از {fa(tb['n'], 0)} نماد USDT فعال{tb_mark}"
    else:
        tb_line = "• پوشش تووبیت (COVERAGE-01): UNAVAILABLE"
    lines = [
        f"• نمادهای یکتای بررسی‌شده در اسکن: {fa(s['scanned'], 0)}",
        f"• جفت‌های دارای اختلاف قیمت بین‌صرافی (متحرک): {fa(len(s['movers']), 0)}",
        f"• جفت‌های با اسپرد مثبت TOB≥۵۰$: {fa(s['pos_tob'], 0)}",
        f"• شناسایی‌شده توسط عقاب (ارزیابی خالص امروز): {fa(s['eagle_evaluated'], 0)}",
        f"• آماده شکار (WOULD_TRADE امروز): {fa(len(s['ready']), 0)}",
        f"• شرایط نامناسب (رد فیلتری امروز): {fa(s['unfit'], 0)}",
        tb_line,
        f"• منبع: m140-tickvault-v1 + toobit-coverage-v1 · چرخهٔ {cyc[:19]}",
        fmt_deriv_line(),
    ]
    return "\n".join(lines)


# ---------- بخش ۲: جزئیات آماده‌شکار ----------
def fmt_hunt_detail(s):
    wt = s["ready"]
    if not wt:
        return ("• امروز هیچ فرصت «آماده شکار» ثبت نشده.\n"
                "• نتیجهٔ منفی هم نتیجهٔ واقعی است — بدون جعل فرصت.")
    lines = []
    for d in sorted(wt, key=lambda x: -(x.get("net_pct") or 0)):
        lines.append(
            f"«{d.get('base')}» — خرید {d.get('buy_ex')} → فروش {d.get('sell_ex')} · چرخهٔ {d.get('cycle_ts','')[11:19]}Z\n"
            f"  قیمت خرید: {fa(d.get('buy_price'), 8)} · قیمت فروش: {fa(d.get('sell_price'), 8)}\n"
            f"  سود ناخالص: {fa(d.get('gross_pct'))}٪ · سود خالص پس از هزینه: {fa(d.get('net_pct'))}٪\n"
            f"  روش قیمت‌گذاری: {'تایید عمق L2' if d.get('method') == 'l2_vwap_100' else 'برآورد TOB (بدون L2 — اعتبار کمتر)'}\n"
            f"  حد ضرر/هدف: برای سفر همزمان دوسویه معنا ندارد (خروج همان لحظه) — مطابق رکورد\n"
            f"  وضعیت: آماده شکار (PAPER) · اندازه: {fa(d.get('size_usdt'), 0)} دلار آزمایشی"
        )
    return "\n".join(lines)


# ---------- بخش ۳: معاملات آزمایشی ----------
def paper_report(only_today=False):
    d = json.load(open(PAPER))
    tr = d.get("trades", [])
    if only_today:
        today0 = datetime.now(TEHRAN).replace(hour=0, minute=0, second=0, microsecond=0)
        tr = [t for t in tr if t.get("exitTime") and
              datetime.fromtimestamp(t["exitTime"] / 1000, TEHRAN) >= today0]
    closed = [t for t in tr if t.get("status") == "CLOSED"]
    open_ = [t for t in tr if t.get("status") != "CLOSED"]
    # طبقه‌بندی با همان تلورانس computeStats — باقیماندهٔ ممیز شناور (±1e-14) دیگر برد/باخت کاذب نمی‌سازد
    wins = [t for t in closed if (t.get("realizedPnlPct") or 0) > BREAKEVEN_EPS]
    losses = [t for t in closed if (t.get("realizedPnlPct") or 0) < -BREAKEVEN_EPS]
    be = [t for t in closed if abs(t.get("realizedPnlPct") or 0) <= BREAKEVEN_EPS]
    pnl_usd = sum((t.get("realizedPnlPct") or 0) / 100 * (t.get("sizeUsd") or 0) for t in closed)
    pnl_pct = sum(t.get("realizedPnlPct") or 0 for t in closed)
    # Max Drawdown از منحنی سود تحقق‌یافته به ترتیب خروج
    curve, acc, maxdd = [], 0.0, 0.0
    for t in sorted(closed, key=lambda x: x.get("exitTime") or 0):
        acc += (t.get("realizedPnlPct") or 0) / 100 * (t.get("sizeUsd") or 0)
        curve.append(acc)
        peak = max(curve)
        maxdd = max(maxdd, peak - acc)
    wr = (100 * len(wins) / (len(wins) + len(losses))) if (wins or losses) else None
    best = max(closed, key=lambda t: t.get("realizedPnlPct") or 0) if closed else None
    worst = min(closed, key=lambda t: t.get("realizedPnlPct") or 0) if closed else None
    # PF دلاری و جمع ناخالص دلاری — سهم سربه‌سرها در دلار عملاً صفر است ولی برای صداقت جدا حساب می‌شود
    gp_usd = sum((t.get("realizedPnlPct") or 0) / 100 * (t.get("sizeUsd") or 0) for t in wins)
    gl_usd = sum((t.get("realizedPnlPct") or 0) / 100 * (t.get("sizeUsd") or 0) for t in losses)
    pf_usd = (gp_usd / abs(gl_usd)) if (wins or losses) and abs(gl_usd) > 1e-12 else None
    return {
        "n": len(tr), "closed": len(closed), "open": len(open_),
        "wins": len(wins), "losses": len(losses), "be": len(be),
        "wr": wr, "gp_usd": gp_usd, "gl_usd": gl_usd, "pf_usd": pf_usd,
        "pnl_usd": pnl_usd, "pnl_pct": pnl_pct, "maxdd": maxdd,
        "best": best, "worst": worst,
        "paused": d.get("paused"), "pause_reason": d.get("autoPauseReason"),
    }


def fmt_paper(p, scope):
    lines = [f"• دامنه: {scope}"]
    lines.append(f"• تعداد معاملات: {fa(p['n'], 0)} (بسته: {fa(p['closed'], 0)} · باز: {fa(p['open'], 0)})")
    lines.append(f"• سودده: {fa(p['wins'], 0)} · زیان‌ده: {fa(p['losses'], 0)} · سر‌به‌سر: {fa(p['be'], 0)}")
    lines.append(f"• درصد موفقیت (بدون سربه‌سر): {fa(p['wr'], 1) + '٪' if p['wr'] is not None else 'نامشخص (برد/باخت بسته‌شده نیست)'}")
    lines.append(f"• سربه‌سر (خروج روی مرز کارمزد ۰٫۱٪): {fa(p['be'], 0)}")
    lines.append(f"• PF دلاری: {fa(p['pf_usd'], 3) if p['pf_usd'] is not None else 'نامشخص'} · سود ناخالص: {fa(p['gp_usd'])}$ · زیان ناخالص: {fa(p['gl_usd'])}$")
    lines.append(f"• مجموع سود/زیان تحقق‌یافته: {fa(p['pnl_usd'])} دلار ({fa(p['pnl_pct'])}٪ انباشته)")
    lines.append(f"• بیشترین افت سرمایه (Drawdown تحقق‌یافته): {fa(p['maxdd'])} دلار")
    if p["best"]:
        lines.append(f"• بهترین: {p['best'].get('symbol')} {fa(p['best'].get('realizedPnlPct'))}٪")
    if p["worst"]:
        lines.append(f"• بدترین: {p['worst'].get('symbol')} {fa(p['worst'].get('realizedPnlPct'))}٪")
    lines.append("• کارمزد و لغزش: در رکوردها ثبت نشده — گزارش نمی‌شود (بدون دادهٔ معتبر)")
    if p["open"]:
        lines.append("• سود/زیان باز از تحقق‌یافته جدا است و در عدد بالا نیامده")
    if p["paused"]:
        lines.append(f"• وضعیت: ربات PAPER متوقف است ({p.get('pause_reason') or 'دلیل ثبت‌شده'})")
    return "\n".join(lines)


# ---------- بخش ۴: گزارش روزانه ----------
def scan_age_line():
    """سن دادهٔ اسکن از cycle_ts (پادزهر صفرِ روی دادهٔ کهنه — فرمان رییس)."""
    try:
        cyc = json.load(open(LAST))
        ts = str(cyc.get("cycle_ts", "")).strip()
        if ts:
            age_h = round((now_utc() - datetime.fromisoformat(
                ts.replace("Z", "+00:00"))).total_seconds() / 3600, 1)
            mark = "✓ تازه" if age_h <= 3.0 else "⚠️ کهنه (حد ۳h) → نامعتبر"
            return f"• سن دادهٔ اسکن: {fa(age_h, 1)}h {mark}"
    except Exception:
        pass
    return "• سن دادهٔ اسکن: MISSING"


def fmt_daily():
    s = scan_numbers()
    p_all = paper_report(False)
    p_today = paper_report(True)
    best = max(s["ready"], key=lambda x: x.get("net_pct") or 0) if s["ready"] else None
    ls = last_success()
    lines = [
        f"• کل بازار بررسی‌شده (نماد یکتا): {fa(s['scanned'], 0)}",
        scan_age_line(),
        f"• فرصت‌های شناسایی‌شده (ارزیابی خالص): {fa(s['eagle_evaluated'], 0)}",
        f"• فرصت‌های تأییدشده (آماده شکار): {fa(len(s['ready']), 0)}",
        f"• معاملات آزمایشی امروز (بسته‌شده): {fa(p_today['closed'], 0)}",
        f"• سود/زیان امروز: {fa(p_today['pnl_usd'])} دلار",
        f"• بهترین شکار امروز: " + (f"{best.get('base')} خالص {fa(best.get('net_pct'))}٪" if best else "نداشت"),
        f"• بدترین عملکرد امروز: " + (f"{p_today['worst'].get('symbol')} {fa(p_today['worst'].get('realizedPnlPct'))}٪" if p_today["worst"] else "نداشت"),
        f"• وضعیت کلی بازار: {('اسپردبین‌صرافی فعال — ' + fa(len(s['movers']), 0) + ' جفت متحرک') if s['movers'] else 'آرام'}",
        f"• وضعیت عقاب (شکارچی آربیتراژ): {'فعال — ' + fa(len(s['ready']), 0) + ' فرصت معتبر امروز'}" if s["ready"] else "• وضعیت عقاب: فعال — امروز فرصت بالای آستانه نداشت",
        f"• آخرین ارسال موفق تلگرام: {ls['ts_utc'][:19] if ls else 'هنوز ثبت نشده'}",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--type", required=True,
                    choices=["short", "hunt", "paper", "daily", "all"])
    ap.add_argument("--send", action="store_true")
    a = ap.parse_args()
    s = scan_numbers()
    t = now_utc().astimezone(TEHRAN).strftime("%Y-%m-%d %H:%M")
    FOOT = f"\n• زمان گزارش (تهران): {t}\n• READ ONLY | PAPER ONLY | NO LIVE ORDERS"

    # — حالت تلفیقی: دو گزارش با یک دستور — ایجنت فقط اجرا می‌کند —
    if a.type == "all":
        p_full = paper_report(False)
        daily_t = "🏆 نتیجهٔ نهایی شکار امروز MARI"
        daily_x = fmt_daily() + FOOT
        paper_t = "💼 گزارش معاملات آزمایشی MARI"
        paper_x = fmt_paper(p_full, f"کل تاریخ PAPER ({fa(p_full['n'], 0)} رکورد واقعی)") + FOOT
        if not a.send:
            print(f"{daily_t}\n{daily_x}")
            print("— — —")
            print(f"{paper_t}\n{paper_x}")
            print(json.dumps({"type": "all", "outcome": "DRY_RUN"}, ensure_ascii=False))
            return 0
        d = send_all(daily_t, daily_x, "daily")
        p = send_all(paper_t, paper_x, "paper")
        out = {"type": "all", "ok": bool(d["ok"] and p["ok"]),
               "daily": {"ok": d["ok"], "message_ids": d["message_ids"], "why": d.get("why")},
               "paper": {"ok": p["ok"], "message_ids": p["message_ids"], "why": p.get("why")}}
        print(json.dumps(out, ensure_ascii=False))
        return 0 if out["ok"] else 1

    if a.type == "short":
        detail = fmt_hunt_detail(s)
        if len(detail) > 600:
            detail = detail[:600].rsplit("\n", 1)[0] + "\n  … (ادامه در گزارش کامل شکار)"
        title, text = "🌍 گزارش شکار جهانی MARI", fmt_scan(s) + "\n" + detail
    elif a.type == "hunt":
        title, text = "🎯 فرصت‌های آماده شکار MARI", fmt_hunt_detail(s)
    elif a.type == "paper":
        p_full = paper_report(False)
        title, text = "💼 گزارش معاملات آزمایشی MARI", fmt_paper(
            p_full, f"کل تاریخ PAPER ({fa(p_full['n'], 0)} رکورد واقعی)")
    else:
        title, text = "🏆 نتیجهٔ نهایی شکار امروز MARI", fmt_daily()

    text = f"{text}{FOOT}"

    if a.send:
        out = send_all(title, text, a.type)
        print(json.dumps(out, ensure_ascii=False))
        return 0 if out["ok"] else 1
    print(f"{title}\n{text}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
