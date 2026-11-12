"""
probe4.py - Coin-match: آیا جابه‌جایی دو سکه‌ی مجاور (match-3) است؟ سه روش جابه‌جایی را آزمایش می‌کند.
تخته را از روی رنگ می‌خواند، گروه‌های هم‌رنگ مجاور را پیدا می‌کند و دو آزمایش می‌کند:
  ۱) فقط یک کلیک روی یک سکه از بزرگ‌ترین گروه
  ۲) کشیدن ماوس (click-and-hold و حرکت) روی ۳ تا ۴ سکه‌ی هم‌رنگ مجاور
بعد از هر آزمایش عکس می‌گیرد. خروجی در probe3/ .
"""
import os, time
from pathlib import Path
import numpy as np
from PIL import Image
from selenium import webdriver
from selenium.webdriver import ActionChains
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from session_utils import load_session, finish_session

SESSION = os.environ.get("RC_SESSION", "")
OUT = Path("probe4"); OUT.mkdir(exist_ok=True)
START_XP = "//button[contains(translate(normalize-space(.),'start','START'),'START')]"
X = [173 + 69.1 * i for i in range(8)]       # مرکز ستون‌ها (پیکسل، canvas 831×623)
Y = [62 + 69.4 * j for j in range(8)]
PROTOS = {"E": (108, 130, 230), "D": (20, 115, 200), "G": (205, 165, 50), "B": (235, 135, 45)}

opts = Options()
if os.environ.get("HEADLESS", "1") == "1":
    opts.add_argument("--headless=new")
for a in ("--no-sandbox", "--disable-dev-shm-usage", "--window-size=1600,1000"):
    opts.add_argument(a)
d = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)


def canvas():
    return d.find_element(By.CSS_SELECTOR, "canvas")


def shot(name):
    canvas().screenshot(str(OUT / f"{name}.png"))


def read_grid(path):
    a = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32)
    g = []
    for j in range(8):
        row = ""
        for i in range(8):
            x, y = int(X[i]), int(Y[j])
            c = a[y - 14:y + 14, x - 14:x + 14].reshape(-1, 3)
            c = c[(c.max(axis=1) - c.min(axis=1)) > 60]
            m = c.mean(axis=0) if len(c) else np.zeros(3)
            row += min(PROTOS, key=lambda p: np.abs(m - np.array(PROTOS[p])).sum())
        g.append(row)
    return g


def components(g):
    seen, comps = set(), []
    for j in range(8):
        for i in range(8):
            if (j, i) in seen: continue
            st, comp = [(j, i)], []
            seen.add((j, i))
            while st:
                y, x = st.pop(); comp.append((y, x))
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < 8 and 0 <= nx < 8 and (ny, nx) not in seen and g[ny][nx] == g[y][x]:
                        seen.add((ny, nx)); st.append((ny, nx))
            comps.append(comp)
    return sorted(comps, key=len, reverse=True)


def path_in(comp, n):
    """یک مسیر ساده از n سکه‌ی مجاور داخل یک گروه (DFS)."""
    cs = set(comp)
    def dfs(p, path):
        if len(path) == n: return path
        y, x = p
        for dy, dx in ((0, 1), (1, 0), (0, -1), (-1, 0)):
            q = (y + dy, x + dx)
            if q in cs and q not in path:
                r = dfs(q, path + [q])
                if r: return r
        return None
    for s in comp:
        r = dfs(s, [s])
        if r: return r
    return comp[:n]


def off(cell):
    w, h = canvas().size["width"], canvas().size["height"]
    return int(X[cell[1]] / 831 * w - w / 2), int(Y[cell[0]] / 623 * h - h / 2)


try:
    if SESSION:
        load_session(d, SESSION)
    d.get("https://rollercoin.com/"); time.sleep(8)
    try:
        d.execute_script("arguments[0].click();", d.find_element(By.CSS_SELECTOR, "a[href*='choose_game']"))
    except Exception:
        d.get("https://rollercoin.com/game/choose_game")
    end = time.time() + 40
    while time.time() < end and not d.find_elements(By.XPATH, START_XP):
        time.sleep(2)
    for b in d.find_elements(By.XPATH, START_XP):
        t = d.execute_script("let e=arguments[0];for(let k=0;k<4&&e.parentElement;k++){e=e.parentElement;}return e.innerText;", b)
        if "coin-match" in t.lower():
            d.execute_script("arguments[0].scrollIntoView({block:'center'});", b); time.sleep(0.5)
            d.execute_script("arguments[0].click();", b); break
    end = time.time() + 40
    while time.time() < end and not d.find_elements(By.CSS_SELECTOR, "canvas"):
        time.sleep(2)
    time.sleep(6)
    d.execute_script("""document.querySelectorAll('button').forEach(b=>{const t=(b.innerText||'').trim().toUpperCase();
        if(['ALLOW SELECTION',"DON'T ALLOW"].includes(t)) b.click();});""")
    time.sleep(1.5)
    c = canvas()
    d.execute_script("window.scrollBy(0, arguments[0].getBoundingClientRect().top - 100);", c); time.sleep(0.5)
    w, h = c.size["width"], c.size["height"]
    ActionChains(d).move_to_element_with_offset(c, 0, int(0.42 * h - h / 2)).click().perform()
    time.sleep(5)                                   # GO!
    ActionChains(d).move_by_offset(0, 0).perform()
    shot("00_start")
    g = read_grid(OUT / "00_start.png")
    comps = components(g)
    print("[probe4] grid:"); [print("   ", r) for r in g]
    print("[probe4] component sizes:", [len(x) for x in comps[:10]])
    def makes_match(h, cell):
        j, i = cell; t = h[j][i]
        cnt, k = 1, i - 1
        while k >= 0 and h[j][k] == t: cnt += 1; k -= 1
        k = i + 1
        while k < 8 and h[j][k] == t: cnt += 1; k += 1
        if cnt >= 3: return True
        cnt, k = 1, j - 1
        while k >= 0 and h[k][i] == t: cnt += 1; k -= 1
        k = j + 1
        while k < 8 and h[k][i] == t: cnt += 1; k += 1
        return cnt >= 3

    def valid_swaps(g):
        res = []
        for j in range(8):
            for i in range(8):
                for dj, di in ((0, 1), (1, 0)):
                    nj, ni = j + dj, i + di
                    if nj < 8 and ni < 8 and g[j][i] != g[nj][ni]:
                        h = [list(r) for r in g]; h[j][i], h[nj][ni] = h[nj][ni], h[j][i]
                        if makes_match(h, (j, i)) or makes_match(h, (nj, ni)):
                            res.append(((j, i), (nj, ni)))
        return res

    def diff_cells(g1, g2):
        return sum(1 for j in range(8) for i in range(8) if g1[j][i] != g2[j][i])

    sw = valid_swaps(g)
    print("[probe4] valid match-3 swaps found:", len(sw), sw[:5])
    cur = g

    # آزمایش ۱: کشیدن ماوس از سکه‌ی A به سکه‌ی مجاور B (دو مرحله‌ای، آرام)
    if sw:
        A, B = sw[0]
        ax, ay = off(A); bx, by = off(B)
        act = (ActionChains(d).move_to_element_with_offset(canvas(), ax, ay).click_and_hold().pause(0.2)
               .move_by_offset((bx - ax) // 2, (by - ay) // 2).pause(0.15)
               .move_by_offset(bx - ax - (bx - ax) // 2, by - ay - (by - ay) // 2).pause(0.2).release())
        act.perform()
        time.sleep(0.7); shot("01_drag_swap_0.7s"); time.sleep(1.5); shot("02_drag_swap_2.2s")
        g1 = read_grid(OUT / "02_drag_swap_2.2s.png")
        print("[probe4] E1 drag-swap: changed cells =", diff_cells(cur, g1), "(", A, "->", B, ")")
        cur = g1

    # آزمایش ۲: دو کلیک پشت‌هم (A بعد B)
    sw = valid_swaps(cur)
    if sw:
        A, B = sw[0]
        ActionChains(d).move_to_element_with_offset(canvas(), *off(A)).click().perform(); time.sleep(0.5)
        ActionChains(d).move_to_element_with_offset(canvas(), *off(B)).click().perform()
        time.sleep(0.7); shot("03_click_click_0.7s"); time.sleep(1.5); shot("04_click_click_2.2s")
        g2 = read_grid(OUT / "04_click_click_2.2s.png")
        print("[probe4] E2 click-click: changed cells =", diff_cells(cur, g2), "(", A, "->", B, ")")
        cur = g2

    # آزمایش ۳: کلیک روی A و بعد کلید جهتی به سمت B
    sw = valid_swaps(cur)
    if sw:
        from selenium.webdriver.common.keys import Keys
        A, B = sw[0]
        key = Keys.ARROW_RIGHT if B[1] > A[1] else Keys.ARROW_DOWN
        ActionChains(d).move_to_element_with_offset(canvas(), *off(A)).click().perform(); time.sleep(0.5)
        ActionChains(d).send_keys(key).perform()
        time.sleep(0.7); shot("05_click_key_0.7s"); time.sleep(1.5); shot("06_click_key_2.2s")
        g3 = read_grid(OUT / "06_click_key_2.2s.png")
        print("[probe4] E3 click+arrow key: changed cells =", diff_cells(cur, g3), "(", A, "->", B, ")")
    print("[probe4] done")
finally:
    try:
        finish_session(d)
    except Exception:
        pass
    d.quit()
