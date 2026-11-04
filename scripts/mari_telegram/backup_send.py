#!/usr/bin/env python3
"""ارسال بکاپ tar.gz با بات تلگرام MARI (sendDocument — همان مقصد گزارش‌ها).
توکن از data/telegram-config.json خوانده می‌شود و هرگز چاپ نمی‌شود.
خروجی: JSON یک‌خطی {delivered, size_mb, files, message_id, why}"""
import json
import os
import sys
import urllib.error
import urllib.request
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from report import load_telegram_config, log_send, now_utc  # noqa: E402


def send_document(path, caption):
    cfg = load_telegram_config()
    tok = cfg.get("token", "")
    chats = cfg.get("chatIds", [])
    if not tok or not chats:
        return {"delivered": False, "why": "کانفیگ تلگرام ناقص"}
    boundary = uuid.uuid4().hex
    fname = os.path.basename(path)
    with open(path, "rb") as f:
        file_bytes = f.read()
    parts = []
    for k, v in [("chat_id", str(chats[0])), ("caption", caption)]:
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    parts.append(
        (f"--{boundary}\r\nContent-Disposition: form-data; name=\"document\"; "
         f"filename=\"{fname}\"\r\nContent-Type: application/gzip\r\n\r\n").encode()
        + file_bytes + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{tok}/sendDocument", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=420) as r:
            resp = json.load(r)
            st = r.status
    except urllib.error.HTTPError as e:
        st = e.code
        raw = e.read().decode(errors="replace")
        resp = {"ok": False, "raw": raw.replace(tok, "***")[:200]}
    except Exception as e:
        return {"delivered": False, "why": f"{type(e).__name__}: {e}"[:150]}
    res_obj = resp.get("result") or {}
    mid = res_obj.get("message_id") if isinstance(res_obj, dict) else None
    ok = st == 200 and resp.get("ok") and mid
    log_send({"ts_utc": now_utc().isoformat(), "type": "backup_tar_gz", "chat_id": chats[0],
              "part": "1/1", "http": st, "api_ok": resp.get("ok"), "message_id": mid,
              "delivered": bool(ok), "error": None if ok else str(resp.get("raw", ""))[:150]})
    why = None if ok else str(resp.get("raw", resp.get("description", "")))[:150]
    return {"delivered": bool(ok), "http": st, "message_id": mid, "why": why}


def main():
    tar = sys.argv[1]
    caption = ("📦 بکاپ کد MARI — scripts/ + universe.json\n"
               "بدون: .env / keys.env / vault-private / paper-trades.json / هر فایل کلید\n"
               "وریفای‌شده: هیچ نام یا الگوی کلید داخل فایل نیست · READ ONLY | PAPER ONLY")
    res = send_document(tar, caption)
    size_mb = round(os.path.getsize(tar) / 1024 / 1024, 1)
    res["size_mb"] = size_mb
    print(json.dumps(res, ensure_ascii=False))
    return 0 if res["delivered"] else 1


if __name__ == "__main__":
    sys.exit(main())
