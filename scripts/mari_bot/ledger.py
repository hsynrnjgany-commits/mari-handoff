# -*- coding: utf-8 -*-
"""دفتر شواهد (Evidence Ledger) — CORE-DOCTRINE بخش ۱۰ + ردیابی منشأ سند مادر بخش ۳۴.

هر رویداد یک خط JSON فقط-افزودنی است، با شناسهٔ اجرا، هش تنظیمات، نسخهٔ کد، هش دادهٔ ورودی
و زنجیرهٔ هش (هر خط هش خط قبلی را دارد) تا هر تغییر بی‌صدا قابل کشف باشد.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone

from .config import CODE_VERSION


class Ledger:
    def __init__(self, path: str | None, run_id: str, config_sha: str):
        self.path, self.run_id, self.config_sha = path, run_id, config_sha
        self.prev = "GENESIS"
        self.events: list[dict] = []
        if path:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            if os.path.exists(path):
                with open(path, encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if line:
                            self.prev = json.loads(line).get("hash", self.prev)

    def write(self, event: str, **data) -> dict:
        rec = {
            "event": event,
            "bar_ts": data.pop("ts", None),
            "logged_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "run_id": self.run_id, "config_sha": self.config_sha, "code": CODE_VERSION,
            "mode": "PAPER", **data, "prev": self.prev,
        }
        body = json.dumps(rec, sort_keys=True, ensure_ascii=False, default=str)
        rec["hash"] = hashlib.sha256(body.encode()).hexdigest()[:20]
        self.prev = rec["hash"]
        self.events.append(rec)
        if self.path:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        return rec


def verify_chain(path: str) -> dict:
    """بازبینی زنجیرهٔ هش دفتر — هر خط باید به خط قبل اشاره کند و هش خودش درست باشد."""
    prev, n, broken = "GENESIS", 0, []
    with open(path, encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            if not line.strip():
                continue
            rec = json.loads(line)
            h = rec.pop("hash", None)
            body = json.dumps(rec, sort_keys=True, ensure_ascii=False, default=str)
            if rec.get("prev") != prev or hashlib.sha256(body.encode()).hexdigest()[:20] != h:
                broken.append(i)
            prev, n = h, n + 1
    return {"ok": not broken, "lines": n, "broken_lines": broken[:20]}
