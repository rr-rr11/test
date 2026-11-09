"""
recon.py - شناسایی ساختار واقعی صفحه بازی‌ها (روی کامپیوتر خودتان اجرا کنید)

اجرا:
  RC_EMAIL=... RC_PASSWORD=... HEADLESS=0 python recon.py

خروجی در پوشه recon/ : اسکرین‌شات، HTML رندر‌شده، لیست لینک‌ها/دکمه‌ها،
و برای هر بازی: ابعاد canvas، iframeها، و لیست درخواست‌های شبکه.
این فایل‌ها را برای من بفرستید تا منطق برد هر بازی را بنویسم.
"""
import json, os, sys, time
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from session_utils import load_session

OUT = Path("recon"); OUT.mkdir(exist_ok=True)

def pause(msg):
    """در حالت تعاملی منتظر Enter می‌ماند؛ در GitHub Actions رد می‌شود."""
    if sys.stdin.isatty():
        input(msg)
    else:
        time.sleep(5)
EMAIL, PASSWORD = os.environ.get("RC_EMAIL", ""), os.environ.get("RC_PASSWORD", "")
SESSION = os.environ.get("RC_SESSION", "")

opts = Options()
if os.environ.get("HEADLESS", "0") == "1":
    opts.add_argument("--headless=new")
opts.add_argument("--window-size=1600,1000")
opts.add_argument("--no-sandbox")
opts.add_argument("--disable-dev-shm-usage")
opts.set_capability("goog:loggingPrefs", {"performance": "ALL"})
d = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)

def dump(name):
    d.save_screenshot(str(OUT / f"{name}.png"))
    (OUT / f"{name}.html").write_text(d.page_source, encoding="utf-8")

try:
    if SESSION:
        load_session(d, SESSION)
    else:
        d.get("https://rollercoin.com/signin"); time.sleep(6)
        d.find_element(By.CSS_SELECTOR, "input[type='email'],input[name='email']").send_keys(EMAIL)
        d.find_element(By.CSS_SELECTOR, "input[type='password']").send_keys(PASSWORD)
        pause("اگر کپچا آمد حلش کنید و لاگین را کامل کنید، بعد Enter بزنید...")

    d.get("https://rollercoin.com/game/choose_game"); time.sleep(10)
    dump("choose_game")

    items = d.execute_script("""
      return [...document.querySelectorAll('a,button,[role=button],[class*=game]')].map(e=>({
        tag:e.tagName, text:(e.innerText||'').trim().slice(0,80),
        href:e.href||null, cls:e.className&&e.className.toString().slice(0,120),
        testid:e.getAttribute('data-testid')}));
    """)
    (OUT / "choose_game_elements.json").write_text(json.dumps(items, ensure_ascii=False, indent=1))
    links = sorted({i["href"] for i in items if i["href"] and "/game/" in i["href"]})
    print("game links:", *links, sep="\n  ")

    for i, url in enumerate(links):
        d.get(url); time.sleep(8)
        dump(f"game_{i}")
        info = d.execute_script("""
          return {url:location.href,
            canvases:[...document.querySelectorAll('canvas')].map(c=>({w:c.width,h:c.height,cls:c.className})),
            iframes:[...document.querySelectorAll('iframe')].map(f=>f.src),
            buttons:[...document.querySelectorAll('button')].map(b=>(b.innerText||'').trim()).filter(Boolean)};
        """)
        net = [json.loads(l["message"])["message"] for l in d.get_log("performance")]
        urls = sorted({m["params"]["request"]["url"] for m in net
                       if m.get("method") == "Network.requestWillBeSent"})
        (OUT / f"game_{i}.json").write_text(json.dumps({"info": info, "requests": urls},
                                                        ensure_ascii=False, indent=1))
        print(i, info["url"], info["canvases"])
finally:
    pause("Enter برای بستن مرورگر..."); d.quit()
