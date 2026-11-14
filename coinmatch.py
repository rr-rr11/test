"""
ربات بازی «Coin-match» (match-3): جدول ۸×۸ از چهار نوع سکه (ETH, DASH, DOGE, BTC).
با جابه‌جایی دو سکه‌ی مجاور طوری که ۳ سکه‌ی هم‌رنگ در یک خط بیایند، سکه‌ها حذف می‌شوند (+۱۸۰ امتیاز برای هر سکه).
جابه‌جایی: کشیدن ماوس از سکه‌ی اول به سکه‌ی مجاور (آزموده‌شده). کلید جهتی استفاده نمی‌شود: کلید ↓ صفحه را اسکرول می‌کند و canvas را جابه‌جا می‌کند.

تخته از روی رنگ سکه‌ها خوانده می‌شود و هر بار جابه‌جایی‌ای انتخاب می‌شود که بیشترین سکه را (با آبشار روی خود تخته) حذف کند.
"""
import time

import numpy as np
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By

import game2048

N = 8
CX = [(173 + 69.1 * i) / 831 for i in range(N)]    # مرکز ستون‌ها (نسبت به عرض canvas)
CY = [(62 + 69.4 * j) / 623 for j in range(N)]     # مرکز ردیف‌ها (نسبت به ارتفاع canvas)
HALF = 14 / 831.0                                  # نیم‌اندازه‌ی ناحیه‌ی نمونه‌برداری رنگ
PROTOS = {"E": (94, 129, 223), "D": (15, 120, 182), "G": (195, 164, 60), "B": (236, 155, 71)}   # میانگین رنگ از ۱۲۸ سکه‌ی واقعی
GRAY_M = 0.05      # Monero (نارنجی بالا / خاکستری پایین): کسر پیکسل‌های خاکستری میانی ≈ ۰٫۰۹ تا ۰٫۱۴؛ بقیه‌ی سکه‌ها ≤ ۰٫۰۰۶
MAX_DIST = 90.0                                    # دورتر از این از همه‌ی رنگ‌ها = خانه‌ی نامطمئن (انیمیشن)


def read_grid(img):
    """تصویر PIL از canvas -> جدول ۸×۸ از حروف E/D/G/B، یا None اگر خانه‌ای نامطمئن بود."""
    a = np.asarray(img.convert("RGB"), dtype=np.float32)
    H, W = a.shape[:2]
    g = []
    for j in range(N):
        row = ""
        for i in range(N):
            x, y, h = int(CX[i] * W), int(CY[j] * H), max(4, int(HALF * W))
            raw = a[y - h:y + h, x - h:x + h].reshape(-1, 3)
            sat = raw.max(axis=1) - raw.min(axis=1)
            c = raw[sat > 60]                                       # فقط پیکسل‌های رنگی (نه سفید/تیره‌ی داخل سکه)
            if len(c) < 20:
                return None
            gray = float(((sat < 40) & (raw.max(axis=1) > 70) & (raw.max(axis=1) < 165)).mean())
            if gray > GRAY_M:                                       # Monero (سطح بالاتر بازی)
                row += "M"
                continue
            m = c.mean(axis=0)
            k, dist = min(((p, float(np.abs(m - np.array(v)).sum())) for p, v in PROTOS.items()), key=lambda t: t[1])
            if dist > MAX_DIST:
                return None
            row += k
        g.append(row)
    return g


def _lines(h):
    """مجموعه‌ی خانه‌های درگیر در خطوط ≥۳ (افقی و عمودی)."""
    out = set()
    for j in range(N):
        i = 0
        while i < N:
            k = i
            while k + 1 < N and h[j][k + 1] == h[j][i] and h[j][i] != ".":
                k += 1
            if k - i + 1 >= 3 and h[j][i] != ".":
                out.update((j, t) for t in range(i, k + 1))
            i = k + 1
    for i in range(N):
        j = 0
        while j < N:
            k = j
            while k + 1 < N and h[k + 1][i] == h[j][i] and h[j][i] != ".":
                k += 1
            if k - j + 1 >= 3 and h[j][i] != ".":
                out.update((t, i) for t in range(j, k + 1))
            j = k + 1
    return out


def resolve(board):
    """حذف خطوط، افتادن سکه‌ها (بدون سکه‌ی جدید) و تکرار. تعداد کل سکه‌های حذف‌شده و پایین‌ترین ردیف حذف را برمی‌گرداند."""
    h = [list(r) for r in board]
    total, lowest = 0, -1
    while True:
        cells = _lines(h)
        if not cells:
            return total, lowest
        total += len(cells)
        lowest = max(lowest, max(j for j, _ in cells))
        for j, i in cells:
            h[j][i] = "."
        for i in range(N):
            col = [h[j][i] for j in range(N) if h[j][i] != "."]
            col = ["."] * (N - len(col)) + col
            for j in range(N):
                h[j][i] = col[j]


def best_swaps(g):
    """همه‌ی جابه‌جایی‌های معتبر، از بهترین به بدترین: [(امتیاز, (ردیف,ستون)A, (ردیف,ستون)B)]. B همیشه راست یا پایین A است."""
    res = []
    for j in range(N):
        for i in range(N):
            for dj, di in ((0, 1), (1, 0)):
                nj, ni = j + dj, i + di
                if nj >= N or ni >= N or g[j][i] == g[nj][ni]:
                    continue
                h = [list(r) for r in g]
                h[j][i], h[nj][ni] = h[nj][ni], h[j][i]
                total, lowest = resolve(h)
                if total:
                    res.append((total + 0.15 * lowest, (j, i), (nj, ni)))   # پایین‌تر = آبشار تصادفیِ بیشتر
    res.sort(reverse=True)
    return res


def _canvas(d):
    return d.find_element(By.CSS_SELECTOR, "canvas")


def _off(d, cell):
    c = _canvas(d)
    w, h = c.size["width"], c.size["height"]
    return int(CX[cell[1]] * w - w / 2), int(CY[cell[0]] * h - h / 2)


def _swap_drag(d, a, b):
    ax, ay = _off(d, a); bx, by = _off(d, b)
    (ActionChains(d).move_to_element_with_offset(_canvas(d), ax, ay).click_and_hold().pause(0.15)
     .move_by_offset((bx - ax) // 2, (by - ay) // 2).pause(0.1)
     .move_by_offset(bx - ax - (bx - ax) // 2, by - ay - (by - ay) // 2).pause(0.15).release().perform())


JS_FIX_SCROLL = ("const c=document.querySelector('canvas');if(!c)return false;"
                 "const t=c.getBoundingClientRect().top;if(Math.abs(t-100)>3){window.scrollBy(0,t-100);}return true;")


def _stable(d, deadline, tries=10):
    """منتظر می‌ماند تا دو خواندن پشت‌سرهم یکی باشد (انیمیشن تمام شده). None اگر canvas رفت، 'TIMEOUT' اگر زمان تمام شد."""
    prev = None
    for _ in range(tries):
        if time.time() > deadline:
            return "TIMEOUT"
        img = game2048._canvas_image(d)
        if img is None:
            return None
        g = read_grid(img)
        if g is not None and g == prev:
            return g
        prev = g
        time.sleep(0.12)
    return prev if prev is not None else "TIMEOUT"


def play(d, seconds=75, log=print):
    """True اگر بازی تمام شد (canvas ناپدید شد)."""
    deadline = time.time() + seconds
    d.execute_script("const c=document.querySelector('canvas');if(c){window.scrollBy(0,c.getBoundingClientRect().top-100);}")
    time.sleep(4.0)                                   # انیمیشن GO!
    d.execute_script(JS_FIX_SCROLL)
    t0 = time.time()
    moves = no_effect = 0
    while time.time() < deadline:
        g = _stable(d, deadline)
        if g is None:
            log(f"[match] canvas gone after {moves} moves in {time.time() - t0:.0f}s"); return True
        if g == "TIMEOUT":
            break
        swaps = best_swaps(g)
        if not swaps:
            log("[match] no valid swap on this board (waiting for refill)"); time.sleep(0.6); continue
        score, a, b = swaps[0]
        before = g
        d.execute_script(JS_FIX_SCROLL)
        _swap_drag(d, a, b)
        moves += 1
        time.sleep(0.5)
        after = _stable(d, deadline)
        if after is None:
            log(f"[match] canvas gone after {moves} moves in {time.time() - t0:.0f}s"); return True
        if after == before:                           # جابه‌جایی اثر نکرد
            no_effect += 1
            if no_effect >= 6:
                log("[match] swaps have no effect; stopping"); break
        else:
            no_effect = 0
        if moves % 5 == 0:
            el = time.time() - t0
            log(f"[match] moves={moves} t={el:.0f}s ({el / moves:.1f}s/move) last swap clears≈{int(score)}")
    log(f"[match] time up after {moves} moves")
    return game2048._canvas_image(d) is None
