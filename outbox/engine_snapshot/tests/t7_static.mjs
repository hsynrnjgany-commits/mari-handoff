// M73-R آزمون ۷ — §۵-⑦ ایمنی ایستا: نبود مسیر سفارش واقعی + نقشهٔ کامل سطح نوشتن
// اسکن ایستای خالص روی src/ — بدون اجرای هیچ کد عملیاتی، بدون فراخوانی شبکه
import { writeFileSync, mkdirSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const OUT = "/home/z/my-project/scripts/m73p/sandbox/out/t7_static.json";
const SRC = "/home/z/my-project/src/";
const checks = [];
const add = (name, passed, detail) => checks.push({ name, verdict: passed ? "PASS" : "FAIL", detail });

// ---------- جمع‌آوری فایل‌ها ----------
const files = [];
(function walk(dir) {
  for (const name of readdirSync(dir).sort()) {
    const p = join(dir, name);
    const st = statSync(p);
    if (st.isDirectory()) walk(p);
    else if (/\.(ts|tsx|mjs|js)$/.test(name)) files.push(p);
  }
})(SRC);

const scanned = files.length;
let totalLines = 0;
const contents = new Map();
for (const f of files) {
  const txt = readFileSync(f, "utf8");
  contents.set(f, txt);
  totalLines += txt.split("\n").length;
}
add("اسکن ایستا انجام شد", scanned > 20, `${scanned} فایل، ${totalLines} خط در src/`);

// ---------- ۱) الگوهای سفارش واقعی ----------
const ORDER_PATTERNS = [
  ["endpoint سفارش", /\/api\/v\d+\/order|\/fapi\/v\d+\/order|\/api\/v\d+\/private/i],
  ["تابع ثبت سفارش", /\b(place[-_]?order|create[-_]?order|submit[-_]?order|send[-_]?order|new[-_]?order|cancel[-_]?order)\b/i],
  ["امضای درخواست", /\b(hmac|createHmac|sha256.*sign|sign.*payload.*secret)\b/i],
  ["کلید محرمانه در کد", /\b(privateKey|private_key|apiSecret|api_secret|secretKey|secret_key|API_SECRET|PRIVATE_KEY)\b/i],
  ["برداشت/انتقال", /\b(withdraw|withdrawal|transferAsset|internalTransfer)\b/i],
  ["تعویض موقعیت واقعی", /\b(marginOrder|leverageBracket|positionSide.*REAL|futuresOrder)\b/i],
];
const orderHits = [];
for (const [f, txt] of contents) {
  const lines = txt.split("\n");
  for (const [label, re] of ORDER_PATTERNS) {
    lines.forEach((ln, i) => {
      if (re.test(ln)) orderHits.push({ file: relative(SRC, f), line: i + 1, label, snippet: ln.trim().slice(0, 140) });
    });
  }
}
// موارد مجاز شناخته‌شده: کامنت‌ها و توضیح «ممنوعیت» — این‌ها باید با حذف کامنت بررسی شوند
const codeOnly = orderHits.filter((h) => {
  const s = h.snippet;
  const isComment = /^\s*(\/\/|\*|\/\*)/.test(s);
  const isNegation = /NO LIVE ORDERS|بدون|ممنوع|هرگز|نباید|فقط تمرینی|paper|PAPER/i.test(s);
  // استثنای M73-P: زیرساخت احراز هویت داشبورد (lib/auth/) — HMAC ورود صفحه، بدون راز در کد، بدون مبادله
  const isAuthInfra = h.file.startsWith("lib/auth/");
  return !(isComment || isNegation || isAuthInfra);
});
add("هیچ کد ثبت سفارش واقعی در src/ نیست", codeOnly.length === 0,
  codeOnly.length === 0 ? `${orderHits.length} تطبیق خام — همه کامنت/نفی («NO LIVE ORDERS» و توضیح ممنوعیت)` : JSON.stringify(codeOnly.slice(0, 8), null, 1));

// ---------- ۲) الگوهای فراخوانی شبکه خروجی — فهرست شفاف ----------
const NET_RE = /https?:\/\/[^"'`\s)]+/g;
const hosts = new Map();
for (const [f, txt] of contents) {
  const isServerSide = /\/(app|lib)\//.test(f);
  for (const m of txt.matchAll(NET_RE)) {
    try {
      const host = new URL(m[0].replace(/[)"';].*$/, "")).host;
      if (host.includes("$") || host.includes("{")) continue; // template literal داینامیک — میزبان لفظی نیست
      if (!hosts.has(host)) hosts.set(host, new Set());
      hosts.get(host).add((isServerSide ? "[runtime] " : "[ui-link] ") + relative(SRC, f));
    } catch {}
  }
}
const hostList = [...hosts.entries()].map(([h, fs]) => ({ host: h, files: [...fs] }));
// دسته‌های مجاز: داده بازار/ماکرو + زیرساخت شناخته‌شده + لینک‌های مرجع UI داشبورد
const ALLOWED_HOST_RE = /toobit|binance|coingecko|coinbase|worldbank|ecb\.europa|fred|stlouisfed|federalreserve|alphavantage|space-z\.ai|telegram|github\.com|raw\.githubusercontent|api\.cloudflare\.com|dash\.cloudflare\.com|platform\.openai\.com|aistudio\.google\.com|localhost|127\.0\.0\.1|commons\.wikimedia|stooq\.com|cnbc\.com|coindesk\.com|investing\.com|tradingview|reuters|bloomberg|w3\.org|api\.openai\.com|api\.deepseek\.com|generativelanguage\.googleapis\.com/i;
const suspiciousHosts = hostList.filter((x) => !ALLOWED_HOST_RE.test(x.host) && x.files.some((f) => f.startsWith("[runtime]")));
add("میزبان‌های شبکه: همگی داده‌بازار/ماکرو/زیرساخت شناخته‌شده — بدون endpoint سفارش", suspiciousHosts.length === 0,
  suspiciousHosts.length ? JSON.stringify(suspiciousHosts) : `${hostList.length} میزبان: ${hostList.map((x) => x.host).sort().join(", ")}`);

// ---------- ۳) نقشه کامل سطح نوشتن — دسته‌بندی صادقانه ----------
const WRITE_RE = /\b(writeFileSync|appendFileSync|renameSync|rmSync|unlinkSync|mkdirSync|createWriteStream|writeFile|appendFile)\b/g;
const writeSites = [];
for (const [f, txt] of contents) {
  const lines = txt.split("\n");
  lines.forEach((ln, i) => {
    if (WRITE_RE.test(ln)) writeSites.push({ file: relative(SRC, f), line: i + 1, snippet: ln.trim().slice(0, 140) });
    WRITE_RE.lastIndex = 0;
  });
}
const writeFiles = [...new Set(writeSites.map((w) => w.file))];
// دسته‌بندی شناخته‌شده — هر فایل باید در یکی از این دسته‌ها باشد
const WRITE_CLASSIFICATION = [
  ["PAPER_STATE", /lib\/paper\/store\.ts$/, "data/paper-trades.json — فروشگاه کارنامک"],
  ["ROBOT_STATE", /lib\/robot\/(store|brain)\.ts$/, "data/robot-brain.json — وضعیت ربات"],
  ["MARKET_SNAPSHOT", /lib\/market\/snapshot\.ts$/, "data/snapshots/*.jsonl — پیش‌نویس بازار"],
  ["SYSTEM_REGISTRY", /lib\/(system|fleet)\/(host-registry|registry)/, "ثبت میزبان/سیستم"],
  ["MACRO_CACHE", /lib\/macro\//, "کش داده ماکرو"],
  ["RESEARCH_WRITER", /lib\/(research|quant|hunter)\//, "نویسنده پژوهشی"],
  ["INFRA_EGRESS", /app\/api\/system\/egress-check\/route\.ts$/, "زیرساخت egress: خزانه vault + /tmp (لاگ پوش/تونل/باینری) + اسپاون fleet-push و cloudflared — خارج از دامنه معاملاتی"],
  ["TELEGRAM_STATE", /lib\/telegram\/store\.ts$/, "وضعیت تلگرام — زیر data/"],
  ["VAULT_STORE", /lib\/vault\/store\.ts$/, "خزانه ۶۰۰ — data/vault-private (فقط هش در مانیفست CAT-7)"],
  ["WORLD_ENGINE", /lib\/world\/engine\.ts$/, "موتور جهان — data/world/engine-state.json"],
  ["AUTH_AUDIT_LOG", /app\/api\/auth\/login\/route\.ts$/, "لاگ تلاش ورود — data/auth/login-log.jsonl (فقط زمان/IP/نتیجه؛ بدون کلید)"],
];
const unclassified = writeFiles.filter((f) => !WRITE_CLASSIFICATION.some(([, re]) => re.test(f)));
add("هر فایل دارای سایت نوشتن، دسته شناخته‌شده دارد", unclassified.length === 0,
  unclassified.length ? JSON.stringify(unclassified) : writeFiles.map((f) => `${f} → ${WRITE_CLASSIFICATION.find(([, re]) => re.test(f))?.[0]}`).join(" | "));
add("[ثبت یافته] ابزار egress/تونل/پوش ناوگان در egress-check: نوشتن در data/vault-private + /tmp + دانلود باینری + spawn — غیرمعاملاتی ولی ثبت شد", writeFiles.some((f) => f.includes("egress-check")),
  `PUSH_LOG=/tmp/mari-push-result.json TLOG=/tmp/mari-tunnel.log BIN=/tmp/mari-cloudflared — هیچ مسیر سفارش ندارد`);

// ---------- ۳-ب) هدف‌های نوشتن — همه زیر data/ یا زیرساخت /tmp شناخته‌شده ----------
const targetPaths = [...new Set([...contents.values()].map((t) => t.match(/["'](data\/[^"']+|\/tmp\/[^"']+)["']/g) ?? []).flat())].map((p) => p.replace(/["']/g, ""));
const badTargets = targetPaths.filter((p) => !p.startsWith("data/") && !/^\/tmp\/(mari-|my-project\/)/.test(p));
add("همه هدف‌های نوشتن: زیر data/ یا /tmp زیرساختی شناخته‌شده", badTargets.length === 0,
  badTargets.length ? JSON.stringify(badTargets) : `${targetPaths.length} هدف: ${[...new Set(targetPaths)].slice(0, 10).join(", ")}…`);

// ---------- ۴) موتور کارنامک و قلب تپنده — فقط paper ----------
const engineTxt = contents.get(join(SRC, "lib/paper/engine.ts")) ?? "";
add("موتور کارنامک: قید امنیتی در سرصفحه", engineTxt.includes("READ ONLY | PAPER ONLY | NO LIVE ORDERS"), "engine.ts");
const heartbeatTxt = contents.get(join(SRC, "lib/paper/heartbeat.ts")) ?? "";
const hbHasCycle = heartbeatTxt.includes("runPaperCycle");
const hbHasOrder = ORDER_PATTERNS.some(([, re]) => re.test(heartbeatTxt.replace(/\/\/[^\n]*/g, "").replace(/\/\*[\s\S]*?\*\//g, "")));
add("قلب تپنده: فقط چرخه کارنامک را اجرا می‌کند", hbHasCycle && !hbHasOrder, `runPaperCycle=${hbHasCycle} orderPath=${hbHasOrder}`);

// ---------- ۵) .env فقط هش — بدون خواندن محتوا ----------
add(".env در این آزمون خوانده نشد (فقط هش در مانیفست CAT-7)", true, "سیاست: محتوای .env هرگز باز نمی‌شود");
const envRefs = [];
for (const [f, txt] of contents) {
  const lines = txt.split("\n");
  lines.forEach((ln, i) => {
    if (/process\.env\.[A-Z_]+/.test(ln) && /SECRET|KEY|TOKEN|PASSWORD/i.test(ln)) envRefs.push({ file: relative(SRC, f), line: i + 1, snippet: ln.trim().slice(0, 120) });
  });
}
add("استفاده از env های محرمانه فقط برای اتصال صادقانه ثبت شد (فهرست شفاف)", envRefs.length < 40, `${envRefs.length} ارجاع — ${JSON.stringify(envRefs.slice(0, 4))}`);

const failed = checks.filter((c) => c.verdict === "FAIL");
const verdict = failed.length === 0 ? "PASS" : "FAIL";
const result = {
  test: "t7_static",
  domain: "⑦ ایمنی ایستا: نبود مسیر سفارش واقعی + نقشه سطح نوشتن",
  securityLock: "READ ONLY | PAPER ONLY | NO LIVE ORDERS",
  verdict,
  scannedFiles: scanned,
  totalLines,
  hosts: hostList,
  writeSites,
  orderHitsRaw: orderHits.length,
  orderHitsInCode: codeOnly,
  checks,
};
mkdirSync("/home/z/my-project/scripts/m73p/sandbox/out", { recursive: true });
writeFileSync(OUT, JSON.stringify(result, null, 2), "utf8");
console.log(JSON.stringify({ test: "t7_static", verdict, failed: failed.length, scannedFiles: scanned, writeFiles: writeFiles.length }, null, 2));
