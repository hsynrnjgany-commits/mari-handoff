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
    from datetime import datetime, timezone
    end_ms = None
    if a.end:
        end_ms = int(datetime.strptime(a.end, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    hyps = [h.strip() for h in a.hypotheses.split(",") if h.strip()] or None
    r = run_research(months=a.months, top=a.top, out_dir=a.out, end_ms=end_ms, hypotheses=hyps)
    out = {"period": r["period"], "baseline": r["baseline"], "symbols": r["universe"]["used"]}
    for hid, x in r["results"].items():
        f = x["full_period"]
        out[hid] = {"verdict": x["verdict"], "trades": f["trades"], "net_return_pct": f["net_return_pct"],
                    "profit_factor": f["profit_factor"], "bootstrap": f["bootstrap"]}
    print(json.dumps(out, ensure_ascii=False, indent=2))


def cmd_momentum(a):
    from .research import run_momentum_research
    from datetime import datetime, timezone

    def ms(d):
        return int(datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000) if d else None
    variants = tuple(v.strip() for v in a.variants.split(",") if v.strip()) or ("H-MARI-M-003", "H-MARI-M-004")
    r = run_momentum_research(years=a.years, top=a.top, out_dir=a.out, start_ms=ms(a.start), end_ms=ms(a.end),
                              variants=variants)
    print(json.dumps({k: {"verdict": v["verdict"], "strategy": v["strategy"], "by_year_pct": v["by_year_pct"]}
                      for k, v in r["results"].items()}, ensure_ascii=False, indent=2))


def cmd_classics(a):
    from .research import run_classics_research
    r = run_classics_research(start=a.start, out_dir=a.out)
    print(json.dumps({k: {kk: v.get(kk) for kk in ("verdict", "total_return_pct", "max_drawdown_pct", "sharpe")}
                      if k != "D-010" else v for k, v in r["results"].items()}, ensure_ascii=False, indent=2))


def cmd_macro(a):
    from .research import run_macro_research
    r = run_macro_research(start=a.start, out_dir=a.out)
    print(json.dumps({k: {kk: v.get(kk) for kk in ("verdict", "total_return_pct", "max_drawdown_pct", "sharpe")}
                      for k, v in r["results"].items()}, ensure_ascii=False, indent=2))


def cmd_funding(a):
    from .research import run_funding_research
    r = run_funding_research(start=a.start, out_dir=a.out)
    print(json.dumps({"verdict": r["results"]["verdict"], "sources": r["sources"]}, ensure_ascii=False, indent=2))


def cmd_pattern(a):
    from .research import run_pattern_research
    r = run_pattern_research(out_dir=a.out)
    print(json.dumps(r["results"]["verdict"], ensure_ascii=False, indent=2))


def cmd_notify_research(a):
    from .telegram import notify_research
    notify_research(a.kind, a.dir, a.status == "success")


def cmd_ideas(a):
    from .research import run_ideas_research
    r = run_ideas_research(start=a.start, out_dir=a.out)
    print(json.dumps(r["results"]["verdict"], ensure_ascii=False, indent=2))


def cmd_ideas2(a):
    from .research import run_ideas2_research
    r = run_ideas2_research(start=a.start, out_dir=a.out)
    print(json.dumps(r["results"]["verdict"], ensure_ascii=False, indent=2))


def cmd_ideas3(a):
    from .research import run_ideas3_research
    r = run_ideas3_research(start=a.start, out_dir=a.out)
    print(json.dumps(r["results"]["verdict"], ensure_ascii=False, indent=2))


def cmd_ideas4(a):
    from .research import run_ideas4_research
    r = run_ideas4_research(start=a.start, out_dir=a.out)
    print(json.dumps(r["results"]["verdict"], ensure_ascii=False, indent=2))


def cmd_ideas5(a):
    from .research import run_ideas5_research
    r = run_ideas5_research(start=a.start, out_dir=a.out)
    print(json.dumps(r["results"]["verdict"], ensure_ascii=False, indent=2))


def cmd_ideas6(a):
    from .research import run_ideas6_research
    r = run_ideas6_research(start=a.start, out_dir=a.out)
    print(json.dumps(r["results"]["verdict"], ensure_ascii=False, indent=2))


def cmd_replication(a):
    from .research import run_replication_research
    r = run_replication_research(start=a.start, out_dir=a.out)
    print(json.dumps(r["results"]["verdict"], ensure_ascii=False, indent=2))


def cmd_ict(a):
    from .research import run_ict_research
    r = run_ict_research(start=a.start, out_dir=a.out)
    print(json.dumps(r["results"]["verdict"], ensure_ascii=False, indent=2))


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
    rs.add_argument("--end", default="", help="پایان دوره YYYY-MM-DD (خالی = اکنون)")
    rs.add_argument("--hypotheses", default="", help="مثلاً H-MARI-B-001,H-MARI-B-002 (خالی = همه)")
    rs.set_defaults(fn=cmd_research)
    mo = sub.add_parser("momentum", help="آزمون H-MARI-M-003 مومنتوم روزانه (نیازمند اینترنت)")
    mo.add_argument("--years", type=int, default=5)
    mo.add_argument("--top", type=int, default=30)
    mo.add_argument("--out", default="research_out")
    mo.add_argument("--variants", default="", help="مثلاً H-MARI-M-003-PIT,H-MARI-M-004-PIT")
    mo.add_argument("--start", default="", help="شروع YYYY-MM-DD (خالی = اکنون منهای years)")
    mo.add_argument("--end", default="", help="پایان YYYY-MM-DD (خالی = اکنون)")
    mo.set_defaults(fn=cmd_momentum)
    cl = sub.add_parser("classics", help="روش‌های کلاسیک بزرگان + خرید پله‌ای (نیازمند اینترنت)")
    cl.add_argument("--start", default="2018-06-01")
    cl.add_argument("--out", default="research_out")
    cl.set_defaults(fn=cmd_classics)
    ma = sub.add_parser("macro", help="فیلترهای اقتصاد کلان آمریکا (FRED) روی BTC")
    ma.add_argument("--start", default="2018-06-01")
    ma.add_argument("--out", default="research_out")
    ma.set_defaults(fn=cmd_macro)
    ic = sub.add_parser("ict", help="آزمون شکار نقدینگی ICT روی BTC/ETH")
    ic.add_argument("--start", default="2018-06-01")
    ic.add_argument("--out", default="research_out")
    ic.set_defaults(fn=cmd_ict)
    fu = sub.add_parser("funding", help="آزمون نرخ فاندینگ روی BTC/ETH")
    fu.add_argument("--start", default="2020-06-01")
    fu.add_argument("--out", default="research_out")
    fu.set_defaults(fn=cmd_funding)
    pa = sub.add_parser("pattern", help="الگوی مشترک پنهان ارزهای صعودی")
    pa.add_argument("--out", default="research_out")
    pa.set_defaults(fn=cmd_pattern)
    idp = sub.add_parser("ideas", help="صف ایده‌ها: کنترل نوسان و تقاطع طلایی")
    idp.add_argument("--start", default="2018-06-01")
    idp.add_argument("--out", default="research_out")
    idp.set_defaults(fn=cmd_ideas)
    i2 = sub.add_parser("ideas2", help="صف ایده‌ها: هاوینگ و روز هفته")
    i2.add_argument("--start", default="2018-06-01")
    i2.add_argument("--out", default="research_out")
    i2.set_defaults(fn=cmd_ideas2)
    i3 = sub.add_parser("ideas3", help="صف ایده‌ها: ویلیامز و بولینگر")
    i3.add_argument("--start", default="2018-06-01")
    i3.add_argument("--out", default="research_out")
    i3.set_defaults(fn=cmd_ideas3)
    i4 = sub.add_parser("ideas4", help="صف ایده‌ها: مینروینی و راشکی")
    i4.add_argument("--start", default="2018-06-01")
    i4.add_argument("--out", default="research_out")
    i4.set_defaults(fn=cmd_ideas4)
    i5 = sub.add_parser("ideas5", help="صف ایده‌ها: الدر و کافمن")
    i5.add_argument("--start", default="2018-06-01")
    i5.add_argument("--out", default="research_out")
    i5.set_defaults(fn=cmd_ideas5)
    i6 = sub.add_parser("ideas6", help="صف ایده‌ها: چرخش BTC/ETH")
    i6.add_argument("--start", default="2018-06-01")
    i6.add_argument("--out", default="research_out")
    i6.set_defaults(fn=cmd_ideas6)
    rp = sub.add_parser("replication", help="آزمون تکرار روش‌های قبول‌شده روی ETH")
    rp.add_argument("--start", default="2018-06-01")
    rp.add_argument("--out", default="research_out")
    rp.set_defaults(fn=cmd_replication)
    nr = sub.add_parser("notify-research", help="خلاصهٔ پژوهش را به تلگرام صاحب ربات می‌فرستد")
    nr.add_argument("--kind", required=True)
    nr.add_argument("--dir", required=True)
    nr.add_argument("--status", default="success")
    nr.set_defaults(fn=cmd_notify_research)
    v = sub.add_parser("verify-ledger")
    v.add_argument("path")
    v.set_defaults(fn=cmd_verify)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
