// تست FIX-RETRO-01 — اجرا از ریشهٔ پروژه:
// npx esbuild tests/test_fix_retro.ts --bundle --platform=node --format=esm --outfile=/tmp/t_retro.mjs && node /tmp/t_retro.mjs src/lib/paper/engine.ts
import fs from "node:fs";
import { evalCursorStart } from "../src/lib/paper/cursor";
const H = 3_600_000;
let pass = 0; const fails: string[] = [];
const check = (name: string, ok: boolean) => { if (ok) pass++; else fails.push(name); };
check("نشانگر ذخیره‌شده اولویت دارد", evalCursorStart({ evalCursorMs: 10 * H, lastCheck: 50 * H + 5 }, H) === 10 * H);
check("بدون نشانگر: از lastCheck به پایین‌ترین مرز ساعت", evalCursorStart({ lastCheck: 7 * H + 1234 }, H) === 7 * H);
check("lastCheck دقیقاً روی مرز ساعت", evalCursorStart({ lastCheck: 7 * H }, H) === 7 * H);
check("معاملهٔ تازه بدون نشانگر و بدون lastCheck ⇒ null", evalCursorStart({ lastCheck: null }, H) === null);
check("نشانگر null و lastCheck موجود", evalCursorStart({ evalCursorMs: null, lastCheck: 3 * H + 1 }, H) === 3 * H);
// شبیه‌سازی کوچک همان قاعده: سه دور پایش؛ دور سوم نباید کندل ۱ را با حد ضرر سربه‌سرِ بعدی دوباره بررسی کند
type K = { ct: number; lo: number; hi: number };
const ks: K[] = [ { ct: 1 * H, lo: 99.95, hi: 100.4 }, { ct: 2 * H, lo: 100.3, hi: 101.2 }, { ct: 3 * H, lo: 100.5, hi: 100.9 } ];
function cycle(state: { sl: number; cur: number | null; closedAt: number | null; lastCheck: number | null }, upto: number, useCursor: boolean) {
  const cursor = useCursor ? evalCursorStart({ evalCursorMs: state.cur, lastCheck: state.lastCheck }, H) : null;
  for (const k of ks.slice(0, upto)) {
    if (state.closedAt !== null) return;
    if (cursor !== null && k.ct <= cursor) continue;
    state.lastCheck = upto * H;
    if (k.lo <= state.sl) { state.closedAt = k.ct; return; }
    if (k.hi >= 101) state.sl = 100.1; // ارتقا به سربه‌سر پس از +۱٪
    state.cur = k.ct;
  }
}
const bug = { sl: 99, cur: null as number | null, closedAt: null as number | null, lastCheck: null as number | null };
const fix = { ...bug };
for (const m of [1, 2, 3]) { cycle(bug, m, false); cycle(fix, m, true); }
check("بدون اصلاح: باگ بازتولید می‌شود (خروج عطف‌به‌ماسبق در کندل ۱)", bug.closedAt === 1 * H);
check("با اصلاح: معامله باز می‌ماند (کندل ۳ به سربه‌سر نرسید)", fix.closedAt === null);
const eng = fs.readFileSync(process.argv[2] ?? "src/lib/paper/engine.ts", "utf8");
check("engine.ts: نشانگر در ابتدای evaluateTrade خوانده می‌شود", eng.includes("const cursor = evalCursorStart(t, intervalMs);"));
check("engine.ts: کندل‌های ارزیابی‌شده رد می‌شوند", eng.includes("if (cursor !== null && ct <= cursor) continue;"));
check("engine.ts: نشانگر پس از هر کندل بدون خروج جلو می‌رود", eng.includes("t.evalCursorMs = ct;"));
console.log(`نتیجه: ${pass}/${pass + fails.length} PASS`); if (fails.length) { console.log("شکست‌ها:", fails); process.exit(1); }
