// MARI — موتور کارنامک (Paper Trading Tracker) — قرارداد داده
// مطابق بخش ۲۲-۲۴ (قرارداد داده) و ۳۹.۱۱ (آزمون Paper) و ۳۷.۵ (نمای اعتبارسنجی) سند مادر
// اصل ثابت: READ ONLY | PAPER ONLY | NO LIVE ORDERS

import type { DecisionLogEntry } from "./decisionlog";

export type PaperSide = "LONG" | "SHORT";
export type PaperStatus = "OPEN" | "CLOSED";
export type PaperExitReason = "TP" | "SL" | "TIME" | "MANUAL";

/** یک معامله تمرینی ثبت‌شده — هر فیلد از داده واقعی منبع می‌آید؛ هیچ عدد ساختگی مجاز نیست */
export interface PaperTrade {
  id: string; // `${symbol}-${interval}-${entryTime}` — قابل ردیابی و بازتولید
  symbol: string; // مثل BTCUSDT (بخش ۳۶.۵: symbol)
  exchange: "toobit" | "binance-vision"; // منشأ داده ورود
  interval: "1h"; // تایم‌فریم موتور کارنامک نسخه ۱
  side: PaperSide;
  status: PaperStatus;
  // --- ورود ---
  entryPrice: number; // قیمت بسته‌شدن آخرین کندلِ بسته‌شده هنگام سیگنال
  entryTime: number; // زمان بسته‌شدن کندل سیگنال (ms) — زمان تصمیم فرضی
  tpPrice: number;
  slPrice: number;
  score: number; // امتیاز خام موتور سیگنال (-۵ تا +۵)
  strength: number; // ۰ تا ۱۰۰
  reason: string; // خلاصه فارسی رأی‌ها (شواهد ورود — بخش ۳۶.۵: evidence)
  sourceVersion: string; // نسخه موتور (بخش ۳۶.۵: source_version)
  // --- پایش زنده ---
  lastPrice: number | null;
  lastCheck: number | null;
  mfePct: number; // حداکثر حرکت مطلوب (٪) — از کندل‌های بسته‌شده پس از ورود
  maePct: number; // حداکثر حرکت نامطلوب (٪)
  // --- خروج ---
  exitPrice: number | null;
  exitTime: number | null;
  exitReason: PaperExitReason | null;
  realizedPnlPct: number | null; // بازده بسته‌شده پس از کسر کارمزد فرضی
  createdAt: number; // زمان ثبت در سامانه
  // --- فیلدهای نسخه ۲ (mari-paper-v2) — معاملات قدیمی نسخه ۱ این فیلدها را ندارند و به‌صورت FIXED خوانده می‌شوند ---
  slBasis?: "FIXED" | "ATR"; // پایه حد ضرر: ثابت نسخه ۱ یا دینامیک ATR نسخه ۲
  atrPctAtEntry?: number | null; // ATR درصدی هنگام ورود (null = داده کافی نبود و به کف ثابت برگشت)
  plannedRiskPct?: number; // ریسک برنامه‌ریزی‌شده هر معامله از حساب تمرینی (قانون ۱٪ محافظه‌کارانه)
  sizeUsd?: number | null; // اندازه تمرینی دلاری (ریسک دلاری ÷ فاصله حد ضرر)
  beActive?: boolean; // آیا حد ضرر به سربه‌سر منتقل شده؟ («هرگز نگذار برنده، بازنده شود»)
  trailActive?: boolean; // آیا حد ضرر متحرک فعال شده؟ («اجازه بده سودها بدوند»)
  trailExtremePct?: number; // بهترین حرکت مطلوب از زمان فعال شدن تریلینگ (٪)
  decisions?: DecisionLogEntry[]; // لاگ payload لحظهٔ تصمیم (گیت ۰۰۳/SHORT-15) — معاملات قدیمی این فیلد را ندارند و بدون آن هم FIXED خوانده می‌شوند
}

/** عکس وضعیت کیفیت داده آخرین چرخه موتور (فاز ۲ سند مادر: Data Quality & Forensics) */
export interface CandleQualitySnapshot {
  at: number; // زمان آخرین چرخه
  ok: boolean; // آیا هیچ نمادی به‌خاطر داده بی‌کیفیت رد نشد؟
  checkedSymbols: number; // چند نماد بررسی شدند
  okSymbols: number; // چند نماد سالم بودند
  skippedSymbols: number; // چند نماد به‌خاطر داده بی‌کیفیت این چرخه رد شدند
  issues: string[]; // حداکثر چند نمونه توضیح فارسی
}

export interface PaperStoreShape {
  version: 1;
  updatedAt: number;
  trades: PaperTrade[];
  paused?: boolean; // توقف اضطراری ثبت سیگنال جدید (الزام بخش ۳۹.۱۱) — پایش بازها ادامه دارد
  lastQuality?: CandleQualitySnapshot | null;
  autoPausedUntil?: number | null; // فیوز ضرر متوالی: تا این زمان ثبت سیگنال جدید خودکار متوقف است
  autoPauseReason?: string | null; // توضیح فارسی آخرین فعال‌سازی فیوز
  autoPauseAtConsec?: number | null; // شمارِ ضرر متوالی در لحظه آخرین فیوز — جلوگیری از قفل همیشگی
}

/** پارامترهای اعلام‌شده موتور — باید در رابط کاربری هم نمایش داده شود (اصل شفافیت بخش ۲۸) */
export const PAPER_PARAMS = {
  // --- پایه نسخه ۱ (برای معاملات قبلی و کف‌های حد ضرر حفظ شده است) ---
  tpPct: 2.0, // حد سود پایه ۲٪ — در نسخه ۲ فقط برای معاملات v1
  slPct: 1.0, // حد ضرر پایه ۱٪ (نسبت R/R برابر ۲) — در نسخه ۲ کف حد ضرر ATR
  feePct: 0.1, // کارمزد فرضی رفت‌وبرگشت (٪) — بخش ۳۹.۱۱: هزینه‌های فرضی لحاظ شود
  maxHoldMs: 24 * 3_600_000, // حداکثر نگهداری ۲۴ ساعت
  cooldownMs: 6 * 3_600_000, // فاصله حداقل پس از بسته‌شدن معامله نماد
  interval: "1h" as const,
  sourceVersion: "mari-paper-v2", // ارتقای موتور با فرمول‌های حرفه‌ای تریدرها
  // --- پارامترهای جدید نسخه ۲ (تعریف دقیق در src/lib/paper/v2.ts) ---
  atrSlMult: 1.5, // حد ضرر دینامیک = ۱.۵ × ATR (کف ۱٪ — سقف ۳.۵٪)؛ حد سود = ۲ برابر حد ضرر
  beTriggerPct: 1.0, // پس از ۱٪ حرکت مطلوب: حد ضرر به سربه‌سر (+کارمزد) — Paul Tudor Jones
  trailTriggerPct: 2.0, // پس از ۲٪ حرکت مطلوب: حد ضرر متحرک با فاصله ۱.۲٪ — Livermore
  trailGapPct: 1.2, // فاصله حد ضرر متحرک از بهترین قیمت
  maxOpenPositions: 5, // حداکثر معاملات باز هم‌زمان (تنوع‌بخشی ریسک)
  riskPerTradePct: 1.0, // ریسک هر معامله از حساب تمرینی ۱۰٬۰۰۰ دلاری (قانون ۲٪ — محافظه‌کارانه‌تر)
  maxConsecLosses: 3, // فیوز ضرر متوالی: ۳ ضرر پشت‌سرهم ⇒ توقف خودکار ثبت سیگنال جدید
  autoPauseHours: 24, // مدت توقف خودکار پس از فیوز (ساعت)
} as const;

/** نتیجه آماری کارنامک — هر معیار null یعنی «نامشخص» (بخش ۳۷.۲: بدون عدد ساختگی) */
export interface PaperStats {
  total: number;
  openCount: number;
  closedCount: number;
  wins: number | null;
  losses: number | null;
  winRatePct: number | null;
  profitFactor: number | null; // null = نامشخص؛ Infinity = بی‌نهایت (هیچ ضرری نبوده)
  avgReturnPct: number | null;
  bestTradePct: number | null;
  worstTradePct: number | null;
  maxDrawdownPct: number | null; // روی منحنی بازده تجمعی (واحد درصد)
  avgMfePct: number | null;
  avgMaePct: number | null;
  avgHoldHours: number | null;
  grossProfitPct: number | null;
  grossLossPct: number | null;
  // --- آمار تفکیکی جهت (کارنامه نسخه ۲) — null یعنی نمونه کافی نیست ---
  longClosed: number | null; // تعداد معاملات خرید بسته‌شده
  longWinRatePct: number | null; // نرخ برد سمت خرید
  shortClosed: number | null; // تعداد معاملات فروش بسته‌شده
  shortWinRatePct: number | null; // نرخ برد سمت فروش
  // --- ممیزی Task 41 (افزودنی) ---
  breakevens?: number | null; // تعداد سربه‌سرها (نه برد، نه باخت)
  avgWinPct?: number | null; // میانگین سود معاملات برنده (٪ خالص)
  avgLossPct?: number | null; // میانگین زیان معاملات بازنده (٪ خالص، عدد منفی)
  expectancyPct?: number | null; // امید ریاضی هر معامله پس از هزینه‌ها (٪)
  longNetPct?: number | null; // مجموع بازده خالص سمت خرید (pp)
  shortNetPct?: number | null; // مجموع بازده خالص سمت فروش (pp)
  strategyBreakdown?: StatBreakdownRow[] | null; // تفکیک نسخه موتور (v1/v2)
  exitReasonBreakdown?: StatBreakdownRow[] | null; // تفکیک علت خروج (TP/SL/TIME/MANUAL)
  symbolBreakdown?: StatBreakdownRow[] | null; // تفکیک نماد
  incompleteCount?: number | null; // معاملات با داده ناقص/غیرقابل‌تأیید — پنهان نمی‌شوند
  incompleteIds?: string[] | null; // شناسه همان معاملات (شفافیت کامل)
  monetaryPnlUsd?: number | null; // سود زیان پولی فقط برای معاملات دارای sizeUsd؛ null = داده کافی نیست
  monetaryTrades?: number | null; // چند معامله اندازه دلاری معتبر داشتند
  reconciliation?: PnlReconciliation | null; // نتیجه تطبیق ذخیره‌شده در برابر بازمحاسبه
  feePctApplied?: number | null; // کارمزد رفت‌وبرگشت اعمال‌شده در همین آمار
}

// --- فیلدهای ممیزی Task 41 — افزودنی و سازگار با قبلی؛ null = «داده کافی نیست» ---

/** یک سطر تفکیک (نماد / علت خروج / استراتژی) */
export interface StatBreakdownRow {
  key: string; // مثلا "BTCUSDT" یا "TP" یا "mari-paper-v1"
  count: number; // تعداد معاملات بسته‌شده این گروه
  wins: number; // تعداد برد این گروه
  netPct: number; // مجموع بازده خالص گروه (واحد: درصد)
}

/** نتیجه تطبیق بازده ذخیره‌شده با بازمحاسبه از قیمت خام (بدون هیچ بازنویسی تاریخچه) */
export interface PnlReconciliation {
  checked: number; // چند معامله بسته‌شده بازمحاسبه شد
  mismatchCount: number; // چند مورد اختلاف معنادار (فراتر از 1e-6) پیدا شد
  mismatches: { id: string; storedPct: number; recomputedPct: number; deltaPct: number }[]; // حداکثر ۲۰ مورد
}

/** خروجی API گزارش کارنامک */
export interface PaperReport {
  ok: true;
  asof: number; // زمان تولید گزارش (بخش ۳۶.۵: generated_at)
  evaluatedAt: number | null; // آخرین ارزیابی قیمت‌ها
  scanSymbolCount: number; // چند نماد بررسی شدند
  params: typeof PAPER_PARAMS;
  stats: PaperStats;
  trades: PaperTrade[]; // جدیدترین اول
  equityCurve: { t: number; v: number }[]; // منحنی بازده تجمعی (نقاط بسته‌شدن)
  paused: boolean; // وضعیت توقف اضطراری ثبت سیگنال
  quality: CandleQualitySnapshot | null; // آخرین بررسی کیفیت کندل‌ها
  heartbeat?: {
    active: boolean; // قلب تپنده ربات روشن است؟ (چرخه خودکار هر ۱۰ دقیقه)
    lastRunAt: number | null; // آخرین چرخه خودکار
    runCount: number; // چند چرخه خودکار اجرا شده
    intervalMinutes: number;
  };
  autoPausedUntil?: number | null; // فیوز ضرر متوالی فعال است؟ تا چه زمانی؟
  autoPauseReason?: string | null; // توضیح فارسی فیوز
  consecutiveLosses?: number | null; // تعداد ضررهای پشت‌سرهم پایان کارنامه (null = نامشخص)
  reconciliation?: PnlReconciliation | null; // ممیزی Task 41: تطبیق بازده ذخیره‌شده با بازمحاسبه
  notes: string[]; // یادداشت‌های صادقانه
}
