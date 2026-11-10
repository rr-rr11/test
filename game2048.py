"""
ربات بازی «2048 Coins» (Phaser / canvas).

وضعیت بازی از روی تصویر canvas خوانده می‌شود: هر خانه با آیکن‌های راهنمای سمت راست
(سطح ۱ تا ۱۱) مقایسه می‌شود. بعد با الگوریتم expectimax بهترین حرکت انتخاب و با کلید جهتی ارسال می‌شود.
"""
import base64
import io
import math
import random
import time

import numpy as np
from PIL import Image
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

# ---------- هندسه (نسبت‌ها نسبت به canvas استاندارد 831×717؛ از تصویر واقعی بازی گرفته شده) ----------
STD_SIZE = (831, 717)
COL_X = [0.1625, 0.3430, 0.5211, 0.6980]
ROW_Y = [0.2204, 0.4296, 0.6388, 0.8480]
LEG_X = 0.8400
LEG_Y = [y / 717.0 for y in (161, 208, 252, 296, 340, 384, 428, 473, 518, 563, 606)]
TILE_HALF = 0.0665  # نیم‌اندازه‌ی برش دور سکه در هر خانه (نسبت به عرض)
LEG_HALF = 0.025    # همین برای آیکن‌های راهنما
S = 32              # اندازه‌ی مشترک مقایسه
EMPTY_STD = 8.0     # خانه خالی تقریباً یک‌رنگ است (انحراف معیار هر کانال، روی برش مرکزی)
_YY, _XX = np.mgrid[0:S, 0:S]
MASK = ((_YY - S / 2 + .5) ** 2 + (_XX - S / 2 + .5) ** 2) <= (S * 0.44) ** 2


def _crop(img, fx, fy, half):
    W, H = img.size
    cx, cy, h = fx * W, fy * H, half * W
    return img.crop((int(cx - h), int(cy - h), int(cx + h), int(cy + h)))


def _feat(im):
    a = np.asarray(im.resize((S, S), Image.LANCZOS).convert("RGB"), dtype=np.float32)
    px = a[MASK]
    return px, px.mean(axis=0)


def _dist(f, t):
    return float(np.abs(f[0] - t[0]).mean() + 2.0 * np.abs(f[1] - t[1]).sum() / 3.0)


_LEGEND = {}
_SHIFT = (0, 0)   # جابه‌جایی احتمالی برش نسبت به canvas (پیکسل در مقیاس 831×717)


def reset_legend():
    global _SHIFT
    _LEGEND.clear()
    _SHIFT = (0, 0)


def _legend(img, shift):
    L = _LEGEND.get(shift)
    if L is None:
        sx, sy = shift
        L = [_feat(_crop(img, LEG_X + sx / 831.0, y + sy / 717.0, LEG_HALF)) for y in LEG_Y]
        _LEGEND[shift] = L
    return L


def read_board(img, shift=None):
    """تصویر PIL از canvas -> (جدول ۴×۴ از سطح‌ها، بدترین نسبت best/second). ۰ = خانه خالی."""
    if shift is None:
        shift = _SHIFT
    if img.size != STD_SIZE:
        img = img.resize(STD_SIZE, Image.LANCZOS)
    sx, sy = shift[0] / 831.0, shift[1] / 717.0
    legend = _legend(img, shift)
    board, worst = [], 0.0
    for r in range(4):
        row = []
        for c in range(4):
            fx, fy = COL_X[c] + sx, ROW_Y[r] + sy
            inner = _crop(img, fx, fy, 0.036)
            arr = np.asarray(inner.convert("RGB"), dtype=np.float32)
            if arr.reshape(-1, 3).std(axis=0).mean() < EMPTY_STD:
                row.append(0)
                continue
            f = _feat(_crop(img, fx, fy, TILE_HALF))
            dists = [_dist(f, t) for t in legend]
            order = np.argsort(dists)
            row.append(int(order[0]) + 1)
            worst = max(worst, dists[int(order[0])] / max(dists[int(order[1])], 1e-6))
        board.append(tuple(row))
    return tuple(board), worst


def calibrate(img):
    """اگر برش canvas چند پیکسل جابه‌جا باشد، بهترین جابه‌جایی را پیدا می‌کند. (shift, board, worst) یا None."""
    global _SHIFT
    best = None
    for dy in range(-16, 17, 4):
        for dx in range(-16, 17, 4):
            b, w = read_board(img, (dx, dy))
            tiles = sum(1 for r in b for x in r if x)
            if tiles < 2 or tiles > 8:
                continue
            if best is None or w < best[2]:
                best = ((dx, dy), b, w)
    if best and best[2] < 0.97:
        _SHIFT = best[0]
        return best
    return None


def reconcile(pred, actual):
    """
    pred: جدول پیش‌بینی‌شده بعد از حرکت (بدون خانه‌ی جدید)، actual: جدول خوانده‌شده.
    اگر actual فقط با یک خانه‌ی جدید با pred فرق دارد، خطاهای تشخیص سکه‌های دیگر اصلاح می‌شود.
    خروجی: (جدول نهایی، تعداد خانه‌های جدید دیده‌شده). اگر ناسازگار بود (None, -1).
    """
    bad = new = 0
    out = [list(r) for r in pred]
    for r in range(4):
        for c in range(4):
            p, a = pred[r][c], actual[r][c]
            if p:
                if a != p:
                    bad += 1
            elif a:
                new += 1
                out[r][c] = a
    if bad <= 2 and new <= 1:
        return tuple(tuple(r) for r in out), new
    return None, -1


# ---------- منطق 2048 ----------
def _slide_left(row):
    tiles = [x for x in row if x]
    out, i, gained = [], 0, 0
    while i < len(tiles):
        if i + 1 < len(tiles) and tiles[i] == tiles[i + 1]:
            out.append(tiles[i] + 1); gained += 1; i += 2
        else:
            out.append(tiles[i]); i += 1
    out += [0] * (4 - len(out))
    return tuple(out)


_LEFT = {}


def _left(row):
    r = _LEFT.get(row)
    if r is None:
        r = _LEFT[row] = _slide_left(row)
    return r


def move(board, d):
    """d: 0=چپ 1=بالا 2=راست 3=پایین"""
    if d == 0:
        nb = tuple(_left(r) for r in board)
    elif d == 2:
        nb = tuple(_left(r[::-1])[::-1] for r in board)
    elif d == 1:
        t = tuple(zip(*board))
        nb = tuple(zip(*(_left(r) for r in t)))
    else:
        t = tuple(zip(*board))
        nb = tuple(zip(*(_left(r[::-1])[::-1] for r in t)))
    return tuple(tuple(r) for r in nb)


_SC = {}


def _row_score(row):
    s = _SC.get(row)
    if s is not None:
        return s
    empty = sum(1 for x in row if x == 0)
    total = sum(math.pow(x, 3.5) for x in row)
    merges, prev, counter = 0, 0, 0
    for x in row:
        if x:
            if prev == x:
                counter += 1
            elif counter:
                merges += 1 + counter; counter = 0
            prev = x
    if counter:
        merges += 1 + counter
    mono_l = mono_r = 0.0
    for i in range(1, 4):
        a, b = row[i - 1], row[i]
        if a > b:
            mono_l += math.pow(a, 4) - math.pow(b, 4)
        else:
            mono_r += math.pow(b, 4) - math.pow(a, 4)
    s = 200000.0 + 270.0 * empty + 700.0 * merges - 47.0 * min(mono_l, mono_r) - 11.0 * total
    _SC[row] = s
    return s


def _score(board):
    return sum(_row_score(r) for r in board) + sum(_row_score(c) for c in zip(*board))


P_TWO = 0.8   # احتمال این‌که خانه‌ی جدید سطح ۱ باشد (بقیه سطح ۲)


def _expect(board, depth, cache):
    key = (board, depth)
    v = cache.get(key)
    if v is not None:
        return v
    empties = [(r, c) for r in range(4) for c in range(4) if board[r][c] == 0]
    if not empties:
        return _best(board, depth, cache)
    if len(empties) > 6 and depth <= 1:
        sample = random.sample(empties, 6)
    else:
        sample = empties
    tot = 0.0
    for r, c in sample:
        for val, p in ((1, P_TWO), (2, 1 - P_TWO)):
            nb = list(list(x) for x in board)
            nb[r][c] = val
            tot += p * _best(tuple(tuple(x) for x in nb), depth - 1, cache)
    v = tot / len(sample)
    cache[key] = v
    return v


def _best(board, depth, cache):
    if depth <= 0:
        return _score(board)
    best = 0.0
    for d in range(4):
        nb = move(board, d)
        if nb != board:
            best = max(best, _expect(nb, depth, cache))
    return best


def best_moves(board):
    """حرکت‌ها از بهترین به بدترین (فقط حرکت‌های ممکن)."""
    empties = sum(1 for r in board for x in r if x == 0)
    depth = 3 if empties <= 6 else 2
    cache, res = {}, []
    for d in range(4):
        nb = move(board, d)
        if nb != board:
            res.append((_expect(nb, depth, cache), d))
    res.sort(reverse=True)
    return [d for _, d in res]


# ---------- تعامل با مرورگر ----------
KEYS = [Keys.ARROW_LEFT, Keys.ARROW_UP, Keys.ARROW_RIGHT, Keys.ARROW_DOWN]
JS_RESULT = ("const t=(document.body.innerText||'').toUpperCase();"
             "return t.includes('CLAIM REWARD')||t.includes('YOU WIN')||t.includes('YOU LOSE')||t.includes('GAME OVER');")
JS_RECT = ("const e=document.querySelector('canvas');if(!e)return null;const c=e.getBoundingClientRect();"
           "return [c.left+window.scrollX,c.top+window.scrollY,c.width,c.height];")

def _canvas_image(d):
    """تصویر سریع فقط از ناحیه‌ی canvas (CDP) با rect تازه. اگر canvas نبود (بازی تمام شد) None."""
    rect = d.execute_script(JS_RECT)
    if rect is None:
        return None
    params = {"format": "jpeg", "quality": 70, "fromSurface": True,
              "clip": {"x": rect[0], "y": rect[1], "width": rect[2], "height": rect[3], "scale": 1}}
    try:
        data = d.execute_cdp_cmd("Page.captureScreenshot", dict(params, optimizeForSpeed=True))
    except Exception:
        try:
            data = d.execute_cdp_cmd("Page.captureScreenshot", params)
        except Exception:
            return None if d.execute_script(JS_RECT) is None else Image.new("RGB", STD_SIZE)
    return Image.open(io.BytesIO(base64.b64decode(data["data"]))).convert("RGB")


def _wait_start(d, log, timeout=10):
    """منتظر می‌ماند تا انیمیشن «GO!» تمام شود و دست‌کم دو خانه‌ی پایدار خوانده شود."""
    end = time.time() + timeout
    prev, calibrated = None, False
    t_cal = time.time() + 4
    while time.time() < end:
        img = _canvas_image(d)
        if img is None:
            return None
        b, worst = read_board(img)
        tiles = [x for r in b for x in r if x]
        if len(tiles) >= 2 and worst < 0.97 and b == prev:
            return b
        if not calibrated and time.time() > t_cal:
            calibrated = True
            c = calibrate(img)
            log(f"[2048] calibration: {('shift=%s worst=%.2f' % (c[0], c[2])) if c else 'failed'}")
            if c:
                return c[1]
        prev = b
        time.sleep(0.15)
    log("[2048] start screen not recognised; continuing anyway")
    img = _canvas_image(d)
    return read_board(img)[0] if img is not None else None


def play(d, seconds=68, log=print):
    """بازی را تا پایان زمان یا ناپدید شدن canvas ادامه می‌دهد. True اگر بازی تمام شد."""
    reset_legend()
    deadline = time.time() + seconds
    # canvas را طوری بالا بیاور که زیر هدر ثابت صفحه نرود (بالا ≈ ۱۰۰ پیکسل)
    d.execute_script("const c=document.querySelector('canvas');if(c){window.scrollBy(0,c.getBoundingClientRect().top-100);}")
    time.sleep(0.5)
    board = _wait_start(d, log)
    if board is None:
        log("[2048] canvas gone before start"); return True
    t0 = time.time()
    moves, unreadable, resyncs = 0, 0, 0
    pred = None
    while time.time() < deadline:
        if pred is not None:
            tries, fixed = 0, None
            while True:
                img = _canvas_image(d)
                if img is None:
                    log(f"[2048] canvas gone after {moves} moves in {time.time()-t0:.0f}s (resyncs={resyncs})")
                    return True
                actual, worst = read_board(img)
                fixed, new = reconcile(pred, actual) if worst <= 0.97 else (None, -1)
                has_empty = any(0 in r for r in pred)
                if fixed is not None and not (new == 0 and has_empty and tries < 2):
                    break
                if tries >= 3:
                    break
                tries += 1
                time.sleep(0.08)
            if fixed is not None:
                board = fixed
            else:
                if worst > 0.97:
                    unreadable += 1
                    if unreadable > 40:
                        log("[2048] too many unreadable frames"); return False
                    pred = None; time.sleep(0.1); continue
                board = actual; resyncs += 1      # کلید اعمال نشد یا ناسازگاری؛ به تصویر اعتماد کن
        else:
            img = _canvas_image(d)
            if img is None:
                return True
            board, worst = read_board(img)
            if worst > 0.97:
                unreadable += 1
                if unreadable > 40:
                    log("[2048] too many unreadable frames"); return False
                time.sleep(0.1); continue
        order = best_moves(board)
        if not order:
            log("[2048] no moves left"); time.sleep(1.0)
            if d.execute_script(JS_RESULT) or _canvas_image(d) is None: return True
            pred = None; continue
        ActionChains(d).send_keys(KEYS[order[0]]).perform()
        pred = move(board, order[0])
        moves += 1
        if moves % 20 == 0:
            el = time.time() - t0
            log(f"[2048] moves={moves} t={el:.0f}s ({el/moves:.2f}s/move) max_level={max(max(r) for r in board)} resyncs={resyncs}")
        time.sleep(0.08)
    log(f"[2048] time up after {moves} moves (resyncs={resyncs})")
    return d.execute_script(JS_RESULT) or _canvas_image(d) is None
