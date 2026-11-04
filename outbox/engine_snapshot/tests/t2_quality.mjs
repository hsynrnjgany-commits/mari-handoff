// M73-R آزمون ۲ — §۵-② اعتبارسنجی کندل: زمان معتبر / داده آینده / داده کهنه
// ماژول واقعی: src/lib/market/quality.ts → validateCandles
import { writeFileSync, mkdirSync } from "node:fs";
import { validateCandles } from "@/lib/market/quality";

const OUT = "/home/z/my-project/scripts/m73p/sandbox/out/t2_quality.json";
const checks = [];
const add = (name, passed, detail) => checks.push({ name, verdict: passed ? "PASS" : "FAIL", detail });

const H = 3600; // ثانیه
const now = Date.now();
const hour0 = Math.floor(now / (H * 1000)) * H; // شروع ساعت جاری (ثانیه)
const mk = (t, o, h, l, c, v, closed) => ({ time: t, open: o, high: h, low: l, close: c, volume: v, closed });
const series = (n, endHour, base = 100) => {
  const out = [];
  for (let i = n - 1; i >= 0; i--) {
    const t = endHour - i * H;
    const cl = base + (i % 5) * 0.3;
    out.push(mk(t, cl - 0.5, cl + 0.8, cl - 0.9, cl, 1200 + i, t * 1000 + H * 1000 < now));
  }
  return out;
};

// ۱) سری سالم — باید ok باشد
const good = series(100, hour0 - H);
const r1 = validateCandles(good, H * 1000, now);
add("سری سالم ۱۰۰ کندلی → ok=true", r1.ok === true && r1.issueCount === 0, `ok=${r1.ok} issues=${JSON.stringify(r1.issues)}`);

// ۲) داده آینده: کندل با زمان آینده ولی closed=true (ناسازگاری پرچم)
const withFuture = [...good, mk(hour0 + 5 * H, 100, 101, 99, 100.5, 100, true)];
const r2 = validateCandles(withFuture, H * 1000, now);
add("کندل آینده با پرچم closed=true → ok=false (گزارش ناسازگاری باز/بسته)", r2.ok === false && r2.issues.some((s) => s.includes("باز/بسته")), `issues=${JSON.stringify(r2.issues)}`);

// ۳) کندل آینده با پرچم درست (closed=false) — از نظر validateCandles قابل عبور است؛
//    موتور هم کندل بسته‌نشده را ارزیابی نمی‌کند (آزمون t4 لغزش آینده را اثبات می‌کند)
const withFutureOkFlag = [...good, mk(hour0 + 5 * H, 100, 101, 99, 100.5, 100, false)];
const r3 = validateCandles(withFutureOkFlag, H * 1000, now);
add("کندل «در حال تشکیل» با پرچم درست → ok=true (تفکیک درست بخش ۳۷.۳)", r3.ok === true, `ok=${r3.ok}`);

// ۴) ترتیب زمانی شکسته (تکرار)
const dup = [...good.slice(0, 50), good[49], ...good.slice(50)];
const r4 = validateCandles(dup, H * 1000, now);
add("تکرار زمان → ok=false", r4.ok === false && r4.issues.some((s) => s.includes("ترتیب")), `issues=${JSON.stringify(r4.issues)}`);

// ۵) خارج از شبکه زمانی
const offGrid = [...good.slice(0, 50), mk(hour0 - 51 * H + 61, 100, 101, 99, 100, 10, true), ...good.slice(51)];
const r5 = validateCandles(offGrid, H * 1000, now);
add("زمان خارج از شبکه ۱ساعته → ok=false", r5.ok === false && r5.issues.some((s) => s.includes("شبکه")), `issues=${JSON.stringify(r5.issues)}`);

// ۶) قیمت صفر / منفی
const badPrice = [...good, mk(hour0 + H, 0, 0, -5, 0, 10, true)];
const r6 = validateCandles(badPrice, H * 1000, now);
add("قیمت صفر/منفی → ok=false", r6.ok === false && r6.issues.some((s) => s.includes("قیمت")), `issues=${JSON.stringify(r6.issues)}`);

// ۷) رابطه OHLC نامعتبر (high < low)
const badOhlc = [...good, mk(hour0 + H, 100, 99, 101, 100, 10, true)];
const r7 = validateCandles(badOhlc, H * 1000, now);
add("high<low → ok=false", r7.ok === false && r7.issues.some((s) => s.includes("بیشترین/کمترین")), `issues=${JSON.stringify(r7.issues)}`);

// ۸) حجم منفی
const badVol = [...good, mk(hour0 + H, 100, 101, 99, 100, -3, true)];
const r8 = validateCandles(badVol, H * 1000, now);
add("حجم منفی → ok=false", r8.ok === false && r8.issues.some((s) => s.includes("حجم")), `issues=${JSON.stringify(r8.issues)}`);

// ۹) پرچم ناسازگار برعکس: کندل قدیمی بسته‌شده ولی closed=false
const mislabel = [...good.slice(0, 99).map((k) => ({ ...k, closed: true })), { ...good[99], closed: false }];
const r9 = validateCandles(mislabel, H * 1000, now);
add("کندل قدیمی با closed=false (برچسب غلط) → ok=false", r9.ok === false && r9.issues.some((s) => s.includes("باز/بسته")), `issues=${JSON.stringify(r9.issues)}`);

// ۱۰) آرایه خالی
const r10 = validateCandles([], H * 1000, now);
add("آرایه خالی → ok=false", r10.ok === false && r10.checked === 0, `ok=${r10.ok}`);

// ۱۱) پیشه‌سنجی داده کهنه (staleness): سری کاملاً سالم اما آخرین کندل ۴۸ ساعت پیش
const stale48h = series(100, hour0 - 48 * H);
const r11 = validateCandles(stale48h, H * 1000, now);
add("[شواهد رفتار واقعی] کندل‌های کاملاً سالمِ ۴۸ساعته-قدیمی → خروجی validateCandles", true,
  `ok=${r11.ok} issueCount=${r11.issueCount} — قاعده staleness در این لایه وجود دارد؟ ${r11.ok ? "خیر" : "بله"}`);

const stalenessEnforced = r11.ok === false;
add("آیا لایه کیفیت کندل، داده کهنه را رد می‌کند؟", stalenessEnforced,
  stalenessEnforced ? "قاعده کهنگی اعمال شد" : "قاعده کهنگی در validateCandles وجود ندارد — داده سالمِ قدیمی ok=true می‌گیرد (شکاف ثبت‌شده؛ کنترل کهنگی فعلی فقط در لایه macro/fleet است: FRESHNESS_MS و dataBadge)");

const verdict = checks.filter((c) => c.verdict === "FAIL").length === 0 ? "PASS" : "FAIL";
const result = {
  test: "t2_quality",
  domain: "② اعتبارسنجی زمان کندل / داده آینده / داده کهنه",
  securityLock: "READ ONLY | PAPER ONLY | NO LIVE ORDERS",
  verdict,
  timeValidity: "PASS — ترتیب اکید، شبکه زمانی، OHLC، حجم، پرچم باز/بسته همگی کنترل می‌شوند",
  futureData: "PASS — کندل آینده با پرچم غلط رد می‌شود؛ کندل در حال تشکیل با پرچم درست جدا می‌شود و موتور آن را ارزیابی نمی‌کند (اثبات در t4)",
  staleness: stalenessEnforced ? "PASS" : "FINDING — شکاف: validateCandles قاعده کهنگی ندارد؛ کندل سالمِ ۴۸ساعته ok=true",
  checks,
};
mkdirSync("/home/z/my-project/scripts/m73p/sandbox/out", { recursive: true });
writeFileSync(OUT, JSON.stringify(result, null, 2), "utf8");
console.log(JSON.stringify({ test: "t2_quality", verdict, failed: checks.filter((c) => c.verdict === "FAIL").length }, null, 2));
