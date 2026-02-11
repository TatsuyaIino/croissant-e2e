# src/leads/sns_lead.py
from __future__ import annotations

import time
from playwright.sync_api import Page

from src.core.artifacts import Artifacts
from src.selectors import sns_selectors as SS


def _safe_click(page: Page, locator, timeout_ms: int = 20000) -> None:
    locator.first.wait_for(state="attached", timeout=timeout_ms)
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


def _is_cta_enabled(modal, cta_selector: str) -> bool:
    cta = modal.locator(cta_selector).first
    if cta.count() < 1:
        return False

    aria_disabled = (cta.get_attribute("aria-disabled") or "").strip().lower()
    if aria_disabled == "true":
        return False

    cls = (cta.get_attribute("class") or "")
    # SS.SNS_CTA_DISABLED_CLASS が selectors にあれば使う（なければ無視される）
    disabled_cls = getattr(SS, "SNS_CTA_DISABLED_CLASS", "")
    if disabled_cls and disabled_cls in cls:
        return False

    # pointer-events: none も無効扱い
    try:
        pe = cta.evaluate("el => window.getComputedStyle(el).pointerEvents")
        if isinstance(pe, str) and pe.strip() == "none":
            return False
    except Exception:
        pass

    return True


def _open_link_in_new_tab(page: Page, a, artifacts: Artifacts, tag: str) -> None:
    ctx = page.context
    href = (a.get_attribute("href") or "").strip()
    if not href:
        artifacts.save_debug(page, f"{tag}_href_empty")
        raise AssertionError("SNSリンクhrefが空です")

    with ctx.expect_page(timeout=20000) as pinfo:
        _safe_click(page, a, timeout_ms=20000)

    newp = pinfo.value
    try:
        newp.wait_for_load_state("domcontentloaded", timeout=30000)
    except Exception:
        pass
    try:
        newp.close()
    except Exception:
        pass


def _wait_until_checks_ready(modal, expected_green: int, timeout_sec: float = 25.0) -> None:
    """
    最終的に
      - gray=0
      - green=expected_green
      - CTA enabled
    になるまで待つ
    """
    end = time.time() + timeout_sec
    while time.time() < end:
        gray = modal.locator(SS.SNS_CHECK_GRAY_SELECTOR).count()
        green = modal.locator(SS.SNS_CHECK_GREEN_SELECTOR).count()
        enabled = _is_cta_enabled(modal, SS.SNS_CTA_SELECTOR)
        if gray == 0 and green == expected_green and enabled:
            return
        time.sleep(0.3)

    # timeout
    gray = modal.locator(SS.SNS_CHECK_GRAY_SELECTOR).count()
    green = modal.locator(SS.SNS_CHECK_GREEN_SELECTOR).count()
    enabled = _is_cta_enabled(modal, SS.SNS_CTA_SELECTOR)
    raise AssertionError(
        f"SNS: チェック状態が整いません (expected_green={expected_green}, gray={gray}, green={green}, cta_enabled={enabled})"
    )


def apply_sns_lead(page: Page, artifacts: Artifacts) -> Page:
    """
    SNSリード（完成系）

    ✅ アカウント数：3件以上OK
    ✅ 緑のアカウントも含め、全件 新規タブ遷移できることを確認
    ✅ 初期状態が2パターンあり得る
        A) 最初から全部緑（gray=0） → CTA押下可能が必須
        B) グレーが残る（gray>0）     → CTA押下不可が必須
           その後、全リンク遷移→全緑→CTA押下可能 になること
    """

    # モーダル待ち
    modal = page.locator(SS.SNS_MODAL_SELECTOR).filter(has_text=SS.SNS_MODAL_TEXT)
    modal.first.wait_for(state="visible", timeout=45000)

    # アカウントリンク（3件以上OK）
    links = modal.locator(SS.SNS_ACCOUNT_LINKS_SELECTOR)
    n = links.count()
    if n < 3:
        artifacts.save_debug(page, "sns_links_less_than_3")
        raise AssertionError(f"SNSアカウントは3件以上必須です (actual={n})")

    # CTA存在
    cta = modal.locator(SS.SNS_CTA_SELECTOR)
    if cta.count() < 1:
        artifacts.save_debug(page, "sns_cta_missing")
        raise AssertionError("SNSモーダル内の「ガチャを回す」CTAが見つかりません")

    # 初期状態チェック
    gray0 = modal.locator(SS.SNS_CHECK_GRAY_SELECTOR).count()
    green0 = modal.locator(SS.SNS_CHECK_GREEN_SELECTOR).count()
    enabled0 = _is_cta_enabled(modal, SS.SNS_CTA_SELECTOR)

    # 「グレーがあるならCTA押下不可」は必須
    if gray0 > 0 and enabled0:
        artifacts.save_debug(page, "sns_gray_exists_but_cta_enabled")
        raise AssertionError(f"SNS: グレーが残っているのにCTAが有効です (gray={gray0}, green={green0})")

    # 「グレー0ならCTA押下可」は必須（最初から全緑パターンを許容）
    if gray0 == 0 and not enabled0:
        artifacts.save_debug(page, "sns_all_green_but_cta_disabled")
        raise AssertionError(f"SNS: グレー0なのにCTAが無効です (green={green0})")

    # ✅ 緑でもグレーでも「全リンク」を新規タブで踏む（要件）
    for i in range(n):
        _open_link_in_new_tab(page, links.nth(i), artifacts, tag=f"sns_link_{i+1}")
        time.sleep(0.2)

    # グレーがあったケースは「最終的に全部緑＆CTA有効」へ変化するのが必須
    # 最初から全部緑のケースは「全部緑のまま＆CTA有効」を必須
    expected_green = n

    if gray0 > 0:
        try:
            _wait_until_checks_ready(modal, expected_green=expected_green, timeout_sec=25.0)
        except Exception:
            artifacts.save_debug(page, "sns_after_visits_not_ready")
            raise
    else:
        # 最初から全緑の場合：状態が崩れていない＆CTA有効のままを確認
        gray1 = modal.locator(SS.SNS_CHECK_GRAY_SELECTOR).count()
        green1 = modal.locator(SS.SNS_CHECK_GREEN_SELECTOR).count()
        enabled1 = _is_cta_enabled(modal, SS.SNS_CTA_SELECTOR)
        if gray1 != 0 or green1 != expected_green or not enabled1:
            artifacts.save_debug(page, "sns_all_green_but_changed_after_visits")
            raise AssertionError(
                f"SNS: 全リンク遷移後に状態が崩れました (expected_green={expected_green}, gray={gray1}, green={green1}, cta_enabled={enabled1})"
            )

    # CTA押下 → 抽選回数画面へ
    _safe_click(page, cta, timeout_ms=30000)

    # 遷移が始まる/DOMが切り替わるのを軽く待つ（判定はgacha_flow側で）
    try:
        page.wait_for_load_state("domcontentloaded", timeout=20000)
    except Exception:
        pass

    return page
