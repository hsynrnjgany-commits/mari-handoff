#!/usr/bin/env python3
"""
MARI — گزارش دوساعتهٔ M153-A (بازسازی‌شده 2026-10-31 با فرمان «ادامهٔ» رییس)
هرگز توکن چاپ نمی‌شود؛ هرگز عدد ساخته نمی‌شود؛ دادهٔ غایب = MISSING/UNAVAILABLE.
اجرای کرون: python3 scripts/mari_telegram/scheduled_2h.py --send
- از فایل‌های واقعی گزارش می‌سازد، با retry محدود می‌فرستد،
- job_state.json و heartbeat.json را به‌روز می‌کند، شکست را FAILED ثبت می‌کند،
- خروجی JSON با report_id و outcome چاپ می‌کند.
پچ 2026-11-04 (فرمان رییس): فیلد last_success_utc جدا نگه داشته می‌شود — اجرای FAILED آن را
پاک/بازنویسی نمی‌کند؛ پنجرهٔ گزارش: last_success_utc → آخرین ارسال موفق 2h در send-log → ۰۰:۰۰Z.
قفل ثابت: READ ONLY | PAPER ONLY | NO LIVE ORDERS
"""
import hashlib
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from report import (CFG, SENDLOG, TEHRAN, fa, api_call, log_send,  # noqa: E402
                    chunk_text, load_jsonl, load_telegram_config)

HERE = os.path.dirname(os.path.abspath(__file__))
JOB_STATE = os.path.join(HERE, "job_state.json")
HEARTBEAT = os.path.join(HERE, "heartbeat.json")
DEC = os.path.join(HERE, "..", "mari_hunt01", "store", "decisions.jsonl")
REJ = os.path.join(HERE, "..", "mari_hunt01", "store", "rejects.jsonl")
PAPER = os.path.join(HERE, "..", "..", "data", "paper-trades.json")
SHADOW = os.path.join(HERE, "..", "m144_adversarial", "out", "shadow", "state.json")
SCAN = os.path.join(HERE, "..", "mari_megatrend", "out", "megatrend_scan.json")
HEALTH_URL = "http://localhost:3000/api/health"
FUNDING_URL = "http://localhost:3000/api/market/funding?symbols=BTCUSDT,ETHUSDT"  # M154 — Funding Reality
BINANCE_PI = "https://fapi.binance.com/fapi/v1/premiumIndex?symbol="  # fallback مستقیم (عمومی، بدون کلید)
REFERENCE_DIGEST = "6d8b7beb6d5a6c01"
RETRIES = 3
RETRY_SLEEP = 3
# — پادزهر «صفرِ روی دادهٔ کهنه» (فرمان رییس 2026-11-01) —
# سن tick-vault از cycle_ts در last_cycle.json خوانده می‌شود (اصلاح فرمان رییس 2026-11-02):
# مسیر قدیمی data/tick-vault وجود خارجی ندارد و همیشه MISSING می‌ساخت.
TICKVAULT_LAST = os.path.join(HERE, "..", "m140_tick_vault", "last_cycle.json")
HUNT_MAX_AGE_H = 3.0    # حد تازگی tick-vault + تصمیمات شکار — سخت‌گیرانه‌تر به فرمان رییس 2026-11-02 (بود: 6.0)
SHADOW_MAX_AGE_H = 13.0 # ریتم ~۱۲ساعته + تحمل — بازگردانی به فرمان رییس 2026-11-04 (حد یکنواخت ۳h لغو شد)
MEGA_MAX_AGE_H = 26.0   # ریتم روزانه + تحمل — بازگردانی به فرمان رییس 2026-11-04 (حد یکنواخت ۳h لغو شد)


def data_ages():
    """سن دادهٔ هر منبع به ساعت (None = غایب). هیچ عدد ساختگی — فقط از فایل واقعی."""
    out = {}
    now = time.time()
    # tick-vault: از cycle_ts فایل واقعی last_cycle.json (خودِ چرخه این مهر را می‌نویسد)
    try:
        d = json.load(open(TICKVAULT_LAST))
        ts = str(d.get("cycle_ts", "")).strip()
        out["tickvault"] = round((now - datetime.fromisoformat(
            ts.replace("Z", "+00:00")).timestamp()) / 3600, 1) if ts else None
    except Exception:
        out["tickvault"] = None
    try:
        last = load_jsonl(DEC)[-1]
        out["hunt"] = round((now - datetime.fromisoformat(
            last["decision_ts_utc"].replace("Z", "+00:00")).timestamp()) / 3600, 1)
    except Exception:
        out["hunt"] = None
    try:
        d = json.load(open(SHADOW))
        out["shadow"] = round((now - d["last_run"] / 1000) / 3600, 1) if d.get("last_run") else None
    except Exception:
        out["shadow"] = None
    try:
        d = json.load(open(SCAN))
        out["megatrend"] = round((now - datetime.fromisoformat(
            d["generated_utc"].replace("Z", "+00:00")).timestamp()) / 3600, 1) if d.get("generated_utc") else None
    except Exception:
        out["megatrend"] = None
    return out


def age_line(name, age, limit):
    if age is None:
        return f"• {name}: MISSING"
    mark = (f"✓ تازه (حد {fa(limit,0)}h)" if age <= limit
            else f"⚠️ کهنه (حد {fa(limit,0)}h) → نامعتبر")
    return f"• {name}: {fa(age,1)}h {mark}"


def now_utc():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat()


def dashboard_check():
    """وارسی سلامت داشبورد — فقط GET عمومی، بدون هیچ تغییر."""
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=8) as r:
            body = json.loads(r.read().decode(errors="replace"))
            return {"http": r.status, "ok": bool(body.get("ok")),
                    "mode": body.get("mode"), "connection": body.get("connection")}
    except urllib.error.HTTPError as e:
        return {"http": e.code, "ok": False, "mode": None, "connection": None}
    except Exception as e:
        return {"http": None, "ok": False, "mode": None, "connection": None,
                "why": f"{type(e).__name__}"}


def core_digest():
    """digest هستهٔ paper-trades — عین منطق verify_core.py (paused+trades+version)."""
    try:
        raw = open(PAPER, "rb").read()
        pt = json.loads(raw)
        core = hashlib.sha256(json.dumps(
            {k: pt[k] for k in ("paused", "trades", "version")},
            sort_keys=True).encode()).hexdigest()[:16]
        return core, len(pt.get("trades", [])), pt.get("paused"), hashlib.sha256(raw).hexdigest()[:16]
    except FileNotFoundError:
        return None, None, None, None


def window_from():
    """پنجرهٔ گزارش (پچ 2026-11-04):
    ۱) last_success_utc از job_state.json (اجرای FAILED دیگر آن را پاک نمی‌کند)
    ۲) اگر نبود: آخرین ردیف موفق type=2h از send-log.jsonl
    ۳) فقط اگر آن هم نبود: ابتدای امروز UTC (۰۰:۰۰Z)"""
    try:
        st = json.load(open(JOB_STATE))
        ls = st.get("last_success_utc")
        if ls:
            return ls
    except Exception:
        pass
    try:
        rows = [r for r in load_jsonl(SENDLOG)
                if r.get("type") == "2h" and r.get("delivered") is True and r.get("ts_utc")]
        if rows:
            return rows[-1]["ts_utc"]
    except Exception:
        pass
    return now_utc().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def hunt_window(w_from_iso):
    """شمارنده‌های واقعی لجر در پنجرهٔ گزارش + کل امروز UTC."""
    w = datetime.fromisoformat(w_from_iso)
    today = now_utc().strftime("%Y-%m-%d")
    dec = load_jsonl(DEC)
    rej = load_jsonl(REJ)
    win_dec = [d for d in dec if d.get("decision_ts_utc", "") > w.isoformat()]
    win_wt = [d for d in win_dec if d.get("decision") == "WOULD_TRADE"]
    win_rej = [r for r in rej if r.get("cycle_ts", "") > w.isoformat()]
    tod_dec = [d for d in dec if d.get("decision_ts_utc", "")[:10] == today]
    tod_wt = [d for d in tod_dec if d.get("decision") == "WOULD_TRADE"]
    tod_rej = [r for r in rej if r.get("cycle_ts", "")[:10] == today]
    return {
        "window": w.isoformat(), "win_dec": len(win_dec), "win_wt": win_wt,
        "win_rej": len(win_rej), "tod_dec": len(tod_dec),
        "tod_wt": len(tod_wt), "tod_rej": len(tod_rej),
    }


def shadow_status():
    try:
        d = json.load(open(SHADOW))
        day = None
        if d.get("started_at") and d.get("last_run"):
            day = round((d["last_run"] - d["started_at"]) / 86_400_000, 2)
        par = d.get("parity") or {}
        return {"runs": d.get("runs"), "day": day, "open": len(d.get("open", [])),
                "closed": d.get("closed_count"), "parity": par.get("checked"),
                "matched": par.get("matched")}
    except FileNotFoundError:
        return None


def last_scan():
    try:
        d = json.load(open(SCAN))
        btc = d.get("btc") or {}
        return {"ts": d.get("generated_utc"), "btc_price": btc.get("price"),
                "regime": d.get("btc_regime"), "states": d.get("states_count")}
    except FileNotFoundError:
        return None


def funding_status():
    """M154 — Funding Reality: فقط عدد واقعی؛ شکست = UNAVAILABLE با علت واقعی، هیچ عدد ساختگی."""
    try:
        with urllib.request.urlopen(FUNDING_URL, timeout=8) as r:
            body = json.loads(r.read().decode(errors="replace"))
        rows = [x for x in body.get("rows", []) if x.get("status") == "OK"]
        if rows:
            return {"via": "dashboard", "rows": rows}
        why = "; ".join(f"{x.get('symbol')}={x.get('error','?')}" for x in body.get("rows", []))[:120]
    except Exception as e:
        why = f"{type(e).__name__}"
    # fallback مستقیم به منبع (همان endpoint عمومی که در پروب M154 VERIFIED شد)
    out = []
    ok_any = False
    for sym in ("BTCUSDT", "ETHUSDT"):
        try:
            with urllib.request.urlopen(BINANCE_PI + sym, timeout=8) as r:
                j = json.loads(r.read().decode(errors="replace"))
            out.append({"symbol": sym, "markPrice": float(j["markPrice"]),
                        "lastFundingRate": float(j["lastFundingRate"]), "status": "OK"})
            ok_any = True
        except Exception as e2:
            out.append({"symbol": sym, "status": "UNAVAILABLE",
                        "error": f"{type(e2).__name__}"})
    if ok_any:
        return {"via": "binance-direct", "rows": [x for x in out if x["status"] == "OK"], "why": why}
    return {"via": None, "rows": [], "why": why}


def build_report():
    w_from = window_from()
    hw = hunt_window(w_from)
    core, n_trades, paused, full_hash = core_digest()
    dash = dashboard_check()
    sh = shadow_status()
    sc = last_scan()
    sends = [r for r in load_jsonl(SENDLOG) if r.get("delivered")]
    last_ok = sends[-1] if sends else None
    t = now_utc().astimezone(TEHRAN).strftime("%Y-%m-%d %H:%M")

    ages = data_ages()
    hunt_stale = (ages.get("hunt") is None or ages.get("tickvault") is None
                  or ages["hunt"] > HUNT_MAX_AGE_H or ages["tickvault"] > HUNT_MAX_AGE_H)

    L = ["🕰 گزارش دوساعتهٔ MARI (M153-A)"]
    L.append(f"• زمان گزارش (تهران): {t}")
    L.append("— داشبورد —")
    if dash.get("http") == 200 and dash.get("ok"):
        L.append(f"• /api/health: HTTP 200 · ok=true · mode={dash.get('mode')}")
    else:
        why = f" · {dash['why']}" if dash.get("why") else ""
        L.append(f"• DASHBOARD_OFFLINE · HTTP {dash.get('http')}{why}")
    L.append("— سن داده (پادزهر صفرِ روی دادهٔ کهنه) —")
    L.append(age_line("tick-vault", ages.get("tickvault"), HUNT_MAX_AGE_H))
    L.append(age_line("تصمیمات شکار", ages.get("hunt"), HUNT_MAX_AGE_H))
    L.append(age_line("شادو پیپر", ages.get("shadow"), SHADOW_MAX_AGE_H))
    L.append(age_line("مگاترند", ages.get("megatrend"), MEGA_MAX_AGE_H))
    L.append("— لجر شکار (فقط‌خواندنی) —")
    L.append(f"• پنجرهٔ گزارش: از {w_from[:19]}Z")
    if hunt_stale:
        L.append(f"• ⚠️ نامعتبر: دادهٔ کهنه (تصمیمات {ages.get('hunt')}h · tick-vault {ages.get('tickvault')}h) — صفر یعنی هیچ، نه «بدون فرصت»")
    else:
        L.append(f"• پنجره: تصمیم {fa(hw['win_dec'],0)} · آماده‌شکار {fa(len(hw['win_wt']),0)} · رویداد رد {fa(hw['win_rej'],0)}")
    if hw["win_wt"]:
        for d_ in sorted(hw["win_wt"], key=lambda x: -(x.get("net_pct") or 0))[:5]:
            L.append(f"  «{d_.get('base')}» خالص {fa(d_.get('net_pct'))}٪ ({d_.get('method')} · {d_.get('cycle_ts','')[11:19]}Z)")
    if hunt_stale:
        L.append("• امروز UTC: نامعتبر — دادهٔ کهنه")
    else:
        L.append(f"• امروز UTC: تصمیم {fa(hw['tod_dec'],0)} · آماده‌شکار {fa(hw['tod_wt'],0)} · رد {fa(hw['tod_rej'],0)}")
    L.append("— حفاظت —")
    if core is None:
        L.append("• paper-trades.json: MISSING")
    else:
        mark = "✓ برابر مرجع" if core == REFERENCE_DIGEST else "✗ ناهمسان با مرجع!"
        L.append(f"• digest هسته = {core} {mark}")
        L.append(f"• paused={paused} · trades={fa(n_trades,0)} · full-hash={full_hash} (فقط bookkeeping)")
    L.append("— شادو پیپر (run#2) —")
    if sh:
        warn = " ⚠️ کهنه" if (ages.get("shadow") is None or ages["shadow"] > SHADOW_MAX_AGE_H) else ""
        L.append(f"• روز {fa(sh['day'],2)} · باز {fa(sh['open'],0)} · بسته {fa(sh['closed'],0)} · parity {fa(sh['matched'],0)}/{fa(sh['parity'],0)} · سن {fa(ages.get('shadow') if ages.get('shadow') is not None else -1,1)}h{warn}")
    else:
        L.append("• shadow/state.json: MISSING")
    L.append("— آخرین اسکن مگاترند —")
    if sc:
        st = sc.get("states") or {}
        mwarn = " ⚠️ کهنه" if (ages.get("megatrend") is None or ages["megatrend"] > MEGA_MAX_AGE_H) else ""
        L.append(f"• {sc['ts'][:19] if sc.get('ts') else 'MISSING'} · BTC {fa(sc.get('btc_price'),0)}$ · رژیم {sc.get('regime')} · روند تأیید: ۰ · سن {fa(ages.get('megatrend') if ages.get('megatrend') is not None else -1,1)}h{mwarn}")
        L.append(f"• WEAKENING {fa(st.get('WEAKENING',0),0)} · REJECTED {fa(st.get('REJECTED',0),0)} · EARLY_ACC {fa(st.get('EARLY_ACCUMULATION',0),0)}")
    else:
        L.append("• megatrend_scan.json: MISSING")
    L.append("— Funding Reality (M154، واقعی) —")
    fr = funding_status()
    if fr["rows"]:
        for x in fr["rows"]:
            L.append(f"• {x['symbol']}: mark {fa(x['markPrice'],0)}$ · نرخ فاندینگ {fa(x['lastFundingRate']*100, 4)}٪ /۸س")
    else:
        L.append(f"• UNAVAILABLE ({fr.get('why','?')})")
    L.append("— گزارش‌گیری —")
    L.append(f"• آخرین ارسال موفق: {last_ok['ts_utc'][:19] + 'Z' if last_ok else 'هیچ'} · نوع {last_ok.get('type') if last_ok else '-'} · msg {last_ok.get('message_id') if last_ok else '-'}")
    L.append("• READ ONLY | PAPER ONLY | NO LIVE ORDERS")
    return "\n".join(L)


def send_with_retry(title, text):
    cfg = load_telegram_config()
    tok = cfg.get("token", "")
    chats = cfg.get("chatIds", [])
    if not tok or not chats:
        return None, "TELEGRAM_CONFIG_MISSING"
    parts = chunk_text(f"{title}\n{text}")
    mids, err = [], None
    for cid in chats:
        for i, part in enumerate(parts, 1):
            suffix = f"\n(بخش {fa(i,0)} از {fa(len(parts),0)})" if len(parts) > 1 else ""
            ok, mid, last_err = False, None, None
            for attempt in range(1, RETRIES + 1):
                st, resp = api_call(tok, "sendMessage",
                                    {"chat_id": cid, "text": part + suffix})
                mid = resp.get("result", {}).get("message_id") if st == 200 else None
                ok = st == 200 and resp.get("ok") and bool(mid)
                last_err = None if ok else str(resp.get("raw", ""))[:150]
                if ok:
                    break
                time.sleep(RETRY_SLEEP * attempt)
            log_send({"ts_utc": iso(now_utc()), "type": "2h", "chat_id": cid,
                      "part": f"{i}/{len(parts)}", "http": st, "api_ok": resp.get("ok"),
                      "message_id": mid, "delivered": bool(ok), "error": last_err})
            if ok:
                mids.append(mid)
            else:
                err = last_err or "SEND_FAILED"
    return mids, err


def main():
    ap = __import__("argparse").ArgumentParser()
    ap.add_argument("--send", action="store_true")
    a = ap.parse_args()

    report_id = f"2H-{now_utc().strftime('%Y%m%dT%H%M')}Z"
    text = build_report()
    # پچ 2026-11-04: last_success_utc جدا از last_run_utc — FAILED آن را پاک نمی‌کند
    try:
        prev_state = json.load(open(JOB_STATE))
    except Exception:
        prev_state = {}
    state = {"job": "m153-a-2h", "last_run_utc": iso(now_utc()), "report_id": report_id,
             "last_success_utc": prev_state.get("last_success_utc")}

    if not a.send:
        print(text)
        print(json.dumps({"outcome": "DRY_RUN", "report_id": report_id}, ensure_ascii=False))
        return 0

    try:
        mids, err = send_with_retry("🕰 MARI دوساعته", text)
    except FileNotFoundError:
        mids, err = None, "TELEGRAM_CONFIG_MISSING"
    except Exception as e:  # علت واقعی ثبت شود، هرگز جعل نشود
        mids, err = None, f"{type(e).__name__}: {e}"[:200]

    outcome = "SUCCESS" if mids else "FAILED"
    if outcome == "SUCCESS":
        state["last_success_utc"] = iso(now_utc())  # فقط موفقیت ثبت می‌شود؛ FAILED دست نمی‌زند
    state.update({"outcome": outcome, "message_ids": mids or [],
                  "error": err, "consecutive_failures": 0 if outcome == "SUCCESS"
                  else _bump_failures()})
    _write_json(JOB_STATE, state)
    _write_json(HEARTBEAT, {"ts_utc": iso(now_utc()), "outcome": outcome,
                            "report_id": report_id, "error": err})
    print(json.dumps({"outcome": outcome, "report_id": report_id,
                      "message_ids": mids or [], "error": err}, ensure_ascii=False))
    return 0 if outcome == "SUCCESS" else 1


def _bump_failures():
    try:
        prev = json.load(open(JOB_STATE)).get("consecutive_failures", 0)
    except Exception:
        prev = 0
    return prev + 1


def _write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


if __name__ == "__main__":
    sys.exit(main())
