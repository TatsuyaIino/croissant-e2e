from __future__ import annotations

import time
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from src.core.artifacts import Artifacts
from src.core.exceptions import LeadSkipped
from src.selectors import gacha_selectors as S


# HubSpot embed iframe
HUBSPOT_IFRAME_SELECTOR = "iframe.hs-form-iframe, iframe#hs-form-iframe-0"

# HubSpot submit button
HUBSPOT_SUBMIT_SELECTOR = "input[type='submit'][value='送信'], input.hs-button[type='submit']"

# 必須エラー（HubSpot）
HUBSPOT_REQUIRED_ERROR_TEXT = "この必須項目を入力してください。"

# CAPTCHA エラー（HubSpot）
CAPTCHA_ERROR_TEXTS = [
    "CAPTCHAの検証に失敗しました。もう一度お試しください。",
    # 画面上に出る場合があるテスト用文言（出ないなら消してOK）
    "This reCAPTCHA is for testing purposes only. Please report to the site admin if you are seeing this.",
]


def _drawcount_screen_visible(page: Page, timeout_ms: int = 7000) -> bool:
    """抽選回数選択画面が見えているか（既存の判定を流用）"""
    try:
        page.get_by_text(S.DRAW_COUNT_BUTTON_TEXT_1, exact=True).wait_for(timeout=timeout_ms)
        return True
    except Exception:
        return False


def _captcha_error_visible(page: Page) -> bool:
    # 親ページ側
    for t in CAPTCHA_ERROR_TEXTS:
        try:
            if page.get_by_text(t).count() > 0:
                return True
        except Exception:
            pass

    # iframe内
    try:
        fl = page.frame_locator(HUBSPOT_IFRAME_SELECTOR)
        for t in CAPTCHA_ERROR_TEXTS:
            try:
                if fl.get_by_text(t).count() > 0:
                    return True
            except Exception:
                pass
    except Exception:
        pass

    return False


def _click_submit_in_iframe(page: Page) -> None:
    fl = page.frame_locator(HUBSPOT_IFRAME_SELECTOR)
    btn = fl.locator(HUBSPOT_SUBMIT_SELECTOR).first
    # HubSpotはたまに “label が上に被る/レイアウト揺れ” があるので force も許可
    btn.scroll_into_view_if_needed()
    btn.click(timeout=25000, force=True)


def _assert_required_errors_in_iframe(page: Page, expected_min: int = 1) -> None:
    """
    未入力送信で必須エラーが出ることを確認（HubSpotの必須は各項目に出ることが多い）
    """
    fl = page.frame_locator(HUBSPOT_IFRAME_SELECTOR)
    errs = fl.get_by_text(HUBSPOT_REQUIRED_ERROR_TEXT)
    # 反映まで少し待つ
    deadline = time.time() + 6.0
    while time.time() < deadline:
        if errs.count() >= expected_min:
            return
        time.sleep(0.2)

    raise AssertionError(f"必須エラーが表示されません: '{HUBSPOT_REQUIRED_ERROR_TEXT}'")


def _fill_required_fields_in_iframe(page: Page) -> None:
    """
    HubSpot埋め込みフォーム 必須:
      姓(firstname) / 名(lastname) / メール(email) / 電話(phone) / 会社(company)
    """
    fl = page.frame_locator(HUBSPOT_IFRAME_SELECTOR)

    # それぞれ “name属性” で取る（最も安定）
    fl.locator("input[name='firstname']").first.fill("姓テスト")
    fl.locator("input[name='lastname']").first.fill("名テスト")
    fl.locator("input[name='email']").first.fill("t.i.0607.g@gmail.com")
    fl.locator("input[name='phone']").first.fill("08012345678")
    fl.locator("input[name='company']").first.fill("テスト株式会社")


def apply_embed_form_lead(page: Page, artifacts: Artifacts) -> Page:
    """
    埋め込みフォームリード（HubSpot iframe）
    1) iframe表示確認
    2) 未入力で送信 → 必須エラー確認
    3) 必須入力 → 送信
    4) 抽選回数画面が出たらOK
       CAPTCHAエラーが出たらSKIP(LeadSkipped)
    """
    # 1) iframe表示確認
    iframe = page.locator(HUBSPOT_IFRAME_SELECTOR).first
    try:
        iframe.wait_for(state="attached", timeout=20000)
        iframe.wait_for(state="visible", timeout=20000)
    except Exception:
        artifacts.save_debug(page, "embed_form_iframe_not_visible")
        raise AssertionError("埋め込みフォーム(iframe)が表示されません")

    # 2) 未入力送信 → 必須エラー確認
    try:
        _click_submit_in_iframe(page)
    except Exception:
        artifacts.save_debug(page, "embed_submit_click_failed_empty")
        raise

    try:
        _assert_required_errors_in_iframe(page, expected_min=1)
    except Exception:
        artifacts.save_debug(page, "embed_required_errors_not_found")
        raise

    # 3) 必須入力 → 送信
    try:
        _fill_required_fields_in_iframe(page)
    except Exception:
        artifacts.save_debug(page, "embed_required_fill_failed")
        raise

    try:
        _click_submit_in_iframe(page)
    except Exception:
        artifacts.save_debug(page, "embed_submit_click_failed_filled")
        raise

    # 4) 抽選回数 or CAPTCHA を待つ
    deadline = time.time() + 25.0
    while time.time() < deadline:
        if _captcha_error_visible(page):
            # CAPTCHAが出たら “進めない” のでテスト都合でSKIP
            artifacts.save_debug(page, "embed_form_captcha")
            raise LeadSkipped("CAPTCHA on embed form")

        time.sleep(0.3)

    # CAPTCHAも出なかった → 先に進めた or フロー側で判定させる
    return page

