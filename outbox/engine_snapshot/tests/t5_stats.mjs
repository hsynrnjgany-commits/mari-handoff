// M73-R آزمون ۵ — §۵-⑤ آمار: Win Rate / Profit Factor / Expectancy / Max Drawdown
// ماژول واقعی: src/lib/paper/stats.ts → computeStats / buildEquityCurve
// داده سینتتیک با «پاسخ‌های معلوم» — همه از قیمت خام بازمحاسبه می‌شوند
import { writeFileSync, mkdirSync } from "node:fs";
import { computeStats, buildEquityCurve } from "@/lib/paper/stats";

const OUT = "/home/z/my-project/scripts/m73p/sandbox/out/t5_stats.json";
const checks = [];
const add = (name, passed, detail) => checks.push({ name, verdict: passed ? "PASS" : "FAIL", detail });
const near = (a, b, eps = 1e-6) => Math.abs(a - b) <= eps;

function mk(id, side, entry, exit, exitTime, opts = {}) {
  return {
    id, symbol: opts.symbol ?? "SYNUSDT", exchange: "toobit", interval: "1h", side,
    status: opts.status ?? "CLOSED",
    entryPrice: entry, entryTime: exitTime - 3_600_000, tpPrice: 0, slPrice: 0,
    score: 1, strength: 50, reason: "fixture", sourceVersion: opts.version ?? "mari-paper-v2",
    lastPrice: exit, lastCheck: exitTime, mfePct: opts.mfe ?? 0, maePct: opts.mae ?? 0,
    exitPrice: exit, exitTime, exitReason: opts.reason ?? "TP",
    realizedPnlPct: opts.stored ?? null, createdAt: exitTime - 3_600_000,
    sizeUsd: opts.size ?? null,
  };
}

const T = 1_700_000_000_000;
// ۴ معامله با پاسخ معلوم (خالص = ناخالص − ۰.۱):
//  L1: LONG 100→102 → +1.9   (exit T+1h)
//  S1: SHORT 100→98 → +1.9   (exit T+2h)
//  L2: LONG 100→99  → −1.1   (exit T+3h)
//  S2: SHORT 100→101 → −1.1  (exit T+4h)
//  WR = ۲/۴ = ۵۰٪ — PF = ۳.۸/۲.۲ = ۱.۷۲۷۲... — Expectancy = میانگین = +۰.۴
//  منحنی: [1.9, 3.8, 2.7, 1.6] — اوج ۳.۸، کف پس از اوج ۱.۶ → MDD = ۲.۲
const trades = [
  mk("A1", "LONG", 100, 102, T + 1 * 3_600_000, { stored: 1.9, size: 2000 }),
  mk("A2", "SHORT", 100, 98, T + 2 * 3_600_000, { stored: 1.9, size: 2000 }),
  mk("A3", "LONG", 100, 99, T + 3 * 3_600_000, { stored: -1.1, size: 2000 }),
  mk("A4", "SHORT", 100, 101, T + 4 * 3_600_000, { stored: -1.1, size: 2000 }),
];
const s = computeStats(trades);

add("تعداد کل/بسته/باز", s.total === 4 && s.closedCount === 4 && s.openCount === 0, `${s.total}/${s.closedCount}/${s.openCount}`);
add("Win Rate = ۵۰٪", near(s.winRatePct, 50), `${s.winRatePct}`);
add("بردها=۲ باخت‌ها=۲", s.wins === 2 && s.losses === 2, `${s.wins}/${s.losses}`);
add("Profit Factor = ۳.۸/۲.۲ ≈ ۱.۷۲۷۲۷", near(s.profitFactor, 3.8 / 2.2, 1e-4), `${s.profitFactor}`);
add("Expectancy = میانگین خالص = +۰.۴٪", near(s.expectancyPct, 0.4), `${s.expectancyPct}`);
add("avgReturnPct هم‌ارز Expectancy", near(s.avgReturnPct, 0.4), `${s.avgReturnPct}`);
add("Max Drawdown = ۲.۲ واحد درصد", near(s.maxDrawdownPct, 2.2), `${s.maxDrawdownPct}`);
add("سود ناخالص=۳.۸ زیان ناخالص=۲.۲", near(s.grossProfitPct, 3.8) && near(s.grossLossPct, 2.2), `${s.grossProfitPct}/${s.grossLossPct}`);
add("بهترین=+۱.۹ بدترین=−۱.۱", near(s.bestTradePct, 1.9) && near(s.worstTradePct, -1.1), `${s.bestTradePct}/${s.worstTradePct}`);
add("تفکیک جهت: LONG×۲ با WR ۵۰٪ — SHORT×۲ با WR ۵۰٪", s.longClosed === 2 && near(s.longWinRatePct, 50) && s.shortClosed === 2 && near(s.shortWinRatePct, 50), `L:${s.longClosed}/${s.longWinRatePct} S:${s.shortClosed}/${s.shortWinRatePct}`);
add("تفکیک جهت: جمع خالص LONG=+۰.۸ — SHORT=+۰.۸", near(s.longNetPct, 0.8) && near(s.shortNetPct, 0.8), `${s.longNetPct}/${s.shortNetPct}`);
add("کارمزد اعمال‌شده در آمار = ۰.۱", near(s.feePctApplied, 0.1), `${s.feePctApplied}`);
add("تطبیق: ۴ بازمحاسبه، صفر مغایرت", s.reconciliation.checked === 4 && s.reconciliation.mismatchCount === 0, JSON.stringify(s.reconciliation));

// PF بی‌نهایت — بدون هیچ باخت
const allWin = [mk("W1", "LONG", 100, 102, T + 1 * 3_600_000, { stored: 1.9 })];
add("PF بدون باخت = بی‌نهایت", computeStats(allWin).profitFactor === Number.POSITIVE_INFINITY, `${computeStats(allWin).profitFactor}`);

// PF نامشخص — بدون سود و بدون زیان (همه سربه‌سر) → null (بدون عدد ساختگی)
const beTrade = mk("BE1", "LONG", 100, 100.1, T + 1 * 3_600_000, { stored: 0, reason: "MANUAL" }); // خالص ≈ ۰
const sBe = computeStats([beTrade]);
add("سربه‌سر مهندسی‌شده جدا شمرده شد (نه برد نه باخت)", sBe.breakevens === 1 && sBe.wins === 0 && sBe.losses === 0, `BE=${sBe.breakevens} W=${sBe.wins} L=${sBe.losses}`);
add("PF همه-سربه‌سر = null (نامشخص، نه صفر)", sBe.profitFactor === null, `${sBe.profitFactor}`);

// مغایرت عمدی — شفاف پرچم می‌خورد، تاریخچه بازنویسی نمی‌شود
const lier = mk("X1", "LONG", 100, 102, T + 1 * 3_600_000, { stored: 5.0 });
const sMis = computeStats([lier]);
add("مقدار ذخیره‌شده غلط (۵.۰) پرچم مغایرت خورد", sMis.reconciliation.mismatchCount === 1 && sMis.reconciliation.mismatches[0]?.id === "X1", JSON.stringify(sMis.reconciliation));
add("آمار از قیمت خام بازمحاسبه شد (۱.۹) نه از مقدار ذخیره‌شده", near(sMis.winRatePct, 100) && near(sMis.avgReturnPct, 1.9), `${sMis.avgReturnPct}`);

// داده ناقص — خروج null: شفاف علامت می‌خورد
const broken = { ...mk("B1", "LONG", 100, 102, T + 1 * 3_600_000, { stored: 1.9 }), exitPrice: null };
const sInc = computeStats([broken]);
add("معامله بدون exitPrice → incomplete و از WR حذف", sInc.incompleteCount === 1 && sInc.incompleteIds?.[0] === "B1" && sInc.winRatePct === null, JSON.stringify({ inc: sInc.incompleteCount, wr: sInc.winRatePct }));

// کارنامک خالی — هیچ عدد ساختگی نباید تولید شود
const sEmpty = computeStats([]);
const noFabrication = [sEmpty.winRatePct, sEmpty.profitFactor, sEmpty.maxDrawdownPct, sEmpty.expectancyPct ?? null]
  .every((v) => v === null || v === undefined);
add("کارنامک خالی → بدون عدد ساختگی (WR/PF/MDD/Expectancy همگی null/غایب)", noFabrication,
  `wr=${sEmpty.winRatePct} pf=${sEmpty.profitFactor} exp=${sEmpty.expectancyPct} mdd=${sEmpty.maxDrawdownPct}`);
add("[ثبت مشاهده] کلید expectancyPct در کارنامک خالی «غایب» است نه null (ناسازگاری جزئی قرارداد خروجی)",
  sEmpty.expectancyPct === undefined,
  `expectancyPct در مسیر خالی تعریف نشده (base فاقد این کلید) — مسیر غیرخالی آن را می‌سازد؛ رفتار ثبت شد`);

// منحنی بازده تجمعی — مرتب بر زمان خروج و هم‌ارز بازمحاسبه
const curve = buildEquityCurve(trades);
add("منحنی: ۴ نقطه با مقادیر [1.9, 3.8, 2.7, 1.6]", curve.length === 4 && near(curve[0].v, 1.9) && near(curve[1].v, 3.8) && near(curve[2].v, 2.7) && near(curve[3].v, 1.6), JSON.stringify(curve.map((p) => p.v)));
add("منحنی: زمان‌ها صعودی", curve.every((p, i) => i === 0 || p.t > curve[i - 1].t), JSON.stringify(curve.map((p) => p.t)));

// سود پولی — فقط معاملات sizeUsd دار — پاسخ معلوم: ۲×(2000×۱.۹/۱۰۰) − ۲×(2000×۱.۱/۱۰۰) = ۳۸+۳۸−۲۲−۲۲ = ۳۲
add("سود پولی = Σ(size×net/100) = ۳۲ دلار", near(s.monetaryPnlUsd, 32.0) && s.monetaryTrades === 4, `${s.monetaryPnlUsd} بر ${s.monetaryTrades} معامله (38+38−22−22)`);

const verdict = checks.filter((c) => c.verdict === "FAIL").length === 0 ? "PASS" : "FAIL";
const result = {
  test: "t5_stats",
  domain: "⑤ Win Rate / Profit Factor / Expectancy / Max Drawdown",
  securityLock: "READ ONLY | PAPER ONLY | NO LIVE ORDERS",
  verdict,
  knownAnswers: { wr: 50, pf: 1.7273, expectancy: 0.4, mdd: 2.2 },
  checks,
};
mkdirSync("/home/z/my-project/scripts/m73p/sandbox/out", { recursive: true });
writeFileSync(OUT, JSON.stringify(result, null, 2), "utf8");
console.log(JSON.stringify({ test: "t5_stats", verdict, failed: checks.filter((c) => c.verdict === "FAIL").length }, null, 2));
