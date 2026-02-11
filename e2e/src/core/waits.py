import time


def wait_until_src_changes(locator, prev_src: str, timeout_sec: float = 15.0, interval_sec: float = 0.2) -> bool:
    end = time.time() + timeout_sec
    while time.time() < end:
        cur = (locator.get_attribute("src") or "").strip()
        if cur and cur != prev_src:
            return True
        time.sleep(interval_sec)
    return False
