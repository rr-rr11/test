"""
ربات بازی «Cryptonoid» (آجرشکن / Breakout): پدل با ماوس حرکت می‌کند و کلیک توپ را رها می‌کند.

هر بار از canvas عکس می‌گیرد، پدل (فیروزه‌ای) و توپ (خاکستری روشن) را پیدا می‌کند، سرعت توپ را از چند فریم اخیر
تخمین می‌زند و محل فرود روی پدل را (با برگشت از دیوارها) پیش‌بینی می‌کند؛ بعد ماوس را با CDP (سریع) به آن‌جا می‌برد.
"""
import base64
import io
import time
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image

STD = (831, 717)             # اندازه‌ی استاندارد canvas
PLAY_L, PLAY_R = 22, 809     # دیوارهای کناری (مرکز توپ)
HIT_Y = 668                  # y مرکز توپ هنگام برخورد با پدل
PADDLE_Y = 683               # y مرکز پدل
HUD_BOTTOM = 66              # بالای این ناحیه‌ی نوار امتیاز/تایمر است

JS_GEOM = ("const e=document.querySelector('canvas');if(!e)return null;const c=e.getBoundingClientRect();"
           "return [c.left,c.top,c.width,c.height,window.scrollX,window.scrollY];")
JS_FIX_SCROLL = ("const c=document.querySelector('canvas');if(!c)return false;"
                 "const t=c.getBoundingClientRect().top;if(Math.abs(t-100)>3){window.scrollBy(0,t-100);}return true;")


def _frame(d):
    """(تصویر استاندارد‌شده، هندسه‌ی canvas در viewport) یا (None, None) اگر canvas رفته."""
    g = d.execute_script(JS_GEOM)
    if g is None:
        return None, None
    left, top, w, h, sx, sy = g
    params = {"format": "jpeg", "quality": 70, "fromSurface": True,
              "clip": {"x": left + sx, "y": top + sy, "width": w, "height": h, "scale": 1}}
    try:
        data = d.execute_cdp_cmd("Page.captureScreenshot", dict(params, optimizeForSpeed=True))
    except Exception:
        data = d.execute_cdp_cmd("Page.captureScreenshot", params)
    img = Image.open(io.BytesIO(base64.b64decode(data["data"]))).convert("RGB")
    if img.size != STD:
        img = img.resize(STD, Image.BILINEAR)
    return img, (left, top, w, h)


def _mouse(d, geom, x, y, kind="mouseMoved", **kw):
    left, top, w, h = geom
    d.execute_cdp_cmd("Input.dispatchMouseEvent", dict(
        type=kind, x=left + x * w / STD[0], y=top + y * h / STD[1], button="left" if kind != "mouseMoved" else "none", **kw))


def _click(d, geom, x, y):
    _mouse(d, geom, x, y, "mouseMoved")
    _mouse(d, geom, x, y, "mousePressed", clickCount=1)
    _mouse(d, geom, x, y, "mouseReleased", clickCount=1)


def detect(img):
    """(مرکز x پدل یا None، (x, y) توپ یا None)."""
    a = np.asarray(img, dtype=np.int16)
    R, G, B = a[..., 0], a[..., 1], a[..., 2]
    # پدل: فیروزه‌ی روشن در نوار پایین
    low = slice(600, 717)
    cy = (R[low] < 140) & (G[low] > 170) & (B[low] > 210)
    paddle = None
    if cy.sum() > 150:
        xs = np.nonzero(cy.any(axis=0))[0]
        paddle = float((np.percentile(xs, 2) + np.percentile(xs, 98)) / 2)
    # توپ: لکه‌ی خاکستری روشن (به‌جز نوار بالا و دیوارهای کناری)
    mn = np.minimum(np.minimum(R, G), B)
    mx = np.maximum(np.maximum(R, G), B)
    gr = (mn > 150) & ((mx - mn) < 35)
    gr[:HUD_BOTTOM, :] = False
    gr[:, :20] = False
    gr[:, STD[0] - 20:] = False
    ys, xs = np.nonzero(gr)
    ball = None
    if 15 < len(ys) < 3000:
        # خوشه‌بندی ساده روی شبکه‌ی ۴ پیکسلی
        cells = {}
        for y, x in zip(ys, xs):
            cells.setdefault((y // 6, x // 6), []).append((y, x))
        seen, best = set(), None
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
            ok = 18 <= len(p) <= 220 and 7 <= h <= 24 and 7 <= w <= 24
            if ok and (best is None or len(p) > best[0]):
                best = (len(p), float(p[:, 1].mean()), float(p[:, 0].mean()))
        if best:
            ball = (best[1], best[2])
    return paddle, ball


def _reflect(x):
    width = PLAY_R - PLAY_L
    u = (x - PLAY_L) % (2 * width)
    return PLAY_L + (u if u <= width else 2 * width - u)


def predict(hist, now):
    """محل فرود توپ روی پدل (x) از تاریخچه‌ی (t, x, y). None اگر نمی‌شود فهمید."""
    pts = [p for p in hist if now - p[0] < 0.7]
    if len(pts) < 2:
        return None
    t = np.array([p[0] for p in pts]); xs = np.array([p[1] for p in pts]); ys = np.array([p[2] for p in pts])
    if t[-1] - t[0] < 0.05:
        return None
    vx = float(np.polyfit(t, xs, 1)[0]); vy = float(np.polyfit(t, ys, 1)[0])
    x, y = xs[-1] + vx * (now - t[-1]) * 0.0, ys[-1]
    if vy < 30:                                   # بالا می‌رود یا ایستاده: همان‌جا دنبالش برو
        return float(np.clip(_reflect(xs[-1] + vx * 0.25), PLAY_L, PLAY_R))
    t_land = max(0.0, (HIT_Y - y) / vy) - (now - t[-1])
    return float(np.clip(_reflect(xs[-1] + vx * (t_land + (now - t[-1]))), PLAY_L, PLAY_R))


def _calibrate(d, geom, log):
    """
    قبل از رها کردن توپ، پدل را به چپ، راست و مرکز می‌فرستد و پاسخش را اندازه می‌گیرد:
    آیا پدل به نشانگر ماوس می‌رسد؟ با چه سرعتی؟ خروجی: سرعت تقریبی پدل (px/s) یا None.
    """
    speeds, rows = [], []
    for tx in (120, 700, 413):
        t_cmd = time.time()
        _mouse(d, geom, tx, PADDLE_Y)
        series = []
        for _ in range(9):
            img, _g = _frame(d)
            if img is None:
                return None
            p, _b = detect(img)
            series.append((time.time() - t_cmd, p))
        pts = [(t, p) for t, p in series if p is not None]
        rows.append((tx, [(round(t, 2), round(p)) for t, p in pts]))
        if len(pts) >= 3:
            sp = max(abs(pts[i + 1][1] - pts[i][1]) / max(1e-3, pts[i + 1][0] - pts[i][0]) for i in range(len(pts) - 1))
            speeds.append(sp)
    for tx, r in rows:
        log(f"[crypto] calibration target={tx}: (seconds, paddle_x) = {r}")
    v = float(np.median(speeds)) if speeds else None
    log(f"[crypto] estimated paddle speed ≈ {v:.0f}px/s" if v else "[crypto] paddle speed unknown")
    return v


def play(d, seconds=75, log=print):
    """True اگر بازی تمام شد (canvas ناپدید شد)."""
    deadline = time.time() + seconds
    d.execute_script(JS_FIX_SCROLL)
    time.sleep(3.5)                               # انیمیشن GO!
    img0, geom0 = _frame(d)
    if img0 is None:
        return True
    v_paddle = _calibrate(d, geom0, log)
    hist = deque(maxlen=6)
    t0 = time.time()
    frames = launches = moves = lost = 0
    target, errs, trace = None, [], []
    last_log = t0
    still = 0
    last_click = 0.0
    below = False

    def save_trace():
        try:
            Path("debug").mkdir(exist_ok=True)
            with open("debug/crypto_trace.csv", "w") as f:
                f.write("t,ball_x,ball_y,paddle_x,target,event\n")
                for r in trace:
                    f.write(",".join("" if v is None else (f"{v:.1f}" if isinstance(v, float) else str(v)) for v in r) + "\n")
        except Exception as e:
            log(f"[crypto] trace save failed: {e}")

    try:
        while time.time() < deadline:
            img, geom = _frame(d)
            if img is None:
                log(f"[crypto] canvas gone after {time.time()-t0:.0f}s: frames={frames} launches={launches} lost={lost}"); return True
            now = time.time(); frames += 1
            paddle, ball = detect(img)
            if paddle is not None and target is not None:
                errs.append(abs(paddle - target))
            if ball is None:
                trace.append((now - t0, None, None, paddle, target, "noball"))
                hist.clear()
                continue
            if hist and (abs(ball[0] - hist[-1][1]) + abs(ball[1] - hist[-1][2])) < 2.5:
                still += 1
            else:
                still = 0
            hist.append((now, ball[0], ball[1]))
            event = ""
            if ball[1] > HIT_Y + 22:                      # زیر پدل: توپ از دست رفت
                if not below:
                    lost += 1; below = True; event = "LOST"
            else:
                below = False
            on_paddle = ball[1] > HIT_Y - 40 and (paddle is None or abs(ball[0] - paddle) < 90)
            if on_paddle and still >= 2 and now - last_click > 1.0:
                _click(d, geom, ball[0], 600); launches += 1; last_click = now      # رها کردن توپ
                hist.clear(); still = 0
                trace.append((now - t0, ball[0], ball[1], paddle, target, "LAUNCH"))
                continue
            if on_paddle and still >= 1:
                pred = ball[0]                            # توپ روی پدل است؛ دنبالش نرو (از رانش جلوگیری)
            else:
                pred = predict(list(hist), now)
                if pred is None:
                    pred = ball[0]
            target = pred
            _mouse(d, geom, target, PADDLE_Y)
            moves += 1
            trace.append((now - t0, ball[0], ball[1], paddle, target, event))
            if now - last_log > 2.0:
                last_log = now
                med = float(np.median(errs[-30:])) if errs else -1
                log(f"[crypto] t={now-t0:.0f}s fps={frames/(now-t0):.1f} ball=({ball[0]:.0f},{ball[1]:.0f}) paddle={paddle if paddle is None else round(paddle)} target={target:.0f} track_err={med:.0f}px lost={lost}")
        log(f"[crypto] time up: frames={frames} launches={launches} moves={moves} lost={lost}")
        img, _ = _frame(d)
        return img is None
    finally:
        save_trace()
