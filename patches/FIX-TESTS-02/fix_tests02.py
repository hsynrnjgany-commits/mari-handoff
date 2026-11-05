#!/usr/bin/env python3
# FIX-TESTS-02 — هماهنگ کردن تست‌ها با FIX-RETRO-01 و لغزش ۰٫۰۵ + نشانگر صریح برای معاملهٔ تازه.
# قفل: PAPER ONLY | NO LIVE ORDERS. به data/ دست نمی‌زند. هیچ کلیدی لازم نیست.
# اجرا از ریشهٔ پروژه:   python3 fix_tests02.py --dry-run   سپس   python3 fix_tests02.py
# هر ویرایش فقط وقتی انجام می‌شود که متن لنگر دقیقاً یک بار پیدا شود؛ وگرنه هیچ فایلی عوض نمی‌شود.
import sys, re, glob, os

DRY = "--dry-run" in sys.argv
plan, errors = [], []


def edit(path, old, new, label):
    if not os.path.exists(path):
        errors.append(f"{label}: فایل نیست — {path}")
        return
    s = open(path, encoding="utf-8").read()
    if new in s:
        print(f"SKIP (قبلاً اعمال شده) — {label} — {path}")
        return
    n = s.count(old)
    if n != 1:
        errors.append(f"{label}: لنگر {n} بار پیدا شد (باید ۱ باشد) — {path}")
        return
    plan.append((path, s.replace(old, new, 1), label))


# A) موتور: معاملهٔ تازه با نشانگر صریح = زمان ورود (قاعدهٔ «معاملهٔ قدیمی بدون نشانگر» دیگر به معاملهٔ تازه نمی‌رسد)
edit("src/lib/paper/engine.ts",
     "    lastCheck: now,\n    mfePct: 0,",
     "    lastCheck: now,\n    evalCursorMs: entryTime, // FIX-TESTS-02: معاملهٔ تازه — ارزیابی از نخستین کندل پس از ورود\n    mfePct: 0,",
     "A engine.ts")

# B) t4: فیکسچرها «معاملهٔ تازه» اند، نه «قدیمی ارزیابی‌شده» — نشانگر = زمان ورود
t4 = [p for p in glob.glob("**/t4_exits.mjs", recursive=True) if "node_modules" not in p]
if not t4:
    errors.append("B t4: هیچ t4_exits.mjs پیدا نشد")
for p in t4:
    edit(p, "lastPrice: 100, lastCheck: now, mfePct: 0,",
         "lastPrice: 100, lastCheck: now, evalCursorMs: entryTime, mfePct: 0,", "B t4")

# C) t_slip: مقدار تنظیم‌شده ۰ یا ۰٫۰۵ مجاز؛ حساب واحد با لغزش ۰ سنجاق می‌شود
edit("tests/test_slippage_cost.ts",
     'check("پیش‌فرض لغزش = ۰", PAPER_PARAMS.slippagePctPerSide === 0, `${PAPER_PARAMS.slippagePctPerSide}`);',
     'check("لغزش تنظیم‌شده ۰ یا ۰٫۰۵", [0, 0.05].includes(PAPER_PARAMS.slippagePctPerSide), `${PAPER_PARAMS.slippagePctPerSide}`);\n'
     '(PAPER_PARAMS as any).slippagePctPerSide = 0; // FIX-TESTS-02: حساب واحد روی هزینهٔ پایهٔ ۰٫۱٪',
     "C t_slip")

# D) test-paper-stats (هر دو نسخه): حساب واحد روی هزینهٔ پایه سنجاق می‌شود
for p in ["tests/test-paper-stats.ts", "scripts/test-paper-stats.ts"]:
    if not os.path.exists(p):
        errors.append(f"D: فایل نیست — {p}")
        continue
    s = open(p, encoding="utf-8").read()
    m = re.findall(r'^import \{[^}]*\} from "([^"]*)/pnl";$', s, re.M)
    if len(m) != 1:
        errors.append(f"D: خط import pnl {len(m)} بار پیدا شد — {p}")
        continue
    line = next(l for l in s.splitlines() if re.match(r'^import \{[^}]*\} from "[^"]*/pnl";$', l))
    edit(p, line + "\n",
         line + f'\nimport {{ PAPER_PARAMS as __PP }} from "{m[0]}/types";\n'
         '(__PP as any).slippagePctPerSide = 0; // FIX-TESTS-02: حساب واحد روی هزینهٔ پایهٔ ۰٫۱٪\n',
         "D paper-stats")

if errors:
    print("خطا — هیچ فایلی عوض نشد:")
    for e in errors:
        print("  " + e)
    sys.exit(1)
for path, s, label in plan:
    print(("DRY " if DRY else "OK  ") + f"{label} — {path}")
    if not DRY:
        open(path, "w", encoding="utf-8").write(s)
print("پایان:", "dry-run بدون خطا" if DRY else f"{len(plan)} ویرایش اعمال شد")
