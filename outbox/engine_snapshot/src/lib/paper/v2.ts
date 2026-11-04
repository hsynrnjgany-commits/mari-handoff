// MARI — موتور کارنامک نسخه ۲ (mari-paper-v2): فرمول‌های حرفه‌ای تریدرهای بزرگ
// هر قاعده از کتاب‌ها و قواعد شناخته‌شده معامله‌گری گرفته شده و «به‌صورت قطعی و قابل بازتولید» پیاده شده است:
//  ۱) «روند دوست توست» — ورود خرید فقط بالای میانگین ۵۰ دوره؛ ورود فروش فقط زیر آن (قاعده کلاسیک روند)
//  ۲) «در اشباع خرید نخر، در اشباع فروش نفروش» — فیلتر RSI(۱۴) روی ورودها
//  ۳) حد ضرر دینامیک با ATR (وایلدر) — ریسک هر بازار با نوسان خودش تنظیم می‌شود، نه درصد ثابت
//  ۴) «هرگز نگذار برنده، بازنده شود» — حد ضرر سربه‌سر (Breakeven + کارمزد) پس از حرکت مطلوب (Paul Tudor Jones)
//  ۵) «اجازه بده سودها بدوند» — حد ضرر متحرک (Trailing) پس از ورود سودمند (Jesse Livermore)
//  ۶) «قانون ۲٪» — در هر معامله فقط بخش کوچکی از سرمایه در معرض ریسک است (قاعده مدیریت سرمایه)
//  ۷) «همه تخم‌مرغ‌ها در یک سبد نباشد» — حداکثر ۵ معامله باز هم‌زمان
//  ۸) فیوز ضرر متوالی — ۳ ضرر پشت‌سرهم ⇒ توقف خودکار ۲۴ ساعته ثبت سیگنال جدید (انضباط، نه احساس)
// اصل ثابت: READ ONLY | PAPER ONLY | NO LIVE ORDERS
// این ماژول هیچ دسترسی شبکه‌ای و هیچ وابستگی به داده «در حال تشکیل» ندارد؛ فقط کندل‌های بسته‌شده.

import type { IndicatorSnapshot } from "@/lib/market/types";
import type { KlinePoint } from "@/lib/market/types";
import type { PaperSide } from "./types";

// ---------- پارامترهای نسخه ۲ — شفاف و اعلام‌شده (بخش ۲۸ سند مادر) ----------
export const V2_PARAMS = {
  atrPeriod: 14, // دوره ATR وایلدر
  atrSlMult: 1.5, // حد ضرر = ۱.۵ برابر ATR (استاندارد رایج حرفه‌ای)
  rrMult: 2, // حد سود = ۲ برابر فاصله حد ضرر (نسبت سود به ریسک ۲)
  slFloorPct: 1.0, // کف حد ضرر (٪) — مثل نسخه ۱، بازارهای خیلی آرام بیش از حد نزدیک نباشند
  slCapPct: 3.5, // سقف حد ضرر (٪) — نوسان شدید به معنای ریسک نامحدود نیست
  beTriggerPct: 1.0, // پس از ۱٪ حرکت مطلوب، حد ضرر به سربه‌سر (+کارمزد) منتقل می‌شود
  trailTriggerPct: 2.0, // پس از ۲٪ حرکت مطلوب، حد ضرر متحرک فعال می‌شود
  trailGapPct: 1.2, // فاصله حد ضرر متحرک از بهترین قیمت (٪) — سبک Chandelier
  maxOpenPositions: 5, // حداکثر معاملات باز هم‌زمان
  riskPerTradePct: 1.0, // ریسک هر معامله از حساب تمرینی (قانون ۲٪ — محافظه‌کارانه‌تر: ۱٪)
  paperEquityUsd: 10_000, // حساب تمرینی فرضی برای نمایش اندازه پوزیشن
  maxConsecLosses: 3, // فیوز ضرر متوالی
  autoPauseMs: 24 * 3_600_000, // مدت توقف خودکار پس از فیوز
} as const;

// ---------- ATR وایلدر (٪ نسبت به آخرین قیمت بسته) ----------
/** میانگین دامنه واقعی — خروجی: ATR درصدی (نسبت به آخرین بسته) یا null اگر داده کافی نباشد */
export function computeAtrPct(closed: KlinePoint[], period = V2_PARAMS.atrPeriod): number | null {
  if (closed.length < period + 2) return null; // حداقل داده برای هموارسازی وایلدر
  const trs: number[] = [];
  for (let i = 1; i < closed.length; i++) {
    const hi = closed[i].high;
    const lo = closed[i].low;
    const prevClose = closed[i - 1].close;
    const tr = Math.max(hi - lo, Math.abs(hi - prevClose), Math.abs(lo - prevClose));
    trs.push(tr);
  }
  if (trs.length < period) return null;
  let atr = trs.slice(0, period).reduce((s, v) => s + v, 0) / period;
  for (let i = period; i < trs.length; i++) {
    atr = (atr * (period - 1) + trs[i]) / period;
  }
  const lastClose = closed[closed.length - 1].close;
  if (!Number.isFinite(atr) || !Number.isFinite(lastClose) || lastClose <= 0) return null;
  return (atr / lastClose) * 100;
}

// ---------- فیلتر ورود نسخه ۲ (روند + اشباع) ----------
export interface V2EntryFilterResult {
  allowed: boolean;
  reasons: string[]; // دلایل فارسی برای ثبت در شواهد ورود
  blockedBy: string[]; // اگر رد شد، کدام قاعده رد کرد
}

/**
 * فیلتر ورود حرفه‌ای — روی همان سیگنال موتور ۵ رأیی اعمال می‌شود (لایه دوم تاییدیه).
 *  - خرید: قیمت باید بالای MA50 باشد (روند صعودی) و RSI در اشباع خرید نباشد
 *  - فروش: قیمت باید زیر MA50 باشد (روند نزولی) و RSI در اشباع فروش نباشد
 */
export function v2EntryFilter(side: PaperSide, ind: IndicatorSnapshot): V2EntryFilterResult {
  const reasons: string[] = [];
  const blockedBy: string[] = [];

  const price = ind.price;
  const ma50 = ind.ma50;
  const rsi = ind.rsi14;

  // قاعده ۱: روند دوست توست — قیمت نسبت به MA50
  const trendOk = price !== null && ma50 !== null && (side === "LONG" ? price > ma50 : price < ma50);
  if (price === null || ma50 === null) {
    blockedBy.push("داده MA50 کافی نیست");
  } else if (trendOk) {
    reasons.push(
      side === "LONG"
        ? "روند دوست توست: قیمت بالای میانگین ۵۰ دوره است"
        : "روند نزولی: قیمت زیر میانگین ۵۰ دوره است"
    );
  } else {
    blockedBy.push(
      side === "LONG"
        ? "قیمت زیر میانگین ۵۰ است — خرید خلاف روند ممنوع"
        : "قیمت بالای میانگین ۵۰ است — فروش خلاف روند ممنوع"
    );
  }

  // قاعده ۲: در اشباع خرید نخر، در اشباع فروش نفروش — فیلتر RSI
  const notExtreme = rsi !== null && (side === "LONG" ? rsi < 70 : rsi > 30);
  if (rsi === null) {
    blockedBy.push("داده RSI کافی نیست");
  } else if (notExtreme) {
    reasons.push(
      side === "LONG"
        ? `RSI در اشباع خرید نیست (${fa2(rsi)}) — ممنوعیت خرید گران اعمال نشد`
        : `RSI در اشباع فروش نیست (${fa2(rsi)}) — ممنوعیت فروش ارزان اعمال نشد`
    );
  } else {
    blockedBy.push(
      side === "LONG"
        ? `RSI در اشباع خرید است (${fa2(rsi)}) — خرید در اوج ممنوع`
        : `RSI در اشباع فروش است (${fa2(rsi)}) — فروش در کف ممنوع`
    );
  }

  return { allowed: blockedBy.length === 0, reasons, blockedBy };
}

// ---------- حد ضرر / حد سود دینامیک ATR ----------
export interface V2Stops {
  slPct: number; // درصد فاصله حد ضرر
  tpPct: number; // درصد فاصله حد سود
  basis: "ATR";
  atrPct: number | null; // اگر null یعنی داده کافی نبود و به کف نسخه ۱ برگشتیم
}

/**
 * حد ضرر دینامیک: ۱.۵ × ATR با کف ۱٪ و سقف ۳.۵٪ ؛ حد سود = ۲ برابر حد ضرر (R/R = ۲).
 * اگر ATR قابل محاسبه نبود، صادقانه به مقدار ثابت نسخه ۱ (۱٪) برمی‌گردیم و basis همان ATR با atrPct=null ثبت می‌شود.
 */
export function computeV2Stops(atrPct: number | null): V2Stops {
  if (atrPct === null || !Number.isFinite(atrPct) || atrPct <= 0) {
    return { slPct: 1.0, tpPct: 2.0, basis: "ATR", atrPct: null };
  }
  const sl = Math.min(V2_PARAMS.slCapPct, Math.max(V2_PARAMS.slFloorPct, atrPct * V2_PARAMS.atrSlMult));
  const tp = sl * V2_PARAMS.rrMult;
  return { slPct: round4(sl), tpPct: round4(tp), basis: "ATR", atrPct: round4(atrPct) };
}

// ---------- اندازه پوزیشن (قانون ریسک ثابت) ----------
/**
 * اندازه تمرینی: ریسک هر معامله = riskPerTradePct از حساب تمرینی.
 * sizeUsd = (ریسک دلاری) ÷ (فاصله حد ضرر به کسر) — یعنی اگر حد ضرر بخورد، دقیقا همان ریسک کسر می‌شود.
 */
export function positionSizeUsd(slPct: number): number {
  if (!Number.isFinite(slPct) || slPct <= 0) return 0;
  const riskUsd = (V2_PARAMS.paperEquityUsd * V2_PARAMS.riskPerTradePct) / 100;
  return round2(riskUsd / (slPct / 100));
}

function round4(n: number): number {
  return Math.round(n * 10000) / 10000;
}

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}

function fa2(n: number): string {
  return n.toLocaleString("fa-IR", { maximumFractionDigits: 1 });
}
