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
PADDLE_Y = 683               # y مرکز پدل (فقط برای تشخیص)
POINTER_Y = 560              # y نشانگر ماوس: پایین‌تر از ~۶۵۰ نوار ثابت ناوبری صفحه روی canvas می‌افتد و رویداد ماوس را می‌خورد
MAX_BALL_Y = 688             # لکه‌های پایین‌تر از این (آیکن‌های نوار ناوبری ثابت صفحه) هرگز توپ نیستند
CAP_Y = 662                  # لکه‌های خاکستری پایین‌تر از این و نزدیک پدل = سرپوش‌های پدل، نه توپ
HUD_BOTTOM = 66              # بالای این ناحیه‌ی نوار امتیاز/تایمر است

JS_GEOM = ("const e=document.querySelector('canvas');if(!e)return null;const c=e.getBoundingClientRect();"
           "return [c.left,c.top,c.width,c.height,window.scrollX,window.scrollY];")
# canvas را بالا ببر (بالای آن ۲۰ پیکسل از بالای viewport): هدر ثابت فقط نوار امتیاز/تایمر را می‌پوشاند، و
# نوار ناوبری ثابت پایین (آیکن‌های خانه/سبد) دیگر روی پدل و توپ نمی‌افتد (در ۱۰۰ پیکسل، آیکن خانه زیر پدل بود).
JS_FIX_SCROLL = ("const c=document.querySelector('canvas');if(!c)return false;"
                 "const t=c.getBoundingClientRect().top;if(Math.abs(t-20)>3){window.scrollBy(0,t-20);}return true;")


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


def _blobs(mask, min_px, max_px, lo, hi):
    """
    لکه‌های کوچکِ یک ماسک دودویی: [(تعداد پیکسل، x مرکز، y مرکز)] با اندازه‌ی جعبه‌ی lo..hi.
    برای سرعت، اول ماسک روی خانه‌های ۶×۶ جمع می‌شود و فقط خانه‌های غیرصفر خوشه‌بندی می‌شوند.
    """
    H, W = mask.shape
    gh, gw = H // 6, W // 6
    m = mask[:gh * 6, :gw * 6]
    cnt = m.reshape(gh, 6, gw, 6).sum(axis=(1, 3))
    if cnt.sum() < min_px:
        return []
    X = np.arange(gw * 6, dtype=np.int32)[None, :]
    Y = np.arange(gh * 6, dtype=np.int32)[:, None]
    sx = (m * X).reshape(gh, 6, gw, 6).sum(axis=(1, 3))
    sy = (m * Y).reshape(gh, 6, gw, 6).sum(axis=(1, 3))
    nz = set(zip(*[a.tolist() for a in np.nonzero(cnt)]))
    if len(nz) > 900:
        return []
    seen, out = set(), []
    for k in nz:
        if k in seen:
            continue
        st, comp = [k], []
        seen.add(k)
        while st:
            c = st.pop(); comp.append(c)
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    n = (c[0] + dy, c[1] + dx)
                    if n in nz and n not in seen:
                        seen.add(n); st.append(n)
        n_px = int(sum(cnt[c] for c in comp))
        gy = [c[0] for c in comp]; gx = [c[1] for c in comp]
        h = (max(gy) - min(gy) + 1) * 6
        w = (max(gx) - min(gx) + 1) * 6
        if min_px <= n_px <= max_px and lo - 6 <= h <= hi + 12 and lo - 6 <= w <= hi + 12:
            out.append((n_px, float(sum(sx[c] for c in comp)) / n_px, float(sum(sy[c] for c in comp)) / n_px))
    return out


def detect(img, ref=None, near=None, ignore=()):
    """
    (مرکز x پدل یا None، (x, y) توپ یا None).
    توپ: ۱) لکه‌ی خاکستری روشن (به‌جز سرپوش‌های پدل)؛ ۲) اگر ref (تصویر مرجع بدون توپ در حال پرواز) داده شود،
    لکه‌ی کوچکِ متحرک نسبت به آن، مستقل از رنگ (توپ در پرواز همیشه خاکستری نیست).
    near: آخرین موقعیت شناخته‌شده‌ی توپ برای انتخاب بین چند نامزد.
    """
    a = img if isinstance(img, np.ndarray) else np.asarray(img, dtype=np.int16)
    R, G, B = a[..., 0], a[..., 1], a[..., 2]
    # پدل: فیروزه‌ی روشن فقط در نوار باریک اطراف پدل (توپ‌ی که رنگی شود، با پدل اشتباه نشود)
    band = slice(664, 704)
    cy = (R[band] < 140) & (G[band] > 170) & (B[band] > 210)
    paddle = None
    if cy.sum() > 150:
        xs = np.nonzero(cy.any(axis=0))[0]
        if xs.max() - xs.min() > 60:
            paddle = float((np.percentile(xs, 2) + np.percentile(xs, 98)) / 2)

    def pick(cands):
        cands = [c for c in cands if c[2] <= MAX_BALL_Y and
                 all((c[1] - ix) ** 2 + (c[2] - iy) ** 2 > 28 ** 2 for ix, iy in ignore)]
        if not cands:
            return None
        if near is not None:
            return min(cands, key=lambda c: (c[1] - near[0]) ** 2 + (c[2] - near[1]) ** 2)
        return max(cands, key=lambda c: c[0])

    def drop_caps(cands):
        return [c for c in cands if not (c[2] >= CAP_Y and (paddle is None or abs(c[1] - paddle) < 110))]

    # ۱) خاکستری روشن. توپ در پرواز دُمِ محوشونده (کومت) دارد که تا ~۶۰ پیکسل کشیده می‌شود؛ سر توپ روشن‌ترین
    #    بخش است (min-channel ≈ ۱۷۰ تا ۲۰۵، دُم ≈ ۱۴۰ تا ۱۷۷). با آستانه‌ی بالا فقط سر جدا می‌شود.
    mn = np.minimum(np.minimum(R, G), B)
    mx = np.maximum(np.maximum(R, G), B)
    lowsat = (mx - mn) < 45
    for thr in (190, 172, 150):
        gr = lowsat & (mn > thr)
        gr[:HUD_BOTTOM, :] = False
        gr[:, :20] = False
        gr[:, STD[0] - 20:] = False
        c = pick(drop_caps(_blobs(gr, 12, 220, 7, 26)))
        if c:
            return paddle, (c[1], c[2])
    # ۲) حرکت نسبت به تصویر مرجع (مستقل از رنگ)
    if ref is not None:
        diff = np.abs(a - ref).sum(axis=2) > 80
        diff[:HUD_BOTTOM, :] = False
        diff[:, :20] = False
        diff[:, STD[0] - 20:] = False
        diff[CAP_Y - 24:, :] = False                      # ناحیه‌ی پدل: خودش جابه‌جا می‌شود
        c = pick(_blobs(diff, 40, 450, 8, 28))
        if c:
            return paddle, (c[1], c[2])
    return paddle, None


BX = [117 + 83.9 * c for c in range(8)]      # مرکز ستون آجرها (x)
BY = [156, 233, 311]                          # مرکز ردیف آجرها (y)؛ ردیف ۲ پایین‌ترین است
AIM_MAX = 38.0                                # حداکثر فاصله‌ی ضربه از مرکز پدل (px)؛ بیشتر از این خطر از دست رفتن توپ دارد
REBOUND_COEF = 4.6                            # از ردیابی واقعی: vx_out ≈ 0.93·vx_in + 4.6·offset
V_UP = 430.0                                  # سرعت عمودی توپ (px/s)


def bricks_present(a):
    """مجموعه‌ی آجرهای باقی‌مانده {(ردیف، ستون)} از روی پیکسل‌های سبز."""
    R, G, B = a[..., 0], a[..., 1], a[..., 2]
    mask = (G > 120) & (R < 70) & (B < 120)
    out = set()
    for r in range(3):
        y0, y1 = int(BY[r] - 24), int(BY[r] + 24)
        for c in range(8):
            x0, x1 = int(BX[c] - 24), int(BX[c] + 24)
            if mask[y0:y1, x0:x1].sum() > 400:
                out.add((r, c))
    return out


def aim_offset(x_land, vx_in, bricks):
    """
    چه‌قدر از مرکز پدل به توپ ضربه بزنیم تا بعد از برگشت به سمت آجری برود که سریع‌تر از بقیه برمی‌گردد:
    پایین‌ترین ردیف (رفت‌وبرگشت کوتاه‌تر) و نزدیک‌ترین ستون. offset = x_توپ − x_پدل؛ مثبت = توپ به راست می‌رود.
    """
    if not bricks:
        return 0.0
    best = None
    for (r, c) in bricks:
        dx = BX[c] - x_land
        t_up = (HIT_Y - BY[r]) / V_UP
        need = dx / t_up
        if abs(need) > 330:
            continue                                # با این زاویه نمی‌رسیم
        score = r * 1000 - abs(dx)
        if best is None or score > best[0]:
            best = (score, need)
    if best is None:
        r, c = min(bricks, key=lambda b: abs(BX[b[1]] - x_land))
        need = max(-330.0, min(330.0, (BX[c] - x_land) / ((HIT_Y - BY[r]) / V_UP)))
    else:
        need = best[1]
    off = (need - 0.93 * vx_in) / REBOUND_COEF
    return float(max(-AIM_MAX, min(AIM_MAX, off)))


def kinematics(hist, now):
    """(vx, vy, x_land) از دو نقطه‌ی آخر؛ x_land محل فرود توپ روی خط پدل (با برگشت از دیوارها). None اگر کافی نیست."""
    pts = list(hist)
    if len(pts) < 2:
        return None
    (t1, x1, y1), (t2, x2, y2) = pts[-2], pts[-1]
    dt = max(1e-3, t2 - t1)
    if dt > 0.5:
        return None
    vx = max(-1200.0, min(1200.0, (x2 - x1) / dt))
    vy = (y2 - y1) / dt
    if vy < 60:
        return vx, vy, None
    t_land = max(0.0, (HIT_Y - y2) / vy - (now - t2))
    x_land = float(np.clip(_reflect(x2 + vx * (t_land + (now - t2))), PLAY_L, PLAY_R))
    return vx, vy, x_land


def _reflect(x):
    width = PLAY_R - PLAY_L
    u = (x - PLAY_L) % (2 * width)
    return PLAY_L + (u if u <= width else 2 * width - u)


def predict(hist, now):
    """
    جای پدل برای گرفتن توپ. پدل بی‌درنگ دنبال ماوس می‌آید (در کالیبراسیون ثابت شد)، پس لازم نیست محل فرود
    را با برگشت از دیوار و آجر حدس بزنیم؛ کافی است همیشه زیر توپ باشیم و فقط تأخیر ~۰٫۱ ثانیه‌ی عکس‌برداری را
    با سرعت لحظه‌ای (از دو نقطه‌ی آخر) جبران کنیم. اگر هنوز دو نقطه نداریم None.
    """
    pts = list(hist)
    if len(pts) < 2:
        return None
    (t1, x1, y1), (t2, x2, y2) = pts[-2], pts[-1]
    dt = max(1e-3, t2 - t1)
    if dt > 0.5:
        return None
    vx = max(-1200.0, min(1200.0, (x2 - x1) / dt))
    vy = (y2 - y1) / dt
    lead = 0.10 if vy > 0 else 0.06                # پایین‌رو: جلوتر؛ بالارو: کمتر
    if vy > 30:
        lead = min(lead, max(0.0, (HIT_Y - y2) / vy))   # از لحظه‌ی برخورد جلوتر نرو
    x = x2 + vx * (lead + (now - t2))
    return float(np.clip(_reflect(x), PLAY_L, PLAY_R))


def _calibrate(d, geom, log):
    """
    قبل از رها کردن توپ، پدل را به چپ، راست و مرکز می‌فرستد و پاسخش را اندازه می‌گیرد:
    آیا پدل به نشانگر ماوس می‌رسد؟ با چه سرعتی؟ خروجی: سرعت تقریبی پدل (px/s) یا None.
    """
    speeds, rows = [], []
    for tx in (120, 700, 413):
        t_cmd = time.time()
        _mouse(d, geom, tx, POINTER_Y)
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
    ref = None          # تشخیص حرکت مبتنی بر مرجع خاموش است (کند بود و لازم نشد)
    dumped = 0
    stat = np.zeros((STD[1], STD[0]), dtype=np.uint8) if ref is not None else None
    prev_a = None
    ignore = []
    t0 = time.time()
    frames = launches = moves = lost = aimed = 0
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
            near = (hist[-1][1], hist[-1][2]) if hist and now - hist[-1][0] < 0.4 else None
            a_now = np.asarray(img, dtype=np.int16)
            bricks = bricks_present(a_now)
            paddle, ball = detect(a_now, ref, near, ignore)
            if ref is not None:
                if prev_a is not None:
                    stable = np.abs(a_now - prev_a).sum(axis=2) < 30
                    differs = np.abs(a_now - ref).sum(axis=2) > 80
                    stat = np.where(differs & stable, np.minimum(stat + 1, 250), 0).astype(np.uint8)
                    upd = stat >= 4                              # چند فریم ثابت و متفاوت از مرجع: آجر شکسته → پس‌زمینه
                    if upd.any():
                        ref[upd] = a_now[upd]; stat[upd] = 0
                prev_a = a_now
            if paddle is not None and target is not None:
                errs.append(abs(paddle - target))
            if ball is None:
                trace.append((now - t0, None, None, paddle, target, "noball"))
                if launches and dumped < 6 and frames % 7 == 0:       # چند فریم بدون توپ برای عیب‌یابی
                    try:
                        Path("debug").mkdir(exist_ok=True)
                        img.save(f"debug/crypto_noball_{dumped}.png"); dumped += 1
                    except Exception:
                        pass
                if hist and now - hist[-1][0] > 0.5:
                    hist.clear()
                continue
            # سرعت لحظه‌ای توپ (px/s) از دو نقطه‌ی آخر: توپ چسبیده به پدل تقریباً ساکن است
            speed = None
            if hist and now - hist[-1][0] < 0.5:
                dt = max(1e-3, now - hist[-1][0])
                speed = ((ball[0] - hist[-1][1]) ** 2 + (ball[1] - hist[-1][2]) ** 2) ** 0.5 / dt
            slow = speed is not None and speed < 150 and (HIT_Y - 20) <= ball[1] <= (HIT_Y - 4)
            still = still + 1 if slow else 0
            hist.append((now, ball[0], ball[1]))
            event = ""
            if ball[1] > HIT_Y + 22:                      # زیر پدل: توپ از دست رفت
                if not below:
                    lost += 1; below = True; event = "LOST"
            else:
                below = False
            on_paddle = ball[1] > HIT_Y - 40 and (paddle is None or abs(ball[0] - paddle) < 90)
            if still >= 25 and not on_paddle:             # ۲٫۵ ثانیه کاملاً ثابت و دور از پدل: مصنوع، نه توپ
                ignore.append((ball[0], ball[1])); hist.clear(); still = 0
                log(f"[crypto] ignoring static object at ({ball[0]:.0f},{ball[1]:.0f})")
                continue
            if on_paddle and slow and still >= 2 and now - last_click > 1.0:
                _click(d, geom, ball[0], POINTER_Y); launches += 1; last_click = now      # رها کردن توپ
                hist.clear(); still = 0
                trace.append((now - t0, ball[0], ball[1], paddle, target, "LAUNCH"))
                continue
            if on_paddle and slow:
                pred = ball[0]                            # توپ روی پدل است؛ دنبالش نرو (از رانش و فرار پدل به دیوار جلوگیری)
            else:
                pred = predict(list(hist), now)
                if pred is None:
                    pred = ball[0]
                kin = kinematics(hist, now)
                if kin and kin[2] is not None and kin[1] > 150 and 430 <= ball[1] <= HIT_Y and bricks:
                    off = aim_offset(kin[2], kin[0], bricks)      # هدف‌گیری: از کنار پدل ضربه بزن تا به آجر برود
                    pred = float(np.clip(kin[2] - off, PLAY_L, PLAY_R))
                    aimed += 1
            target = pred
            _mouse(d, geom, target, POINTER_Y)
            moves += 1
            trace.append((now - t0, ball[0], ball[1], paddle, target, event))
            if now - last_log > 2.0:
                last_log = now
                med = float(np.median(errs[-30:])) if errs else -1
                log(f"[crypto] t={now-t0:.0f}s fps={frames/(now-t0):.1f} ball=({ball[0]:.0f},{ball[1]:.0f}) paddle={paddle if paddle is None else round(paddle)} target={target:.0f} track_err={med:.0f}px bricks={len(bricks)} aimed={aimed}")
        log(f"[crypto] time up: frames={frames} launches={launches} moves={moves} lost={lost}")
        img, _ = _frame(d)
        return img is None
    finally:
        save_trace()
