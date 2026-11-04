// M73-R آزمون ۱ — §۵-① trimStore: نگهداشت آخرین ۵۰۰ معامله؟
// ورودی: سینتتیک، ترتیب زمانی قدیمی→جدید (همان قرارداد واقعی فایل data/paper-trades.json
// که رسماً اندازه‌گیری شد: trades[0].entryTime < trades[last].entryTime)
// خروجی: scripts/m73p/sandbox/out/t1_trim.json — هیچ نوشتن دیگری
import { writeFileSync, mkdirSync } from "node:fs";
import { trimStore } from "@/lib/paper/store";

const OUT = "/home/z/my-project/scripts/m73p/sandbox/out/t1_trim.json";
const checks = [];
const add = (name, passed, detail) => checks.push({ name, verdict: passed ? "PASS" : "FAIL", detail });

function mkTrade(i, status) {
  const t0 = 1_700_000_000_000 + i * 3_600_000; // قدیمی → جدید
  return {
    id: `SYN${String(i).padStart(4, "0")}-1h-${t0}`,
    symbol: "SYNUSDT", exchange: "toobit", interval: "1h",
    side: i % 2 === 0 ? "LONG" : "SHORT", status,
    entryPrice: 100, entryTime: t0, tpPrice: 102, slPrice: 99,
    score: 1, strength: 50, reason: "fixture", sourceVersion: "mari-paper-v2",
    lastPrice: 100, lastCheck: t0, mfePct: 0, maePct: 0,
    exitPrice: status === "CLOSED" ? 101 : null,
    exitTime: status === "CLOSED" ? t0 + 3_600_000 : null,
    exitReason: status === "CLOSED" ? "TP" : null,
    realizedPnlPct: status === "CLOSED" ? 0.9 : null,
    createdAt: t0, slBasis: "FIXED", atrPctAtEntry: null,
    plannedRiskPct: 1, sizeUsd: 1000, beActive: false, trailActive: false, trailExtremePct: 0,
  };
}

// سناریوی الف: ۵۱۰ معامله — ۵۰۷ بسته (قدیمی→جدید) + ۳ باز در انتها
const trades = [];
for (let i = 0; i < 507; i++) trades.push(mkTrade(i, "CLOSED"));
for (let i = 507; i < 510; i++) trades.push(mkTrade(i, "OPEN"));

const out = trimStore(trades);
add("طول خروجی = ۵۰۰", out.length === 500, `ورودی ۵۱۰ → خروجی ${out.length}`);

const openKept = out.filter((t) => t.status === "OPEN");
add("هر ۳ معامله OPEN حفظ شد", openKept.length === 3 && openKept.every((t) => t.entryTime >= 1_700_000_000_000 + 507 * 3_600_000),
  `OPEN در خروجی: ${openKept.length}؛ جدیدترین‌ها: ${openKept.map((t) => t.id.slice(3, 7)).join(",")}`);

const closedKept = out.filter((t) => t.status === "CLOSED");
const firstKept = closedKept[0], lastKept = closedKept[closedKept.length - 1];
const idxOf = (t) => Number(t.id.slice(3, 7));
add("بسته‌های حفظ‌شده = ۴۹۷", closedKept.length === 497, `${closedKept.length}`);

// انتظار وظیفه (M73-P: حساب اصلاح‌شده): از ۵۰۷ بسته با room=۴۹۷، تازه‌ترین‌ها (اندیس ۱۰..۵۰۶) می‌مانند
const keptAreNewest = idxOf(firstKept) === 10 && idxOf(lastKept) === 506;
add("بسته‌های «جدیدترین» حفظ شدند (اندیس ۱۰ تا ۵۰۶)", keptAreNewest,
  `حفظ‌شده از اندیس ${idxOf(firstKept)} تا ${idxOf(lastKept)}`);
const oldestDropped = [0, 1, 9].every((i) => !out.some((t) => t.id === trades[i].id));
add("«قدیمی‌ترین» بسته‌شده‌ها (۰ تا ۹) حذف شدند — قرارداد «حذف قدیمی‌ها» برقرار", oldestDropped,
  `حذف‌شده: ${[0,1,2,3,4,5,6,7,8,9].filter((i) => !out.some((t) => t.id === trades[i].id)).join(",")}`);

const newestClosedKept = [505, 506].every((i) => out.some((t) => t.id === trades[i].id));
add("جدیدترین بسته‌شده‌ها (۵۰۵ و ۵۰۶) حفظ شدند", newestClosedKept,
  `حفظ‌شده: ${[505, 506].filter((i) => out.some((t) => out.some((t2) => t2.id === trades[i].id))).join(",")}`);

// سناریوی ب: زیر آستانه — بدون تغییر
const small = trades.slice(0, 400);
const outSmall = trimStore(small);
add("زیر آستانه: همان آرایه برگشت (بدون برش)", outSmall === small || (outSmall.length === 400), `طول ${outSmall.length}`);

// سناریوی ج: سفارشی max=10 با ۱۲ معامله (۱۰ بسته + ۲ باز)
const t12 = [];
for (let i = 0; i < 10; i++) t12.push(mkTrade(100 + i, "CLOSED"));
t12.push(mkTrade(110, "OPEN"), mkTrade(111, "OPEN"));
const outC = trimStore(t12, 10);
const cKeptClosed = outC.filter((t) => t.status === "CLOSED").map(idxOf);
add("max سفارشی=۱۰: OPEN×۲ + بسته‌های تازه‌ترین تا سقف", outC.length === 10,
  `طول ${outC.length}؛ بسته‌های حفظ‌شده: اندیس ${Math.min(...cKeptClosed)}..${Math.max(...cKeptClosed)}`);

// سناریوی د: idempotency
const twice = trimStore(out);
add("دوبار اجرا = همان نتیجه (idempotent)", twice.length === out.length && twice.every((t, i) => t.id === out[i].id),
  `طول دوم ${twice.length}`);

// داوری نهایی حوزه ①
const expectationVerdict = keptAreNewest ? "PASS" : "FAIL";
const result = {
  test: "t1_trim",
  domain: "① trimStore نگهداشت آخرین ۵۰۰ معامله",
  securityLock: "READ ONLY | PAPER ONLY | NO LIVE ORDERS",
  verdict: expectationVerdict,
  behaviorNote: keptAreNewest
    ? "رفتار با انتظار «حفظ جدیدترین‌ها» همخوان است"
    : "ناسازگاری: کد slice(0, max-open) روی آرایه قدیمی→جدید، «قدیمی‌ترین بسته‌شده‌ها» را نگه می‌دارد و «جدیدترین بسته‌شده‌ها» را حذف می‌کند — برخلاف انتظار وظیفه (حفظ آخرین ۵۰۰) و برخلاف توضیح خود تابع (حذف قدیمی‌ها)",
  checks,
};
mkdirSync("/home/z/my-project/scripts/m73p/sandbox/out", { recursive: true });
writeFileSync(OUT, JSON.stringify(result, null, 2), "utf8");
console.log(JSON.stringify({ test: "t1_trim", verdict: expectationVerdict, failed: checks.filter((c) => c.verdict === "FAIL").length }, null, 2));
