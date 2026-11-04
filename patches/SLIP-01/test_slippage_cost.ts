// SLIP-01 — آزمون پچ «لغزش و هزینهٔ قابل تنظیم + ثبت هزینه در هر معامله». فقط‌خواندنی؛ فایل داده‌ای نمی‌نویسد.
// اجرا (از ریشهٔ پروژه): npx esbuild tests/test_slippage_cost.ts --bundle --platform=node --format=esm --outfile=/tmp/t.mjs && node /tmp/t.mjs data/paper-trades.json src/lib/paper/engine.ts
import { readFileSync } from "node:fs";
import { computeStats } from "../src/lib/paper/stats";
import { grossPct, netPct, roundTripCostPct, isBreakeven } from "../src/lib/paper/pnl";
import { PAPER_PARAMS } from "../src/lib/paper/types";

let fails = 0, total = 0;
const near = (a: number, b: number, e = 1e-6) => Math.abs(a - b) <= e;
function check(name: string, ok: boolean, detail = "") {
  total += 1; if (!ok) fails += 1;
  console.log(`${ok ? "PASS" : "FAIL"} — ${name}${detail ? "  [" + detail + "]" : ""}`);
}

const ledgerPath = process.argv[2];
const ledger = JSON.parse(readFileSync(ledgerPath, "utf8"));

// ۱) پیش‌فرض: رفتار قبلی دقیقاً حفظ شده (لغزش = ۰ ⇒ هزینه = ۰.۱٪)
check("پیش‌فرض لغزش = ۰", PAPER_PARAMS.slippagePctPerSide === 0, `${PAPER_PARAMS.slippagePctPerSide}`);
check("هزینه کل پیش‌فرض = ۰.۱", near(roundTripCostPct(), 0.1), `${roundTripCostPct()}`);
check("LONG 100→102 خالص = ۱.۹", near(netPct("LONG", 100, 102), 1.9));
check("SHORT 100→98 خالص = ۱.۹", near(netPct("SHORT", 100, 98), 1.9));
check("LONG 100→98 خالص = ۲.۱−", near(netPct("LONG", 100, 98), -2.1));

// ۲) رگرسیون روی دفتر واقعی: آمار تاریخچه نباید تکان بخورد
const s: any = computeStats(ledger.trades);
check("دفتر: ۷۴ معامله بسته", s.closedCount === 74 && ledger.trades.length === 74, `${s.closedCount}`);
check("دفتر: ۱۹ برد", s.wins === 19, `${s.wins}`);
check("دفتر: ۲۴ باخت", s.losses === 24, `${s.losses}`);
check("دفتر: ۳۱ سربه‌سر", s.breakevens === 31, `${s.breakevens}`);
check("دفتر: PF درصدی ≈ ۱.۰۴۹۴", near(s.profitFactor, 1.049387, 1e-4), `${s.profitFactor}`);
const v2 = (s.strategyBreakdown as any[]).find((r) => r.key === "mari-paper-v2");
check("دفتر: خالص v2 ≈ −۱۰.۲۲۶۴", !!v2 && near(v2.netPct, -10.22639, 1e-3), `${v2?.netPct}`);

// ۳) با لغزش ۰.۰۵٪ هر سمت: هزینه کل ۰.۲٪ و سربه‌سر هنوز سربه‌سر می‌ماند
(PAPER_PARAMS as any).slippagePctPerSide = 0.05;
check("با لغزش ۰.۰۵: هزینه کل = ۰.۲", near(roundTripCostPct(), 0.2), `${roundTripCostPct()}`);
check("با لغزش: LONG 100→102 خالص = ۱.۸", near(netPct("LONG", 100, 102), 1.8));
const beLong = 100 * (1 + roundTripCostPct() / 100);   // همان فرمول قیمت سربه‌سر در engine.ts
const beShort = 100 * (1 - roundTripCostPct() / 100);
check("قیمت BE خرید پس از هزینه کل = سربه‌سر", isBreakeven(netPct("LONG", 100, beLong)), `${netPct("LONG", 100, beLong)}`);
check("قیمت BE فروش پس از هزینه کل = سربه‌سر", isBreakeven(netPct("SHORT", 100, beShort)), `${netPct("SHORT", 100, beShort)}`);

// ۴) هزینهٔ ثبت‌شده در معامله بر بازمحاسبهٔ آمار حاکم است، نه پارامتر جاری
const base = ledger.trades.find((t: any) => t.sourceVersion === "mari-paper-v2" && t.exitReason === "TP");
const mk = (cost?: number) => {
  const t = { ...base, id: "X" + String(cost), status: "CLOSED" };
  if (cost !== undefined) t.costPctApplied = cost;
  return t;
};
const g = grossPct(base.side, base.entryPrice, base.exitPrice);
const sNew: any = computeStats([mk(0.3)]);
check("معامله با costPctApplied=0.3 ⇒ خالص = ناخالص−۰.۳", near(sNew.avgReturnPct, g - 0.3, 1e-6), `${sNew.avgReturnPct} vs ${g - 0.3}`);
const sOld: any = computeStats([mk(undefined)]);
check("معامله بدون فیلد ⇒ همان ۰.۱٪ قدیمی حتی وقتی لغزش جاری روشن است", near(sOld.avgReturnPct, g - 0.1, 1e-6), `${sOld.avgReturnPct} vs ${g - 0.1}`);
(PAPER_PARAMS as any).slippagePctPerSide = 0;

// ۵) بررسی ایستای engine.ts (چون server-only است، باندل نمی‌شود)
// مسیر engine.ts نسبت به پوشهٔ جاری (ریشهٔ پروژه) خوانده می‌شود؛ بعد از باندل، import.meta.url به جای دیگری اشاره می‌کند
const eng = readFileSync(process.argv[3] ?? "src/lib/paper/engine.ts", "utf8");
check("engine: هزینه در لحظهٔ بستن ثبت می‌شود", eng.includes("t.costPctApplied = roundTripCostPct()"));
check("engine: بازده بسته‌شده با هزینهٔ ثبت‌شده", eng.includes("netPctWithCost(t.side, t.entryPrice, price, t.costPctApplied)"));
check("engine: قیمت BE با هزینه کل (دو سمت)", (eng.match(/roundTripCostPct\(\) \/ 100/g) || []).length === 2);
check("engine: دیگر feePct/100 مستقیم ندارد", !/feePct\s*\/\s*100/.test(eng));

console.log(`\nنتیجه: ${total - fails}/${total} PASS`);
process.exit(fails ? 1 : 0);
