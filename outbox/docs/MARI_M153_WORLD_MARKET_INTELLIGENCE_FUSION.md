# MARI — M153: WORLD MARKET INTELLIGENCE FUSION & PROFIT HARVESTING

| فیلد | مقدار |
|---|---|
| پروژه | MARI — World Market Core |
| شناسه | M153 |
| تاریخ مرجع | 2026-10-31 |
| اولویت | CRITICAL — ARCHITECTURE & RESEARCH |
| نوع اجرا | FORENSIC AUDIT \| KNOWLEDGE RECOVERY \| ARCHITECTURE \| PAPER RESEARCH \| INDEPENDENT VALIDATION |
| اصل بنیادین | BREAK THE ASSUMPTIONS — VERIFY THE EVIDENCE — NEVER FAKE SUCCESS |
| قفل امنیتی | READ ONLY \| PAPER ONLY \| NO LIVE ORDERS |
| وضعیت نهایی | **PARTIAL** (دلیل در بخش ۱۰) |
| سند مرجع معماری مادر | `docs/architecture/MARI_CORE_DOCTRINE_001.md` (sha256 cf02820a…53de2 — دست‌نخورده) |
| ثبت در worklog | Task 154 (اولین شمارهٔ آزاد واقعی؛ Task 153 قبلاً برای M152 استفاده شده بود) |

> هیچ سفارش واقعی، برداشت، انتقال وجه، تغییر موجودی واقعی، افشای کلید خصوصی یا دسترسی معاملاتی انجام نشد.

---

## بخش ۰ — مرحلهٔ صفر: قفل، ممیزی و حفاظت (گزارش واقعی)

1. **Git**: HEAD=`cb4b5fa5c391bf596abcbd85da73dad240adc2db`، branch=`main`، **remote=ندارد (REMOTE_COUNT=0)** ⇒ هرگونه ادعای push به GitHub غیرممکن و غیرصادقانه است. آخرین commitهای ثبت‌شدهٔ قبلی: `3440eb4` (دکترین) و `988cb86`.
2. **گزارش‌های M140-M152**: همه بازیابی و تطبیق داده شدند (بخش ۲). دو پیاده‌سازی متفاوت M143 تأیید و تفکیک شد: `scripts/m143_trend/` (موتور) و `scripts/m143_profit_runner/` (پژوهش دوم).
3. **CORE-DOCTRINE-001**: `docs/architecture/MARI_CORE_DOCTRINE_001.md` — sha256 `cf02820ae106e6d328fa76cee592d8d04f8946ba26a1514f1260820536532de2` — دست‌نخورده ماند.
4. **فایل‌های محافظت‌شده — SHA256 قبل از مأموریت**:
   - `data/paper-trades.json` = `35a6a1601959d1e3c3975948d163add420c9c76c07e05ba6d1e85cb12a086558`
   - `scripts/m3_engine.py` = `4470a35b228b2134ef707d33546dbde00be04ad3318f86564ed5d54458dc98a7`
   - `scripts/m143_trend/engine143.py` = `2aa9436f2b425967765378c1d337e5cee9561898e5546d4fb22b4809264aeac4`
   - `docs/architecture/MARI_CORE_DOCTRINE_001.md` = `cf02820a…de2`
   - `docs/mother-document.md` = `d73b7de6472a25a027e2553fa236dc2d004fb2d783f1bb26d344f5faa34a71f1`
5. **یافتهٔ ممیزی paper-trades.json**: در ابتدای مأموریت فایل نسبت به HEAD تغییر دیده بود (`M` در git status). بررسی دقیق diff: فقط ۲ خط timestamp (`updatedAt` و `lastQuality.at`) عوض شده بود؛ `paused:true` و آرایهٔ trades دست‌نخورده. **علت: ضربان Shadow Paper cron فعال (روزانه ۰۹:۳۰ تهران تا 2026-11-29)** — تغییر موردانتظار و خوش‌خیم؛ فایل وارد commit نشد و هیچ عددی از آن تغییر نکرد.
6. **همان‌جایی با مأموریت فعال**: M153 در ساعت ۰۱:۲۸ تهران اجرا شد (۸ ساعت قبل از cron بعدی) — هیچ تداخل پردازشی.
7. **نه reset، نه clean، نه حذف، نه بازنویسی تاریخچه** انجام شد.

---

## بخش ۱ — متن کامل مرجع مأموریت M153 (عیناً و بدون حذف)

> متن زیر عیناً فرمان مدیر پروژه است و برای رعایت الزام «بدون حذف» کامل ذخیره شده است.

---

MARI MISSION 153

WORLD MARKET INTELLIGENCE FUSION & PROFIT HARVESTING

مأموریت یکپارچه‌سازی هوش بازار جهانی، حافظهٔ دائمی و عملکرد قابل‌اندازه‌گیری

پروژه: MARI — World Market Core
شناسه: M153
تاریخ مرجع: 2026-10-31
اولویت: CRITICAL — ARCHITECTURE & RESEARCH
نوع اجرا: FORENSIC AUDIT | KNOWLEDGE RECOVERY | ARCHITECTURE | PAPER RESEARCH | INDEPENDENT VALIDATION

اصل بنیادین:

BREAK THE ASSUMPTIONS — VERIFY THE EVIDENCE — NEVER FAKE SUCCESS

قفل امنیتی غیرقابل‌تغییر:

READ ONLY | PAPER ONLY | NO LIVE ORDERS

هیچ سفارش واقعی، برداشت، انتقال وجه، تغییر موجودی واقعی، افشای کلید خصوصی یا دسترسی معاملاتی مجاز نیست.

بخش اول — فرمان مدیر پروژه

این مأموریت ادامهٔ مستقیم پژوهش‌های MARI است، نه شروع دوبارهٔ پروژه.

هدف، تبدیل دانش انباشته‌شده از چهار شاخهٔ پژوهشی به یک معماری هماهنگ، قابل‌اندازه‌گیری، قابل‌بازتولید و مقاوم در برابر خطاست.

MARI نباید فقط سیگنال صادر کند. باید بتواند:

1. بازار جهانی را پایش کند.
2. فرصت‌های واقعی را از حرکت‌های تصادفی جدا کند.
3. روندهای صعودی و نزولی را تشخیص دهد.
4. شروع، ادامه، ضعف و ابطال روند را ارزیابی کند.
5. سودهای کوچک را پس از هزینه‌ها بررسی و مدیریت کند.
6. فرصت‌های بزرگ را به دلیل رسیدن به اولین هدف سود زودهنگام از دست ندهد.
7. از تبدیل سود شناور به زیان جلوگیری کند.
8. ریسک هم‌زمانی و هم‌بستگی را کنترل کند.
9. فرصت‌های ازدست‌رفته را اندازه‌گیری کند.
10. یادگیری‌های مثبت، منفی، متناقض و نامشخص را برای همیشه قابل‌ردیابی نگه دارد.

اصل مدیریتی پروژه:

«دو صد گفته چون نیم کردار نیست؛ اکنون زمان آن است که دانش انباشته‌شدهٔ MARI به عملکرد قابل‌اندازه‌گیری تبدیل شود.»

بخش دوم — مرحله صفر: قفل، ممیزی و حفاظت

قبل از هر اقدامی:

1. Git HEAD، branch، commit، remote، وضعیت working tree و تغییرات اخیر را ثبت کن.
2. گزارش‌های M140 تا M152 و وضعیت آخرین مأموریت‌ها را بررسی کن.
3. CORE-DOCTRINE-001 را به‌عنوان مرجع معماری دائمی شناسایی کن.
4. فایل‌های محافظت‌شده را شناسایی و SHA256 آن‌ها را ثبت کن.
5. وضعیت Paper Engine و Shadow Paper را بررسی کن.
6. اگر مأموریت یا پردازش قبلی فعال است، هیچ پردازش متداخل ایجاد نکن.
7. اگر "data/paper-trades.json" یا هر فایل محافظت‌شده برخلاف انتظار تغییر کرده است، متوقف شو و علت را گزارش کن.
8. هیچ فایل محافظت‌شده‌ای را تغییر نده.
9. هیچ reset، clean، حذف، بازنویسی تاریخچه، تغییر موجودی، تغییر سفارش یا تغییر ساختاری پرخطر انجام نده.
10. وابستگی پولی، API پولی یا سرویس خارجی پولی را اجباری نکن.

مجوز مشخص این مأموریت:

ایجاد اسناد جدید، ثبت دانش، ایجاد فهرست ارجاع، ساخت تست مستقل و توسعهٔ نمونهٔ پژوهشی در مسیر جداگانه مجاز است؛ مشروط بر اینکه به موتورهای موجود و فایل‌های محافظت‌شده دست نزند.

برای ثبت در GitHub:

- ابتدا سند و تغییرات را در مسیر مستقل ایجاد کن.
- تغییرات را قبل از ثبت نهایی با diff و SHA256 گزارش کن.
- فقط فایل‌های جدید این مأموریت و ارجاع‌های ضروری به سند مادر مجاز به commit هستند.
- commit فقط برای همین تغییرات محدود مجاز است.
- push به remote فقط در صورت دسترسی مجاز، نبود تعارض و تأیید صحت محتوای commit انجام شود.
- اگر هر فایل خارج از محدوده تغییر کرده، آن را وارد commit نکن.
- هیچ فایل محافظت‌شده‌ای را به commit اضافه نکن.
- اگر push ممکن نیست، گزارش دقیق بده؛ ادعای ذخیره در GitHub نکن.

بخش سوم — ثبت دائمی مأموریت در معماری و مغز دانشی MARI

این مأموریت نباید فقط در worklog ثبت شود.

ساختار پیشنهادی:

"docs/architecture/MARI_M153_WORLD_MARKET_INTELLIGENCE_FUSION.md"

در صورت وجود ساختار مناسب‌تر، ابتدا آن را ممیزی کن و سپس مسیر موجود را حفظ کن.

الزامات ثبت:

1. متن کامل مرجع این مأموریت باید بدون حذف در سند اصلی ذخیره شود.
2. خلاصهٔ اجرایی در "docs/mother-document.md" به‌صورت افزایشی اضافه شود.
3. CORE-DOCTRINE-001 دست‌نخورده بماند و فقط از آن ارجاع گرفته شود.
4. شناسهٔ مأموریت در worklog با شمارهٔ بعدی آزاد و واقعی ثبت شود؛ شناسهٔ Task را حدس نزن.
5. در صورت وجود Knowledge Registry یا Research Index، M153 به آن متصل شود.
6. اگر Registry وجود ندارد، ابتدا طراحی مستقل ارائه کن؛ بدون مجوز ساختاری آن را به موتور عملیاتی تبدیل نکن.
7. برای سند، خلاصه، نتایج و manifest هش SHA256 ثبت کن.
8. نسخهٔ اصلی متن مرجع، نسخهٔ به‌روزشده و تاریخچهٔ تغییرات قابل‌ردیابی باشند.

اتصال به مغز ربات:

منظور از اتصال به مغز ربات، ثبت قابل‌دسترسی و نسخه‌بندی‌شده در حافظهٔ دانشی معماری است؛ نه اینکه صرفاً یک فایل ساخته شود و ادعا کنیم موتور آن را می‌خواند.

باید بررسی کنی:

- ربات دانش خود را از کدام فایل‌ها یا Registry دریافت می‌کند؟
- آیا اسناد معماری در مسیر تصمیم‌گیری پژوهشی قابل‌دسترسی‌اند؟
- آیا دستیار می‌تواند مأموریت‌ها، فرضیه‌ها و نتایج ردشده را بازیابی کند؟
- آیا منبع و نسخهٔ هر قانون مشخص است؟
- آیا تعارض میان دو قانون شناسایی می‌شود؟
- آیا نسخهٔ قدیمی می‌تواند به اشتباه به‌عنوان قانون فعال استفاده شود؟

اگر اتصال واقعی به runtime وجود ندارد، صریحاً ثبت کن:

"KNOWLEDGE_DOCUMENT_REGISTERED — RUNTIME_INTEGRATION_NOT_VERIFIED"

هرگز اتصال ظاهری را اتصال واقعی معرفی نکن.

بخش چهارم — بازیابی چهار شاخهٔ دانش

چهار شاخه باید به یک ساختار دانش مشترک متصل شوند.

A — TRADER DNA

بازیابی Mission 65 تا M68.2، Mission 77، Mission 142 و سایر پژوهش‌های مرتبط.

برای هر روش:

- صاحب روش و منبع اولیه
- تاریخ و منبع
- شرایط ورود و خروج
- تایم‌فریم و بازار مناسب
- مدیریت سرمایه
- حد ضرر و نگهداری سود
- محدودیت‌ها
- شواهد مستقل
- نتیجهٔ آزمایش MARI
- وضعیت: CONFIRMED / REJECTED / CONDITIONAL / UNTESTED

داستان موفقیت اشخاص، مدرک سودآوری نیست.

B — SUCCESSFUL IDEAS

تمام ایده‌های زیر و سایر موارد ثبت‌شده را بررسی کن:

Momentum، Trend Following، Breakout، Pullback، Volatility Expansion، Mean Reversion، Relative Strength، Relative Volume، Liquidity Sweeps، Market Structure Shift، Volume Profile، VWAP، Darvas Box، VCP، AMD، Session Structure، Liquidity Grab، Funding، Open Interest، Cross-Market Confirmation و Regime Detection.

هر فرضیه باید شرایط فعال‌شدن، شرایط ابطال و آزمون مستقل داشته باشد.

C — PROFESSIONAL MARKET VISUAL INTELLIGENCE

قابلیت محاسبه و اعتبار ابزارهای حرفه‌ای را بررسی کن:

Candlestick Structure، Multi-Timeframe Analysis، Market Structure، Support/Resistance، Volume Profile، VWAP، Relative Volume، Order Book Imbalance، Bid/Ask Spread، Liquidity Heatmap، Liquidation Clusters، Open Interest، Funding Rate، CVD/Delta، ATR، RSI، MACD، Bollinger Bands، Fibonacci، Breakout/Retest، Volatility Regime و BTC Dominance.

برای هر ابزار، منبع، کیفیت، تازگی، فرمول، تایم‌فریم، هم‌پوشانی، ارزش مستقل و محدودیت را ثبت کن.

دادهٔ غیرموجود را شبیه‌سازی نکن. وضعیت آن را "UNAVAILABLE" ثبت کن.

D — MATHEMATICAL RESEARCH

تمام نتایج مثبت و منفی را حفظ کن:

Probability، Expected Value، PF، Win Rate، MaxDD، Risk of Ruin، Position Sizing، Kelly، Volatility Scaling، ATR Risk، Bayesian Updating، Statistical Significance، Bootstrap، Monte Carlo، Walk-Forward، OOS، Multiple Testing Correction، Survivorship، Look-Ahead، Costs، Slippage، Funding و Execution Delay.

بخش پنجم — نتایج قطعی و محدودیت‌های مأموریت‌های قبلی

این قسمت باید پیش از هر طراحی جدید در حافظهٔ پژوهشی MARI ثبت شود.

5.1 CORE-DOCTRINE-001

طبق گزارش ثبت:

- PHASE 1 و PHASE 2 تکمیل شده‌اند.
- سند معماری در "docs/architecture/MARI_CORE_DOCTRINE_001.md" ثبت شده است.
- سند مادر به‌صورت افزایشی به‌روزرسانی شده است.
- commit گزارش‌شده: "3440eb4".
- آخرین commit گزارش‌شده در ادامه: "988cb86".
- قابلیت‌ها: IMPLEMENTED=12، PARTIAL=16، NOT IMPLEMENTED=11، NOT TESTED=1، BLOCKED=1.
- اجرای آربیتراژ پس از هزینه همچنان به علت "transfer_cost=UNKNOWN" مسدود است.

این اطلاعات را از گزارش‌ها دریافت کرده‌ای؛ قبل از استفادهٔ اجرایی، با وضعیت واقعی Repository تطبیق بده.

5.2 M143 تا M146 — موتور روند

دو گزارش متفاوت M143 وجود دارد:

- "scripts/m143_trend/"
- "scripts/m143_profit_runner/"

این دو را یکی فرض نکن.

M144 گزارش اول را بازپخش و خصمانه بررسی کرده است؛ نه اینکه تمام نتایج موتور دوم را تأیید کرده باشد.

نتایج مهم:

- NEW-A نسبت به OLD در چند آزمون جهت بهتری نشان داده است.
- CI سود مطلق در آزمون‌های اصلی شامل صفر بوده است.
- هزینهٔ 30bp مزیت NEW-A را از بین برده است.
- حذف Top5% سود، نتیجه را منفی کرده است.
- سوگیری بقا هنوز کامل حل نشده است.
- NEW-B در آزمون‌های اصلی شکست خورده است.
- هیچ‌یک مجوز ارتقای موتور اصلی را نگرفته‌اند.

M146:

- در فولدهای واقعی کرش، NEW-A نسبت به OLD جهت بهتری نشان داده است.
- CF1-6: NEW-A +400.73 دلار و PF1.064؛ OLD −1834.45 دلار و PF0.679.
- بااین‌حال حذف دُم Top5%، هزینهٔ 30bp و CI سود مطلق هر سه گیت ارتقا را رد کرده‌اند.
- CAP برتری معناداری بر NEW-A نداشته و آن خط بسته شده است.

این یافته‌ها را به‌معنای اثبات سودآوری قطعی NEW-A تفسیر نکن.

5.3 M148 — Trend Classifier

گزارش آزمون:

- T0: همانی engine143 برابر 12975/12975.
- T3: تشخیص CRASH با precision گزارش‌شده 100%، اما پوشش سمت ریسک فقط 65.6%.
- T4: UNKNOWN در warmup و گپ مصنوعی درست عمل کرده است.
- T5: همهٔ مؤلفه‌ها در تصمیم نقش دارند.
- T7: آزمون lookahead برابر 200/200.
- T8: سهم سمت ریسک در فولدهای کرش بالاتر از کنترل بوده است.
- T2: FAIL؛ همبستگی رتبه‌ای بازده آینده منفی و معکوس فرض روندی.
- T6: FAIL؛ پایداری برچسب 68.2%، کمتر از آستانهٔ 70%.

حکم: طبقه‌بندی چندعاملی و جداسازی وضعیت‌ها پژوهشی است؛ لبهٔ روندی تأیید نشده و hysteresis نیازمند آزمون مستقل است.

هیچ برچسبی به‌تنهایی مجوز خرید یا فروش نیست.

5.4 M149 — Profit Runner و خروج پنج‌مرحله‌ای

- STAGED: n=6281، net −913.49، PF0.813.
- NEW-A: n=4273، net +413.33، PF1.066.
- اختلاف زوجی STAGED−NEW-A برابر −0.19%/trade با CI منفی.
- Giveback بهتر به‌تنهایی اثبات لبه نیست.
- فروش پله‌ای پنج‌مرحله‌ای در این آزمون رد شده است.
- Trailing فعلاً مرجع مقایسه باقی می‌ماند.

این نتیجه مانع پژوهش آینده نیست؛ اما تکرار همان روش بدون فرضیهٔ جدید و آزمون مستقل ممنوع است.

5.5 M151 و M152 — G3

M151:

- G3 سقف هم‌زمانی 5 موقعیت، افت سرمایه را کاهش داد.
- G4 منع ورود در کرش سود را کاهش داد و رد شد.
- G5 نمونهٔ بسیار کوچک داشت.

M152:

- cap=5: فقط 36% سود پایه را حفظ کرد.
- cap=8 و cap=10 در CF1-6 تعادل بهتری نشان دادند.
- در پنجرهٔ OOS بازنده، G3 زیان مطلق را کاهش داد اما PF را بدتر کرد.
- آزمون زوجی حذف شد چون G3 زیرمجموعهٔ عین معاملات پایه است.

حکم: G3 فقط ابزار کنترل اکسپوژر است، نه تولیدکنندهٔ edge.

هیچ سقف موقعیتی به موتور اصلی منتقل نشود. capهای 8 و 10 فقط کاندیدای پژوهشی‌اند.

5.6 ENGINE A و M140 تا M142

- M140 داده‌های Tick Vault را از منابع عمومی جمع‌آوری می‌کند.
- M141 تحلیل‌گر Edge است.
- M142 شبیه‌ساز آربیتراژ است.
- هزینهٔ انتقال نامعلوم است.
- گیت اجرای آربیتراژ همچنان BLOCKED است.
- سودهای شبیه‌سازی‌شدهٔ محدود، اثبات سودآوری نیستند.

"WOULD_TRADE"، فرصت شناسایی‌شده است؛ نه معاملهٔ اجراشده و نه سود تحقق‌یافته.

بخش ششم — مأموریت جدید M153

M153 باید بر پایهٔ وضعیت موجود، نه با تکرار آزمایش‌های قبلی، انجام شود.

M153-A — Recovery and Baseline Audit

- بازیابی گزارش‌ها و artifactهای موجود.
- تطبیق مسیر، نسخه، hash و تاریخ.
- تفکیک نتایج قطعی، گزارش‌شده، متناقض و ناقص.
- شناسایی آزمایش‌های انجام‌شده و جلوگیری از تکرار بی‌دلیل.
- ارائهٔ baseline قابل‌بازتولید.

M153-B — Four Branches Evidence Inventory

برای هر چهار شاخه یک Knowledge Inventory ایجاد کن.

هر رکورد باید حداقل این فیلدها را داشته باشد:

"research_id"
"hypothesis_id"
"strategy_id"
"source_id"
"data_ref"
"dataset_hash"
"code_version"
"parameter_version"
"timeframe"
"market_regime"
"sample_size"
"gross_return"
"net_return"
"profit_factor"
"max_drawdown"
"confidence_interval"
"validation_status"
"falsification_conditions"
"limitations"
"timestamp"

نتیجهٔ منفی و متناقض حذف نشود.

M153-C — Unified Architecture

معماری یکپارچه را طراحی کن:

A. Global Market Scanner
B. Market Data Quality Engine
C. Trader DNA Knowledge Engine
D. Strategy Research Engine
E. Visual Market Intelligence Engine
F. Mathematical Validation Engine
G. Market Regime Classifier
H. Trend Intelligence Engine
I. Opportunity Ranking Engine
J. Intelligent Profit Runner
K. Risk and Portfolio Engine
L. Adversarial Evidence Engine
M. Paper Performance Dashboard

هر ماژول باید ورودی، خروجی، نسخه، منبع داده، کیفیت داده، محدودیت و وضعیت اعتبار داشته باشد.

هیچ ماژولی به‌تنهایی اختیار صدور مجوز معاملهٔ واقعی ندارد.

M153-D — Trend Intelligence

سه حالت پایه:

BULLISH / BEARISH / SIDEWAYS

و حالت‌های تفصیلی:

Early Trend، Trend Confirmation، Strong Trend، Trend Acceleration، Healthy Pullback، Trend Weakening، Distribution، Reversal Warning و Trend Invalidated.

اما ابتدا T2 و T6 در M148 را حل کن.

- برای T6، hysteresis را در نمونهٔ مستقل طراحی و آزمایش کن.
- برای T2، فرضیهٔ mean reversion در برابر trend following را جداگانه بررسی کن.
- هیچ تغییر پارامتری پس از مشاهدهٔ Test مجاز نیست.
- اگر بازده آینده در بازار فعلی معکوس است، آن را پنهان نکن.
- برچسب روند نباید مستقیماً به سیگنال معاملاتی تبدیل شود.

M153-E — Intelligent Profit Runner

سه روش خروج را مستقل آزمایش کن:

1. R-based exit.
2. ATR-based trailing.
3. Structure-based exit.

روش‌های ترکیبی فقط با فرضیهٔ ازپیش‌ثبت‌شده مجازند.

M149 نشان داده است که فروش پنج‌مرحله‌ای فعلی برتری ندارد. بنابراین همان نسخه بدون تغییر فرضیه تکرار نشود.

برای هر معامله:

- MFE
- MAE
- Peak Unrealized Profit
- Realized Profit
- Giveback
- Exit Efficiency
- Time in Trade
- Remaining Risk
- Net Return After Costs

محاسبه و ذخیره شود.

فرمول:

"Giveback = Peak Unrealized Profit - Realized Profit"

هدف، حفظ فرصت‌های کوچک و نگهداری کنترل‌شدهٔ موج‌های بزرگ است؛ نه فروش کورکورانه در سود کوچک و نه نگهداری کورکورانه تا چندصد درصد.

M153-F — Opportunity Scoring

امتیاز 0 تا 100 طراحی کن:

Trend Quality، Momentum، Relative Strength، Volume، Liquidity، Structure، Volatility، Multi-Timeframe Agreement، Derivatives، Cross-Market، Data Quality، Expected Net Return، Risk/Reward و Signal Freshness.

از دوباره‌شماری شواهد هم‌بسته جلوگیری کن.

امتیاز به‌معنای احتمال موفقیت نیست، مگر اینکه جداگانه کالیبره و خارج از نمونه تأیید شود.

M153-G — Global Market Capture

برای یک بازهٔ زمانی ثابت:

- Universe واقعی
- نمادهای معتبر
- داده‌های ناقص
- فرصت‌های واقعی
- فرصت‌های شناسایی‌شده
- فرصت‌های ازدست‌رفته
- False Positive
- False Negative
- Precision
- Recall
- F1
- Early Detection Rate
- Detection Delay
- Net Capture After Costs

اندازه‌گیری شود.

برچسب آینده فقط برای ارزیابی پس از وقوع استفاده شود و هرگز وارد ورودی مدل نشود.

حرکت‌های زیر به‌صورت دسته‌بندی گذشته بررسی شوند:

زیر 2%، 2–5%، 5–10%، 10–25%، 25–50%، 50–100%، 100–300% و بالاتر از 300%.

این دسته‌ها پیش‌بینی تضمینی آینده نیستند.

M153-H — Adversarial Validation

OLD، NEW-A، NEW-B و HYBRID را فقط در صورت وجود پیاده‌سازی مستقل و قابل‌بازتولید مقایسه کن.

- Train، Validation و Test زمانی جدا.
- هزینه و اسلیپیج یکسان.
- عدم نشت آینده.
- کنترل survivorship.
- حذف دُم سود.
- Bootstrap بلوکی.
- Multiple Testing Correction.
- حساسیت پارامترها.
- تحلیل جداگانهٔ Bull/Bear/Sideways/Crash/HighVol.
- ثبت تعداد معاملات و CI.

سه گیت قبلی M144/M146 را دوباره به‌عنوان نتیجهٔ تأییدشده گزارش نکن؛ فقط در صورت تغییر واقعی داده یا فرضیه، آزمون جدید با شناسهٔ مستقل تعریف کن.

M153-I — Paper Simulation

فقط در محیط جداگانه و ایزوله.

- هیچ اتصال سفارش واقعی.
- هیچ دسترسی معاملاتی.
- هیچ تغییر در Paper Engine موجود.
- هیچ دست‌کاری در "data/paper-trades.json".
- هیچ ادغام خودکار با Shadow Paper.
- هر دادهٔ جدید با زمان UTC و hash ثبت شود.

M153-J — Independent Final Audit

گزارش نهایی باید شامل:

- baseline و وضعیت شروع
- منابع بازیابی‌شده
- چهار شاخهٔ دانش
- معماری طراحی‌شده
- ماژول‌های واقعاً ساخته‌شده
- ماژول‌های صرفاً طراحی‌شده
- نتایج مستقل
- هزینه‌ها
- MDD و ریسک
- سودهای کوچک حفظ‌شده
- موج‌های بزرگ شناسایی‌شده
- فرصت‌های ازدست‌رفته
- Precision و Recall
- خطاها و محدودیت‌ها
- hash فایل‌های حساس قبل و بعد
- وضعیت Git
- تست‌ها و رگرسیون‌ها

در پایان دقیقاً یکی از این وضعیت‌ها:

"PASS" — تمام معیارهای اصلی با شواهد مستقل تأیید شده‌اند.

"PARTIAL" — بخشی از مأموریت انجام شده اما موارد مهم باقی مانده‌اند.

"BLOCKED" — محدودیت فنی، داده‌ای یا امنیتی مانع ادامه شده است.

تکمیل مراحل به‌تنهایی مجوز PASS نیست.

بخش هفتم — قوانین دائمی جلوگیری از خطا

1. هیچ نتیجهٔ پژوهشی بدون source، data_ref و hash معتبر نیست.
2. هیچ روش مشهور بدون آزمون مستقل وارد تصمیم‌گیری نمی‌شود.
3. هیچ شاخصی به‌تنهایی فرمان معامله صادر نمی‌کند.
4. UNKNOWN باید امکان NO TRADE را حفظ کند.
5. نتیجهٔ منفی هرگز حذف یا بازنویسی نمی‌شود.
6. هر فرضیه پیش از آزمون ثبت می‌شود.
7. تغییر پارامتر پس از مشاهدهٔ Test ممنوع است.
8. دادهٔ ناموجود با عدد ساختگی پر نمی‌شود.
9. "WOULD_TRADE" معاملهٔ واقعی نیست.
10. سود ناخالص، سود خالص نیست.
11. سود شناور، سود تحقق‌یافته نیست.
12. سود شبیه‌سازی‌شده، سابقهٔ عملکرد واقعی نیست.
13. کاهش Drawdown به‌تنهایی اثبات Edge نیست.
14. بهبود نسبت به OLD به‌تنهایی اثبات سودآوری نیست.
15. هیچ نتیجه‌ای مجوز سفارش واقعی ایجاد نمی‌کند.

بخش هشتم — دستور ذخیره‌سازی و ثبت در GitHub

پس از تکمیل ممیزی:

1. سند کامل M153 را در مسیر معماری ثبت کن.
2. متن مرجع کامل این مأموریت را بدون حذف در سند نگه دار.
3. خلاصهٔ مدیریتی را به mother-document اضافه کن.
4. شناسه و وضعیت را در worklog ثبت کن.
5. Knowledge Registry را به سند متصل کن، اگر ساختار معتبر آن موجود است.
6. تمام تغییرات را در یک manifest ثبت کن.
7. SHA256 قبل و بعد را ارائه کن.
8. diff را بررسی کن.
9. فقط تغییرات مجاز M153 را commit کن.
10. push فقط طبق مجوز محدود این مأموریت و پس از بررسی remote انجام شود.
11. نتیجهٔ commit و push را با شناسه و شواهد واقعی گزارش کن.

اگر GitHub در دسترس نیست، فقط بگو LOCAL DOCUMENT REGISTERED و GITHUB PUSH NOT VERIFIED.

اگر runtime ربات واقعاً سند را نمی‌خواند، ادعای اتصال به مغز ربات نکن.

بخش نهم — فرمان اجرای نهایی

ابتدا فقط ممیزی و بازیابی را انجام بده.

پس از آن، تا حدی که بدون نقض قفل‌ها و بدون تداخل با مأموریت‌های فعال ممکن است، مراحل برگشت‌پذیر و مستقل را اجرا کن.

هرجا نیاز به تغییر فایل محافظت‌شده، تغییر ساختاری پرخطر، دسترسی معاملاتی یا اقدام خارج از PAPER بود، متوقف شو و گزارش بده.

هیچ‌وقت برای تکمیل ظاهری مأموریت، نتیجهٔ ناقص را موفق اعلام نکن.

هدف نهایی MARI:

پیداکردن فرصت‌های واقعی از میان هزاران نماد، مدیریت سودهای کوچک، حفظ فرصت موج‌های بزرگ، تشخیص درست روند و محافظت از سرمایه؛ همه با شواهد مستقل و بدون افزایش بی‌ضابطهٔ ریسک.

BREAK THE ASSUMPTIONS. VERIFY THE EVIDENCE. NEVER FAKE SUCCESS.

---

## پیوست A — متن مرجع کامل مدیر پروژه (M148)

> متن اصلی ارائه‌شده برای M148 باید عیناً در این پیوست حفظ می‌شد (شامل تمام بخش‌های ۱۶گانهٔ M148).

**وضعیت: `SOURCE_TEXT_NOT_RECOVERED`**

- متن کامل ۱۶‌بخشی M148 نه در این پیام (که فقط دستور جایگذاری آمده)، نه در تاریخچهٔ گفتگوی در دسترس (خلاصه‌سازی شده)، و نه در مخزن (جستجوی `docs/`، `worklog.md`، `scripts/` — فقط ارجاع به M148 وجود دارد، متن کامل نیست) یافت نشد.
- طبق فرمان: جای خالی با حدس یا بازنویسی پر نمی‌شود؛ ثبت نسخهٔ کامل تا بازیابی متن متوقف می‌ماند.
- **آنچه از M148 محفوظ و قابل‌استناد است**: گزارش اجرای کامل M148 (آزمون‌های T0-T8 با اعداد) در `scripts/m148_trend_classifier/out/m148_tc_results.json` (sha256 75a09246…4840)، خلاصهٔ دکترین در mother-document و CORE-DOCTRINE-001، و ارجاع‌های worklog Task 148. اینها «اجرای M148» را پوشش می‌دهند، نه «متن فرمان M148».

---

## بخش ۲ — M153-A: بازیابی و Baseline قابل‌بازتولید

### 2.1 رجیستری مأموریت‌های بازیابی‌شده (با artifact واقعی و hash)

| مأموریت | artifact | SHA256 | وضعیت تفکیک‌شده |
|---|---|---|---|
| M140 Tick Vault | `scripts/m140_tick_vault/` | — (cron حذف شده؛ Job 484899) | گزارش‌شده |
| M141 Edge Analyzer | `scripts/m141_edge_analyzer/` | — | گزارش‌شده (drift p90=29bps/75s) |
| M142 Arb Sim | `scripts/m142_arb_sim/` | — | BLOCKED (transfer_cost=UNKNOWN) |
| M143 موتور | `scripts/m143_trend/engine143.py` | `2aa9436f…4aec4` | IMPLEMENTED — مرجع |
| M143 پروفیت‌رانر | `scripts/m143_profit_runner/` | — | پژوهش دوم — با M143 موتور یکی نیست |
| M144 Adversarial | `out/m144_step234_stats.json` و 4 فایل trades | — | نتایج قطعی (OLD f0123 = −864.66$ PF0.729) |
| M145 Verify | `out/m145_results.json` | `64870aa3…4d028` | قطعی (paired +0.221 [0.056,0.389]؛ مطلق شامل صفر؛ survivorship PARTIAL) |
| M146 Crash | `out/m146_pooled.json`، `m146_folds.jsonl` | `8dfe75d1…12ad`، `49b3a239…31a5` | قطعی (NEW-A +400.73/PF1.064؛ سه گیت FAIL) |
| M148 Classifier | `out/m148_tc_results.json` | `75a09246…4840` | 6/8 PASS؛ T2/T6 FAIL |
| M149 Staged | `out/m149_staged.json` | `85bf786c…adbd3` | REJECTED (۳ گیت FAIL) |
| M151 Combined | `out/m151_combined.json` | `eaf6703a…e34773` | G3 ابزار ریسک؛ G4 REJECTED |
| M152 G3 Validation | `out/m152_g3.json` | `3531714b…e05f89` | cap8-10 کاندیدای پژوهشی |

### 2.2 نتایج قطعی در برابر گزارش‌شده/متناقض/ناقص

- **قطعی (مستقل تأیید)**: OLD در ضرر است و NEW-A جهت بهتری دارد (M144/M145/M146 + زنده‌ماندن پس از BH-FDR در M153-H)؛ فروش پله‌ای ۵مرحله‌ای بدتر از trailing است (M149)؛ G4 منع ورود در کرش ضدسود است (M151)؛ سه گیت ارتقا FAIL (M152).
- **گزارش‌شده ولی بازمحاسبه‌نشده در M153**: عدد زوجی M146 (+0.205 [0.0543,0.3337]) — در متاآزمون با برچسب «مقدار گزارش‌شده» استفاده شد.
- **متناقض**: T2 (لِیبل صعودی ⇔ بازده آیندهٔ منفی) در نیمهٔ اول دادهٔ 2024-2026 تکرار نشد — نتیجهٔ M148 T2 وابسته به پنجره است (M153-D2).
- **ناقص**: survivorship (PARTIAL)، transfer_cost (UNKNOWN)، Early Detection Rate (تعریف دژنره — M153-G).

### 2.3 مانع تکرار بی‌دلیل

ممنوعیت‌های فعال از قبل: تکرار STAGED بدون فرضیهٔ جدید (M149)، خط CAP بسته (M146)، اجرای آربیتراژ (M142 BLOCKED). M153 فقط آزمون‌های با شناسهٔ مستقل جدید اجرا کرد (M153-D1/D2/E/FG/H) و هیچ گیت قبلی را به‌عنوان «تأییدشدهٔ جدید» گزارش نکرد.

---

## بخش ۳ — M153-B: چهار شاخهٔ دانش (Knowledge Inventory)

- فایل: `scripts/m153_fusion/out/m153_knowledge_inventory.json` (sha256 `4de9d1d9…2c5c3`) — **14 رکورد** با تمام ۲۰ فیلد الزامی؛ نتایج منفی و متناقض حفظ شده‌اند.
- **A — TRADER DNA**: `R-M65..M77` = UNTESTED_IN_MARI_ENGINE (بازخوانی کامل مأموریت‌های M65-M68.2/M77 در این اجرا انجام نشد؛ فهرست روش‌ها در `m65_build_research.py`/`m66_inventory.py` موجود است؛ «داستان موفقیت اشخاص، مدرک سودآوری نیست»).
- **B — SUCCESSFUL IDEAS**: Momentum/TrendFollowing (R-M143، CONDITIONAL) · MeanReversion (R-M153-D2، UNRESOLVED) · StagedExit (REJECTED) · R-exit/Structure-exit (REJECTED) · 8-state classification (PARTIAL) · Hysteresis (CONFIRMED پژوهشی) · ConcurrencyCap (CONDITIONAL) · CrashEntryBan (REJECTED) · Arbitrage (BLOCKED) · OpportunityDetection (NEGATIVE).
- **C — VISUAL INTELLIGENCE**: IMPLEMENTED: candlestick structure، EMA، RSI، MACD، ATR، swing structure، relative volume (مبنای score143) · **UNAVAILABLE** (دادهٔ خام در merged_1h.json نیست و شبیه‌سازی نشد — قانون ۸): Volume Profile، VWAP، Order Book Imbalance، Bid/Ask، Liquidity Heatmap، Liquidation Clusters، OI، Funding سری زمانی، CVD/Delta، Bollinger، Fibonacci، Multi-TF واقعی، BTC Dominance.
- **D — MATHEMATICAL**: EXERCISED: bootstrap بلوکی 24h×5000، WF folds، OOS، paired، BH-FDR، حساسیت هزینهٔ 20-50bp، حذف دُم، lookahead audit، UNKNOWN discipline · NOT EXERCISED: Monte Carlo کامل، Kelly، Risk of Ruin، Bayesian Updating.

---

## بخش ۴ — M153-C: معماری یکپارچه (طراحی + نگاشت واقعیت)

**حکم صادقانه: معماری «طراحی» است؛ هیچ ماژولی در یک runtime واحد به هم نخورده‌اند. هر ردیف به پیاده‌سازی پژوهشی واقعی موجود نگاشت شده است.**

| ماژول | ورودی | خروجی | پیاده‌سازی واقعی موجود | وضعیت اعتبار |
|---|---|---|---|---|
| A Global Market Scanner | universe عمومی | نمادهای فعال | M140 vault (cron حذف) + merged_1h (29 نماد) | PARTIAL |
| B Data Quality Engine | klines | گپ/کیفیت | چک گپ 24h در classify + F1/F2 تازگی M140 + UNKNOWN | PARTIAL |
| C Trader DNA Knowledge | روش‌های اشخاص | فهرست ارزیابی‌شده | M65/M66 artifacts | UNTESTED_IN_ENGINE |
| D Strategy Research | فرضیه‌ها | نتیجهٔ مستقل | M143-M153 scripts | ACTIVE (پژوهشی) |
| E Visual Intelligence | OHLCV | اندیکاتورها | engine143 (EMA/RSI/MACD/ATR/swings) | PARTIAL (بقیهٔ ابزارها UNAVAILABLE) |
| F Mathematical Validation | trades | CI/p/gates | M144/M145/M153-H | ACTIVE |
| G Regime Classifier | BTC series | RISK_ON/… | engine143.btc_regime | IMPLEMENTED |
| H Trend Intelligence | multi-factor score | ۸ حالت | M148 + واریانت H1 (M153-D1) | پژوهشی — T6 حل، T2 بدون حکم |
| I Opportunity Ranking | ویژگی‌ها | score 0-100 | M153-F | NOT CALIBRATED (score≠احتمال) |
| J Intelligent Profit Runner | موقعیت | خروج | engine143.run_smart_exit (X_ATR برندهٔ همهٔ مقایسه‌ها) | IMPLEMENTED — مرجع |
| K Risk & Portfolio | پرتفوی | گیت‌ها | M151/M152 (cap پژوهشی) | NOT TRANSFERRED |
| L Adversarial Evidence | هر ادعا | PASS/FAIL | M144/M145/M149/M153-H | ACTIVE |
| M Paper Dashboard | paper trades | گزارش | data/paper-trades.json + تلگرام (موجود، دست‌نخورده) | IMPLEMENTED (خارج از M153) |

هیچ ماژولی اختیار معاملهٔ واقعی ندارد. **"KNOWLEDGE_DOCUMENT_REGISTERED — RUNTIME_INTEGRATION_NOT_VERIFIED"** — ربات runtime از `data/*.json` و state خودش می‌خواند؛ هیچ شاهدی وجود ندارد که runtime این سند یا Registry را در مسیر تصمیم بخواند. اتصال ظاهری را اتصال واقعی معرفی نمی‌کنیم.

---

## بخش ۵ — M153-D: نتایج (رفع T6 و بررسی T2)

پیش‌ثبت: `scripts/m153_fusion/PREREGISTRATION.md` — قبل از اجرا، با hash. خروجی: `out/m153_d_trend.json` (sha256 `e2aa8171…83c8`).

### 5.1 T6 — hysteresis مستقل: **RESOLVED در واریانت پژوهشی (H1) — 3/3 PASS**

| واریانت | persistence | blink WEAKENING↔NEUTRAL | CRASH BTC (89 اپیزود) |
|---|---|---|---|
| RAW (M148 مرجع) | 68.13% | 7.68% | — (مرجع تأخیر صفر) |
| **H1 (PRIMARY): K=2 + مصونیت CRASH/UNKNOWN** | **84.73% ✓** | **3.21% ✓** | **تشخیص 100%، تأخیر 0.00 کندل ✓** |
| H2 (EMA3 امتیاز) — اکتشافی | 77.76% | 4.91% | — |
| H3 (تأخیر همه حتی CRASH) — اکتشافی | 84.97% | 3.22% | تشخیص 76.4%، تأخیر 0.76 — **بهای ایمنی: 24% اپیزودها دیر/جاافتاده** |

- H3 نشان داد تأخیر دادن به CRASH خطرناک است ⇒ طراحی H1 (مصونیت ایمنی) درست بود.
- انضباط گپ UNKNOWN در H1 حفظ شد (UNKNOWN فوری عبور می‌کند).
- **قید**: این واریانت پژوهشی است؛ هیچ تغییری در engine143/M148 انجام نشد؛ K=2 فقط روی همین داده ثبت شده و OOS مستقل ندارد.

### 5.2 T2 — mean reversion در برابر trend following: **UNRESOLVED (بدون حکم)**

- نمونه: 2228 ورود (710 LONG در STRONG_BULLISH، 1518 SHORT در STRONG_BEARISH)؛ نگهداری 168h؛ هزینهٔ M-series.
- نیمهٔ اول: TF +0.170%/trade (CI95 بلوکی [−1.367, +1.727]) — MR = −0.170%.
- نیمهٔ دوم: TF −0.519%/trade (CI95 [−1.694, +0.591]) — MR = +0.519%.
- **علامت بین دو نیمه ناسازگار ⇒ طبق قاعدهٔ پیش‌ثبت: «نتیجهٔ ناپایدار — بدون حکم».**
- یافتهٔ توصیفی: میانهٔ LONG-SBULL در هر دو نیمه منفی است (−1.78٪/−2.18٪) ولی میانهٔ SHORT-SBEAR مثبتِ کوچک (+0.07٪/+0.37٪) — با CI شامل صفر ⇒ لبه نیست.
- **نتیجهٔ عملی**: نه لبهٔ روندی و نه لبهٔ میانگین‌برگشتی پایدار از برچسب‌های فعلی قابل استخراج است؛ وارونگی T2 در M148 ویژگی ثابت داده نیست. برچسب روند همچنان «توصیف‌گر» است نه «سیگنال».

---

## بخش ۶ — M153-E: سه روش خروج مستقل (ورود مشترک، پارامتر منجمد)

پیش‌ثبت بخش C؛ خروجی: `out/m153_e_exits.json` (sha256 `848637b3…13f5d`) + `out/m153_e_trades.jsonl`. اعتبارسنجی هارنس: X_ATR دقیقاً NEW-A را بازتولید کرد (n=657 در V0؛ n=4273 در CF؛ +413.33$).

### جمع CF1-6 (ورود مشترک 4273):

| واریانت | net | PF | MDD | Giveback | ExitEff | MAE | TimeInTrade | حذف دُم Top5% | 30bp |
|---|---|---|---|---|---|---|---|---|---|
| **X_ATR (مرجع trailing)** | **+413.33$** | **1.066** | **−388$** | 1.202 | 0.401 | 2.48% | 9.7h | −1208.76$ | −441.27$ |
| X_R (R-based) | −471.21$ | 0.960 | −1569$ | 7.836 | 0.171 | 4.36% | 45.1h | −4943.10$ | −1325.81$ |
| X_ST (Structure-based) | −561.77$ | 0.925 | −1261$ | 4.385 | 0.160 | 2.59% | 19.1h | −3724.42$ | −1416.37$ |

- زوجی (n=4273): X_R −0.207%/trade [−0.726, +0.304]؛ X_ST −0.228% [−0.522, +0.077] — هر دو شامل صفر.
- **هر ۶ گیت FAIL** ⇒ X_R و X_ST رد شدند؛ **ATR trailing (NEW-A) مرجع می‌ماند** — سومین شکست متوالی خانوادهٔ «خروج جایگزین» پس از STAGED (M149).
- دلایل خروج: X_R = 70% STOP (استاپ 1R نسبت به نویز تنگ است، R=3×ATR نگه نمی‌دارد)؛ X_ST = 64% STRUCT.
- متریک‌های الزامی M153 (MFE/MAE/PeakUnrealized/Realized/Giveback/ExitEfficiency/TimeInTrade/RemainingRisk/NetAfterCosts) برای هر ۱۲٬۸۱۹ معامله در jsonl ذخیره شد.
- قید: خط بسته — تکرار بدون فرضیهٔ جدید ممنوع (عین قید M149).

---

## بخش ۷ — M153-F/G: Opportunity Scoring و Global Capture (نتیجهٔ منفیِ مهم)

پیش‌ثبت بخش D؛ خروجی: `out/m153_fg_capture.json` (sha256 `422fc1db…5a7c0`).

### 7.1 Scoring (بدون هیچ کالیبراسیون — امتیاز ≠ احتمال)

- 486,303 نقطهٔ امتیازدهی (28 نماد × پنجرهٔ کامل) — p50=26، p90=63، p95=72، p99=83.
- نرخ پرچم‌زدن: آشکارساز A (برچسب صعودی) 15.12%؛ آشکارساز B (score≥60) 12.25%.
- داده‌های Derivatives/Cross-Market در merged وجود ندارند ⇒ آن مؤلفه‌ها از امتیاز حذف (نه ساختگی) — قانون ۸.

### 7.2 Capture (رویداد +5٪ در پنجرهٔ 72h؛ برچسب آینده فقط برای ارزیابی)

| سنجه | A (برچسب صعودی) | B (score≥60) |
|---|---|---|
| نرخ پایهٔ رویداد | **45.2%** (219,986 از 486,303) | همان |
| Precision | 46.76% | 49.43% |
| Recall | 15.62% | 13.38% |
| F1 | 23.4 | 21.1 |
| تأخیر میانه | 45 کندل (از 72) | 43 کندل |
| FN در موج‌های ≥25% (17,910 رویداد) | **14,164 (79%)** | 14,319 (80%) |
| Early Detection Rate | **UNAVAILABLE** (تعریف پیش‌ثبت برای رویداد 72h/+5% دژنره بود — 0% سازه‌ای) | همان |

- **حکم صادقانه**: روی alts این داده، حرکت +5%/72h تقریباً «وضع عادی» است (نرخ پایه 45%)؛ هر دو آشکارساز فقط +1.5 تا +4.2pp بالای نرخ پایه‌اند — تمایز عملی ناچیز؛ طبقه‌بند روند **توصیف‌گر دنباله‌دار** است نه آشکارساز زودهنگام فرصت؛ 79% موج‌های ≥25% هنگام سیگنال‌سازی از قلم افتادند.
- این «شکار موج بزرگ» را به مسئلهٔ بازِ شمارهٔ یک MARI تبدیل می‌کند: تشخیص پیش از حرکت باید از سیگنال‌های ساختاری/مشتقاتیِ پیش‌رویداد بیاید (دادهٔ فعلی موجود نیست — UNAVAILABLE)، نه از تأیید روندِ پس از شروع.
- دسته‌بندی گذشتهٔ حرکت‌ها ثبت شد: <2%: 130,736 · 2-5%: 135,581 · 5-10%: 119,034 · 10-25%: 83,042 · 25-50%: 13,975 · 50-100%: 3,248 · 100-300%: 687 · >300%: 0.

---

## بخش ۸ — M153-H: متاآزمون خصمانه (تصحیح Multiple-Testing)

خروجی: `out/m153_h_meta.json` (sha256 `41186a2d…89ed489`). خانوادهٔ ۸ آزمونِ ثبت‌شدهٔ M144-M152؛ p تقریبی از CI95 (تقریب نرمال، برچسب‌گذاری صریح)؛ BH-FDR q=0.10.

| ID | ادعا | CI95 | p تقریبی | حکم پس از BH |
|---|---|---|---|---|
| F3 | M146 زوجی NEW-A>OLD (CF) | [+0.0543, +0.3337] | 0.0040 | **زنده** |
| F1 | M145 زوجی NEW-A>OLD (f0-3) | [+0.056, +0.3891] | 0.0093 | **زنده** |
| F5 | M149 زوجی STAGED<NEW-A | [−0.3551, −0.0315] | 0.0208 | **زنده** |
| F8 | M151 G2 مطلق | [−15.32, +249.92] | 0.0830 | مرده |
| F2 | M145 سود مطلق NEW-A | [−66.59, +549.56] | 0.1245 | مرده |
| F6 | M151 G1 مطلق | [−664.97, +1525.87] | 0.4412 | مرده |
| F7 | M151 G3 مطلق | [−268.06, +569.42] | 0.4806 | مرده |
| F4 | M146 سود مطلق NEW-A | [−1831.22, +2461.69] | 0.7736 | مرده |

- **نتیجه**: فقط ادعاهای «جهت‌گیری زوجی» پس از تصحیح زنده می‌مانند؛ هر پنج ادعای «سود مطلق» می‌میرند — عین نتیجهٔ سه گیت ارتقا. NEW-A بهتر از OLD است، ولی هیچ‌کس اثبات نکرده سودآور است.
- **HYBRID**: پیاده‌سازی مستقل و قابل‌بازتولید وجود ندارد ⇒ NOT IMPLEMENTED — ساخته نشد (ممنوعیت ساخت بدون مجوز).

## بخش ۹ — M153-I: Paper Simulation

**۹-۱ | گزارش اجرای نخست (Task 154):** هیچ موتور paper جدید ایزوله‌ای در اجرای نخست ساخته نشد؛ وضعیت **NOT IMPLEMENTED** صادقانه ثبت شد.

**۹-۲ | تکمیل در ادامهٔ مأموریت (Task 155، 2026-10-31) — حلقهٔ paper ایزولهٔ WOULD_TRADE:**

- پیش‌ثبت پیش از اجرا: `PREREGISTRATION.md` بخش G (پنجرهٔ منجمد 2026-08-08→انتهای داده، ورود entry_signals_v1 + خروج X_ATR(3.0,0.75,0.0) منجمد، یک موقعیت در هر نماد، بدون G3، SIZE=100$، هزینه 10bp+slip5bp).
- پیاده‌سازی: `scripts/m153_fusion/m153_i_paper.py` — فقط WOULD_TRADE؛ صفر اتصال به `data/paper-trades.json`/Shadow Paper؛ صفر سفارش واقعی؛ خروجی فقط در پوشهٔ ایزولهٔ m153_fusion/out.
- **باگ گرفته‌شده توسط گیت پیش‌ثبت:** off-by-one در entry_bar ردیاب سایه، توسط لنگر G-I4 (تطبیق استاپِ ردیابی‌شده با قیمت خروج در همهٔ TRAIL/STOP) گرفتار شد؛ اصلاح و اجرای مجدد شد — ثبت طبق قانون «هرگز موفقیت جعل نشود».

**گیت‌های تمرین (هر چهار PASS):**

| گیت | نتیجه |
|---|---|
| G-I1 صفر هم‌پوشانی موقعیت در هر نماد | PASS (0) |
| G-I2 کامل‌بودن ۹ متریک در همهٔ رکوردها | PASS (0 ناقص از 2794) |
| G-I3 سازگاری state↔ledger | PASS (2794=2794=2794) |
| G-I4 لنگر سایه (استاپِ ردیابی‌شده = قیمت خروج در TRAIL/STOP) | PASS (0 خطا از 2595) |

**پرتفوی WOULD_TRADE (توصیفی — حکم سود نیست):** n=2794 در 29 نماد · خالص +301.27$ · PF 1.093 · hit 41.8% · MDD −187.78$ · خروج‌ها: TRAIL 2419 / STOP 176 / FOLD_END 8 · هم‌زمانی: حداکثر 28، میانگین 15.9 موقعیت باز · ترکیب برچسب ورود: NEUTRAL 1025 / WEAKENING 557 / BEARISH 500 / BULLISH 406 / STRONG_BEARISH 158 / CRASH 101 / STRONG_BULLISH 47.

- منحنی هزینه: 10bp→+301.27$ · 15bp→+161.57$ · 20bp→+21.87$ · **30bp→−257.53$** · 40bp→−536.93$ — عین امضای هزینهٔ خانواده (30bp منفی).
- حذف دُم Top5%: −661.40$ (PF 0.797) — سود مطلق وابسته به دُم کوچکی از معاملات است؛ همسو با متاآزمون H (ادعاهای مطلق مرده).
- مشاهدهٔ پژوهشی جدید (بدون اقدام): 101 ورود در برچسب CRASH و هم‌زمانی بالا (میانگین 15.9) — ورودی برای پژوهش آیندهٔ لایهٔ پرتفوی؛ G3 اعمال نشد چون ارتقای آن ممنوع بود.
- `data/paper-trades.json` دست نخورد؛ هیچ ادغامی با Shadow Paper انجام نشد.
- وضعیت: **IMPLEMENTED (حلقهٔ paper ایزولهٔ WOULD_TRADE — تمرین مکانیک؛ OOS خالص نیست: هم‌پوشانی جزئی با C0-C3؛ سود شبیه‌سازی ≠ عملکرد واقعی)**

---

## بخش ۱۰ — M153-J: ممیزی نهایی مستقل

**پوشش فرمان:**
- baseline و شروع: بخش ۰ و ۲ ✓
- منابع بازیابی‌شده: 2.1 ✓ (پیوست A = SOURCE_TEXT_NOT_RECOVERED)
- چهار شاخهٔ دانش: بخش ۳ ✓
- معماری طراحی‌شده: بخش ۴ ✓ (طراحی + نگاشت؛ ادغام runtime = نه)
- ماژول‌های واقعاً ساخته‌شده در M153: ۵ باتری آزمون مستقل (D1 hysteresis، D2 TF/MR، E سه‌خروجی، FG scoring/capture، H متا) + Inventory + Registry + این سند
- ماژول‌های فقط طراحی‌شده: ادغام A-M در runtime واحد، موتور paper ایزولهٔ جدید، HYBRID
- نتایج مستقل: بخش ۵-۸ ✓
- هزینه‌ها: منحنی 20-50bp در همهٔ باتری‌ها ✓ — 30bp در همهٔ گزینه‌های موتور روند منفی است
- MDD: X_ATR −388$ بهترین؛ X_R −1569$؛ X_ST −1261$؛ G3 MDD را 65% کم‌عمق می‌کند (پژوهشی)
- سودهای کوچک/موج‌های بزرگ: ExitEff مرجع 0.40 — یعنی 60% اوج سود شناور از دست می‌رود ولی دو جایگزین بدتر بودند؛ موج‌های ≥25%: 79% از قلم (بخش ۷)
- Precision/Recall: 46.76/15.62 (A) و 49.43/13.38 (B) در برابر نرخ پایهٔ 45.2%
- خطاها و محدودیت‌ها: باگ‌های اجرای میدانی (falsy-zero در حکم، MAE init، bucket منفی، classify بدون s) همگی قبل از نتیجه‌گیری نهایی یافت و اصلاح شدند؛ لاگ‌ها و jsonl نهایی بازبینی شد
- hash فایل‌های حساس قبل/بعد: بخش ۰ (قبل) و بخش ۱۱ manifest (بعد) — protected ها تغییر نکردند
- وضعیت Git: HEAD cb4b5fa، remote ندارد ⇒ فقط commit محلی
- تست‌ها و رگرسیون: هارنس X_ATR عین NEW-A بازتولید شد (n=657 V0 / +413.33$ CF) — رگرسیون موتور تأیید شد؛ engine143 دست‌نخورده

**وضعیت نهایی M153: `PARTIAL`**

دلایل (مطابق «تکمیل مراحل به‌تنهایی مجوز PASS نیست»):
1. متن کامل فرمان M148 بازیابی نشد (SOURCE_TEXT_NOT_RECOVERED) — پیوست A باز است.
2. RUNTIME_INTEGRATION_NOT_VERIFIED — ادغام دانش در runtime تصمیم اثبات نشد.
3. Survivorship هنوز PARTIAL؛ transfer_cost هنوز UNKNOWN.
4. حلقهٔ paper ایزولهٔ جدید (M153-I) ساخته نشد.
5. هیچ ادعای سودآوری مطلقی تأیید نشد (متاآزمون: 5/5 ادعای مطلق مرده) و ارتقای موتور همچنان ممنوع است.
6. شکار موج بزرگ (پوشش 21% از موج‌های ≥25%) مسئلهٔ باز است.

آنچه واقعاً پیش رفت: T6 با واریانت مستقل حل شد؛ T2 به‌طور مستقل «بی‌حکم» شد؛ سه خروجی جایگزین رد شدند؛ کمبود قدرت آشکارساز فرصت اندازه‌گیری و ثبت شد؛ کل دانش M140-M153 با hash در Registry نسخه‌بندی شد.

**پیوست ممیزی نهایی (Task 155، 2026-10-31):** دلیل ۴ (حلقهٔ paper ایزوله) با پیاده‌سازی `m153_i_paper.py` بسته شد — چهار گیت تمرین PASS، 2794 رکورد کامل، لنگر سایه بدون خطا (بخش ۹-۲). بقیهٔ دلایل همچنان برقرارند (متن M148، ادغام runtime، survivorship، transfer_cost، ادعای سود مطلق، پوشش موج بزرگ) ⇒ **وضعیت نهایی بدون تغییر: `PARTIAL`** — تکمیل یک دلیل به‌تنهایی مجوز PASS نیست. باگ off-by-one ردیاب سایه توسط گیت پیش‌ثبت G-I4 قبل از ثبت نتیجه گرفتار و اصلاح شد (هیچ نتیجه‌ای پس از باگ گزارش نشد).

---

## بخش ۱۱ — Manifest ثبت (SHA256)

| فایل | SHA256 |
|---|---|
| `scripts/m153_fusion/PREREGISTRATION.md` | (پیش از اجرا ثبت شد — بخش ۱۱ manifest.json) |
| `scripts/m153_fusion/out/m153_d_trend.json` | `e2aa81717877dbd501c399a7d40ec127cdafc5e4f10e67edef69fdb859e883c8` |
| `scripts/m153_fusion/out/m153_e_exits.json` | `848637b3d06f2ea4270ce1fd7eaff542ddc62a6eede3e8803900eac393513f5d` |
| `scripts/m153_fusion/out/m153_fg_capture.json` | `422fc1dbaebb741c061c6788eecd6961b42fc47f39ade5fa7773180d4085a7c0` |
| `scripts/m153_fusion/out/m153_h_meta.json` | `41186a2db9887a84b28f2306aa2d6819813eafee4cdc582551d6890abb9ed489` |
| `scripts/m153_fusion/out/m153_knowledge_inventory.json` | `4de9d1d9231ec63be96565c3453a3b3efd2645942238929ecd849f9ed232c5c3` |
| `scripts/m153_fusion/out/m153_e_trades.jsonl` | `27b1f04de01408c6393581636efd354fabfe5f7e86099b0642e23eddace577ad` |
| `docs/architecture/MARI_M153_WORLD_MARKET_INTELLIGENCE_FUSION.md` | (در manifest.json نهایی) |
| `docs/mother-document.md` (بعد از افزودن خلاصه) | (در manifest.json نهایی) |
| `worklog.md` (بعد از Task 154) | (در manifest.json نهایی) |

محافظت‌شده‌ها (بعد از مأموریت — باید با قبل برابر باشند): engine143.py، m3_engine.py، paper-trades.json، CORE-DOCTRINE-001.md — تأیید در manifest.json.

**ثبت GitHub**: `git remote` خالی است (REMOTE_COUNT=0) ⇒ **LOCAL DOCUMENT REGISTERED — GITHUB PUSH NOT VERIFIED**. ادعایی از ذخیره در GitHub نمی‌شود.

**Status نهایی: PARTIAL** — BREAK THE ASSUMPTIONS · VERIFY THE EVIDENCE · NEVER FAKE SUCCESS

---

## پیوست B — متن مرجع تکمیلی: MASTER EXECUTION ORDER + PERMANENT KNOWLEDGE INTEGRATION (ثبت 2026-10-31/11-01)

> منشأ: فرمان جدید مدیر پروژه دریافت‌شده در 2026-10-31 (ساعت تهران 20:30). این دو متن، افزودهٔ رسمی M153 هستند و طبق «MARI CORE — PERMANENT KNOWLEDGE INTEGRATION» عیناً و بدون حذف در آرشیو مأموریت ثبت می‌شوند. بخش‌های ۰ تا ۱۱ و پیوست A بالا بدون هیچ تغییری حفظ شده‌اند (نسخهٔ قبلی سند دست‌نخورده است؛ این فقط الحاق است).

### B-1) متن عیناً — MARI — MASTER EXECUTION ORDER

MISSION M153 → AUTONOMOUS WORLD MARKET INTELLIGENCE

دستور مادر اجرایی، حیاتی و غیرقابل‌فراموشی

اصول بنیادین:

BREAK THE ASSUMPTIONS — VERIFY THE EVIDENCE — NEVER FAKE SUCCESS

قفل امنیتی دائمی:
READ ONLY | PAPER ONLY | NO LIVE ORDERS

1. مأموریت اصلی

تو مسئول اجرای مهندسی، پژوهش، نظارت، عیب‌یابی و تکامل MARI — World Market Core هستی.

هدف نهایی، ساخت سامانه‌ای است که بتواند:

1. بازار جهانی رمزارزها را به‌صورت پیوسته رصد کند.
2. فرصت‌های صعودی و نزولی را قبل از حرکت اصلی شناسایی کند.
3. حرکت واقعی بازار را از شکست کاذب تشخیص دهد.
4. Funding، Open Interest، Volume، Liquidity و Market Structure را تحلیل کند.
5. روندهای کوچک را از روندهای بزرگ تفکیک کند.
6. معاملات موفق را زودهنگام نبندد.
7. در صورت تغییر ساختار روند، سود را مرحله‌ای حفظ کند.
8. عملکرد خودش را با واقعیت بازار مقایسه کند.
9. اشتباهاتش را ثبت کند و از آن‌ها یاد بگیرد.
10. بدون نیاز به سرویس پولی یا API هوش مصنوعی پولی فعالیت پژوهشی خود را ادامه دهد.

2. اولویت فوری: M153

ابتدا وضعیت واقعی M153 را بررسی کن.

هیچ مرحله‌ای را صرفاً به دلیل وجود گزارش قبلی تکمیل‌شده فرض نکن.

ترتیب اجرا:

- بررسی کامل وضعیت PHASE 0.
- بررسی صحت منابع داده عمومی.
- بررسی امکان دریافت Funding واقعی.
- تفکیک داده واقعی، تخمینی، ناقص و UNAVAILABLE.
- بررسی کیفیت داده، Timestamp و هم‌زمانی بازارها.
- بررسی صحت محاسبات.
- اجرای تست‌های مستقل.
- ثبت نتایج مثبت و منفی.
- تهیه گزارش مستند هر مرحله.

Funding واقعی اولویت ویژه دارد.

اگر Funding واقعی قابل دریافت نیست، صریحاً UNAVAILABLE ثبت کن. Funding تخمینی را هرگز به‌جای Funding واقعی نمایش نده.

پس از تکمیل و تأیید M153، سراغ M154 برو و مسیر Shadow Research را طبق برنامه تا ۲۹ نوامبر ادامه بده.

هیچ مرحله‌ای را با نتیجه ساختگی PASS اعلام نکن.

3. مأموریت حیاتی: تعمیر و فعال‌سازی داشبورد

داشبورد MARI باید وضعیت واقعی سیستم را نمایش دهد.

موارد ضروری:

- وضعیت اتصال منابع داده.
- تعداد نمادهای تحت پوشش.
- آخرین زمان دریافت داده.
- وضعیت Funding.
- وضعیت بازار و Regime.
- تعداد فرصت‌های شناسایی‌شده.
- فرصت‌های LONG و SHORT.
- تعداد سیگنال‌های تأییدشده و ردشده.
- وضعیت Paper Engine.
- معاملات باز و بسته.
- سود و زیان تحقق‌یافته.
- سود و زیان تحقق‌نیافته.
- Drawdown.
- وضعیت Risk Gate.
- خطاهای سیستم.
- آخرین زمان اجرای هر موتور.
- آخرین زمان ارسال گزارش تلگرام.

داشبورد باید از داده واقعی و فایل‌های مرجع سیستم تغذیه شود.

هیچ عدد نمایشی یا ساختگی مجاز نیست.

اگر بخشی از سیستم کار نمی‌کند، وضعیت آن باید مشخص باشد؛ نه اینکه با عدد صفر یا وضعیت سبز پنهان شود.

4. مأموریت حیاتی: گزارش تلگرام هر دو ساعت

سیستم گزارش‌دهی تلگرام را بررسی و تعمیر کن.

هدف: ارسال گزارش خودکار هر دو ساعت، بدون وابستگی به اجرای دستی.

گزارش باید شامل این اطلاعات باشد:

1. ساعت و تاریخ گزارش.
2. وضعیت کلی MARI.
3. تعداد نمادهای بررسی‌شده.
4. تعداد فرصت‌های جدید.
5. بهترین فرصت‌های LONG.
6. بهترین فرصت‌های SHORT.
7. Funding واقعی و وضعیت دسترسی آن.
8. تغییرات مهم حجم و نقدینگی.
9. تغییر ساختار روند.
10. وضعیت معاملات Paper.
11. سود و زیان و Drawdown.
12. خطاها و هشدارهای مهم.
13. وضعیت اجرای مأموریت جاری.
14. اقدام بعدی سیستم.

قوانین گزارش‌دهی:

- گزارش باید هر ۱۲۰ دقیقه ارسال شود.
- گزارش موفق باید ثبت شود.
- ارسال ناموفق باید با علت دقیق ثبت شود.
- گزارش تکراری و بدون تغییر نباید به‌عنوان فعالیت جدید معرفی شود.
- اگر بازار فاقد فرصت معتبر است، صریحاً اعلام کن.
- اگر داده‌ای در دسترس نیست، UNAVAILABLE اعلام کن.
- اگر ربات متوقف شده، آن را پنهان نکن.
- زمان آخرین ارسال موفق باید در داشبورد قابل مشاهده باشد.

ابتدا مسیر فعلی تلگرام، Scheduler، Heartbeat، Logs و تنظیمات ارسال را بررسی کن.

توکن و اطلاعات محرمانه را در گزارش یا خروجی ترمینال چاپ نکن.

5. مغز تصمیم‌گیری بازار

تمام موتورهای تحلیلی باید در یک زنجیره تصمیم‌گیری هماهنگ شوند:

- Liquidity Intelligence
- AMD & Session Analysis
- Volume & Value
- Market Structure
- Derivatives Intelligence
- Funding & Open Interest
- Cross-Market Analysis
- Macro & News
- Risk & Portfolio
- Data Integrity & Forensics

هیچ موتور به‌تنهایی مجاز به صدور تصمیم نهایی نیست.

تصمیم نهایی باید مبتنی بر شواهد مستقل، هم‌زمانی داده‌ها، کیفیت اطلاعات و وضعیت ریسک باشد.

6. قانون حیاتی شکار روند و حفظ سود

MARI نباید صرفاً به‌دلیل رسیدن به یک دلار سود، یک درصد سود یا هر آستانه ثابت دیگری، یک دارایی ر

ا بفروشد.

مثال:

اگر یک دارایی وارد روند صعودی معتبر شده و یک دلار سود ایجاد کرده است، سیستم باید بررسی کند آیا روند همچنان قدرت ادامه دارد یا خیر.

اگر احتمال ادامه روند با شواهد معتبر تأیید شود، نگهداری پله‌ای باید بررسی شود.

اگر روند تضعیف شود، مدیریت ریسک و خروج مرحله‌ای فعال شود.

قواعد:

- تشخیص روند صعودی و نزولی.
- تفکیک اصلاح موقت از تغییر روند.
- شناسایی شکست معتبر و شکست کاذب.
- استفاده از Trailing Stop تطبیقی.
- حفظ بخشی از سود در صورت تضعیف روند.
- امکان نگهداری بخش باقی‌مانده در روندهای قوی.
- جلوگیری از فروش زودهنگام صرفاً بر اساس سود ثابت.
- جلوگیری از تبدیل سود قابل‌توجه به زیان بزرگ.

هیچ درصد سود یا هدف قیمتی نباید بدون آزمون و شواهد به‌عنوان قانون قطعی ثبت شود.

این منطق ابتدا باید در Paper و با احتساب کارمزد، اسلیپیج و Funding آزمایش شود.

7. موتور یادگیری و حافظه دائمی

هر کشف، شکست، فرضیه، آزمایش و نتیجه باید قابل بازیابی باشد.

برای هر فرضیه ثبت کن:

- شناسه یکتا.
- فرضیه اولیه.
- منطق اقتصادی.
- داده مورد استفاده.
- شرایط آزمایش.
- معیار موفقیت.
- معیار ابطال.
- نتیجه واقعی.
- محدودیت‌ها.
- تصمیم بعدی.

نتایج منفی را حذف نکن.

فرضیه ردشده را بدون شواهد جدید دوباره به‌عنوان کشف موفق معرفی نکن.

دانش تأییدشده باید در اسناد دکترین و حافظه قابل‌بازیابی پروژه ثبت شود.

8. استقلال اجرایی و کنترل کیفیت

بدون توقف برای تأییدهای غیرضروری، تمام مراحل READ ONLY و تعمیرات غیرمخرب را اجرا کن.

اما:

- هیچ فایل محافظت‌شده‌ای را تغییر نده.
- هیچ معامله‌ای ایجاد نکن.
- هیچ سفارش زنده‌ای ارسال نکن.
- هیچ داده تاریخی را حذف نکن.
- هیچ کلید یا توکنی را افشا نکن.
- هیچ آزمایش ناقصی را موفق اعلام نکن.
- هیچ نتیجه‌ای را بدون بازتولید مستقل تأیید نکن.

قبل از هر تغییر احتمالی در فایل‌های عملیاتی، ابتدا نسخه پشتیبان، محدوده تغییر و ریسک آن را مشخص کن. تغییر در داده‌های محافظت‌شده و وضعیت Paper بدون مجوز صریح ممنوع است.

9. آزمون مستقل عملکرد در برابر بازار جهانی

عملکرد MARI باید با حرکت واقعی بازار مقایسه شود.

برای هر دوره:

- تمام نمادهای قابل‌دسترسی را ثبت کن.
- صعودهای واقعی را شناسایی کن.
- نزول‌های واقعی را شناسایی کن.
- فرصت‌های ازدست‌رفته را ثبت کن.
- سیگنال‌های اشتباه را محاسبه کن.
- زمان تشخیص را بسنج.
- میزان حرکت قابل‌شناسایی را اندازه‌گیری کن.
- عملکرد پس از هزینه‌ها را محاسبه کن.
- نتایج خارج از نمونه را جداگانه ارزیابی کن.

معیارهای ضروری:

Precision، Recall، False Positive Rate، Detection Delay، Profit Factor، Expectancy، Max Drawdown و Net Return.

مقایسه باید با Universe واقعی و بدون سوگیری بقا انجام شود.

10. ترتیب تحویل نهایی

به این ترتیب اجرا کن:

A. ممیزی وضعیت واقعی پروژه و Git.

B. بررسی و تکمیل M153.

C. بررسی Funding واقعی و کیفیت داده‌ها.

D. بررسی ارتباط موتورهای تحلیلی.

E. تعمیر داشبورد.

F. تعمیر Scheduler و گزارش تلگرام ۱۲۰ دقیقه‌ای.

G. بررسی سلامت Paper Engine.

H. اعتبارسنجی منطق حفظ سود و تشخیص روند.

I. آزمون مستقل در برابر بازار واقعی.

J. تکمیل M154 و ادامه Shadow Research طبق برنامه.

K. تهیه گزارش نهایی و ثبت مستندات.

11. استاندارد گزارش نهایی

برای هر بخش فقط یکی از وضعیت‌های زیر را ثبت کن:

- PASS: با شواهد و آزمون مستقل تأیید شده.
- FAIL: آزمون شکست خورده.
- PARTIAL: بخشی از کار انجام شده.
- BLOCKED: مانع مشخص وجود دارد.
- UNAVAILABLE: منبع یا قابلیت واقعاً در دسترس نیست.
- NOT TESTED: هنوز آزمایش نشده است.

برای هر بخش ارائه کن:

1. وضعیت قبل از اجرا.
2. اقدام انجام‌شده.
3. فایل‌ها و اجزای بررسی‌شده.
4. شواهد واقعی.
5. نتیجه تست.
6. خطاهای باقی‌مانده.
7. وضعیت امنیت.
8. اقدام بعدی.

در پایان، صریحاً اعلام کن:

- آیا داشبورد واقعاً کار می‌کند؟
- آیا گزارش تلگرام هر دو ساعت واقعاً ارسال می‌شود؟
- آیا Funding واقعی دریافت می‌شود؟
- آیا موتور بازار فعال است؟
- آیا Paper Engine سالم است؟
- چه چیزهایی هنوز ناقص است؟

هیچ‌وقت ادعای اجرای موفق را جایگزین شواهد واقعی نکن.

فرمان نهایی

MARI باید از یک مجموعه اسکریپت پراکنده به یک سامانه یکپارچه پژوهش، کشف فرصت، تشخیص روند، مدیریت ریسک و یادگیری مستمر تبدیل شود.

اول زیرساخت را درست کن، سپس داده را اعتبارسنجی کن، بعد تصمیم‌گیری را بهبود بده و در نهایت عملکرد را در برابر بازار واقعی بسنج.

اولویت امروز:

M153 → FUNDING REALITY → DASHBOARD → TELEGRAM 120M → M154 → SHADOW VALIDATION

هیچ مرحله‌ای را به‌خاطر سرعت قربانی کیفیت نکن.

هیچ سودی را جعل نکن.

هیچ شکستی را پنهان نکن.

هیچ فرضیه‌ای را بدون آزمون حقیقت فرض نکن.

MARI MUST

PROVE ITS EDGE — NOT CLAIM IT.

READ ONLY | PAPER ONLY | NO LIVE ORDERS

END OF MASTER EXECUTION ORDER

### B-2) متن عیناً — MARI CORE — PERMANENT KNOWLEDGE INTEGRATION

مأموریت: ثبت آخرین دستور و متن اجرایی تأییدشده در هستهٔ اصلی MARI.

1. آخرین متن اجرایی ارسال‌شده را به‌عنوان ورودی رسمی دانش هسته بررسی کن.
2. محتوای آن را استخراج و به بخش معماری و منطق مربوطه در WORLD MARKET CORE متصل کن.
3. اصول، فرضیه‌ها، محدودیت‌ها، معیارهای ارزیابی و شروط اجرایی آن را حفظ کن.
4. از ایجاد نسخه‌های تکراری یا متناقض جلوگیری کن.
5. متن اصلی را بدون حذف یا تحریف در آرشیو مأموریت‌ها نگهداری کن.
6. ارتباط آن با مأموریت‌های قبلی و بعدی را ثبت کن.
7. آزمون‌های لازم برای اطمینان از قابل‌بازیابی بودن اطلاعات انجام بده.

محدودیت‌های قطعی:

- READ ONLY
- PAPER ONLY
- NO LIVE ORDERS
- NO WITHDRAWALS
- هیچ تغییر مخربی در داده‌های موجود انجام نشود.
- فایل "data/paper-trades.json" دست‌نخورده باقی بماند.

گزارش الزامی:

- نام فایل‌های بررسی‌شده
- نام فایل‌های تغییرکرده
- محل دقیق ثبت دانش
- شناسه و نسخهٔ ثبت‌شده
- نتیجهٔ آزمون بازیابی
- خطاها و موارد انجام‌نشده

هیچ کاری را انجام‌شده اعلام نکن مگر اینکه شواهد واقعی آن موجود باشد.

شعار:
BREAK THE ASSUMPTIONS — VERIFY THE EVIDENCE — NEVER FAKE SUCCESS

### B-3) وارسی واقعیت اجرایی هفت‌گانهٔ دستور مادر (پاسخ مستند، 2026-10-31T16:5xZ)

| # | پرسش فرمان | وضعیت | شواهد واقعی |
|---|---|---|---|
| 1 | آیا داشبورد واقعاً کار می‌کند؟ | PASS (endpoint) | GET /api/health → HTTP 200، ok=true، liveOrders=DISABLED (سه بار ممیزی مستقل M153-B)؛ فید بازار فعلاً idle: connection=قطع، source=none، lastFetchAt=null — صادقانه، بدون سبزِ دروغین |
| 2 | گزارش تلگرام هر دو ساعت واقعاً ارسال می‌شود؟ | PASS | کرون 488813 (هر 2 ساعت تهران) + کرون 486300 ساعتی؛ سه ارسال موفق متوالی: msg 197 (15:45Z)، 198 (16:26Z)، 199 (16:37Z) — همه delivered=true در send-log.jsonl؛ job_state/heartbeat SUCCESS، consecutive_failures=0 |
| 3 | آیا Funding واقعی دریافت می‌شود؟ | PARTIAL → منبع واقعی VERIFIED، ادغام runtime NOT VERIFIED | probe عمومی GET fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT → پاسخ واقعی: markPrice=77556.69، lastFundingRate=0.0001 (0.01%)، nextFundingTime=1793491200000. دادهٔ واقعی است (نه تخمینی)؛ اما هنوز به موتور/داشبورد ادغام نشده — ادغام کاری M154 است |
| 4 | آیا موتور بازار فعال است؟ | PARTIAL | موتور PAPER: paused=True (توقف خودکار طبق قانون ریسک، علت ثبت‌شده در autoPauseReason) — موتور سالم اما غیرفعال طبق طراحی؛ موتور پژوهشی (کرون‌ها) فعال |
| 5 | آیا Paper Engine سالم است؟ | PASS | core_digest=6d8b7beb6d5a6c01 == مرجع ✓ (دوباره در ممیزی M153-B تأیید شد) · trades=74 · نسخهٔ git موتور (m3_engine.py) دست‌نخورده از 10-24 |
| 6 | چه چیزهایی هنوز ناقص است؟ | ثبت شد | (الف) ادغام runtime سند→ربات: KNOWLEDGE_DOCUMENT_REGISTERED — RUNTIME_INTEGRATION_NOT_VERIFIED؛ (ب) پیوست A: SOURCE_TEXT_NOT_RECOVERED (متن ۱۶‌بخشی M148)؛ (ج) transfer_cost=UNKNOWN ⇒ گیت اجرای آربیتراژ BLOCKED؛ (د) OOS خالص منفی ⇒ هیچ ادعای سود مطلق؛ (هـ) T2 همچنان UNRESOLVED؛ (و) داشبورد هنوز همهٔ ۱۷ قلم فهرست بند ۳ را نمایش نمی‌دهد (فید idle)؛ (ز) funding واقعی به pipeline رسمی وصل نشده |
| 7 | Shadow Research تا 2026-11-29 | ACTIVE | شادو run#2: روز 1.04، باز 18، بسته 7، parity 36/36؛ حکم ۳۰روزه: 2026-11-29 |

### B-4) وضعیت نسخهٔ سند

- نسخهٔ پایهٔ سند (بخش‌های ۰ تا ۱۱ + پیوست A): تغییر نکرده — byte-to-byte حفظ شد.
- این پیوست B: الحاق 2026-10-31، فقط‌افزوده، بدون بازنویسی تاریخچه.
- قانون B-2 بند ۴ (جلوگیری از نسخهٔ تکراری/متناقض): MASTER EXECUTION ORDER قبلاً در این مخزن ثبت نشده بود (grep=0)؛ این نخستین ثبت رسمی است.
