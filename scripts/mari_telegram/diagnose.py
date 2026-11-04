#!/usr/bin/env python3
"""
MARI — تشخیص کامل مسیر تلگرام (فرمان §۶)
هرگز توکن چاپ نمی‌شود. موفقیت فقط با پاسخ واقعی API اعلام می‌شود.
READ ONLY | PAPER ONLY | NO LIVE ORDERS — فقط یک پیام آزمایشی send می‌کند.
"""
import json
import os
import stat
import sys
import urllib.request
import urllib.error

CFG = "data/telegram-config.json"
API = "https://api.telegram.org"


def load_cfg():
    if not os.path.exists(CFG):
        print(json.dumps({"step": "config", "ok": False,
                          "why": f"{CFG} وجود ندارد (data/ دیشب بازسازی شد)"}))
        return None
    cfg = json.load(open(CFG))
    tok = cfg.get("token", "")
    chats = cfg.get("chatIds", cfg.get("chat_ids", []))
    print(json.dumps({
        "step": "config", "ok": bool(tok and chats),
        "config_path": CFG, "config_bytes": os.path.getsize(CFG),
        "token_present": bool(tok), "token_len": len(tok),
        "chat_ids": chats,
        "extra_fields": sorted(set(cfg.keys()) - {"token", "chatIds", "chat_ids"}),
        "perm": stat.filemode(os.stat(CFG).st_mode),
    }, ensure_ascii=False))
    if not tok or not chats:
        return None
    return cfg


def call(token, method, payload=None, timeout=15):
    """برگرداندن (status, body) — توکن در خطا هم فیلتر می‌شود."""
    url = f"{API}/bot{token}/{method}"
    data = json.dumps(payload or {}).encode()
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        body = body.replace(token, "***TOKEN***")
        return e.code, {"raw": body[:300]}
    except Exception as e:
        return None, {"raw": f"{type(e).__name__}: {str(e)[:200]}"}


def main():
    cfg = load_cfg()
    if not cfg:
        return 1
    tok = cfg["token"]
    chats = cfg.get("chatIds", cfg.get("chat_ids", []))

    # ۱) getMe — اعتبار توکن
    st, me = call(tok, "getMe")
    bot = me.get("result", {}).get("username") if st == 200 else None
    print(json.dumps({"step": "getMe", "http": st, "api_ok": me.get("ok"),
                      "bot": f"@{bot}" if bot else None,
                      "why": None if st == 200 else me.get("raw", "")[:150]},
                     ensure_ascii=False))
    if st != 200 or not me.get("ok"):
        return 1

    # ۲) getChat — اعتبارسنجی هر مقصد
    valid = []
    for cid in chats:
        st2, ch = call(tok, "getChat", {"chat_id": cid})
        kind = ch.get("result", {}).get("type") if st2 == 200 else None
        title = ch.get("result", {}).get("title") or ch.get("result", {}).get("username")
        print(json.dumps({"step": "getChat", "chat_id": cid, "http": st2,
                          "api_ok": ch.get("ok"), "type": kind,
                          "title": title,
                          "why": None if st2 == 200 else str(ch.get("raw", ""))[:150]},
                         ensure_ascii=False))
        if st2 == 200 and ch.get("ok"):
            valid.append(cid)

    # ۳) getWebhookInfo — وضعیت webhook/سرویس
    st3, wh = call(tok, "getWebhookInfo")
    print(json.dumps({"step": "getWebhookInfo", "http": st3, "api_ok": wh.get("ok"),
                      "pending_updates": wh.get("result", {}).get("pending_update_count"),
                      "webhook_url": wh.get("result", {}).get("url") or "(polling)",
                      "last_error": wh.get("result", {}).get("last_error_message")},
                     ensure_ascii=False))

    # ۴) پیام آزمایشی به اولین مقصد معتبر — با شواهد message_id
    if not valid:
        print(json.dumps({"step": "sendMessage", "ok": False,
                          "why": "هیچ chat_id معتبری — پیام آزمایشی ارسال نشد"}))
        return 1
    text = ("🧪 پیام آزمایشی MARI\n"
            "زمان (UTC): " + __import__("datetime").datetime.utcnow().isoformat() +
            "\nاگر این پیام را می‌بینید، مسیر تلگرام سالم است.\n"
            "READ ONLY | PAPER ONLY | NO LIVE ORDERS")
    st4, sent = call(tok, "sendMessage",
                     {"chat_id": valid[0], "text": text}, timeout=20)
    ok = st4 == 200 and sent.get("ok") and sent.get("result", {}).get("message_id")
    print(json.dumps({"step": "sendMessage", "http": st4, "api_ok": sent.get("ok"),
                      "chat_id": valid[0],
                      "message_id": sent.get("result", {}).get("message_id"),
                      "date_epoch": sent.get("result", {}).get("date"),
                      "delivered": bool(ok),
                      "why": None if ok else str(sent.get("raw", ""))[:200]},
                     ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
