#!/usr/bin/env python3
"""
M155 HUNT GATE v2 — گیت‌های کیفیت موتور آربیتراژ (فازهای ۲ تا ۶ مأموریت M155)
==============================================================================
READ ONLY | PAPER ONLY | NO LIVE ORDERS — هیچ سفارشی ارسال نمی‌شود.
قوانین:
  فاز ۲: سیگنال بدون L2 معتبر هرگز WOULD_TRADE نمی‌شود → UNVERIFIED
  فاز ۳: MAX_BOOK_AGE_SECONDS=10 → STALE؛ timestamp نامعتبر/آینده‌دار → INVALID_TIMESTAMP
  فاز ۴: dedup بر کلید symbol+buy_exchange+sell_exchange با first_seen/last_seen/seen_count
  فاز ۵: هویت توکن (قرارداد/شبکه/quote) + وضعیت withdraw/deposit — نبودِ اطلاعات = تأیید نیست
  فاز ۶: gross>3% → SUSPECT (حذف خودکار نیست؛ فقط با PASS همهٔ گیت‌ها به WOULD_TRADE می‌رسد)
هزینه‌ها: فقط هزینهٔ قابل اندازه‌گیری (taker×2)؛ slippage داخل VWAP واقعی عمق است؛
هزینهٔ انتقال حدس زده نمی‌شود → transfer_cost=UNAVAILABLE مگر از API عمومی به‌دست آید.
"""
import json
import os
import urllib.request
import urllib.error
import ssl
from datetime import datetime, timezone

CONFIG = {
    "MAX_BOOK_AGE_SECONDS": 10.0,
    "MAX_REPORT_AGE_MINUTES": 30,
    "SUSPICIOUS_GROSS_SPREAD_PCT": 3.0,
    "NOTIONAL_USDT": 100.0,
    "TAKER_FEE_PCT": 0.10,          # هر سمت، درصد
    "NET_MIN_PCT": 0.15,            # حداقل لبهٔ خالصِ قابل‌اندازه‌گیری
    "CLOCK_SKEW_TOLERANCE_S": 5.0,
    "PROBE_TIMEOUT_S": 5.0,
    "PROBE_VENUES": ("kucoin", "gate", "htx"),   # فقط endpointهای عمومی بدون کلید
}

CTX = ssl.create_default_context()
UA = {"User-Agent": "MARI-huntgate/2.0 (paper-research)"}

# نام‌های رایج شبکه بین صرافی‌ها → کلید نرمال
CHAIN_ALIAS = {
    "eth": "erc20", "erc20": "erc20", "ethereum": "erc20",
    "trx": "trc20", "trc20": "trc20", "tron": "trc20",
    "bsc": "bep20", "bep20": "bep20", "bnb": "bep20", "bnb smart chain": "bep20",
    "polygon": "polygon", "matic": "polygon", "poly": "polygon",
    "arbitrum": "arbitrum", "arb": "arbitrum", "optimism": "optimism", "op": "optimism",
    "sol": "solana", "solana": "solana",
}

# ── فاز ۳: تازگی ─────────────────────────────────────────────────────────────
def classify_book_age(ts, now=None):
    """(status, age_s) — status ∈ FRESH/STALE/INVALID_TIMESTAMP/UNAVAILABLE.
    ts می‌تواند ISO-string یا epoch-ms باشد. timestamp آینده‌دار/نامعتبر → INVALID_TIMESTAMP."""
    if ts in (None, "", 0):
        return "UNAVAILABLE", None
    try:
        if isinstance(ts, (int, float)):
            t = datetime.fromtimestamp(float(ts) / 1000.0, tz=timezone.utc)
        else:
            s = str(ts).replace("Z", "+00:00")
            t = datetime.fromisoformat(s)
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
    except Exception:
        return "INVALID_TIMESTAMP", None
    now = now or datetime.now(timezone.utc)
    if t.tzinfo is None:
        return "INVALID_TIMESTAMP", None
    age = (now - t).total_seconds()
    if age < -CONFIG["CLOCK_SKEW_TOLERANCE_S"]:
        return "INVALID_TIMESTAMP", age          # دادهٔ آینده‌دار
    if age > CONFIG["MAX_BOOK_AGE_SECONDS"]:
        return "STALE", age
    return "FRESH", age

# ── فاز ۲: VWAP عمق واقعی برای نوتینال ───────────────────────────────────────
def vwap_fill(levels, notional):
    """(vwap|None, filled_bool, slippage_pct_vs_top|None) — از بهترین سطح L1 برای
    کل نوتینال استفاده نمی‌شود؛ میانگین وزنی سطوح واقعی تا پرشدن نوتینال."""
    spent = got = 0.0
    top = None
    for lvl in levels or []:
        try:
            p, q = float(lvl[0]), float(lvl[1])
        except Exception:
            continue
        if p <= 0 or q <= 0:
            continue
        if top is None:
            top = p
        cost = p * q
        if spent + cost >= notional:
            got += (notional - spent) / p
            vwap = notional / got if got > 0 else None
            slip = (abs(vwap - top) / top * 100) if (vwap and top) else None
            return vwap, True, slip
        spent += cost
        got += q
    return None, False, None

def measurable_net_pct(buy_vwap, sell_vwap):
    """سود خالص ٪ برای نوتینال با هزینهٔ taker دو سمت (slippage داخل VWAP است).
    هزینهٔ انتقال در این عدد حدس زده نمی‌شود — جداگانه UNAVAILABLE/ثبت می‌شود."""
    if not buy_vwap or not sell_vwap or buy_vwap <= 0:
        return None
    gross = (sell_vwap / buy_vwap - 1.0) * 100.0
    return gross - 2.0 * CONFIG["TAKER_FEE_PCT"]

# ── فاز ۴: dedup ─────────────────────────────────────────────────────────────
def dedup_key(base, buy_ex, sell_ex):
    return f"{base}|{buy_ex}|{sell_ex}"

def update_index(index_path, base, buy_ex, sell_ex, cycle_id, payload=None):
    """ایندکس append-only فرصت‌های یکتا. برگشت: (rec, duplicate_bool).
    duplicate = این کلید قبلاً در چرخهٔ دیگری دیده شده است."""
    recs = []
    if os.path.exists(index_path):
        with open(index_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        recs.append(json.loads(line))
                    except Exception:
                        pass
    k = dedup_key(base, buy_ex, sell_ex)
    now_iso = datetime.now(timezone.utc).isoformat()
    rec = next((r for r in recs if r.get("key") == k), None)
    duplicate = rec is not None
    if rec is None:
        rec = {"key": k, "base": base, "buy_ex": buy_ex, "sell_ex": sell_ex,
               "first_seen": now_iso, "first_cycle_id": cycle_id,
               "last_seen": now_iso, "last_cycle_id": cycle_id,
               "seen_count": 1}
        recs.append(rec)
    else:
        rec["last_seen"] = now_iso
        rec["last_cycle_id"] = cycle_id
        rec["seen_count"] = int(rec.get("seen_count", 1)) + 1
        if payload:
            rec["latest"] = payload
    if payload and duplicate is False:
        rec["latest"] = payload
    os.makedirs(os.path.dirname(index_path), exist_ok=True)
    with open(index_path, "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return rec, duplicate

# ── فاز ۵: هویت توکن + وضعیت انتقال (فقط endpoint عمومی بدون کلید) ──────────
def coin_from_sym(sym):
    s = str(sym or "").upper()
    for sep in ("-", "_", "/"):
        if sep in s:
            return s.split(sep)[0] or None
    if s.endswith("USDT") and len(s) > 4:
        return s[:-4]
    return s or None

def _http_json(url, timeout=None):
    t = timeout or CONFIG["PROBE_TIMEOUT_S"]
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=t, context=CTX) as r:
        return json.loads(r.read().decode("utf-8", "replace"))

def _norm_chain(name):
    return CHAIN_ALIAS.get(str(name or "").strip().lower(), str(name or "").strip().lower())

def probe_venue(ex, coin, cache=None):
    """بررسی هویت/انتقال از endpoint عمومی. برگشت:
    {status: VERIFIED|UNAVAILABLE, contract, chains:{CHAIN:{withdraw,deposit}}, fee_hint, source}
    هر خطا → UNAVAILABLE (نبود اطلاعات هرگز تأیید تلقی نمی‌شود)."""
    ck = (ex, coin)
    if cache is not None and ck in cache:
        return cache[ck]
    out = {"status": "UNAVAILABLE", "contract": None, "chains": {},
           "fee_hint": None, "source": None}
    try:
        if ex == "kucoin" and coin:
            d = _http_json(f"https://api.kucoin.com/api/v2/currencies/{coin}")["data"]
            out["contract"] = d.get("contractAddress") or None
            for ch in d.get("chains") or []:
                key = _norm_chain(ch.get("chain") or ch.get("chainName"))
                out["chains"][key] = {"withdraw": ch.get("withdrawable") is True,
                                      "deposit": ch.get("depositable") is True}
                if out["fee_hint"] is None and ch.get("withdrawFee"):
                    out["fee_hint"] = ch.get("withdrawFee")
            out["source"] = "kucoin/api-v2-currencies"
        elif ex == "gate" and coin:
            d = _http_json(f"https://api.gateio.ws/api/v4/spot/currency_chains/{coin}")
            arr = d if isinstance(d, list) else []
            for ch in arr:
                key = _norm_chain(ch.get("chain"))
                out["chains"][key] = {"withdraw": ch.get("is_withdraw_enabled") is True,
                                      "deposit": ch.get("is_deposit_enabled") is True}
                if not out["contract"] and ch.get("contract_addr"):
                    out["contract"] = ch.get("contract_addr")
            out["source"] = "gate/api-v4-currency_chains"
        elif ex == "htx" and coin:
            d = _http_json(f"https://api.huobi.pro/v2/reference/currencies?currency={coin.lower()}")
            for item in d.get("data") or []:
                for ch in item.get("chains") or []:
                    key = _norm_chain(ch.get("chain"))
                    out["chains"][key] = {
                        "withdraw": ch.get("withdrawStatus") == "allowed",
                        "deposit": ch.get("depositStatus") == "allowed"}
                    if not out["contract"] and ch.get("contractAddress"):
                        out["contract"] = ch.get("contractAddress")
            out["source"] = "htx/api-v2-reference-currencies"
        else:
            out["source"] = "no_public_endpoint"
    except Exception as e:
        out["source"] = f"error:{type(e).__name__}"
    if out["chains"] or out["contract"]:
        out["status"] = "VERIFIED"
    if cache is not None:
        cache[ck] = out
    return out

def identity_and_transfer_check(base, buy_sym, sell_sym, buy_ex, sell_ex, cache=None):
    """برگشت: {quote, identity: VERIFIED|SYMBOL_MISMATCH|UNAVAILABLE,
    transfer: OPEN|TRANSFER_BLOCKED|UNAVAILABLE, network, contract_buy, contract_sell,
    withdraw_buy, deposit_sell, transfer_cost}"""
    r = {"quote": None, "identity": "UNAVAILABLE", "transfer": "UNAVAILABLE",
         "network": "UNAVAILABLE", "contract_buy": None, "contract_sell": None,
         "withdraw_buy": None, "deposit_sell": None, "transfer_cost": "UNAVAILABLE",
         "detail": []}
    # ۵.۴ quote currency دقیقاً یکسان (USDT با USDT)
    bq = str(buy_sym or "").upper().endswith("USDT")
    sq = str(sell_sym or "").upper().endswith("USDT")
    r["quote"] = "USDT" if (bq and sq) else ("MIXED" if (bq or sq) else "UNKNOWN")
    if not (bq and sq):
        r["identity"] = "SYMBOL_MISMATCH"
        r["detail"].append("quote_currency_mismatch")
        return r
    coin_b, coin_s = coin_from_sym(buy_sym), coin_from_sym(sell_sym)
    if not coin_b or not coin_s or coin_b != coin_s:
        r["identity"] = "SYMBOL_MISMATCH"
        r["detail"].append(f"base_symbol:{coin_b}!={coin_s}")
        return r
    pb = probe_venue(buy_ex, coin_b, cache)
    ps = probe_venue(sell_ex, coin_s, cache)
    r["contract_buy"], r["contract_sell"] = pb.get("contract"), ps.get("contract")
    # ۵.۲ قرارداد — فقط وقتی هر دو در دسترس‌اند قابل اثبات است
    if pb["status"] == "VERIFIED" and ps["status"] == "VERIFIED":
        cb, cs = (pb["contract"] or "").lower(), (ps["contract"] or "").lower()
        if cb and cs:
            if cb != cs:
                r["identity"] = "SYMBOL_MISMATCH"
                r["detail"].append("contract_address_differs")
                return r
            r["identity"] = "VERIFIED"
        else:
            r["detail"].append("contract_missing_on_one_side")
    else:
        r["detail"].append(f"probe_unavailable:{buy_ex}={pb['status']},{sell_ex}={ps['status']}")
    # ۵.۳/۵.۵/۵.۶ شبکه مشترک + withdraw (خرید) + deposit (فروش)
    chains_b, chains_s = pb.get("chains") or {}, ps.get("chains") or {}
    if chains_b and chains_s:
        common = sorted(set(chains_b) & set(chains_s))
        if not common:
            r["transfer"] = "TRANSFER_BLOCKED"
            r["detail"].append("no_common_network")
            return r
        ch = common[0]
        r["network"] = ch
        wb, dp = chains_b[ch]["withdraw"], chains_s[ch]["deposit"]
        r["withdraw_buy"], r["deposit_sell"] = wb, dp
        if wb is False or dp is False:
            r["transfer"] = "TRANSFER_BLOCKED"
            r["detail"].append(f"route_closed:{ch}(w={wb},d={dp})")
            return r
        if wb and dp:
            r["transfer"] = "OPEN"
            fee = pb.get("fee_hint")
            if fee is not None:
                try:
                    r["transfer_cost"] = f"fee={fee} {coin_b} ({ch})"
                except Exception:
                    pass
    else:
        r["detail"].append("chain_data_unavailable")
    return r

# ── ارزیابی کامل یک فرصت ────────────────────────────────────────────────────
def evaluate_opportunity(cand, l2, now=None, cache=None):
    """ارزیابی یک فرصت با همهٔ گیت‌ها. برگشت dict با:
    status, checks{...}, ages, vwap, net, suspect, reason, reasons_all"""
    now = now or datetime.now(timezone.utc)
    cfg = CONFIG
    checks = {"l2_both_sides": False, "fresh": False, "identity": None,
              "transfer": None, "quote": None, "depth_sufficient": False,
              "net_ok": False, "suspect": False}
    res = {"status": "UNAVAILABLE", "reason": None, "reasons_all": [],
           "checks": checks, "buy_vwap": None, "sell_vwap": None,
           "buy_slip_pct": None, "sell_slip_pct": None, "gross_vwap_pct": None,
           "net_pct": None, "net_after_transfer_pct": None,
           "buy_age_s": None, "sell_age_s": None, "opp_age_s": None,
           "ts_source": "recv_fallback", "suspect": False, "transfer_cost": "UNAVAILABLE"}
    def fail(status, reason):
        res["status"] = status
        res["reason"] = reason
        res["reasons_all"].append(reason)
        return res
    # گیت فاز ۲ — بدون L2 معتبر هرگز WOULD_TRADE
    if not l2:
        checks["l2_both_sides"] = False
        return fail("UNVERIFIED", "UNVERIFIED(tob_only)")
    checks["l2_both_sides"] = True
    # گیت فاز ۳ — تازگی هر دو سمت (recv-fallback برچسب‌گذاری می‌شود)
    st_b, age_b = classify_book_age(l2.get("recv_ts"), now)
    st_s, age_s = st_b, age_b          # دو کتاب در یک recv گرفته شده‌اند
    res["buy_age_s"], res["sell_age_s"] = age_b, age_s
    res["opp_age_s"] = max(a for a in (age_b, age_s) if a is not None) if age_b is not None else None
    if st_b == "INVALID_TIMESTAMP" or st_s == "INVALID_TIMESTAMP":
        return fail("INVALID_TIMESTAMP", "INVALID_TIMESTAMP(book_age)")
    if st_b == "STALE" or st_s == "STALE":
        return fail("STALE", f"STALE(book_age>{cfg['MAX_BOOK_AGE_SECONDS']}s)")
    if st_b == "UNAVAILABLE":
        return fail("UNAVAILABLE", "UNAVAILABLE(no_book_timestamp)")
    checks["fresh"] = True
    # گیت فاز ۲ — VWAP عمق واقعی برای $100 در هر دو سمت
    nb = cfg["NOTIONAL_USDT"]
    bv, bf, bs = vwap_fill(l2.get("asks_buy_venue"), nb)
    sv, sf, ss = vwap_fill(l2.get("bids_sell_venue"), nb)
    res["buy_vwap"], res["sell_vwap"] = bv, sv
    res["buy_slip_pct"], res["sell_slip_pct"] = bs, ss
    if not (bf and sf and bv and sv):
        checks["depth_sufficient"] = False
        return fail("THIN_BOOK", "THIN_BOOK(depth<$%d)" % int(nb))
    checks["depth_sufficient"] = True
    gross = (sv / bv - 1.0) * 100.0
    res["gross_vwap_pct"] = round(gross, 4)
    # گیت فاز ۶ — پرچم SUSPECT بلافاصله بعد از محاسبهٔ gross ثبت می‌شود تا هر
    # خروجیِ gross>3% آن را حمل کند (حذف خودکار نیست؛ بررسی سخت‌گیرانه‌تر است)
    if gross > cfg["SUSPICIOUS_GROSS_SPREAD_PCT"]:
        res["suspect"] = True
        checks["suspect"] = True
    # گیت فاز ۵ — هویت + انتقال
    idt = identity_and_transfer_check(cand.get("base"), l2.get("buy_sym"), l2.get("sell_sym"),
                                      l2.get("buy_ex"), l2.get("sell_ex"), cache)
    checks["quote"] = idt["quote"]
    checks["identity"] = idt["identity"]
    checks["transfer"] = idt["transfer"]
    res["transfer_cost"] = idt["transfer_cost"]
    res["identity_detail"] = idt
    if idt["identity"] == "SYMBOL_MISMATCH":
        return fail("SYMBOL_MISMATCH", "SYMBOL_MISMATCH(" + ";".join(idt["detail"]) + ")")
    if idt["transfer"] == "TRANSFER_BLOCKED":
        return fail("TRANSFER_BLOCKED", "TRANSFER_BLOCKED(" + ";".join(idt["detail"]) + ")")
    # سود خالصِ قابل‌اندازه‌گیری (taker×2؛ slippage داخل VWAP؛ انتقال حدس زده نمی‌شود)
    net = measurable_net_pct(bv, sv)
    res["net_pct"] = round(net, 4) if net is not None else None
    if net is None or net < cfg["NET_MIN_PCT"]:
        checks["net_ok"] = False
        return fail("NET_BELOW_MIN", f"NET_BELOW_MIN(net={net})")
    checks["net_ok"] = True
    # حکم نهایی — همهٔ گیت‌ها باید PASS باشند (نبود اطلاعات = تأیید نیست)
    if checks["identity"] != "VERIFIED":
        return fail("UNAVAILABLE", "UNAVAILABLE(identity_unproven)")
    if checks["transfer"] != "OPEN":
        return fail("UNAVAILABLE", "UNAVAILABLE(transfer_unproven)")
    res["status"] = "WOULD_TRADE"
    res["reason"] = "SUSPECT_PASS_ALL_GATES" if res["suspect"] else "ALL_GATES_PASS"
    return res

def status_is_hunt_ready(status):
    return status == "WOULD_TRADE"
