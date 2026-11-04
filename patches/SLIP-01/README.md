# SLIP-01 — لغزش و هزینهٔ قابل تنظیم + ثبت هزینه در هر معامله

قفل: READ ONLY | PAPER ONLY | NO LIVE ORDERS. هیچ کلید یا توکنی در این پوشه نیست و نباید باشد.

## چه چیزی عوض می‌شود
- `types.ts`: پارامتر جدید `slippagePctPerSide` (پیش‌فرض **۰**، یعنی رفتار فعلی دست‌نخورده) و فیلد اختیاری `costPctApplied` روی هر معامله.
- `pnl.ts`: `roundTripCostPct()` (= کارمزد + ۲×لغزش) و `netPctWithCost()`.
- `engine.ts`: هنگام بستن معامله هزینهٔ اعمال‌شده ثبت می‌شود؛ قیمت سربه‌سر (BE) با هزینهٔ کل حساب می‌شود.
- `stats.ts`: بازمحاسبهٔ آمار از `costPctApplied` استفاده می‌کند؛ معاملات قدیمی (بدون این فیلد) همان ۰٫۱٪ قبلی را می‌گیرند، پس آمار تاریخچه تکان نمی‌خورد.

## نحوهٔ اعمال (از ریشهٔ پروژه، یعنی همان جایی که پوشهٔ `src/` هست)
```
patch -p1 --dry-run < patches/SLIP-01/slip01.patch   # اول فقط آزمایش
patch -p1 < patches/SLIP-01/slip01.patch             # اگر آزمایش بدون خطا بود
cp patches/SLIP-01/test_slippage_cost.ts tests/test_slippage_cost.ts
npx esbuild tests/test_slippage_cost.ts --bundle --platform=node --format=esm --outfile=/tmp/t_slip.mjs && node /tmp/t_slip.mjs data/paper-trades.json
```
انتظار: `نتیجه: 21/21 PASS`. اگر `esbuild` نصب نبود: `npm i -D esbuild`.
اگر `--dry-run` خطا داد، فقط همان خطا را گزارش کن و چیزی را دستی بازنویسی نکن.

بعد از آن، تست‌های موجود `t1` تا `t7` و `test-paper-stats.ts` را هم اجرا کن و نتیجه را گزارش بده.
`engine.ts` را من فقط از نظر نحوی بررسی کرده‌ام (روی اپ واقعی اجرا نشده)؛ اجرای تست‌های موجود همین را پوشش می‌دهد.

## خیلی مهم
- پیش‌فرض لغزش صفر است؛ پچ را اعمال کن ولی `slippagePctPerSide` را **تغییر نده**، مگر وقتی رییس صریحاً بگوید.
- اگر روزی روشن شود (مثلاً `0.05`)، فقط معاملات «تازه» با هزینهٔ جدید بسته می‌شوند و آمار باید جدا از قبلی‌ها خوانده شود.
- `data/paper-trades.json` را دست نزن. دایجست هسته باید همان `6d8b7beb6d5a6c01` بماند.

## v2_stats.py
اسکریپت فقط‌خواندنی: آمار را جدا برای v1 و v2 و با سناریوهای هزینهٔ ۰٫۱۰ و ۰٫۲۲ و ۰٫۳۰ درصد حساب می‌کند.
```
python3 -I patches/SLIP-01/v2_stats.py data/paper-trades.json
```
