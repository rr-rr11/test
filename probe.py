"""
probe.py - بررسی داخلی یک بازی (Phaser) برای فهمیدن این‌که وضعیت بازی از کجا خوانده می‌شود.

متغیر محیطی:  GAME = اسم بازی مثل "2048 Coins"   (پیش‌فرض: 2048 Coins)
خروجی در پوشه probe/ : اسکرین‌شات‌ها + فایل‌های JSON از ساختار صحنه‌های Phaser.
این اسکریپت فقط می‌خواند و چند کلید فلش می‌زند؛ چیزی در بازی تغییر نمی‌دهد.
"""
import json, os, time
from pathlib import Path
from selenium import webdriver
from selenium.webdriver import ActionChains
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager
from session_utils import load_session, finish_session

GAME = os.environ.get("GAME", "2048 Coins").strip() or "2048 Coins"
SESSION = os.environ.get("RC_SESSION", "")
OUT = Path("probe"); OUT.mkdir(exist_ok=True)
START_XP = "//button[contains(translate(normalize-space(.),'start','START'),'START')]"

opts = Options()
if os.environ.get("HEADLESS", "1") == "1":
    opts.add_argument("--headless=new")
for a in ("--no-sandbox", "--disable-dev-shm-usage", "--window-size=1600,1000"):
    opts.add_argument(a)
d = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)

JS_DUMP = r"""
const g = (window.Phaser && Phaser.GAMES && Phaser.GAMES[0]) || null;
if (!g) return {error: 'no Phaser.GAMES[0]'};
const STD = new Set(['sys','game','anims','cache','registry','sound','textures','events','cameras','add','make',
  'scene','children','lights','data','input','load','time','tweens','physics','matter','scale','plugins',
  'renderer','displayList','updateList','scenePlugin']);
function summ(v, d) {
  const t = typeof v;
  if (v === null || v === undefined) return String(v);
  if (t === 'number' || t === 'boolean') return v;
  if (t === 'string') return v.slice(0, 60);
  if (t === 'function') return 'fn';
  if (Array.isArray(v)) {
    return {array: v.length,
            first: (v.length && d > 0) ? summ(v[0], d - 1) : undefined,
            sample: (v.length && typeof v[0] !== 'object') ? v.slice(0, 40) : undefined};
  }
  if (t === 'object') {
    const ks = Object.keys(v).slice(0, 25);
    if (d <= 0) return {obj: ks};
    const o = {};
    ks.forEach(k => { try { o[k] = summ(v[k], d - 1); } catch (e) {} });
    return o;
  }
  return t;
}
function walk(list, texts, sprites, key) {
  list.forEach(o => {
    try {
      const m = o.getWorldTransformMatrix ? o.getWorldTransformMatrix() : null;
      const x = m ? m.tx : o.x, y = m ? m.ty : o.y;
      if (o.text !== undefined) texts.push({scene: key, type: o.type, text: String(o.text).slice(0, 40), x, y, visible: o.visible});
      else if (o.texture && sprites.length < 250)
        sprites.push({scene: key, tex: o.texture.key, frame: o.frame && o.frame.name, x, y, visible: o.visible});
      if (o.list) walk(o.list, texts, sprites, key);
    } catch (e) {}
  });
}
const scenes = [];
g.scene.scenes.forEach(s => {
  const key = s.sys.settings.key;
  const custom = {};
  Object.keys(s).filter(k => !STD.has(k)).slice(0, 60).forEach(k => { try { custom[k] = summ(s[k], 3); } catch (e) {} });
  const texts = [], sprites = [];
  walk(s.children.list, texts, sprites, key);
  scenes.push({key, active: s.sys.isActive(), visible: s.sys.isVisible(), children: s.children.list.length, custom, texts, sprites});
});
const r = g.canvas.getBoundingClientRect();
return {gameW: g.config.width, gameH: g.config.height,
        rect: [r.left, r.top, r.width, r.height], scenes};
"""


def snap(name):
    d.save_screenshot(str(OUT / f"{name}.png"))


def dump(name):
    try:
        data = d.execute_script(JS_DUMP)
    except Exception as e:
        data = {"error": str(e)}
    (OUT / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str))
    snap(name)
    return data


def dismiss_overlays():
    for xp in ("//button[normalize-space()='ALLOW SELECTION']",
               "//button[normalize-space()=\"Don't allow\"]"):
        for b in d.find_elements(By.XPATH, xp):
            try:
                d.execute_script("arguments[0].click();", b)
            except Exception:
                pass
    time.sleep(1)


def click_game_xy(gx, gy):
    canvas = d.find_element(By.CSS_SELECTOR, "canvas")
    d.execute_script("arguments[0].scrollIntoView({block:'center'});", canvas)
    time.sleep(0.5)
    info = d.execute_script(
        "const g=Phaser.GAMES[0];const r=g.canvas.getBoundingClientRect();"
        "return [r.width,r.height,g.config.width,g.config.height];")
    w, h, gw, gh = info
    dx = gx / gw * w - w / 2
    dy = gy / gh * h - h / 2
    ActionChains(d).move_to_element_with_offset(canvas, int(dx), int(dy)).click().perform()


try:
    if SESSION:
        load_session(d, SESSION)

    # --- صفحه بازی‌ها (از طریق منو) و کلیک روی کارت مورد نظر ---
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
        card = d.execute_script(
            "let e=arguments[0];for(let k=0;k<4&&e.parentElement;k++){e=e.parentElement;}return e.innerText;", b)
        if GAME.lower() in card.lower():
            target = b; break
    print("[probe] game:", GAME, "found card:", target is not None, "url:", d.current_url)
    if target is None:
        snap("card_not_found"); raise SystemExit(1)
    d.execute_script("arguments[0].scrollIntoView({block:'center'});", target)
    time.sleep(0.5)
    d.execute_script("arguments[0].click();", target)

    # --- منتظر Phaser و منوی بازی ---
    end = time.time() + 40
    while time.time() < end:
        ok = d.execute_script("return !!(window.Phaser && Phaser.GAMES && Phaser.GAMES[0] && Phaser.GAMES[0].canvas)")
        if ok: break
        time.sleep(2)
    time.sleep(6)
    dismiss_overlays()
    menu = dump("p0_menu")
    print("[probe] scenes:", [(s["key"], s["active"], s["children"]) for s in menu.get("scenes", [])])

    # --- کلیک روی START داخل canvas ---
    start = None
    for s in menu.get("scenes", []):
        for t in s["texts"]:
            if t["text"].strip().upper() == "START" and t.get("visible", True):
                start = t; break
        if start: break
    if start:
        print("[probe] in-canvas START at", start["x"], start["y"])
        click_game_xy(start["x"], start["y"])
    else:
        print("[probe] START text not found, using fallback position")
        gw, gh = menu.get("gameW", 960), menu.get("gameH", 828)
        click_game_xy(gw * 0.5, gh * 0.42)
    time.sleep(5)
    dump("p1_started")

    # --- چند حرکت با کلیدهای جهتی و ثبت وضعیت بعد از آن‌ها ---
    canvas = d.find_element(By.CSS_SELECTOR, "canvas")
    for i, key in enumerate([Keys.ARROW_LEFT, Keys.ARROW_UP, Keys.ARROW_RIGHT, Keys.ARROW_DOWN] * 2):
        ActionChains(d).send_keys(key).perform()
        time.sleep(0.5)
    dump("p2_after_keys")
    time.sleep(5)
    dump("p3_later")
finally:
    try:
        finish_session(d)
    except Exception:
        pass
    d.quit()
