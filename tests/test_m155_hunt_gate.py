#!/usr/bin/env python3
"""
M155 — ۱۰ تست الزامی مأموریت (همه با دادهٔ ساختگی، بدون شبکه، بدون سفارش)
==========================================================================
اجرا: python3 tests/test_m155_hunt_gate.py
تست ۱۰: SHA-256 فایل حفاظت‌شدهٔ data/paper-trades.json قبل/بعد باید یکسان باشد.
مرز تازگی (مستند): age == MAX_BOOK_AGE_SECONDS → هنوز FRESH است؛ فقط age > MAX → STALE.
"""
import hashlib
import json
import math
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/home/z/my-project/scripts/mari_hunt01")
import hunt_gate_v2 as gate          # noqa: E402
import hunt_report_v2 as rpt        # noqa: E402

PT = "/home/z/my-project/data/paper-trades.json"
NOW = datetime(2026, 10, 31, 2, 0, 0, tzinfo=timezone.utc)

def iso(dt):
    return dt.isoformat()

def good_probes(contract="0xAAA", sell_contract=None, deposit=True, withdraw=True):
    """پروب ساختگی هر دو صرافی (kucoin=خرید، gate=فروش) — بدون شبکه."""
    return {
        ("kucoin", "ABC"): {"status": "VERIFIED", "contract": contract,
                            "chains": {"erc20": {"withdraw": withdraw, "deposit": True}},
                            "fee_hint": "1.5", "source": "fake"},
        ("gate", "ABC"): {"status": "VERIFIED", "contract": sell_contract or contract,
                          "chains": {"erc20": {"withdraw": True, "deposit": deposit}},
                          "fee_hint": None, "source": "fake"},
    }

def l2_rec(asks=None, bids=None, recv=None, buy_sym="ABC-USDT", sell_sym="ABCUSDT"):
    return {"base": "ABC", "buy_ex": "kucoin", "buy_sym": buy_sym,
            "sell_ex": "gate", "sell_sym": sell_sym,
            "recv_ts": iso(recv or (NOW - timedelta(seconds=1))),
            "asks_buy_venue": asks or [[100.0, 2.0]],
            "bids_sell_venue": bids or [[101.0, 2.0]]}

def cand():
    return {"base": "ABC", "buy_ex": "kucoin", "sell_ex": "gate",
            "buy_sym": "ABC-USDT", "sell_sym": "ABCUSDT"}

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

# ── تست ۱: فقط TOB → UNVERIFIED و هرگز WOULD_TRADE ──────────────────────────
def t01():
    r = gate.evaluate_opportunity(cand(), None, now=NOW, cache=good_probes())
    assert r["status"] == "UNVERIFIED", r["status"]
    assert r["status"] != "WOULD_TRADE"
    assert r["reason"] == "UNVERIFIED(tob_only)"

# ── تست ۲: VWAP واقعی L2 برای 100 USDT + سود خالص ────────────────────────────
def t02():
    v, filled, slip = gate.vwap_fill([[100.0, 1.0], [101.0, 10.0]], 100.0)
    assert filled and math.isclose(v, 100.0, abs_tol=1e-12) and slip == 0.0
    v2, filled2, _ = gate.vwap_fill([[100.0, 0.5], [101.0, 1.0]], 100.0)
    assert filled2 and math.isclose(v2, 10100 / 100.5, rel_tol=1e-12), v2
    v3, filled3, _ = gate.vwap_fill([[100.0, 0.1]], 100.0)
    assert not filled3 and v3 is None
    net = gate.measurable_net_pct(100.0, 102.0)
    assert net is not None and math.isclose(net, 1.8, abs_tol=1e-9), net

# ── تست ۳: تازگی ۵/۱۰/۱۱ ثانیه + مرز مستند ───────────────────────────────────
def t03():
    s5, a5 = gate.classify_book_age(NOW - timedelta(seconds=5), NOW)
    s10, a10 = gate.classify_book_age(NOW - timedelta(seconds=10), NOW)
    s11, a11 = gate.classify_book_age(NOW - timedelta(seconds=11), NOW)
    assert s5 == "FRESH" and abs(a5 - 5.0) < 1e-6
    assert s10 == "FRESH", "مرز: سن دقیقاً برابر MAX هنوز FRESH است (فقط بیشتر از MAX → STALE)"
    assert s11 == "STALE" and abs(a11 - 11.0) < 1e-6
    sf, _ = gate.classify_book_age(NOW + timedelta(seconds=30), NOW)
    assert sf == "INVALID_TIMESTAMP", "timestamp آینده‌دار"
    sg, _ = gate.classify_book_age("not-a-date", NOW)
    assert sg == "INVALID_TIMESTAMP"
    sn, _ = gate.classify_book_age(None, NOW)
    assert sn == "UNAVAILABLE"

# ── تست ۴: تکرار در سه چرخه → seen_count=3 و آخرین چرخه ─────────────────────
def t04():
    tmp = tempfile.mktemp(suffix=".jsonl")
    try:
        r1, d1 = gate.update_index(tmp, "ABC", "kucoin", "gate", "c1")
        r2, d2 = gate.update_index(tmp, "ABC", "kucoin", "gate", "c2")
        r3, d3 = gate.update_index(tmp, "ABC", "kucoin", "gate", "c3")
        assert not d1 and d2 and d3
        assert r3["seen_count"] == 3
        assert r3["first_cycle_id"] == "c1" and r3["last_cycle_id"] == "c3"
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)

# ── تست ۵: نماد یکسان، قرارداد متفاوت → SYMBOL_MISMATCH ─────────────────────
def t05():
    r = gate.evaluate_opportunity(cand(), l2_rec(), now=NOW,
                                  cache=good_probes(contract="0xAAA", sell_contract="0xBBB"))
    assert r["status"] == "SYMBOL_MISMATCH", r["status"]
    assert "contract_address_differs" in r["reason"]

# ── تست ۶: withdraw یا deposit بسته → TRANSFER_BLOCKED ──────────────────────
def t06():
    r = gate.evaluate_opportunity(cand(), l2_rec(), now=NOW,
                                  cache=good_probes(deposit=False))
    assert r["status"] == "TRANSFER_BLOCKED", r["status"]
    r2 = gate.evaluate_opportunity(cand(), l2_rec(), now=NOW,
                                   cache=good_probes(withdraw=False))
    assert r2["status"] == "TRANSFER_BLOCKED", r2["status"]

# ── تست ۷: USDT در برابر USDC → رد ──────────────────────────────────────────
def t07():
    r = gate.evaluate_opportunity(cand(), l2_rec(sell_sym="ABCUSDC"), now=NOW,
                                  cache=good_probes())
    assert r["status"] == "SYMBOL_MISMATCH", r["status"]
    assert "quote_currency_mismatch" in r["reason"]

# ── تست ۸: اسپرد مشکوک 3.5٪ → SUSPECT (حذف خودکار نیست) ────────────────────
def t08():
    r = gate.evaluate_opportunity(cand(), l2_rec(bids=[[103.5, 2.0]]),
                                  now=NOW, cache=good_probes())
    assert r["suspect"] is True and r["status"] == "WOULD_TRADE", (r["status"], r["suspect"])
    assert r["reason"] == "SUSPECT_PASS_ALL_GATES"
    r2 = gate.evaluate_opportunity(cand(), l2_rec(bids=[[103.5, 2.0]]),
                                   now=NOW, cache=good_probes(deposit=False))
    assert r2["suspect"] is True and r2["status"] == "TRANSFER_BLOCKED", r2["status"]

# ── تست ۹: گزارش — فقط ۱۰ فرصت برتر ─────────────────────────────────────────
def t09():
    opps = []
    for i in range(5):
        opps.append({"base": f"W{i}", "buy_ex": "kucoin", "sell_ex": "gate",
                     "gross_pct": 1.0, "net_pct": 0.2 + i * 0.1, "buy_vwap": 1.0,
                     "sell_vwap": 1.01, "buy_age_s": 1, "sell_age_s": 1,
                     "seen_count": 1, "gate_status": "WOULD_TRADE"})
    for i in range(10):
        opps.append({"base": f"S{i}", "buy_ex": "kucoin", "sell_ex": "gate",
                     "gross_pct": 0.5 + i * 0.01, "net_pct": None, "buy_vwap": 1.0,
                     "sell_vwap": 1.005, "buy_age_s": 1, "sell_age_s": 1,
                     "seen_count": 2, "gate_status": "UNAVAILABLE"})
    txt, n = rpt.render_top(opps, 10)
    assert n == 10, n
    lines = txt.strip().splitlines()
    assert len(lines) == 11, len(lines)      # ۱ سرخط + ۱۰ ردیف
    assert "W4" in lines[1], "بالاترین netِ WOULD_TRADE باید اول باشد"

# ── تست ۱۰: فایل حفاظت‌شده — SHA قبل/بعد یکسان ───────────────────────────────
def t10():
    def sha():
        return hashlib.sha256(open(PT, "rb").read()).hexdigest()
    before = sha()
    d = json.load(open(PT))
    assert d.get("paused") is True and len(d.get("trades", [])) == 74
    tmp = tempfile.mktemp(suffix=".jsonl")
    try:
        gate.evaluate_opportunity(cand(), l2_rec(), now=NOW, cache=good_probes())
        gate.update_index(tmp, "X", "kucoin", "gate", "cx")
        opps = [{"base": "A", "gate_status": "WOULD_TRADE", "net_pct": 0.2}]
        rpt.render_top(opps, 10)
        rpt.build_report(cycle_rows=[], decisions=[], rejects=[], index=[],
                         last_cycle={}, errlog_lines=[], sendlog=[], now=NOW)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    after = sha()
    assert before == after, "فایل حفاظت‌شده تغییر کرده!"
    print(f"      sha256(paper-trades.json) = {before[:16]}… (قبل=بعد ✓)")

if __name__ == "__main__":
    check("T01 TOB-only → UNVERIFIED و بدون WOULD_TRADE", t01)
    check("T02 VWAP عمق واقعی $100 + سود خالص", t02)
    check("T03 تازگی 5/10/11s + مرز + INVALID/UNAVAILABLE", t03)
    check("T04 تکرار سه چرخه → seen_count=3", t04)
    check("T05 قرارداد متفاوت → SYMBOL_MISMATCH", t05)
    check("T06 withdraw/deposit بسته → TRANSFER_BLOCKED", t06)
    check("T07 USDT مقابل USDC → رد", t07)
    check("T08 gross 3.5% → SUSPECT (با PASS کامل → WOULD_TRADE برچسب‌دار)", t08)
    check("T09 گزارش فقط ۱۰ فرصت برتر", t09)
    check("T10 SHA-256 فایل حفاظت‌شده قبل/بعد یکسان", t10)
    p = sum(1 for _, s, _ in RESULTS if s == "PASS")
    print(f"\nSUMMARY: {p}/{len(RESULTS)} PASS")
    sys.exit(0 if p == len(RESULTS) else 1)
