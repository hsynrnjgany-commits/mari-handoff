# HANDOFF_NOTES — MARI Paper-Trading Pipeline

تاریخ: 2026-11-04 · trace: 1a1a7161b52fcbc1 · مأموریت: HANDOFF-PUBLIC-01
قفل پروژه: **PAPER ONLY | NO LIVE ORDERS | READ-ONLY stores** — هیچ کلید/توکنی در این مخزن نیست و نباید باشد.

## ۱) درخت پوشه‌ها

```
mari-handoff/
├── HANDOFF_NOTES.md            ← همین فایل
├── sample_decisions.jsonl      ← ۵۰ خط آخر decisions.jsonl (نمونهٔ واقعی خروجی gate)
├── scripts/
│   ├── ai_gateway/             ← دروازهٔ AI (deepseek/glm) برای حسابرسی COVERAGE-01
│   ├── mari_hunt01/            ← موتور شکار آربیتراژ (sweep/gate/report) + universe.json
│   │   └── (store/ عمداً حذف شد — دادهٔ عملیاتی)
│   ├── mari_telegram/          ← گزارش‌سنج تلگرام (فایل‌های .py؛ state/logها حذف شدند)
│   ├── mari_deriv/             ← جمع‌آوری funding/OI از bybit+toobit (با store نمونه)
│   ├── mari_megatrend/         ← اسکنر مگاترند + دادهٔ کندل 1h (67 نماد)
│   ├── m140_tick_vault/        ← اسنپ‌شات تیک چند-منبعی (8 منبع، p50 latency)
│   └── m144_adversarial/       ← آزمون خصمانهٔ استراتژی (shadow/replay/stats)
└── tests/                      ← تست‌های gate/sweep + اسکریپت‌های runtime
```

## ۲) متغیرهای محیطی مورد انتظار — **فقط نام، بدون هیچ مقدار**

| نام | نقش |
|---|---|
| `MARI_TELEGRAM_TOKEN` | توکن بات تلگرام برای ارسال گزارش |
| `TELEGRAM_BOT_TOKEN` | نام جایگزین در برخی ماژول‌ها |
| `DEEPSEEK_API_KEY` | ارائه‌دهندهٔ AI حسابرسی |
| `ZAI_API_KEY` | ارائه‌دهندهٔ AI حسابرسی (GLM) |
| `GLM_MODEL` | نام مدل GLM (پیش‌فرض در کد) |
| `GH_TOKEN` / `GITHUB_TOKEN` | فقط برای عملیات push موقت؛ هرگز در کد ذخیره نمی‌شود |

کلیدهای صرافی (Toobit و…) از کانال امن خارج از این مخزن خوانده می‌شوند (vault-private — عمداً حذف شده).
نکته: در زمان تهیهٔ این فایل، کلیدهای DEEPSEEK/ZAI در محیط اجرا موجود نبود → حسابرسی AI با `SKIPPED_NO_KEY` رد می‌شود.

## ۳) وضعیت کار (به وقت 2026-11-04 ~11:24Z)

- **خط داده زنده**: snapshot هر ~۲h با ۸ منبع سالم؛ آخرین چرخه: 14,735 ردیف نرمال، 5,752 پایهٔ منطبق، p50=0.043s
- **پوشش تووبیت**: ۵۱۰ از ۵۱۰ جفت USDT در هر چرخه (cursor=0، 26 دستهٔ ۲۰تایی، بدون 418/429)
- **تصمیم‌ها**: امروز ۳ چرخهٔ sweep با decisions_written=8/10/10 و **would_trade=0** — هنوز سیگنال قابل‌معاملهٔ واقعی ثبت نشده
- **حسابرسی COVERAGE-01**: قالب آماده است ولی بدون کلید AI حکم نمی‌دهد (NO_REAL_VERDICT)
- **M144 shadow**: parity 36/36=1.0، day 4.61، ۱۰ معاملهٔ بستهٔ اخیر +8.03% خالص (paper)
- **مگاترند**: اسکن هر ۲۲h؛ مشتقات: ۵۱۰ ردیف/چرخه (funding/OI پوشش ۳۴۸)
- **paper-trades.json**: خارج از این مخزن؛ digest مرجع `6d8b7beb6d5a6c01` (74 trades، paused)

## ۴) باگ شناخته‌شدهٔ باز (مهم برای تحویل‌گیرنده)

`mari_hunt01/hunt_sweep.py` (~خطوط ۱۳۶-۱۴۴): چک `min_cycles=3` برای frozen_quote **طول کل تاریخچه** را
می‌سنجد نه تعداد تکرار همان (symbol, venue, ask, bid) → F1 (frozen_quote) تقریباً ۱۰۰٪ false-positive است
(301 ردیف F1 در ۷ روز؛ فقط ۳ مورد واقعی ≥3 تکرار). اصلاح پیشنهادی: شمارش تکرار متوالی per-key.
مأموریت pending: **FIX-FROZEN-01**.

## ۵) نمونهٔ خروجی اسکریپت‌ها (مقادیر حساس سانسور/حذف شده)

**m140_tick_vault/snapshot.py**:
```json
{"ok": true, "cycle_ts": "2026-11-04T11:20:41Z", "sources_ok": 8, "normalized_rows": 14735,
 "matched_bases": 5752, "p50": 0.0427, "pos_tob50": 64, "suspect": 55, "l2_archived": 3}
```

**mari_hunt01/hunt_sweep.py** (خلاصهٔ toobit_coverage):
```json
{"ok": true, "decision_ts_utc": "2026-11-04T11:21:53Z", "sources_ok": "8/8",
 "decisions_written": 10, "would_trade": 0, "gate_status_counts": {"UNAVAILABLE": 2, "UNVERIFIED": 8},
 "toobit_coverage": {"symbols_processed": 510, "batches": 26, "stopped": "completed",
 "rate_limit_stop": null, "no_signal": 430, "no_cross_venue": 39, "rejects_written": 31}}
```

**mari_deriv/collect.py**:
```json
{"ok": true, "run_id": "DERIV-20261104T112339Z", "rows_written": 510, "funding_covered": 348,
 "oi_covered": 348, "sources": {"bybit_funding_oi": "ok(826 sym)", "toobit_qv_24h": "ok(1104 sym)"}}
```

## ۶) قراردادهای امنیتی این مخزن

- تک‌کامیت تازه؛ هیچ تاریخی از مخزن اصلی نمی‌آید
- حذف‌شده‌ها: `.env*`، `vault-private`، هر فایل key/secret/token، `send-log.jsonl`، `paper-trades.json`،
  `cache.json`، `__pycache__`، `node_modules`، `scripts/test-vault.ts`، `scripts/m74/out/raw/cg_markets_pages.json`
- دو اسکن مستقل الگوهای `ghp_ / github_pat_ / sk- / botNN: / API_KEY= / SECRET= / TOKEN= / PRIVATE KEY`
  قبل از push اجرا شده؛ فایل‌های مثبت حذف و در گزارش صرفاً با نام اعلام می‌شوند
