from __future__ import annotations

import time
from typing import Iterable, Optional

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError


def is_domain_in(url: str, domains: Iterable[str]) -> bool:
    u = (url or "").lower()
    return any(d.lower() in u for d in domains)


def safe_click(locator, timeout_ms: int = 15000) -> None:
    """
    clickが詰まる場合に備えて押し切る。
    """
    locator.first.wait_for(timeout=timeout_ms)
    try:
        locator.first.scroll_into_view_if_needed(timeout=timeout_ms)
    except Exception:
        pass

    try:
        locator.first.click(timeout=timeout_ms)
        return
    except Exception:
        pass

    try:
        locator.first.click(timeout=timeout_ms, force=True)
        return
    except Exception:
        pass

    locator.first.evaluate("el => el.click()")


def click_and_get_external_page(current_page: Page, trigger_locator, external_domains: list[str], timeout_sec: float = 12.0) -> Page:
    """
    クリック後に popup / 新規タブ / 同一タブ遷移 のいずれでも
    external_domainsに合致するページが取れれば返す。
    """
    ctx = current_page.context
    before_pages = set(ctx.pages)

    # popup狙い
    try:
        with current_page.expect_popup(timeout=3000) as pop:
            safe_click(trigger_locator, timeout_ms=15000)
        p = pop.value
        try:
            p.bring_to_front()
        except Exception:
            pass
        if is_domain_in(p.url, external_domains):
            return p
        # popup取れたがドメイン違いなら後続探索へ
    except Exception:
        # popup出ないケース
        safe_click(trigger_locator, timeout_ms=15000)

    end = time.time() + timeout_sec
    while time.time() < end:
        # 新規タブ探索
        for p in list(ctx.pages):
            if p not in before_pages and is_domain_in(p.url, external_domains):
                try:
                    p.bring_to_front()
                except Exception:
                    pass
                return p
        # 同一タブ遷移
        if is_domain_in(current_page.url, external_domains):
            return current_page
        time.sleep(0.2)

    # 最後に全探索
    for p in list(ctx.pages):
        if is_domain_in(p.url, external_domains):
            return p

    return current_page


def find_draw_count_page(context, timeout_sec: float = 60.0) -> Page:
    """
    抽選回数画面（'1'ボタンが見える）に戻ったページを探す。
    """
    end = time.time() + timeout_sec
    while time.time() < end:
        for p in list(context.pages):
            try:
                loc = p.get_by_text("1", exact=True)
                if loc.count() > 0:
                    try:
                        loc.first.wait_for(timeout=1200)
                        return p
                    except PlaywrightTimeoutError:
                        pass
            except Exception:
                pass
        time.sleep(0.4)
    raise PlaywrightTimeoutError("draw count screen not found")
