"""
RollerCoin bot - آموزشی (Selenium 4.10 + webdriver-manager)

متغیرهای محیطی:
  RC_EMAIL, RC_PASSWORD  : اطلاعات ورود (در GitHub Secrets بگذارید)
  HEADLESS               : "1" (پیش‌فرض) یا "0" برای دیدن مرورگر
"""
import logging
import os
import random
import sys
import time
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver import ActionChains
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from session_utils import load_session, finish_session

# ───────────────────────── تنظیمات ─────────────────────────
BASE_URL = "https://rollercoin.com"
LOGIN_URL = f"{BASE_URL}/signin"
GAMES_URL = f"{BASE_URL}/game/choose_game"

SESSION = os.environ.get("RC_SESSION", "")
EMAIL = os.environ.get("RC_EMAIL", "")
PASSWORD = os.environ.get("RC_PASSWORD", "")
HEADLESS = os.environ.get("HEADLESS", "1") == "1"

DEBUG_DIR = Path("debug")
DEBUG_DIR.mkdir(exist_ok=True)

MAX_GAMES_PER_RUN = 10
GAME_PLAY_SECONDS = 45                  # مدت تعامل با هر بازی

# چند سلکتور جایگزین برای هر المان؛ اولین موردی که پیدا شود استفاده می‌شود.
# اگر سایت تغییر کرد، فقط همین بخش را با DevTools اصلاح کنید.
SEL = {
    "cookie_accept": [
        "button#onetrust-accept-btn-handler",
        "button[class*='cookie'][class*='accept']",
    ],
    "email": ["input[type='email']", "input[name='email']", "input#email"],
    "password": ["input[type='password']", "input[name='password']", "input#password"],
    "submit": ["button[type='submit']"],
}

XPATH_PLAY = (
    "//*[self::button or self::a]"
    "[contains(translate(normalize-space(.), 'PLAY', 'play'), 'play')]"
)
XPATH_COLLECT = (
    "//*[self::button or self::a]"
    "[contains(translate(normalize-space(.), 'COLLECTLAIMGR', 'collectlaimgr'), 'collect')"
    " or contains(translate(normalize-space(.), 'CLAIM', 'claim'), 'claim')"
    " or contains(translate(normalize-space(.), 'GETREWAD', 'getrewad'), 'get reward')]"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("rc-bot")


# ───────────────────────── ابزارها ─────────────────────────
def setup_driver() -> webdriver.Chrome:
    opts = Options()
    if HEADLESS:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--lang=en-US")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=opts
    )
    driver.set_page_load_timeout(60)
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"},
    )
    return driver


def snap(driver, name: str) -> None:
    """اسکرین‌شات + HTML برای دیباگ."""
    try:
        driver.save_screenshot(str(DEBUG_DIR / f"{name}.png"))
        (DEBUG_DIR / f"{name}.html").write_text(driver.page_source, encoding="utf-8")
        log.info("debug saved: %s", name)
    except WebDriverException as e:
        log.warning("snap failed: %s", e)


def find_first(driver, selectors, timeout=15, clickable=False):
    """اولین سلکتوری که در زمان مجاز پیدا شود را برمی‌گرداند."""
    end = time.time() + timeout
    cond = EC.element_to_be_clickable if clickable else EC.visibility_of_element_located
    while time.time() < end:
        for s in selectors:
            try:
                return WebDriverWait(driver, 1).until(cond((By.CSS_SELECTOR, s)))
            except TimeoutException:
                continue
    raise TimeoutException(f"none of selectors found: {selectors}")


def safe_click(driver, el) -> bool:
    try:
        el.click()
        return True
    except (ElementClickInterceptedException, WebDriverException):
        try:
            driver.execute_script("arguments[0].click();", el)
            return True
        except WebDriverException:
            return False


def dismiss_cookies(driver) -> None:
    try:
        btn = find_first(driver, SEL["cookie_accept"], timeout=4, clickable=True)
        safe_click(driver, btn)
        log.info("cookie banner dismissed")
    except TimeoutException:
        pass


# ───────────────────────── ورود ─────────────────────────
def login_with_session(driver) -> bool:
    """ورود با نشست ذخیره‌شده (برای حساب‌های ورود با گوگل)."""
    load_session(driver, SESSION)
    driver.get(GAMES_URL)
    time.sleep(6)
    snap(driver, "session_check")
    if "signin" in driver.current_url:
        log.error("نشست منقضی شده؛ save_session.py را دوباره اجرا کنید و RC_SESSION را عوض کنید.")
        return False
    log.info("session login OK -> %s", driver.current_url)
    return True


def login(driver) -> bool:
    if SESSION:
        return login_with_session(driver)
    if not EMAIL or not PASSWORD:
        log.error("RC_EMAIL / RC_PASSWORD تنظیم نشده‌اند.")
        return False

    driver.get(LOGIN_URL)
    dismiss_cookies(driver)

    try:
        email = find_first(driver, SEL["email"], timeout=20)
        pwd = find_first(driver, SEL["password"], timeout=10)
    except TimeoutException:
        snap(driver, "login_form_not_found")
        return False

    email.clear()
    email.send_keys(EMAIL)
    pwd.clear()
    pwd.send_keys(PASSWORD)
    snap(driver, "login_filled")

    try:
        safe_click(driver, find_first(driver, SEL["submit"], timeout=10, clickable=True))
    except TimeoutException:
        pwd.send_keys("\n")

    # موفقیت = خروج از صفحه signin
    try:
        WebDriverWait(driver, 30).until(lambda d: "signin" not in d.current_url)
    except TimeoutException:
        snap(driver, "login_failed")  # احتمالاً کپچا یا رمز اشتباه
        log.error("ورود ناموفق (کپچا / رمز اشتباه / بلاک IP). debug را ببینید.")
        return False

    log.info("login OK -> %s", driver.current_url)
    snap(driver, "after_login")
    return True


# ───────────────────────── بازی‌ها ─────────────────────────
def click_collect_if_any(driver) -> bool:
    for el in driver.find_elements(By.XPATH, XPATH_COLLECT):
        try:
            if el.is_displayed() and safe_click(driver, el):
                log.info("reward button clicked: %r", el.text.strip()[:30])
                return True
        except StaleElementReferenceException:
            continue
    return False


def play_generic(driver, seconds: int) -> None:
    """
    هندلر عمومی: روی canvas بازی کلیک تصادفی می‌زند.
    ⚠️ بازی‌های RollerCoin قوانین متفاوتی دارند و این هندلر فقط یک نقطه شروع است.
    برای هر بازی باید منطق اختصاصی بنویسید (به PLAYERS پایین فایل نگاه کنید).
    """
    try:
        canvas = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "canvas"))
        )
    except TimeoutException:
        log.warning("canvas پیدا نشد")
        return

    size = canvas.size
    end = time.time() + seconds
    actions = ActionChains(driver)
    while time.time() < end:
        x = random.randint(-size["width"] // 2 + 10, size["width"] // 2 - 10)
        y = random.randint(-size["height"] // 2 + 10, size["height"] // 2 - 10)
        try:
            actions.move_to_element_with_offset(canvas, x, y).click().perform()
        except WebDriverException:
            break
        time.sleep(random.uniform(0.15, 0.4))


# نام بخشی از URL بازی -> تابع اختصاصی (driver, seconds)
PLAYERS = {
    # "coinclick": play_coinclick,
}


def pick_player(url: str):
    for key, fn in PLAYERS.items():
        if key in url:
            return fn
    return play_generic


def play_games(driver) -> None:
    driver.get(GAMES_URL)
    time.sleep(4)
    dismiss_cookies(driver)
    snap(driver, "games_page")

    played = 0
    while played < MAX_GAMES_PER_RUN:
        buttons = [b for b in driver.find_elements(By.XPATH, XPATH_PLAY) if b.is_displayed()]
        if played >= len(buttons):
            log.info("بازی دیگری برای اجرا نیست (%d دکمه).", len(buttons))
            break

        btn = buttons[played]
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
            time.sleep(0.5)
            if not safe_click(driver, btn):
                played += 1
                continue
        except StaleElementReferenceException:
            continue

        time.sleep(5)
        log.info("game %d started: %s", played + 1, driver.current_url)
        snap(driver, f"game_{played + 1}_start")

        pick_player(driver.current_url)(driver, GAME_PLAY_SECONDS)

        time.sleep(2)
        click_collect_if_any(driver)
        snap(driver, f"game_{played + 1}_end")

        played += 1
        driver.get(GAMES_URL)
        time.sleep(4)

    log.info("games finished: %d", played)


# ───────────────────────── اجرای اصلی ─────────────────────────
def main() -> int:
    driver = setup_driver()
    try:
        if not login(driver):
            return 1
        play_games(driver)
        return 0
    except Exception:
        log.exception("unexpected error")
        snap(driver, "fatal")
        return 1
    finally:
        if SESSION:
            finish_session(driver)
        driver.quit()


if __name__ == "__main__":
    sys.exit(main())
