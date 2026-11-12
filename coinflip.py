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
SAME = 30.0          # فاصله‌ی کمتر از این = همان سکه (همان کارت در زمان‌های مختلف ≈ ۰، سکه‌های مختلف ۶۶ تا ۱۱۲)
BACK_CYAN = 0.03     # کسر پیکسل‌های فیروزه‌ای: پشت کارت ≈ ۰٫۳۸، رو‌شده ≈ ۰، نیمه‌برگشته ≈ ۰٫۱۱
FLIP_BACK_WAIT = 1.5  # بعد از ناجور بودن دو کارت، تا برگشتن هر دو صبر کن


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


def play(d, seconds=72, log=print):
    """True اگر بازی تمام شد (canvas ناپدید شد)."""
    deadline = time.time() + seconds
    d.execute_script("const c=document.querySelector('canvas');if(c){window.scrollBy(0,c.getBoundingClientRect().top-100);}")
    time.sleep(4.0)                       # انیمیشن GO!
    known, matched = {}, set()
    clicks = 0

    def open_card(i):
        nonlocal clicks
        for _ in range(2):
            _click(d, i); clicks += 1
            s = _face(d, i)
            if s is not None:
                return s
        return None

    while time.time() < deadline and len(matched) < len(CARDS):
        # ۱) جفتِ شناخته‌شده؟
        pair = None
        items = [(i, s) for i, s in known.items() if i not in matched]
        for a in range(len(items)):
            for b in range(a + 1, len(items)):
                if _same(items[a][1], items[b][1]):
                    pair = (items[a][0], items[b][0]); break
            if pair: break
        if pair:
            for i in pair:
                s = open_card(i)
                if isinstance(s, str):
                    log(f"[flip] game over after {clicks} clicks"); return True
            matched.update(pair)
            log(f"[flip] matched {pair} (known) -> {len(matched)//2}/6")
            continue

        # ۲) کارت ناشناخته‌ی اول
        unknown = [i for i in range(len(CARDS)) if i not in known and i not in matched]
        if not unknown:
            log("[flip] no unknown cards and no known pair; stopping"); break
        u1 = unknown[0]
        s1 = open_card(u1)
        if isinstance(s1, str):
            log(f"[flip] game over after {clicks} clicks"); return True
        if s1 is None:
            known[u1] = np.full((12, 12, 3), -999, dtype=np.float32)   # این کارت باز نشد؛ کنارش بگذار
            continue
        partner = next((k for k, s in known.items() if k not in matched and _same(s, s1)), None)
        known[u1] = s1
        if partner is not None:
            s = open_card(partner)
            if isinstance(s, str):
                log(f"[flip] game over after {clicks} clicks"); return True
            matched.update((u1, partner))
            log(f"[flip] matched {(u1, partner)} -> {len(matched)//2}/6")
            continue

        # ۳) کارت ناشناخته‌ی دوم
        rest = [i for i in unknown if i != u1]
        if not rest:
            break
        u2 = rest[0]
        s2 = open_card(u2)
        if isinstance(s2, str):
            log(f"[flip] game over after {clicks} clicks"); return True
        if s2 is None:
            known[u2] = np.full((12, 12, 3), -999, dtype=np.float32)
            time.sleep(FLIP_BACK_WAIT); continue
        known[u2] = s2
        if _same(s1, s2):
            matched.update((u1, u2))
            log(f"[flip] matched {(u1, u2)} (lucky) -> {len(matched)//2}/6")
            time.sleep(0.4)
        else:
            time.sleep(FLIP_BACK_WAIT)    # هر دو کارت برمی‌گردند

    # پایان: چند ثانیه صبر کن تا صفحه‌ی نتیجه بیاید
    end = time.time() + 6
    while time.time() < end:
        if game2048._canvas_image(d) is None:
            log(f"[flip] finished: matched={len(matched)//2}/6, clicks={clicks}"); return True
        time.sleep(0.5)
    log(f"[flip] ended without result screen: matched={len(matched)//2}/6, clicks={clicks}")
    return False
