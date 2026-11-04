// MARI — آمار کارنامک (بخش ۲۸ و ۳۷.۵ سند مادر) — نسخه ممیزی‌شده Task 41
// اصول این نسخه:
//  ۱) همه معیارها از «قیمت خام ورود/خروج» بازمحاسبه می‌شوند، نه از عدد ذخیره‌شده —
//     بازده ذخیره‌شده فقط با بازمحاسبه تطبیق داده می‌شود و اختلاف‌ها «پرچم» می‌خورند (بدون بازنویسی تاریخچه).
//  ۲) فرمول مرجع (pnl.ts): خرید (Exit−Entry)/Entry — فروش (Entry−Exit)/Entry — کارمزد رفت‌وبرگشت فقط یک بار.
//  ۳) سربه‌سر (|خالص| ≤ 1e-9) جداگانه شمرده می‌شود — نه برد، نه باخت.
//  ۴) هر معیار همراه با تعریف؛ مقدار null یعنی «نامشخص/داده کافی نیست» — عدد ساختگی ممنوع.
// نرخ برد = معاملات بسته‌شده سودده ÷ همه معاملات بسته‌شده
// Profit Factor = مجموع بازده سودده ÷ قدرمطلق مجموع زیان‌ها (مخرج صفر → بی‌نهایت یا نامشخص)
// حداکثر افت سرمایه = بیشترین فاصله اوج تا کف روی منحنی بازده تجمعی (واحد: واحد درصد pp)

import type { PaperStats, PaperTrade, StatBreakdownRow, PnlReconciliation } from "./types";
import { PAPER_PARAMS } from "./types";
import { netPct, grossPct, isBreakeven, BREAKEVEN_EPS } from "./pnl";

// کارمزد اعمال‌شده در همین آمار — از همان منبع موتور خوانده می‌شود تا همیشه یکی باشد
const PAPER_FEE_SNAPSHOT: number = PAPER_PARAMS.feePct;

/** بازده معتبر یک معامله بسته‌شده از قیمت خام؛ اگر قیمت‌ها معتبر نیستند null */
function recomputedNet(t: PaperTrade): number | null {
  if (t.exitPrice === null || t.exitPrice === undefined || !Number.isFinite(t.entryPrice)) return null;
  const net = netPct(t.side, t.entryPrice, t.exitPrice);
  return Number.isFinite(net) ? net : null;
}

function breakdown(
  closed: PaperTrade[],
  nets: Map<string, number>,
  keyFn: (t: PaperTrade) => string
): StatBreakdownRow[] {
  const map = new Map<string, StatBreakdownRow>();
  for (const t of closed) {
    const key = keyFn(t);
    const net = nets.get(t.id) ?? 0;
    const row = map.get(key) ?? { key, count: 0, wins: 0, netPct: 0 };
    row.count += 1;
    if (net > BREAKEVEN_EPS) row.wins += 1;
    row.netPct = Math.round((row.netPct + net) * 1e6) / 1e6;
    map.set(key, row);
  }
  return [...map.values()].sort((a, b) => b.netPct - a.netPct);
}

export function computeStats(trades: PaperTrade[]): PaperStats {
  const open = trades.filter((t) => t.status === "OPEN");
  const closedAll = trades.filter((t) => t.status === "CLOSED");

  // بازمحاسبه + تطبیق با مقدار ذخیره‌شده (پرچم اختلاف — هیچ بازنویسی‌ای انجام نمی‌شود)
  const mismatches: PnlReconciliation["mismatches"] = [];
  const nets = new Map<string, number>();
  const incompleteIds: string[] = [];
  let checked = 0;
  for (const t of closedAll) {
    const rec = recomputedNet(t);
    if (rec === null) {
      incompleteIds.push(t.id); // داده ناقص — پنهان نمی‌شود، علامت می‌خورد
      continue;
    }
    checked += 1;
    nets.set(t.id, rec);
    const stored = t.realizedPnlPct;
    if (typeof stored === "number" && Math.abs(stored - rec) > 1e-6 && mismatches.length < 20) {
      mismatches.push({
        id: t.id,
        storedPct: Math.round(stored * 1e6) / 1e6,
        recomputedPct: Math.round(rec * 1e6) / 1e6,
        deltaPct: Math.round((stored - rec) * 1e6) / 1e6,
      });
    }
  }
  const closed = closedAll.filter((t) => nets.has(t.id)).sort((a, b) => (a.exitTime ?? 0) - (b.exitTime ?? 0));

  const base: PaperStats = {
    total: trades.length,
    openCount: open.length,
    closedCount: closedAll.length,
    wins: null,
    losses: null,
    winRatePct: null,
    profitFactor: null,
    avgReturnPct: null,
    bestTradePct: null,
    worstTradePct: null,
    maxDrawdownPct: null,
    avgMfePct: null,
    avgMaePct: null,
    avgHoldHours: null,
    grossProfitPct: null,
    grossLossPct: null,
    longClosed: null,
    longWinRatePct: null,
    shortClosed: null,
    shortWinRatePct: null,
  };

  if (closed.length === 0) {
    return {
      ...base,
      breakevens: 0,
      incompleteCount: incompleteIds.length,
      incompleteIds: incompleteIds.length > 0 ? incompleteIds : null,
      monetaryPnlUsd: null,
      monetaryTrades: 0,
      reconciliation: { checked: 0, mismatchCount: 0, mismatches: [] },
      feePctApplied: null,
    };
  }

  const pnls = closed.map((t) => nets.get(t.id) as number);
  const winsArr = pnls.filter((p) => p > BREAKEVEN_EPS);
  const lossesArr = pnls.filter((p) => p < -BREAKEVEN_EPS);
  const beArr = pnls.filter((p) => isBreakeven(p));
  const grossProfit = winsArr.reduce((s, p) => s + p, 0);
  const grossLoss = Math.abs(lossesArr.reduce((s, p) => s + p, 0));

  // منحنی بازده تجمعی + حداکثر افت سرمایه
  let cum = 0;
  let peak = 0;
  let maxDd = 0;
  for (const p of pnls) {
    cum += p;
    if (cum > peak) peak = cum;
    const dd = peak - cum;
    if (dd > maxDd) maxDd = dd;
  }

  const holds = closed
    .filter((t) => t.exitTime !== null && t.exitTime > t.entryTime)
    .map((t) => ((t.exitTime as number) - t.entryTime) / 3_600_000);

  const avg = (arr: number[]): number | null =>
    arr.length === 0 ? null : arr.reduce((s, v) => s + v, 0) / arr.length;

  // آمار تفکیکی جهت — هر سمت فقط وقتی گزارش می‌شود که نمونه بسته‌شده داشته باشد
  const longs = closed.filter((t) => t.side === "LONG");
  const shorts = closed.filter((t) => t.side === "SHORT");
  const sideWinRate = (arr: PaperTrade[]): number | null => {
    if (arr.length === 0) return null;
    const w = arr.filter((t) => (nets.get(t.id) as number) > BREAKEVEN_EPS).length;
    return (w / arr.length) * 100;
  };
  const sideSum = (arr: PaperTrade[]): number | null =>
    arr.length === 0 ? null : arr.reduce((s, t) => s + (nets.get(t.id) as number), 0);

  // سود زیان پولی — فقط معاملاتی که اندازه دلاری معتبر دارند (بقیه: داده کافی نیست)
  const sized = closed.filter((t) => typeof t.sizeUsd === "number" && (t.sizeUsd as number) > 0);
  const monetaryPnlUsd =
    sized.length === 0
      ? null
      : sized.reduce((s, t) => s + ((t.sizeUsd as number) * (nets.get(t.id) as number)) / 100, 0);

  const reconciliation: PnlReconciliation = {
    checked,
    mismatchCount: mismatches.length,
    mismatches,
  };

  return {
    ...base,
    wins: winsArr.length,
    losses: lossesArr.length,
    breakevens: beArr.length,
    winRatePct: (winsArr.length / closed.length) * 100,
    // PF: اگر زیانی نبوده و سود بوده = بی‌نهایت؛ اگر هیچ‌کدام = نامشخص
    profitFactor: grossLoss > 0 ? grossProfit / grossLoss : grossProfit > 0 ? Number.POSITIVE_INFINITY : null,
    avgReturnPct: avg(pnls),
    expectancyPct: avg(pnls), // امید ریاضی هر معامله پس از هزینه‌ها = میانگین بازده خالص
    bestTradePct: Math.max(...pnls),
    worstTradePct: Math.min(...pnls),
    maxDrawdownPct: maxDd,
    avgMfePct: avg(closed.map((t) => t.mfePct)),
    avgMaePct: avg(closed.map((t) => t.maePct)),
    avgHoldHours: avg(holds),
    grossProfitPct: grossProfit,
    grossLossPct: grossLoss,
    avgWinPct: avg(winsArr),
    avgLossPct: avg(lossesArr),
    longClosed: longs.length,
    longWinRatePct: sideWinRate(longs),
    longNetPct: sideSum(longs),
    shortClosed: shorts.length,
    shortWinRatePct: sideWinRate(shorts),
    shortNetPct: sideSum(shorts),
    strategyBreakdown: breakdown(closed, nets, (t) => t.sourceVersion),
    exitReasonBreakdown: breakdown(closed, nets, (t) => t.exitReason ?? "نامشخص"),
    symbolBreakdown: breakdown(closed, nets, (t) => t.symbol),
    incompleteCount: incompleteIds.length,
    incompleteIds: incompleteIds.length > 0 ? incompleteIds : null,
    monetaryPnlUsd: monetaryPnlUsd === null ? null : Math.round(monetaryPnlUsd * 100) / 100,
    monetaryTrades: sized.length,
    reconciliation,
    feePctApplied: PAPER_FEE_SNAPSHOT,
  };
}


/** نقاط منحنی بازده تجمعی به ترتیب زمان بسته‌شدن — از قیمت خام بازمحاسبه می‌شود */
export function buildEquityCurve(trades: PaperTrade[]): { t: number; v: number }[] {
  const closed = trades
    .filter((t) => t.status === "CLOSED" && t.exitTime !== null && recomputedNet(t) !== null)
    .sort((a, b) => (a.exitTime as number) - (b.exitTime as number));
  const out: { t: number; v: number }[] = [];
  let cum = 0;
  for (const t of closed) {
    cum += recomputedNet(t) as number;
    out.push({ t: t.exitTime as number, v: Number(cum.toFixed(4)) });
  }
  return out;
}

// خروجی‌های کمکی برای گزارش تلگرام (بدون عدد ساختگی)
export { grossPct, netPct, isBreakeven };
