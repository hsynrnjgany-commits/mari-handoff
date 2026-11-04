#!/usr/bin/env python3
"""
MARI-HUNT-01 metrics v2 — ۲۰ شاخص اجباری از انبار مقاوم مأموریت
================================================================
ورودی: scripts/mari_hunt01/store/{mission,decisions,rejects,cycles}(.json|.jsonl)
رکوردهای aggregate_reconstruction فقط در شمارش ردشدگان می‌آیند، نه معامله.
"""
import json
import os
import statistics
import sys
from collections import defaultdict

M = "scripts/mari_hunt01/store"

def load_jsonl(p):
    if not os.path.exists(p):
        return []
    out = []
    for line in open(p, encoding="utf-8"):
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out

def main():
    mission = json.load(open(f"{M}/mission.json"))
    dec_all = load_jsonl(f"{M}/decisions.jsonl")
    rej = load_jsonl(f"{M}/rejects.jsonl")
    cyc = load_jsonl(f"{M}/cycles.jsonl")
    agg = [d for d in dec_all if d.get("type", "").startswith("aggregate")]
    dec = [d for d in dec_all if not d.get("type", "").startswith("aggregate")]
    trades = [d for d in dec if d.get("decision") == "WOULD_TRADE"]
    skipnet = [d for d in dec if d.get("decision") == "SKIP_NET"]
    recon = [d for d in dec if d.get("reconstructed_from_transcript")]

    CAP = mission["paper_account"]["capital_usdt"]
    SIZE = mission["paper_account"]["position_size_usdt_per_trip"]

    bases_dec = {d["base"] for d in dec if d.get("base")}
    bases_rej = {r["base"] for r in rej}
    symbols_total = len(bases_dec | bases_rej) + sum(a.get("skip_net_count", 0) for a in agg)
    symbols_valid = len(bases_dec)

    wins = [t for t in trades if t["net_pct"] > 0]
    losses = [t for t in trades if t["net_pct"] < 0]
    bes = [t for t in trades if t["net_pct"] == 0]
    gross_usd = lambda t: t["gross_pct"] / 100 * t["size_usdt"]
    net_usd = lambda t: t["net_pct"] / 100 * t["size_usdt"]
    gross_win = sum(gross_usd(t) for t in trades if gross_usd(t) > 0)
    gross_loss = sum(gross_usd(t) for t in trades if gross_usd(t) < 0)
    net_total = sum(net_usd(t) for t in trades)
    pf = (gross_win / abs(gross_loss)) if gross_loss > 0 else None
    wr_den = len(wins) + len(losses) + len(bes)
    wr = len(wins) / wr_den if wr_den else None
    net_rets = [t["net_pct"] for t in trades]
    avg_win = statistics.mean([t["net_pct"] for t in wins]) if wins else None
    avg_loss = statistics.mean([t["net_pct"] for t in losses]) if losses else None

    eq = CAP
    peak = CAP
    maxdd = 0.0
    dd_at = ""
    for t in sorted(trades, key=lambda x: (x.get("decision_ts_utc", ""), x.get("id", ""))):
        eq += net_usd(t)
        if eq > peak:
            peak = eq
        dd = (eq - peak) / peak * 100
        if dd < maxdd:
            maxdd = dd
            dd_at = t.get("decision_ts_utc", "")[:19]

    per_cycle = defaultdict(int)
    for t in trades:
        per_cycle[t.get("cycle_ts")] += 1
    max_concurrent = max(per_cycle.values()) if per_cycle else 0
    max_exposure = max_concurrent * SIZE
    per_base = defaultdict(float)
    for t in trades:
        per_base[t["base"]] += net_usd(t)
    top_base = max(per_base.items(), key=lambda kv: kv[1]) if per_base else ("-", 0)
    conc = (abs(top_base[1]) / abs(net_total) * 100) if net_total and top_base[1] else 0

    reasons = defaultdict(int)
    for r in rej:
        reasons[r["reason"].split("(")[0]] += 1
    for d in skipnet:
        reasons["net<0.15%"] += 1
    for a in agg:
        if a.get("skip_net_count"):
            reasons["net<0.15% (بازسازی‌شده)"] += a["skip_net_count"]

    src_fail = sum(1 for c in cyc if c["sources_ok"] < c["sources_total"])
    fail_detail = [(c["cycle_ts"][:19], c["failed_sources"]) for c in cyc if c.get("failed_sources")]

    W = 66
    a = lambda s: print(s)
    a("=" * W)
    a("MARI-MULTIMARKET-HUNT-01 | شاخص‌های اجباری v2 (بازتولید‌پذیر)")
    a(f"بازه: {mission['window']['start_utc']} → {mission['window']['deadline_utc']}")
    a(f"چرخه‌های ارزیابی‌شده: {len(cyc)} | رکوردهای بازسازی‌شده پس از ریست: {len(recon)}")
    a("=" * W)
    a(f"۱) نمادهای بررسی‌شده (یکتا + شمارش بازسازی‌شده): {symbols_total}")
    a(f"۲) نمادهای دارای دادهٔ معتبر (از فیلترها گذشتند): {symbols_valid}")
    a("۳) فرصت‌های جهت‌دار صعودی/نزولی تأییدشده: 0 (پوشش‌داده‌نشده — H-HUNT-03)")
    a(f"   فرصت‌های آربیتراژ دوسویه (ARB LONG@buy/SELL@sell): {len(trades)}")
    a(f"۴) فرصت‌های تأییدشده پس از QC/ریسک (WOULD_TRADE): {len(trades)}")
    a(f"۵) معاملات شبیه‌سازی‌شده: {len(trades)} (باز: 0، بسته: {len(trades)} — سفر همزمان)")
    a(f"۶) برنده: {len(wins)} | بازنده: {len(losses)} | سربه‌سر: {len(bes)}")
    a(f"۷) نرخ برد = wins/(W+L+BE) = {len(wins)}/{wr_den} = "
      f"{wr*100:.1f}%" if wr is not None else "۷) نرخ برد: قابل محاسبه نیست (مخرج صفر)")
    a(f"۸) سود ناخالص: ${gross_win:.3f} | زیان ناخالص: ${gross_loss:.3f} | خالص: ${net_total:.3f}")
    a("۹) Profit Factor = grossWin/|grossLoss| = " +
      (f"{pf:.3f}" if pf is not None else
       "قابل محاسبه نیست/بی‌نهایت طبق تعریف (زیان ناخالص صفر)"))
    if net_rets:
        a(f"۱۰) بازده خالص هر معامله — میانگین: {statistics.mean(net_rets):.4f}% | "
          f"میانه: {statistics.median(net_rets):.4f}%")
    else:
        a("۱۰) بازده خالص: داده‌ای موجود نیست")
    a(f"۱۱) میانگین سود: {avg_win:.4f}% | میانگین زیان: {avg_loss:.4f}% | نسبت: "
      f"{abs(avg_win/avg_loss):.2f}" if avg_win and avg_loss else
      "۱۱) میانگین سود/زیان: نمونه ناکافی")
    a(f"۱۲) Max Drawdown منحنی سرمایه (${CAP} شروع): {maxdd:.3f}%"
      + (f" (در {dd_at})" if dd_at else ""))
    a(f"۱۳) حداکثر مواجهه هم‌زمان: {max_concurrent} سفر = ${max_exposure} "
      f"({max_exposure/CAP*100:.0f}% سرمایه) | تمرکز بزرگ‌ترین نماد "
      f"({top_base[0]}): {conc:.1f}% از خالص")
    a("۱۴) تفکیک بازار: crypto-spot فقط | فارکس/کالا/شاخص: پوشش‌داده‌نشده | رژیم: کهنه (N/A)")
    a(f"۱۵) قبل از هزینه (ناخالص): ${gross_win + gross_loss:.3f} | بعد از هزینه: ${net_total:.3f} "
      f"| ردپای هزینه: ${(gross_win + gross_loss) - net_total:.3f} (انتقال کلی: UNKNOWN)")
    a(f"۱۶) ردشدگان فیلترها: {sum(reasons.values())} — " +
      ", ".join(f"{k}={v}" for k, v in sorted(reasons.items(), key=lambda x: -x[1])))
    a(f"۱۷) منجمد: {reasons.get('frozen_quote(F1)',0)} | کهنه: {reasons.get('stale_venue',0)} | "
      f"فانتوم: {reasons.get('phantom>100%',0)+reasons.get('phantom_m142',0)} | ناقص: "
      f"{reasons.get('no_price',0)+reasons.get('thin_book_l2',0)}")
    a(f"۱۸) چرخه‌های دارای منبع معیوب: {src_fail} از {len(cyc)} — "
      f"{fail_detail if fail_detail else '—'}")
    a("۱۹) معیار پایه: نقد (0%) — سری قیمت BTC در دادهٔ مأموریت نیست؛ مقایسه با BTC: ناممکن")
    a("۲۰) OOS/درون‌نمونه: معاملات مأموریت رو به جلو (OOS نسبت به M141/M142)؛ "
      "پیش‌دانستهٔ M141/M142 فقط به‌عنوان درون‌نمونه‌ای افشا شده")
    a("=" * W)
    return 0

if __name__ == "__main__":
    sys.exit(main())
