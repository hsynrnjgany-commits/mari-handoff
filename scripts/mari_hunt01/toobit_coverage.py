#!/usr/bin/env python3
"""
MARI COVERAGE-01 — پوشش کامل جفت‌های USDT فعال تووبیت (فرمان رییس 2026-11-02)
==============================================================================
READ ONLY | PAPER ONLY | NO LIVE ORDERS — فقط endpoint عمومی بدون کلید.
- لیست نمادها: /api/v1/exchangeInfo تووبیت (فقط quoteAsset=USDT و status=TRADING)
  → کش scripts/mari_hunt01/universe.json با به‌روزرسانی روزی یک‌بار (TTL 24h)
- sweep دسته‌ای: هر دسته ۲۰ نماد (درخواست bookTicker به‌تفکیک نماد)، فاصلهٔ ≥۲ ثانیه
  بین دسته‌ها؛ HTTP 418 یا 429 → توقف فوری، ثبت علت در state، بدون هیچ تلاش مجدد
- سقف زمان چرخهٔ پوشش: ۸ دقیقه؛ نمادهای باقی‌مانده با cursor در state به چرخهٔ بعد
  منتقل می‌شوند تا بعد از چند چرخه همهٔ universe پوشش داده شود
- تصمیم‌ها از همان گیت M155 (hunt_gate_v2) می‌گذرند؛ بدون L2 معتبر هرگز WOULD_TRADE نیست
- بودجهٔ L2 در هر چرخه: ۳ کاندید (همان الگوی m140)؛ باقی → UNVERIFIED (tob_estimate)
- این ماژول هرگز به دادهٔ قدیمی تصمیم نمی‌سازد: TOB و عمق در لحظهٔ اجرا گرفته می‌شود
- خرابی این ماژول هرگز مسیر legacy hunt_sweep را نمی‌شکند (exceptionها در فراخواننده گرفته می‌شوند)
Endpointهای تأییدشده با پروب زندهٔ 2026-11-02:
  GET /api/v1/exchangeInfo                  → 200 (۵۳۶ نماد، ۵۱۶ جفت USDT TRADING)
  GET /quote/v1/ticker/bookTicker?symbol=X  → 200 [{s,b,bq,a,aq,t}]
  GET /quote/v1/depth?symbol=X&limit=50     → 200 {t, b:[[p,q]..], a:[[p,q]..]}
نسخهٔ کانونی این فایل در data/vault-private/coverage01/ نگهداری می‌شود تا از
بازیابی ساندباکس بازسازی‌پذیر باشد (الگوی M153 vault).
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import ssl
from datetime import datetime, timezone

ROOT = "/home/z/my-project"
sys.path.insert(0, f"{ROOT}/scripts/m140_tick_vault")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import snapshot as m140          # noqa: E402  آداپترهای بولک/عمق اثبات‌شدهٔ ۸ صرافی
import hunt_gate_v2 as gate      # noqa: E402  گیت کامل M155

TOOBIT = "https://api.toobit.com"
UNIVERSE = f"{ROOT}/scripts/mari_hunt01/universe.json"
STATE = f"{ROOT}/scripts/mari_hunt01/store/toobit_sweep_state.json"
DECISIONS = f"{ROOT}/scripts/mari_hunt01/store/decisions.jsonl"
REJECTS = f"{ROOT}/scripts/mari_hunt01/store/rejects.jsonl"
LAST = f"{ROOT}/scripts/m140_tick_vault/last_cycle.json"

BATCH = 20                # هر دسته ۲۰ نماد (فرمان رییس)
BATCH_GAP_S = 2.0         # فاصلهٔ بین دسته‌ها ≥ ۲ ثانیه (فرمان رییس)
CYCLE_CAP_S = 480.0       # سقف ۸ دقیقه برای یک چرخهٔ پوشش (فرمان رییس)
CAP_MARGIN_S = 20.0       # حاشیهٔ ایمن پیش از رسیدن به سقف
L2_BUDGET = 3             # حداکثر کاندید دارای عمق L2 در هر چرخه (الگوی m140)
UNIVERSE_TTL_S = 86400.0  # به‌روزرسانی کش universe: روزی یک‌بار
SIZE = 100.0              # حداقل نقدینگی TOB هر سمت (همان $100 گیت legacy)
COST_MIN_PCT = 0.30       # کف هزینه (taker×2+slip) — زیر آن فرصت نیست
PHANTOM_GROSS = 100.0     # >100٪ فانتوم
PHANTOM_M142 = 10.0       # >10٪ با عمق <$1000 → فانتوم M142
VENUES = ["binance", "mexc", "okx", "bybit", "kucoin", "gate", "bitget", "htx"]
CTX = ssl.create_default_context()
UA = {"User-Agent": "MARI-coverage01/1.0 (paper-research)"}


class RateLimitStop(Exception):
    """HTTP 418 (بن IP) یا 429 (تعداد درخواست) از تووبیت — توقف فوری بدون تلاش مجدد."""
    def __init__(self, code, sym):
        super().__init__(f"HTTP_{code}")
        self.code = code
        self.sym = sym


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def fnum(x):
    try:
        v = float(x)
        return v if v == v and v not in (float("inf"), float("-inf")) else None
    except Exception:
        return None


def http_json(url, timeout=12):
    """(data|None, http_code, err) — کد HTTP برای تشخیص 418/429 برگردانده می‌شود."""
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
            return json.loads(r.read().decode("utf-8", "replace")), 200, None
    except urllib.error.HTTPError as e:
        return None, e.code, f"HTTP_{e.code}"
    except Exception as e:
        return None, 0, type(e).__name__


# ── کش universe (به‌روزرسانی روزی یک‌بار) ────────────────────────────────────
def load_universe(force=False):
    now = datetime.now(timezone.utc)
    if not force and os.path.exists(UNIVERSE):
        try:
            u = json.load(open(UNIVERSE, encoding="utf-8"))
            age = (now - datetime.fromisoformat(u["refreshed_utc"])).total_seconds()
            if age <= UNIVERSE_TTL_S and u.get("symbols"):
                return u, False
        except Exception:
            pass
    d, code, err = http_json(f"{TOOBIT}/api/v1/exchangeInfo", timeout=30)
    if code != 200 or not isinstance(d, dict):
        raise RuntimeError(f"exchangeInfo_failed http={code} err={err}")
    raw = [s for s in d.get("symbols", [])
           if s.get("quoteAsset") == "USDT" and str(s.get("status", "")).upper() == "TRADING"]
    syms = sorted({s["symbol"] for s in raw if s.get("symbol") and m140.norm_base(s["symbol"])})
    u = {"schema": "toobit-universe-v1", "refreshed_utc": now.isoformat(),
         "source": f"{TOOBIT}/api/v1/exchangeInfo",
         "filter": "quoteAsset=USDT AND status=TRADING AND base not leveraged/stable",
         "raw_usdt_trading": len(raw), "count": len(syms), "symbols": syms}
    tmp = UNIVERSE + ".tmp"
    os.makedirs(os.path.dirname(UNIVERSE), exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(u, f, ensure_ascii=False)
    os.replace(tmp, UNIVERSE)
    return u, True


# ── سرب‌دفتر تووبیت به‌تفکیک نماد (یک درخواست به‌ازای هر نماد) ────────────────
def toobit_tob(sym):
    d, code, err = http_json(f"{TOOBIT}/quote/v1/ticker/bookTicker?symbol={sym}")
    if code in (418, 429):
        raise RateLimitStop(code, sym)
    if code != 200 or not isinstance(d, list) or not d:
        return None
    r = d[0]
    return {"bid": fnum(r.get("b")), "bidq": fnum(r.get("bq")),
            "ask": fnum(r.get("a")), "askq": fnum(r.get("aq"))}


def toobit_depth(sym, limit=50):
    d, code, err = http_json(f"{TOOBIT}/quote/v1/depth?symbol={sym}&limit={limit}")
    if code in (418, 429):
        raise RateLimitStop(code, sym)
    if code != 200 or not isinstance(d, dict):
        return None, None
    asks = [[fnum(p), fnum(q)] for p, q in d.get("a", []) or []]
    bids = [[fnum(p), fnum(q)] for p, q in d.get("b", []) or []]
    return asks, bids


# ── سرب‌دفتر ۸ صرافی دیگر (بولک، یک درخواست به‌ازای هر صرافی) ────────────────
def venue_book():
    """base → {"ask": (p, q, ex, sym), "bid": (p, q, ex, sym)} بهترین سمت هر صرافی دیگر."""
    best = {}
    errors = {}
    for ex in VENUES:
        try:
            rows, _lat = m140.bulk(ex)
        except Exception as e:
            errors[ex] = f"{type(e).__name__}"
            continue
        for r in rows:
            b = m140.norm_base(r.get("sym"))
            if not b:
                continue
            slot = best.setdefault(b, {"ask": None, "bid": None})
            a, aq, bi, bq_ = fnum(r.get("ask")), fnum(r.get("askSz")), fnum(r.get("bid")), fnum(r.get("bidSz"))
            if a and aq and a > 0 and (slot["ask"] is None or a < slot["ask"][0]):
                slot["ask"] = (a, aq, ex, r["sym"])
            if bi and bq_ and bi > 0 and (slot["bid"] is None or bi > slot["bid"][0]):
                slot["bid"] = (bi, bq_, ex, r["sym"])
        time.sleep(0.15)
    return best, errors


# ── پردازش یک نماد ───────────────────────────────────────────────────────────
def process_symbol(sym, base, cross, cycle_ts, decision_ts, seen, budget, probe_cache):
    """برگشت: (kind, row|None, extra|None) — kind ∈
    decision_wt / decision_skip / decision_unv / reject / no_signal / no_cross / empty / dup"""
    t = toobit_tob(sym)
    if not t or not t["bid"] or not t["ask"] or t["bid"] <= 0 or t["ask"] <= 0 \
            or not t["bidq"] or not t["askq"]:
        return "empty", None, None
    c = cross.get(base)
    if not c or not c.get("ask") or not c.get("bid"):
        return "no_cross", None, None
    opts = []
    oa, oaq, oa_ex, oa_sym = c["ask"]
    ob, obq, ob_ex, ob_sym = c["bid"]
    if oa and oaq and oa > 0 and oaq > 0:
        opts.append({"buy_p": oa, "buy_q": oaq, "buy_ex": oa_ex, "buy_sym": oa_sym,
                     "sell_p": t["bid"], "sell_q": t["bidq"], "sell_ex": "toobit", "sell_sym": sym,
                     "gross": (t["bid"] / oa - 1.0) * 100.0,
                     "tob_buy": oa * oaq, "tob_sell": t["bid"] * t["bidq"]})
    if ob and obq and ob > 0 and obq > 0:
        opts.append({"buy_p": t["ask"], "buy_q": t["askq"], "buy_ex": "toobit", "buy_sym": sym,
                     "sell_p": ob, "sell_q": obq, "sell_ex": ob_ex, "sell_sym": ob_sym,
                     "gross": (ob / t["ask"] - 1.0) * 100.0,
                     "tob_buy": t["ask"] * t["askq"], "tob_sell": ob * obq})
    if not opts:
        return "empty", None, None
    best = max(opts, key=lambda o: o["gross"])
    g = best["gross"]
    tob_min = min(best["tob_buy"], best["tob_sell"])
    bex, sex = best["buy_ex"], best["sell_ex"]
    uid = f"HUNT01-{cycle_ts[:19].replace(':','').replace('-','')}-{base}-{bex}-{sex}"
    if (cycle_ts, base, bex, sex) in seen:
        return "dup", None, None
    rej_base = {"id": uid, "base": base, "gross_pct": round(g, 4), "cycle_ts": cycle_ts,
                "sweep": "toobit_coverage_01"}
    if g > PHANTOM_GROSS:
        return "reject", dict(rej_base, reason="phantom>100%"), None
    if g > PHANTOM_M142 and tob_min < 1000:
        return "reject", dict(rej_base, reason="phantom_m142(gross>10%,depth<1000)"), None
    if g <= COST_MIN_PCT:
        return "no_signal", None, None
    if tob_min < SIZE:
        return "reject", dict(rej_base, reason=(
            f"liquidity<${SIZE:.0f}(tob ${best['tob_buy']:.0f}/${best['tob_sell']:.0f})")), None

    # ── کاندید سالم: با بودجهٔ L2 → گیت کامل M155؛ بدون بودجه → UNVERIFIED ──
    row_base = {
        "id": uid, "mission": "MARI-MULTIMARKET-HUNT-01",
        "decision_ts_utc": decision_ts, "cycle_ts": cycle_ts,
        "market": "crypto-spot", "base": base, "buy_ex": bex, "sell_ex": sex,
        "direction": f"ARB:LONG@{bex}/SELL@{sex}",
        "size_usdt": 100, "gross_pct": round(g, 4),
        "buy_price": round(best["buy_p"], 12), "sell_price": round(best["sell_p"], 12),
        "sweep": "toobit_coverage_01", "universe_sym": sym,
        "paper_only": True, "m155": True, "data_source": "toobit-coverage-v1",
    }
    asks_buy = bids_sell = None
    if budget[0] > 0:
        budget[0] -= 1
        if best["buy_ex"] == "toobit":
            asks_buy, _ = toobit_depth(best["buy_sym"])
        else:
            asks_buy, _, _ = m140.depth(best["buy_ex"], best["buy_sym"])
        time.sleep(0.15)
        if best["sell_ex"] == "toobit":
            _, bids_sell = toobit_depth(best["sell_sym"])
        else:
            _, bids_sell, _ = m140.depth(best["sell_ex"], best["sell_sym"])
        time.sleep(0.15)
    if asks_buy is None or bids_sell is None or not asks_buy or not bids_sell:
        # عمق در دسترس نیست → هرگز WOULD_TRADE نیست؛ UNVERIFIED صادقانه
        row = dict(row_base, method="tob_estimate", gate_status="UNVERIFIED",
                   gate_reason="UNVERIFIED(tob_only_depth_unavailable)", net_pct=None,
                   transfer_cost="UNAVAILABLE", decision="UNVERIFIED",
                   status="unverified_no_l2", buy_vwap=None, sell_vwap=None)
        return "decision_unv", row, None
    l2 = {"base": base, "buy_sym": best["buy_sym"], "sell_sym": best["sell_sym"],
          "buy_ex": bex, "sell_ex": sex, "gross_pct": round(g, 4),
          "buy_ask_top": best["buy_p"], "sell_bid_top": best["sell_p"],
          "asks_buy_venue": asks_buy[:50], "bids_sell_venue": bids_sell[:50],
          "recv_ts": now_iso()}
    gv = gate.evaluate_opportunity({"base": base}, l2, cache=probe_cache)
    if gv["status"] == "THIN_BOOK":
        return "reject", dict(rej_base, reason="thin_book_l2"), None
    idx_rec, duplicate = gate.update_index(
        f"{ROOT}/scripts/mari_hunt01/store/opportunities_index.jsonl",
        base, bex, sex, cycle_ts,
        payload={"status": gv["status"], "net_pct": gv["net_pct"],
                 "gross_vwap_pct": gv["gross_vwap_pct"], "sweep": "toobit_coverage_01"})
    dec = "WOULD_TRADE" if gv["status"] == "WOULD_TRADE" else "SKIP_NET"
    idt = gv.get("identity_detail") or {}
    gross_frac = (gv["gross_vwap_pct"] or 0) / 100.0
    scen = {f"fee{fu}$@inv{di}$": round((gross_frac - 0.003 - fu / di) * 100, 4)
            for fu, di in [(0.5, 5000), (1.0, 2000), (2.0, 1000), (5.0, 500)]}
    row = dict(row_base,
               method="l2_vwap_100",
               buy_vwap=round(gv["buy_vwap"], 12) if gv["buy_vwap"] else None,
               sell_vwap=round(gv["sell_vwap"], 12) if gv["sell_vwap"] else None,
               buy_slip_pct=round(gv["buy_slip_pct"], 4) if gv["buy_slip_pct"] is not None else None,
               sell_slip_pct=round(gv["sell_slip_pct"], 4) if gv["sell_slip_pct"] is not None else None,
               gross_pct=gv["gross_vwap_pct"], net_pct=gv["net_pct"],
               buy_age_s=round(gv["buy_age_s"], 2) if gv["buy_age_s"] is not None else None,
               sell_age_s=round(gv["sell_age_s"], 2) if gv["sell_age_s"] is not None else None,
               ts_source=gv["ts_source"], suspect=gv["suspect"],
               gate_status=gv["status"], gate_reason=gv["reason"],
               identity=idt.get("identity"), transfer=idt.get("transfer"),
               network=idt.get("network"), quote=idt.get("quote"),
               withdraw_buy=idt.get("withdraw_buy"), deposit_sell=idt.get("deposit_sell"),
               transfer_cost=gv["transfer_cost"], transfer_scenarios_net_pct=scen,
               duplicate_sighting=duplicate, seen_count=idx_rec.get("seen_count"),
               decision=dec,
               sl_target="N/A — سفر همزمان دوسویه",
               invalidation="بسته‌شدن اسپرد/افت عمق/کشف قیمت منجمد پیش از اجرا",
               status="closed_instant" if dec == "WOULD_TRADE" else "rejected_before_entry",
               reconstructed_from_transcript=False)
    kind = "decision_wt" if dec == "WOULD_TRADE" else "decision_skip"
    return kind, row, duplicate


# ── حلقهٔ اصلی پوشش ──────────────────────────────────────────────────────────
def load_state():
    if os.path.exists(STATE):
        try:
            return json.load(open(STATE, encoding="utf-8"))
        except Exception:
            pass
    return {"cursor": 0, "covered_symbols": [], "recent": []}


def save_state(state):
    tmp = STATE + ".tmp"
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)
    os.replace(tmp, STATE)


def append_jsonl(path, rows):
    if not rows:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def run_coverage(cycle_ts, decision_ts=None, probe_cache=None, seen=None, limit=None):
    """پوشش دسته‌ای universe تووبیت. برگشت: dict خلاصهٔ یک‌چرخه (برای cycles.jsonl و گزارش)."""
    t0 = time.monotonic()
    decision_ts = decision_ts or now_iso()
    uni, refreshed = load_universe()
    syms = uni["symbols"]
    n = len(syms)
    cross, venue_errors = venue_book()
    if not cross:
        return {"ok": False, "stage": "toobit_coverage", "reason": "no_venue_book",
                "venue_errors": venue_errors, "elapsed_s": round(time.monotonic() - t0, 1)}
    state = load_state()
    start = int(state.get("cursor") or 0) % n
    planned = min(n, int(limit)) if limit else n
    budget = [L2_BUDGET]
    probe_cache = probe_cache if probe_cache is not None else {}
    seen = seen if seen is not None else set()

    cnt = {"processed": 0, "decision_wt": 0, "decision_skip": 0, "decision_unv": 0,
           "reject": 0, "no_signal": 0, "no_cross": 0, "empty": 0, "dup": 0}
    decisions, rejects, covered = [], [], []
    gi = start
    done = 0
    stopped = "completed"
    rate_stop = None
    while done < planned:
        elapsed = time.monotonic() - t0
        if elapsed >= CYCLE_CAP_S - CAP_MARGIN_S:
            stopped = "time_cap"
            break
        batch = []
        for _ in range(BATCH):
            # بدون پیچش درون یک اجرا: رسیدن به انتهای لیست = پایان کامل (cursor → 0)
            # تا هیچ نمادی درون همان چرخه دوبار پردازش/ثبت نشود
            if done + len(batch) >= planned or gi >= n:
                break
            batch.append((gi % n, syms[gi % n]))
            gi += 1
        if not batch:
            break
        stop_now = False
        processed_in_batch = 0
        for pos, sym in batch:
            try:
                kind, row, _dup = process_symbol(
                    sym, m140.norm_base(sym), cross, cycle_ts, decision_ts, seen, budget, probe_cache)
            except RateLimitStop as e:
                # این نماد پردازش نشد — cursor دقیقاً روی همان نماد می‌ماند تا چرخهٔ بعد
                # از دست‌نخورده‌ترین نقطه ادامه دهد (هیچ نمادی از پوشش جا نمی‌ماند)
                gi = pos
                stopped = f"rate_limit_{e.code}"
                rate_stop = {"http": e.code, "symbol": e.sym, "utc": now_iso(),
                             "note": "توقف فوری طبق فرمان؛ بدون تلاش مجدد"}
                stop_now = True
                break
            processed_in_batch += 1
            cnt["processed"] += 1
            covered.append(m140.norm_base(sym) or sym)
            if kind == "decision_wt":
                cnt["decision_wt"] += 1
                decisions.append(row)
            elif kind == "decision_skip":
                cnt["decision_skip"] += 1
                decisions.append(row)
            elif kind == "decision_unv":
                cnt["decision_unv"] += 1
                decisions.append(row)
            elif kind == "reject":
                cnt["reject"] += 1
                rejects.append(row)
            else:
                cnt[kind] = cnt.get(kind, 0) + 1
            if time.monotonic() - t0 >= CYCLE_CAP_S:
                stopped = "time_cap"
                stop_now = True
                break
        done += processed_in_batch
        if stop_now:
            break
        if done < planned:
            time.sleep(BATCH_GAP_S)
    cursor_next = gi % n
    summary = {
        "ok": True, "stage": "toobit_coverage",
        "cycle_ts": cycle_ts, "universe_count": n,
        "universe_refreshed": refreshed, "universe_age_h": round(
            (datetime.now(timezone.utc) - datetime.fromisoformat(uni["refreshed_utc"])
             ).total_seconds() / 3600, 2),
        "cursor_start": start, "cursor_next": cursor_next,
        "planned": planned, "symbols_processed": cnt["processed"],
        "batches": (done + BATCH - 1) // BATCH,
        "decisions": cnt["decision_wt"] + cnt["decision_skip"] + cnt["decision_unv"],
        "would_trade": cnt["decision_wt"], "skip_net": cnt["decision_skip"],
        "unverified": cnt["decision_unv"], "rejects_written": cnt["reject"],
        "no_signal": cnt["no_signal"], "no_cross_venue": cnt["no_cross"],
        "quote_empty": cnt["empty"], "duplicate_skip": cnt["dup"],
        "l2_budget_used": L2_BUDGET - budget[0],
        "venue_errors": venue_errors,
        "stopped": stopped, "rate_limit_stop": rate_stop,
        "elapsed_s": round(time.monotonic() - t0, 1),
        "cap_s": CYCLE_CAP_S,
    }
    # ── نوشتن خروجی‌ها و state (append-only store) ──
    append_jsonl(DECISIONS, decisions)
    append_jsonl(REJECTS, rejects)
    prev_cov = set(state.get("covered_symbols") or [])
    merged = sorted(prev_cov | set(covered))
    state.update({
        "cursor": cursor_next,
        "universe_count": n, "universe_ts": uni["refreshed_utc"],
        "covered_count": len(merged), "covered_symbols": merged[:5000],
        "last_cycle_ts": cycle_ts, "last_run": summary,
        "rate_limit_stop": rate_stop,
        "recent": (state.get("recent") or [])[-4:] + [summary],
    })
    save_state(state)
    summary["covered_cumulative"] = len(merged)
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None,
                    help="حداکثر نماد این چرخه (اجرای آزمایشی)")
    ap.add_argument("--skip-snapshot", action="store_true",
                    help="snapshot تازه نگیر (فقط وقتی hunt_sweep همین حالا snapshot گرفته)")
    a = ap.parse_args()
    if not a.skip_snapshot:
        snap = subprocess.run(
            [sys.executable, f"{ROOT}/scripts/m140_tick_vault/snapshot.py"],
            capture_output=True, text=True, timeout=200)
        if snap.returncode != 0:
            print(json.dumps({"ok": False, "stage": "toobit_coverage",
                              "reason": "snapshot_failed", "stderr": snap.stderr[-300:]},
                             ensure_ascii=False))
            return 1
    cyc = json.load(open(LAST))
    cov = run_coverage(cycle_ts=cyc.get("cycle_ts", "?"), limit=a.limit)
    print(json.dumps(cov, ensure_ascii=False))
    return 0 if cov.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
