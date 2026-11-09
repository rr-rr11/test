"""ذخیره و بازیابی نشست لاگین (کوکی + localStorage) برای حساب‌های ورود با گوگل."""
import base64, json, os, time

BASE_URL = "https://rollercoin.com"


def export_session(driver) -> str:
    data = {
        "cookies": driver.get_cookies(),
        "local": driver.execute_script(
            "var o={};for(var i=0;i<localStorage.length;i++){var k=localStorage.key(i);o[k]=localStorage.getItem(k)}return o;"
        ),
    }
    return base64.b64encode(json.dumps(data).encode()).decode()


def _parse(blob: str) -> dict:
    """هم base64 (خروجی save_session.py) و هم JSON خام کوکی (خروجی Cookie-Editor) را می‌پذیرد."""
    blob = blob.strip()
    if blob[:1] in "[{":
        raw = json.loads(blob)
        if isinstance(raw, list):
            raw = {"cookies": raw, "local": {}}
    else:
        raw = json.loads(base64.b64decode(blob).decode())
    for c in raw.get("cookies", []):
        if "expirationDate" in c and "expiry" not in c:   # فرمت Cookie-Editor
            c["expiry"] = c["expirationDate"]
    return raw


def load_session(driver, blob: str) -> None:
    data = _parse(blob)
    driver.get(BASE_URL)
    time.sleep(3)
    for c in data.get("cookies", []):
        c = {k: v for k, v in c.items() if k in
             ("name", "value", "domain", "path", "secure", "httpOnly", "expiry")}
        if "expiry" in c:
            c["expiry"] = int(c["expiry"])
        try:
            driver.add_cookie(c)
        except Exception:
            c.pop("domain", None)
            try:
                driver.add_cookie(c)
            except Exception:
                pass
    for k, v in data.get("local", {}).items():
        driver.execute_script("localStorage.setItem(arguments[0], arguments[1]);", k, v)
    driver.refresh()
    time.sleep(4)
