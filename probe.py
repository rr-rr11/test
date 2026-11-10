"""
probe.py - از چند بازی عکس می‌گیرد تا برای هر کدام ربات نوشت.

متغیر محیطی:  GAMES = اسم بازی‌ها با کاما، مثل "Coin-Flip,Coin-match"
برای هر بازی (پوشه‌ی probe/):
  <slug>_menu_canvas.png   صفحه‌ی شروع بازی با راهنمای کنترل
  <slug>_t04/t09/t15/t25_canvas.png   بازی بعد از START در چند لحظه (بدون هیچ حرکتی)
  <slug>_t25_full.png      کل صفحه
این اسکریپت فقط START می‌زند و صبر می‌کند؛ هیچ حرکتی در بازی نمی‌کند.
"""
import json, os, re, time
from pathlib import Path
from selenium import webdriver
from selenium.webdriver import ActionChains
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from session_utils import load_session, finish_session

GAMES = [g.strip() for g in (os.environ.get("GAMES") or os.environ.get("GAME") or "Coin-Flip").split(",") if g.strip()]
SESSION = os.environ.get("RC_SESSION", "")
OUT = Path("probe"); OUT.mkdir(exist_ok=True)
START_XP = "//button[contains(translate(normalize-space(.),'start','START'),'START')]"

opts = Options()
if os.environ.get("HEADLESS", "1") == "1":
    opts.add_argument("--headless=new")
for a in ("--no-sandbox", "--disable-dev-shm-usage", "--window-size=1600,1000"):
    opts.add_argument(a)
d = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)


def slug(n):
    return re.sub(r"[^a-z0-9]+", "_", n.lower()).strip("_")


def full(name):
    d.save_screenshot(str(OUT / f"{name}.png"))


def canvas_shot(name):
    try:
        d.find_element(By.CSS_SELECTOR, "canvas").screenshot(str(OUT / f"{name}_canvas.png"))
    except Exception as e:
        print("[probe] canvas shot failed:", name, e)


def dismiss_overlays():
    d.execute_script("""
      const want = ['ALLOW SELECTION', "DON'T ALLOW", '×'];
      document.querySelectorAll('button, a, div[role=button]').forEach(b => {
        const t = (b.innerText || '').trim().toUpperCase();
        if (want.includes(t)) { try { b.click(); } catch (e) {} }
      });
    """)
    time.sleep(1.5)


def card_name(text):
    lines = [x.strip() for x in text.split("\n") if x.strip()]
    return next((x for x in lines if x.upper() not in ("NEW", "HOT", "COMMUNITY")), "")


def open_games():
    d.get("https://rollercoin.com/"); time.sleep(8)
    try:
        d.execute_script("arguments[0].click();", d.find_element(By.CSS_SELECTOR, "a[href*='choose_game']"))
    except Exception:
        d.get("https://rollercoin.com/game/choose_game")
    end = time.time() + 40
    while time.time() < end and not d.find_elements(By.XPATH, START_XP):
        time.sleep(2)


def click_rel(fx, fy):
    canvas = d.find_element(By.CSS_SELECTOR, "canvas")
    d.execute_script("arguments[0].scrollIntoView({block:'center'});", canvas)
    time.sleep(0.5)
    w, h = canvas.size["width"], canvas.size["height"]
    ActionChains(d).move_to_element_with_offset(canvas, int(fx * w - w / 2), int(fy * h - h / 2)).click().perform()


def probe(name):
    s = slug(name)
    print(f"[probe] === {name} ===")
    open_games()
    target = None
    for b in d.find_elements(By.XPATH, START_XP):
        t = d.execute_script(
            "let e=arguments[0];for(let k=0;k<4&&e.parentElement;k++){e=e.parentElement;}return e.innerText;", b)
        if card_name(t).lower() == name.lower():
            target = b; break
    if target is None:
        print("[probe] card not found:", name); full(f"{s}_card_not_found"); return
    d.execute_script("arguments[0].scrollIntoView({block:'center'});", target)
    time.sleep(0.5)
    d.execute_script("arguments[0].click();", target)

    end = time.time() + 40
    while time.time() < end and not d.find_elements(By.CSS_SELECTOR, "canvas"):
        time.sleep(2)
    time.sleep(6)
    dismiss_overlays()
    full(f"{s}_menu"); canvas_shot(f"{s}_menu")
    # کنترل‌ها پایین canvas هستند؛ صفحه را کمی پایین ببر و یک عکس کل صفحه هم بگیر
    d.execute_script("window.scrollBy(0, 350);"); time.sleep(0.5); full(f"{s}_menu_scrolled")
    d.execute_script("window.scrollBy(0, -350);"); time.sleep(0.5)

    click_rel(0.5, 0.42)         # START داخل بازی
    t0 = time.time()
    for tag, at in (("t04", 4), ("t09", 9), ("t15", 15), ("t25", 25)):
        time.sleep(max(0, at - (time.time() - t0)))
        canvas_shot(f"{s}_{tag}")
        if tag == "t25":
            full(f"{s}_{tag}_full")
    print(f"[probe] done: {name}")


try:
    if SESSION:
        load_session(d, SESSION)
    for g in GAMES:
        try:
            probe(g)
        except Exception as e:
            print(f"[probe] {g} failed:", e)
            full(f"{slug(g)}_error")
finally:
    try:
        finish_session(d)
    except Exception:
        pass
    d.quit()
