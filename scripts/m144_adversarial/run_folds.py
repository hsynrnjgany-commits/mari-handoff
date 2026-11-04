#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M144 — اجرای پروتکل فولد M143 با چک‌پوینت.
mode=orig : بازتولید دقیق ۳ فولد M143 روی دادهٔ اصلی (راستی‌آزمایی نتایج ذخیره‌شده)
mode=ext  : همان پروتکل روی دادهٔ ادغام‌شدهٔ ~۲ساله (فولدهای بیشتر شامل BEAR واقعی)
usage: python3 run_folds.py orig|ext [k0] [k1]
قفل: READ ONLY | PAPER ONLY | NO LIVE ORDERS
"""
import json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from m144lib import (load_states, load_bars, run_fold, fold_count, OUTD,
                     ORIG_DATA, EXT_DATA, btc_regimes_data)

KEEP = {"entry_t", "exit_t", "sym", "side", "net_pct", "gross_pct", "reason", "held_h",
        "mfe_pct", "peak_unreal_pct", "partial", "entry", "exit"}


def compact(trades):
    return [{k: t.get(k) for k in KEEP} for t in trades]


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "orig"
    k0 = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    k1 = int(sys.argv[3]) if len(sys.argv) > 3 else 10 ** 9
    path = ORIG_DATA if mode == "orig" else EXT_DATA
    states = load_states(path, min_bars=2600 if mode == "orig" else 4800)
    btc = states.get("BTCUSDT")
    btc_map = (lambda ts: btc.time_idx.get(ts)) if btc is not None else None
    ks = fold_count(len(btc.bars))
    ks = [k for k in ks if k0 <= k < k1]
    print(f"mode={mode} symbols={len(states)} btc_bars={len(btc.bars)} folds={len(ks)} range={ks[:3]}..{ks[-3:]}", flush=True)
    tdir = f"{OUTD}/trades_{mode}"
    os.makedirs(tdir, exist_ok=True)
    outj = f"{OUTD}/folds_{mode}.jsonl"
    done = set()
    if os.path.exists(outj):
        for line in open(outj):
            try:
                done.add(json.loads(line)["fold"])
            except Exception:
                pass
    t_start = time.time()
    for k in ks:
        if k in done:
            continue
        row, old_t, newA_t, newB_t = run_fold(states, k, btc=btc, btc_map=btc_map)
        json.dump(row, open(outj, "a"), default=str)
        open(outj, "a").write("\n")
        json.dump(compact(old_t), open(f"{tdir}/fold{k}_old.json", "w"))
        json.dump(compact(newA_t), open(f"{tdir}/fold{k}_newA.json", "w"))
        json.dump(compact(newB_t), open(f"{tdir}/fold{k}_newB.json", "w"))
        el = time.time() - t_start
        print(f"fold{k} reg={row['regime']} old_n={row['old']['n']} old_net={row['old']['net_usd']} "
              f"newA_n={row['newA']['n']} newA_net={row['newA']['net_usd']} newB_n={row['newB']['n']} "
              f"newB_net={row['newB']['net_usd']} params={row['params']} [{el:.0f}s]", flush=True)


if __name__ == "__main__":
    main()
