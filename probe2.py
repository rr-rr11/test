"""
probe2.py - بازی‌های تعاملی (Coin-Flip و Coin-match): چند کلیک آزمایشی می‌زند و بعد از هر کدام عکس می‌گیرد
تا بفهمیم بازی با کلیک چه می‌کند (کارت چطور برمی‌گردد، سکه‌ها چطور حذف می‌شوند و ...).
فقط چند کلیک مشخص می‌زند؛ بازی را کامل نمی‌کند.
خروجی در probe2/ . متغیر GAMES: "Coin-Flip,Coin-match"
"""
import os, re, time
from pathlib import Path
from selenium import webdriver
from selenium.webdriver import ActionChains
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from session_utils import load_session, finish_session

GAMES = [g.strip() for g in (os.environ.get("GAMES") or "Coin-Flip,Coin-match").split(",") if g.strip()]
SESSION = os.environ.get("RC_SESSION", "")
OUT = Path("probe2"); OUT.mkdir(exist_ok=True)
START_XP = "//button[contains(translate(normalize-space(.),'start','START'),'START')]"

# مختصات نسبی (۰ تا ۱) از عکس‌های واقعی هر بازی
FLIP_X = [261 / 831, 411 / 831, 561 / 831]
FLIP_Y = [161 / 717, 313 / 717, 467 / 717, 620 / 717]
MATCH_X = [(173 + 69.1 * i) / 831 for i in range(8)]
MATCH_Y = [(62 + 69.4 * j) / 623 for j in range(8)]

SCRIPTS = {
    # (کار, آرگومان‌ها): click(fx,fy) | shot(برچسب) | wait(ثانیه)
    "Coin-Flip": [
        ("wait", 2), ("shot", "a0_before"),
        ("click", FLIP_X[0], FLIP_Y[0]), ("wait", 0.3), ("shot", "a1_card00_0.3s"), ("wait", 0.7), ("shot", "a2_card00_1.0s"),
        ("wait", 1.5), ("shot", "a3_card00_2.5s"),
        ("click", FLIP_X[1], FLIP_Y[0]), ("wait", 0.3), ("shot", "b1_card01_0.3s"), ("wait", 0.7), ("shot", "b2_card01_1.0s"),
        ("wait", 1.5), ("shot", "b3_card01_2.5s"), ("wait", 2.0), ("shot", "b4_card01_4.5s"),
        ("click", FLIP_X[2], FLIP_Y[3]), ("wait", 1.0), ("shot", "c1_card32_1.0s"),
        ("click", FLIP_X[0], FLIP_Y[2]), ("wait", 1.0), ("shot", "c2_card20_1.0s"), ("wait", 3.0), ("shot", "c3_after"),
    ],
    "Coin-match": [
        ("wait", 2), ("shot", "a0_before"),
        # دو ETH بالای هم در ستون ۰: (ردیف ۰ و ۱)
        ("click", MATCH_X[0], MATCH_Y[0]), ("wait", 0.4), ("shot", "a1_click00_0.4s"), ("wait", 1.2), ("shot", "a2_click00_1.6s"),
        # یک سکه‌ی منفرد/دیگر
        ("click", MATCH_X[3], MATCH_Y[3]), ("wait", 0.4), ("shot", "b1_click33_0.4s"), ("wait", 1.2), ("shot", "b2_click33_1.6s"),
        # دو کلیک پشت‌هم روی خانه‌های مجاور (برای دیدن حالت «جابه‌جایی»)
        ("click", MATCH_X[5], MATCH_Y[5]), ("wait", 0.4), ("shot", "c1_click55_0.4s"),
        ("click", MATCH_X[6], MATCH_Y[5]), ("wait", 0.5), ("shot", "c2_click65_0.5s"), ("wait", 1.5), ("shot", "c3_after"),
    ],
}

opts = Options()
if os.environ.get("HEADLESS", "1") == "1":
    opts.add_argument("--headless=new")
for a in ("--no-sandbox", "--disable-dev-shm-usage", "--window-size=1600,1000"):
    opts.add_argument(a)
d = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)


def slug(n):
    return re.sub(r"[^a-z0-9]+", "_", n.lower()).strip("_")


def card_name(text):
    lines = [x.strip() for x in text.split("\n") if x.strip()]
    return next((x for x in lines if x.upper() not in ("NEW", "HOT", "COMMUNITY")), "")


def dismiss_overlays():
    d.execute_script("""
      const want = ['ALLOW SELECTION', "DON'T ALLOW", '×'];
      document.querySelectorAll('button, a, div[role=button]').forEach(b => {
        const t = (b.innerText || '').trim().toUpperCase();
        if (want.includes(t)) { try { b.click(); } catch (e) {} }
      });
    """)
    time.sleep(1.5)


def click_rel(fx, fy):
    c = d.find_element(By.CSS_SELECTOR, "canvas")
    w, h = c.size["width"], c.size["height"]
    ActionChains(d).move_to_element_with_offset(c, int(fx * w - w / 2), int(fy * h - h / 2)).click().perform()


def run(name):
    s = slug(name)
    print(f"[probe2] === {name} ===")
    d.get("https://rollercoin.com/"); time.sleep(8)
    try:
        d.execute_script("arguments[0].click();", d.find_element(By.CSS_SELECTOR, "a[href*='choose_game']"))
    except Exception:
        d.get("https://rollercoin.com/game/choose_game")
    end = time.time() + 40
    while time.time() < end and not d.find_elements(By.XPATH, START_XP):
        time.sleep(2)
    target = None
    for b in d.find_elements(By.XPATH, START_XP):
        t = d.execute_script("let e=arguments[0];for(let k=0;k<4&&e.parentElement;k++){e=e.parentElement;}return e.innerText;", b)
        if card_name(t).lower() == name.lower():
            target = b; break
    if target is None:
        print("[probe2] card not found:", name); return
    d.execute_script("arguments[0].scrollIntoView({block:'center'});", target); time.sleep(0.5)
    d.execute_script("arguments[0].click();", target)
    end = time.time() + 40
    while time.time() < end and not d.find_elements(By.CSS_SELECTOR, "canvas"):
        time.sleep(2)
    time.sleep(6); dismiss_overlays()
    c = d.find_element(By.CSS_SELECTOR, "canvas")
    d.execute_script("window.scrollBy(0, arguments[0].getBoundingClientRect().top - 100);", c); time.sleep(0.5)
    click_rel(0.5, 0.42)                    # START داخل بازی
    time.sleep(4)                            # انیمیشن GO!
    n = 0
    for step in SCRIPTS[name]:
        kind = step[0]
        if kind == "wait":
            time.sleep(step[1])
        elif kind == "click":
            click_rel(step[1], step[2])
        elif kind == "shot":
            n += 1
            d.find_element(By.CSS_SELECTOR, "canvas").screenshot(str(OUT / f"{s}_{n:02d}_{step[1]}.png"))
    print(f"[probe2] done: {name} ({n} shots)")


try:
    if SESSION:
        load_session(d, SESSION)
    for g in GAMES:
        try:
            if g in SCRIPTS:
                run(g)
            else:
                print("[probe2] no script for", g)
        except Exception as e:
            print(f"[probe2] {g} failed:", e)
            d.save_screenshot(str(OUT / f"{slug(g)}_error.png"))
finally:
    try:
        finish_session(d)
    except Exception:
        pass
    d.quit()
