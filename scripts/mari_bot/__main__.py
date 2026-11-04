# -*- coding: utf-8 -*-
"""ورودی خط فرمان ربات ماری.

  python3 -m mari_bot backtest --data mari_megatrend/data      بازپخش آفلاین روی دادهٔ موجود
  python3 -m mari_bot once                                     یک چرخهٔ زندهٔ تمرینی (دادهٔ عمومی تووبیت)
  python3 -m mari_bot run                                      اجرای پیوسته + فرمان‌های تلگرام
  python3 -m mari_bot report                                   گزارش فارسی از وضعیت ذخیره‌شده
  python3 -m mari_bot verify-ledger <path>                     بازبینی زنجیرهٔ هش دفتر شواهد

قفل: READ ONLY | PAPER ONLY | NO LIVE ORDERS
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from .config import LOCK_LINE, BotConfig, assert_locks

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_STATE = os.path.join(HERE, "state")
DEFAULT_DATA = os.path.join(os.path.dirname(HERE), "mari_megatrend", "data")


def cmd_backtest(a):
    from .backtest import run_backtest
    from .data import load_local_dir
    raw = load_local_dir(a.data)
    if not raw:
        sys.exit(f"داده‌ای در {a.data} پیدا نشد")
    r = run_backtest(raw, BotConfig(), ledger_path=a.ledger)
    m = r["metrics"]
    if a.json:
        print(json.dumps(m, ensure_ascii=False, indent=2))
        return
    from .telegram import fa
    print("═══ بازپخش تمرینی ربات ماری ═══")
    print(f"نمادها: {m['symbols']} — شناسهٔ تنظیمات: {m['config_sha']}")
    print(f"معامله‌های بسته: {m['trades']} — موقعیت باز در پایان: {m['open_positions']}")
    print(f"نرخ برد: {fa(m['win_rate_pct'], 1)}٪ — ضریب سود: {fa(m['profit_factor'])}")
    print(f"بازده خالص: {fa(m['net_return_pct'], sign=True)}٪ — بیشترین افت سرمایه: {fa(m['max_drawdown_pct'])}٪")
    print(f"میانگین برنده: {fa(m['avg_winner_pct'])}٪ — میانگین بازنده: {fa(m['avg_loser_pct'])}٪")
    print(f"نسبت شکار سود: {fa(m['profit_capture_ratio'])} — سود بازگردانده (میانگین): {fa(m['avg_giveback_pct'])}٪")
    if m["bootstrap"]:
        b = m["bootstrap"]
        print(f"بازهٔ اطمینان ۹۵٪ میانگین هر معامله: {fa(b['ci95_low'])}٪ تا {fa(b['ci95_high'])}٪")
    print(f"علت‌های خروج: {m['exit_reasons']}")
    print("توجه: چند هفته داده برای اثبات سودآوری کافی نیست — این فقط مشاهده است.")
    print(f"⚠️ {LOCK_LINE}")


def _runner(a):
    from .live import LiveRunner
    wl = [s.strip().upper() for s in (a.watchlist or "").split(",") if s.strip()]
    return LiveRunner(a.state, watchlist=wl, top_n=a.top, rotate_n=a.rotate)


def cmd_once(a):
    print(json.dumps(_runner(a).cycle(), ensure_ascii=False, indent=2))


def cmd_run(a):
    try:
        _runner(a).loop()
    except KeyboardInterrupt:
        print("\nمتوقف شد. وضعیت ذخیره شده است.")


def cmd_report(a):
    from .engine import MariBot
    from .ledger import Ledger
    from .telegram import fmt_report, fmt_trades
    p = os.path.join(a.state, "state.json")
    if not os.path.exists(p):
        sys.exit("هنوز وضعیتی ذخیره نشده — اول `once` یا `run` را اجرا کنید.")
    with open(p, encoding="utf-8") as fh:
        st = json.load(fh)
    bot = MariBot(BotConfig(), Ledger(None, "REPORT", "-"), st)
    print(fmt_report(bot).replace("<b>", "").replace("</b>", ""))
    print()
    print(fmt_trades(bot).replace("<b>", "").replace("</b>", ""))


def cmd_research(a):
    from .research import run_research
    r = run_research(months=a.months, top=a.top, out_dir=a.out)
    f = r["full_period"]
    print(json.dumps({"verdict": r["verdict"], "trades": f["trades"], "net_return_pct": f["net_return_pct"],
                      "profit_factor": f["profit_factor"], "bootstrap": f["bootstrap"],
                      "baseline": r["baseline"], "symbols": r["universe"]["used"]}, ensure_ascii=False, indent=2))


def cmd_verify(a):
    from .ledger import verify_chain
    print(json.dumps(verify_chain(a.path), ensure_ascii=False))


def main(argv=None):
    assert_locks()
    ap = argparse.ArgumentParser(prog="mari_bot", description="ربات تمرینی ماری — بدون سفارش واقعی")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backtest", help="بازپخش آفلاین")
    b.add_argument("--data", default=DEFAULT_DATA)
    b.add_argument("--ledger", default=None, help="مسیر دفتر شواهد JSONL (اختیاری)")
    b.add_argument("--json", action="store_true")
    b.set_defaults(fn=cmd_backtest)
    for name, fn in (("once", cmd_once), ("run", cmd_run)):
        p = sub.add_parser(name)
        p.add_argument("--state", default=DEFAULT_STATE)
        p.add_argument("--watchlist", default="", help="مثلاً BTCUSDT,ETHUSDT,SOLUSDT")
        p.add_argument("--top", type=int, default=40)
        p.add_argument("--rotate", type=int, default=60)
        p.set_defaults(fn=fn)
    r = sub.add_parser("report")
    r.add_argument("--state", default=DEFAULT_STATE)
    r.set_defaults(fn=cmd_report)
    rs = sub.add_parser("research", help="آزمون خارج از نمونه روی تاریخچهٔ طولانی (نیازمند اینترنت)")
    rs.add_argument("--months", type=int, default=6)
    rs.add_argument("--top", type=int, default=60)
    rs.add_argument("--out", default="research_out")
    rs.set_defaults(fn=cmd_research)
    v = sub.add_parser("verify-ledger")
    v.add_argument("path")
    v.set_defaults(fn=cmd_verify)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
