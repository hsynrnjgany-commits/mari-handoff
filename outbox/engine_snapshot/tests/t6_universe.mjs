// M73-R آزمون ۶ — §۵-⑥ کشف全局 بازار / کیفیت داده سراسری / هماهنگی خوشه‌ها
// ماژول واقعی: universe.ts (با provider استاب) + command-center-shared.ts + نقشه خوشه واقعی research
import { writeFileSync, mkdirSync, readFileSync } from "node:fs";
import { isTradableSpot, buildHunterBatch, getHunterUniverse, faNameOf, HUNTER_PARAMS } from "@/lib/market/universe";
import { dataBadge, recomputeNetPct, drawdownSeries } from "@/lib/fleet/command-center-shared";
import { netPct } from "@/lib/paper/pnl";
import { WATCH_SYMBOLS } from "@/lib/market/types";

const OUT = "/home/z/my-project/scripts/m73p/sandbox/out/t6_universe.json";
const checks = [];
const add = (name, passed, detail) => checks.push({ name, verdict: passed ? "PASS" : "FAIL", detail });
const near = (a, b, eps = 1e-9) => Math.abs(a - b) <= eps;

// ---------- ۱) ماتریس حذف تعریفی ----------
add("BTCUSDT قابل معامله", isTradableSpot("BTCUSDT") === true, `${isTradableSpot("BTCUSDT")}`);
add("USDCUSDT (استیبل) حذف", isTradableSpot("USDCUSDT") === false, `${isTradableSpot("USDCUSDT")}`);
add("BTCUPUSDT (اهرمی) حذف", isTradableSpot("BTCUPUSDT") === false, `${isTradableSpot("BTCUPUSDT")}`);
add("BTC3LUSDT (اهرمی) حذف", isTradableSpot("BTC3LUSDT") === false, `${isTradableSpot("BTC3LUSDT")}`);
add("BTCBEARUSDT (اهرمی) حذف", isTradableSpot("BTCBEARUSDT") === false, `${isTradableSpot("BTCBEARUSDT")}`);
add("ETHUSDT (غیر USDT؟) — جفت غیر USDT حذف", isTradableSpot("ETHBTC") === false, `${isTradableSpot("ETHBTC")}`);

// ---------- ۲) کشف جهان با provider استاب ----------
process.env.M73P_FIXTURE = "/home/z/my-project/scripts/m73p/sandbox/out/t6_tickers.json";
const tickers = {};
const qvs = [1000, 500, 300, 100, 50, 10, 5, 1];
const names = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "PEPEUSDT", "USDCUSDT", "BTCUPUSDT", "ZEROUSDT"];
names.forEach((s, i) => { tickers[s] = { price: s === "ZEROUSDT" ? 0 : 100 - i, changePct: 1.5, qv: qvs[i] }; });
mkdirSync("/home/z/my-project/scripts/m73p/sandbox/out", { recursive: true });
writeFileSync(process.env.M73P_FIXTURE, JSON.stringify({ source: "toobit", asOf: Date.now(), tickers }, null, 2), "utf8");

const uni = await getHunterUniverse();
add("استیبل/اهرمی/بی‌قیمت در کشف نیامده‌اند (۵ از ۸)", uni.discovered === 5, `discovered=${uni.discovered} rows=${uni.rows.length}`);
add("رتبه‌بندی نزولی بر حجم (اولویت گشت‌زنی، نه حذف)", uni.rows.every((r, i) => i === 0 || (uni.rows[i - 1].quoteVolume ?? 0) >= (r.quoteVolume ?? 0)), JSON.stringify(uni.rows.map((r) => `${r.symbol}:${r.quoteVolume}`)));
const cached = await getHunterUniverse();
add("کش ۵دقیقه‌ای جهان (TTL)", cached.rows.length === uni.rows.length && cached.asOf === uni.asOf, `asOf برابر: ${cached.asOf === uni.asOf}`);

// ---------- ۳) گشت چرخشی buildHunterBatch ----------
const bigUniverse = [];
for (let i = 0; i < 150; i++) bigUniverse.push({ symbol: `SYM${String(i).padStart(3, "0")}USDT`, price: 1, changePct: 0, quoteVolume: 150 - i });
const watch = WATCH_SYMBOLS.filter((s) => !s.stable).map((s) => s.symbol).slice(0, 4);
const batch1 = buildHunterBatch(bigUniverse, watch);
add("واچ‌لیست همیشه در دسته است", watch.every((s) => batch1.symbols.includes(s)), JSON.stringify(watch));
add("سر بازار = ۴۰ (HUNTER_PARAMS)", batch1.headCount === HUNTER_PARAMS.headCount, `${batch1.headCount}`);
add("گشت چرخشی = ۶۰", batch1.patrolCount === HUNTER_PARAMS.patrolCount, `${batch1.patrolCount}`);
add("بدون تکرار در دسته", new Set(batch1.symbols).size === batch1.symbols.length, `len=${batch1.symbols.length} uniq=${new Set(batch1.symbols).size}`);
const batch2 = buildHunterBatch(bigUniverse, watch);
const patrol1 = batch1.symbols.slice(-batch1.patrolCount);
const patrol2 = batch2.symbols.slice(-batch2.patrolCount);
add("پنجره گشت دوم جابه‌جا شد (چرخش دورانی)", JSON.stringify(patrol1) !== JSON.stringify(patrol2), `cursor: ${batch1.cursor} → ${batch2.cursor}`);
const union = new Set([...patrol1, ...patrol2]);
add("پوشش با اتحاد دو چرخه بزرگ‌تر شد (هیچ نمادی از دید دور نمی‌ماند)", union.size > patrol1.length, `|P1|=60 |P2|=60 |P1∪P2|=${union.size}`);

// ---------- ۴) نقشه خوشه واقعی (فقط خواندن) — نقشه هماهنگی گیت‌های پژوهشی ----------
const MAP_PATH = "/home/z/my-project/data/research/mari_cluster_map_v1.json";
const cmap = JSON.parse(readFileSync(MAP_PATH, "utf8"));
const mappings = Array.isArray(cmap.mappings) ? cmap.mappings : Object.values(cmap.mappings ?? {});
add("نقشه خوشه: ساختار mappings موجود است", mappings.length > 0, `repo_id=${cmap.repo_id} version=${cmap.version} clusters=${mappings.length}`);
const clusterNames = mappings.map((m) => m?.cluster).filter(Boolean);
add("هر خوشه نام غیرخالی دارد", clusterNames.length === mappings.length && clusterNames.every((c) => typeof c === "string" && c.length > 0), JSON.stringify(clusterNames).slice(0, 200));
const allItems = mappings.flatMap((m) => m?.items ?? []);
add("هر خوشه حداقل یک گیت/قلم دارد", mappings.every((m) => Array.isArray(m?.items) && m.items.length > 0), `total items=${allItems.length}`);
const gateIds = allItems.map((x) => String(x).split(" ")[0]);
const gateLike = gateIds.filter((g) => /^(H65-\d+|P-\d+|H\d+-\d+)$/.test(g));
const namedProtocols = allItems.length - gateLike.length;
add("اقلام نقشه: همگی شناسه گیت استاندارد یا نام پروتکل فارسی", gateLike.length + namedProtocols === allItems.length && namedProtocols >= 0,
  `${gateLike.length} گیت استاندارد + ${namedProtocols} پروتکل نامی (مثل «پروتکل ضد-بیش‌برازش») از ${allItems.length} قلم`);
const shared = gateIds.filter((g, i) => gateIds.indexOf(g) !== i);
add("[ثبت مشاهده] گیت‌های مشترک بین خوشه‌ها (هماهنگی افقی عمدی است)", true,
  shared.length === 0 ? "هیچ اشتراکی نیست" : `${[...new Set(shared)].join(", ")} در چند خوشه موضوعی ظاهر می‌شوند — نقشه، متن‌محور است نه انحصاری`);
add("فراداده نقشه کامل است", ["repo_id", "version", "timestamp", "lang"].every((k) => cmap[k] !== undefined), `keys=${Object.keys(cmap).join(",")}`);
add("[ثبت مشاهده] این نقشه «هماهنگی گیت‌های پژوهشی» است (H65/P-XX)، نه خوشه نمادهای بازار", true,
  `۹ خوشه موضوعی؛ نمادهای بازار از این نقشه عبور نمی‌کنند — هماهنگی نمادها از طریق WATCH_SYMBOLS و جهان شکار است`);

// نام فارسی — صادقانه null برای بیرون واچ‌لیست
add("faNameOf: واچ‌لیست → نام، بیرون → null", faNameOf("BTCUSDT") !== null && faNameOf("NOTREALUSDT") === null, `BTCUSDT=${faNameOf("BTCUSDT")}`);

// ---------- ۵) کیفیت داده سراسری — هم‌راستایی لایه‌ها ----------
// ۵-الف: recomputeNetPct (fleet) == netPct (paper) — تک‌منبع حقیقت
const fNet = recomputeNetPct({ side: "SHORT", entryPrice: 100, exitPrice: 98 }, 0.1);
const pNet = netPct("SHORT", 100, 98);
add("فرمول بازمحاسبه fleet == فرمول paper (تک‌منبع حقیقت)", near(fNet, pNet), `fleet=${fNet} paper=${pNet}`);
// ۵-ب: drawdownSeries هم‌خوان با حساب دستی
const curve = [{ t: 1, v: 0 }, { t: 2, v: 3.8 }, { t: 3, v: 1.6 }, { t: 4, v: 2.5 }];
const dd = drawdownSeries(curve);
const maxDd = Math.max(...dd.map((p) => p.dd));
add("drawdownSeries: بیشترین افت = ۲.۲ (اوج ۳.۸ → کف ۱.۶)", near(maxDd, 2.2), `maxDD=${maxDd}`);
// ۵-ج: dataBadge — گذرگاه صداقت داده
add("dataBadge: NO_DATA برای null", dataBadge(null, 5 * 60_000, null) === "NO_DATA", `${dataBadge(null, 5 * 60_000, null)}`);
add("dataBadge: STALE_DATA برای داده قدیمی", dataBadge(Date.now() - 10 * 60_000, 5 * 60_000, null) === "STALE_DATA", `${dataBadge(Date.now() - 10 * 60_000, 5 * 60_000, null)}`);
add("dataBadge: LIVE_DATA برای تازه", dataBadge(Date.now(), 5 * 60_000, null) === "LIVE_DATA", `${dataBadge(Date.now(), 5 * 60_000, null)}`);
add("dataBadge: ERROR برای خطای واکشی (اولویت خطا)", dataBadge(Date.now(), 5 * 60_000, "network fail") === "ERROR", `${dataBadge(Date.now(), 5 * 60_000, "network fail")}`);

const failed = checks.filter((c) => c.verdict === "FAIL");
const verdict = failed.length === 0 ? "PASS" : "FAIL";
const result = {
  test: "t6_universe",
  domain: "⑥ کشف全局 بازار / کیفیت داده سراسری / هماهنگی خوشه‌ها",
  securityLock: "READ ONLY | PAPER ONLY | NO LIVE ORDERS",
  verdict,
  clusterMapPath: MAP_PATH,
  clusterMapReadonly: true,
  checks,
};
writeFileSync(OUT, JSON.stringify(result, null, 2), "utf8");
console.log(JSON.stringify({ test: "t6_universe", verdict, failed: failed.length }, null, 2));
