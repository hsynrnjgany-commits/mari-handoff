// MARI — آزمون آفلاین decisionlog (لاگ payload لحظهٔ تصمیم — گیت ۰۰۳/SHORT-15)
// اجرا: bun scripts/test-decisionlog.ts — فقط-خواندنی؛ بدون شبکه؛ بدون فایل.
import assert from "node:assert";
import { klineHash, pushDecision, bePromotion, trailPromotion, openDecision, type DecisionLogEntry } from "../src/lib/paper/decisionlog";
import type { PaperTrade } from "../src/lib/paper/types";
import type { KlinePoint } from "../src/lib/market/types";

let pass = 0;
let fail = 0;
function check(name: string, cond: boolean, detail = ""): void {
  if (cond) { pass++; console.log(`  ✓ ${name}`); }
  else { fail++; console.log(`  ✗ ${name} ${detail}`); }
}

const k: KlinePoint = { time: 1_710_000_000, open: 100, high: 102, low: 99, close: 101, volume: 5, closed: true };

// ۱) هش قطعی و حساس به payload
check("hash deterministic", klineHash("BTCUSDT", k) === klineHash("BTCUSDT", k));
check("hash differs per symbol", klineHash("BTCUSDT", k) !== klineHash("ETHUSDT", k));
const k2 = { ...k, close: 101.5 };
check("hash differs per ohlc", klineHash("BTCUSDT", k) !== klineHash("BTCUSDT", k2));
check("hash 16 hex chars", /^[0-9a-f]{16}$/.test(klineHash("BTCUSDT", k)));

// ۲) الحاق امن — معاملهٔ قدیمی بدون فیلد decisions
const t = { symbol: "BTCUSDT" } as PaperTrade;
check("old trade has no decisions", !t.decisions);
pushDecision(t, bePromotion(t, k, 99.0, 100.1, k.time * 1000 + 3_600_000));
check("push creates array", Array.isArray(t.decisions) && t.decisions.length === 1);
pushDecision(t, trailPromotion(t, k, 100.1, 100.8, k.time * 1000 + 7_200_000));
check("push appends", t.decisions!.length === 2);

// ۳) ساختار ورودی‌ها
const be: DecisionLogEntry = t.decisions![0];
check("BE entry kind", be.kind === "BE_PROMOTED");
check("BE from/to", be.fromSl === 99.0 && be.toSl === 100.1);
check("BE hash matches candle", be.ohlcHash === klineHash("BTCUSDT", k));
check("BE candleTime", be.candleTime === k.time);
check("BE source tag", be.source === "mari-paper-v2/decisionlog/v1");
const tr: DecisionLogEntry = t.decisions![1];
check("TRAIL entry kind", tr.kind === "TRAIL_PROMOTED");
check("TRAIL from/to", tr.fromSl === 100.1 && tr.toSl === 100.8);

// ۴) ورودی OPEN
const op = openDecision("BTCUSDT", k, "SHORT", 101.0, 97.0, "ATR", k.time * 1000);
check("OPEN kind", op.kind === "OPEN");
check("OPEN null fromSl", op.fromSl === null);
check("OPEN toSl = planned SL", op.toSl === 101.0);
check("OPEN hash", op.ohlcHash === klineHash("BTCUSDT", k));
check("OPEN detail has side+basis", op.detail.includes("SHORT") && op.detail.includes("ATR"));

// ۵) JSON-safe (دفتر فقط JSON ذخیره می‌کند)
check("entries json-safe", JSON.parse(JSON.stringify(t.decisions)).length === 2);

console.log(`\nنتیجه: ${pass} pass / ${fail} fail`);
process.exit(fail === 0 ? 0 : 1);
