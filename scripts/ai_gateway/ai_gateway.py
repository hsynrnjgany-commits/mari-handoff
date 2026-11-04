# scripts/ai_gateway/ai_gateway.py - PAPER ONLY | NO LIVE ORDERS
# حسابرسی مستقل دو-مدلی (DeepSeek + GLM) روی متن داده‌شده — فقط متن، هیچ سفارشی نیست
# بازسازی 2026-11-02T01:2xZ بعد از گم‌شدن در بازیابی ساندباکس (فایل هرگز کامیت نشده بود)
# شامل هر سه پچ قبلی: thinking disabled برای glm، max_tokens 3000، EMPTY_CONTENT
# پچ 2026-11-03 (فرمان رییس):
#  ۱) کلید خالی/placeholder = SKIPPED_NO_KEY (نه خطا) — فقط ارائه‌دهندهٔ دارای کلید اجرا می‌شود
#  ۲) بین هر دو درخواست GLM حداقل ۸ ثانیه فاصله (GLM_MIN_GAP_S)
#  ۳) روی HTTP 429 فقط یک بار بعد از ۴۵ ثانیه تلاش مجدد؛ شکست مجدد = verdict=NO_VERDICT + دلیل واقعی
# پچ 2026-11-04 (فرمان رییس): 429 با کد ۱۱۱۳ یا عبارت Insufficient balance = NO_BALANCE
#  — بدون هیچ تلاش مجدد (رای کشک است، retry بی‌معناست)؛ retry ۴۵ ثانیه‌ای فقط برای 429 بدون ۱۱۱۳.
import os, sys, re, json, time, uuid, datetime, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))  # سخت‌سازی: اجرا از هر پوشه‌ای درست کار می‌کند
RECORDS = os.path.join(HERE, "records")
ROOT = os.path.dirname(os.path.dirname(HERE))  # ریشهٔ پروژه — جایی که .env زندگی می‌کند

# لودر کوچک .env: کلیدها از فایل پروژه خوانده می‌شوند؛ متغیر محیطی موجود اولویت دارد.
# هیچ مقداری چاپ نمی‌شود. (پایتون برخلاف Next.js خودش .env را نمی‌خواند)
def _load_keyfile(p):
    if not os.path.isfile(p):
        return
    for line in open(p, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v

def _load_dotenv():
    # ۱) .env استاندارد پروژه
    _load_keyfile(os.path.join(ROOT, ".env"))
    # ۲) امنیت (سخت‌سازی 2026-11-02): vault خصوصی به‌عنوان منبع پایدار کلیدها —
    #    .env توسط بازیابی ساندباکس بازنشانی می‌شود؛ data/vault-private/keys.env (600+gitignore) می‌ماند.
    #    فقط کلیدهای «مفقود» پر می‌شوند؛ هیچ مقداری چاپ نمی‌شود.
    _load_keyfile(os.path.join(ROOT, "data", "vault-private", "keys.env"))

_load_dotenv()

P = {
 "deepseek": ("AI-07a", "DEEPSEEK_API_KEY", "https://api.deepseek.com/chat/completions", "deepseek-chat"),
 "glm": ("AI-07b", "ZAI_API_KEY", "https://api.z.ai/api/paas/v4/chat/completions", "glm-4.6"),
}
VERDICTS = ("SUPPORTED", "UNSUPPORTED", "INSUFFICIENT_EVIDENCE")
NO_VERDICT = "NO_VERDICT"  # پچ 2026-11-03: هر نتیجهٔ بدون حکم واقعی این برچسب را می‌گیرد

# پچ 2026-11-03 (بند ۱): تشخیص کلید خالی/placeholder — هیچ مقدار کلیدی چاپ نمی‌شود
_PLACEHOLDER_TOKENS = ("PASTE_KEY", "PLACEHOLDER", "YOUR_API_KEY", "YOUR_KEY", "CHANGE_ME", "CHANGEME", "TODO", "XXX", "SET_YOUR", "ENTER_")

def _key_usable(k):
    if not k:
        return False
    ku = k.strip().upper()
    if not ku:
        return False
    if any(tok in ku for tok in _PLACEHOLDER_TOKENS):
        return False
    return True

# پچ 2026-11-03 (بند ۲): فاصلهٔ حداقلی بین درخواست‌های GLM در همین فرایند
GLM_MIN_GAP_S = 8.0
GLM_429_RETRY_WAIT_S = 45.0  # بند ۳: روی 429 فقط یک بار بعد از ۴۵ ثانیه
_GLM_LAST_TS = {"t": 0.0}

def _glm_gap():
    wait = GLM_MIN_GAP_S - (time.time() - _GLM_LAST_TS["t"])
    if wait > 0:
        time.sleep(wait)

LIST_KEYS = ("evidence", "limitations", "suggested_validation")  # اگر آمدند باید لیست باشند
SYSTEM = ("You are an independent auditor for a PAPER-ONLY market research system. "
 "Use ONLY the numbers in the given text. Never invent data. Reply with ONE JSON object only, keys: "
 "verdict (SUPPORTED|UNSUPPORTED|INSUFFICIENT_EVIDENCE), hypothesis, evidence (list of short quotes from the text), "
 "limitations (list), uncertainty (0..1), suggested_validation (list). Write strings in Persian.")

def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def call(name, task):
    agent, kenv, url, model = P[name]
    model = os.environ.get(name.upper() + "_MODEL", model)
    rec = {"message_id": str(uuid.uuid4()), "agent_id": agent, "provider": name, "model": model,
           "generated_at": now(), "schema_version": "gw-0.1", "status": "PENDING",
           "validation_status": "UNVALIDATED"}
    key = os.environ.get(kenv)
    if not _key_usable(key):
        # پچ 2026-11-03 (بند ۱): خالی/placeholder خطا نیست — SKIPPED_NO_KEY و اجرا نمی‌شود
        rec["status"] = "SKIPPED_NO_KEY"
        rec["reason"] = "کلید %s خالی یا placeholder است — اجرا نشد" % kenv
        return rec
    payload = {"model": model, "temperature": 0, "max_tokens": 2000,
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": task}]}
    if name == "glm":
        # GLM-4.5+: فاز تفکر پیش‌فرض می‌تواند کل بودجهٔ توکن را ببلعد و content خالی برگرداند
        # (اتفاق واقعی HUNTAUD-20261101T233308Z: completion_tokens=2000، content="")
        payload["thinking"] = {"type": "disabled"}
        payload["max_tokens"] = 3000
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json", "Authorization": "Bearer " + key})
    t0 = time.time()
    text = None
    think = ""
    # پچ 2026-11-03 (بند ۲/۳): فاصلهٔ ≥۸s قبل از هر درخواست GLM؛ روی 429 فقط یک تلاش مجدد بعد از ۴۵s
    # پچ 2026-11-04: 429 با کد ۱۱۱۳ / Insufficient balance = NO_BALANCE بدون تلاش مجدد
    retries_left = 1 if name == "glm" else 0
    while True:
        try:
            if name == "glm":
                _glm_gap()
                _GLM_LAST_TS["t"] = time.time()
            with urllib.request.urlopen(req, timeout=90) as r:
                data = json.loads(r.read())
            msg = data["choices"][0]["message"]
            text = msg.get("content") or ""
            think = msg.get("reasoning_content") or ""
            rec["usage"] = data.get("usage")
            rec["reasoning_chars"] = len(think)
            break
        except urllib.error.HTTPError as e:
            body_txt = ""
            try:  # سخت‌سازی: بدنهٔ خطای واقعی ارائه‌دهنده ثبت شود (این بدنه کلید ندارد)
                body_txt = e.read().decode("utf-8", "replace").strip()[:300]
            except Exception:
                pass
            # پچ 2026-11-04: تشخیص موجودی صفر (کد ۱۱۱۳ / Insufficient balance) در همان تلاش اول
            if name == "glm" and e.code == 429 and ("1113" in body_txt or "Insufficient balance" in body_txt):
                rec["status"] = "NO_BALANCE"  # verdict=NO_VERDICT در run() ثبت می‌شود
                if body_txt:
                    rec["error_body"] = body_txt
                break
            if name == "glm" and e.code == 429 and retries_left > 0:
                retries_left -= 1
                rec["note_429"] = "HTTP_429 در تلاش اول؛ تلاش مجدد بعد از ۴۵ ثانیه"
                if body_txt:
                    rec["error_body_1st"] = body_txt
                time.sleep(GLM_429_RETRY_WAIT_S)
                continue
            rec["status"] = "HTTP_%d" % e.code
            if body_txt:
                rec["error_body"] = body_txt
            break
        except Exception as e:
            rec["status"] = "ERR_" + type(e).__name__
            break
    rec["latency_s"] = round(time.time() - t0, 2)
    if text is not None:
        if not text.strip():
            # تشخیص صادقانه: پاسخ خالی (معمولاً تفکر بودجه را خورده) — به‌جای PARSE_FAILED مبهم
            rec["status"] = "EMPTY_CONTENT"
            if think:
                rec["raw"] = think[:1500]
            return rec
        try:
            out = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
            if out.get("verdict") not in VERDICTS:
                raise ValueError("bad verdict")
            for k in LIST_KEYS:  # سخت‌سازی: نوع لیستی — فقط وقتی کلید در پاسخ هست
                if k in out and not isinstance(out[k], list):
                    raise ValueError("bad type: " + k)
            rec["output"] = out
            rec["status"] = "OK"
        except Exception:
            rec["status"] = "PARSE_FAILED"
            rec["raw"] = text[:3000]
    return rec

def run(task):
    res = [call(n, task) for n in P]
    # پچ 2026-11-03 (بند ۳): هر نتیجهٔ بدون حکم واقعی = NO_VERDICT + دلیل واقعی (بدنهٔ خطا)
    v = []
    reasons = []
    for r in res:
        verdict = (r.get("output") or {}).get("verdict")
        if verdict not in VERDICTS:
            reason = r.get("status", "?")
            if r.get("error_body"):
                reason += ": " + str(r["error_body"])[:160]
            reasons.append({"provider": r.get("provider"), "reason": reason})
            verdict = NO_VERDICT
        v.append(verdict)
    real_all = all(x in VERDICTS for x in v)
    s = {"task_time": now(), "verdicts": v,
         "disagreement": (len(set(v)) > 1) if real_all else None,
         "reasons": reasons, "results": res}
    os.makedirs(RECORDS, exist_ok=True)
    with open(os.path.join(RECORDS, "log.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(s, ensure_ascii=False) + "\n")
    return s

if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["--file"]:
        if len(a) < 2:  # سخت‌سازی: گارد ورودی — بدون traceback
            print("استفاده: ai_gateway.py --file <مسیر-متن> | ai_gateway.py <متن>")
            sys.exit(2)
        task = open(a[1], encoding="utf-8").read()
    else:
        task = " ".join(a)
    if not task.strip():  # سخت‌سازی: ورودی خالی به API فرستاده نمی‌شود
        print("ورودی خالی است — هیچ تماسی زده نشد.")
        sys.exit(2)
    s = run(task)
    for r in s["results"]:
        o = r.get("output", {})
        print(r["provider"], r["status"], r.get("latency_s"), o.get("verdict"))
        if r.get("error_body"):
            print("   ", r["error_body"][:120])
        print("  ", o.get("hypothesis", ""))
    print("اختلاف نظر:", s["disagreement"])

# END_OF_FILE
