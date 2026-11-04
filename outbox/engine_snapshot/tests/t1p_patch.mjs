// M73-P آزمون پچ P1 — trimStore: جهت نگهداشت + گارد room=0 + تلهٔ slice(-0)
// مأموریت Task-123 — پچ F1 بر اساس یافتهٔ M73-R (store.ts:70-76: slice(0,…) قدیمی‌ها را نگه می‌داشت)
// خروجی: فقط scripts/m73p/sandbox/out/t1p_patch.json — نوشتن بیرون sandbox ممنوع
import { writeFileSync, mkdirSync } from "node:fs";
import { trimStore } from "@/lib/paper/store";

const OUT = "/home/z/my-project/scripts/m73p/sandbox/out/t1p_patch.json";
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
const idxOf = (t) => Number(t.id.slice(3, 7));

// ── سناریوی ۱: ۵۱۰ معامله (۵۰۷ بسته قدیمی→جدید + ۳ باز) — قرارداد اصلی
const trades = [];
for (let i = 0; i < 507; i++) trades.push(mkTrade(i, "CLOSED"));
for (let i = 507; i < 510; i++) trades.push(mkTrade(i, "OPEN"));
const out = trimStore(trades);

add("طول خروجی = ۵۰۰", out.length === 500, `ورودی ۵۱۰ → خروجی ${out.length}`);
const openKept = out.filter((t) => t.status === "OPEN");
add("هر ۳ معامله OPEN حفظ شد", openKept.length === 3, `OPEN: ${openKept.length}`);
const closedKept = out.filter((t) => t.status === "CLOSED");
const keptIdx = closedKept.map(idxOf);
add("بسته‌های حفظ‌شده = ۴۹۷ (جدیدترین‌ها)", closedKept.length === 497 && keptIdx[0] === 10 && keptIdx[keptIdx.length - 1] === 506,
  `از اندیس ${keptIdx[0]} تا ${keptIdx[keptIdx.length - 1]}`);
const oldestDropped = [0, 1, 6].every((i) => !out.some((t) => t.id === trades[i].id));
add("قدیمی‌ترین بسته‌شده‌ها (۰ تا ۶) حذف شدند — قرارداد «حذف قدیمی‌ها»", oldestDropped,
  `حذف‌شده‌ها: ${[0, 1, 2, 3, 4, 5, 6].filter((i) => !out.some((t) => t.id === trades[i].id)).join(",")}`);

// ── سناریوی ۲: تلهٔ slice(-0) — room=0 (فقط بازها، بیش از سقف)
// ۶۰۰ باز + ۵ بسته، max=۵۰۰ ⇒ room = max(0, ۵۰۰−۶۰۰) = ۰ ⇒ باید «صفر» بسته بماند
// پیاده‌سازی نادرست closed.slice(-0) کل آرایهٔ بسته‌ها را برمی‌گرداند!
const trap = [];
for (let i = 0; i < 600; i++) trap.push(mkTrade(1000 + i, "OPEN"));
for (let i = 600; i < 605; i++) trap.push(mkTrade(1000 + i, "CLOSED"));
const outTrap = trimStore(trap, 500);
const trapOpen = outTrap.filter((t) => t.status === "OPEN").length;
const trapClosed = outTrap.filter((t) => t.status === "CLOSED").length;
add("گارد room=0: بسته‌ها صفر شدند (نه همه!)", trapClosed === 0,
  `open=${trapOpen} closed=${trapClosed} — slice(-0) خراب باشد closed=${trap.length - 600} می‌شد`);
add("گارد room=0: همهٔ بازها حفظ شدند", trapOpen === 600, `open=${trapOpen} (طول کل ${outTrap.length} — بازها هرگز حذف نمی‌شوند)`);

// ── سناریوی ۳: مرز دقیق — ۵۰۰ بسته + ۳ باز، max=۵۰۰ ⇒ room=۴۹۷
const bnd = [];
for (let i = 0; i < 500; i++) bnd.push(mkTrade(2000 + i, "CLOSED"));
for (let i = 500; i < 503; i++) bnd.push(mkTrade(2000 + i, "OPEN"));
const outBnd = trimStore(bnd, 500);
const bndClosed = outBnd.filter((t) => t.status === "CLOSED").map(idxOf);
add("مرز دقیق: ۴۹۷ بستهٔ تازه‌ترین + ۳ باز", outBnd.length === 500 && bndClosed.length === 497 && Math.min(...bndClosed) === 2000 + 3,
  `کل=${outBnd.length} بسته=${bndClosed.length} از اندیس ${Math.min(...bndClosed) - 2000} (قدیمی‌ترین حفظ‌شده)`);

// ── سناریوی ۴: زیر آستانه — بدون تغییر
const small = trades.slice(0, 400);
const outSmall = trimStore(small);
add("زیر آستانه: همان آرایه", outSmall === small || outSmall.length === 400, `طول ${outSmall.length}`);

// ── سناریوی ۵: idempotency خروجی پچ‌شده
const twice = trimStore(out);
add("دوبار اجرا = همان نتیجه", twice.length === out.length && twice.every((t, i) => t.id === out[i].id), `طول دوم ${twice.length}`);

// ── سناریوی ۶: ترتیب حفظ‌شده‌ها بدون جابه‌جایی (بازها اول، بسته‌ها به ترتیب زمانی)
// چیدمان «بازها-اول، سپس بسته‌ها» همان قرارداد نسخهٔ قبل از پچ است؛ ترتیب درون هر گروه باید حفظ شود
const openIdx = out.filter((t) => t.status === "OPEN").map(idxOf);
const closedIdx = out.filter((t) => t.status === "CLOSED").map(idxOf);
const withinGroupOk = openIdx.every((v, i) => i === 0 || openIdx[i - 1] <= v) && closedIdx.every((v, i) => i === 0 || closedIdx[i - 1] <= v);
add("ترتیب درون هر گروه (باز/بسته) حفظ شده", withinGroupOk, "هر گروه قدیمی→جدید است؛ چیدمان کلی بازها-اول بدون تغییر");

const verdict = checks.filter((c) => c.verdict === "FAIL").length === 0 ? "PASS" : "FAIL";
const result = {
  test: "t1p_patch",
  domain: "P1 — trimStore: جهت جدید→قدیمی + گارد room=0 + تلهٔ slice(-0)",
  securityLock: "READ ONLY | PAPER ONLY | NO LIVE ORDERS",
  verdict,
  checks,
};
mkdirSync("/home/z/my-project/scripts/m73p/sandbox/out", { recursive: true });
writeFileSync(OUT, JSON.stringify(result, null, 2), "utf8");
console.log(JSON.stringify({ test: "t1p_patch", verdict, failed: checks.filter((c) => c.verdict === "FAIL").length }));
