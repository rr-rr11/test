"""بازی‌های ساده / آزمایشی: ربات «بی‌حرکت» که فقط منتظر پایان بازی می‌ماند و چند عکس میان‌بازی می‌گیرد."""
import re
import time
from pathlib import Path

import game2048


def play_idle(d, seconds=75, log=print, name="game", shots=(6, 18, 32)):
    """هیچ حرکتی نمی‌کند. در ثانیه‌های shots از canvas عکس می‌گیرد (debug/idle_<name>_<t>s.png)."""
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    t0 = time.time()
    pending = list(shots)
    while time.time() - t0 < seconds:
        if not d.execute_script("return !!document.querySelector('canvas')"):
            log(f"[idle:{name}] game finished after {time.time() - t0:.0f}s")
            return True
        if pending and time.time() - t0 >= pending[0]:
            t = pending.pop(0)
            img = game2048._canvas_image(d)
            if img is not None:
                game2048._dump(img, f"idle_{slug}_{t}s")
        time.sleep(0.5)
    log(f"[idle:{name}] time up, canvas still present")
    return False


def make_idle(name):
    def bot(d, seconds=75, log=print):
        return play_idle(d, seconds, log, name)
    return bot
