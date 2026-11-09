"""ذخیره و بازیابی نشست لاگین (کوکی + localStorage) برای حساب‌های ورود با گوگل."""
import base64, hashlib, json, os, time
from pathlib import Path

STATE_FILE = Path('session_state/state.json')
_SECRET_FP = ''

BASE_URL = "https://rollercoin.com"


def export_session(driver) -> str:
    data = {
        "cookies": driver.get_cookies(),
        "local": driver.execute_script(
            "var o={};for(var i=0;i<localStorage.length;i++){var k=localStorage.key(i);o[k]=localStorage.getItem(k)}return o;"
        ),
    }
    return base64.b64encode(json.dumps(data).encode()).decode()


def _jwt_exp(tok):
    try:
        p = tok.split(".")[1]
        p += "=" * (-len(p) % 4)
        return json.loads(base64.urlsafe_b64decode(p)).get("exp")
    except Exception:
        return None


def describe_tokens(driver, tag: str) -> None:
    """اثر انگشت کوتاه و زمان انقضای توکن‌ها را چاپ می‌کند (خود توکن هرگز چاپ نمی‌شود)."""
    t, r = driver.execute_script(
        "return [localStorage.getItem('token'), localStorage.getItem('refreshToken')]")
    now = time.time()

    def d(tok):
        if not tok:
            return "missing"
        exp = _jwt_exp(tok)
        fp = hashlib.sha256(tok.encode()).hexdigest()[:6]
        return f"fp={fp} " + (f"expires_in={int(exp - now)}s" if exp else "exp=n/a")

    print(f"[tokens:{tag}] token: {d(t)} | refresh: {d(r)}")


def finish_session(driver) -> None:
    """آخر هر اجرا: توکن‌های تازه را برای اجرای بعدی ذخیره می‌کند (با actions/cache)."""
    try:
        describe_tokens(driver, "end")
        t, r = driver.execute_script(
            "return [localStorage.getItem('token'), localStorage.getItem('refreshToken')]")
        if t and r and "sign-in" not in driver.current_url:
            STATE_FILE.parent.mkdir(exist_ok=True)
            STATE_FILE.write_text(json.dumps(
                {"secret_fp": _SECRET_FP, "local": {"token": t, "refreshToken": r}}))
            print("[session] state saved for next run")
        else:
            print("[session] not logged in at end; state not saved")
    except Exception as e:
        print("[session] finish failed:", e)


def _parse(blob: str) -> dict:
    """هم base64 (خروجی save_session.py) و هم JSON خام کوکی (خروجی Cookie-Editor) را می‌پذیرد."""
    blob = blob.strip()
    if blob[:1] in "[{":
        raw = json.loads(blob)
        if isinstance(raw, list):
            raw = {"cookies": raw, "local": {}}
        elif "cookies" not in raw and "local" not in raw:
            # فقط توکن‌ها (خروجی localStorage) داده شده؛ به‌عنوان localStorage بخوان
            raw = {"cookies": [], "local": raw}
    else:
        raw = json.loads(base64.b64decode(blob).decode())
    for c in raw.get("cookies", []):
        if "expirationDate" in c and "expiry" not in c:   # فرمت Cookie-Editor
            c["expiry"] = c["expirationDate"]
    return raw


def load_session(driver, blob: str) -> None:
    global _SECRET_FP
    _SECRET_FP = hashlib.sha256(blob.encode()).hexdigest()[:12]
    data = _parse(blob)
    # اگر اجرای قبلی توکن تازه ذخیره کرده (و Secret از آن موقع عوض نشده)، آن را ترجیح بده
    if STATE_FILE.exists():
        try:
            st = json.loads(STATE_FILE.read_text())
            if st.get("secret_fp") == _SECRET_FP:
                data["local"] = st["local"]
                print("[session] using state saved by previous run")
            else:
                print("[session] RC_SESSION changed; ignoring old state")
        except Exception as e:
            print("[session] bad state file:", e)
    # localStorage را می‌شود جدا در Secret به نام RC_LOCAL (JSON) هم داد
    extra = os.environ.get("RC_LOCAL", "").strip()
    if extra:
        data.setdefault("local", {}).update(json.loads(extra))

    driver.get(BASE_URL)
    time.sleep(3)
    added, failed = [], []
    for c in data.get("cookies", []):
        c = {k: v for k, v in c.items() if k in
             ("name", "value", "domain", "path", "secure", "httpOnly", "expiry")}
        if "expiry" in c:
            c["expiry"] = int(c["expiry"])
        try:
            driver.add_cookie(c)
            added.append(c["name"])
        except Exception:
            c.pop("domain", None)
            try:
                driver.add_cookie(c)
                added.append(c["name"])
            except Exception as e:
                failed.append(c.get("name"))
    for k, v in data.get("local", {}).items():
        if v is None:
            continue
        driver.execute_script("localStorage.setItem(arguments[0], arguments[1]);", k, str(v))

    # فقط اسم‌ها لاگ می‌شوند، نه مقدارها
    print(f"[session] cookies added={len(added)} failed={len(failed)} {failed}")
    print(f"[session] cookie names: {added}")
    print(f"[session] localStorage keys: {list(data.get('local', {}).keys())}")
    describe_tokens(driver, "loaded")
    driver.refresh()
    time.sleep(5)
    print(f"[session] url after refresh: {driver.current_url}")
    describe_tokens(driver, "after_refresh")
