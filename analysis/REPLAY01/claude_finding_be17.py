# READ ONLY / PAPER ONLY — بازتولید یافتهٔ ۱۷ معاملهٔ سربه‌سر (هیچ فایلی را تغییر نمی‌دهد)
# اجرا از ریشهٔ مخزن: python3 analysis/REPLAY01/claude_finding_be17.py
import json, collections
H = 3600000
tr = {t['id']: t for t in json.load(open('outbox/engine_snapshot/data/paper-trades.json'))['trades']}
cd = collections.defaultdict(list)
for l in open('outbox/candles/candles_ext_for_trades.jsonl'):
    r = json.loads(l); cd[r['tradeId']].append(r)
ids = [l.split()[0] for l in open('analysis/REPLAY01/unmatched17_ext.txt') if l.strip()]
match = 0
for i in ids:
    t = tr[i]; e = t['entryPrice']; L = t['side'] == 'LONG'
    lc_off = round((t['lastCheck'] - t['entryTime']) / H - 1.0 - 0.25)   # کندل بستهٔ پیش از lastCheck
    rows = {(k['t'] - t['entryTime']) // H: k for k in cd[i]}
    k = rows.get(lc_off)
    if k is None:
        print(i, 'lastCheck خارج از پنجرهٔ کندل‌ها (+', lc_off, 'h)'); continue
    fav = ((k['h'] - e) / e if L else (e - k['l']) / e) * 100
    bep = e * (1.001 if L else 0.999)
    hit = k['l'] <= bep if L else k['h'] >= bep
    same = abs(fav - t['mfePct']) < 0.01
    match += same
    print(i, f"کندل +{lc_off}h: fav={fav:.3f}٪ mfe_ثبت‌شده={t['mfePct']:.3f}٪ {'= برابر' if same else ''} | "
             f"BE-stop در همان کندل خورده؟ {hit} | exitTime ثبت‌شده = ورود+{(t['exitTime']-t['entryTime'])/H:.0f}h")
print('MFE ثبت‌شده = favِ تک‌کندلِ پیش از lastCheck در', match, 'از', len(ids))
