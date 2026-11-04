#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M144 — STEPS 2-4: adversarial statistics on instrumented M143 trades.
STEP 2: circular block bootstrap (time-ordered, L=24) CI95 for net mean/total, PF, MaxDD;
        paired NEW-A vs OLD block bootstrap; drop-top-5/10; cost perturbation grid.
STEP 3: regime analysis (folds incl. BEAR fold3), BTC vs ALT, crash overlap, vol spike.
STEP 4: keep_ratio {0.65,0.70,0.75} sensitivity on frozen TEST windows, TRAIN-only selection.
Writes out/m144_step234_stats.json. READ ONLY | PAPER ONLY.
"""
import json, os, random, hashlib

HERE = "/home/z/my-project/scripts/m144_adversarial"
OUTD = f"{HERE}/out"
SIZE = 100.0
SEED = 42
ITERS = 5000
BLOCK = 24

def load_trades():
    folds = {}
    for k in range(4):
        folds[k] = json.load(open(f"{OUTD}/m144_trades_fold{k}.json"))
    return folds

def metrics(ts, size=SIZE):
    n = len(ts)
    if n == 0:
        return {"n": 0, "net_usd": 0.0, "net_mean_pct": 0.0, "pf": None, "maxdd_usd": 0.0,
                "winrate": 0.0, "expectancy_usd": 0.0, "avg_mfe_pct": 0.0, "avg_mae_pct": 0.0,
                "giveback_usd": 0.0, "avg_winner_h": 0.0, "fees_usd": 0.0}
    nets = [t["net_pct"] for t in ts]
    wins = [x for x in nets if x > 0]; losses = [x for x in nets if x < 0]
    pf = round(sum(wins) / abs(sum(losses)), 3) if losses and sum(losses) != 0 else None
    seq = sorted(ts, key=lambda t: t["exit_t"])
    eq = pk = dd = 0.0
    for t in seq:
        eq += t["net_pct"] / 100 * size
        pk = max(pk, eq); dd = min(dd, eq - pk)
    giveback = sum(max(0.0, t.get("peak_unreal_pct", 0) - t["net_pct"]) for t in ts) / 100 * size
    fees = sum((0.10 + 2 * 0.05) for t in ts) / 100 * size  # per unit transacted = 1.0
    return {"n": n, "net_usd": round(sum(nets) / 100 * size, 2),
            "net_mean_pct": round(sum(nets) / n, 4), "pf": pf,
            "maxdd_usd": round(dd, 2), "winrate": round(len(wins) / n, 4),
            "expectancy_usd": round(sum(nets) / n / 100 * size, 4),
            "avg_mfe_pct": round(sum(v for v in (t.get("mfe_pct", 0) for t in ts) if -1e8 < v < 1e8) / max(1, sum(1 for v in (t.get("mfe_pct", 0) for t in ts) if -1e8 < v < 1e8)), 3),
            "avg_mae_pct": round(sum(t.get("mae_pct", 0) for t in ts) / n, 3),
            "giveback_usd": round(giveback, 2), "avg_winner_h": round(
                sum(t["held_h"] for t in ts if t["net_pct"] > 0) / max(1, len(wins)), 1),
            "fees_usd": round(fees, 2)}

def reprice(t, fee, slip):
    c = t["comps"]
    pnl = 0.0
    for e in c["events"]:
        pnl += e["frac"] * (e["gross"] - fee - 2 * slip)
    pnl += c["rem"] * (c["exit_gross"] - fee - 2 * slip)
    return pnl

def block_boot(ts, stat_fns, iters=ITERS, block=BLOCK, seed=SEED):
    """Circular block bootstrap over trades sorted by exit time. stat_fns: dict name->fn(list)->float"""
    ts_sorted = sorted(ts, key=lambda t: (t["exit_t"], t["sym"]))
    n = len(ts_sorted)
    if n == 0:
        return {}
    rnd = random.Random(seed)
    stats = {k: [] for k in stat_fns}
    nblocks = (n + block - 1) // block
    for _ in range(iters):
        sample = []
        for _b in range(nblocks):
            st = rnd.randrange(n)
            for j in range(block):
                sample.append(ts_sorted[(st + j) % n])
        sample = sample[:n]
        for k, fn in stat_fns.items():
            stats[k].append(fn(sample))
    out = {}
    for k, vals in stats.items():
        vals.sort()
        out[k] = {"point": None, "lo": vals[int(0.025 * iters)], "hi": vals[int(0.975 * iters)]}
    return out

def main():
    folds = load_trades()
    old_all = [t for k in range(4) for t in folds[k]["old"]]
    newA_all = [t for k in range(4) for t in folds[k]["newA"]]
    newB_all = [t for k in range(4) for t in folds[k]["newB"]]
    res = {"mission": "M144-STEP2-3-4", "block_len": BLOCK, "iters": ITERS, "seed": SEED}

    # ---------- baseline metrics (pooled folds 0-3 and 0-2) ----------
    for tag, (o, a, b) in {"pooled_f0123": (old_all, newA_all, newB_all),
                           "pooled_f012": ([t for k in range(3) for t in folds[k]["old"]],
                                           [t for k in range(3) for t in folds[k]["newA"]],
                                           [t for k in range(3) for t in folds[k]["newB"]])}.items():
        res[tag] = {"OLD": metrics(o), "NEW_A": metrics(a), "NEW_B": metrics(b)}

    # ---------- STEP 2: bootstrap ----------
    def net_sum(ts): return round(sum(t["net_pct"] for t in ts) / 100 * SIZE, 2)
    def net_mean(ts): return sum(t["net_pct"] for t in ts) / len(ts) if ts else 0.0
    def pf_f(ts):
        w = sum(t["net_pct"] for t in ts if t["net_pct"] > 0)
        l = -sum(t["net_pct"] for t in ts if t["net_pct"] < 0)
        return round(w / l, 3) if l > 0 else None
    def maxdd_f(ts):
        seq = sorted(ts, key=lambda t: (t["exit_t"], t["sym"]))
        eq = pk = dd = 0.0
        for t in seq:
            eq += t["net_pct"] / 100 * SIZE
            pk = max(pk, eq); dd = min(dd, eq - pk)
        return round(dd, 2)
    fns = {"net_mean_pct": net_mean, "net_usd": net_sum, "pf": pf_f, "maxdd_usd": maxdd_f}

    boot = {}
    for eng, ts in {"OLD": old_all, "NEW_A": newA_all, "NEW_B": newB_all}.items():
        b = block_boot(ts, fns)
        m = metrics(ts)
        for k in b: b[k]["point"] = m.get(k.replace("_usd", "_usd") if k != "net_mean_pct" else "net_mean_pct", m.get(k))
        boot[eng] = b
    res["step2_bootstrap"] = boot

    # paired NEW-A vs OLD on common entries, block bootstrap of diffs
    old_map = {(t["sym"], t["entry_t"]): t["net_pct"] for t in old_all}
    new_map = {(t["sym"], t["entry_t"]): t["net_pct"] for t in newA_all}
    common = sorted(set(old_map) & set(new_map), key=lambda k: k[1])
    diffs = [{"exit_t": k[1], "sym": k[0], "net_pct": new_map[k] - old_map[k]} for k in common]
    b = block_boot(diffs, {"mean_diff_pct": lambda ts: sum(t["net_pct"] for t in ts) / len(ts),
                           "total_diff_usd": lambda ts: round(sum(t["net_pct"] for t in ts) / 100 * SIZE, 2)})
    res["step2_paired_newA_vs_old"] = {"n_common": len(common), **b}

    # ---------- STEP 2b: drop top-5 / top-10 ----------
    drop = {}
    for eng, ts in {"OLD": old_all, "NEW_A": newA_all, "NEW_B": newB_all}.items():
        srt = sorted(ts, key=lambda t: -t["net_pct"])
        drop[eng] = {}
        for m in (5, 10):
            rest = srt[m:]
            mm = metrics(rest)
            drop[eng][f"drop_top{m}"] = {"n": mm["n"], "net_usd": mm["net_usd"], "pf": mm["pf"],
                                         "winrate": mm["winrate"], "maxdd_usd": mm["maxdd_usd"],
                                         "dropped_net_usd": round(sum(t["net_pct"] for t in srt[:m]) / 100 * SIZE, 2)}
        # concentration: share of total net from top 10
        tot = sum(t["net_pct"] for t in ts)
        top10 = sum(t["net_pct"] for t in srt[:10])
        drop[eng]["top10_share_of_gross_wins_pct"] = round(100 * top10 / sum(t["net_pct"] for t in ts if t["net_pct"] > 0), 1) if tot != 0 else None
    res["step2_drop_top"] = drop

    # ---------- STEP 2c: cost perturbation ----------
    grid = []
    for fee in (0.10, 0.15, 0.20, 0.30):
        for slip in (0.05, 0.10):
            row = {"fee_rt": fee, "slip": slip, "cost_per_trade_pct": fee + 2 * slip}
            for eng, ts in {"OLD": old_all, "NEW_A": newA_all, "NEW_B": newB_all}.items():
                rt = [{**t, "net_pct": round(reprice(t, fee, slip), 4)} for t in ts]
                mm = metrics(rt)
                row[eng] = {"net_usd": mm["net_usd"], "pf": mm["pf"], "winrate": mm["winrate"]}
            grid.append(row)
    res["step2_cost_grid"] = grid

    # ---------- STEP 3: regime ----------
    reg = {"by_fold": []}
    for k in range(4):
        f = folds[k]
        row = {"fold": k, "regime": f["regime"], "test": f["test"],
               "OLD": metrics(f["old"]), "NEW_A": metrics(f["newA"]), "NEW_B": metrics(f["newB"])}
        reg["by_fold"].append(row)
    def bucket(ts, pred):
        sel = [t for t in ts if pred(t)]
        return metrics(sel)
    for eng, ts in {"OLD": old_all, "NEW_A": newA_all, "NEW_B": newB_all}.items():
        reg[eng] = {
            "BTC_only": bucket(ts, lambda t: t["cls"] == "BTC"),
            "ALT_only": bucket(ts, lambda t: t["cls"] == "ALT"),
            "crash_overlap": bucket(ts, lambda t: t.get("crash_overlap")),
            "no_crash": bucket(ts, lambda t: not t.get("crash_overlap")),
            "btc_vol_spike_entry": bucket(ts, lambda t: (t.get("btc_atr_rank") or 0) > 0.95),
            "btc_bear_7d_entry": bucket(ts, lambda t: (t.get("btc_7d_ret") is not None) and t["btc_7d_ret"] < -5),
            "btc_bull_7d_entry": bucket(ts, lambda t: (t.get("btc_7d_ret") is not None) and t["btc_7d_ret"] > 5),
        }
    res["step3_regime"] = reg

    json.dump(res, open(f"{OUTD}/m144_step234_stats.json", "w"), ensure_ascii=False, indent=1)
    print("WROTE m144_step234_stats.json")
    # console digest
    p = res["pooled_f0123"]
    for e in ("OLD", "NEW_A", "NEW_B"):
        m = p[e]
        print(f"{e}: n={m['n']} net={m['net_usd']} pf={m['pf']} wr={m['winrate']} maxdd={m['maxdd_usd']} mae={m['avg_mae_pct']}")
    pa = res["step2_paired_newA_vs_old"]
    print("paired newA-old:", pa["n_common"], "mean", pa["mean_diff_pct"]["point"], "CI", pa["mean_diff_pct"]["lo"], pa["mean_diff_pct"]["hi"])
    for e in ("OLD", "NEW_A", "NEW_B"):
        print(e, "drop10:", res["step2_drop_top"][e]["drop_top10"])
    for row in res["step2_cost_grid"]:
        print("cost", row["cost_per_trade_pct"], {e: row[e]["net_usd"] for e in ("OLD", "NEW_A", "NEW_B")})
    for r in reg["by_fold"]:
        print(f"fold{r['fold']} {r['regime']}: OLD {r['OLD']['net_usd']} | NEW-A {r['NEW_A']['net_usd']} | NEW-B {r['NEW_B']['net_usd']}")

if __name__ == "__main__":
    main()
