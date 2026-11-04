#!/usr/bin/env python3
"""MARI cron 486335 reconcile + digest check (READ ONLY)."""
import json, hashlib
from pathlib import Path

STORE = Path("/home/z/my-project/scripts/mari_hunt01/store")
PT = Path("/home/z/my-project/data/paper-trades.json")
REF = "6d8b7beb6d5a6c01"

def nlines(p):
    with open(p, "rb") as f:
        return sum(1 for ln in f if ln.strip())

dec = nlines(STORE / "decisions.jsonl")
rej = nlines(STORE / "rejects.jsonl")
cyc = nlines(STORE / "cycles.jsonl")
mir = nlines(STORE / "vault-mirror.jsonl")
cand_total = dec + rej

# WOULD_TRADE stats
wt_total = 0
wt_new = []
with open(STORE / "decisions.jsonl") as f:
    for ln in f:
        if not ln.strip():
            continue
        d = json.loads(ln)
        if str(d.get("decision", "")).upper() == "WOULD_TRADE":
            wt_total += 1
            if d.get("cycle_ts", "").startswith("2026-10-31T02:40"):
                wt_new.append({
                    "id": d.get("id"),
                    "base": d.get("base"),
                    "buy": d.get("buy_ex"),
                    "sell": d.get("sell_ex"),
                    "net_pct": d.get("net_pct"),
                    "method": d.get("method"),
                })

print(json.dumps({
    "ledger": {"decisions": dec, "rejects": rej, "candidates_total": cand_total,
               "cycles": cyc, "vault_mirror_cycles": mir},
    "would_trade": {"cumulative": wt_total, "new_this_cycle": len(wt_new), "new": wt_new},
}, ensure_ascii=False, indent=1))

# Digest of protected file: core = {paused, trades, version} (confirmed formula)
raw = json.loads(PT.read_text())
core = {k: raw[k] for k in ("paused", "trades", "version") if k in raw} if isinstance(raw, dict) else raw
dg = hashlib.sha256(json.dumps(core, sort_keys=True).encode()).hexdigest()[:16]
print(f"DIGEST[core=paused+trades+version] = {dg}  MATCH_REF={dg == REF}")
print("FULL_FILE_SHA16 =", hashlib.sha256(PT.read_bytes()).hexdigest()[:16])
print("PAUSED =", raw.get("paused") if isinstance(raw, dict) else "?")
print("TRADES_N =", len(raw.get("trades", [])) if isinstance(raw, dict) else "?")
