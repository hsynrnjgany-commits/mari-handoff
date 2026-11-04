#!/usr/bin/env python3
# scripts/ai_gateway/hunt_audit.py - PAPER ONLY | READ-ONLY روی store شکار | NO KEYS چاپ نمی‌شود
# حلقهٔ اتصال رییس (2026-11-02، تأیید «hunt_sweep.py»): بعد از hunt_sweep.py در pipeline،
# تصمیم‌های آخرین چرخه به‌صورت «متن» به AI Gateway می‌رود و حکم مستقل ثبت می‌شود.
# بازسازی 2026-11-02T01:2xZ بعد از گم‌شدن در بازیابی ساندباکس (فایل هرگز کامیت نشده بود)
# طراحی:
#  - hunt_sweep.py دست‌نخورده می‌ماند؛ حسابرسی جداگانه است تا خرابی Gateway هرگز مسیر شکار را نشکند
#  - فقط اعداد موجود در decisions/cycles/rejects به مدل می‌رسد — هیچ داده‌ای ساخته نمی‌شود
#  - idempotent: هر cycle_ts فقط یک بار حسابرسی می‌شود (state در records/hunt_audit_state.json)
#  - رکورد کامل (متن + پاسخ‌ها) در records/hunt_audit.jsonl — append-only
# پچ 2026-11-03 (فرمان رییس): NO_VERDICT حکم واقعی نیست — state مصرف نمی‌شود؛
#  دلیل واقعی هر ارائه‌دهنده در reasons خروجی JSON می‌آید (مثل 429 بعد از تلاش مجدد).
import os
import re
import sys
import json
import hashlib
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ai_gateway as gw  # noqa: E402  (.env loader هم همین‌جا اجرا می‌شود)

ROOT = gw.ROOT
STORE = os.path.join(ROOT, "scripts", "mari_hunt01", "store")
DECISIONS = os.path.join(STORE, "decisions.jsonl")
CYCLES = os.path.join(STORE, "cycles.jsonl")
REJECTS = os.path.join(STORE, "rejects.jsonl")
AUDIT_LOG = os.path.join(gw.RECORDS, "hunt_audit.jsonl")
STATE = os.path.join(gw.RECORDS, "hunt_audit_state.json")
MAX_DECISIONS = 20
MAX_LINE = 240
# COVERAGE-01 (فرمان رییس 2026-11-02، بند ۷): حسابرسی فقط روی تصمیم‌های WOULD_TRADE
# و حداکثر ۱۰ ردشدهٔ «نزدیک آستانه» — نه همهٔ تصمیم‌ها (جلوگیری از 429 و هزینه).
# idempotency (state بر کلید cycle_ts) دست‌نخورده می‌ماند.
MAX_NEAR_REJECTS = 10


def load_jsonl(path):
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
    return out


def last_cycle():
    rows = load_jsonl(CYCLES)
    return rows[-1] if rows else None


def near_threshold_rejects(rej):
    """ردشده‌های «نزدیک آستانه» برای حسابرسی محدود (COVERAGE-01/۷):
    - liquidity<$100(tob $X/$Y): نزدیک اگر min(X,Y) ≥ 50$ (دو برابرِ حد) — چیدمان بر اساس نزدیکی
    - thin_book_l2: عمق تا $100 پُر نشده اما از TOB جلوتر است (نزدیک‌ترین رده)
    بقیهٔ ردها (phantom/frozen/stale) فاقد مجاورت عددی به آستانه‌اند و حسابرسی نمی‌شوند.
    برگشت: حداکثر MAX_NEAR_REJECTS رکورد."""
    scored = []
    for r in rej:
        reason = str(r.get("reason", ""))
        key = reason.split("(")[0]
        if key == "liquidity<$100":
            try:
                nums = [float(x) for x in re.findall(r"\$([0-9.]+)", reason)]
                if nums and min(nums) >= 50.0:
                    scored.append((min(nums), r))
            except Exception:
                pass
        elif key == "thin_book_l2":
            scored.append((100.0, r))
    scored.sort(key=lambda t: -t[0])
    return [r for _s, r in scored[:MAX_NEAR_REJECTS]]


def build_task(cyc, decs, rej_counts, near):
    """متن حسابرسی (COVERAGE-01/۷): فقط WOULD_TRADE + ردشده‌های نزدیک آستانه.
    UNVERIFIED/SKIP_NET دیگر حسابرسی نمی‌شوند (هزینه/429)."""
    n = len(decs)
    lines = []
    for d in decs[:MAX_DECISIONS]:
        base = d.get("base")
        bex, sex = d.get("buy_ex"), d.get("sell_ex")
        core = (
            "- id=%s base=%s %s->%s method=%s size=%s gross_pct=%s net_pct=%s "
            "gate_status=%s decision=%s dup=%s"
            % (d.get("id"), base, bex, sex, d.get("method"), d.get("size_usdt"),
               d.get("gross_pct"), d.get("net_pct"), d.get("gate_status"),
               d.get("decision"), d.get("duplicate_sighting"))
        )
        extra = ""
        if d.get("method") == "l2_vwap_100":
            extra = (
                " buy_vwap=%s sell_vwap=%s slip_buy=%s slip_sell=%s "
                "transfer_cost=%s scenarios=%s"
                % (d.get("buy_vwap"), d.get("sell_vwap"),
                   d.get("buy_slip_pct"), d.get("sell_slip_pct"),
                   d.get("transfer_cost"), json.dumps(d.get("transfer_scenarios_net_pct")))
            )
        lines.append((core + extra)[:MAX_LINE])
    if n > MAX_DECISIONS:
        lines.append("... (%d تصمیم دیگر نمایش داده نشد)" % (n - MAX_DECISIONS))
    if not lines:
        lines.append("(در این چرخه WOULD_TRADE وجود نداشت — فقط ردشده‌های نزدیک آستانه حسابرسی می‌شوند)")

    near_lines = []
    for r in near[:MAX_NEAR_REJECTS]:
        near_lines.append(("- REJECT id=%s base=%s reason=%s gross_pct=%s" % (
            r.get("id"), r.get("base"), r.get("reason"), r.get("gross_pct")))[:MAX_LINE])
    if not near_lines:
        near_lines.append("(ردشدهٔ نزدیک آستانه‌ای در این چرخه نبود)")

    task = (
        "حسابرسی محدود تصمیم‌های شکار آربیتراژ (سیستم فقط-کاغذی HUNT-01) — چرخهٔ %s\n"
        "دامنهٔ حسابرسی (COVERAGE-01): فقط تصمیم‌های WOULD_TRADE + حداکثر ۱۰ ردشدهٔ نزدیک آستانه.\n"
        "منبع: decisions.jsonl و rejects.jsonl. شما فقط اعداد همین متن را دارید؛ هیچ دادهٔ خارجی نمی‌دانید و نباید چیزی بسازید.\n"
        "خلاصهٔ چرخه: sources_ok=%s/%s candidates_in=%s decisions_written=%s "
        "would_trade=%s unverified_tob_only=%s rejects_by_reason=%s\n"
        "قواعد سازگاری برای بررسی:\n"
        "- decision=WOULD_TRADE: method باید l2_vwap_100 باشد و net_pct عددی > 0.\n"
        "- ردشده‌های نزدیک آستانه فقط برای راستی‌آزمایی اعدادند (مثلاً liquidity<$100 باید واقعاً tob زیر 100 باشد)؛ رد، تصمیم شکار نیست.\n"
        "- dup=true فقط اطلاع‌رسانی تکراری‌بودن فرصت است، خطا نیست.\n"
        "معیار حکم: SUPPORTED=موارد حسابرسی‌شده با اعداد همین متن سازگارند؛ UNSUPPORTED=تناقض پیدا شد؛ "
        "INSUFFICIENT_EVIDENCE=اعداد کافی نیست.\n"
        "تصمیم‌های WOULD_TRADE این چرخه:\n%s\n"
        "ردشده‌های نزدیک آستانه (حداکثر ۱۰):\n%s"
        % (cyc.get("cycle_ts"),
           cyc.get("sources_ok"), cyc.get("sources_total"), cyc.get("candidates_in"),
           cyc.get("decisions_written"), cyc.get("would_trade"),
           cyc.get("unverified_tob_only"), json.dumps(rej_counts, ensure_ascii=False),
           "\n".join(lines),
           "\n".join(near_lines))
    )
    return task


def main():
    cyc = last_cycle()
    if not cyc:
        print(json.dumps({"ok": False, "stage": "hunt_audit",
                          "reason": "no_cycle_in_cycles.jsonl"}, ensure_ascii=False))
        return 2
    cycle_ts = cyc.get("cycle_ts")
    state = {}
    if os.path.exists(STATE):
        try:
            state = json.load(open(STATE, encoding="utf-8"))
        except Exception:
            state = {}
    if state.get("last_cycle_ts") == cycle_ts:
        print(json.dumps({"ok": True, "stage": "hunt_audit", "skipped": "already_audited",
                          "cycle_ts": cycle_ts, "audit_id": state.get("last_audit_id")},
                         ensure_ascii=False))
        return 0

    decs_all = [d for d in load_jsonl(DECISIONS) if d.get("cycle_ts") == cycle_ts]
    # COVERAGE-01/۷: فقط WOULD_TRADE حسابرسی می‌شود — نه UNVERIFIED و نه SKIP_NET
    decs = [d for d in decs_all if d.get("decision") == "WOULD_TRADE"]
    rej = [r for r in load_jsonl(REJECTS) if r.get("cycle_ts") == cycle_ts]
    near = near_threshold_rejects(rej)
    rej_counts = {}
    for r in rej:
        reason = str(r.get("reason", "?")).split("(")[0]
        rej_counts[reason] = rej_counts.get(reason, 0) + 1

    task = build_task(cyc, decs, rej_counts, near)
    audit_id = "HUNTAUD-" + datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    t0 = datetime.datetime.now(datetime.timezone.utc).isoformat()
    try:
        s = gw.run(task)
    except Exception as e:  # حتی کرش داخلی هم ثبت و صادقانه گزارش می‌شود
        os.makedirs(gw.RECORDS, exist_ok=True)
        err_rec = {"audit_id": audit_id, "stage": "hunt_decisions_audit", "cycle_ts": cycle_ts,
                   "audit_started_utc": t0, "status": "GATEWAY_EXCEPTION",
                   "error": type(e).__name__ + ": " + str(e)[:200]}
        with open(AUDIT_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(err_rec, ensure_ascii=False) + "\n")
        print(json.dumps({"ok": False, "stage": "hunt_audit", "audit_id": audit_id,
                          "status": "GATEWAY_EXCEPTION"}, ensure_ascii=False))
        return 1

    rec = {
        "audit_id": audit_id, "stage": "hunt_decisions_audit",
        "cycle_ts": cycle_ts, "decision_ts_utc": cyc.get("evaluated_ts_utc"),
        "audit_started_utc": t0,
        "counts": {"decisions": len(decs),
                   "decisions_total_in_cycle": len(decs_all),
                   "would_trade": sum(1 for d in decs if d.get("decision") == "WOULD_TRADE"),
                   "unverified": sum(1 for d in decs if d.get("decision") == "UNVERIFIED"),
                   "skip_net": sum(1 for d in decs if d.get("decision") == "SKIP_NET"),
                   "rejects": len(rej),
                   "near_threshold_rejects_audited": len(near)},
        "verdicts": s.get("verdicts"), "disagreement": s.get("disagreement"),
        "results": s.get("results"),
        "task_text": task, "task_text_sha256": hashlib.sha256(task.encode()).hexdigest(),
    }
    os.makedirs(gw.RECORDS, exist_ok=True)
    with open(AUDIT_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # سیم‌کشی خود-ترمیم (2026-11-02، تأیید رییس «وصل کن»): اگر هیچ حکم واقعی برنگشت
    # (مثلاً 429/402 در هر دو ارائه‌دهنده)، state مصرف نمی‌شود تا اجرای بعدی pipeline
    # همین چرخه را دوباره حسابرسی کند. ثبت تلاش در AUDIT_LOG (append-only) کامل می‌ماند
    # و خرابی هرگز مراحل بعدی pipeline را نمی‌شکند (exit=1 فقط گزارش است).
    # پچ 2026-11-03: فقط حکم‌های واقعی (SUPPORTED/UNSUPPORTED/INSUFFICIENT_EVIDENCE) شمرده
    # می‌شوند؛ NO_VERDICT (مثل 429 پایدار بعد از تلاش مجدد) حکم واقعی نیست → state مصرف
    # نمی‌شود تا چرخهٔ بعدی همین cycle را دوباره حسابرسی کند.
    real_verdicts = [v for v in (s.get("verdicts") or []) if v in gw.VERDICTS]
    if not real_verdicts:
        print(json.dumps({"ok": False, "stage": "hunt_audit", "audit_id": audit_id,
                          "cycle_ts": cycle_ts, "status": "NO_REAL_VERDICT",
                          "decisions_audited": len(decs),
                          "near_threshold_rejects_audited": len(near),
                          "reasons": s.get("reasons"),
                          "providers": [{"provider": r.get("provider"), "status": r.get("status"),
                                         "model": r.get("model")} for r in s.get("results", [])]},
                         ensure_ascii=False))
        return 1

    with open(STATE, "w", encoding="utf-8") as f:
        json.dump({"last_cycle_ts": cycle_ts, "last_audit_id": audit_id,
                   "last_audit_utc": t0}, f, ensure_ascii=False)

    print(json.dumps({"ok": True, "stage": "hunt_audit", "audit_id": audit_id,
                      "cycle_ts": cycle_ts, "decisions_audited": len(decs),
                      "near_threshold_rejects_audited": len(near),
                      "verdicts": s.get("verdicts"), "disagreement": s.get("disagreement"),
                      "reasons": s.get("reasons"),
                      "providers": [{"provider": r.get("provider"), "status": r.get("status"),
                                     "model": r.get("model")} for r in s.get("results", [])]},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

# END_OF_FILE
