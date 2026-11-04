#!/usr/bin/env python3
"""
MARI-MULTIMARKET-HUNT-01 — hunt_sweep v2 (مقاوم در برابر ریست)
===============================================================
READ-ONLY | PAPER ONLY | NO KEYS | خروجی فقط در scripts/mari_hunt01/store/
- تصمیم فقط برای آخرین چرخهٔ همین لحظه (ضد انتخاب پسینی)، idempotent
- vault-mirror.jsonl: کپی append-only بایگانی data/tick-vault (که در
  .gitignore است و با هر ریست cron-agent پاک می‌شود)
M155 ارتقا: فاز ۲ — سیگنال بدون L2 معتبر هرگز WOULD_TRADE نمی‌شود (UNVERIFIED).
مسیر L2 از گیت کامل hunt_gate_v2 می‌گذرد: تازگی≤10s، VWAP عمق $100،
هویت توکن/قرارداد/شبکه، withdraw/deposit، SUSPECT>3%، هزینهٔ انتقال حدس زده نمی‌شود.
"""
import glob
import json
import os
import statistics
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hunt_gate_v2 as gate  # noqa: E402

STORE = "scripts/mari_hunt01/store"
DECISIONS = f"{STORE}/decisions.jsonl"
CYCLES = f"{STORE}/cycles.jsonl"
REJECTS = f"{STORE}/rejects.jsonl"
MIRROR = f"{STORE}/vault-mirror.jsonl"
OPP_INDEX = f"{STORE}/opportunities_index.jsonl"
LAST = "scripts/m140_tick_vault/last_cycle.json"

FEE_TAKER = 0.001
SLIP = 0.001
BASE_COST = FEE_TAKER * 2 + SLIP
AMORT_TRANSFER_DEFAULT = 0.0005
TRANSFER_SCENARIOS = [(0.5, 5000), (1.0, 2000), (2.0, 1000), (5.0, 500)]
NET_MIN = 0.0015
SIZE = 100
STALE_TOL = 0.05
PHANTOM_GROSS = 100.0
PHANTOM_M142 = 10.0

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def load_jsonl(path):
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
    return out

def append_jsonl(path, rows):
    if not rows:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

def vwap_quote(levels, notional):
    spent = got = 0.0
    for lvl in levels or []:
        try:
            p, q = float(lvl[0]), float(lvl[1])
        except Exception:
            continue
        cost = p * q
        if spent + cost >= notional:
            got += (notional - spent) / p
            return (notional / got if got > 0 else None), True
        spent += cost
        got += q
    return (None, False)

def all_cycles():
    """آرشیو زنده + آینهٔ بقا (بدون تکرار cycle_ts)."""
    seen, out = set(), []
    for src in (load_jsonl(MIRROR), _read_archive()):
        for r in src:
            ts = r.get("cycle_ts")
            if ts and ts not in seen:
                seen.add(ts)
                out.append(r)
    out.sort(key=lambda r: r.get("cycle_ts") or "")
    return out

def _read_archive():
    recs = []
    for fp in sorted(glob.glob("data/tick-vault/snapshots-*.jsonl")):
        with open(fp, encoding="utf-8") as f:
            for line in f:
                try:
                    recs.append(json.loads(line))
                except Exception:
                    pass
    return recs

def mirror_archive():
    """چرخه‌های آرشیو زنده که در آینه نیستند → append."""
    mir_ts = {r.get("cycle_ts") for r in load_jsonl(MIRROR)}
    new = [r for r in _read_archive() if r.get("cycle_ts") not in mir_ts]
    append_jsonl(MIRROR, new)
    return len(new)

def stale_map(cycles):
    quotes = defaultdict(lambda: defaultdict(list))
    for r in cycles:
        for t in r.get("top20") or []:
            b = t.get("base")
            if not b:
                continue
            if t.get("buy_ex") and t.get("ask"):
                quotes[b][t["buy_ex"]].append(float(t["ask"]))
            if t.get("sell_ex") and t.get("bid"):
                quotes[b][t["sell_ex"]].append(float(t["bid"]))
    stale = {}
    for base, venues in quotes.items():
        if len(venues) < 2:
            continue
        med = statistics.median([p for ps in venues.values() for p in ps])
        for venue, ps in venues.items():
            dev = abs(statistics.median(ps) / med - 1) if med > 0 else 0
            if dev > STALE_TOL:
                stale[(base, venue)] = dev
    return stale

def frozen_keys(cycles, min_repeat=3):
    """FIX-FROZEN-01 (فرمان رییس 2026-11-04): کلید (base,buy_ex,sell_ex) فقط وقتی منجمد است
    که در ≥min_repeat مشاهدهٔ پشت‌سرهمِ «خودِ آن کلید»، (ask,bid) دقیقاً یکسان باشد
    (مقایسهٔ repr مثل قبل). کمتر از min_repeat مشاهده = هرگز frozen نیست.
    باگ قبلی: min_cycles فقط طول کل تاریخچه را می‌سنجید و کلید تک‌مشاهده‌ای را هم منجمد می‌زد."""
    seq = defaultdict(list)  # کلید → [(repr(ask),repr(bid)), ...] به ترتیب cycle_ts
    for r in sorted(cycles, key=lambda r: r.get("cycle_ts") or ""):
        for t in r.get("top20") or []:
            seq[(t.get("base"), t.get("buy_ex"), t.get("sell_ex"))].append(
                (repr(t.get("ask")), repr(t.get("bid"))))
    frozen = set()
    for k, quotes in seq.items():
        run = best = 1
        for i in range(1, len(quotes)):
            run = run + 1 if quotes[i] == quotes[i - 1] else 1
            best = max(best, run)
        if best >= min_repeat:
            frozen.add(k)
    return frozen

def main():
    snap = subprocess.run(
        [sys.executable, "scripts/m140_tick_vault/snapshot.py"],
        capture_output=True, text=True, timeout=170)
    if snap.returncode != 0:
        print(json.dumps({"ok": False, "stage": "snapshot", "exit": snap.returncode,
                          "stderr": snap.stderr[-400:]}, ensure_ascii=False))
        return 1
    mirrored = mirror_archive()

    cyc = json.load(open(LAST))
    decision_ts = now_iso()
    cycle_ts = cyc.get("cycle_ts", "?")
    sources = cyc.get("sources", {})
    src_ok = sum(1 for v in sources.values() if v.get("http") == 200 and v.get("rows"))
    failed = [k for k, v in sources.items() if not (v.get("http") == 200 and v.get("rows"))]

    cycles_hist = all_cycles()
    sm = stale_map(cycles_hist)
    frozen = frozen_keys(cycles_hist)
    l2map = {(l.get("base"), l.get("buy_ex"), l.get("sell_ex")): l
             for l in cyc.get("l2") or []}
    seen = {(d.get("cycle_ts"), d.get("base"), d.get("buy_ex"), d.get("sell_ex"))
            for d in load_jsonl(DECISIONS) if d.get("type") != "aggregate_reconstruction"}
    probe_cache = {}
    gate_counts = defaultdict(int)

    decisions, rejects = [], []
    cands = cyc.get("top20") or []
    for t in cands:
        base = t.get("base")
        g = float(t.get("gross_pct", 0) or 0)
        bex, sex = t.get("buy_ex"), t.get("sell_ex")
        tob_b = float(t.get("tob_buy_usdt", 0) or 0)
        tob_s = float(t.get("tob_sell_usdt", 0) or 0)
        key = (cycle_ts, base, bex, sex)
        uid = f"HUNT01-{cycle_ts[:19].replace(':','').replace('-','')}-{base}-{bex}-{sex}"
        if key in seen:
            continue
        if g > PHANTOM_GROSS:
            rejects.append({"id": uid, "base": base, "reason": "phantom>100%",
                            "gross_pct": g, "cycle_ts": cycle_ts}); continue
        if (base, bex, sex) in frozen:
            rejects.append({"id": uid, "base": base, "reason": "frozen_quote(F1)",
                            "gross_pct": g, "cycle_ts": cycle_ts}); continue
        bad = [v for (b, v) in sm if b == base and v in (bex, sex)]
        if bad:
            rejects.append({"id": uid, "base": base,
                            "reason": f"stale_venue({','.join(bad)})",
                            "gross_pct": g, "cycle_ts": cycle_ts}); continue
        if g > PHANTOM_M142 and min(tob_b, tob_s) < 1000:
            rejects.append({"id": uid, "base": base,
                            "reason": "phantom_m142(gross>10%,depth<1000)",
                            "gross_pct": g, "cycle_ts": cycle_ts}); continue
        if tob_b < SIZE or tob_s < SIZE:
            rejects.append({"id": uid, "base": base,
                            "reason": f"liquidity<${SIZE}(tob ${tob_b:.0f}/${tob_s:.0f})",
                            "gross_pct": g, "cycle_ts": cycle_ts}); continue
        l2 = l2map.get((base, bex, sex))
        if not l2:
            # ── M155 فاز ۲: بدون L2 معتبر هرگز WOULD_TRADE — فقط UNVERIFIED ──
            gate_counts["UNVERIFIED"] += 1
            decisions.append({
                "id": uid, "mission": "MARI-MULTIMARKET-HUNT-01",
                "decision_ts_utc": decision_ts, "cycle_ts": cycle_ts,
                "market": "crypto-spot", "base": base, "buy_ex": bex, "sell_ex": sex,
                "direction": f"ARB:LONG@{bex}/SELL@{sex}",
                "method": "tob_estimate", "size_usdt": SIZE,
                "buy_price": round(float(t.get("ask") or 0), 12),
                "sell_price": round(float(t.get("bid") or 0), 12),
                "gross_pct": round(g, 4),
                "gate_status": "UNVERIFIED", "gate_reason": "UNVERIFIED(tob_only)",
                "net_pct": None, "transfer_cost": "UNAVAILABLE",
                "decision": "UNVERIFIED", "status": "unverified_no_l2",
                "data_source": "m140-tickvault-v1",
                "paper_only": True, "m155": True,
            })
            continue
        # ── مسیر L2: گیت کامل M155 ──
        gv = gate.evaluate_opportunity(t, l2, cache=probe_cache)
        if gv["status"] == "THIN_BOOK":
            rejects.append({"id": uid, "base": base, "reason": "thin_book_l2",
                            "gross_pct": g, "cycle_ts": cycle_ts})
            continue
        idx_rec, duplicate = gate.update_index(
            OPP_INDEX, base, bex, sex, cycle_ts,
            payload={"status": gv["status"], "net_pct": gv["net_pct"],
                     "gross_vwap_pct": gv["gross_vwap_pct"]})
        gate_counts[gv["status"]] += 1
        dec = "WOULD_TRADE" if gv["status"] == "WOULD_TRADE" else "SKIP_NET"
        idt = gv.get("identity_detail") or {}
        gross_frac = (gv["gross_vwap_pct"] or 0) / 100.0
        scen = {f"fee{fu}$@inv{di}$": round((gross_frac - BASE_COST - fu / di) * 100, 4)
                for fu, di in TRANSFER_SCENARIOS}
        decisions.append({
            "id": uid, "mission": "MARI-MULTIMARKET-HUNT-01",
            "decision_ts_utc": decision_ts, "cycle_ts": cycle_ts,
            "market": "crypto-spot", "base": base, "buy_ex": bex, "sell_ex": sex,
            "direction": f"ARB:LONG@{bex}/SELL@{sex}",
            "method": "l2_vwap_100", "size_usdt": SIZE,
            "buy_price": round(gv["buy_vwap"], 12), "sell_price": round(gv["sell_vwap"], 12),
            "buy_vwap": round(gv["buy_vwap"], 12), "sell_vwap": round(gv["sell_vwap"], 12),
            "buy_slip_pct": round(gv["buy_slip_pct"], 4) if gv["buy_slip_pct"] is not None else None,
            "sell_slip_pct": round(gv["sell_slip_pct"], 4) if gv["sell_slip_pct"] is not None else None,
            "gross_pct": gv["gross_vwap_pct"],
            "net_pct": gv["net_pct"],
            "buy_age_s": round(gv["buy_age_s"], 2) if gv["buy_age_s"] is not None else None,
            "sell_age_s": round(gv["sell_age_s"], 2) if gv["sell_age_s"] is not None else None,
            "ts_source": gv["ts_source"],
            "suspect": gv["suspect"],
            "gate_status": gv["status"], "gate_reason": gv["reason"],
            "identity": idt.get("identity"), "transfer": idt.get("transfer"),
            "network": idt.get("network"), "quote": idt.get("quote"),
            "withdraw_buy": idt.get("withdraw_buy"), "deposit_sell": idt.get("deposit_sell"),
            "transfer_cost": gv["transfer_cost"],
            "transfer_scenarios_net_pct": scen,
            "duplicate_sighting": duplicate,
            "seen_count": idx_rec.get("seen_count"),
            "decision": dec,
            "sl_target": "N/A — سفر همزمان دوسویه",
            "invalidation": "بسته‌شدن اسپرد/افت عمق/کشف قیمت منجمد پیش از اجرا",
            "status": "closed_instant" if dec == "WOULD_TRADE" else "rejected_before_entry",
            "data_source": "m140-tickvault-v1",
            "paper_only": True, "m155": True,
            "reconstructed_from_transcript": False,
        })

    wt = [d for d in decisions if d["decision"] == "WOULD_TRADE"]
    unv = [d for d in decisions if d["decision"] == "UNVERIFIED"]
    dups = [d for d in decisions if d.get("duplicate_sighting")]
    append_jsonl(DECISIONS, decisions)
    append_jsonl(REJECTS, [r for r in rejects if not r["reason"].startswith("net<")])

    # ── COVERAGE-01 (فرمان رییس 2026-11-02): پوشش کامل جفت‌های USDT تووبیت ──
    # دسته‌ای ۲۰تایی، فاصله ≥۲s، توقف فوری روی 418/429، سقف ۸ دقیقه + cursor در state.
    # خرابی پوشش هرگز مسیر legacy را نمی‌شکند (exception گرفته می‌شود و صادقانه ثبت می‌گردد).
    coverage = {}
    try:
        import toobit_coverage as tbc
        coverage = tbc.run_coverage(cycle_ts=cycle_ts, decision_ts=now_iso(),
                                    probe_cache=probe_cache, seen=seen)
    except Exception as e:
        coverage = {"ok": False, "stage": "toobit_coverage",
                    "error": f"{type(e).__name__}: {str(e)[:160]}"}

    append_jsonl(CYCLES, [{
        "evaluated_ts_utc": decision_ts, "cycle_ts": cycle_ts,
        "sources_ok": src_ok, "sources_total": len(sources),
        "failed_sources": failed, "mirror_new_cycles": mirrored,
        "candidates_in": len(cands), "decisions_written": len(decisions),
        "would_trade": len(wt),
        "unverified_tob_only": len(unv),
        "duplicate_sightings": len(dups),
        "gate_status_counts": dict(gate_counts),
        "m155_gate": True,
        "reject_reasons": sorted({r["reason"].split("(")[0] for r in rejects}),
        "toobit_coverage": coverage,
    }])
    print(json.dumps({
        "ok": True, "decision_ts_utc": decision_ts, "cycle_ts": cycle_ts,
        "sources_ok": f"{src_ok}/{len(sources)}", "failed_sources": failed,
        "mirror_new_cycles": mirrored, "candidates_in": len(cands),
        "decisions_written": len(decisions), "would_trade": len(wt),
        "unverified_tob_only": len(unv), "duplicate_sightings": len(dups),
        "gate_status_counts": dict(gate_counts),
        "unique_opportunities_indexed": len(load_jsonl(OPP_INDEX)),
        "rejects": len(rejects), "would_trade_ids": [d["id"] for d in wt],
        "toobit_coverage": coverage,
    }, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())
