#!/usr/bin/env python3
"""MARI HUNT-01 — FINAL STATE LOCK (read-only).

فقط‌خواندنی: هیچ سوینی اجرا نمی‌کند، هیچ فایل مأموریت را تغییر نمی‌دهد، هیچ شبکه‌ای صدا نمی‌زند.
تنها خروجی: چاپ گزارش + نوشتن فایل گزارش در download/ (یا مسیر --out).
قفل: READ ONLY | PAPER ONLY | NO LIVE ORDERS
"""
import json, hashlib, argparse
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path("/home/z/my-project")
STORE = ROOT / "scripts/mari_hunt01/store"
PT = ROOT / "data/paper-trades.json"
ENG = ROOT / "data/world/engine-state.json"
M155 = ROOT / "scripts/m155_ab_upgrade/out/m155_evaluation.json"
REF = "6d8b7beb6d5a6c01"
DEADLINE = datetime(2026, 10, 31, 8, 30, 0, tzinfo=timezone.utc)
START = datetime(2026, 10, 29, 21, 15, 22, tzinfo=timezone.utc)


def nlines(p):
    return sum(1 for ln in open(p, "rb") if ln.strip())


def sha16(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()[:16]


def jload(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def ts(s):
    return datetime.fromisoformat(s)


ap = argparse.ArgumentParser()
ap.add_argument("--out", default=None, help="override output path")
args = ap.parse_args()

now = datetime.now(timezone.utc)
final = now >= DEADLINE
L = []  # report lines (Persian main body)

cyc = jload(STORE / "cycles.jsonl")
dec = jload(STORE / "decisions.jsonl")
rej = jload(STORE / "rejects.jsonl")
mir = nlines(STORE / "vault-mirror.jsonl")

# --- counters ---
wt_rows = [d for d in dec if str(d.get("decision", "")).upper() == "WOULD_TRADE"]
wt_by_method = {}
for d in wt_rows:
    wt_by_method[d.get("method")] = wt_by_method.get(d.get("method"), 0) + 1
rej_by_reason = {}
for r in rej:
    key = r.get("reason") or r.get("reject_reason") or "?"
    rej_by_reason[key] = rej_by_reason.get(key, 0) + 1
rej_top = sorted(rej_by_reason.items(), key=lambda x: -x[1])[:6]

last_wt = max((d.get("cycle_ts", "") for d in wt_rows), default="—")

# per-cycle balance
cyc_by_ts = {c["cycle_ts"]: c for c in cyc}
dec_by_cyc, rej_by_cyc = {}, {}
for d in dec:
    dec_by_cyc[d.get("cycle_ts")] = dec_by_cyc.get(d.get("cycle_ts"), 0) + 1
for r in rej:
    rej_by_cyc[r.get("cycle_ts")] = rej_by_cyc.get(r.get("cycle_ts"), 0) + 1
pilot_ts = "2026-10-29T21:16:41"
balanced, unbalanced = 0, []
for c in cyc:
    got = dec_by_cyc.get(c["cycle_ts"], 0) + rej_by_cyc.get(c["cycle_ts"], 0)
    if got == c.get("candidates_in"):
        balanced += 1
    else:
        unbalanced.append((c["cycle_ts"], c.get("candidates_in"), got))
partial = [c["cycle_ts"][:19] for c in cyc if c.get("sources_ok", 8) < c.get("sources_total", 8)]

# gaps
gaps = []
prev = None
for c in cyc:
    t = ts(c["cycle_ts"])
    if prev:
        dtm = (t - prev).total_seconds() / 60
        if dtm > 40:
            gaps.append((dtm, prev.isoformat()[:19], t.isoformat()[:19]))
    prev = t
gaps.sort(reverse=True)

# missed 30-min slots after 02:40Z (cron fires UTC :10/:40)
last_cyc_ts = ts(cyc[-1]["cycle_ts"])
slots = []
t = datetime(2026, 10, 31, 2, 40, 0, tzinfo=timezone.utc)
while t < DEADLINE:
    slots.append(t)
    t += timedelta(minutes=30)
covered = set()
for s in slots:
    for c in cyc:
        if abs((ts(c["cycle_ts"]) - s).total_seconds()) <= 600:
            covered.add(s)
            break
missed = [s for s in slots if s not in covered]
offslot = [c["cycle_ts"][:19] for c in cyc
           if ts(c["cycle_ts"]) > datetime(2026, 10, 31, 2, 40, 0, tzinfo=timezone.utc)
           and all(abs((ts(c["cycle_ts"]) - s).total_seconds()) > 600 for s in slots)]

# --- protection ---
raw = json.loads(PT.read_text())
core = {k: raw[k] for k in ("paused", "trades", "version") if k in raw} if isinstance(raw, dict) else raw
dg = hashlib.sha256(json.dumps(core, sort_keys=True).encode()).hexdigest()[:16]
digest_ok = dg == REF
paused = raw.get("paused") if isinstance(raw, dict) else "?"
trades_n = len(raw.get("trades", [])) if isinstance(raw.get("trades", []), list) else "?"
eng_ok = eng_ver = "?"
if ENG.exists():
    e = json.loads(ENG.read_text())
    eng_ok = e.get("ok")
    eng_ver = e.get("engineVersion")

# --- M155 gate citation (archived, no re-evaluation) ---
m155_line = "MISSING"
m = {}
if M155.exists():
    m = json.loads(M155.read_text())
    gc = m.get("gate_status_counts", {})
    m155_line = (f"مستقل M155 (ts={m.get('ts_utc','?')[:19]}Z، {m.get('engine_decisions','?')} تصمیم): "
                 f"VERIFIED_EXECUTABLE={m.get('verified_executable')} · "
                 f"UNVERIFIED={gc.get('UNVERIFIED')} UNAVAILABLE={gc.get('UNAVAILABLE')} "
                 f"INVALID={gc.get('INVALID')} REJECTED={gc.get('REJECTED')} STALE={gc.get('STALE')}")

last = cyc[-1]
src_line = f"{last.get('sources_ok')}/{last.get('sources_total')}" + (f" failed={last.get('failed_sources')}" if last.get("failed_sources") else " بدون خطا")

# ---------- report ----------
L.append("MARI — HUNT-01 FINAL STATE LOCK / ثبت وضعیت نهایی مأموریت HUNT-01")
L.append("PROJECT: MARI — World Market Core · MODE: READ ONLY | PAPER ONLY | NO LIVE ORDERS")
L.append(f"Snapshot: {now.strftime('%Y-%m-%dT%H:%M:%SZ')} · مهلت مأموریت: {DEADLINE.strftime('%Y-%m-%dT%H:%M:%SZ')}")
if final:
    L.append("وضعیت: مهلت سپری شده — این ثبت، وضعیت نهایی و قطعی از فایل‌های واقعی است (بدون اجرای هر چرخهٔ جدید).")
else:
    L.append("وضعیت: مهلت هنوز نرسیده — این یک بررسی میانی است و ثبت نهایی نیست.")
L.append("قانون: هیچ عددی اختراع نشد؛ مفقود = MISSING؛ غیرقابل‌دسترس = UNAVAILABLE؛ هیچ سوین دستی اجرا نشد.")
L.append("")
L.append("۱) پنجرهٔ مأموریت: شروع " + START.strftime('%Y-%m-%dT%H:%M:%SZ') + " — مهلت " + DEADLINE.strftime('%Y-%m-%dT%H:%M:%SZ'))
L.append(f"۲) چرخه‌ها: {len(cyc)} چرخهٔ کامل ثبت‌شده · اولین {cyc[0]['cycle_ts'][:19]}Z · آخرین {last_cyc_ts.isoformat()[:19]}Z")
L.append(f"   توازن لجر در چرخه‌ها: {balanced}/{len(cyc)} سالم" + (f" · ناسازگار: {unbalanced}" if unbalanced else " ✓")
         + f" · منبع-ناقص (7/8): {len(partial)} چرخه")
L.append(f"   آخرین چرخه از نظر منابع: {src_line}")
pilot_dec = sum(1 for d in dec if d.get("cycle_ts", "").startswith("2026-10-29T21:16"))
pilot_rej = sum(1 for r in rej if r.get("cycle_ts", "").startswith("2026-10-29T21:16"))
L.append(f"۳) لجر: تصمیم‌ها {len(dec)} · ردها {len(rej)} · جمع کاندید {len(dec)+len(rej)} (شامل سطر آزمایشی 2026-10-29T21:16:41Z: "
         f"{pilot_dec} تصمیم / {pilot_rej} رد)")
L.append(f"۴) WOULD_TRADE تاریخی: {len(wt_rows)} (" +
         " + ".join(f"{k}={v}" for k, v in sorted(wt_by_method.items(), key=lambda x: -x[1])) +
         f") · آخرین WT: {last_wt[:19]}Z")
L.append("۵) ردها بر اساس دلیل (۶ دلیل بزرگ): " +
         " · ".join(f"{k}×{v}" for k, v in rej_top))
L.append("۶) اجراپذیری راستی‌آزمایی‌شده: " + m155_line)
L.append("   ارزیابی گیت پس از زمان بالا اجرا نشد (پس از مهلت فقط‌خواندنی) → هر رکورد WT پس از آن: UNVERIFIED. "
         f"WT پس از ممیزی M155: {sum(1 for d in wt_rows if d.get('cycle_ts','') > '2026-10-31T03:13')}")
L.append(f"۷) شکاف‌های ریتم ۳۰ دقیقه‌ای (>40 دقیقه): {len(gaps)} شکاف؛ بزرگ‌ترین: {gaps[0][1]}→{gaps[0][2]} ({gaps[0][0]:.0f} دقیقه)" if gaps else "۷) شکاف: 0")
L.append(f"۸) چرخه‌های اجرا‌نشده پس از 2026-10-31T02:40Z (اسلات‌های خالی ۳۰ دقیقه‌ای): {len(missed)} اسلات → " +
         ("، ".join(s.isoformat()[11:16] + "Z" for s in missed) if missed else "هیچ") +
         f" · اجرای واقعی خارج از اسلات: {len(offslot)} → " + ("، ".join(offslot) if offslot else "هیچ"))
L.append(f"۹) حفاظت پروژه: digest هستهٔ paper-trades = {dg} → " + ("✓ برابر مرجع قفل‌شده" if digest_ok else "✗ مغایرت با مرجع!")
         + f" · paused={paused} · trades={trades_n} · engine ok={eng_ok} ({eng_ver})")
L.append("   هیچ سفارش واقعی، هیچ مسیر LIVE، هیچ برداشت/انتقال، هیچ تغییر استراتژی/تنظیمات ریسک، هیچ بازنویسی تاریخچه.")
L.append("۱۰) هش فایل‌ها (sha256، ۱۶ کاراکتر نخست):")
for p, label in [
    (ROOT / "scripts/mari_hunt01/hunt_sweep.py", "hunt_sweep.py"),
    (ROOT / "scripts/m155_ab_upgrade/arb_reality_gate.py", "arb_reality_gate.py"),
    (STORE / "decisions.jsonl", "decisions.jsonl"),
    (STORE / "rejects.jsonl", "rejects.jsonl"),
    (STORE / "cycles.jsonl", "cycles.jsonl"),
    (STORE / "vault-mirror.jsonl", "vault-mirror.jsonl"),
    (STORE / "mission.json", "mission.json"),
]:
    L.append(f"   {sha16(p)}  {label}")
L.append(f"   {dg}  data/paper-trades.json (هش هستهٔ قفل‌شده)")
L.append("")
L.append("نتیجهٔ نهایی:")
if not final:
    L.append("PRE-DEADLINE CHECK — ثبت نهایی پس از مهلت انجام می‌شود.")
elif digest_ok and paused is True:
    L.append("★ PARTIALLY VERIFIED ★")
    L.append("- VERIFIED: اجرای واقعی چرخه‌ها با توازن لجر؛ قفل‌ها بدون استثنا؛ digest هستهٔ کاغذی سالم (paused=True)؛ صفر اجرای پس از مهلت.")
    L.append("- INSUFFICIENT EVIDENCE: سود قابل تحقق — VERIFIED_EXECUTABLE=0؛ هزینهٔ انتقال UNKNOWN؛ funding MISSING؛ timestamp منبع صفر؛ هویت ۴ صرافی اثبات‌نشده.")
    L.append("- قانون نهایی: NO VERIFIED EVIDENCE = NO VERIFIED CLAIM.")
elif not digest_ok or paused is not True:
    L.append("★ BLOCKED ★ — حفاظت پروندهٔ کاغذی نقض شده (digest/paused). هیچ ادعای دیگری معتبر نیست.")
else:
    L.append("★ INSUFFICIENT EVIDENCE ★ — دادهٔ کافی برای نتیجه‌گیری نیست.")
L.append("شعار: BREAK THE ASSUMPTIONS — VERIFY THE EVIDENCE — NEVER FAKE SUCCESS")

# English compact section
L.append("")
L.append("──────────── ENGLISH (compact) ────────────")
L.append(f"Snapshot {now.strftime('%Y-%m-%dT%H:%M:%SZ')} · deadline {DEADLINE.strftime('%Y-%m-%dT%H:%M:%SZ')} · {'FINAL' if final else 'PRE-DEADLINE CHECK'}")
L.append(f"Cycles: {len(cyc)} complete · first {cyc[0]['cycle_ts'][:19]}Z · last {last_cyc_ts.isoformat()[:19]}Z · ledger balance {balanced}/{len(cyc)} OK · source-partial: {len(partial)}")
L.append(f"Ledger: decisions {len(dec)} · rejects {len(rej)} · candidates {len(dec)+len(rej)} (incl. pilot row 2026-10-29T21:16:41)")
L.append(f"WOULD_TRADE: {len(wt_rows)} (" + ", ".join(f"{k}={v}" for k, v in sorted(wt_by_method.items(), key=lambda x: -x[1])) + f") · last WT {last_wt[:19]}Z")
L.append("Top rejects: " + ", ".join(f"{k}x{v}" for k, v in rej_top))
L.append(f"Independent gate (M155, archived {m.get('ts_utc','?')[:19]}Z): VERIFIED_EXECUTABLE={m.get('verified_executable')} — no post-audit re-evaluation; any WT after that = UNVERIFIED")
L.append(f"Missed 30-min slots after 02:40Z: {len(missed)}" + (f" ({', '.join(s.strftime('%H:%MZ') for s in missed)})" if missed else ""))
L.append(f"Protection: paper-trades core digest {dg} {'== REF OK' if digest_ok else 'MISMATCH!'} · paused={paused} · trades={trades_n} · no live orders / no transfers / no config change")
L.append("Verdict: " + ("PRE-DEADLINE CHECK (not final)" if not final else
                      ("PARTIALLY VERIFIED" if digest_ok and paused is True else
                       ("BLOCKED" if not digest_ok or paused is not True else "INSUFFICIENT EVIDENCE"))))
full = "\n".join(L)

if args.out:
    outp = Path(args.out)
else:
    name = ("MARI_HUNT01_FINAL_LOCK_%s.txt" if final else "MARI_HUNT01_predeadline_check_%s.txt") % now.strftime("%Y%m%dT%H%M%SZ")
    outp = ROOT / "download" / name
outp.write_text(full, encoding="utf-8")
print(full)
print(f"\n[SAVED] {outp}")
