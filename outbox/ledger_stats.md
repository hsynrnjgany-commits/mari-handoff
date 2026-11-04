# outbox/ledger_stats.md — آمار دفتر معاملات PAPER

تهیه: 2026-11-04 (فقط‌خواندنی، از روی خود فایل‌ها — بدون هیچ عدد از گزارش‌های قبلی)
قفل: READ ONLY | PAPER ONLY | NO LIVE ORDERS

## منبع

- فایل لجر: `data/paper-trades.json` (۹۲,۷۴۱ بایت · version=1 · paused=true)
- digest هسته (sha256 روی paused+trades+version، منطق verify_core): `6d8b7beb6d5a6c01` ✓ برابر مرجع
- full-file sha256[:16] = `a3e0b16b5ca83034` (فقط bookkeeping)
- اسکریپت محاسبه: `scripts/ro_ledger_stats_20261105.py` — همان منطق و همان تلورانس رسمی `report.py::paper_report` (eps=1e-9، سازگار با src/lib/paper/stats.ts)

## جدول آمار

| سنجه | مقدار |
| --- | --- |
| کل معاملات | ۷۴ |
| بسته‌شده (CLOSED) | ۷۴ |
| باز | ۰ |
| برد (realizedPnlPct > +1e-9) | ۱۹ |
| باخت (realizedPnlPct < −1e-9) | ۲۴ |
| سربه‌سر (|pnl| ≤ 1e-9) | ۳۱ — همه SL روی مرز کارمزد (باقیماندهٔ ممیز شناور ±1e-14) |
| خروج‌ها بر اساس دلیل | TP=۱۲ · SL=۵۴ · TIME=۸ |
| سود ناخالص (دلاری) | ‎+791.605 دلار |
| ضرر ناخالص (دلاری) | ‎−1802.249 دلار |
| خالص (دلاری) | ‎−1010.644 دلار |
| سود ناخالص (واحد درصد) | ‎+31.4051 |
| ضرر ناخالص (واحد درصد) | ‎−29.9167 |
| خالص (واحد درصد) | ‎+1.4883 |
| Win Rate | ۴۴٫۱۸۶٪ |
| Profit Factor (دلاری) | ۰٫۴۳۹۲ |
| Profit Factor (درصدی) | ۱٫۰۴۹۸ |
| بهترین معامله | ANIMEUSDT ‎+6.9٪ |
| بدترین معامله | NEARUSDT ‎−3.08٪ |

## فرمول‌ها (عین منطق رسمی)

- برد: `realizedPnlPct > +1e-9` — باخت: `realizedPnlPct < −1e-9` — سربه‌سر: `|realizedPnlPct| ≤ 1e-9`
- سود/ضرر دلاری هر معامله: `realizedPnlPct/100 × sizeUsd`
- Win Rate = `100 × برد ÷ (برد + باخت)` = `100 × 19 ÷ 43` = 44.186٪ — سربه‌سرها طبق منطق رسمی از WR حذف می‌شوند
- Profit Factor = `سود ناخالص ÷ |ضرر ناخالص|`
  - دلاری: `791.605 ÷ 1802.249` = 0.4392
  - درصدی: `31.4051 ÷ 29.9167` = 1.0498

## یادداشت شفافیت دربارهٔ sizeUsd

- ۵۸ رکورد از ۷۴ فیلد `sizeUsd` دارند؛ ۱۶ رکورد ندارند.
- در جمع دلاریِ رسمی، رکورد بدون `sizeUsd` با سهم صفر جمع می‌شود (منطق `report.py`).
- جمع درصدی (واحد درصد) هر ۷۴ را هم‌وزن می‌شمارد. به همین دلیل PF دلاری (0.4392) و PF درصدی (1.0498) واگرا هستند — هر دو از خود فایل محاسبه شده و هر دو گزارش شد.

## error ledger

- فایل error ledger اختصاصی برای معاملات وجود خارجی ندارد (جستجو شد: الگوی `*error*` در data/، همهٔ `*.jsonl`ها، مراجع error_ledger/errors.jsonl در کد — هیچ).
- ثبت‌کنندهٔ واقعی خطاهای عملیاتی: `scripts/mari_telegram/send-log.jsonl` (ستون error) + `scripts/mari_telegram/job_state.json` و `heartbeat.json` (ستون error) + `data/auth/login-log.jsonl` (لاگ ورود).
- آمار send-log.jsonl: ۸۵ ردیف کل، ۴ ردیف با خطا.

### متن ۳ خطای آخر (عیناً از فایل)

1. `2026-11-03T14:40:41Z · type=2h · delivered=false · error=TimeoutError: The read operation timed out`
2. `2026-10-31T18:37:38Z · type=2h · delivered=false · error={"ok":false,"error_code":401,"description":"Unauthorized"}`
3. `2026-10-31T17:48:13Z · type=short · delivered=false · error={"ok":false,"error_code":401,"description":"Unauthorized"}`

(چهارمین خطای تاریخی: `2026-10-30T06:19:55Z · type=hunt · Bad Request: message is too long`)

## دلیل نوشته‌شدن «آخرین خطا: هیچ» در گزارش قبلی

گزارش‌ها فقط ستون error آخرین اجراها را می‌خوانند (job_state/heartbeat/send-log). در لحظهٔ گزارش‌گیری، آخرین اجراها error=null بودند و همهٔ ارسال‌های اخیر delivered=true؛ بنابراین «هیچ» دربارهٔ وضعیت جاری درست بود اما دربارهٔ کل تاریخچه نیست — کل لاگ ۴ خطای تاریخی دارد که آخرینشان TimeoutError در 2026-11-03T14:40:41Z است و ارسال‌های بعد از آن همگی موفق بوده‌اند.
