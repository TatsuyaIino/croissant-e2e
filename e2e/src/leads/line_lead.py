# e2e/src/leads/line_lead.py
import time
import os
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from src.core.artifacts import Artifacts
from src.selectors import line_selectors as L


def _is_line_domain(url: str) -> bool:
    u = url or ""
    return ("access.line.me" in u) or ("line.me" in u)


def _safe_click(locator, timeout_ms: int = 15000) -> None:
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

def _find_post_login_gacha_page(context, timeout_sec: float = 90.0) -> Page:
    """
    LINEログイン後に戻ってくるページを探す。

    優先順位:
      1) 一括：抽選回数指定画面（1〜10がある画面）
      2) 単発：抽選スタート画面（「抽選スタート」ボタンだけの画面）
    """
    end = time.time() + timeout_sec

    def _is_draw_count_screen(p: Page) -> bool:
        # 既存ロジック（マーカー文言がある）
        try:
            loc = p.get_by_text(L.DRAW_COUNT_MARK_TEXT_1, exact=True)
            if loc.count() > 0:
                loc.first.wait_for(timeout=800)
                return True
        except Exception:
            pass
        return False

    def _is_single_start_screen(p: Page) -> bool:
        try:
            start = p.get_by_text("抽選スタート", exact=True)
            if start.count() < 1:
                return False
            start.first.wait_for(timeout=800)
        except Exception:
            return False

        # 単発は 1〜10 が無い（「1」が見えるなら回数指定っぽいので除外）
        try:
            if p.get_by_text("1", exact=True).count() > 0:
                return False
        except Exception:
            pass
        return True

    def _is_paid_member_login_screen(p: Page) -> bool:
        try:
            if p.get_by_text("会員登録済みの方はこちら", exact=True).count() < 1:
                return False
            email = p.locator("input[name='email']")
            pw = p.locator("input[name='password']")
            btn = p.get_by_role("button", name="ログイン")
            if email.count() < 1 or pw.count() < 1 or btn.count() < 1:
                return False
            btn.first.wait_for(timeout=800)
            return True
        except Exception:
            return False

    def _is_purchase_confirm_screen(p: Page) -> bool:
        try:
            if p.get_by_text("購入内容の確認", exact=True).count() < 1:
                return False
            sel = p.locator("[data-scope='select'] select")
            buy_btn = p.get_by_role("button", name="ガチャを購入する")
            if sel.count() < 1 or buy_btn.count() < 1:
                return False
            buy_btn.first.wait_for(timeout=800)
            return True
        except Exception:
            return False

    while time.time() < end:
        pages = list(context.pages)

        # 1) 一括（回数指定）を優先
        for p in pages:
            try:
                if _is_line_domain(p.url):
                    continue
                if _is_draw_count_screen(p):
                    return p
            except Exception:
                pass

        # 2) 単発（抽選スタート）
        for p in pages:
            try:
                if _is_line_domain(p.url):
                    continue
                if _is_single_start_screen(p):
                    return p
            except Exception:
                pass

        # 3) 課金：購入内容の確認
        for p in pages:
            try:
                if _is_line_domain(p.url):
                    continue
                if _is_purchase_confirm_screen(p):
                    return p
            except Exception:
                pass

        # 4) 課金：会員ログイン
        for p in pages:
            try:
                if _is_line_domain(p.url):
                    continue
                if _is_paid_member_login_screen(p):
                    return p
            except Exception:
                pass

        time.sleep(0.4)

    raise PlaywrightTimeoutError(
        "gacha screen not found after LINE login (draw-count or single-start or purchase screens)"
    )

def _get_line_page_after_click(current_page: Page, before_pages: set, timeout_sec: float = 15.0) -> Page:
    ctx = current_page.context
    if _is_line_domain(current_page.url):
        return current_page

    end = time.time() + timeout_sec
    while time.time() < end:
        # 新規ページ
        for p in list(ctx.pages):
            if p not in before_pages and _is_line_domain(p.url):
                try:
                    p.bring_to_front()
                except Exception:
                    pass
                return p

        # 同一タブ遷移
        if _is_line_domain(current_page.url):
            return current_page

        # 既存のどこかがLINEにいる
        for p in list(ctx.pages):
            if _is_line_domain(p.url):
                try:
                    p.bring_to_front()
                except Exception:
                    pass
                return p

        time.sleep(0.2)

    return current_page

def _handle_line_login_if_needed(line_page, artifacts) -> bool:
    """
    LINEログイン画面が
    - (A) ログインボタンだけ
    - (B) メール/パスワード入力欄 + ログインボタン
    のどちらでも通す
    """

    # --- (B) メール/パスワード入力フォーム判定 ---
    # あなたが貼ってくれたHTMLだと name="tid", name="tpasswd"
    email_input = line_page.locator("input[name='tid']")
    pass_input  = line_page.locator("input[name='tpasswd']")

    try:
        # 入力欄が「見えている」ならフォーム型とみなす
        is_form = (email_input.count() > 0 and email_input.first.is_visible()) or (
            pass_input.count() > 0 and pass_input.first.is_visible()
        )
    except Exception:
        is_form = False

    if is_form:
        # 資格情報（.env推奨、無ければフォールバック）
        email = os.getenv("LINE_TEST_EMAIL")
        password = os.getenv("LINE_TEST_PASSWORD")

        if not email or not password:
            artifacts.save_debug(line_page, "line_env_missing")
            return False

        try:
            # 入力
            email_input.first.wait_for(state="visible", timeout=25000)
            pass_input.first.wait_for(state="visible", timeout=25000)

            email_input.first.fill(email, timeout=25000)
            pass_input.first.fill(password, timeout=25000)

            # submitボタン（disabled解除を待つ）
            submit_btn = line_page.locator("button[type='submit']:has-text('ログイン'), button:has-text('ログイン')")
            submit_btn.first.wait_for(state="visible", timeout=25000)

            # disabled が外れるまで少し待つ（UI実装によっては即外れない）
            line_page.wait_for_timeout(300)  # 見やすさ & 安定化
            try:
                line_page.wait_for_function(
                    "(el) => !el.disabled",
                    submit_btn.first,
                    timeout=25000,
                )
            except Exception:
                # disabled属性が無い実装もあるので、クリック自体は試す
                pass

            submit_btn.first.click(timeout=25000)
            return True

        except Exception:
            artifacts.save_debug(line_page, "line_form_login_failed")
            return False

    # --- (A) ボタンだけのログイン画面 ---
    login_btn = line_page.locator("button:has-text('ログイン'), input[type='submit'][value='ログイン']")
    if login_btn.count() < 1:
        # 既存のあなたのselector(L.LINE_LOGIN_BUTTON_SELECTOR)があるならそっちでもOK
        artifacts.save_debug(line_page, "line_login_button_not_found")
        return False

    try:
        login_btn.first.wait_for(state="visible", timeout=25000)
        login_btn.first.click(timeout=25000)
        return True
    except Exception:
        artifacts.save_debug(line_page, "line_login_click_failed")
        return False

def _click_line_login_trigger(modal: Page, artifacts: Artifacts, page: Page) -> bool:
    """
    あなたのDOMは button ではなく div/img なので、
    クリック対象を段階的に変えて押し切る。
    """
    img = modal.locator(L.LINE_LOGIN_IMG_SELECTOR)
    txt = modal.locator(L.LINE_LOGIN_TEXT_SELECTOR)

    # クリック候補を優先順で試す
    candidates = []

    if img.count() > 0:
        # img自体
        candidates.append(("img", img.first))
        # imgの親
        candidates.append(("img_parent", img.first.locator("xpath=..")))
        # imgの親の親（MuiBox-rootがクリック受付することが多い）
        candidates.append(("img_grandparent", img.first.locator("xpath=../..")))

    if txt.count() > 0:
        candidates.append(("text", txt.first))
        candidates.append(("text_parent", txt.first.locator("xpath=..")))
        candidates.append(("text_grandparent", txt.first.locator("xpath=../..")))

    if not candidates:
        artifacts.save_debug(page, "line_trigger_not_found")
        return False

    for name, loc in candidates:
        try:
            _safe_click(loc, timeout_ms=12000)
            time.sleep(0.4)
            return True
        except Exception:
            # 次の候補へ
            continue

    artifacts.save_debug(page, "line_trigger_click_failed")
    return False


def apply_line_lead(page: Page, artifacts: Artifacts) -> Page:
    """
    ① LINE連携モーダル（文言+LINEでログイン導線）
    ② LINEでログイン押下 → LINEログイン画面（ログインボタン確認）
    ③ ログイン押下 → 抽選回数画面へ戻る
    """
    # ① モーダル待ち
    modal = page.locator(L.LINE_MODAL_SELECTOR)
    try:
        modal.first.wait_for(timeout=25000)
    except PlaywrightTimeoutError:
        artifacts.save_debug(page, "line_modal_missing")
        return page

    # 文言確認
    try:
        modal.get_by_text(L.LINE_MODAL_TEXT).first.wait_for(timeout=12000)
    except PlaywrightTimeoutError:
        artifacts.save_debug(page, "line_modal_text_missing")
        return page

    before_pages = set(page.context.pages)

    # ② 「LINEでログイン」を押す（buttonでない前提で押し切る）
    ok = _click_line_login_trigger(modal, artifacts, page)
    if not ok:
        return page

    # LINEページ取得
    line_page = _get_line_page_after_click(page, before_pages, timeout_sec=20.0)

    try:
        line_page.wait_for_load_state("domcontentloaded", timeout=30000)
    except Exception:
        pass

    # LINEログイン画面のログインボタン
    login_btn = line_page.locator(L.LINE_LOGIN_BUTTON_SELECTOR)
    if login_btn.count() < 1:
        artifacts.save_debug(line_page, "line_login_button_not_found")
        artifacts.save_debug(page, "line_login_button_not_found_main")
        return page

    # ③ ログイン押下
    ok = _handle_line_login_if_needed(line_page, artifacts)
    if not ok:
        artifacts.save_debug(line_page, "line_login_step_failed")
        return page

    # 抽選スタート画面へ戻る
    try:
        draw_page = _find_post_login_gacha_page(page.context, timeout_sec=90.0)

        try:
            draw_page.bring_to_front()
        except Exception:
            pass
        return draw_page
    except PlaywrightTimeoutError:
        artifacts.save_debug(page, "line_return_failed_main")
        try:
            artifacts.save_debug(line_page, "line_return_failed_line")
        except Exception:
            pass
        return page
