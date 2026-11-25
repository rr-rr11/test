"""
probe5.py - کنترل بازی‌های Token Blaster و Crypto Hamster را کشف می‌کند: ماوس، کلیدهای جهتی، Space و کلیک را
به‌نوبت می‌زند و بعد از هر کدام از canvas عکس می‌گیرد. خروجی در probe5/ . متغیر GAMES: "Token Blaster,Crypto Hamster"
"""
import os, re, time
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from session_utils import load_session, finish_session

GAMES = [g.strip() for g in (os.environ.get("GAMES") or "Token Blaster,Crypto Hamster").split(",") if g.strip()]
SESSION = os.environ.get("RC_SESSION", "")
OUT = Path("probe5"); OUT.mkdir(exist_ok=True)
START_XP = "//button[contains(translate(normalize-space(.),'start','START'),'START')]"
KEYS = {"left": (37, "ArrowLeft"), "up": (38, "ArrowUp"), "right": (39, "ArrowRight"), "down": (40, "ArrowDown"), "space": (32, "Space")}

SCRIPTS = {
    "Token Blaster": [
        ("wait", 1.0), ("shot", "a0"),
        ("move", 0.15, 0.9), ("wait", 0.8), ("shot", "b1_mouse_left"),
        ("move", 0.85, 0.9), ("wait", 0.8), ("shot", "b2_mouse_right"),
        ("move", 0.5, 0.9), ("wait", 0.6), ("shot", "b3_mouse_center"),
        ("hold", "left", 0.7), ("shot", "c1_key_left"),
        ("hold", "right", 1.4), ("shot", "c2_key_right"),
        ("hold", "left", 0.7), ("shot", "c3_key_left"),
        ("hold", "space", 0.3), ("wait", 0.4), ("shot", "d1_space"),
        ("click", 0.5, 0.9), ("wait", 0.4), ("shot", "d2_click"),
        ("wait", 3.0), ("shot", "e0_idle"),
    ],
    "Crypto Hamster": [
        ("wait", 1.0), ("shot", "a0"),
        ("hold", "left", 0.6), ("shot", "b1_key_left"),
        ("hold", "right", 1.0), ("shot", "b2_key_right"),
        ("hold", "space", 0.2), ("wait", 0.4), ("shot", "c1_space"), ("wait", 0.5), ("shot", "c2_after_space"),
        ("hold", "up", 0.5), ("shot", "d1_key_up"),
        ("click", 0.5, 0.5), ("wait", 0.5), ("shot", "e1_click"),
        ("move", 0.2, 0.5), ("wait", 0.6), ("shot", "f1_mouse_left"),
        ("move", 0.8, 0.5), ("wait", 0.6), ("shot", "f2_mouse_right"),
        ("wait", 3.0), ("shot", "g0_idle"),
    ],
}

opts = Options()
if os.environ.get("HEADLESS", "1") == "1":
    opts.add_argument("--headless=new")
for a in ("--no-sandbox", "--disable-dev-shm-usage", "--window-size=1600,1000"):
    opts.add_argument(a)
d = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
JS_GEOM = ("const e=document.querySelector('canvas');if(!e)return null;const c=e.getBoundingClientRect();"
           "return [c.left,c.top,c.width,c.height];")


def slug(n):
    return re.sub(r"[^a-z0-9]+", "_", n.lower()).strip("_")


def card_name(text):
    lines = [x.strip() for x in text.split("\n") if x.strip()]
    return next((x for x in lines if x.upper() not in ("NEW", "HOT", "COMMUNITY")), "")


def dismiss():
    d.execute_script("""document.querySelectorAll('button').forEach(b=>{const t=(b.innerText||'').trim().toUpperCase();
        if(['ALLOW SELECTION',"DON'T ALLOW"].includes(t)) b.click();});""")
    time.sleep(1.5)


def mouse(kind, fx, fy, **kw):
    left, top, w, h = d.execute_script(JS_GEOM)
    d.execute_cdp_cmd("Input.dispatchMouseEvent", dict(
        type=kind, x=left + fx * w, y=top + fy * h, button="left" if kind != "mouseMoved" else "none", **kw))


def key(kind, name):
    code, k = KEYS[name]
    d.execute_cdp_cmd("Input.dispatchKeyEvent", dict(
        type=kind, windowsVirtualKeyCode=code, nativeVirtualKeyCode=code, key=k, code=k,
        text=" " if name == "space" and kind == "keyDown" else ""))


def run(name):
    s = slug(name)
    print(f"[probe5] === {name} ===")
    d.get("https://rollercoin.com/"); time.sleep(8)
    try:
        d.execute_script("arguments[0].click();", d.find_element(By.CSS_SELECTOR, "a[href*='choose_game']"))
    except Exception:
        d.get("https://rollercoin.com/game/choose_game")
    end = time.time() + 40
    while time.time() < end and len(d.find_elements(By.XPATH, START_XP)) < 10:
        time.sleep(2)
    target = None
    for _ in range(8):
        for b in d.find_elements(By.XPATH, START_XP):
            t = d.execute_script("let e=arguments[0];for(let k=0;k<4&&e.parentElement;k++){e=e.parentElement;}return e.innerText;", b)
            if card_name(t).lower() == name.lower():
                target = b; break
        if target: break
        d.execute_script("window.scrollBy(0,650);"); time.sleep(1.5)
    if target is None:
        print("[probe5] card not available (cooldown?):", name); return
    d.execute_script("arguments[0].scrollIntoView({block:'center'});", target); time.sleep(0.5)
    d.execute_script("arguments[0].click();", target)
    end = time.time() + 40
    while time.time() < end and not d.find_elements(By.CSS_SELECTOR, "canvas"):
        time.sleep(2)
    time.sleep(6); dismiss()
    d.execute_script("const c=document.querySelector('canvas');window.scrollBy(0,c.getBoundingClientRect().top-20);"); time.sleep(0.5)
    left, top, w, h = d.execute_script(JS_GEOM)
    mouse("mouseMoved", 0.5, 0.42); mouse("mousePressed", 0.5, 0.42, clickCount=1); mouse("mouseReleased", 0.5, 0.42, clickCount=1)
    time.sleep(4.0)                                   # GO!
    n = 0
    for step in SCRIPTS[name]:
        k = step[0]
        if k == "wait": time.sleep(step[1])
        elif k == "move": mouse("mouseMoved", step[1], step[2])
        elif k == "click":
            mouse("mouseMoved", step[1], step[2]); mouse("mousePressed", step[1], step[2], clickCount=1); mouse("mouseReleased", step[1], step[2], clickCount=1)
        elif k == "hold":
            key("keyDown", step[1]); time.sleep(step[2]); key("keyUp", step[1])
        elif k == "shot":
            n += 1
            try:
                d.find_element(By.CSS_SELECTOR, "canvas").screenshot(str(OUT / f"{s}_{n:02d}_{step[1]}.png"))
            except Exception as e:
                print("[probe5] shot failed:", step[1], type(e).__name__); break
    print(f"[probe5] done: {name} ({n} shots, canvas {w:.0f}x{h:.0f})")


try:
    if SESSION:
        load_session(d, SESSION)
    for g in GAMES:
        try:
            if g in SCRIPTS: run(g)
            else: print("[probe5] no script for", g)
        except Exception as e:
            print(f"[probe5] {g} failed:", type(e).__name__, e)
            try: d.save_screenshot(str(OUT / f"{slug(g)}_error.png"))
            except Exception: pass
        time.sleep(2)
finally:
    try: finish_session(d)
    except Exception: pass
    d.quit()
