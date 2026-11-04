#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M155 PHASE 8 — ۲۰ تست خصمانهٔ مأموریت + کنترل مثبت + گارد رگرسیون
==================================================================
* همه با دادهٔ کاملاً مصنوعی — بدون شبکه (پروب‌ها از کش ساختگی)، بدون سفارش.
* هیچ تستی صرفاً به علت اجرای موفق کد PASS نمی‌شود؛ «خروجی مورد انتظار»
  (status و reason دقیق) مستقلاً assert می‌شود.
* اجرا: python3 tests/test_m155_arb_gate.py   (exit=0 فقط اگر همه PASS)
"""
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/home/z/my-project/scripts/m155_ab_upgrade")
import arb_reality_gate as g          # noqa: E402

PT = "/home/z/my-project/data/paper-trades.json"
SWEEP = "/home/z/my-project/scripts/mari_hunt01/hunt_sweep.py"
NOW = datetime(2026, 10, 31, 3, 0, 0, tzinfo=timezone.utc)

RESULTS = []


def check(name, fn):
    try:
        fn()
        RESULTS.append((name, "PASS", ""))
        print(f"PASS  {name}")
    except AssertionError as e:
        RESULTS.append((name, "FAIL", str(e)))
        print(f"FAIL  {name} — {e}")
    except Exception as e:
        RESULTS.append((name, "ERROR", f"{type(e).__name__}: {e}"))
        print(f"ERROR {name} — {type(e).__name__}: {e}")


# ─────────── دادهٔ ساختگی مشترک ───────────
def full_probes(contract="0xAAA", fee=0.5, buy_chains=None, sell_chains=None):
    """پروب کاملِ قابل‌تأیید برای kucoin (خرید) و gate (فروش) — بدون شبکه."""
    bch = buy_chains or {"erc20": {"withdraw": True, "deposit": True}}
    sch = sell_chains or {"erc20": {"withdraw": True, "deposit": True}}
    return {
        ("kucoin", "ABC"): {"status": "VERIFIED", "contract": contract, "chains": bch,
                            "min_withdrawal": 2.0, "withdraw_fee": fee,
                            "transfer_restrictions": None, "source": "fake"},
        ("gate", "ABC"): {"status": "VERIFIED", "contract": contract, "chains": sch,
                          "min_withdrawal": 2.0, "withdraw_fee": fee,
                          "transfer_restrictions": None, "source": "fake"},
    }


def l2(asks=None, bids=None, ex_ts=1.0, recv=True):
    rec = {"asks_buy_venue": asks if asks is not None else [[100.0, 2.0]],
           "bids_sell_venue": bids if bids is not None else [[101.6, 2.0]]}
    if ex_ts is not None:
        rec["exchange_ts_buy"] = rec["exchange_ts_sell"] = (
            NOW - timedelta(seconds=ex_ts)).isoformat()
    if recv:
        rec["recv_ts"] = (NOW - timedelta(seconds=0.5)).isoformat()
    return rec


def cand(l2rec="DEFAULT", base="ABC", buy="kucoin", sell="gate"):
    # لایه‌سنتینل: l2rec=None یعنی واقعاً بدون L2 (تست ۱)؛ "DEFAULT" یعنی L2 کامل ساختگی
    return {"base": base, "buy_ex": buy, "sell_ex": sell,
            "buy_sym": f"{base}-USDT", "sell_sym": f"{base}USDT",
            "cycle_ts": NOW.isoformat(), "l2": l2() if l2rec == "DEFAULT" else l2rec}


def ev(c, **kw):
    return g.evaluate_opportunity(c, now=NOW, cache=kw.pop("cache", full_probes()), **kw)


# ── T00: کنترل مثبت — با شواهد کامل، گیت واقعاً می‌تواند VERIFIED بدهد ──
def t00():
    r = ev(cand())
    assert r["status"] == "VERIFIED_EXECUTABLE", (r["status"], r["reason"])
    assert r["reason"] == "all_gates_pass"
    assert r["evidence"]["provable_net_pct"] is not None and r["evidence"]["provable_net_pct"] > 0.15
    assert r["evidence"]["ts_source"] == "exchange" and not r["evidence"]["recv_fallback"]


# ── ۱: L2 مفقود → UNVERIFIED (هرگز VERIFIED/WOULD_TRADE نیست) ──
def t01():
    r = ev(cand(l2rec=None))
    assert r["status"] == "UNVERIFIED" and r["reason"] == "tob_only", (r["status"], r["reason"])
    assert r["status"] != "VERIFIED_EXECUTABLE" and r["status"] != "WOULD_TRADE"


# ── ۲: L2 منقضی → STALE؛ مرز مستند: دقیقاً 10s هنوز FRESH ──
def t02():
    r = ev(cand(l2rec=l2(ex_ts=11.0)))
    assert r["status"] == "STALE" and r["reason"] == "stale_book", (r["status"], r["reason"])
    assert abs(r["evidence"]["ages"]["buy"] - 11.0) < 1e-6
    for age, want in ((9.9, "FRESH"), (10.0, "FRESH"), (10.1, "STALE")):
        s, _ = g.classify_book_age(NOW - timedelta(seconds=age), NOW)
        assert s == want, (age, s)
    rb = ev(cand(l2rec=l2(ex_ts=10.0)))           # مرز دقیقاً MAX → مسیر کامل
    assert rb["status"] == "VERIFIED_EXECUTABLE", (rb["status"], rb["reason"])


# ── ۳: timestamp آینده → INVALID ──
def t03():
    r = ev(cand(l2rec=l2(ex_ts=-30.0)))           # NOW+30s
    assert r["status"] == "INVALID" and r["reason"] == "invalid_or_future_timestamp", r["reason"]


# ── ۴: timestamp مفقود → UNAVAILABLE ──
def t04():
    r = ev(cand(l2rec=l2(ex_ts=None, recv=False)))
    assert r["status"] == "UNAVAILABLE" and r["reason"] == "no_book_timestamp", r["reason"]


# ── ۵: عمق ناکافی (<$100) → REJECTED ──
def t05():
    r = ev(cand(l2rec=l2(asks=[[100.0, 0.5]])))   # فقط $50
    assert r["status"] == "REJECTED" and r["reason"] == "insufficient_depth", r["reason"]


# ── ۶: VWAP نامعتبر (قیمت صفر) → REJECTED ──
def t06():
    r = ev(cand(l2rec=l2(asks=[[0.0, 200.0]])))
    assert r["status"] == "REJECTED" and r["reason"] == "invalid_vwap", r["reason"]


# ── ۷: قرارداد متفاوت → REJECTED/SYMBOL_MISMATCH ──
def t07():
    c = full_probes()
    c[("gate", "ABC")] = dict(c[("gate", "ABC")], contract="0xBBB")
    r = ev(cand(), cache=c)
    assert r["status"] == "REJECTED" and r["reason"] == "symbol_mismatch", r["reason"]
    assert any("contract_address_differs" in d for d in (r["evidence"]["probe_sources"] or []))


# ── ۸: شبکه متفاوت → REJECTED/NO_COMMON_NETWORK ──
def t08():
    c = full_probes(sell_chains={"bep20": {"withdraw": True, "deposit": True}})
    r = ev(cand(), cache=c)
    assert r["status"] == "REJECTED" and r["reason"] == "no_common_network", r["reason"]


# ── ۹: برداشت غیرفعال (از صرافی خرید — جهت انتقال) → REJECTED/TRANSFER_BLOCKED ──
def t09():
    c = full_probes(buy_chains={"erc20": {"withdraw": False, "deposit": True}})
    r = ev(cand(), cache=c)
    assert r["status"] == "REJECTED" and r["reason"] == "transfer_blocked", r["reason"]
    assert any("withdraw" in d for d in (r["evidence"]["probe_sources"] or []))


# ── ۱۰: واریز غیرفعال → REJECTED/TRANSFER_BLOCKED ──
def t10():
    c = full_probes(sell_chains={"erc20": {"withdraw": True, "deposit": False}})
    r = ev(cand(), cache=c)
    assert r["status"] == "REJECTED" and r["reason"] == "transfer_blocked", r["reason"]
    assert any("deposit" in d for d in (r["evidence"]["probe_sources"] or []))


# ── ۱۱: هزینهٔ انتقال UNKNOWN → UNAVAILABLE (هرگز صفر فرض نمی‌شود) ──
def t11():
    c = full_probes(fee=None)
    r = ev(cand(), cache=c)
    assert r["status"] == "UNAVAILABLE" and r["reason"] == "transfer_unverified", r["reason"]
    assert r["evidence"]["provable_net_pct"] is None, "سود قابل‌اثبات نباید با هزینهٔ ناشناخته حساب شود"
    assert any("not_assumed_zero" in x for x in r["evidence"]["checks"])


# ── ۱۲: اسپرد >۳٪ → SUSPICIOUS (توقف برای بررسی مستقل، نه تأیید) ──
def t12():
    r = ev(cand(l2rec=l2(bids=[[103.5, 2.0]])))   # gross=3.5٪
    assert r["status"] == "SUSPICIOUS" and r["reason"] == "pending_independent_review", r["reason"]
    assert r["suspect"] is True and r["evidence"]["phantom"] is False
    c = full_probes(sell_chains={"erc20": {"withdraw": True, "deposit": False}})
    r2 = ev(cand(l2rec=l2(bids=[[103.5, 2.0]])), cache=c)
    assert r2["suspect"] is True and r2["status"] == "REJECTED" and r2["reason"] == "transfer_blocked"


# ── ۱۳: شکست پای دوم → INCOMPLETE_TRIP ──
def t13():
    r = ev(cand(), second_leg="FAILED")
    assert r["status"] == "INCOMPLETE_TRIP" and r["reason"] == "second_leg_failed", r["reason"]


# ── ۱۴: حرکت نامساعد قیمت → REJECTED/NET_BELOW_MIN ──
def t14():
    r = ev(cand(l2rec=l2(bids=[[99.0, 10.0]])))   # سمت فروش زیر خرید می‌افتد
    assert r["status"] == "REJECTED" and r["reason"] == "net_below_min_without_transfer", r["reason"]


# ── ۱۵: تکرار سیگنال → RAW=2، UNIQUE=1 ──
def t15():
    ts = NOW.replace(minute=5, second=0, microsecond=0)
    rec = ["ABC", "USDT", "UNPROVEN", "kucoin", "gate", "LONG@kucoin->SELL@gate", ts]
    d = g.dedup_scan([rec, list(rec)])
    assert d["raw"] == 2 and d["unique"] == 1 and d["duplicates"] == 1, d
    assert d["uniques"][0]["seen_count"] == 2
    ts2 = ts + timedelta(minutes=31)               # پنجرهٔ بعدی → یکتا
    d2 = g.dedup_scan([rec, ["ABC", "USDT", "UNPROVEN", "kucoin", "gate",
                             "LONG@kucoin->SELL@gate", ts2]])
    assert d2["unique"] == 2, d2


# ── ۱۶: اختلاف ساعت صرافی‌ها (>5s) → INVALID ──
def t16():
    lr = l2()
    lr["exchange_ts_buy"] = (NOW - timedelta(seconds=1)).isoformat()
    lr["exchange_ts_sell"] = (NOW - timedelta(seconds=20)).isoformat()
    r = ev(cand(l2rec=lr))
    assert r["status"] == "INVALID" and r["reason"] == "clock_skew_between_venues", r["reason"]


# ── ۱۷: حجم غیرقابل‌اجرا (مجموع <$100) → REJECTED ──
def t17():
    r = ev(cand(l2rec=l2(asks=[[100.0, 0.4], [100.5, 0.5]])))   # $90.25
    assert r["status"] == "REJECTED" and r["reason"] == "insufficient_depth", r["reason"]


# ── ۱۸: قیمت فانتوم (gross>100٪) → SUSPICIOUS + پرچم phantom، هرگز VERIFIED ──
def t18():
    r = ev(cand(l2rec=l2(bids=[[250.0, 2.0]])))
    assert r["status"] == "SUSPICIOUS" and r["reason"] == "pending_independent_review", r["reason"]
    assert r["evidence"]["phantom"] is True and r["suspect"] is True
    assert r["status"] != "VERIFIED_EXECUTABLE"


# ── ۱۹: قطع منبع داده → UNAVAILABLE ──
def t19():
    r = ev(cand(), source_ok=False)
    assert r["status"] == "UNAVAILABLE" and r["reason"] == "source_unavailable", r["reason"]


# ── ۲۰: دادهٔ ناقص → INVALID ──
def t20():
    bad = {"base": "ABC", "buy_ex": "kucoin", "sell_ex": "gate",
           "buy_sym": "ABC-USDT", "l2": l2()}       # sell_sym غایب
    r = ev(bad)
    assert r["status"] == "INVALID" and r["reason"] == "malformed_input", (r["status"], r["reason"])


# ── T21: گارد رگرسیون — فایل‌های محافظت‌شده دست‌نخورده ──
def t21():
    def sha(p):
        return hashlib.sha256(open(p, "rb").read()).hexdigest()
    pt_before, sw_before = sha(PT), sha(SWEEP)
    d = json.load(open(PT))
    assert d.get("paused") is True and len(d.get("trades", [])) == 74
    g.evaluate_opportunity(cand(), now=NOW, cache=full_probes())
    g.dedup_scan([["X", "USDT", "UNPROVEN", "kucoin", "gate", "d", NOW]])
    assert sha(PT) == pt_before, "paper-trades.json تغییر کرده!"
    assert sha(SWEEP) == sw_before, "hunt_sweep.py تغییر کرده!"
    print(f"      sha256(paper-trades.json)={pt_before[:16]}… sha256(hunt_sweep.py)={sw_before[:16]}… ✓")


if __name__ == "__main__":
    check("T00 کنترل مثبت: شواهد کامل → VERIFIED_EXECUTABLE", t00)
    check("T01 L2 مفقود → UNVERIFIED (بدون WOULD_TRADE)", t01)
    check("T02 L2 منقضی → STALE + مرز 10s + گذر کامل مرز", t02)
    check("T03 timestamp آینده → INVALID", t03)
    check("T04 timestamp مفقود → UNAVAILABLE", t04)
    check("T05 عمق ناکافی → REJECTED/insufficient_depth", t05)
    check("T06 VWAP نامعتبر → REJECTED/invalid_vwap", t06)
    check("T07 قرارداد متفاوت → REJECTED/symbol_mismatch", t07)
    check("T08 شبکه متفاوت → REJECTED/no_common_network", t08)
    check("T09 برداشت غیرفعال → REJECTED/transfer_blocked", t09)
    check("T10 واریز غیرفعال → REJECTED/transfer_blocked", t10)
    check("T11 هزینهٔ انتقال UNKNOWN → UNAVAILABLE (صفر فرض نمی‌شود)", t11)
    check("T12 اسپرد >3٪ → SUSPICIOUS (و با شکست همزمان، REJECTED برچسب‌دار)", t12)
    check("T13 شکست پای دوم → INCOMPLETE_TRIP", t13)
    check("T14 حرکت نامساعد → REJECTED/net_below_min", t14)
    check("T15 تکرار سیگنال → RAW=2/UNIQUE=1 + پنجرهٔ ۳۰ دقیقه", t15)
    check("T16 اختلاف ساعت صرافی‌ها → INVALID/clock_skew", t16)
    check("T17 حجم غیرقابل‌اجرا → REJECTED/insufficient_depth", t17)
    check("T18 قیمت فانتوم → SUSPICIOUS + phantom (هرگز VERIFIED)", t18)
    check("T19 قطع منبع داده → UNAVAILABLE/source_unavailable", t19)
    check("T20 دادهٔ ناقص → INVALID/malformed_input", t20)
    check("T21 گارد رگرسیون: فایل‌های محافظت‌شده دست‌نخورده", t21)
    p = sum(1 for _, s, _ in RESULTS if s == "PASS")
    print(f"\nSUMMARY: {p}/{len(RESULTS)} PASS")
    sys.exit(0 if p == len(RESULTS) else 1)
