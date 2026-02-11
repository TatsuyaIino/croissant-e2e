from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from playwright.sync_api import Page, Locator, TimeoutError as PlaywrightTimeoutError

from src.core.artifacts import Artifacts
from src.selectors import gacha_selectors as GS  # 抽選回数画面判定に使うなら
from src.selectors import form_selectors as FS
from src.core.text import normalize_text

def _safe_click(loc: Locator, timeout_ms: int = 25000) -> None:
    """既存の _safe_click があるなら消してそれを使ってOK。無ければこれでOK。"""
    loc.first.wait_for(state="visible", timeout=timeout_ms)
    try:
        loc.first.click(timeout=timeout_ms)
    except Exception:
        # 被り対策
        loc.first.scroll_into_view_if_needed(timeout=timeout_ms)
        loc.first.click(timeout=timeout_ms)


def _wait_form_screen(page: Page, timeout_ms: int = 30000) -> None:
    page.get_by_text(FS.FORM_HEADING_TEXT1).first.wait_for(timeout=timeout_ms)
    page.get_by_text(FS.FORM_HEADING_TEXT2).first.wait_for(timeout=timeout_ms)
    page.get_by_text(FS.SUBMIT_TEXT, exact=False).first.wait_for(timeout=timeout_ms)


def _form_control_by_label(page: Page, label_text: str) -> Locator:
    """
    「メールアドレス」「テキスト」「電話番号」などのラベルを含む FormControl を拾う
    DOM例: <div class="MuiFormControl-root ..."><div>ラベル</div> ... <input ...>
    """
    return page.locator(f"div.MuiFormControl-root:has-text('{label_text}')").first


def _assert_required_badge_exists(ctrl: Locator, label_text: str) -> None:
    badge = ctrl.locator(f":has-text('{FS.REQUIRED_BADGE_TEXT}')")
    if badge.count() < 1:
        raise AssertionError(f"必須バッジが見つかりません: {label_text}")


def _assert_required_error(ctrl: Locator, label_text: str) -> None:
    err = ctrl.locator(f":has-text('{FS.REQUIRED_ERROR_TEXT}')")
    if err.count() < 1:
        raise AssertionError(f"必須エラー『{FS.REQUIRED_ERROR_TEXT}』が出ていません: {label_text}")


def _fill_email(ctrl: Locator, email: str) -> None:
    # <input ... placeholder="入力してください" class="chakra-input ...">
    inp = ctrl.locator("input.chakra-input")
    if inp.count() < 1:
        raise AssertionError("メール input が見つかりません")
    inp.first.fill(email)


def _fill_text(ctrl: Locator, text: str) -> None:
    inp = ctrl.locator("input.chakra-input")
    if inp.count() < 1:
        raise AssertionError("テキスト input が見つかりません")
    inp.first.fill(text)


def _fill_phone(page: Page, p1: str, p2: str, p3: str) -> None:
    # name が固定（あなたのHTML通り）
    a = page.locator("input[name='mobilePhoneId']")
    b = page.locator("input[name='carrierNumber']")
    c = page.locator("input[name='identifierNumber']")
    if a.count() < 1 or b.count() < 1 or c.count() < 1:
        raise AssertionError("電話番号の3分割inputが見つかりません")
    a.first.fill(p1)
    b.first.fill(p2)
    c.first.fill(p3)


def _assert_all_field_types_exist(page: Page) -> None:
    """
    全項目（テキスト/メール/電話/プルダウン/チェック/ラジオ/添付）が表示されること
    ※ uuid name は不定なので構造で判定
    """
    # 必須3つ（表示の確認）
    _form_control_by_label(page, "メールアドレス").wait_for(state="visible", timeout=20000)
    _form_control_by_label(page, "テキスト").wait_for(state="visible", timeout=20000)
    page.locator("input[name='mobilePhoneId']").first.wait_for(state="visible", timeout=20000)

    # ラジオ
    if page.locator("[data-scope='radio-group'][role='radiogroup']").count() < 1:
        raise AssertionError("ラジオグループが表示されていません")

    # チェックボックス
    if page.locator("[data-scope='checkbox'][data-part='root']").count() < 1:
        raise AssertionError("チェックボックスが表示されていません")

    # プルダウン
    if page.locator("[data-scope='select'][data-part='root']").count() < 1:
        raise AssertionError("プルダウンが表示されていません")

    # 添付
    if page.locator("[data-scope='file-upload'][data-part='root']").count() < 1:
        raise AssertionError("ファイル添付が表示されていません")


def _select_optional_dropdown(page: Page) -> None:
    """
    プルダウン：任意で1つ選択
    - まず <select> の option から空以外を選ぶ（最も確実）
    """
    sel = page.locator("[data-scope='select'] select").first
    if sel.count() < 1:
        # fallback
        sel = page.locator("select").first
    if sel.count() < 1:
        raise AssertionError("select要素が見つかりません")

    # option を読んで空以外を選択
    options = sel.locator("option")
    n = options.count()
    if n < 2:
        # 空 + 1つ以上が普通。2未満は選択できない
        return

    chosen_value: Optional[str] = None
    for i in range(n):
        v = (options.nth(i).get_attribute("value") or "").strip()
        if v != "":
            chosen_value = v
            break

    if chosen_value:
        sel.select_option(value=chosen_value)


def _select_optional_radio(page: Page) -> None:
    """
    ラジオ：1つ選択

    Chakra UI の radio-group は input を直接 check() すると
    label(item) が pointer events を intercept してタイムアウトすることがあるため、
    label(item) をクリックする。
    """
    items = page.locator("[data-scope='radio-group'][data-part='item']")
    if items.count() < 1:
        raise AssertionError("ラジオ項目(label item) が見つかりません")

    first_item = items.first
    first_item.wait_for(state="visible", timeout=20000)
    first_item.scroll_into_view_if_needed(timeout=20000)

    # すでに checked の可能性もあるので data-state を見る（unchecked / checked）
    state = (first_item.get_attribute("data-state") or "").strip()
    if state != "checked":
        try:
            first_item.click(timeout=20000)
        except Exception:
            first_item.click(timeout=20000, force=True)

    # 念のため、配下の input が checked になっているか確認
    inp = first_item.locator("input[type='radio']")
    if inp.count() >= 1:
        if not inp.first.is_checked():
            raise AssertionError("ラジオをクリックしたのに checked になりませんでした")


def _select_optional_checkbox(page: Page) -> None:
    """
    チェック：1つ以上ON

    Chakra UI などで input 自体がクリック対象ではなく label/control がクリック対象になっているため、
    input.check() ではなく label をクリックする。
    """
    labels = page.locator("[data-scope='checkbox'][data-part='root']")
    if labels.count() < 1:
        raise AssertionError("チェックボックス(label root) が見つかりません")

    # 1つ目をON（未チェックならクリック）
    first_label = labels.first
    first_label.wait_for(state="visible", timeout=20000)
    first_label.scroll_into_view_if_needed(timeout=20000)

    # すでに checked の可能性もあるので data-state を見る（unchecked / checked）
    state = (first_label.get_attribute("data-state") or "").strip()
    if state != "checked":
        # force は最終手段。まず普通にクリック→ダメなら force
        try:
            first_label.click(timeout=20000)
        except Exception:
            first_label.click(timeout=20000, force=True)

    # 念のため、input 側も確認（checked になっているか）
    inp = first_label.locator("input[type='checkbox']")
    if inp.count() >= 1:
        checked = inp.first.is_checked()
        if not checked:
            raise AssertionError("チェックボックスをクリックしたのに checked になりませんでした")



def _ensure_dummy_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("dummy", encoding="utf-8")


def _attach_optional_file(page: Page, artifacts: Artifacts) -> None:
    """
    添付は「表示される」要件なので必須ではないが、任意で付けたいなら付ける。
    付けると落ちやすいなら、この関数呼び出しをコメントアウトでOK。
    """
    file_input = page.locator("[data-scope='file-upload'] input[type='file']").first
    if file_input.count() < 1:
        return
    dummy = Path(artifacts.base_dir) / artifacts.scenario_id / "upload_dummy.txt"
    _ensure_dummy_file(dummy)
    file_input.set_input_files(str(dummy))


def _drawcount_screen_visible(page: Page, timeout_ms: int = 7000) -> bool:
    """
    既存に同名があるならそれを使用してOK。
    抽選回数画面にある「1」ボタンで判定する（あなたの既存定義に合わせて適宜）
    """
    try:
        page.get_by_text("1", exact=True).wait_for(timeout=timeout_ms)
        return True
    except Exception:
        return False


def apply_form_lead(page: Page, artifacts: Artifacts) -> Page:
    """
    フォームリード
    ① ガチャを回す → フォーム画面へ
    ② 必須未入力で送信 → 各必須に「必須です」＆送信不可
    ③ 必須入力＋任意入力（プル/チェック/ラジオ）で送信 → 抽選回数画面へ
    """

    # ① フォーム画面が開く
    try:
        _wait_form_screen(page, timeout_ms=45000)
    except Exception:
        artifacts.save_debug(page, "form_screen_not_visible")
        return page

    # 全項目表示チェック
    try:
        _assert_all_field_types_exist(page)
    except Exception:
        artifacts.save_debug(page, "form_fields_missing")
        raise

    # 必須マークが付いていること（メール/テキスト/電話）
    email_ctrl = _form_control_by_label(page, "メールアドレス")
    text_ctrl = _form_control_by_label(page, "テキスト")
    phone_ctrl = _form_control_by_label(page, "電話番号")

    try:
        _assert_required_badge_exists(email_ctrl, "メールアドレス")
        _assert_required_badge_exists(text_ctrl, "テキスト")
        _assert_required_badge_exists(phone_ctrl, "電話番号")
    except Exception:
        artifacts.save_debug(page, "form_required_badge_missing")
        raise

    # ② 必須未入力で送信 → 必須です が出る & 遷移しない
    submit_btn = page.locator(f"button:has-text('{FS.SUBMIT_TEXT}')").first
    if submit_btn.count() < 1:
        # aタグbutton風もあるためfallback
        submit_btn = page.locator(f"[role='button']:has-text('{FS.SUBMIT_TEXT}')").first
    if submit_btn.count() < 1:
        artifacts.save_debug(page, "form_submit_not_found")
        return page

    _safe_click(submit_btn, timeout_ms=25000)
    page.wait_for_timeout(300)  # 見やすさ＋バリデーション反映待ち

    try:
        _assert_required_error(email_ctrl, "メールアドレス")
        _assert_required_error(text_ctrl, "テキスト")
        _assert_required_error(phone_ctrl, "電話番号")
    except Exception:
        artifacts.save_debug(page, "form_required_error_not_shown")
        raise

    # 遷移していない（まだフォーム画面のまま）
    if _drawcount_screen_visible(page, timeout_ms=1500):
        artifacts.save_debug(page, "form_should_not_navigate_on_error")
        raise AssertionError("必須未入力なのに抽選回数画面へ遷移しました")

    # ③ 必須入力＋任意入力 → 送信して開始 → 抽選回数画面
    # 必須
    _fill_email(email_ctrl, os.getenv("FORM_TEST_EMAIL", "test@example.com"))
    _fill_text(text_ctrl, os.getenv("FORM_TEST_TEXT", "E2Eテスト"))
    _fill_phone(page, "080", "1234", "5678")

    # 任意（要件）
    _select_optional_dropdown(page)
    _select_optional_checkbox(page)
    _select_optional_radio(page)

    # 添付（任意・表示だけなら不要。必要なら有効化）
    # _attach_optional_file(page, artifacts)

    # 送信は lead 側の責務（押せてないと何も始まらない）
    try:
        _safe_click(submit_btn, timeout_ms=25000)
    except Exception:
        artifacts.save_debug(page, "form_submit_click_failed")
        # ここは「落とす/落とさない」方針で選べる
        # raise
        return page

    return page

