// M73-P آزمون پچ P2 — validateCandles: قاعدهٔ کهنگی (staleness) — شکاف F2 یافتهٔ M73-R
// پیمانهٔ پیش‌فرض: maxAgeMs = max(3×intervalMs, 10 دقیقه) — قابل بازنویسی با opts.maxAgeMs
// خروجی: فقط scripts/m73p/sandbox/out/t2p_patch.json — نوشتن بیرون sandbox ممنوع
import { writeFileSync, mkdirSync } from "node:fs";
import { validateCandles } from "@/lib/market/quality";

const OUT = "/home/z/my-project/scripts/m73p/sandbox/out/t2p_patch.json";
const checks = [];
const add = (name, passed, detail) => checks.push({ name, verdict: passed ? "PASS" : "FAIL", detail });

const H = 3600;
const now = Date.now();
const hour0 = Math.floor(now / (H * 1000)) * H;
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

// ۱) سری تازه (آخرین بسته‌شدن ≤ ۱ ساعت پیش) → ok=true — رگرسیون مثبت
const fresh = series(100, hour0 - H);
const r1 = validateCandles(fresh, H * 1000, now);
add("سری تازه → ok=true (رفتار قبلی حفظ شد)", r1.ok === true, `ok=${r1.ok} issues=${JSON.stringify(r1.issues)}`);

// ۲) دادهٔ کهنهٔ ۴۸ ساعتهٔ کاملاً سالم → ok=false (قلب پچ F2)
const stale48h = series(100, hour0 - 48 * H);
const r2 = validateCandles(stale48h, H * 1000, now);
add("سری سالمِ ۴۸ساعته → ok=false", r2.ok === false, `ok=${r2.ok} issues=${JSON.stringify(r2.issues)}`);
add("پیام کهنگی فارسی گزارش شد", r2.issues.some((s) => s.includes("کهنه")), `issues=${JSON.stringify(r2.issues)}`);

// ۳) مرز دقیق پیمانه (۳×interval): آخرین بسته‌شدن کمی قدیمی‌تر از ۳ ساعت → رد؛ کمی تازه‌تر → قبول
const maxAge3h = 3 * H * 1000;
const slightlyStale = series(50, hour0 - 4 * H); // آخرین بسته‌شدن ≈ ۳ ساعت + کمی پیش
const r3 = validateCandles(slightlyStale, H * 1000, now);
add("کهنگی بیش از ۳×interval → ok=false", r3.ok === false, `ok=${r3.ok}`);
const atEdge = series(50, hour0 - 2 * H); // آخرین بسته‌شدن ≈ ۲ ساعت پیش < ۳ ساعت
const r3b = validateCandles(atEdge, H * 1000, now);
add("کهنگی کمتر از ۳×interval → ok=true", r3b.ok === true, `ok=${r3b.ok} (پیمانه=${maxAge3h / 60000} دقیقه)`);

// ۴) کندل «در حال تشکیل» کهنه شمرده نمی‌شود — رگرسیون بحرانی موتور
const withForming = [...series(99, hour0 - H), mk(hour0, 100, 101, 99, 100.5, 100, false)];
const r4 = validateCandles(withForming, H * 1000, now);
add("کندل در حال تشکیل → ok=true (نشانهٔ کهنگی نمی‌گیرد)", r4.ok === true, `ok=${r4.ok} issues=${JSON.stringify(r4.issues)}`);

// ۵) پیمانهٔ سفارشی سخت‌گیرانه‌تر: maxAgeMs=۳۰ دقیقه روی سری با آخرین بسته‌شدن ≈ ۲ ساعت پیش
const r5 = validateCandles(atEdge, H * 1000, now, { maxAgeMs: 30 * 60 * 1000 });
add("opts.maxAgeMs=۳۰دقیقه → همان سری تازه، رد می‌شود", r5.ok === false, `ok=${r5.ok} issues=${JSON.stringify(r5.issues)}`);

// ۶) کف ۱۰ دقیقه برای تایم‌فریم‌های ریز (۱ دقیقه): ۵ دقیقه وقفه → قبول؛ ۱۵ دقیقه → رد
// کندل‌های ۱ دقیقه‌ای — زمان بر حسب «ثانیه» روی شبکهٔ ۶۰ ثانیه‌ای (همان قرارداد واقعی KlinePoint)
const min0s = Math.floor(now / 60_000) * 60; // شروع دقیقهٔ جاری (ثانیه)
const mSeries = (lastOpenSec) => {
  const out = [];
  for (let i = 119; i >= 0; i--) {
    const t = lastOpenSec - i * 60;
    const cl = 100 + (i % 5) * 0.1;
    out.push(mk(t, cl - 0.05, cl + 0.1, cl - 0.1, cl, 50 + i, t * 1000 + 60_000 < now));
  }
  return out;
};
const r6a = validateCandles(mSeries(min0s - 2 * 60), 60_000, now); // آخرین بسته‌شدن = شروع دقیقهٔ جاری → وقفه < ۱ دقیقه
add("۱دقیقه‌ای، وقفهٔ <۱دقیقه → ok=true (کف ۱۰ دقیقه)", r6a.ok === true, `ok=${r6a.ok} issues=${JSON.stringify(r6a.issues)}`);
const r6b = validateCandles(mSeries(min0s - 19 * 60), 60_000, now); // آخرین بسته‌شدن ≈ ۱۸-۱۹ دقیقه پیش > کف
add("۱دقیقه‌ای، وقفهٔ ~۱۸دقیقه → ok=false", r6b.ok === false, `ok=${r6b.ok} issues=${JSON.stringify(r6b.issues)}`);

// ۷) کهنگی + خرابی ساختاری هم‌زمان → هر دو شمرده می‌شوند
const bothBad = [...stale48h.slice(0, 50), stale48h[49], ...stale48h.slice(50)];
const r7 = validateCandles(bothBad, H * 1000, now);
add("ترتیب شکسته + کهنه → issueCount ≥ ۲", r7.ok === false && r7.issueCount >= 2, `issueCount=${r7.issueCount} issues=${JSON.stringify(r7.issues)}`);

// ۸) شکل خروجی تغییر نکرده
add("شکل خروجی: {ok,checked,issues,issueCount}", ["ok", "checked", "issues", "issueCount"].every((k) => k in r2) && Array.isArray(r2.issues), `keys=${Object.keys(r2).join(",")}`);

const verdict = checks.filter((c) => c.verdict === "FAIL").length === 0 ? "PASS" : "FAIL";
const result = {
  test: "t2p_patch",
  domain: "P2 — validateCandles: قاعدهٔ کهنگی (شکاف F2 بسته شد)",
  securityLock: "READ ONLY | PAPER ONLY | NO LIVE ORDERS",
  verdict,
  checks,
};
mkdirSync("/home/z/my-project/scripts/m73p/sandbox/out", { recursive: true });
writeFileSync(OUT, JSON.stringify(result, null, 2), "utf8");
console.log(JSON.stringify({ test: "t2p_patch", verdict, failed: checks.filter((c) => c.verdict === "FAIL").length }));
