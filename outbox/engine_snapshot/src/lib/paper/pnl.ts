// MARI — ریاضیات بازده معاملات تمرینی (تک‌منبع حقیقت — Task 41)
// فرمول مرجع دستور اجرایی:
//   خرید:  (Exit − Entry) / Entry × 100
//   فروش:  (Entry − Exit) / Entry × 100
// هر دو سمت بر «مبنای قیمت ورود» هستند؛ مخرج هرگز قیمت خروج نیست.
// کارمزد فرضی رفت‌وبرگشت فقط «یک بار» در انتها کسر می‌شود (بدون کسر دوباره).
// اصل ثابت: READ ONLY | PAPER ONLY | NO LIVE ORDERS

import { PAPER_PARAMS } from "./types";

export type PnlSide = "LONG" | "SHORT";

/** مرز تشخیص سربه‌سر — خطای ممیز شناور معاملات سربه‌سرِ مهندسی‌شده (~1e-14) را پوشش می‌دهد */
export const BREAKEVEN_EPS = 1e-9;

/** بازده ناخالص بر مبنای قیمت ورود (٪) — بدون هیچ هزینه */
export function grossPct(side: PnlSide, entry: number, exit: number): number {
  if (!Number.isFinite(entry) || !Number.isFinite(exit) || entry <= 0) return Number.NaN;
  return side === "LONG" ? ((exit - entry) / entry) * 100 : ((entry - exit) / entry) * 100;
}

/** بازده خالص = ناخالص − کارمزد رفت‌وبرگشت (فقط یک بار) */
export function netPct(side: PnlSide, entry: number, exit: number): number {
  return grossPct(side, entry, exit) - PAPER_PARAMS.feePct;
}

/** آیا این بازده عملاً سربه‌سر است؟ (نه برد، نه باخت) */
export function isBreakeven(net: number): boolean {
  return Number.isFinite(net) && Math.abs(net) <= BREAKEVEN_EPS;
}
