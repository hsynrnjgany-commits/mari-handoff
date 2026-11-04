#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M144 — STEP 4: keep_ratio {0.65, 0.70, 0.75} sensitivity for NEW-A.
- TRAIN-only selection per fold (same protocol as calibrate_exit_params: cooldown=6, cap=140 sig/sym).
- TEST/OOS windows frozen (identical signal sets & entry timing as M143 replay).
- Records Net PnL, PF, MaxDD, n, Giveback (mean ratio + USD), Fees per keep value.
Writes out/m144_step4_sensitivity.json. READ ONLY | PAPER ONLY.
"""
import json, os, sys, hashlib

sys.path.insert(0, "/home/z/my-project/scripts/m144_adversarial")
from m144_replay import load_states, entry_signals_v1, run_smart_exit
from engine143 import SmartExitParams
import engine143

HERE = "/home/z/my-project/scripts/m144_adversarial"
OUTD = f"{HERE}/out"
SIZE = 100.0
KEEPS = (0.65, 0.70, 0.75)
FROZEN_ATR, FROZEN_PARTIAL = 3.0, 0.0   # atr_mult/partial frozen to M143 fold selection

def run_set(states, sigs, keep, cap_i, max_sig=140):
    p = SmartExitParams(atr_mult=FROZEN_ATR, keep_ratio=keep, partial_frac=FROZEN_PARTIAL)
    out = []
    for sym, s in states.items():
        cnt, last_exit = 0, -1
        for (i, side, *_r) in sigs[sym]:
            if cnt >= max_sig: break
            if i <= last_exit + 6: continue
            t = run_smart_exit(s, i, side, p, cap_i=cap_i)
            cnt += 1
            if t:
                out.append(t)
                last_exit = s.time_idx.get(t["exit_t"], 10**9)
    return out

def metrics(ts):
    n = len(ts)
    if n == 0:
        return {"n": 0, "net_usd": 0.0, "pf": None, "maxdd_usd": 0.0, "winrate": 0.0,
                "giveback_ratio": 0.0, "giveback_usd": 0.0, "fees_usd": 0.0}
    nets = [t["net_pct"] for t in ts]
    wins = [x for x in nets if x > 0]; losses = [x for x in nets if x < 0]
    pf = round(sum(wins) / abs(sum(losses)), 3) if losses and sum(losses) else None
    seq = sorted(ts, key=lambda t: t["exit_t"])
    eq = pk = dd = 0.0
    for t in seq:
        eq += t["net_pct"] / 100 * SIZE
        pk = max(pk, eq); dd = min(dd, eq - pk)
    gb = [ (t["peak_unreal_pct"] - t["net_pct"]) / t["peak_unreal_pct"]
           for t in ts if t.get("peak_unreal_pct", 0) >= 1.0 and t["net_pct"] < t["peak_unreal_pct"] ]
    return {"n": n, "net_usd": round(sum(nets) / 100 * SIZE, 2), "pf": pf,
            "maxdd_usd": round(dd, 2), "winrate": round(len(wins) / n, 4),
            "giveback_ratio": round(sum(gb) / n, 3),
            "giveback_usd": round(sum(max(0.0, t.get("peak_unreal_pct", 0) - t["net_pct"]) for t in ts) / 100 * SIZE, 2),
            "fees_usd": round(n * 0.2, 2)}  # 0.20% round-trip cost on $100 per trade

def main():
    states = load_states()
    folds = [(0, 1920, 2400), (1, 2400, 2880), (2, 2880, 3360), (3, 3360, 3840)]
    res = {"mission": "M144-STEP4", "keeps": KEEPS, "frozen": {"atr_mult": FROZEN_ATR, "partial_frac": FROZEN_PARTIAL},
           "protocol": "keep selected on TRAIN only; TEST frozen with identical signals", "by_fold": []}
    for k, tr_hi, te_hi in folds:
        sig_train = {sym: entry_signals_v1(s, 60, tr_hi) for sym, s in states.items()}
        sig_test = {sym: entry_signals_v1(s, tr_hi, te_hi) for sym, s in states.items()}
        tr = {keep: metrics(run_set(states, sig_train, keep, cap_i=tr_hi)) for keep in KEEPS}
        te = {keep: metrics(run_set(states, sig_test, keep, cap_i=te_hi)) for keep in KEEPS}
        sel = max(KEEPS, key=lambda kk: tr[kk]["net_usd"])
        boundary_hit = sel == max(KEEPS)
        res["by_fold"].append({"fold": k, "train_hi": tr_hi, "test_hi": te_hi,
                               "train": tr, "test": te,
                               "train_selected_keep": sel, "selection_at_grid_boundary": boundary_hit,
                               "oos_of_selected": te[sel]})
        print(f"fold{k}: train_sel={sel} boundary={boundary_hit} | TEST: " +
              " | ".join(f"keep{kk}: n={te[kk]['n']} net={te[kk]['net_usd']} pf={te[kk]['pf']} dd={te[kk]['maxdd_usd']} gb={te[kk]['giveback_usd']}" for kk in KEEPS), flush=True)
    # pooled TEST across folds per keep
    pooled = {}
    for keep in KEEPS:
        allts = []
        # re-run pooled via per-fold test trades re-simulation is heavy; approximate by summing fold metrics
        rows = [f["test"][keep] for f in res["by_fold"]]
        pooled[keep] = {"sum_net_usd": round(sum(r["net_usd"] for r in rows), 2),
                        "sum_n": sum(r["n"] for r in rows),
                        "fees_usd": round(sum(r["fees_usd"] for r in rows), 2),
                        "giveback_usd": round(sum(r["giveback_usd"] for r in rows), 2)}
    res["pooled_test"] = pooled
    p = f"{OUTD}/m144_step4_sensitivity.json"
    json.dump(res, open(p, "w"), ensure_ascii=False, indent=1)
    print("WROTE", p, "sha256", hashlib.sha256(open(p, "rb").read()).hexdigest()[:16])

if __name__ == "__main__":
    main()
