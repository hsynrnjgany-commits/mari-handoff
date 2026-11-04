#!/usr/bin/env python3
"""بکاپ تلگرام MARI — ساخت tar.gz پاک از کلید + وریفای محتوا + گزارش JSON.
مستثنی‌ها (فرمان رییس): .env، keys.env، vault-private، paper-trades.json، هر فایل کلید.
خروجی: {"files": N, "size_mb": X, "verify": {...}, "tar": path} — هیچ Secretی چاپ نمی‌شود.
READ ONLY — فقط می‌سازد و می‌خواند؛ هیچ فایل موجودی تغییر نمی‌کند."""
import json
import os
import re
import subprocess
import sys
import tarfile
from datetime import datetime, timezone

ROOT = "/home/z/my-project"
TS = datetime.now(timezone.utc).strftime("%Y%m%dT%H%MZ")
TAR = f"/tmp/mari_scripts_backup_{TS}.tar.gz"
VERIFY_DIR = "/tmp/mari_backup_verify"

# فایل‌هایی که پیش‌اسکن به‌عنوان «فایل کلید»/دارای الگوی توکن علامت زد — مستثنی کامل
NAME_EXCLUDE = [
    "scripts/m71/sandbox/data/paper-trades.json",
    "scripts/m71_bv2/data/paper-trades.json",
    "scripts/m71_sandbox/data/paper-trades.json",
    "scripts/test-vault.ts",
]
NAME_PAT = re.compile(
    r"(^\.env($|\.)|/\.env($|\.)|keys\.env$|vault-private|paper-trades\.json$|"
    r"telegram-config\.json$|\.pem$|\.key$|id_rsa|credentials?\.json$)", re.I)
# الگوهای سخت‌گیرانهٔ کلید واقعی (آستانهٔ طول برای حذف مثبت کاذب دادهٔ بازار مثل SK Hynix)
VALUE_PATS = [
    ("ghp_pat", re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}")),
    ("openai_sk", re.compile(r"sk-[A-Za-z0-9]{40,}")),
    ("aws_akia", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("slack_xox", re.compile(r"xox[baprs]-[A-Za-z0-9\-]{20,}")),
    ("privkey_block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("assign_token", re.compile(r"(?:GH_TOKEN|GITHUB_TOKEN|MARI_TELEGRAM_TOKEN|TELEGRAM_BOT_TOKEN|BOT_TOKEN|API_KEY|APIKEY|SECRET_KEY|ACCESS_TOKEN|DEEPSEEK_API_KEY|ZAI_API_KEY)\s*[=:]\s*[\"']?[A-Za-z0-9_\-\.]{25,}", re.I)),
]
SKIP_EXT = {".png", ".jpg", ".jpeg", ".gif", ".zip", ".gz", ".tgz", ".pyc", ".bin",
            ".parquet", ".xlsx", ".pdf", ".ico", ".woff", ".woff2"}


def scan_names(names):
    bad = [n for n in names if NAME_PAT.search(n) or
           os.path.basename(n) in {os.path.basename(p) for p in NAME_EXCLUDE}]
    return bad


def scan_content(root_dir):
    bad, n_files = [], 0
    for dirpath, dirnames, filenames in os.walk(root_dir):
        dirnames[:] = [d for d in dirnames if d not in ("node_modules", "__pycache__")]
        for fn in filenames:
            p = os.path.join(dirpath, fn)
            n_files += 1
            if os.path.splitext(fn)[1].lower() in SKIP_EXT:
                continue
            try:
                with open(p, "rb") as f:
                    for chunk in iter(lambda: f.read(1024 * 1024), b""):
                        text = chunk.decode("utf-8", errors="ignore")
                        for name, pat in VALUE_PATS:
                            if pat.search(text):
                                bad.append({"file": p, "pattern": name})
            except OSError:
                pass
    return bad, n_files


def main():
    # ۱) ساخت tar.gz با مستثنی‌ها
    excl = []
    for e in ["__pycache__", "*.pyc", ".env", ".env.*", "keys.env",
              "*vault-private*", "*paper-trades.json", "test-vault.ts"]:
        excl += ["--exclude", e]
    cmd = ["tar", "-czf", TAR] + excl + ["-C", ROOT, "scripts", "scripts/mari_hunt01/universe.json"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(json.dumps({"ok": False, "why": f"tar_failed: {r.stderr[:200]}"}, ensure_ascii=False))
        return 1
    size = os.path.getsize(TAR)
    size_mb = round(size / 1024 / 1024, 1)

    # ۲) وریفای داخل فایل: نام‌ها
    with tarfile.open(TAR, "r:gz") as tf:
        names = tf.getnames()
    name_bad = scan_names(names)
    leaked_excl = [n for n in names
                   for x in NAME_EXCLUDE if n.endswith(os.path.basename(x))]

    # ۳) وریفای داخل فایل: محتوا (استخراج به /tmp و اسکن کامل)
    subprocess.run(["rm", "-rf", VERIFY_DIR], check=False)
    os.makedirs(VERIFY_DIR, exist_ok=True)
    with tarfile.open(TAR, "r:gz") as tf:
        tf.extractall(VERIFY_DIR)
    content_bad, n_files = scan_content(VERIFY_DIR)

    out = {
        "ok": not name_bad and not content_bad,
        "tar": TAR, "files": len(names), "scanned_files": n_files,
        "size_mb": size_mb, "under_45mb": size < 45 * 1024 * 1024,
        "universe_json_included": any("mari_hunt01/universe.json" == n[len("scripts/"):] or
                                      n.endswith("mari_hunt01/universe.json") for n in names),
        "name_violations": name_bad[:10],
        "content_violations": [{"file": b["file"].replace(VERIFY_DIR, ""), "pattern": b["pattern"]}
                               for b in content_bad[:10]],
        "excluded_applied": NAME_EXCLUDE,
    }
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
