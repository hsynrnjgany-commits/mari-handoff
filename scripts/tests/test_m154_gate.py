#!/usr/bin/env python3
"""M154 ARBITRAGE REALITY GATE — hostile-fixture tests (PAPER ONLY).
هر گیت با دادهٔ خصمانه آزمون می‌شود؛ هیچ شبکه‌ای در کار نیست."""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "scripts", "m154_arb_gate"))
import gate  # noqa: E402
from gate import (CONFIG, Opportunity, classify_freshness, dedup_key,
                  market_quality, simulate_execution, spread_tag,
                  validate_opportunity, vwap_fill)  # noqa: E402

NOW = datetime(2026, 10, 31, 12, 0, 0, tzinfo=timezone.utc)


def mkl2(px=100.0, depth_usdt=500.0, tick=0.0001):
    """دفتر سنتتیک: 10 سطح با عمق total=depth_usdt."""
    lvls, remaining = [], depth_usdt / 10
    for i in range(10):
        p = px * (1 + tick * i)
        lvls.append([p, remaining / p])
    return lvls


def full_op(**kw):
    """فرصتی که هر ۹ شرطش برقرار است (تنها مسیر VERIFIED_EXECUTABLE)."""
    base = dict(
        base="X", buy_ex="a", sell_ex="b", direction="ARB:LONG@a/SELL@b",
        gross_pct=0.5, data_ts=NOW - timedelta(seconds=1), decision_ts=NOW,
        clock_skew_known=True,
        l2_buy=mkl2(px=100.0), l2_sell=mkl2(px=100.6),
        contract_address="0xabc", network="ERC20",
        deposit_withdraw_ok=True, transfer_cost_pct=0.1,
        quote_currency="USDT",
    )
    base.update(kw)
    return Opportunity(**base)


# ---------- G1 Freshness ----------
def test_t1_fresh_under_3s():
    assert classify_freshness(NOW - timedelta(seconds=2.9), NOW) == "FRESH"

def test_t1_stale_over_3s():
    assert classify_freshness(NOW - timedelta(seconds=3.1), NOW) == "STALE"

def test_t1_invalid_timestamp():
    assert classify_freshness("not-a-time", NOW) == "INVALID"
    assert classify_freshness(None, NOW) == "UNAVAILABLE"

def test_t1_unknown_clock_skew_is_invalid():
    assert classify_freshness(NOW - timedelta(seconds=1), NOW,
                              clock_skew_known=False) == "INVALID"

def test_t1_future_data_invalid():
    assert classify_freshness(NOW + timedelta(seconds=10), NOW) == "INVALID"

def test_t1_threshold_configurable():
    old = CONFIG["FRESH_MAX_S"]
    try:
        CONFIG["FRESH_MAX_S"] = 5.0
        assert classify_freshness(NOW - timedelta(seconds=4), NOW) == "FRESH"
        CONFIG["FRESH_MAX_S"] = 2.0
        assert classify_freshness(NOW - timedelta(seconds=4), NOW) == "STALE"
    finally:
        CONFIG["FRESH_MAX_S"] = old


# ---------- G2 Suspicious Spread ----------
def test_t2_spread_tags():
    assert spread_tag(2.9) == "NORMAL"
    assert spread_tag(3.0) == "NORMAL"      # «بالاتر از ۳٪»
    assert spread_tag(3.01) == "SUSPICIOUS"
    assert spread_tag(-1) == "INVALID"
    assert spread_tag(None) == "UNAVAILABLE"
    assert spread_tag(float("inf")) == "INVALID"


# ---------- G3 Nine-condition validation ----------
def test_t3_all_pass_verifies():
    v = validate_opportunity(full_op())
    assert v["verdict"] == "VERIFIED_EXECUTABLE", v

def test_t3_each_missing_check_blocks():
    mutations = {
        "freshness": dict(data_ts=NOW - timedelta(seconds=10)),
        "l2": dict(l2_buy=None),
        "asset_identity": dict(contract_address=None),
        "transfer_status": dict(deposit_withdraw_ok=None),
        "transfer_cost": dict(transfer_cost_pct=None),  # UNKNOWN → UNVERIFIED
        "quote": dict(quote_currency="BUSD"),
    }
    for name, kw in mutations.items():
        v = validate_opportunity(full_op(**kw))
        assert v["verdict"] == "NOT_VERIFIED", (name, v)

def test_t3_suspicious_spread_flagged_not_silent():
    v = validate_opportunity(full_op(gross_pct=7.8))
    assert "gross>3%_SUSPICIOUS" in v["reasons"]


# ---------- G4 Deduplication ----------
def test_t4_same_window_same_key():
    a, b = full_op(), full_op()
    assert dedup_key(a, NOW) == dedup_key(b, NOW)

def test_t4_different_direction_or_window_different_key():
    a = full_op()
    c = full_op(direction="ARB:LONG@b/SELL@a")
    assert dedup_key(a, NOW) != dedup_key(c, NOW)
    later = NOW + timedelta(minutes=45)   # پنجرهٔ ۳۰ دقیقه‌ای بعدی
    assert dedup_key(a, NOW) != dedup_key(a, later)

def test_t4_identity_changes_key():
    a = full_op()
    b = full_op(contract_address="0xdifferent")
    assert dedup_key(a, NOW) != dedup_key(b, NOW)


# ---------- G5 Execution Simulation ----------
def test_t5_two_side_complete():
    r = simulate_execution(full_op())
    assert r["two_side_complete"] and r["verdict"] == "EXECUTABLE_PAPER"
    assert r["net_pct"] > 0
    assert abs(r["net_usdt"] - r["net_pct"]) < 1e-9  # n=$100 → 1:1

def test_t5_second_side_fail_is_incomplete():
    r = simulate_execution(full_op(), second_side_fail=True)
    assert r["verdict"] == "INCOMPLETE_TRIP"
    assert r["one_side_failure"] == "SELL_SIDE_FAIL"
    assert not r["two_side_complete"]

def test_t5_missing_l2_not_executable():
    r = simulate_execution(full_op(l2_sell=None))
    assert r["verdict"] == "NOT_EXECUTABLE"
    assert r["one_side_failure"] == "L2_MISSING"

def test_t5_price_move_flips_net():
    """حرکت زیان‌بار adverse: خرید گران‌تر + فروش ارزان‌تر → خالص حتماً بدتر."""
    op = full_op()
    base = simulate_execution(op)
    moved = simulate_execution(op, price_move_pct=0.25)
    assert moved["net_pct"] < base["net_pct"]
    assert moved["verdict"] == "NET_NEGATIVE"  # لبهٔ کوچک با حرکت می‌میرد

def test_t5_insufficient_depth_fails():
    thin = mkl2(depth_usdt=50.0)                # < $100 سایز فرضی
    v, ok = vwap_fill(thin, 100.0)
    assert ok is False and v is None

def test_t5_slippage_measured():
    r = simulate_execution(full_op(l2_buy=mkl2(tick=0.001)))
    assert r["slippage_buy_pct"] is not None and r["slippage_buy_pct"] > 0


# ---------- G6 Market Quality ----------
def test_t6_quality_buckets():
    assert market_quality(full_op()) == "LIQUID"
    assert market_quality(full_op(contract_address=None)) == "UNIDENTIFIED_TOKEN"
    assert market_quality(full_op(deposit_withdraw_ok=False)) == "TRANSFER_RESTRICTED"
    assert market_quality(full_op(l2_buy=mkl2(depth_usdt=40.0))) == "THIN_BOOK"
