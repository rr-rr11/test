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


def read_board(img):
    """تصویر PIL از canvas -> (جدول ۴×۴ از سطح‌ها، بدترین نسبت best/second). ۰ = خانه خالی."""
    if img.size != STD_SIZE:
        img = img.resize(STD_SIZE, Image.LANCZOS)
    legend = [_feat(_crop(img, LEG_X, y, LEG_HALF)) for y in LEG_Y]
    board, worst = [], 0.0
    for r in range(4):
        row = []
        for c in range(4):
            crop = _crop(img, COL_X[c], ROW_Y[r], TILE_HALF)
            inner = _crop(img, COL_X[c], ROW_Y[r], 0.036)
            arr = np.asarray(inner.convert("RGB"), dtype=np.float32)
            if arr.reshape(-1, 3).std(axis=0).mean() < EMPTY_STD:
                row.append(0)
                continue
            f = _feat(crop)
            dists = [_dist(f, t) for t in legend]
            order = np.argsort(dists)
            row.append(int(order[0]) + 1)
            worst = max(worst, dists[int(order[0])] / max(dists[int(order[1])], 1e-6))
        board.append(tuple(row))
    return tuple(board), worst


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


def _canvas_image(d):
    """تصویر سریع فقط از ناحیه‌ی canvas (CDP)."""
    r = d.execute_script(
        "const c=document.querySelector('canvas').getBoundingClientRect();"
        "return [c.left+window.scrollX,c.top+window.scrollY,c.width,c.height];")
    data = d.execute_cdp_cmd("Page.captureScreenshot", {
        "format": "jpeg", "quality": 85, "fromSurface": True,
        "clip": {"x": r[0], "y": r[1], "width": r[2], "height": r[3], "scale": 1}})
    return Image.open(io.BytesIO(base64.b64decode(data["data"]))).convert("RGB")


def _read_stable(d, tries=4):
    prev = None
    for _ in range(tries):
        b, worst = read_board(_canvas_image(d))
        if b == prev:
            return b, worst
        prev = b
        time.sleep(0.06)
    return prev, 99.0


def play(d, seconds=68, log=print):
    """بازی را تا پایان زمان یا نمایش صفحه‌ی نتیجه ادامه می‌دهد. True اگر به صفحه‌ی نتیجه رسید."""
    deadline = time.time() + seconds
    d.execute_script("document.querySelector('canvas').scrollIntoView({block:'center'});")
    time.sleep(0.5)
    moves, unreadable, resyncs = 0, 0, 0
    board, pred = None, None
    while time.time() < deadline:
        if moves % 4 == 0 and d.execute_script(JS_RESULT):
            log(f"[2048] result screen after {moves} moves (resyncs={resyncs})")
            return True
        actual, worst = _read_stable(d)
        if actual is None or worst > 0.97:
            unreadable += 1
            if unreadable > 40:
                log("[2048] too many unreadable frames"); return False
            time.sleep(0.1); continue
        if pred is not None:
            fixed, new = reconcile(pred, actual)
            if fixed is not None and new == 0 and any(0 in r for r in pred):
                time.sleep(0.12)                      # خانه‌ی جدید هنوز ظاهر نشده
                actual, worst = _read_stable(d)
                fixed, new = reconcile(pred, actual)
            if fixed is not None:
                board = fixed
            else:
                board = actual; resyncs += 1          # کلید اعمال نشد یا ناسازگاری؛ به تصویر اعتماد کن
        else:
            board = actual
        order = best_moves(board)
        if not order:
            log("[2048] no moves left"); time.sleep(1.0)
            if d.execute_script(JS_RESULT): return True
            pred = None; continue
        ActionChains(d).send_keys(KEYS[order[0]]).perform()
        pred = move(board, order[0])
        moves += 1
        if moves % 20 == 0:
            log(f"[2048] moves={moves} max_level={max(max(r) for r in board)} resyncs={resyncs}")
        time.sleep(0.10)
    log(f"[2048] time up after {moves} moves (resyncs={resyncs})")
    return d.execute_script(JS_RESULT)
