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

import coinflip
import coinmatch
import cryptonoid
import game2048
import games_simple
from session_utils import finish_session, load_session

SESSION = os.environ.get("RC_SESSION", "")
GAMES = [g.strip() for g in os.environ.get("GAMES", "2048 Coins").split(",") if g.strip()]
ROUNDS = int(os.environ.get("ROUNDS", "1") or "1")
HEADLESS = os.environ.get("HEADLESS", "1") == "1"
JITTER = os.environ.get("JITTER", "0") == "1"   # در اجرای زمان‌بندی‌شده: تأخیر تصادفی تا ۴ دقیقه

DEBUG = Path("debug"); DEBUG.mkdir(exist_ok=True)
START_XP = "//button[contains(translate(normalize-space(.),'start','START'),'START')]"

# بازی -> تابع بازی‌کننده (driver, seconds, log)
BOTS = {
    "2048 Coins": game2048.play,
    "Coin-Flip": coinflip.play,
    "Coin-match": coinmatch.play,
    "Cryptonoid": cryptonoid.play,          # جدید: هنوز روی بازی واقعی آزموده نشده
    "Lambo Rider": games_simple.play_idle,   # آزمایشی: بدون حرکت
}

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
    # کارت‌ها تنبل بارگذاری می‌شوند؛ صبر کن تا تعدادشان پایدار شود (یا حداقل ۱۲ تا)
    end, prev, stable = time.time() + 25, -1, 0
    while time.time() < end:
        n = len(d.find_elements(By.XPATH, START_XP))
        stable = stable + 1 if n == prev else 0
        if n >= 12 or (n > 0 and stable >= 3):
            break
        prev = n
        time.sleep(1.5)
    return bool(d.find_elements(By.XPATH, START_XP))


def card_name(text):
    lines = [x.strip() for x in text.split("\n") if x.strip()]
    return next((x for x in lines if x.upper() not in ("NEW", "HOT", "COMMUNITY")), "")


def click_card(d, name):
    """کارت بازی را پیدا و کلیک می‌کند؛ اگر هنوز بارگذاری نشده، صفحه را اسکرول می‌کند و دوباره می‌گردد."""
    for attempt in range(8):
        for b in d.find_elements(By.XPATH, START_XP):
            t = d.execute_script(
                "let e=arguments[0];for(let k=0;k<4&&e.parentElement;k++){e=e.parentElement;}return e.innerText;", b)
            if card_name(t).lower() == name.lower():
                d.execute_script("arguments[0].scrollIntoView({block:'center'});", b)
                time.sleep(0.5)
                d.execute_script("arguments[0].click();", b)
                return True
        log(f"card {name!r} not visible yet (attempt {attempt + 1}); scrolling")
        d.execute_script("window.scrollBy(0, 650);")
        time.sleep(1.5)
    return False


def click_rel(d, fx, fy):
    c = d.find_element(By.CSS_SELECTOR, "canvas")
    d.execute_script("arguments[0].scrollIntoView({block:'center'});", c)
    time.sleep(0.5)
    w, h = c.size["width"], c.size["height"]
    ActionChains(d).move_to_element_with_offset(c, int(fx * w - w / 2), int(fy * h - h / 2)).click().perform()


def page_text(d):
    return d.execute_script("return document.body.innerText || ''")


def log_pc_status(d, tag):
    """وضعیت سطح PC را از بالای صفحه‌ی بازی‌ها در لاگ می‌نویسد (برای پیگیری بالا رفتن سطح)."""
    try:
        keys = ("pc ", "power holding", "level reset", "next pc level")
        lines = [ln.strip() for ln in page_text(d).split("\n") if any(k in ln.lower() for k in keys)]
        log(f"[pc:{tag}] " + " | ".join(lines[:5]))
    except Exception as e:
        log(f"[pc:{tag}] unavailable: {e}")


def collect_bonus(d, wait=8):
    """پاپ‌آپ «CONGRATULATIONS / Free power ... COLLECT» را (فقط اگر ظاهر شد) می‌بندد و دکمه‌ی COLLECT را می‌زند."""
    JS = """
      if (!(document.body.innerText || '').toUpperCase().includes('CONGRATULATIONS')) return null;
      const txt = ((document.body.innerText.match(/Free power[^\\n]*/i) || [''])[0]);
      for (const b of document.querySelectorAll('button, a, div[role=button]')) {
        if ((b.innerText || '').trim().toUpperCase() === 'COLLECT') { b.click(); return txt || 'collected'; }
      }
      return null;"""
    end, got = time.time() + wait, 0
    while time.time() < end:
        r = d.execute_script(JS)
        if r is not None:
            got += 1
            log(f"bonus collected: {r}")
            snap(d, f"bonus_{int(time.time())}")
            time.sleep(1.5)
        else:
            time.sleep(1)
    return got


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
    collect_bonus(d, 8)
    return True


def play_one(d, name, n):
    tag = f"{name.replace(' ', '_')}_{n}"
    for attempt in range(1, 4):
        if not open_games(d):
            log("games page not available (logged out?)"); snap(d, f"{tag}_nogames"); return False
        collect_bonus(d, 3)
        if click_card(d, name):
            break
        # بعد از هر بازی، کارتش حدود یک دقیقه غیرفعال می‌شود؛ صبر می‌کنیم و صفحه را دوباره می‌گیریم
        log(f"card {name!r} not available (attempt {attempt}/3); waiting 50s then reloading")
        snap(d, f"{tag}_nocard{attempt}")
        time.sleep(50)
    else:
        log(f"card not found: {name}"); return False
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
    if JITTER:
        import random
        delay = random.randint(0, 240)
        log(f"scheduled run: waiting {delay}s before starting")
        time.sleep(delay)
    d = setup_driver()
    try:
        load_session(d, SESSION)
        ok = 0
        if open_games(d):
            log_pc_status(d, "start")
        games = []
        for name in GAMES:
            if name in BOTS:
                games.append(name)
            else:
                log(f"برای «{name}» هنوز ربات نوشته نشده؛ رد شد.")
        for n in range(1, ROUNDS + 1):                 # دور به دور؛ هر دور همه‌ی بازی‌ها به ترتیب
            for name in games:
                log(f"=== round {n}/{ROUNDS}: {name} ===")
                try:
                    ok += 1 if play_one(d, name, n) else 0
                except Exception:
                    logging.exception("game failed"); snap(d, f"fatal_{name.replace(' ', '_')}_{n}")
        if open_games(d):
            log_pc_status(d, "end")
        log(f"done: {ok} reward(s) claimed")
        return 0
    finally:
        finish_session(d)
        d.quit()


if __name__ == "__main__":
    sys.exit(main())
