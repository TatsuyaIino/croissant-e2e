from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from playwright.sync_api import sync_playwright, Browser, BrowserContext, Playwright


@dataclass
class PWContextBundle:
    playwright: Playwright
    browser: Browser
    context: BrowserContext


def _env_true(name: str) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    return v in ("1", "true", "yes", "y", "on")


def create_context() -> PWContextBundle:
    """
    まずは安定性優先：persistent profileは使わず、毎回新規context。
    LINEなどログイン必要になったら storage_state / persistent を検討。
    """
    is_ci = _env_true("CI")
    headless = _env_true("PW_HEADLESS") if os.getenv("PW_HEADLESS") else is_ci
    channel = os.getenv("PW_CHANNEL")  # "chrome" 等（任意）

    pw = sync_playwright().start()

    launch_kwargs = {"headless": headless}
    if channel:
        launch_kwargs["channel"] = channel

    browser = pw.chromium.launch(**launch_kwargs)

    # 必要なら viewport や locale 等をここで統一
    context = browser.new_context()

    # タイムアウト統一
    context.set_default_timeout(30000)
    context.set_default_navigation_timeout(45000)

    # trace開始（stopはテスト側で）
    context.tracing.start(screenshots=True, snapshots=True, sources=True)

    return PWContextBundle(playwright=pw, browser=browser, context=context)


def close_context(bundle: PWContextBundle) -> None:
    try:
        bundle.context.close()
    except Exception:
        pass
    try:
        bundle.browser.close()
    except Exception:
        pass
    try:
        bundle.playwright.stop()
    except Exception:
        pass
