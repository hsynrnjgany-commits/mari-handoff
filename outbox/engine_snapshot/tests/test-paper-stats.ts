// MARI — آزمون آفلاین موتور ارزیابی ممیزی‌شده (Task 41) — اجرا: bun scripts/test-paper-stats.ts
// فقط-خواندنی: هیچ دفتر یا فایل عملیاتی‌ای را نمی‌سازد/تغییر نمی‌دهد؛ بدون شبکه.
import fs from "node:fs";
import { computeStats, buildEquityCurve } from "../src/lib/paper/stats";
import { grossPct, netPct, isBreakeven, BREAKEVEN_EPS } from "../src/lib/paper/pnl";
import type { PaperTrade } from "../src/lib/paper/types";

let pass = 0;
let fail = 0;
const failures: string[] = [];
function check(name: string, cond: boolean, detail = ""): void {
  if (cond) {
    pass += 1;
    console.log(`  ✓ ${name}`);
  } else {
    fail += 1;
    failures.push(name + (detail ? ` — ${detail}` : ""));
    console.error(`  ✗ ${name}${detail ? " — " + detail : ""}`);
  }
}
function near(a: number, b: number, eps = 1e-9): boolean {
  return Math.abs(a - b) <= eps;
}

console.log("— محور ۱: فرمول مرجع grossPct (مبنای قیمت ورود) —");
check("LONG (100→102) = +2٪", near(grossPct("LONG", 100, 102), 2.0));
check("SHORT (100→98) = +2٪", near(grossPct("SHORT", 100, 98), 2.0));
check("SHORT (0.3313→0.3306) = +0.211289٪", near(grossPct("SHORT", 0.3313, 0.3306), (0.3313 - 0.3306) / 0.3313 * 100, 1e-9));
check("LONG (741.14→741.83) = +0.093103٪", near(grossPct("LONG", 741.14, 741.83), (741.83 - 741.14) / 741.14 * 100, 1e-9));
check("ورودی نامعتبر → NaN", Number.isNaN(grossPct("LONG", 0, 100)));

console.log("— محور ۲: کارمزد فقط یک بار —");
check("netPct LONG (100→102) = 1.9", near(netPct("LONG", 100, 102), 1.9));
check("netPct SHORT (1.739→1.75639) = -1.10 (باگ مخرج-خروج رفع شد)", near(netPct("SHORT", 1.739, 1.75639), -1.1, 1e-9), `دریافتی: ${netPct("SHORT", 1.739, 1.75639)}`);
check("پرونده BNBUSDT: netPct = -0.0069001808٪ (Δ=۰ با دفتر)", near(netPct("LONG", 741.14, 741.83), -0.006900180802540068, 1e-9), `دریافتی ${netPct("LONG", 741.14, 741.83)}`);
check("پرونده TRXUSDT: netPct SHORT = +0.111289٪ (مبنای ورود)", near(netPct("SHORT", 0.3313, 0.3306), ((0.3313 - 0.3306) / 0.3313) * 100 - 0.1, 1e-9));
check("پرونده TRXUSDT: دیگر مقدار باگ‌دار 0.111736 نیست", Math.abs(netPct("SHORT", 0.3313, 0.3306) - 0.11173623714457906) > 1e-4);

console.log("— محور ۳: مرز سربه‌سر —");
check("۰ سربه‌سر است", isBreakeven(0));
check("خطای شناور 7e-15 سربه‌سر است", isBreakeven(-7e-15) && isBreakeven(7e-15));
check("0.001 سربه‌سر نیست", !isBreakeven(0.001));
check("-0.0069 سربه‌سر نیست (زیان واقعی)", !isBreakeven(-0.0069));
check("مرز EPS = 1e-9", BREAKEVEN_EPS === 1e-9);

// ---------- فیکسچر ----------
let seq = 0;
function mk(over: Partial<PaperTrade>): PaperTrade {
  seq += 1;
  const entryTime = 1_700_000_000_000 + seq * 3_600_000;
  return {
    id: `SYM-1h-${entryTime}`,
    symbol: "SYMUSDT",
    exchange: "toobit",
    interval: "1h",
    side: "LONG",
    status: "CLOSED",
    entryPrice: 100,
    entryTime,
    tpPrice: 102,
    slPrice: 99,
    score: 2,
    strength: 40,
    reason: "تست",
    sourceVersion: "mari-paper-v1",
    lastPrice: 100,
    lastCheck: entryTime,
    mfePct: 0,
    maePct: 0,
    exitPrice: 102,
    exitTime: entryTime + 3_600_000,
    exitReason: "TP",
    realizedPnlPct: 1.9,
    createdAt: entryTime,
    ...over,
  };
}

console.log("— محور ۴: computeStats روی فیکسچر کنترل‌شده —");
// ۴ معامله: TP(+1.9) ، SL(−1.1) ، سربه‌سر(0) ، SHORT TP(+1.9)
const t1 = mk({ symbol: "AAAUSDT", exitPrice: 102, realizedPnlPct: 1.9, exitTime: 1_700_000_100_000 }); // +1.9
const t2 = mk({ symbol: "BBBUSDT", exitPrice: 99, exitReason: "SL", slPrice: 99, realizedPnlPct: -1.1, exitTime: 1_700_000_200_000, sizeUsd: 1000 }); // −1.1
const t3 = mk({ symbol: "CCCUSDT", exitPrice: 100.1, exitReason: "SL", slPrice: 100.1, realizedPnlPct: -7e-15, exitTime: 1_700_000_300_000 }); // 0
const t4 = mk({ symbol: "DDDUSDT", side: "SHORT", entryPrice: 100, exitPrice: 98, tpPrice: 98, realizedPnlPct: 1.9, exitTime: 1_700_000_400_000 }); // +1.9
const s = computeStats([t1, t2, t3, t4]);
check("بسته‌شده = ۴", s.closedCount === 4, `دریافتی ${s.closedCount}`);
check("برد = ۲", s.wins === 2, `دریافتی ${s.wins}`);
check("باخت = ۱ (سربه‌سر باخت شمرده نمی‌شود)", s.losses === 1, `دریافتی ${s.losses}`);
check("سربه‌سر = ۱", s.breakevens === 1, `دریافتی ${s.breakevens}`);
check("نرخ برد = ۵۰٪", near(s.winRatePct ?? -1, 50));
check("PF = (1.9+1.9)/1.1 = 1.727272", near(s.profitFactor ?? -1, 1.9 + 1.9 === 0 ? 0 : 3.8 / 1.1, 1e-9), `دریافتی ${s.profitFactor}`);
check("امید ریاضی = 0.675", near(s.expectancyPct ?? -1, (1.9 - 1.1 + 0 + 1.9) / 4), `دریافتی ${s.expectancyPct}`);
check("میانگین برد = 1.9", near(s.avgWinPct ?? -1, 1.9));
check("میانگین باخت = -1.1", near(s.avgLossPct ?? -1, -1.1));
check("MaxDD = 1.1 (اوج 1.9، کف 0.8)", near(s.maxDrawdownPct ?? -1, 1.1), `دریافتی ${s.maxDrawdownPct}`);
check("سمت خرید = +0.8pp", near(s.longNetPct ?? -1, 1.9 - 1.1 + 0));
check("سمت فروش = +1.9pp", near(s.shortNetPct ?? -1, 1.9));
check("سربار مالی = -11 دلار (فقط معامله دارای sizeUsd)", near(s.monetaryPnlUsd ?? -1, 1000 * -1.1 / 100), `دریافتی ${s.monetaryPnlUsd}`);
check("پوشش مالی = ۱ معامله", s.monetaryTrades === 1);
check("تفکیک علت خروج: TP=۲ با +3.8", (() => {
  const row = (s.exitReasonBreakdown ?? []).find((r) => r.key === "TP");
  return !!row && row.count === 2 && near(row.netPct, 3.8);
})());
check("تفکیک استراتژی شامل mari-paper-v1", (s.strategyBreakdown ?? []).some((r) => r.key === "mari-paper-v1"));
check("تفکیک نماد ۴ سطر", (s.symbolBreakdown ?? []).length === 4);
check("کارمزد اعمال‌شده = 0.1", near(s.feePctApplied ?? -1, 0.1));

console.log("— محور ۵: تطبیق (reconciliation) بدون بازنویسی —");
const corrupted = mk({ symbol: "BADUSDT", exitPrice: 102, realizedPnlPct: 5.0 }); // ذخیره خراب: +5 به‌جای +1.9
const sBad = computeStats([corrupted]);
check("اختلاف خراب پرچم خورد", sBad.reconciliation?.mismatchCount === 1, JSON.stringify(sBad.reconciliation));
check("بازمحاسبه = 1.9 در پرچم", near(sBad.reconciliation?.mismatches[0]?.recomputedPct ?? -1, 1.9));
check("ذخیره اصلی 5.0 دست‌نخورده در پرچم", near(sBad.reconciliation?.mismatches[0]?.storedPct ?? -1, 5.0));
check("آمار از بازمحاسبه استفاده کرد نه ذخیره خراب", near(sBad.avgReturnPct ?? -1, 1.9), `دریافتی ${sBad.avgReturnPct}`);
check("corrupted.id در فایل دفتر تغییر نکرد", corrupted.realizedPnlPct === 5.0); // کاملاً در حافظه — بدون نوشتن

console.log("— محور ۶: داده ناقص پنهان نمی‌شود —");
const broken = mk({ symbol: "XXXUSDT", exitPrice: null, exitReason: null, exitTime: null, realizedPnlPct: null, status: "CLOSED" });
const sInc = computeStats([t1, broken]);
check("ناقص شمرده شد = ۱", sInc.incompleteCount === 1, `دریافتی ${sInc.incompleteCount}`);
check("شناسه ناقص گزارش شد", (sInc.incompleteIds ?? []).includes(broken.id));
check("ناقص از آمار کنار گذاشته شد (نه حذف از دفتر)", sInc.closedCount === 2 && sInc.wins === 1);

console.log("— محور ۷: حالت‌های مرزی PF —");
const onlyWins = computeStats([t1, t4]);
check("بدون باخت → PF بی‌نهایت", onlyWins.profitFactor === Number.POSITIVE_INFINITY, `دریافتی ${onlyWins.profitFactor}`);
const empty = computeStats([]);
check("دفتر خالی → همه نامشخص", empty.wins === null && empty.winRatePct === null && empty.profitFactor === null);

console.log("— محور ۸: منحنی بازده از بازمحاسبه —");
const curve = buildEquityCurve([corrupted, t2]);
check("نقطه اول منحنی = -1.1 (t2)", near(curve[0]?.v ?? -1, -1.1), `دریافتی ${curve[0]?.v}`);
check("نقطه دوم = 0.8 (بازمحاسبه 1.9 برای خراب، نه 5)", near(curve[1]?.v ?? -1, 0.8), `دریافتی ${curve[1]?.v}`);

console.log("— محور ۹: اثبات ساختاری اصلاحات engine.ts —");
const eng = fs.readFileSync(new URL("../src/lib/paper/engine.ts", import.meta.url), "utf8");
check("sidePnl از grossPct استفاده می‌کند (مبنای ورود)", eng.includes("return grossPct(side, entry, price);"));
check("فرمول قدیمی مخرج-خروج حذف شده", !eng.includes("pctChange(price, entry)"));
check("closeTrade از netPct استفاده می‌کند", eng.includes("t.realizedPnlPct = netPct(t.side, t.entryPrice, price);"));
check("کسر دوباره کارمزد حذف شده", !eng.includes("raw - feePct"));
check("MFE فروش با sidePnl فروش (جهت درست)", eng.includes('sidePnl("SHORT", t.entryPrice, k.low)'));
check("فیوز فقط ضرر واقعی را می‌شمارد", eng.includes("(t.realizedPnlPct as number) < -BREAKEVEN_EPS"));
check("ضدنش و ضدثبت‌دوباره پابرجاست", eng.includes("if (!k.closed)") && eng.includes("x.id === t.id"));

console.log("— محور ۱۰: گزارش روزانه تلگرام سربه‌سر را «ضرر» اعلام نمی‌کند —");
const notifySrc = fs.readFileSync(new URL("../src/lib/telegram/notify.ts", import.meta.url), "utf8");
check("verdict سربه‌سر با isBreakeven", notifySrc.includes("isBreakeven(pnl) ? \"سربه‌سر\""));
check("گزارش روزانه دوره و منطقه زمانی را اعلام می‌کند", notifySrc.includes("دوره محاسبه") && notifySrc.includes("به وقت تهران"));
check("PF ناموجود → «داده کافی نیست»", notifySrc.includes("\"داده کافی نیست\""));

console.log(`\nنتیجه: ${pass} پاس، ${fail} خطا`);
if (fail > 0) {
  console.error("شکست‌ها:", failures);
  process.exit(1);
}
