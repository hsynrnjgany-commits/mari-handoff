// M73-R آزمون ۳ — §۵-③ P&L LONG/SHORT + کارمزد — ماژول واقعی pnl.ts
// فرمول مرجع: خرید (Exit−Entry)/Entry×۱۰۰ — فروش (Entry−Exit)/Entry×۱۰۰ — کارمزد فقط یک بار
import { writeFileSync, mkdirSync } from "node:fs";
import { grossPct, netPct, isBreakeven, BREAKEVEN_EPS } from "@/lib/paper/pnl";
import { PAPER_PARAMS } from "@/lib/paper/types";

const OUT = "/home/z/my-project/scripts/m73p/sandbox/out/t3_pnl.json";
const checks = [];
const add = (name, passed, detail) => checks.push({ name, verdict: passed ? "PASS" : "FAIL", detail });
const near = (a, b, eps = 1e-9) => Math.abs(a - b) <= eps;

const fee = PAPER_PARAMS.feePct;
add("کارمزد اعلام‌شده = ۰.۱٪", fee === 0.1, `feePct=${fee}`);

// LONG
add("LONG 100→102: ناخالص = +۲٪", near(grossPct("LONG", 100, 102), 2.0), `${grossPct("LONG", 100, 102)}`);
add("LONG 100→102: خالص = +۱.۹٪ (کارمزد یک‌بار)", near(netPct("LONG", 100, 102), 1.9), `${netPct("LONG", 100, 102)}`);
add("LONG 100→98: ناخالص = −۲٪", near(grossPct("LONG", 100, 98), -2.0), `${grossPct("LONG", 100, 98)}`);
add("LONG 100→98: خالص = −۲.۱٪", near(netPct("LONG", 100, 98), -2.1), `${netPct("LONG", 100, 98)}`);

// SHORT — مخرج باید «قیمت ورود» باشد نه خروج
add("SHORT 100→98: ناخالص = +۲٪", near(grossPct("SHORT", 100, 98), 2.0), `${grossPct("SHORT", 100, 98)}`);
add("SHORT 100→98: خالص = +۱.۹٪", near(netPct("SHORT", 100, 98), 1.9), `${netPct("SHORT", 100, 98)}`);
add("SHORT 100→102: ناخالص = −۲٪", near(grossPct("SHORT", 100, 102), -2.0), `${grossPct("SHORT", 100, 102)}`);
add("SHORT 100→102: خالص = −۲.۱٪", near(netPct("SHORT", 100, 102), -2.1), `${netPct("SHORT", 100, 102)}`);
// شاهد مخرج ورود-محور: فروش ۱۰۰→۵۰ باید +۵۰٪ باشد (با مخرج خروج می‌شد +۱۰۰٪)
add("SHORT 100→50: +۵۰٪ (اثبات مخرج ورود-محور)", near(grossPct("SHORT", 100, 50), 50.0), `${grossPct("SHORT", 100, 50)}`);
// دوبرابر شدن قیمت خرید = +۱۰۰٪
add("LONG 100→200: +۱۰۰٪ (مخرج ورود)", near(grossPct("LONG", 100, 200), 100.0), `${grossPct("LONG", 100, 200)}`);

// کارمزد فقط یک بار — سربه‌سر ناخالص = زیان به اندازه کارمزد
add("LONG 100→100: خالص = −۰.۱٪ (کارمزد دوباره کسر نشد؛ فقط یک‌بار)", near(netPct("LONG", 100, 100), -0.1), `${netPct("LONG", 100, 100)}`);
add("سربه‌سر ناخالص، برد محسوب نمی‌شود", !isBreakeven(netPct("LONG", 100, 100)), `isBreakeven=${isBreakeven(netPct("LONG", 100, 100))}`);

// سربه‌سر مهندسی‌شده — دلیل وجود BREAKEVEN_EPS
const beGross = grossPct("LONG", 100, 100.1);
const beNet = netPct("LONG", 100, 100.1);
add("LONG 100→100.1: خالص ≈ ۰ و در مرز EPS پوشش داده می‌شود", isBreakeven(beNet), `gross=${beGross} net=${beNet} EPS=${BREAKEVEN_EPS}`);

// ورودی نامعتبر — صادقانه NaN
add("entry=0 → NaN", Number.isNaN(grossPct("LONG", 0, 102)), `${grossPct("LONG", 0, 102)}`);
add("entry منفی → NaN", Number.isNaN(grossPct("SHORT", -100, 98)), `${grossPct("SHORT", -100, 98)}`);
add("exit=NaN → NaN", Number.isNaN(grossPct("LONG", 100, Number.NaN)), `${grossPct("LONG", 100, NaN)}`);

const verdict = checks.filter((c) => c.verdict === "FAIL").length === 0 ? "PASS" : "FAIL";
const result = {
  test: "t3_pnl",
  domain: "③ P&L LONG/SHORT و کارمزد",
  securityLock: "READ ONLY | PAPER ONLY | NO LIVE ORDERS",
  verdict,
  formulaBasis: "مبنای هر دو سمت: قیمت ورود (رسماً اثبات شد با SHORT 100→50 = +۵۰٪)",
  feeAppliedOnce: true,
  checks,
};
mkdirSync("/home/z/my-project/scripts/m73p/sandbox/out", { recursive: true });
writeFileSync(OUT, JSON.stringify(result, null, 2), "utf8");
console.log(JSON.stringify({ test: "t3_pnl", verdict, failed: checks.filter((c) => c.verdict === "FAIL").length }, null, 2));
