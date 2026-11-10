"""
RollerCoin bot - آموزشی.

متغیرهای محیطی:
  RC_SESSION   : توکن‌های ورود (JSON) — برای حساب‌هایی که با گوگل وارد می‌شوند
  GAMES        : اسم بازی‌ها با کاما (فعلاً فقط: 2048 Coins)
  ROUNDS       : تعداد دفعات بازی کردن هر بازی در یک اجرا (پیش‌فرض ۱)
  HEADLESS     : "1" (پیش‌فرض) یا "0"
"""
import logging
import os
import sys
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver import ActionChains
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

import game2048
from session_utils import finish_session, load_session

SESSION = os.environ.get("RC_SESSION", "")
GAMES = [g.strip() for g in os.environ.get("GAMES", "2048 Coins").split(",") if g.strip()]
ROUNDS = int(os.environ.get("ROUNDS", "1") or "1")
HEADLESS = os.environ.get("HEADLESS", "1") == "1"

DEBUG = Path("debug"); DEBUG.mkdir(exist_ok=True)
START_XP = "//button[contains(translate(normalize-space(.),'start','START'),'START')]"

# بازی -> تابع بازی‌کننده (driver, seconds, log)
BOTS = {"2048 Coins": game2048.play}

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("rc-bot").info


def setup_driver():
    o = Options()
    if HEADLESS:
        o.add_argument("--headless=new")
    for a in ("--no-sandbox", "--disable-dev-shm-usage", "--window-size=1600,1000", "--lang=en-US"):
        o.add_argument(a)
    d = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=o)
    d.set_page_load_timeout(60)
    return d


def snap(d, name):
    try:
        d.save_screenshot(str(DEBUG / f"{name}.png"))
    except Exception:
        pass


def dismiss_overlays(d):
    d.execute_script("""
      const want = ['ALLOW SELECTION', "DON'T ALLOW", '×'];
      document.querySelectorAll('button, a, div[role=button]').forEach(b => {
        const t = (b.innerText || '').trim().toUpperCase();
        if (want.includes(t)) { try { b.click(); } catch (e) {} }
      });
    """)
    time.sleep(1.5)


def open_games(d):
    d.get("https://rollercoin.com/"); time.sleep(8)
    if "sign-in" in d.current_url:
        return False
    try:
        d.execute_script("arguments[0].click();", d.find_element(By.CSS_SELECTOR, "a[href*='choose_game']"))
    except Exception:
        d.get("https://rollercoin.com/game/choose_game")
    end = time.time() + 40
    while time.time() < end and not d.find_elements(By.XPATH, START_XP):
        time.sleep(2)
    return bool(d.find_elements(By.XPATH, START_XP))


def card_name(text):
    lines = [x.strip() for x in text.split("\n") if x.strip()]
    return next((x for x in lines if x.upper() not in ("NEW", "HOT", "COMMUNITY")), "")


def click_card(d, name):
    for b in d.find_elements(By.XPATH, START_XP):
        t = d.execute_script(
            "let e=arguments[0];for(let k=0;k<4&&e.parentElement;k++){e=e.parentElement;}return e.innerText;", b)
        if card_name(t).lower() == name.lower():
            d.execute_script("arguments[0].scrollIntoView({block:'center'});", b)
            time.sleep(0.5)
            d.execute_script("arguments[0].click();", b)
            return True
    return False


def click_rel(d, fx, fy):
    c = d.find_element(By.CSS_SELECTOR, "canvas")
    d.execute_script("arguments[0].scrollIntoView({block:'center'});", c)
    time.sleep(0.5)
    w, h = c.size["width"], c.size["height"]
    ActionChains(d).move_to_element_with_offset(c, int(fx * w - w / 2), int(fy * h - h / 2)).click().perform()


def page_text(d):
    return d.execute_script("return document.body.innerText || ''")


def claim_reward(d):
    """دکمه‌ی CLAIM REWARD را می‌زند و نتیجه را چاپ می‌کند."""
    JS_CLICK = """
      for (const b of document.querySelectorAll('button, a, div[role=button]')) {
        if ((b.innerText || '').trim().toUpperCase() === 'CLAIM REWARD') { b.click(); return true; }
      }
      return false;"""
    end = time.time() + 30
    clicked = False
    while time.time() < end:
        if d.execute_script(JS_CLICK):
            clicked = True; break
        time.sleep(1)
    snap(d, "result_before_claim")
    txt = page_text(d)
    score = [ln for ln in txt.split("\n") if "point" in ln.lower() or "score" in ln.lower()][:3]
    log(f"claim clicked={clicked} score_lines={score}")
    if not clicked:
        return False
    end = time.time() + 45
    while time.time() < end:
        t = page_text(d).upper()
        if "POWER WILL REMAIN VALID" in t or "NEW HASHRATE" in t:
            break
        time.sleep(2)
    snap(d, "result_claimed")
    out = [ln for ln in page_text(d).split("\n") if "power" in ln.lower() or "hashrate" in ln.lower()][:4]
    log(f"after claim: {out}")
    return True


def play_one(d, name, n):
    tag = f"{name.replace(' ', '_')}_{n}"
    if not open_games(d):
        log("games page not available (logged out?)"); snap(d, f"{tag}_nogames"); return False
    if not click_card(d, name):
        log(f"card not found: {name}"); snap(d, f"{tag}_nocard"); return False
    end = time.time() + 40
    while time.time() < end and not d.find_elements(By.CSS_SELECTOR, "canvas"):
        time.sleep(2)
    time.sleep(6)
    dismiss_overlays(d)
    snap(d, f"{tag}_menu")
    click_rel(d, 0.5, 0.42)                      # دکمه‌ی START داخل خود بازی
    time.sleep(3)
    snap(d, f"{tag}_started")
    finished = BOTS[name](d, 72, log)
    snap(d, f"{tag}_end")
    log(f"{name}: finished={finished}")
    return claim_reward(d)


def main():
    if not SESSION:
        log("RC_SESSION تنظیم نشده است."); return 1
    d = setup_driver()
    try:
        load_session(d, SESSION)
        ok = 0
        for name in GAMES:
            if name not in BOTS:
                log(f"برای «{name}» هنوز ربات نوشته نشده؛ رد شد."); continue
            for n in range(1, ROUNDS + 1):
                log(f"=== {name} (round {n}/{ROUNDS}) ===")
                try:
                    ok += 1 if play_one(d, name, n) else 0
                except Exception:
                    logging.exception("game failed"); snap(d, f"fatal_{n}")
        log(f"done: {ok} reward(s) claimed")
        return 0
    finally:
        finish_session(d)
        d.quit()


if __name__ == "__main__":
    sys.exit(main())
