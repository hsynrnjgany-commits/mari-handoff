// MARI — موتور کارنامک: ارزیابی معاملات باز + ثبت سیگنال‌های جدید (نسخه ۱)
// قواعد صریح و قابل بازتولید (بخش ۳۹.۵ و ۳۹.۱۱ سند مادر):
//  - سیگنال: همان موتور ۵ رأیی داشبورد (RSI/MACD/MA) — فقط روی کندل‌های بسته‌شده
//  - ورود: قیمت بسته‌شدن کندل سیگنال (زمان تصمیم فرضی = بسته‌شدن کندل، بدون نشت آینده)
//  - خروج: اولین برخورد حد ضرر یا حد سود در کندل‌های بعدی؛ اگر هر دو در یک کندل،
//    «بدبینانه» حد ضرر حساب می‌شود (اصل محافظه‌کاری، بخش ۴۰.۴)
//  - پایان مهلت: ۲۴ ساعت — خروج با قیمت آخرین کندل بسته‌شده
//  - کارمزد فرضی رفت‌وبرگشت: ۰.۱٪ (بخش ۳۹.۱۱)
// اصل ثابت: READ ONLY | PAPER ONLY | NO LIVE ORDERS

import "server-only";
import { getKlinesAny } from "@/lib/market/provider";
import { computeIndicators } from "@/lib/market/indicators";
import { buildSignal } from "@/lib/market/signal";
import { validateCandles } from "@/lib/market/quality";
import { INTERVALS, WATCH_SYMBOLS, type KlinePoint } from "@/lib/market/types";
import { getHunterUniverse, buildHunterBatch } from "@/lib/market/universe";
import { PAPER_PARAMS, type CandleQualitySnapshot, type PaperStoreShape, type PaperTrade } from "./types";
import { readStore, writeStore, trimStore } from "./store";
import { V2_PARAMS, computeAtrPct, computeV2Stops, v2EntryFilter, positionSizeUsd } from "./v2";
import { grossPct, netPct, BREAKEVEN_EPS } from "./pnl";
import { pushDecision, bePromotion, trailPromotion, openDecision } from "./decisionlog";

const { tpPct, slPct, feePct, maxHoldMs, cooldownMs, interval, sourceVersion } = PAPER_PARAMS;
const intervalMs = INTERVALS[interval].ms;

// نمادهای قابل بررسی: همه نمادهای غیر استیبل واچ‌لیست داشبورد
const SCAN_SYMBOLS = WATCH_SYMBOLS.filter((s) => !s.stable).map((s) => s.symbol);

function closeTimeMs(k: KlinePoint): number {
  return k.time * 1000 + intervalMs;
}

function pctChange(from: number, to: number): number {
  return ((to - from) / from) * 100;
}

function sidePnl(side: PaperTrade["side"], entry: number, price: number): number {
  // فرمول مرجع Task 41 (pnl.ts): هر دو سمت بر مبنای قیمت ورود —
  //  خرید: (price−entry)/entry — فروش: (entry−price)/entry
  // (اصلاح باگ قبلی: سمت فروش روی مخرج قیمت خروج محاسبه می‌شد)
  return grossPct(side, entry, price);
}

function closeTrade(t: PaperTrade, price: number, timeMs: number, reason: PaperTrade["exitReason"]): void {
  t.exitPrice = price;
  t.exitTime = timeMs;
  t.exitReason = reason;
  t.realizedPnlPct = netPct(t.side, t.entryPrice, price); // ناخالص − کارمزد رفت‌وبرگشت (فقط یک بار)
  t.status = "CLOSED";
}

/** ارزیابی یک معامله باز با کندل‌های بسته‌شده پس از ورود — قابل بازتولید */
function evaluateTrade(t: PaperTrade, candles: KlinePoint[], now: number): void {
  for (const k of candles) {
    if (t.status !== "OPEN") return;
    if (!k.closed) {
      t.lastPrice = k.close; // کندل در حال تشکیل فقط قیمت لحظه‌ای را به‌روز می‌کند
      continue;
    }
    const ct = closeTimeMs(k);
    if (ct <= t.entryTime) continue; // کندل‌های قبل یا هم‌زمان تصمیم — استفاده نمی‌شوند (بدون نشت آینده)
    t.lastPrice = k.close;
    t.lastCheck = now;
    if (t.side === "LONG") {
      // بدبینانه: اول حد ضرر — با سطح حد ضرر «قبل از این کندل» (ضد نشت آینده)
      if (k.low <= t.slPrice) {
        t.mfePct = Math.max(t.mfePct, pctChange(t.entryPrice, k.high));
        t.maePct = Math.min(t.maePct, pctChange(t.entryPrice, k.low));
        closeTrade(t, t.slPrice, ct, "SL");
        return;
      }
      if (k.high >= t.tpPrice) {
        t.mfePct = Math.max(t.mfePct, pctChange(t.entryPrice, k.high));
        t.maePct = Math.min(t.maePct, pctChange(t.entryPrice, k.low));
        closeTrade(t, t.tpPrice, ct, "TP");
        return;
      }
      t.mfePct = Math.max(t.mfePct, pctChange(t.entryPrice, k.high));
      t.maePct = Math.min(t.maePct, pctChange(t.entryPrice, k.low));
      // نسخه ۲: پس از بقا در این کندل، حد ضرر برای کندل‌های «آینده» به‌روز می‌شود (بدون نشت آینده)
      if (t.slBasis === "ATR") updateV2StopsLong(t, k);
    } else {
      // MFE/MAE فروش: حرکت مطلوب = ریزش (sidePnl فروش مثبت می‌شود) —
      // (اصلاح Task 41: قبلاً جهت‌ها وارونه ثبت می‌شدند)
      if (k.high >= t.slPrice) {
        t.mfePct = Math.max(t.mfePct, sidePnl("SHORT", t.entryPrice, k.low));
        t.maePct = Math.min(t.maePct, sidePnl("SHORT", t.entryPrice, k.high));
        closeTrade(t, t.slPrice, ct, "SL");
        return;
      }
      if (k.low <= t.tpPrice) {
        t.mfePct = Math.max(t.mfePct, sidePnl("SHORT", t.entryPrice, k.low));
        t.maePct = Math.min(t.maePct, sidePnl("SHORT", t.entryPrice, k.high));
        closeTrade(t, t.tpPrice, ct, "TP");
        return;
      }
      t.mfePct = Math.max(t.mfePct, sidePnl("SHORT", t.entryPrice, k.low));
      t.maePct = Math.min(t.maePct, sidePnl("SHORT", t.entryPrice, k.high));
      if (t.slBasis === "ATR") updateV2StopsShort(t, k);
    }
  }
  // پایان مهلت نگهداری — خروج با قیمت آخرین کندل بسته‌شده
  if (t.status === "OPEN" && now - t.entryTime >= maxHoldMs) {
    const lastClosed = [...candles].reverse().find((k) => k.closed && closeTimeMs(k) > t.entryTime);
    if (lastClosed) closeTrade(t, lastClosed.close, closeTimeMs(lastClosed), "TIME");
  }
}

// ---------- قواعد حد ضرر نسخه ۲ (فقط با داده کندلِ بسته‌شده جاری — اعمال از کندل بعدی) ----------

/** قاعده ۴ و ۵ برای خرید: سربه‌سر (Paul Tudor Jones) + حد ضرر متحرک (Livermore) */
function updateV2StopsLong(t: PaperTrade, k: KlinePoint): void {
  const favHigh = pctChange(t.entryPrice, k.high);
  if (!t.beActive && favHigh >= V2_PARAMS.beTriggerPct) {
    const bePrice = t.entryPrice * (1 + feePct / 100); // سربه‌سر پس از کارمزد — برنده تبدیل به بازنده نمی‌شود
    if (bePrice > t.slPrice) {
      const fromSl = t.slPrice; // لاگ payload لحظهٔ تصمیم (گیت ۰۰۳/SHORT-15) — منطق دست‌نخورده
      t.slPrice = bePrice;
      pushDecision(t, bePromotion(t, k, fromSl, t.slPrice, closeTimeMs(k)));
    }
    t.beActive = true;
  }
  if (favHigh >= V2_PARAMS.trailTriggerPct) {
    t.trailActive = true;
    t.trailExtremePct = Math.max(t.trailExtremePct ?? 0, Math.round(favHigh * 100) / 100);
    const trailSl = k.high * (1 - V2_PARAMS.trailGapPct / 100); // فاصله ثابت از بهترین قیمت
    if (trailSl > t.slPrice) {
      const fromSl = t.slPrice; // فقط سخت‌گیرانه‌تر — هرگز شل نمی‌شود (لاگ تصمیم)
      t.slPrice = trailSl;
      pushDecision(t, trailPromotion(t, k, fromSl, t.slPrice, closeTimeMs(k)));
    }
  }
}

/** قاعده ۴ و ۵ برای فروش — آینه نسخه خرید (مبنای مخرج: قیمت ورود — هماهنگ با سمت خرید) */
function updateV2StopsShort(t: PaperTrade, k: KlinePoint): void {
  const favLow = sidePnl("SHORT", t.entryPrice, k.low);
  if (!t.beActive && favLow >= V2_PARAMS.beTriggerPct) {
    const bePrice = t.entryPrice * (1 - feePct / 100);
    if (bePrice < t.slPrice) {
      const fromSl = t.slPrice; // لاگ payload لحظهٔ تصمیم — ریشهٔ ۱۵ مغایرت SHORT اکنون ثبت می‌شود
      t.slPrice = bePrice;
      pushDecision(t, bePromotion(t, k, fromSl, t.slPrice, closeTimeMs(k)));
    }
    t.beActive = true;
  }
  if (favLow >= V2_PARAMS.trailTriggerPct) {
    t.trailActive = true;
    t.trailExtremePct = Math.max(t.trailExtremePct ?? 0, Math.round(favLow * 100) / 100);
    const trailSl = k.low * (1 + V2_PARAMS.trailGapPct / 100);
    if (trailSl < t.slPrice) {
      const fromSl = t.slPrice; // فقط سخت‌گیرانه‌تر (لاگ تصمیم)
      t.slPrice = trailSl;
      pushDecision(t, trailPromotion(t, k, fromSl, t.slPrice, closeTimeMs(k)));
    }
  }
}

/** تعداد ضررهای واقعی پشت‌سرهم پایان کارنامه (برای فیوز ایمنی) —
 *  Task 41: سربه‌سرِ مهندسی‌شده (|خالص| ≤ 1e-9) باخت نیست و شمرده نمی‌شود */
function consecutiveLossCount(trades: PaperTrade[]): number {
  const closed = trades
    .filter((t) => t.status === "CLOSED" && typeof t.realizedPnlPct === "number")
    .sort((a, b) => (b.exitTime ?? 0) - (a.exitTime ?? 0));
  let n = 0;
  for (const t of closed) {
    if ((t.realizedPnlPct as number) < -BREAKEVEN_EPS) n += 1;
    else break;
  }
  return n;
}

function summarizeVotes(votes: ReturnType<typeof buildSignal>["votes"], side: PaperTrade["side"]): string {
  const used = votes.filter((v) => v.vote !== "neutral");
  const arrows = used.map((v) => `${v.label} ${v.vote === "up" ? "↑" : "↓"}`).join(" • ");
  return (side === "LONG" ? "خرید — " : "فروش — ") + (arrows || "بدون رأی مشخص");
}

/** ساخت معامله تمرینی از آخرین کندل بسته‌شده — نسخه ۲: فیلتر حرفه‌ای + حد ضرر دینامیک ATR
 *  خروجی به‌عنوان «کاندید مشاهده‌ای» هم استفاده می‌شود (مسیر /hunt) بدون اینکه وارد دفتر شود */
export function openFromSignal(
  symbol: string,
  exchange: PaperTrade["exchange"],
  candles: KlinePoint[],
  now: number
): PaperTrade | null {
  const closed = candles.filter((k) => k.closed);
  if (closed.length < 60) return null; // داده کافی برای اندیکاتورها نیست — صادقانه ثبت نمی‌کنیم
  const ind = computeIndicators(closed);
  const sig = buildSignal(ind);
  if (sig.action === "hold") return null;

  const isLong = sig.action === "buy";
  // لایه دوم تاییدیه — قواعد تریدرهای بزرگ: روند دوست توست + ممنوعیت ورود در اشباع
  const filter = v2EntryFilter(isLong ? "LONG" : "SHORT", ind);
  if (!filter.allowed) return null;

  // حد ضرر دینامیک ATR + حد سود دوبرابر فاصله ضرر (نسبت R/R = ۲)
  const stops = computeV2Stops(computeAtrPct(closed));

  const lastClosed = closed[closed.length - 1];
  const entryTime = closeTimeMs(lastClosed);
  const id = `${symbol}-${interval}-${entryTime}`;
  const entryPrice = lastClosed.close;
  const tpPrice = isLong ? entryPrice * (1 + stops.tpPct / 100) : entryPrice * (1 - stops.tpPct / 100);
  const slPrice = isLong ? entryPrice * (1 - stops.slPct / 100) : entryPrice * (1 + stops.slPct / 100);

  const trade: PaperTrade = {
    id,
    symbol,
    exchange,
    interval,
    side: isLong ? "LONG" : "SHORT",
    status: "OPEN",
    entryPrice,
    entryTime,
    tpPrice,
    slPrice,
    score: (sig.strength / 100) * 5 * (isLong ? 1 : -1), // بازسازی دقیق امتیاز خام از قدرت
    strength: sig.strength,
    reason:
      summarizeVotes(sig.votes, isLong ? "LONG" : "SHORT") +
      " • " +
      filter.reasons.join(" • ") +
      ` • حدضرر دینامیک ATR: ٪${stops.slPct.toLocaleString("fa-IR", { maximumFractionDigits: 2 })}` +
      (stops.atrPct === null ? " (داده نوسان کافی نبود — کف ثابت)" : ""),
    sourceVersion,
    lastPrice: entryPrice,
    lastCheck: now,
    mfePct: 0,
    maePct: 0,
    exitPrice: null,
    exitTime: null,
    exitReason: null,
    realizedPnlPct: null,
    createdAt: now,
    // فیلدهای نسخه ۲
    slBasis: stops.basis,
    atrPctAtEntry: stops.atrPct,
    plannedRiskPct: V2_PARAMS.riskPerTradePct,
    sizeUsd: positionSizeUsd(stops.slPct),
    beActive: false,
    trailActive: false,
    trailExtremePct: 0,
  };
  // لاگ payload لحظهٔ تصمیم ورود (گیت ۰۰۳) — بدون تغییر منطق انتخاب ورود
  pushDecision(trade, openDecision(symbol, lastClosed, trade.side, slPrice, tpPrice, stops.basis, entryTime));
  return trade;
}

export interface RunResult {
  store: PaperStoreShape;
  scanSymbolCount: number;
  universeCount: number; // جهان کشف‌شدهٔ شکارچی در این چرخه (۰ = اسکن انجام نشد یا در دسترس نبود)
  patrolCount: number; // چند نماد از چرخش گشت‌زنی این چرخه بررسی شد
  paused: boolean; // آیا ثبت سیگنال جدید متوقف است؟
  autoPaused: boolean; // آیا فیوز ضرر متوالی فعال است؟
  consecutiveLosses: number; // تعداد ضررهای پشت‌سرهم در پایان این چرخه
  quality: CandleQualitySnapshot; // نتیجه کنترل کیفیت کندل‌ها در همین چرخه (فاز ۲)
}

/** یک نوبت کامل: کنترل کیفیت + ارزیابی بازها + (در صورت عدم توقف) جست‌وجوی سیگنال جدید + ذخیره */
export async function runPaperCycle(): Promise<RunResult> {
  const now = Date.now();
  const store = readStore();
  const trades = [...store.trades];
  let evaluated = 0;
  let scanCount = 0;
  let universeCount = 0;
  let patrolCount = 0;
  const paused = store.paused === true;
  const quality: CandleQualitySnapshot = { at: now, ok: true, checkedSymbols: 0, okSymbols: 0, skippedSymbols: 0, issues: [] };

  // ---------- ۰) کنترل کیفیت داده (فاز ۲ — داده بی‌کیفیت به مرحله بعد تحویل نمی‌شود، بخش ۳۶.۳)
  const candlesUsable = (symbol: string, candles: KlinePoint[]): boolean => {
    const q = validateCandles(candles, intervalMs, now);
    quality.checkedSymbols += 1;
    if (q.ok) {
      quality.okSymbols += 1;
      return true;
    }
    quality.skippedSymbols += 1;
    quality.ok = false;
    if (quality.issues.length < 6) {
      for (const issue of q.issues) {
        if (quality.issues.length >= 6) break;
        quality.issues.push(`${symbol}: ${issue}`);
      }
    }
    console.error(`[paper-engine] کیفیت داده ${symbol} نامعتبر — این چرخه بدون آن نماد ادامه می‌یابد`);
    return false;
  };

  // ---------- ۱) ارزیابی معاملات باز
  const openTrades = trades.filter((t) => t.status === "OPEN");
  for (const t of openTrades) {
    try {
      const res = await getKlinesAny(t.symbol, interval, 200); // معاملات باز ممکن است خارج واچ‌لیست باشند — شکارچی
      if (!res || !candlesUsable(t.symbol, res.candles)) continue;
      evaluateTrade(t, res.candles, now);
      evaluated += 1;
    } catch (err) {
      console.error(`[paper-engine] ارزیابی ${t.symbol} ناموفق:`, err instanceof Error ? err.message : err);
    }
  }

  // ---------- ۱.۵) فیوز ضرر متوالی (فرمول انضباط — نسخه ۲)
  // تازه‌سازی فقط وقتی ضررهای پشت‌سرهم از شمارِ ثبت‌شده در فیوز قبلی بیشتر شده باشد؛
  // این‌طور پس از پایان مهلت توقف، موتور واقعا فرصت ادامه می‌یابد و قفل همیشگی رخ نمی‌دهد.
  let autoPausedUntil = store.autoPausedUntil ?? null;
  let autoPauseReason = store.autoPauseReason ?? null;
  let autoPauseAtConsec = store.autoPauseAtConsec ?? null;
  const consec = consecutiveLossCount(trades);
  const fuseExpired = autoPausedUntil === null || now >= autoPausedUntil;
  if (consec >= V2_PARAMS.maxConsecLosses && fuseExpired && (autoPauseAtConsec === null || consec > autoPauseAtConsec)) {
    autoPausedUntil = now + V2_PARAMS.autoPauseMs;
    autoPauseAtConsec = consec;
    autoPauseReason = `فیوز ایمنی: ${consec.toLocaleString("fa-IR", { useGrouping: false })} ضرر پشت‌سرهم — ثبت سیگنال جدید ${V2_PARAMS.autoPauseMs / 3_600_000} ساعت متوقف شد (قاعده انضباط نسخه ۲)`;
    console.warn(`[paper-engine] ${autoPauseReason}`);
  }
  const autoPaused = autoPausedUntil !== null && now < autoPausedUntil;

  // ---------- ۲) جست‌وجوی سیگنال جدید — در حالت توقف اضطراری یا فیوز انجام نمی‌شود (بخش ۳۹.۱۱)
  if (!paused && !autoPaused) {
    const openSymbols = new Set(trades.filter((t) => t.status === "OPEN").map((t) => t.symbol));
    // قاعده سبد: همه تخم‌مرغ‌ها در یک سبد نباشد — حداکثر ۵ معامله باز هم‌زمان (نسخه ۲)
    if (openSymbols.size >= V2_PARAMS.maxOpenPositions) {
      console.warn(
        `[paper-engine] سبد پر است (${openSymbols.size} معامله باز از حداکثر ${V2_PARAMS.maxOpenPositions}) — این چرخه سیگنال جدید جست‌وجو نمی‌شود`
      );
    } else {
    // ---------- سایه بر کل بازار (بخش ۶ و ۴۱ سند HANDOFF): Discover → Rank → Patrol ----------
    // هیچ کف حجمی حذف‌کننده وجود ندارد؛ نقدشوندگی فقط اولویت گشت‌زنی است.
    // اگر جهان شکار در دسترس نباشد، صادقانه به واچ‌لیست داشبورد برمی‌گردیم.
    let scanList: string[] = SCAN_SYMBOLS;
    try {
      const uni = await getHunterUniverse();
      if (uni.rows.length > 0) {
        const batch = buildHunterBatch(uni.rows, SCAN_SYMBOLS);
        scanList = batch.symbols;
        universeCount = uni.discovered;
        patrolCount = batch.patrolCount;
        console.log(
          `[paper-engine] گشت سایه: ${batch.symbols.length} نماد این چرخه (واچ‌لیست + سر ${batch.headCount} + گشت ${batch.patrolCount}) از ${uni.discovered} نماد کشف‌شده`
        );
      }
    } catch (err) {
      console.error("[paper-engine] جهان شکار در دسترس نبود — این چرخه فقط واچ‌لیست:", err instanceof Error ? err.message : err);
    }
    for (const symbol of scanList) {
      if (openSymbols.size >= V2_PARAMS.maxOpenPositions) break; // سبد در میانه اسکن هم پر شد — توقف
      if (openSymbols.has(symbol)) continue; // هر نماد حداکثر یک معامله باز
      // فاصله پس از بسته‌شدن آخرین معامله نماد (جلوگیری از ورود پشت‌سرهم — بخش ۳۶.۷)
      const lastClosedForSymbol = trades
        .filter((t) => t.symbol === symbol && t.status === "CLOSED")
        .sort((a, b) => (b.exitTime ?? 0) - (a.exitTime ?? 0))[0];
      if (lastClosedForSymbol?.exitTime && now - lastClosedForSymbol.exitTime < cooldownMs) continue;

      try {
        const res = await getKlinesAny(symbol, interval, 200); // اسکن کل جهان — نه فقط واچ‌لیست
        if (!res || !candlesUsable(symbol, res.candles)) continue;
        scanCount += 1;
        const t = openFromSignal(symbol, res.source, res.candles, now);
        if (!t) continue;
        // رکورد تکراری ممنوع (بخش ۳۶.۷): همان کندل ورود قبلاً ثبت شده؟
        if (trades.some((x) => x.id === t.id)) continue;
        trades.push(t);
        openSymbols.add(symbol);
      } catch (err) {
        console.error(`[paper-engine] جست‌وجوی ${symbol} ناموفق:`, err instanceof Error ? err.message : err);
      }
    }
    }
  }

  const next: PaperStoreShape = {
    version: 1,
    updatedAt: now,
    trades: trimStore(trades),
    paused,
    lastQuality: quality,
    autoPausedUntil,
    autoPauseReason,
    autoPauseAtConsec,
  };
  void writeStore(next);
  return { store: next, scanSymbolCount: scanCount, universeCount, patrolCount, paused, autoPaused, consecutiveLosses: consec, quality };
}
