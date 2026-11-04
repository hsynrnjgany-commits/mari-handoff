#!/usr/bin/env python3
"""پیش‌اسکن scripts/ برای یافتن فایل‌های کلید — فقط مسیر و نام الگو چاپ می‌شود، هرگز مقدار.
مبنای مستثنی‌سازی «هر فایل کلید» در بکاپ تلگرام. READ ONLY — هیچ فایلی تغییر نمی‌کند."""
import os
import re
import sys

ROOT = "scripts"
# نام‌فایل‌هایی که به‌هرحال کلید/محیط حساب می‌شوند
NAME_PAT = re.compile(
    r"(^\.env($|\.)|keys\.env$|vault-private|paper-trades\.json$|"
    r"\.pem$|\.key$|\.p12$|id_rsa|credentials?\.json$|telegram-config\.json$)", re.I)
# الگوهای کلید واقعی داخل متن (نمایش مقدار ممنوع)
VALUE_PATS = [
    ("ghp_pat", re.compile(r"gh[pousr]_[A-Za-z0-9]{25,}")),
    ("openai_sk", re.compile(r"sk-[A-Za-z0-9_\-]{20,}")),
    ("aws_akia", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("slack_xox", re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}")),
    ("privkey_block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("assign_token", re.compile(r"(?:GH_TOKEN|GITHUB_TOKEN|MARI_TELEGRAM_TOKEN|TELEGRAM_BOT_TOKEN|BOT_TOKEN|API_KEY|APIKEY|SECRET_KEY|ACCESS_TOKEN|DEEPSEEK_API_KEY|ZAI_API_KEY)\s*[=:]\s*[\"']?[A-Za-z0-9_\-\.]{20,}", re.I)),
    ("bearer_long", re.compile(r"[Bb]earer\s+[A-Za-z0-9_\-\.]{30,}")),
    ("deepseek_style", re.compile(r"[A-Za-z0-9]{32,45}(?=\s*$)")),
]
SKIP_EXT = {".png", ".jpg", ".jpeg", ".gif", ".zip", ".gz", ".tgz", ".pyc", ".bin",
            ".parquet", ".csv.gz", ".xlsx", ".pdf", ".ico", ".woff", ".woff2"}
MAX_BYTES = 8 * 1024 * 1024  # فایل‌های بزرگ‌تر را تکه‌تکه می‌خوانیم ولی کامل اسکن می‌کنیم


def scan_file(path):
    hits = set()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                try:
                    text = chunk.decode("utf-8", errors="ignore")
                except Exception:
                    hits.add("binary")
                    break
                for name, pat in VALUE_PATS:
                    if pat.search(text):
                        hits.add(name)
    except OSError as e:
        hits.add(f"unreadable:{type(e).__name__}")
    return hits


def main():
    flagged, names = [], []
    n_files = 0
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in ("node_modules", "__pycache__")]
        for fn in filenames:
            p = os.path.join(dirpath, fn)
            n_files += 1
            if NAME_PAT.search(fn):
                names.append(p)
                continue
            if os.path.splitext(fn)[1].lower() in SKIP_EXT:
                continue
            hits = scan_file(p)
            if hits:
                flagged.append((p, sorted(hits)))
    print(f"FILES_WALKED={n_files}")
    print(f"NAME_EXCLUDES={len(names)}")
    for p in names:
        print(f"  NAME\t{p}")
    print(f"CONTENT_FLAGGED={len(flagged)}")
    for p, hits in flagged:
        print(f"  CONTENT\t{p}\t{','.join(hits)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
