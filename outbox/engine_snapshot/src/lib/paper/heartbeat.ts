// MARI — قلب تپنده ربات (Bot Heartbeat)
// هدف: ربات کارنامک باید حتی بدون باز بودن داشبورد هم زنده بماند و هر ۱۰ دقیقه
// یک چرخه کامل (کنترل کیفیت + ارزیابی معاملات باز + جست‌وجوی سیگنال جدید) را اجرا کند.
// اصل ثابت: READ ONLY | PAPER ONLY | NO LIVE ORDERS — این چرخه فقط معامله تمرینی ثبت می‌کند.
// حفاظ: globalThis guard → با هات‌ریلود/dev بیشتر از یک تایمر ساخته نمی‌شود؛
// پرچم running → چرخه‌ها روی هم سوار نمی‌شوند؛ توقف اضطراری را موتور خودش رعایت می‌کند.

import "server-only";
import { runPaperCycle } from "./engine";
import { readStore } from "./store";
import { ensureTelegram } from "@/lib/telegram/bot";
import { notifyTradeEvents, dailyReportIfNeeded } from "@/lib/telegram/notify";

const HEARTBEAT_INTERVAL_MS = 10 * 60 * 1000; // هر ۱۰ دقیقه
const FIRST_TICK_DELAY_MS = 30 * 1000; // اولین چرخه: ۳۰ ثانیه پس از بوت سرور

export interface HeartbeatStatus {
  active: boolean; // آیا قلب تپنده در این فرایند روشن است؟
  startedAt: number | null;
  lastRunAt: number | null;
  lastOk: boolean;
  lastError: string | null;
  runCount: number;
  intervalMinutes: number;
  running: boolean; // آیا همین الان چرخه در حال اجراست؟
}

interface HeartbeatState {
  timer: ReturnType<typeof setInterval>;
  startedAt: number;
  lastRunAt: number | null;
  lastOk: boolean;
  lastError: string | null;
  runCount: number;
  running: boolean;
}

const g = globalThis as typeof globalThis & { __mariHeartbeat?: HeartbeatState };

async function tick(): Promise<void> {
  const st = g.__mariHeartbeat;
  if (!st || st.running) return;
  st.running = true;
  try {
    const before = readStore().trades; // عکس قبل — برای تشخیص رویدادهای تازه
    const res = await runPaperCycle();
    st.lastRunAt = Date.now();
    st.lastOk = true;
    st.lastError = null;
    st.runCount += 1;
    // خبرنگار تلگرام: سیگنال تازه / بسته‌شدن معامله را به چت‌های ثبت‌شده می‌فرستد
    await notifyTradeEvents(before, res.store.trades).catch((err) =>
      console.error("[mari-heartbeat] ارسال رویداد تلگرام ناموفق:", err instanceof Error ? err.message : err)
    );
    // گزارش روزانه ۹ صبح تهران — فقط اگر همین حالا در پنجره باشیم (وگرنه بدون هزینه)
    await dailyReportIfNeeded().catch((err) =>
      console.error("[mari-heartbeat] گزارش روزانه ناموفق:", err instanceof Error ? err.message : err)
    );
  } catch (err) {
    st.lastRunAt = Date.now();
    st.lastOk = false;
    st.lastError = err instanceof Error ? err.message : String(err);
    console.error("[mari-heartbeat] چرخه خودکار ناموفق:", st.lastError);
  } finally {
    st.running = false;
  }
}

/** روشن کردن قلب ربات — شنونده (idempotent): چند بار صدا زدن مشکلی ندارد */
export function ensureHeartbeat(): void {
  // حفاظ محیطی: در نسخهٔ منتشرشدهٔ عمومی (NODE_ENV=production) هیچ حلقهٔ پس‌زمینه‌ای روشن نمی‌شود.
  // دلیل: موتور اصلی (نظرسنجی تلگرام + قلب تپنده) فقط در سندباکسِ توسعه کار می‌کند —
  // وگرنه دو نظرسنجی موازی روی یک توکن خطای 409 تلگرام می‌سازد و دو دفتر کارنامک واگرا پیدا می‌شود.
  // داشبورد منتشرشده همچنان زنده است: APIهای درخواست‌محور (تیکر/کندل/گزارش) بدون قلب هم کار می‌کنند.
  if (process.env.NODE_ENV === "production") return;
  ensureTelegram(); // ربات تلگرام هم همراه قلب روشن می‌شود (idempotent)
  if (g.__mariHeartbeat) return;
  const st: HeartbeatState = {
    timer: setInterval(() => {
      void tick();
    }, HEARTBEAT_INTERVAL_MS),
    startedAt: Date.now(),
    lastRunAt: null,
    lastOk: true,
    lastError: null,
    runCount: 0,
    running: false,
  };
  g.__mariHeartbeat = st;
  console.log("[mari-heartbeat] قلب ربات روشن شد — چرخه خودکار هر ۱۰ دقیقه (PAPER ONLY)");
  setTimeout(() => {
    void tick();
  }, FIRST_TICK_DELAY_MS);
}

/** وضعیت قلب برای نمایش صادقانه در داشبورد */
export function getHeartbeatStatus(): HeartbeatStatus {
  const st = g.__mariHeartbeat;
  return {
    active: st !== undefined,
    startedAt: st?.startedAt ?? null,
    lastRunAt: st?.lastRunAt ?? null,
    lastOk: st?.lastOk ?? true,
    lastError: st?.lastError ?? null,
    runCount: st?.runCount ?? 0,
    intervalMinutes: HEARTBEAT_INTERVAL_MS / 60_000,
    running: st?.running ?? false,
  };
}
