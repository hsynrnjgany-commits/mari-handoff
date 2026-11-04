#!/usr/bin/env python3
"""
MARI DERIV-01 — لایهٔ دادهٔ مشتقه (پژوهشی؛ فعلاً بر تصمیم‌ها اثر ندارد)
=======================================================================
READ ONLY | PAPER ONLY | NO LIVE ORDERS | NO KEYS — فقط endpoint عمومی، stdlib، بدون نصب جدید.
فرمان رییس 2026-11-02 · هر اجرا به‌ازای هر نماد یک ردیف در store/deriv.jsonl می‌نویسد:
  ts_utc، symbol، funding، oi، تغییر OI نسبت به اجرای قبل همین نماد، لیکویید (در دسترس نبود → null)

منابع — فقط آنچه پروب زندهٔ 2026-11-02 تأیید کرد (بدون حدس):
  فاندینگ:  BINANCE fapi /fapi/v1/premiumIndex            → 200 (bulk، lastFundingRate)
  OI:       BYBIT   v5   /v5/market/tickers?category=linear → 200 (bulk، openInterest(+Value))
  حجم 24h:  TOOBIT /quote/v1/ticker/24hr            → 200 (bulk، qv — برای fallback و بافت)
  لیکویید:  بایننس REST 404 (فقط وب‌سوکت)؛ OKX فقط per-instrument (محدود؛ bulk ندارد)
            → در جمع انبوه در دسترس نیست → null + برچسب صادقانه
  تووبیت مشتقه: همهٔ نامزدهای پروب‌شده (funding/OI/L-S/forceOrders/v5/fapi) → 404 (در دسترس نیست)

نرخ (فرمان رییس): منابع bulk = ۲ درخواست در کل اجرا (بای‌بیت فاندینگ+OI یکجا،
تووبیت حجم). مسیر per-symbol (فقط fallback اختیاری OI بایننس برای نمادهای
فاقد Bybit): دستهٔ ۲۰تایی، فاصلهٔ ≥۲ ثانیه، HTTP 418/429 → توقف فوری،
ثبت علت در state، بدون هیچ تلاش مجدد.
⚠️ اجرای زندهٔ 2026-11-02: بایننس fapi → HTTP_418 (IP محدود) → فاندینگ از بای‌بیت.
نمادها (فرمان رییس): فقط universe.json (COVERAGE-01)؛ نبودِ آن → ۶۰ نماد برتر حجم تووبیت.
"""
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

ROOT = "/home/z/my-project"
UNIVERSE = f"{ROOT}/scripts/mari_hunt01/universe.json"
STORE = f"{ROOT}/scripts/mari_deriv/store"
OUT = f"{STORE}/deriv.jsonl"
STATE = f"{STORE}/state.json"

BATCH = 20          # هر دسته ۲۰ نماد (فرمان رییس)
BATCH_GAP_S = 2.0   # فاصلهٔ دسته‌ها ≥ ۲ ثانیه (فرمان رییس)
CAP_S = 480.0       # سقف نرم اجرا
CTX = ssl.create_default_context()
UA = {"User-Agent": "MARI-deriv01/1.0 (paper-research)"}


class RateLimitStop(Exception):
    """HTTP 418/429 — توقف فوری بدون تلاش مجدد (فرمان رییس)."""
    def __init__(self, code, sym):
        super().__init__(f"HTTP_{code}")
        self.code, self.sym = code, sym


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def fnum(x):
    try:
        v = float(x)
        return v if v == v and v not in (float("inf"), float("-inf")) else None
    except Exception:
        return None


def http_json(url, timeout=15):
    """(data|None, code, err) — کد برای تشخیص 418/429 لازم است."""
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
            return json.loads(r.read().decode("utf-8", "replace")), r.status, None
    except urllib.error.HTTPError as e:
        return None, e.code, f"HTTP_{e.code}"
    except Exception as e:
        return None, 0, type(e).__name__


# ── منابع bulk (پروب‌شده) ────────────────────────────────────────────────────
def fetch_binance_funding():
    """symbol→lastFundingRate. یک درخواست برای همهٔ بازار USDT-M."""
    d, code, err = http_json("https://fapi.binance.com/fapi/v1/premiumIndex")
    if code in (418, 429):
        raise RateLimitStop(code, "binance:premiumIndex")
    if code != 200 or not isinstance(d, list):
        return {}, f"http_{code}_{err}"
    out = {}
    for r in d:
        s = r.get("symbol") or ""
        if s.endswith("USDT"):
            out[s] = fnum(r.get("lastFundingRate"))
    return out, None


def fetch_bybit_oi():
    """symbol→{oi_base, oi_usd, funding, turnover24h}. یک درخواست برای کل linear."""
    d, code, err = http_json("https://api.bybit.com/v5/market/tickers?category=linear")
    if code in (418, 429):
        raise RateLimitStop(code, "bybit:tickers")
    if code != 200 or not isinstance(d, dict):
        return {}, f"http_{code}_{err}"
    lst = (d.get("result") or {}).get("list") or []
    out = {}
    for r in lst:
        s = r.get("symbol") or ""
        if s.endswith("USDT"):
            out[s] = {"oi_base": fnum(r.get("openInterest")),
                      "oi_usd": fnum(r.get("openInterestValue")),
                      "funding": fnum(r.get("fundingRate")),
                      "interval_h": fnum(r.get("fundingIntervalHour")),
                      "turnover24h": fnum(r.get("turnover24h"))}
    return out, None


def fetch_toobit_qv():
    """symbol→qv (حجم ۲۴ساعتهٔ اسپات تووبیت). یک درخواست؛ برای fallback و بافت."""
    d, code, err = http_json("https://api.toobit.com/quote/v1/ticker/24hr", timeout=20)
    if code in (418, 429):
        raise RateLimitStop(code, "toobit:24hr")
    if code != 200 or not isinstance(d, list):
        return {}, f"http_{code}_{err}"
    return {r.get("s"): fnum(r.get("qv")) for r in d if r.get("s")}, None


# ── مسیر per-symbol با نظم نرخ (فقط fallback OI) ─────────────────────────────
def batch_fetch_binance_oi(symbols, t0):
    """symbol→openInterest بایننس، دستهٔ ۲۰تایی، فاصلهٔ ≥۲s، 418/429 → توقف فوری."""
    out, done = {}, 0
    stopped = None
    while done < len(symbols):
        if time.monotonic() - t0 >= CAP_S:
            stopped = "time_cap"
            break
        chunk = symbols[done:done + BATCH]
        for s in chunk:
            d, code, err = http_json(
                f"https://fapi.binance.com/fapi/v1/openInterest?symbol={s}")
            if code in (418, 429):
                raise RateLimitStop(code, s)
            if code == 200 and isinstance(d, dict):
                out[s] = fnum(d.get("openInterest"))
            time.sleep(0.15)
        done += len(chunk)
        if done < len(symbols):
            time.sleep(BATCH_GAP_S)
    return out, stopped


# ── universe (فرمان رییس: universe.json یا ۶۰ نماد برتر حجم) ────────────────
def load_symbols(qv):
    if os.path.exists(UNIVERSE):
        try:
            u = json.load(open(UNIVERSE, encoding="utf-8"))
            syms = u.get("symbols") or []
            if syms:
                return sorted(syms), f"universe.json({u.get('count')})"
        except Exception:
            pass
    # fallback: ۶۰ نماد برتر حجم اسپات تووبیت (فقط جفت‌های USDT)
    ranked = sorted(((s, v) for s, v in qv.items()
                     if s.endswith("USDT") and v), key=lambda x: -x[1])
    return [s for s, _ in ranked[:60]], "top60_toobit_qv_fallback"


def prev_oi_map():
    """symbol→(ts, oi) آخرین ردیف هر نماد از اجراهای قبل (قبل از append این اجرا)."""
    last = {}
    if not os.path.exists(OUT):
        return last
    with open(OUT, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("oi") is not None and r.get("symbol"):
                last[r["symbol"]] = (r.get("ts_utc"), float(r["oi"]))
    return last


def append_jsonl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def load_state():
    if os.path.exists(STATE):
        try:
            return json.load(open(STATE, encoding="utf-8"))
        except Exception:
            pass
    return {"runs": 0}


def save_state(st):
    tmp = STATE + ".tmp"
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False)
    os.replace(tmp, STATE)


def main():
    ap_t0 = time.monotonic()
    run_id = "DERIV-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    src_status = {}
    try:
        return _main_inner(ap_t0, run_id, src_status)
    except RateLimitStop as e:
        # توقف فوری طبق فرمان رییس — بدون هیچ تلاش مجدد، علت در state
        st = load_state()
        st["stop"] = {"http": e.code, "symbol": e.sym, "utc": now_iso(),
                      "note": "توقف فوری 418/429؛ بدون تلاش مجدد"}
        save_state(st)
        print(json.dumps({"ok": False, "stopped": f"rate_limit_{e.code}",
                          "symbol": e.sym, "utc": st["stop"]["utc"],
                          "rows_written": 0}, ensure_ascii=False))
        return 2


def _main_inner(ap_t0, run_id, src_status):
    # منبع اصلی فاندینگ و OI: بای‌بیت (یک درخواست bulk، هر دو فیلد).
    # بایننس premiumIndex در اجرای زندهٔ 2026-11-02T07:0xZ → HTTP_418 (محدودیت نرخ IP)
    # → طبق فرمان بدون تلاش مجدد؛ فقط با --binance-funding به‌عنوان چک متقاطع استفاده می‌شود.
    bybit, b_err = fetch_bybit_oi()
    src_status["bybit_funding_oi"] = b_err or f"ok({len(bybit)} sym)"
    qv, qv_err = fetch_toobit_qv()
    src_status["toobit_qv_24h"] = qv_err or f"ok({len(qv)} sym)"
    funding = {s: v.get("funding") for s, v in bybit.items()}
    f_err = "bybit_v5_tickers"
    if "--binance-funding" in sys.argv:
        bf, bf_err = fetch_binance_funding()
        src_status["binance_funding"] = bf_err or f"ok({len(bf)} sym)"
        if bf:
            funding, f_err = bf, "binance_fapi_premiumindex"

    syms, sym_src = load_symbols(qv)
    prev = prev_oi_map()

    rows, n_fund, n_oi, n_delta, n_liq_avail = [], 0, 0, 0, 0
    for s in syms:
        base = s[:-4] if s.endswith("USDT") else s
        oi_usd = (bybit.get(s) or {}).get("oi_usd")
        fu = funding.get(s)
        p_ts, p_oi = prev.get(s, (None, None))
        delta = pct = None
        if oi_usd is not None and p_oi is not None and p_oi > 0:
            delta = round(oi_usd - p_oi, 2)
            pct = round((oi_usd - p_oi) / p_oi * 100.0, 4)
        if fu is not None:
            n_fund += 1
        if oi_usd is not None:
            n_oi += 1
        if delta is not None:
            n_delta += 1
        rows.append({
            "run_id": run_id, "ts_utc": now_iso(), "symbol": s, "base": base,
            "funding": fu, "funding_src": f_err if fu is not None else None,
            "funding_interval_h": (bybit.get(s) or {}).get("interval_h") if f_err == "bybit_v5_tickers" else None,
            "oi": oi_usd, "oi_base": (bybit.get(s) or {}).get("oi_base"),
            "oi_src": "bybit_v5_tickers" if oi_usd is not None else None,
            "oi_prev": p_oi, "oi_delta": delta, "oi_delta_pct": pct,
            "liquidations": None, "liq_status": "unavailable_bulk",
            "toobit_qv_24h": qv.get(s), "layer": "deriv01", "paper_only": True,
            "no_effect_on_decisions": True,
        })

    elapsed = round(time.monotonic() - ap_t0, 1)
    summary = {
        "ok": True, "run_id": run_id, "ts_utc": now_iso(),
        "symbols_source": sym_src, "symbols_total": len(syms),
        "rows_written": len(rows), "funding_covered": n_fund, "oi_covered": n_oi,
        "oi_delta_covered": n_delta, "liquidations_covered": n_liq_avail,
        "liquidations_note": "بایننس REST 404؛ OKX فقط per-instrument → bulk ندارد",
        "sources": src_status, "elapsed_s": elapsed, "stopped": "completed",
        "per_symbol_requests_used": 0,
    }
    append_jsonl(OUT, rows)
    st = load_state()
    st["runs"] = int(st.get("runs", 0)) + 1
    st["last_run"] = summary
    st["stop"] = None
    save_state(st)
    print(json.dumps(summary, ensure_ascii=False))
    return 0


def main_fallback_oi():
    """اجرای fallback OI بایننس برای نمادهای بدون Bybit — با نظم نرخ کامل."""
    t0 = time.monotonic()
    qv, _ = fetch_toobit_qv()
    syms, sym_src = load_symbols(qv)
    bybit, b_err = fetch_bybit_oi()
    if b_err:
        print(json.dumps({"ok": False, "stage": "bybit", "err": b_err}, ensure_ascii=False))
        return 1
    missing = [s for s in syms if not (bybit.get(s) or {}).get("oi_usd")]
    try:
        oi_map, stopped = batch_fetch_binance_oi(missing, t0)
    except RateLimitStop as e:
        st = load_state()
        st["stop"] = {"http": e.code, "symbol": e.sym, "utc": now_iso(),
                      "note": "توقف فوری طبق فرمان؛ بدون تلاش مجدد"}
        save_state(st)
        print(json.dumps({"ok": False, "stopped": f"rate_limit_{e.code}",
                          "symbol": e.sym, "utc": st["stop"]["utc"]}, ensure_ascii=False))
        return 2
    print(json.dumps({"ok": True, "missing": len(missing), "filled": len(oi_map),
                      "stopped": stopped or "completed"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    if "--oi-fallback" in sys.argv:
        sys.exit(main_fallback_oi())
    sys.exit(main())
