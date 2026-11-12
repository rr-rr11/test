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

# مرکز کارت‌ها (نسبت به canvas 831×717): ۳ ستون × ۴ ردیف
CX = [261 / 831, 411 / 831, 561 / 831]
CY = [161 / 717, 313 / 717, 467 / 717, 620 / 717]
CARDS = [(r, c) for r in range(4) for c in range(3)]
HALF = 0.05          # نیم‌اندازه‌ی برش مرکزی هر کارت (نسبت به عرض)
SAME = 14.0          # فاصله‌ی کمتر از این = «احتمالاً همان سکه» (کارت یکسان ≈ ۰؛ سکه‌های مختلف معمولاً > ۶۰). تأیید نهایی با دیدن ناپدید شدن کارت‌هاست
BACK_CYAN = 0.03     # کسر پیکسل‌های فیروزه‌ای: پشت کارت ≈ ۰٫۳۸، رو‌شده ≈ ۰، نیمه‌برگشته ≈ ۰٫۱۱
VERIFY_WAIT = 1.3    # بعد از رو شدن کارت دوم صبر کن تا یا ناپدید شوند (جفت درست) یا برگردند (اشتباه)
BACK_FRAC = 0.2      # کسر فیروزه‌ای بیشتر از این = کارت دوباره پشت‌رو است


def _crop(img, idx):
    r, c = CARDS[idx]
    w, h = img.size
    cx, cy, hh = CX[c] * w, CY[r] * h, HALF * w
    return img.crop((int(cx - hh), int(cy - hh), int(cx + hh), int(cy + hh)))


def _cyan(im):
    a = np.asarray(im.convert("RGB"), dtype=np.int16)
    m = (a[..., 0] < 110) & (a[..., 1] > 170) & (a[..., 2] > 170)
    return float(m.mean())


def _sig(im):
    return np.asarray(im.convert("RGB").resize((12, 12), Image.LANCZOS), dtype=np.float32)


def _same(a, b):
    return float(np.abs(a - b).mean()) < SAME


def _click(d, idx):
    r, c = CARDS[idx]
    canvas = d.find_element(By.CSS_SELECTOR, "canvas")
    w, h = canvas.size["width"], canvas.size["height"]
    ActionChains(d).move_to_element_with_offset(
        canvas, int(CX[c] * w - w / 2), int(CY[r] * h - h / 2)).click().perform()


def _face(d, idx):
    """بعد از کلیک منتظر می‌ماند تا کارت کاملاً رو شود. امضای چهره، 'GONE' (بازی تمام شد) یا None."""
    prev = None
    for attempt in range(8):
        time.sleep(0.35 if attempt == 0 else 0.15)
        img = game2048._canvas_image(d)
        if img is None:
            return "GONE"
        cr = _crop(img, idx)
        if _cyan(cr) < BACK_CYAN:
            s = _sig(cr)
            if prev is not None and float(np.abs(s - prev).mean()) < 6.0:
                return s          # دو نمونه‌ی پشت‌سرهم یکسان = انیمیشن تمام شده
            prev = s
    return None


def _is_back(img, idx):
    return _cyan(_crop(img, idx)) > BACK_FRAC


def play(d, seconds=72, log=print):
    """True اگر بازی تمام شد (canvas ناپدید شد)."""
    deadline = time.time() + seconds
    d.execute_script("const c=document.querySelector('canvas');if(c){window.scrollBy(0,c.getBoundingClientRect().top-100);}")
    time.sleep(4.0)                       # انیمیشن GO!
    known, matched, neq = {}, set(), set()
    clicks = 0

    def same(i, j):
        return frozenset((i, j)) not in neq and _same(known[i], known[j])

    def open_card(i):
        nonlocal clicks
        for _ in range(2):
            _click(d, i); clicks += 1
            s = _face(d, i)
            if s is not None:
                return s
        return None

    def verify(a, b):
        """بعد از رو کردن دو کارت: True اگر جفت درست بود (کارت‌ها دیگر پشت‌رو نیستند)، False اگر برگشتند، 'GONE' اگر بازی تمام شد."""
        time.sleep(VERIFY_WAIT)
        img = game2048._canvas_image(d)
        if img is None:
            return "GONE"
        if _is_back(img, a) or _is_back(img, b):
            return False
        return True

    def finish(tag=""):
        log(f"[flip] game over {tag} after {clicks} clicks, matched={len(matched)//2}/6")
        return True

    while time.time() < deadline and len(matched) < len(CARDS):
        # ۱) جفتِ شناخته‌شده؟
        pair = None
        items = [i for i in known if i not in matched]
        for x in range(len(items)):
            for y in range(x + 1, len(items)):
                if same(items[x], items[y]):
                    pair = (items[x], items[y]); break
            if pair: break
        if pair:
            a, b = pair
            for i in pair:
                if isinstance(open_card(i), str):
                    return finish()
            r = verify(a, b)
            if r == "GONE": return finish()
            if r:
                matched.update(pair); log(f"[flip] matched {pair} (known) -> {len(matched)//2}/6")
            else:
                neq.add(frozenset(pair)); log(f"[flip] {pair} looked the same but are NOT a pair")
            continue

        # ۲) کارت ناشناخته‌ی اول
        unknown = [i for i in range(len(CARDS)) if i not in known and i not in matched]
        if not unknown:
            log("[flip] no unknown cards and no known pair; stopping"); break
        u1 = unknown[0]
        s1 = open_card(u1)
        if isinstance(s1, str):
            return finish()
        if s1 is None:
            known[u1] = np.full((12, 12, 3), -999, dtype=np.float32); continue
        known[u1] = s1
        partner = next((k for k in known if k != u1 and k not in matched and same(u1, k)), None)
        if partner is not None:
            if isinstance(open_card(partner), str):
                return finish()
            r = verify(u1, partner)
            if r == "GONE": return finish()
            if r:
                matched.update((u1, partner)); log(f"[flip] matched {(u1, partner)} -> {len(matched)//2}/6")
            else:
                neq.add(frozenset((u1, partner))); log(f"[flip] {(u1, partner)} looked the same but are NOT a pair")
            continue

        # ۳) کارت ناشناخته‌ی دوم
        rest = [i for i in unknown if i != u1]
        if not rest:
            break
        u2 = rest[0]
        s2 = open_card(u2)
        if isinstance(s2, str):
            return finish()
        if s2 is None:
            known[u2] = np.full((12, 12, 3), -999, dtype=np.float32)
            time.sleep(VERIFY_WAIT); continue
        known[u2] = s2
        r = verify(u1, u2)
        if r == "GONE": return finish()
        if r:
            matched.update((u1, u2)); log(f"[flip] matched {(u1, u2)} (lucky) -> {len(matched)//2}/6")
        elif _same(s1, s2):
            neq.add(frozenset((u1, u2)))

    # پایان: چند ثانیه صبر کن تا صفحه‌ی نتیجه بیاید
    end = time.time() + 6
    while time.time() < end:
        if game2048._canvas_image(d) is None:
            return finish("(result screen)")
        time.sleep(0.5)
    log(f"[flip] no result screen: matched={len(matched)//2}/6, clicks={clicks}")
    return False
