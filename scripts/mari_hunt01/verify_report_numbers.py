#!/usr/bin/env python3
"""M155 — verification of every number claimed in the HUNT-01 final recovery report.
READ ONLY — no writes to store. Prints PASS/FAIL per claim."""
import json, hashlib, statistics, collections, datetime

BASE = "/home/z/my-project"
STORE = BASE + "/scripts/mari_hunt01/store"

def load_jsonl(p):
    out = []
    for ln in open(p, encoding="utf-8"):
        ln = ln.strip()
        if ln:
            try:
                out.append(json.loads(ln))
            except Exception:
                pass
    return out

cycles = load_jsonl(STORE + "/cycles.jsonl")
decisions = load_jsonl(STORE + "/decisions.jsonl")
rejects = load_jsonl(STORE + "/rejects.jsonl")
mirror = load_jsonl(STORE + "/vault-mirror.jsonl")
idx = load_jsonl(STORE + "/opportunities_index.jsonl")

print("=== CORE COUNTERS ===")
print("cycles:", len(cycles), "(claim 32)")
print("decisions:", len(decisions), "(claim 260)")
print("rejects:", len(rejects), "(claim 385)")
print("total rows:", len(decisions) + len(rejects), "(claim 645)")

# WOULD_TRADE count in decisions
wt = [d for d in decisions if str(d.get("decision", d.get("gate_status", ""))).upper() == "WOULD_TRADE"]
wt2 = [d for d in decisions if "WOULD_TRADE" in json.dumps(d).upper()]
print("decisions with WOULD_TRADE field:", len(wt), "/ loose match:", len(wt2), "(claim 83 incl 3 pilot)")

# per-cycle WT
per_cycle = collections.Counter()
for d in decisions:
    if "WOULD_TRADE" in json.dumps(d).upper():
        per_cycle[d.get("cycle_ts", "?")[:19]] += 1
cyc_sum = sum(per_cycle.values())
pilot = len(wt2) - cyc_sum
print("per-cycle WT sum:", cyc_sum, "pilot WT:", pilot, "(claim 80+3=83)")

# reject reasons
reasons = collections.Counter()
for r in rejects:
    reasons[r.get("reason", r.get("reject_reason", "?"))] += 1
top = reasons.most_common(6)
print("=== TOP REJECT REASONS ===")
for k, v in top:
    print(f"  {k}: {v}")
print("(claim frozen_quote x202, phantom x22)")

# net stats over WOULD_TRADE rows
nets = []
for d in wt2:
    np_ = d.get("net_pct")
    if np_ is None and "net_pct" in json.dumps(d):
        np_ = d.get("net_pct")
    try:
        nets.append(float(np_))
    except Exception:
        pass
print("=== NET EDGE STATS (over", len(nets), "records; claim 83) ===")
if nets:
    print("mean %.4f median %.4f max %.4f min %.4f neg %d" % (
        statistics.mean(nets), statistics.median(nets), max(nets), min(nets),
        sum(1 for n in nets if n < 0)))
print("(claim mean 1.1457 / median 0.5047 / max 8.1211 / min 0.1565 / neg 0)")

# qualified tiers
tiers = collections.Counter()
for d in wt2:
    tiers[str(d.get("tier", d.get("eval_tier", "?")))] += 1
print("tiers:", dict(tiers), "(claim 46 tob_estimate + 37 l2_vwap_100)")

# mirror records
print("mirror records:", len(mirror), "(claim 129)")

# sources per cycle
partial = []
for i, c in enumerate(cycles, 1):
    if c.get("sources_ok", 8) < 8:
        partial.append(i)
print("partial-source cycles:", partial, "(claim 1,10,12,15,22)")

# balance check per cycle
from collections import defaultdict
bal_bad = []
dec_by_cycle = defaultdict(int)
rej_by_cycle = defaultdict(int)
for d in decisions:
    dec_by_cycle[d.get("cycle_ts", "?")[:19]] += 1
for r in rejects:
    rej_by_cycle[r.get("cycle_ts", "?")[:19]] += 1
for c in cycles:
    ts = c["cycle_ts"][:19]
    if c.get("candidates_in", 20) != dec_by_cycle.get(ts, 0) + rej_by_cycle.get(ts, 0):
        bal_bad.append(ts)
print("balance violations:", bal_bad if bal_bad else "NONE (all 20 = dec+rej)")

# hashes
def h16(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()[:16]
print("=== HASHES ===")
for p, claim in [
    ("scripts/mari_hunt01/hunt_sweep.py", "798b42dd8c19cbf8"),
    ("scripts/m155_ab_upgrade/arb_reality_gate.py", "a5b2135f42e2d236"),
    ("scripts/m155_ab_upgrade/m155_evaluate.py", "8e41f357e89107fa"),
    ("scripts/mari_hunt01/store/decisions.jsonl", "5fdb929a8098507e"),
    ("scripts/mari_hunt01/store/rejects.jsonl", "a37d17a157b961c3"),
    ("scripts/mari_hunt01/store/cycles.jsonl", "160b6a418f2bfa4b"),
]:
    got = h16(BASE + "/" + p)
    print(("OK " if got == claim else "MISMATCH ") + got, p, "(claim " + claim + ")")

pt = json.load(open(BASE + "/data/paper-trades.json", "rb").read() and open(BASE + "/data/paper-trades.json"))
core = hashlib.sha256(json.dumps(pt.get("core", pt), sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16] if isinstance(pt, dict) else "?"
print("paper-trades core hash attempt:", core, "(claim 6d8b7beb6d5a6c01)")

# cycle table qualified/rejected per cycle — print compact for report check
print("=== PER-CYCLE TABLE (ledger-derived) ===")
for i, c in enumerate(cycles, 1):
    ts = c["cycle_ts"][:19]
    print(f"{i}|{ts}|cand={c.get('candidates_in')}|dec={dec_by_cycle.get(ts,0)}|rej={rej_by_cycle.get(ts,0)}|WT={per_cycle.get(ts,0)}|src={c.get('sources_ok')}/8")
