// MARI — لاگ payload لحظهٔ تصمیم — رفع بلوکر مشاهده‌ناپذیری (گیت ۰۰۳، ریشهٔ SHORT-15)
// MODE: READ ONLY | PAPER ONLY | NO LIVE ORDERS
//
// خاستگاه: گیت ۰۰۳ — ۱۵ مغایرت SHORT بازپخش: سطح و زمان خروج ۱۵/۱۵ دقیقاً
// بازتولید شد، اما «رویداد ارتقای استاپ» (سربه‌سر/تریلینگ) در لحظهٔ تصمیم
// لاگ نمی‌شد و بازپخش را غیرقابل‌توضیح می‌گذاشت. پیشنهاد تأییدشدهٔ گیت ۰۰۳:
// لاگ منبع + هش OHLC در لحظهٔ تصمیم. این ماژول فقط «ثبت» می‌کند؛
// هیچ منطق معاملاتی را تغییر نمی‌دهد و هیچ شبکه‌ای باز نمی‌کند.
// هر ورودی: نوع تصمیم، زمان، هش sha256 کوتاه payload کندل محرک،
// سطح قبلی/جدید حد ضرر — تا هر خروج آینده دقیقاً بازپخش‌پذیر بماند.

import { createHash } from "node:crypto";
import type { KlinePoint } from "@/lib/market/types";
import type { PaperTrade } from "./types";

export type DecisionKind = "BE_PROMOTED" | "TRAIL_PROMOTED" | "OPEN";

export interface DecisionLogEntry {
  kind: DecisionKind; // نوع رویداد تصمیم
  timeMs: number; // زمان تصمیم (بسته‌شدن کندل محرک یا لحظه ورود)
  candleTime: number | null; // open_time کندل محرک (ثانیه) — null برای OPEN
  ohlcHash: string | null; // ۱۶ کاراکتر اول sha256 payload کندل — null برای OPEN
  fromSl: number | null; // حد ضرر پیش از تصمیم
  toSl: number | null; // حد ضرر پس از تصمیم
  detail: string; // توضیح صادقانه فارسی
  source: string; // شناسه ثابت تولیدکننده — بازتولیدپذیر
}

const DECISIONLOG_SOURCE = "mari-paper-v2/decisionlog/v1";

/** هش قطعی payload کندل محرک — بدون افشای قیمت کامل، فقط اثر انگشت برای بازپخش */
export function klineHash(symbol: string, k: KlinePoint): string {
  return createHash("sha256")
    .update(`${symbol}|${k.time}|${k.open}|${k.high}|${k.low}|${k.close}|${k.volume}`)
    .digest("hex")
    .slice(0, 16);
}

/** الحاق امن به دفتر تصمیم معامله — معاملات قدیمی فیلد را ندارند و همین‌جا ساخته می‌شود */
export function pushDecision(t: PaperTrade, entry: DecisionLogEntry): void {
  if (!t.decisions) t.decisions = [];
  t.decisions.push(entry);
}

/** ورودی OPEN — ثبت پایلود تصمیم ورود: سطوح برنامه‌ریزی‌شده و پایه حد ضرر */
export function openDecision(
  symbol: string,
  k: KlinePoint,
  side: PaperTrade["side"],
  slPrice: number,
  tpPrice: number,
  basis: PaperTrade["slBasis"],
  timeMs: number
): DecisionLogEntry {
  return {
    kind: "OPEN",
    timeMs,
    candleTime: k.time,
    ohlcHash: klineHash(symbol, k),
    fromSl: null,
    toSl: slPrice,
    detail: `ورود ${side} — حد ضرر ${slPrice} / حد سود ${tpPrice} / پایه ${basis ?? "FIXED"}`,
    source: DECISIONLOG_SOURCE,
  };
}

/** ارتقای سربه‌سر — رویدادی که در ۱۵ مغایرت SHORT دیده نمی‌شد */
export function bePromotion(
  t: PaperTrade,
  k: KlinePoint,
  fromSl: number,
  toSl: number,
  timeMs: number
): DecisionLogEntry {
  return {
    kind: "BE_PROMOTED",
    timeMs,
    candleTime: k.time,
    ohlcHash: klineHash(t.symbol, k),
    fromSl,
    toSl,
    detail: "ارتقای حد ضرر به سربه‌سر پس از کارمزد — لحظهٔ تصمیم اکنون ثبت است",
    source: DECISIONLOG_SOURCE,
  };
}

/** ارتقای تریلینگ — فقط وقتی حد ضرر واقعاً سخت‌گیرانه‌تر شد */
export function trailPromotion(
  t: PaperTrade,
  k: KlinePoint,
  fromSl: number,
  toSl: number,
  timeMs: number
): DecisionLogEntry {
  return {
    kind: "TRAIL_PROMOTED",
    timeMs,
    candleTime: k.time,
    ohlcHash: klineHash(t.symbol, k),
    fromSl,
    toSl,
    detail: "ارتقای حد ضرر متحرک — فقط سخت‌گیرانه‌تر، هرگز شل‌تر",
    source: DECISIONLOG_SOURCE,
  };
}
