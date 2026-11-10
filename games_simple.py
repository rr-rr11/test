"""بازی‌های ساده: فعلاً فقط «ربات بی‌حرکت» برای تست."""
import time


def play_idle(d, seconds=75, log=print):
    """هیچ کاری نمی‌کند تا بازی تمام شود (canvas ناپدید شود). برای ببینیم بازی خودش امتیاز می‌دهد یا نه."""
    end = time.time() + seconds
    t0 = time.time()
    while time.time() < end:
        if not d.execute_script("return !!document.querySelector('canvas')"):
            log(f"[idle] game finished after {time.time() - t0:.0f}s")
            return True
        time.sleep(1)
    log("[idle] time up, canvas still present")
    return False
