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


_REF_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAHMAAAHvCAAAAABC+7+2AAA6h0lEQVR42uW9abgkR3Xn/Yvcs7a79qpe1FJLrRUtICTAFmaxZQQY"
    "A8IGjLcxZkYyDOCV4ZkZe2y/BtuM38FmbGNjDyAMNpYNYjEgQBIICbSgfWtJrW5J3eq+fbfas3KN90NkZlXdW1X3qm5Lel5Pfri3"
    "KiNPnsrIiBP/848TccRXWOaRG4l57g7D4jk/DBCI51znZo4+tzo1noe6bVJa86LpU3u/Hd5otRitdeicOr/3W3h04+9zjePyAkc/"
    "23vi9Cvgmg3qnKM+6oqJEgtL/Y/9LD/nS875VGPFqR/8AN795Dc20G5te0Spsys8GA0qOFjfVRpf5+TkqAZ7WfOr3qCCrx66bMez"
    "U7eXdq4/BtBpXrIrO1e/A4CF6ycv/X44ts5pCkMK9x2+CYCoseWs7Nyc0tl88BX7bhtfpznkYV8z+4lk9dlNv/LDuwH43vevEJ8f"
    "KPd6uGqkzmSo+bOdTu9X6UNCQXMdx5dAGNqDJDW3VF7rOefZsr4aaX4Kjnb+J7zoRZ9dGn7Z9g+N34amNx1dAKDFi/zGjDrpGrcV"
    "z84vecTYVzu2Uq713V0nr62zSWdAwa6L/nkOgCXxqvzkJP+0s6vzJvtXH1mlc/lv37AOnS2C/wvGzy3Mjb5iJx9rzr/jAiBtQycC"
    "m6xxhGy2hQPaFEQ+4HXiDeu0Rys+Jt4PQPHn0hP33LHx55wcavsGHa2Hjz77dbvSNHx/4+9zienRV2zmGq962enpt2tSuy608V+q"
    "sebYYHOsOd/K325mfeMN9c8kSdZz5fJvfBF491tOSF+ZpzmgoPp4WetrLcJpP77NxdrWyC7faj4+P0Bycf+4beiOr79v58d6T+jb"
    "Dv7wP53G1Jt/kPWV18r/NrFtteT3vrdW3ZaHjHbFzat+jjN9x5eB3S/L+pa2uTzW+ywM6Zzu9Cqd9sT9NwLbLnCy6p4uneD++cnw"
    "qmPfWtFvkj/a/kvp50v2frwzM24b2sKxgUW1TqUhZNo1EhJA1w8X0kYu3MqyN55OcR1wz5cG+/YP773ypnsGy538us/futcYs3/6"
    "/vDCcnKfPHXgjU8t3tcujzv2atXq8MKTok+K17gD8eTWT86fpI1vE0Yc1raHn7rA4tj9fc+4Bz7rb3M3YoeWaA0tnZhbfs0Uep/O"
    "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"
    "l6SRDnpem+nUDi1RSN9bPRSpHQkaa2PNk21O6htCtpwZrt/fGPI+0zgp4eQ+vp1kVa47vG0ad5M0fDvUiU3fil9xPvxOXpzJOFLv"
    "ymTdv1ts6SIv7saDaV3Y2G3H5oWnbHWRNakHuU59At4w94MVMoVBFqRb3HUV9OJadbvnpVOT7fhpyMBhi/LmoPDSh36wgbqdpc+N"
    "WsZOf3ErYGr3z22aWlpawSc2PaltKW2/5tZJkck4ac00w2whddikZGbFZurpeB2mAGOFG5LkgZIywXInXS2JU3SkWjfIiFizJgvm"
    "apmelU09N5JJ95ZpG+qL1+yS85rBH9gztWza6mJ1Pl33c9Q96Vfe9vutlTJ6zjqKnpP5/VPfYGVcahdYFk4vuJo3dNCJNPcFzftW"
    "yBR7cfPqWzprRUtw2Y4pfyjd73mb7DelOnuPN8NDD8Kb4e6hM6RGLfsdSYssAK6V6CtWKW2vCIBbFys9qAXiNm76q5tSLwA/DeGt"
    "lH4aGgeggZWaEy8SaUOKPK2TTZbJIMjedRisdB/LswLgyKM9letqJF2ZIMgYnziXHnjLJBhatz/241uskbPk1drmmT+55dPj2b50"
    "LwO9CxgmAc3QxCruu1BxFP4FkHp5rpALdZGgm58T3Vt234k188ymy35S/btTBWAUxpwFMAr0RXB00NcawY8eS5tAtEom6DFZYbIK"
    "4YcxDqvX7rVaa04dH/puq9tylUzWfDo9HnuQ/aR2K2umYau1Th5MO7t31Fi+3jw9bf+mP/b4uYmeZThTAzjvvrjx4PD2rLm0V8mU"
    "5Xu2ffCyl6u3beUtMit2czukoY3CRxflIOHu7wDFF3bbYnU1Rq8WPeyUkRyG8I0wQ30yJhvLI0QOGaze53b0Xp6uCTLSBRGalssc"
    "eVeSYFwNsUxLlKGQGCQJBjI2ljIMltRyDNbMMRgn9U237uprcFaEXytb1HAL1HMM5reZBjqhJWs5BmuFYpqOxwzhmhjs4CFgVq1a"
    "3vbS6Rx2eMdhzOkyDKgpPl4r5di6IPMKffI4cLrSuaVnhmLpOERglQwoYUBJZu/N0hCAbSBKeb9wbQG2DhglAzqKjxddQGkBCw+e"
    "5m4Oqltn0c5fzVZ8xt1SdufCB4/ZoNpMF3jpes7L2T2MS1ai2UPrNvQC04gxTbQBntvixBbdiEJvmAH5xVE1v5KPX8RRg/1Dt//m"
    "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"
)
REF_X0, REF_Y0 = 655, 140   # گوشه‌ی بالا-چپ ناحیه‌ی مرجع (ستون ثابت راهنما) در canvas استاندارد
_REF = None


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


def _ref():
    global _REF
    if _REF is None:
        _REF = np.asarray(Image.open(io.BytesIO(base64.b64decode(_REF_B64))).convert("L"), dtype=np.float32)
    return _REF


def align(img):
    """
    ستون ثابت آیکن‌های راهنما را با تصویر مرجع تطبیق می‌دهد و جابه‌جایی دقیق (dx, dy) را برمی‌گرداند.
    خروجی: (dx, dy, خطا). خطای کم (زیر ~۱۰) یعنی ستون راهنما واقعاً دیده شده است.
    """
    if img.size != STD_SIZE:
        img = img.resize(STD_SIZE, Image.LANCZOS)
    cur = np.asarray(img.convert("L"), dtype=np.float32)
    R = _ref()
    h, w = R.shape

    def err(dx, dy, step):
        y, x = REF_Y0 + dy, REF_X0 + dx
        if y < 0 or x < 0 or y + h > cur.shape[0] or x + w > cur.shape[1]:
            return 1e9
        return float(np.abs(cur[y:y + h:step, x:x + w:step] - R[::step, ::step]).mean())

    best = (1e9, 0, 0)
    for dy in range(-30, 31, 3):
        for dx in range(-30, 31, 3):
            e = err(dx, dy, 2)
            if e < best[0]:
                best = (e, dx, dy)
    e0, bx, by = best
    for dy in range(by - 2, by + 3):
        for dx in range(bx - 2, bx + 3):
            e = err(dx, dy, 1)
            if e < best[0]:
                best = (e, dx, dy)
    return best[1], best[2], best[0]


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


def _wait_start(d, log, timeout=14):
    """
    منتظر می‌ماند تا انیمیشن «GO!» تمام شود و ستون راهنما دیده شود، بعد جابه‌جایی دقیق برش را
    پیدا می‌کند و تا خوانده شدن دو خانه‌ی پایدار ادامه می‌دهد.
    """
    global _SHIFT
    end = time.time() + timeout
    prev, aligned = None, False
    while time.time() < end:
        img = _canvas_image(d)
        if img is None:
            return None
        if not aligned:
            dx, dy, e = align(img)
            if e < 10:
                _SHIFT = (dx, dy); aligned = True
                log(f"[2048] aligned: shift=({dx},{dy}) err={e:.1f}")
            else:
                time.sleep(0.15); continue
        b, worst = read_board(img)
        tiles = [x for r in b for x in r if x]
        if len(tiles) >= 2 and worst < 0.97 and b == prev:
            return b
        prev = b
        time.sleep(0.12)
    log("[2048] start screen not recognised; continuing anyway")
    img = _canvas_image(d)
    return read_board(img)[0] if img is not None else None


def play(d, seconds=68, log=print):
    """بازی را تا پایان زمان یا ناپدید شدن canvas ادامه می‌دهد. True اگر بازی تمام شد."""
    global _SHIFT
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
                    if unreadable % 5 == 0:
                        dx, dy, e = align(img)
                        if e < 10:
                            _SHIFT = (dx, dy); log(f"[2048] re-aligned: shift=({dx},{dy})")
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
