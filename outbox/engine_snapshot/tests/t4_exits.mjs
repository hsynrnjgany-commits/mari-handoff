// M73-R آزمون ۴ — §۵-④ خروج‌ها: SL / TP / بدبینانه SL-first / سربه‌سر / تریلینگ / TIME / ضد نشت آینده
// موتور «واقعی» src/lib/paper/engine.ts با:
//   - provider استاب (Fixture محلی، صفر فراخوانی شبکه)
//   - store استاب (trimStore واقعی؛ readStore از فیکسچر sandbox؛ writeStore فقط داخل sandbox)
// ۹ سناریوی OPEN با پاسخ‌های معلوم روی شبکه ساعتی.
import { writeFileSync, mkdirSync, readFileSync } from "node:fs";
import { createHash } from "node:crypto";

const OUTDIR = "/home/z/my-project/scripts/m73p/sandbox/out";
const OUT = OUTDIR + "/t4_exits.json";
const H_MS = 3_600_000;
const now = Date.now();
const hour0 = Math.floor(now / H_MS) * H_MS; // شروع ساعت جاری (ms)

const checks = [];
const add = (name, passed, detail) => checks.push({ name, verdict: passed ? "PASS" : "FAIL", detail });
const near = (a, b, eps = 1e-6) => Math.abs(a - b) <= eps;
const sha = (p) => createHash("sha256").update(readFileSync(p)).digest("hex");

// ---- ساعت‌های سناریو ----
// M73-P: لنگرها به‌گونه‌ای بازتنظیم شدند که آخرین بسته‌شدن کندل هر سناریو < ۳ ساعت (پیمانهٔ کهنگی P2) باشد
const E = hour0 - 4 * H_MS;       // ورود سناریوهای ۱..۷ (۴ ساعت پیش — کندل محرک: ساعت -۳..-۲)
const E30 = hour0 - 30 * H_MS;    // ورود TIME-exit (۳۰ ساعت پیش — کندل‌ها تا -۱ ساعت)
const E5 = hour0 - 3 * H_MS;      // ورود NOLEAK (۳ ساعت پیش — کندل پس از ورود: -۲..-۱)

const C = (t, o, h, l, c, v, closed) => ({ time: t, open: o, high: h, low: l, close: c, volume: v, closed });
const closedFlag = (tSec) => tSec * 1000 + H_MS < now; // همان فرمول validateCandles

// ---- کندل‌های هر سناریو (همه روی شبکه ساعتی، فاصله ایمن از مرز now) ----
const klines = {};
klines[`TPHITUSDT:1h`] = [C(E / 1000 + 3600, 100.3, 103, 100.2, 101.5, 900, closedFlag(E / 1000 + 3600))];
klines[`SLHITUSDT:1h`] = [C(E / 1000 + 3600, 99.9, 100.2, 98.5, 99.2, 900, closedFlag(E / 1000 + 3600))];
klines[`BOTHCANDLEUSDT:1h`] = [C(E / 1000 + 3600, 100, 103, 98, 100.1, 900, closedFlag(E / 1000 + 3600))];
klines[`SHORTTPUSDT:1h`] = [C(E / 1000 + 3600, 99.3, 99.5, 97, 97.5, 900, closedFlag(E / 1000 + 3600))];
klines[`SHORTSLUSDT:1h`] = [C(E / 1000 + 3600, 100.2, 101.5, 99.8, 101.2, 900, closedFlag(E / 1000 + 3600))];
klines[`TRAILLONGUSDT:1h`] = [
  C(E / 1000 + 3600, 100.2, 102.5, 100.1, 102, 900, closedFlag(E / 1000 + 3600)),
  C(E / 1000 + 7200, 101.5, 101.8, 100.4, 100.6, 900, closedFlag(E / 1000 + 7200)),
];
klines[`SHORTTRAILUSDT:1h`] = [
  C(E / 1000 + 3600, 98, 98.5, 97.5, 97.8, 900, closedFlag(E / 1000 + 3600)),
  C(E / 1000 + 7200, 98.5, 98.9, 98.3, 98.5, 900, closedFlag(E / 1000 + 7200)),
];
klines[`TIMEEXITUSDT:1h`] = [
  C(E30 / 1000 + 27 * 3600, 100.2, 100.8, 99.9, 100.4, 800, closedFlag(E30 / 1000 + 27 * 3600)),
  C(E30 / 1000 + 28 * 3600, 100.4, 100.7, 100, 100.6, 800, closedFlag(E30 / 1000 + 28 * 3600)),
  C(E30 / 1000 + 29 * 3600, 100.6, 100.8, 100.1, 100.5, 800, closedFlag(E30 / 1000 + 29 * 3600)),
];
klines[`NOLEAKUSDT:1h`] = [
  C(E5 / 1000 - 7200, 104, 108, 103, 105, 700, closedFlag(E5 / 1000 - 7200)),  // پیش از تصمیم — باید نادیده گرفته شود
  C(E5 / 1000 - 3600, 105, 110, 99, 105, 700, closedFlag(E5 / 1000 - 3600)),   // closeTime == entryTime — باید نادیده گرفته شود
  C(E5 / 1000 + 3600, 100.1, 101, 99.5, 100.2, 700, closedFlag(E5 / 1000 + 3600)), // نخستین کندل پس از ورود
  C(hour0 / 1000, 100.2, 100.4, 99.9, 100.3, 500, false),                       // در حال تشکیل — فقط lastPrice
];

function mkOpen(symbol, side, slPrice, tpPrice, entryTime, slBasis = "FIXED") {
  return {
    id: `${symbol}-1h-${entryTime}`, symbol, exchange: "toobit", interval: "1h", side,
    status: "OPEN", entryPrice: 100, entryTime, tpPrice, slPrice,
    score: 2, strength: 70, reason: "fixture — سناریوی آزمون", sourceVersion: "mari-paper-v2",
    lastPrice: 100, lastCheck: now, mfePct: 0, maePct: 0,
    exitPrice: null, exitTime: null, exitReason: null, realizedPnlPct: null, createdAt: now,
    slBasis, atrPctAtEntry: slBasis === "ATR" ? 1.0 : null,
    plannedRiskPct: 1.0, sizeUsd: 1000, beActive: false, trailActive: false, trailExtremePct: 0,
  };
}

// ---- فیکسچر فروشگاه: ۹ معامله OPEN ----
const storeFixture = {
  version: 1, updatedAt: now, paused: true,
  trades: [
    mkOpen("TPHITUSDT", "LONG", 99, 102, E),
    mkOpen("SLHITUSDT", "LONG", 99, 102, E),
    mkOpen("BOTHCANDLEUSDT", "LONG", 99, 102, E),
    mkOpen("SHORTTPUSDT", "SHORT", 101, 98, E),
    mkOpen("SHORTSLUSDT", "SHORT", 101, 98, E),
    mkOpen("TRAILLONGUSDT", "LONG", 99, 105, E, "ATR"),
    mkOpen("SHORTTRAILUSDT", "SHORT", 101, 95, E, "ATR"),
    mkOpen("TIMEEXITUSDT", "LONG", 99, 102, E30),
    mkOpen("NOLEAKUSDT", "LONG", 99, 102, E5),
  ],
};
const klinesFixture = { source: "toobit", asOf: now, klines };

// ---- نوشتن فیکسچرها فقط داخل sandbox ----
mkdirSync(OUTDIR, { recursive: true });
const FIXTURE = OUTDIR + "/t4_klines.json";
const STORE_FIX = OUTDIR + "/t4_store_fixture.json";
const STORE_AFTER = OUTDIR + "/t4_store_after.json";
writeFileSync(FIXTURE, JSON.stringify(klinesFixture, null, 2), "utf8");
writeFileSync(STORE_FIX, JSON.stringify(storeFixture, null, 2), "utf8");

// ---- محیط استاب‌ها پیش از import موتور ----
process.env.M73P_FIXTURE = FIXTURE;
process.env.M73P_STORE_FIXTURE = STORE_FIX;
process.env.M73P_STORE_OUT = STORE_AFTER;

// ---- شمارنده شبکه: هیچ fetchی نباید رخ دهد ----
let fetchCalls = 0;
const realFetch = globalThis.fetch;
globalThis.fetch = (...args) => { fetchCalls += 1; return realFetch(...args); };

// ---- گارد درون‌آزمونی: فایل واقعی فروشگاه نباید تغییر کند ----
const REAL_STORE = "/home/z/my-project/data/paper-trades.json";
const shaBefore = sha(REAL_STORE);

// ---- import موتور واقعی (با هوک‌های sandbox) ----
const { runPaperCycle } = await import("@/lib/paper/engine");
const res = await runPaperCycle();

const shaAfter = sha(REAL_STORE);
add("فایل واقعی data/paper-trades.json دست‌نخورده ماند", shaBefore === shaAfter, `sha256 قبل=بعد: ${shaBefore.slice(0, 16)}…`);
add("صفر فراخوانی شبکه (fetch)", fetchCalls === 0, `fetchCalls=${fetchCalls}`);
add("چرخه در حالت paused (بدون جست‌وجوی سیگنال جدید)", res.paused === true && res.scanSymbolCount === 0, `paused=${res.paused} scan=${res.scanSymbolCount}`);
add("کیفیت کندل: ۹ نماد بررسی، ۹ سالم، صفر رد‌شده", res.quality.checkedSymbols === 9 && res.quality.okSymbols === 9 && res.quality.skippedSymbols === 0, `checked=${res.quality.checkedSymbols} ok=${res.quality.okSymbols} skip=${res.quality.skippedSymbols}`);

const after = JSON.parse(readFileSync(STORE_AFTER, "utf8"));
const bySym = Object.fromEntries(after.trades.map((t) => [t.symbol, t]));

// ---- سناریو ۱: TP خرید ----
{
  const t = bySym["TPHITUSDT"];
  add("TP خرید: خروج در ۱۰۲ با علت TP", t.exitReason === "TP" && near(t.exitPrice, 102), `exit=${t.exitPrice} reason=${t.exitReason}`);
  add("TP خرید: خالص = +۱.۹٪", near(t.realizedPnlPct, 1.9, 1e-9), `${t.realizedPnlPct}`);
  add("TP خرید: MFE=۳.۰ MAE=۰", near(t.mfePct, 3.0) && near(t.maePct, 0), `${t.mfePct}/${t.maePct}`);
  add("TP خرید: زمان خروج = بسته‌شدن کندل محرک", t.exitTime === (E / 1000 + 3600) * 1000 + H_MS, `${t.exitTime}`);
}
// ---- سناریو ۲: SL خرید ----
{
  const t = bySym["SLHITUSDT"];
  add("SL خرید: خروج در ۹۹ با علت SL (قیمت سطح SL نه کندل)", t.exitReason === "SL" && near(t.exitPrice, 99), `exit=${t.exitPrice} reason=${t.exitReason}`);
  add("SL خرید: خالص = −۱.۱٪", near(t.realizedPnlPct, -1.1, 1e-9), `${t.realizedPnlPct}`);
  add("SL خرید: MFE=۰.۲ MAE=−۱.۵", near(t.mfePct, 0.2) && near(t.maePct, -1.5), `${t.mfePct}/${t.maePct}`);
}
// ---- سناریو ۳: هر دو در یک کندل → بدبینانه SL-first ----
{
  const t = bySym["BOTHCANDLEUSDT"];
  add("هر دو سطح در یک کندل → SL اولویت (اصل محافظه‌کاری ۴۰.۴)", t.exitReason === "SL" && near(t.exitPrice, 99), `exit=${t.exitPrice} reason=${t.exitReason}`);
  add("بدبینانه: خالص = −۱.۱٪ (نه +۱.۹٪)", near(t.realizedPnlPct, -1.1, 1e-9), `${t.realizedPnlPct}`);
  add("بدبینانه: شواهد کندل کامل ثبت شد MFE=۳.۰", near(t.mfePct, 3.0), `${t.mfePct}`);
}
// ---- سناریو ۴: TP فروش ----
{
  const t = bySym["SHORTTPUSDT"];
  add("TP فروش: خروج در ۹۸ با علت TP", t.exitReason === "TP" && near(t.exitPrice, 98), `exit=${t.exitPrice} reason=${t.exitReason}`);
  add("TP فروش: خالص = +۱.۹٪", near(t.realizedPnlPct, 1.9, 1e-9), `${t.realizedPnlPct}`);
}
// ---- سناریو ۵: SL فروش ----
{
  const t = bySym["SHORTSLUSDT"];
  add("SL فروش: خروج در ۱۰۱ با علت SL", t.exitReason === "SL" && near(t.exitPrice, 101), `exit=${t.exitPrice} reason=${t.exitReason}`);
  add("SL فروش: خالص = −۱.۱٪", near(t.realizedPnlPct, -1.1, 1e-9), `${t.realizedPnlPct}`);
  add("SL فروش: جهت MFE/MAE درست (MFE=۰.۲ MAE=−۱.۵)", near(t.mfePct, 0.2) && near(t.maePct, -1.5), `${t.mfePct}/${t.maePct}`);
}
// ---- سناریو ۶: تریلینگ خرید + سربه‌سر ----
{
  const t = bySym["TRAILLONGUSDT"];
  const expectedTrailSl = 102.5 * (1 - 0.012); // ۱۰۲.۵ × (۱−۱.۲٪)
  add("تریلینگ خرید: ارتقای سربه‌سر ثبت شد (BE_PROMOTED)", (t.decisions ?? []).some((d) => d.kind === "BE_PROMOTED"), `${(t.decisions ?? []).map((d) => d.kind).join(",")}`);
  add("تریلینگ خرید: ارتقای تریل ثبت شد (TRAIL_PROMOTED)", (t.decisions ?? []).some((d) => d.kind === "TRAIL_PROMOTED"), `${(t.decisions ?? []).map((d) => d.kind).join(",")}`);
  add("تریلینگ خرید: خروج در حد متحرک ۱۰۲.۵×(۱−۱.۲٪)", t.exitReason === "SL" && near(t.exitPrice, expectedTrailSl, 1e-9), `exit=${t.exitPrice} expected=${expectedTrailSl}`);
  add("تریلینگ خرید: خالص ≈ +۱.۱۷٪", near(t.realizedPnlPct, 1.17, 1e-6), `${t.realizedPnlPct}`);
  add("تریلینگ خرید: ترتیب تصمیم‌ها BE→TRAIL (معامله seedشده بدون OPEN دارد)", JSON.stringify((t.decisions ?? []).map((d) => d.kind)) === JSON.stringify(["BE_PROMOTED", "TRAIL_PROMOTED"]), `${(t.decisions ?? []).map((d) => d.kind).join("→")}`);
}
// ---- سناریو ۷: تریلینگ فروش (آینه — ریشه SHORT-15) ----
{
  const t = bySym["SHORTTRAILUSDT"];
  const expectedTrailSl = 97.5 * (1 + 0.012); // ۹۷.۵ × (۱+۱.۲٪)
  add("تریلینگ فروش: ارتقای سربه‌سر ثبت شد (رفع ناپیدایی SHORT-15)", (t.decisions ?? []).some((d) => d.kind === "BE_PROMOTED"), `${(t.decisions ?? []).map((d) => d.kind).join(",")}`);
  add("تریلینگ فروش: ارتقای تری ثبت شد", (t.decisions ?? []).some((d) => d.kind === "TRAIL_PROMOTED"), `${(t.decisions ?? []).map((d) => d.kind).join(",")}`);
  add("تریلینگ فروش: خروج در حد متحرک ۹۷.۵×(۱+۱.۲٪)", t.exitReason === "SL" && near(t.exitPrice, expectedTrailSl, 1e-9), `exit=${t.exitPrice} expected=${expectedTrailSl}`);
  add("تریلینگ فروش: خالص ≈ +۱.۲۳٪", near(t.realizedPnlPct, 1.23, 1e-6), `${t.realizedPnlPct}`);
}
// ---- سناریو ۸: پایان مهلت ۲۴ساعته ----
{
  const t = bySym["TIMEEXITUSDT"];
  add("TIME: خروج با علت TIME در آخرین کندل بسته‌شده", t.exitReason === "TIME" && near(t.exitPrice, 100.5), `exit=${t.exitPrice} reason=${t.exitReason}`);
  add("TIME: خالص = +۰.۴٪", near(t.realizedPnlPct, 0.4, 1e-9), `${t.realizedPnlPct}`);
  add("TIME: حدود SL/TP در کندل‌ها لمس نشده بود", near(t.mfePct, 0.8) && near(t.maePct, -0.1), `mfe=${t.mfePct} mae=${t.maePct}`);
}
// ---- سناریو ۹: ضد نشت آینده / ضد کندل پیش از تصمیم ----
{
  const t = bySym["NOLEAKUSDT"];
  add("ضد نشت: معامله همچنان OPEN است (کندل‌های پیش/هم‌زمان تصمیم استفاده نشدند)", t.status === "OPEN" && t.exitPrice === null, `status=${t.status} exit=${t.exitPrice}`);
  add("ضد نشت: MFE فقط از کندل پس از ورود = ۱.۰ (نه ۱۰ از کندل ممنوعه)", near(t.mfePct, 1.0, 1e-9), `mfe=${t.mfePct}`);
  add("ضد نشت: MAE از کندل پس از ورود = −۰.۵", near(t.maePct, -0.5, 1e-9), `mae=${t.maePct}`);
  add("ضد نشت: lastPrice از کندل در حال تشکیل به‌روز شد", near(t.lastPrice, 100.3), `lastPrice=${t.lastPrice}`);
}
// ---- فروشگاه پایدارشده ----
add("فروشگاه خروجی: ۹ معامله (۸ بسته + ۱ باز)", after.trades.length === 9 && after.trades.filter((t) => t.status === "CLOSED").length === 8, `total=${after.trades.length} closed=${after.trades.filter((t) => t.status === "CLOSED").length}`);
add("قرارداد صعودی فیوز: بدون ضرر متوالی (صفر بسته در فیکسچر)", res.consecutiveLosses === 0 && res.autoPaused === false, `consec=${res.consecutiveLosses} autoPaused=${res.autoPaused}`);

const failed = checks.filter((c) => c.verdict === "FAIL");
const verdict = failed.length === 0 ? "PASS" : "FAIL";
const result = {
  test: "t4_exits",
  domain: "④ SL/TP/سربه‌سر/تریلینگ/خروج زمانی + ضد نشت آینده (LONG و SHORT)",
  securityLock: "READ ONLY | PAPER ONLY | NO LIVE ORDERS",
  verdict,
  network: { fetchCalls, provider: "sandbox-stub" },
  realStoreSha256Unchanged: shaBefore === shaAfter,
  runResult: { paused: res.paused, scanSymbolCount: res.scanSymbolCount, universeCount: res.universeCount, consecutiveLosses: res.consecutiveLosses, quality: res.quality },
  checks,
};
writeFileSync(OUT, JSON.stringify(result, null, 2), "utf8");
console.log(JSON.stringify({ test: "t4_exits", verdict, failed: failed.length, fetchCalls, realStoreUnchanged: shaBefore === shaAfter }, null, 2));
