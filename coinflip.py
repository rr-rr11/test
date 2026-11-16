"""
ربات بازی «Coin-Flip» (بازی حافظه با کلیک): ۱۲ کارت = ۶ جفت. تایمر ۶۰ ثانیه.

هر کارت با کلیک رو می‌شود و چهره‌ی سکه‌اش دیده می‌شود. اگر دو کارت رو‌شده یکی نباشند، بعد از حدود ۱ ثانیه
هر دو برمی‌گردند. ربات چهره‌ها را به خاطر می‌سپارد و جفت‌ها را بدون حدس بی‌جا برمی‌دارد.
"""
import time

import numpy as np
from PIL import Image
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By

import game2048   # فقط برای گرفتن سریع تصویر canvas

# مرکز کارت‌ها (کسری از عرض و ارتفاع canvas). پیش‌فرض: چیدمان ۳ ستون × ۴ ردیف؛ بازی با بالا رفتن سطح
# چیدمان بزرگ‌تر می‌کند (مثلاً ۴×۴)، پس در شروع هر بازی از روی تصویر تشخیص داده می‌شود.
_DEFAULT_CENTERS = [(cx / 831, cy / 717) for cy in (161, 313, 467, 620) for cx in (261, 411, 561)]
_CENTERS = list(_DEFAULT_CENTERS)
_HALF = 0.05         # نیم‌اندازه‌ی برش مرکزی هر کارت (کسری از عرض)
SAME = 14.0          # فاصله‌ی کمتر از این = «احتمالاً همان سکه» (کارت یکسان ≈ ۰؛ سکه‌های مختلف معمولاً > ۶۰). تأیید نهایی با دیدن ناپدید شدن کارت‌هاست
BACK_DIST = 20.0     # فاصله‌ی امضا تا الگوی پشت‌کارت: پشت‌رو ≤ ۴، هر چهره ≥ ۵۴ (حتی چهره‌ی «R» که فیروزه‌ای است)
VERIFY_WAIT = 1.3    # بعد از رو شدن کارت دوم صبر کن تا یا ناپدید شوند (جفت درست) یا برگردند (اشتباه)


def _detect_cards(img):
    """
    کارت‌های پشت‌رو را از روی دایره‌ی فن فیروزه‌ای‌شان پیدا می‌کند (همه‌ی کارت‌ها در شروع پشت‌رو هستند).
    خروجی: لیست مرکزها (fx, fy) به ترتیب ردیف و ستون، یا None اگر نتیجه‌ی قابل‌قبولی نبود.
    """
    a = np.asarray(img.convert("RGB"), dtype=np.int16)
    mask = (a[..., 0] < 140) & (a[..., 1] > 170) & (a[..., 2] > 210)
    mask[:75, :] = False                                  # نوار بالا
    H, W = mask.shape
    ys, xs = np.nonzero(mask)
    cells = {}
    for y, x in zip(ys, xs):
        cells.setdefault((y // 8, x // 8), []).append((y, x))
    seen, blobs = set(), []
    for k in cells:
        if k in seen:
            continue
        st, pts = [k], []
        seen.add(k)
        while st:
            c = st.pop(); pts += cells[c]
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    n = (c[0] + dy, c[1] + dx)
                    if n in cells and n not in seen:
                        seen.add(n); st.append(n)
        p = np.array(pts)
        h = p[:, 0].max() - p[:, 0].min() + 1
        w = p[:, 1].max() - p[:, 1].min() + 1
        if len(p) >= 600 and 0.7 < h / w < 1.4 and 40 <= w <= 160:
            blobs.append((float(p[:, 1].mean()), float(p[:, 0].mean()), w))
    if len(blobs) < 4 or len(blobs) % 2:
        return None
    blobs.sort(key=lambda t: t[1])
    rows, cur = [], [blobs[0]]
    for b in blobs[1:]:
        if abs(b[1] - np.mean([c[1] for c in cur])) < 45:
            cur.append(b)
        else:
            rows.append(cur); cur = [b]
    rows.append(cur)
    ordered = [b for r in rows for b in sorted(r, key=lambda t: t[0])]
    return [(x / W, y / H) for x, y, _ in ordered]


def _setup_layout(img, log):
    """چیدمان کارت‌ها را تشخیص می‌دهد و مرکزها و اندازه‌ی برش را تنظیم می‌کند."""
    global _CENTERS, _HALF
    found = _detect_cards(img)
    if found is None:
        _CENTERS = list(_DEFAULT_CENTERS); _HALF = 0.05
        log(f"[flip] layout detection failed; using default {len(_CENTERS)} cards")
        return
    _CENTERS = found
    W, H = img.size
    pts = np.array([(x * W, y * H) for x, y in found])
    d = np.sqrt(((pts[:, None, :] - pts[None, :, :]) ** 2).sum(axis=2)); np.fill_diagonal(d, 1e9)
    spacing = float(np.median(d.min(axis=1)))
    _HALF = max(0.025, min(0.06, 0.277 * spacing / W))
    rows = len({round(y * H / 50) for _, y in found})
    log(f"[flip] layout: {len(found)} cards ({len(found)//rows} per row × {rows} rows), spacing {spacing:.0f}px")


def _crop(img, idx):
    w, h = img.size
    fx, fy = _CENTERS[idx]
    cx, cy, hh = fx * w, fy * h, _HALF * w
    return img.crop((int(cx - hh), int(cy - hh), int(cx + hh), int(cy + hh)))


def _cyan(im):
    a = np.asarray(im.convert("RGB"), dtype=np.int16)
    m = (a[..., 0] < 110) & (a[..., 1] > 170) & (a[..., 2] > 170)
    return float(m.mean())


def _sig(im):
    return np.asarray(im.convert("RGB").resize((12, 12), Image.LANCZOS), dtype=np.float32)


_BACK = None


def _learn_back(img):
    """الگوی پشت‌کارت: میانه‌ی امضای ۱۲ کارت در لحظه‌ای که همه پشت‌رو هستند."""
    global _BACK
    _BACK = np.median(np.stack([_sig(_crop(img, i)) for i in range(len(_CENTERS))]), axis=0)


def _is_back(img, idx):
    return float(np.abs(_sig(_crop(img, idx)) - _BACK).mean()) < BACK_DIST


def _same(a, b):
    return float(np.abs(a - b).mean()) < SAME


def _click(d, idx):
    fx, fy = _CENTERS[idx]
    canvas = d.find_element(By.CSS_SELECTOR, "canvas")
    w, h = canvas.size["width"], canvas.size["height"]
    ActionChains(d).move_to_element_with_offset(
        canvas, int(fx * w - w / 2), int(fy * h - h / 2)).click().perform()


def _face(d, idx):
    """بعد از کلیک منتظر می‌ماند تا کارت کاملاً رو شود. امضای چهره، 'GONE' (بازی تمام شد) یا None."""
    prev = None
    for attempt in range(8):
        time.sleep(0.35 if attempt == 0 else 0.15)
        img = game2048._canvas_image(d)
        if img is None:
            return "GONE"
        if not _is_back(img, idx):
            s = _sig(_crop(img, idx))
            if prev is not None and float(np.abs(s - prev).mean()) < 6.0:
                return s          # دو نمونه‌ی پشت‌سرهم یکسان = انیمیشن تمام شده
            prev = s
    return None


def play(d, seconds=72, log=print):
    """True اگر بازی تمام شد (canvas ناپدید شد)."""
    deadline = time.time() + seconds
    d.execute_script("const c=document.querySelector('canvas');if(c){window.scrollBy(0,c.getBoundingClientRect().top-100);}")
    time.sleep(4.0)                       # انیمیشن GO!
    img0 = game2048._canvas_image(d)
    if img0 is None:
        return True
    _setup_layout(img0, log)
    _learn_back(img0)
    known, matched, neq = {}, set(), {}
    clicks, stalls = 0, 0

    def same(i, j):
        return neq.get(frozenset((i, j)), 0) < 2 and _same(known[i], known[j])

    def open_card(i):
        nonlocal clicks
        for _ in range(2):
            _click(d, i); clicks += 1
            s = _face(d, i)
            if s is not None:
                return s
        return None

    def verify(a, b):
        """بعد از رو کردن هر دو کارت: True اگر جفت درست بود (دیگر پشت‌رو نیستند)، False اگر برگشتند، 'GONE' اگر بازی تمام شد."""
        time.sleep(VERIFY_WAIT)
        img = game2048._canvas_image(d)
        if img is None:
            return "GONE"
        if _is_back(img, a) or _is_back(img, b):
            return False
        return True

    def attempt(a, b):
        """هر دو کارت را رو می‌کند و نتیجه را می‌سنجد. None اگر یکی از کارت‌ها اصلاً باز نشد (حکم نده!)."""
        for i in (a, b):
            s = open_card(i)
            if isinstance(s, str):
                return "GONE"
            if s is None:
                return None
            known.setdefault(i, s)
        return verify(a, b)

    def result(pair, r, how=""):
        nonlocal stalls
        if r is None:
            stalls += 1; return
        if r:
            matched.update(pair); stalls = 0
            log(f"[flip] matched {pair} {how}-> {len(matched)//2}/{len(_CENTERS)//2}")
        else:
            key = frozenset(pair); neq[key] = neq.get(key, 0) + 1
            log(f"[flip] {pair} did NOT match (flipped back)")

    def finish(tag=""):
        log(f"[flip] game over {tag} after {clicks} clicks, matched={len(matched)//2}/{len(_CENTERS)//2}")
        return True

    while time.time() < deadline and len(matched) < len(_CENTERS) and stalls < 8:
        remaining = [i for i in range(len(_CENTERS)) if i not in matched]

        # آخرین دو کارت حتماً یک جفت‌اند، حتی اگر امضایشان فرق کند
        if len(remaining) == 2:
            r = attempt(*remaining)
            if r == "GONE": return finish()
            result(tuple(remaining), r, "(last two) ")
            continue

        # ۱) جفتِ شناخته‌شده؟
        pair = None
        items = [i for i in known if i not in matched]
        for x in range(len(items)):
            for y in range(x + 1, len(items)):
                if same(items[x], items[y]):
                    pair = (items[x], items[y]); break
            if pair: break
        if pair:
            r = attempt(*pair)
            if r == "GONE": return finish()
            result(pair, r, "(known) ")
            continue

        # ۲) کارت ناشناخته‌ی اول
        unknown = [i for i in range(len(_CENTERS)) if i not in known and i not in matched]
        if not unknown:
            # همه شناخته‌شده‌اند ولی جفتی نمی‌بینیم: شمارنده‌ی ناجور را صفر کن و نزدیک‌ترین امضاها را امتحان کن
            neq.clear()
            cands = sorted(((float(np.abs(known[x] - known[y]).mean()), x, y)
                            for x in items for y in items if x < y))
            if not cands:
                break
            r = attempt(cands[0][1], cands[0][2])
            if r == "GONE": return finish()
            result((cands[0][1], cands[0][2]), r, "(closest) ")
            continue
        u1 = unknown[0]
        s1 = open_card(u1)
        if isinstance(s1, str):
            return finish()
        if s1 is None:
            stalls += 1; continue
        known[u1] = s1
        partner = next((k for k in known if k != u1 and k not in matched and same(u1, k)), None)
        if partner is not None:
            r = attempt(u1, partner)
            if r == "GONE": return finish()
            result((u1, partner), r)
            continue

        # ۳) کارت ناشناخته‌ی دوم
        rest = [i for i in unknown if i != u1]
        if not rest:
            continue
        u2 = rest[0]
        s2 = open_card(u2)
        if isinstance(s2, str):
            return finish()
        if s2 is None:
            stalls += 1; time.sleep(VERIFY_WAIT); continue
        known[u2] = s2
        r = verify(u1, u2)
        if r == "GONE": return finish()
        result((u1, u2), r, "(lucky) ")

    # پایان: چند ثانیه صبر کن تا صفحه‌ی نتیجه بیاید
    end = time.time() + 6
    while time.time() < end:
        if game2048._canvas_image(d) is None:
            return finish("(result screen)")
        time.sleep(0.5)
    log(f"[flip] no result screen: matched={len(matched)//2}/{len(_CENTERS)//2}, clicks={clicks}")
    return False
