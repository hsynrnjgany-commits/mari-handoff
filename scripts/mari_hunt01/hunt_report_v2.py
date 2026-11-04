#!/usr/bin/env python3
"""
M155 HUNT REPORT v2 — گزارش کوتاه بخش‌بندی‌شدهٔ شکار (فاز ۷ مأموریت M155)
==========================================================================
اجرا: python3 scripts/mari_hunt01/hunt_report_v2.py [--cycle-index N]
بخش‌های اجباری: A. MARKET SCAN · B. EXECUTABILITY · C. TOP 10 (حداکثر ۱۰ ردیف)
D. REJECTION SUMMARY (شمارش رخداد مستقل هر دلیل) · E. SYSTEM HEALTH
توابع رندر خالص‌اند (بدون I/O) تا در تست‌ها با دادهٔ ساختگی قابل‌استفاده باشند.
READ ONLY | PAPER ONLY | NO LIVE ORDERS
"""
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone

S = "scripts/mari_hunt01/store"
LAST = "scripts/m140_tick_vault/last_cycle.json"
ERRLOG = "scripts/m140_tick_vault/errors.log"
SENDLOG = "scripts/mari_telegram/send-log.jsonl"
UNIVERSE = "scripts/mari_hunt01/universe.json"
COV_STATE = f"{S}/toobit_sweep_state.json"
TOP_LIMIT = 10
MAX_REPORT_AGE_MINUTES = 30   # پارامتر مستقل نمایش فرصت‌های تازه در گزارش

def load_jsonl(p):
    out = []
    if os.path.exists(p):
        for ln in open(p, encoding="utf-8"):
            ln = ln.strip()
            if ln:
                try:
                    out.append(json.loads(ln))
                except Exception:
                    pass
    return out

def render_top(opps, limit=TOP_LIMIT):
    """حداکثر «limit» فرصت برتر: اول WOULD_TRADE (بیشترین net)، بعد بقیه با بیشترین gross."""
    def rank(o):
        pri = 0 if str(o.get("gate_status")) == "WOULD_TRADE" else 1
        try:
            net = float(o.get("net_pct") or -999)
        except Exception:
            net = -999
        try:
            gross = float(o.get("gross_pct") or -999)
        except Exception:
            gross = -999
        return (pri, -net if pri == 0 else 0, -gross)
    rows = sorted([o for o in opps if o.get("gate_status")], key=rank)[:limit]
    lines = ["  # | Symbol | Buy→Sell | Gross% | Net100USDT$ | BuyVWAP | SellVWAP | AgeBuy/s | AgeSell/s | Seen | Status"]
    for i, o in enumerate(rows, 1):
        net100 = (float(o["net_pct"]) * 1.0) if o.get("net_pct") is not None else None
        st = o.get("gate_status") or "?"
        if o.get("suspect") and st == "WOULD_TRADE":
            st += "(SUSPECT_PASS)"
        lines.append(
            f"  {i} | {o.get('base')} | {o.get('buy_ex')}→{o.get('sell_ex')} | "
            f"{o.get('gross_pct')} | {net100 if net100 is not None else 'N/A'} | "
            f"{o.get('buy_vwap') or o.get('buy_price')} | {o.get('sell_vwap') or o.get('sell_price')} | "
            f"{o.get('buy_age_s', 'N/A')} | {o.get('sell_age_s', 'N/A')} | "
            f"{o.get('seen_count', 1)} | {st}")
    return "\n".join(lines), len(rows)

def toobit_coverage_line(now=None):
    """«نماد پوشش‌داده‌شده از N» (COVERAGE-01 بند ۸) + گارد کهنگی universe.
    universe قدیمی‌تر از 25 ساعت → «نامعتبر — داده کهنه» (همان الگوی گارد گزارش‌ها)."""
    try:
        u = json.load(open(UNIVERSE, encoding="utf-8"))
        n = u.get("count") or len(u.get("symbols") or [])
        age_h = ((now or datetime.now(timezone.utc))
                 - datetime.fromisoformat(u["refreshed_utc"])).total_seconds() / 3600
        guard = "✓ تازه" if age_h <= 25.0 else "⚠️ کهنه (>25h) → نامعتبر — داده کهنه"
        covered, cur, last = "؟", "؟", {}
        if os.path.exists(COV_STATE):
            st = json.load(open(COV_STATE, encoding="utf-8"))
            covered = st.get("covered_count", len(st.get("covered_symbols") or []))
            cur = st.get("cursor", "؟")
            last = st.get("last_run") or {}
        return (f"  پوشش تووبیت (COVERAGE-01): {covered} از {n} نماد USDT فعال · "
                f"آخرین چرخه: {last.get('symbols_processed', 0)} پردازش / "
                f"cursor={cur} · universe: {guard}")
    except Exception:
        return "  پوشش تووبیت (COVERAGE-01): UNAVAILABLE"


def build_report(cycle_rows=None, decisions=None, rejects=None, index=None,
                 last_cycle=None, errlog_lines=None, sendlog=None, now=None):
    now = now or datetime.now(timezone.utc)
    cycle_rows = cycle_rows if cycle_rows is not None else load_jsonl(f"{S}/cycles.jsonl")
    decisions = decisions if decisions is not None else load_jsonl(f"{S}/decisions.jsonl")
    rejects = rejects if rejects is not None else load_jsonl(f"{S}/rejects.jsonl")
    index = index if index is not None else load_jsonl(f"{S}/opportunities_index.jsonl")
    last_cycle = last_cycle if last_cycle is not None else (
        json.load(open(LAST)) if os.path.exists(LAST) else {})
    last = cycle_rows[-1] if cycle_rows else {}
    ct = last.get("cycle_ts")
    cur_dec = [d for d in decisions if d.get("cycle_ts") == ct and not str(d.get("type", "")).startswith("aggregate")]
    cur_rej = [r for r in rejects if r.get("cycle_ts") == ct]

    # A — MARKET SCAN
    scanned = last_cycle.get("matched_bases")
    raw_signals = last.get("candidates_in", len(cur_dec) + len(cur_rej))
    uniques_total = len(index)
    new_uniques = sum(1 for d in cur_dec if d.get("seen_count") == 1 and d.get("method") == "l2_vwap_100")
    cov = toobit_coverage_line(now)
    A = (f"  نمادهای بررسی‌شده (matched bases): {scanned if scanned is not None else 'UNAVAILABLE'}\n"
         f"  سیگنال خام این چرخه: {raw_signals}\n"
         f"  فرصت‌های یکتا (ایندکس تجمعی): {uniques_total} · جدید در این چرخه: {new_uniques}\n"
         f"{cov}")

    # B — EXECUTABILITY (روی ردیف‌های L2 این چرخه)
    l2rows = [d for d in cur_dec if d.get("method") == "l2_vwap_100"]
    max_age = 10.0
    fresh = sum(1 for d in l2rows
                if d.get("buy_age_s") is not None and float(d["buy_age_s"]) <= max_age
                and d.get("sell_age_s") is not None and float(d["sell_age_s"]) <= max_age)
    B = (f"  L2 verified: {len(l2rows)} از {len(cur_dec)} سیگنال این چرخه\n"
         f"  Fresh (≤{10}s): {fresh}\n"
         f"  Identity verified: {sum(1 for d in l2rows if d.get('identity') == 'VERIFIED')}\n"
         f"  Transfer verified/open: {sum(1 for d in l2rows if d.get('transfer') == 'OPEN')}\n"
         f"  Depth sufficient: {sum(1 for d in l2rows if d.get('gate_status') != 'THIN_BOOK')}\n"
         f"  UNVERIFIED (فقط TOB — از شمارش آماده‌شکار حذف): {sum(1 for d in cur_dec if d.get('decision') == 'UNVERIFIED')}")

    # C — TOP 10
    top_txt, top_n = render_top(cur_dec, TOP_LIMIT)

    # D — REJECTION SUMMARY (رخدادهای مستقل؛ جمع این ستون‌ها = تعداد فرصت یکتا نیست)
    rc = Counter(str(r.get("reason", "?")).split("(")[0] for r in cur_rej)
    dc = Counter(str(d.get("gate_status")) for d in cur_dec if d.get("gate_status") and d.get("gate_status") not in ("WOULD_TRADE",))
    dup_occ = sum(1 for d in cur_dec if d.get("duplicate_sighting"))
    D = ["  -- این چرخه (رخدادهای مستقل) --"]
    for k in ("UNVERIFIED", "STALE", "DUPLICATE", "SYMBOL_MISMATCH", "TRANSFER_BLOCKED", "SUSPECT"):
        v = dup_occ if k == "DUPLICATE" else dc.get(k, 0) + rc.get(k, 0)
        D.append(f"  {k}: {v}")
    extra = {k: v for k, v in list(dc.items()) + list(rc.items())
             if k not in ("UNVERIFIED", "STALE", "DUPLICATE", "SYMBOL_MISMATCH", "TRANSFER_BLOCKED", "SUSPECT")}
    for k, v in sorted(extra.items()):
        D.append(f"  {k}: {v}")
    rc_all = Counter(str(r.get("reason", "?")).split("(")[0] for r in rejects)
    D.append("  -- تجمعی کل پرونده (top) --")
    for k, v in rc_all.most_common(8):
        D.append(f"  {k}: {v}")
    D = "\n".join(D)

    # E — SYSTEM HEALTH
    l2ts = [l.get("recv_ts") for l in (last_cycle.get("l2") or []) if l.get("recv_ts")]
    err_n = len(errlog_lines) if errlog_lines is not None else len(load_jsonl(ERRLOG))
    failed_ex = last.get("failed_sources") or []
    sends = sendlog if sendlog is not None else load_jsonl(SENDLOG)
    last_send = sends[-1] if sends else None
    send_state = "UNAVAILABLE (no send log)" if not last_send else \
        f"آخرین ارسال: {last_send.get('ts_utc') or last_send.get('ts')} ok={last_send.get('ok', last_send.get('sent', '?'))}"
    E = (f"  Last successful scan: {ct or 'UNAVAILABLE'}\n"
         f"  Last L2 update: {max(l2ts) if l2ts else 'UNAVAILABLE'}\n"
         f"  Data errors (l2_fail این چرخه): {len(last_cycle.get('l2_fail') or [])} · errors.log تجمعی: {err_n}\n"
         f"  Exchange errors: {failed_ex if failed_ex else 'هیچ'}\n"
         f"  Report delivery: {send_state} · زمان‌بند ۲ساعته: از دست‌رفته در ریست workspace → UNAVAILABLE")

    rep = []
    rep.append("═══ M155 HUNT REPORT v2 — %sUTC ═══" % now.strftime("%Y-%m-%dT%H:%M"))
    rep.append("چرخه: %s" % (ct or "?"))
    rep.append("A. MARKET SCAN\n" + A)
    rep.append("B. EXECUTABILITY\n" + B)
    rep.append("C. TOP %d (از %d فرصت ارزیابی‌شدهٔ این چرخه)\n%s" % (TOP_LIMIT, len(cur_dec), top_txt))
    rep.append("D. REJECTION SUMMARY\n" + D)
    rep.append("E. SYSTEM HEALTH\n" + E)
    rep.append("توجه: جمع دلایل رد، تعداد فرصت یکتا نیست (شمارش رخداد مستقل است).")
    rep.append("READ ONLY | PAPER ONLY | NO LIVE ORDERS")
    return "\n".join(rep), {"A": A, "B": B, "top_n": top_n, "D": D, "E": E}

def main():
    txt, _ = build_report()
    print(txt)
    return 0

if __name__ == "__main__":
    sys.exit(main())
