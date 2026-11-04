// MARI — فروشگاه کارنامک: ذخیره‌سازی پایدار روی فایل + حافظه جایگزین
// بخش ۳۶.۷: اجرای مجدد نباید رکورد تکراری بسازد؛ نوشتن اتمی با فایل موقت
// بخش ۳۸.۷: داده پژوهشی جدا از داده خام نگهداری می‌شود (پوشه data/)

import "server-only";
import fs from "fs";
import path from "path";
import type { PaperStoreShape, PaperTrade } from "./types";

const DATA_DIR = path.join(process.cwd(), "data");
const STORE_PATH = path.join(DATA_DIR, "paper-trades.json");

// حافظه جایگزین اگر فایل‌سیستم در دسترس نباشد (وضعیت صادقانه ثبت می‌شود)
let memStore: PaperStoreShape | null = null;
let fsDisabled = false;

// زنجیره نوشتن برای جلوگیری از تداخل نوشتن هم‌زمان (بخش ۳۶.۴: جلوگیری از اجرای ناسازگار هم‌زمان)
let writeChain: Promise<void> = Promise.resolve();

function normalizeStore(parsed: unknown): PaperStoreShape | null {
  if (parsed && typeof parsed === "object" && Array.isArray((parsed as PaperStoreShape).trades)) {
    return parsed as PaperStoreShape;
  }
  return null;
}

export function readStore(): PaperStoreShape {
  if (!fsDisabled) {
    try {
      const raw = fs.readFileSync(STORE_PATH, "utf8");
      const parsed = normalizeStore(JSON.parse(raw));
      if (parsed) return parsed;
    } catch (err) {
      if ((err as NodeJS.ErrnoException).code === "ENOENT") {
        // فایل هنوز ساخته نشده — وضعیت اولیه، خطا نیست
      } else if ((err as NodeJS.ErrnoException).code === "EACCES" || (err as NodeJS.ErrnoException).code === "EROFS") {
        fsDisabled = true;
        console.error("[paper-store] دسترسی فایل ممکن نیست؛ ادامه با حافظه موقت");
      } else {
        console.error("[paper-store] خطای خواندن:", err instanceof Error ? err.message : err);
      }
    }
  }
  return memStore ?? { version: 1, updatedAt: 0, trades: [], paused: false };
}

export function writeStore(store: PaperStoreShape): Promise<void> {
  memStore = store;
  if (fsDisabled) return Promise.resolve();
  writeChain = writeChain.then(() => {
    try {
      fs.mkdirSync(DATA_DIR, { recursive: true });
      const tmp = `${STORE_PATH}.${process.pid}.tmp`;
      fs.writeFileSync(tmp, JSON.stringify(store, null, 2), "utf8");
      fs.renameSync(tmp, STORE_PATH);
    } catch (err) {
      const code = (err as NodeJS.ErrnoException).code;
      if (code === "EACCES" || code === "EROFS") {
        fsDisabled = true;
        console.error("[paper-store] نوشتن فایل ممکن نیست؛ ادامه فقط با حافظه موقت");
      } else {
        console.error("[paper-store] خطای نوشتن:", err instanceof Error ? err.message : err);
      }
    }
  });
  return writeChain;
}

/** نگهداشت فروشگاه در اندازه معقول: حداکثر ۵۰۰ معامله (قدیمی‌های بسته‌شده حذف می‌شوند؛ جدیدترین‌ها می‌مانند) */
export function trimStore(trades: PaperTrade[], max = 500): PaperTrade[] {
  if (trades.length <= max) return trades;
  const open = trades.filter((t) => t.status === "OPEN");
  const closed = trades.filter((t) => t.status === "CLOSED");
  // M73-P/P1 (Task-123) — اصلاح جهت: نسخهٔ قبلی slice(0, …) روی آرایهٔ قدیمی→جدید
  // «قدیمی‌ترین» بسته‌شده‌ها را نگه می‌داشت و «جدیدترین»ها را حذف می‌کرد — برخلاف قرارداد
  // و برخلاف توضیح همین تابع. اکنون از انتهای آرایه (جدیدترین‌ها) نگه داشته می‌شود؛
  // گارد room<=0 هم از تلهٔ slice(-0) (بازگشت کل آرایه) جلوگیری می‌کند.
  const room = Math.max(0, max - open.length);
  const keepClosed = room > 0 ? closed.slice(-room) : [];
  return [...open, ...keepClosed];
}
