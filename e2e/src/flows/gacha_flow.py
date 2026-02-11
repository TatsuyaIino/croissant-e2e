from __future__ import annotations

import os
import re
import time
import uuid
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from typing import List, Dict, Any
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from src.core.types import Scenario
from src.core.artifacts import Artifacts
from src.core.text import normalize_text
from src.core.waits import wait_until_src_changes
from src.selectors import gacha_selectors as S
from src.selectors import line_selectors as L
from src.selectors import sns_selectors as N
from src.selectors import form_selectors as F
from src.leads.lead_router import apply_lead
from playwright.sync_api import Page, Locator, TimeoutError as PlaywrightTimeoutError
from src.core.exceptions import LeadSkipped


ALLOWED_RESULT_NAMES = {"結果A", "結果B", "結果C"}

def _maybe_randomize_userid(url: str, lead_params: dict | None = None) -> str:
    params = lead_params or {}
    reuse_policy = (params.get("reuse_policy") or "either").strip()

    # must_reusable だけは同一ユーザーで再利用確認したいので固定のまま
    if reuse_policy == "must_reusable":
        return url

    p = urlparse(url)
    q = parse_qs(p.query)

    q["userid"] = [f"e2e_{uuid.uuid4().hex}"]

    return urlunparse(
        (p.scheme, p.netloc, p.path, p.params, urlencode(q, doseq=True), p.fragment)
    )

def _is_paid_confirm_screen(page: Page) -> bool:
    try:
        return page.get_by_text(S.PAID_CONFIRM_TITLE_TEXT, exact=False).count() > 0
    except Exception:
        return False

def _is_paid_member_login_screen(page: Page) -> bool:
    try:
        return page.get_by_text(S.PAID_MEMBER_LOGIN_TITLE_TEXT, exact=False).count() > 0
    except Exception:
        return False

def _paid_member_login_if_needed(page: Page, artifacts: Artifacts) -> bool:
    """
    課金パターンB：クロワッサン未認証 → 会員ログインしてAへ
    """
    if not _is_paid_member_login_screen(page):
        return True

    email = os.getenv("CROISSANT_MEMBER_EMAIL", "t.i.0607.g@gmail.com")
    password = os.getenv("CROISSANT_MEMBER_PASSWORD", "tatsuya0607")

    try:
        email_input = page.locator("input[name='email']")
        pass_input  = page.locator("input[name='password']")
        login_btn   = page.locator("button[type='submit']:has-text('ログイン'), button:has-text('ログイン')")

        email_input.first.wait_for(state="visible", timeout=25000)
        pass_input.first.wait_for(state="visible", timeout=25000)

        email_input.first.fill(email, timeout=25000)
        pass_input.first.fill(password, timeout=25000)

        login_btn.first.click(timeout=25000)

        page.get_by_text(S.PAID_CONFIRM_TITLE_TEXT, exact=False).wait_for(timeout=45000)
        return True
    except Exception:
        artifacts.save_debug(page, "paid_member_login_failed")
        return False

def _paid_purchase_and_restrict_check(page: Page, artifacts: Artifacts, purchase_draw_count: int) -> bool:
    """
    課金パターンA：購入内容の確認 → 5回選択 → 同意 → 購入 → 抽選回数画面で5以外disabled確認
    """
    try:
        page.get_by_text(S.PAID_CONFIRM_TITLE_TEXT, exact=False).wait_for(timeout=45000)
    except Exception:
        artifacts.save_debug(page, "paid_confirm_not_visible")
        return False

    # 金額の表示確認（存在チェック）
    try:
        if page.get_by_text("購入価格", exact=False).count() < 1 or page.get_by_text("500円", exact=False).count() < 1:
            artifacts.save_debug(page, "paid_price_missing_500")
            return False
        if page.get_by_text("消費税", exact=False).count() < 1 or page.get_by_text("50円", exact=False).count() < 1:
            artifacts.save_debug(page, "paid_tax_missing_50")
            return False
        if page.get_by_text("支払い金額", exact=False).count() < 1 or page.get_by_text("550円", exact=False).count() < 1:
            artifacts.save_debug(page, "paid_total_missing_550")
            return False
    except Exception:
        artifacts.save_debug(page, "paid_price_check_failed")
        return False

    # 回数選択（hidden select を select_option）
    try:
        hidden_select = page.locator("[data-scope='select'] select")
        hidden_select.first.wait_for(state="attached", timeout=25000)
        hidden_select.first.select_option(value=str(purchase_draw_count), timeout=25000)
    except Exception:
        artifacts.save_debug(page, "paid_select_drawcount_failed")
        return False

    # 同意チェックボックス
    try:
        chk = page.locator("[data-scope='checkbox'][data-part='control']")
        if chk.count() > 0:
            chk.first.click(timeout=10000, force=True)
    except Exception:
        artifacts.save_debug(page, "paid_checkbox_click_failed")
        return False

    # 購入ボタン
    buy_btn = page.locator("button:has-text('ガチャを購入する')")
    
    try:
        buy_btn.first.wait_for(state="visible", timeout=25000)
    except Exception:
        artifacts.save_debug(page, "paid_buy_button_missing")
        return False

    # disabled解除を待って押す（取れない場合もあるのでクリックは試す）
    try:
        page.wait_for_function("(el) => !el.disabled", buy_btn.first, timeout=25000)
    except Exception:
        pass

    try:
        buy_btn.first.click(timeout=25000)
    except Exception:
        try:
            buy_btn.first.click(timeout=25000, force=True)
        except Exception:
            artifacts.save_debug(page, "paid_buy_button_click_failed")
            return False

    # 抽選回数指定画面（5だけ押せる）
    try:
        page.get_by_text(S.DRAW_START_TEXT, exact=True).wait_for(timeout=45000)
        page.get_by_text(str(purchase_draw_count), exact=True).wait_for(timeout=45000)
    except Exception:
        artifacts.save_debug(page, "paid_after_buy_no_drawcount")
        return False

    # 指定回数以外がdisabled
    try:
        for n in range(1, 11):
            btn = page.locator(f"button[value='{n}']")
            if btn.count() < 1:
                continue
            if n == purchase_draw_count:
                # ここは押下可能想定
                if btn.first.get_attribute("disabled") is not None:
                    artifacts.save_debug(page, "paid_target_btn_disabled")
                    return False
            else:
                # disabled想定
                if btn.first.get_attribute("disabled") is None:
                    artifacts.save_debug(page, f"paid_other_btn_not_disabled_{n}")
                    return False
    except Exception:
        artifacts.save_debug(page, "paid_disabled_check_failed")
        return False

    return True

def _wait_paid_screen_ready(page: Page, timeout_sec: float = 30.0) -> str:
    """
    /order に入った直後など、読み込み中でDOMがまだ無い時間を吸収する。
    戻り値: "confirm" | "login" | "timeout"
    """
    end = time.time() + timeout_sec

    while time.time() < end:
        # どっちかの画面が出たら終了
        if _is_paid_confirm_screen(page):
            return "confirm"
        if _is_paid_member_login_screen(page):
            return "login"

        # 読み込みが終わるのを少し待つ（SPAなので短いポーリングが安定）
        try:
            page.wait_for_load_state("domcontentloaded", timeout=800)
        except Exception:
            pass
        page.wait_for_timeout(250)

    return "timeout"

def _maybe_handle_paid_gacha_after_lead(page: Page, artifacts: Artifacts, sc: Scenario) -> Page:
    lead_params = sc.lead_params if isinstance(sc.lead_params, dict) else {}
    if not bool(lead_params.get("paid_gacha", False)):
        return page

    purchase_draw_count = int(lead_params.get("purchase_draw_count", sc.draw_count or 5) or 5)

    # ★ ここが最重要：読み込み中を吸収してから判定に入る
    st = _wait_paid_screen_ready(page, timeout_sec=35.0)
    if st == "timeout":
        artifacts.save_debug(page, "paid_loading_timeout")
        return page  # ここで落とさず、後段で拾えるようにする（崩さない方針）
    
    # B: 会員ログイン画面ならログイン
    if _is_paid_member_login_screen(page):
        if not _paid_member_login_if_needed(page, artifacts):
            return page

    # A: 購入内容確認なら購入処理
    if _is_paid_confirm_screen(page):
        ok = _paid_purchase_and_restrict_check(page, artifacts, purchase_draw_count=purchase_draw_count)
        if not ok:
            return page

    # ここまで来たら「抽選回数指定画面」にいる想定（以降は既存フローのチェックへ）
    return page

def pick_result_name(text: str) -> str:
    m = re.search(r"(結果[ABC])", text or "")
    return m.group(1) if m else ""


def _is_ci() -> bool:
    return (os.getenv("CI", "") or "").lower() == "true"


def _demo_wait(sec_default: float = 0.8) -> None:
    """ローカル目視用：CIでは待たない"""
    if _is_ci():
        return
    sec = float(os.getenv("PW_DEMO_WAIT", str(sec_default)) or str(sec_default))
    if sec > 0:
        time.sleep(sec)

# ---------------- ① 抽選回数画面：表示チェック（クリックしない） ----------------
def _assert_draw_count_screen(page: Page, artifacts: Artifacts, sc: Scenario) -> bool:
    """
    ①「ガチャを回す」押下後：
      - 抽選回数指定画面が開く
      - (ケースごとに) 表示されるべき回数が表示されている
      - 「スタート」ボタンが表示される

    対応方針：
      - デフォルト：sc.draw_count が表示されていること（＝そのケースが進める最低条件）
      - 任意で lead_params に draw_counts_expected を入れれば、その一覧が表示されていることをチェック
        例）lead_params: { draw_counts_expected: [1,3,10] }
      - さらに strict にしたい場合：draw_counts_strict=True で、他の数字が出ていないこともチェック
    """
    lead_params = sc.lead_params if isinstance(sc.lead_params, dict) else {}
    expected: List[int] | None = lead_params.get("draw_counts_expected")
    strict: bool = bool(lead_params.get("draw_counts_strict", False))

    # 抽選回数画面の目印：「スタート」が見える
    try:
        page.get_by_text(S.DRAW_START_TEXT, exact=True).wait_for(timeout=20000)
    except PlaywrightTimeoutError:
        artifacts.save_debug(page, "draw_count_screen_not_opened")
        return False

    # 押下したい回数は必ず表示されている（最低条件）
    if sc.draw_count is None:
        artifacts.save_debug(page, "draw_count_missing_in_scenario")
        return False
    must_n = sc.draw_count
    must_btn = page.get_by_text(str(must_n), exact=True)
    if must_btn.count() < 1:
        artifacts.save_debug(page, f"draw_count_required_missing_{must_n}")
        return False

    # expected があれば、その数字が表示されていることをチェック（クリックしない）
    if expected is not None:
        for n in expected:
            loc = page.get_by_text(str(n), exact=True)
            if loc.count() < 1:
                artifacts.save_debug(page, f"draw_count_expected_missing_{n}")
                return False

        if strict:
            # 画面にある “数字ボタン” をざっくり集計して expected と一致するかを確認
            # ※ UIが数字以外も含む場合があるので、あくまで保守的に “1〜10のみ”を抽出
            present = set()
            for n in range(1, 11):
                if page.get_by_text(str(n), exact=True).count() > 0:
                    present.add(n)
            if present != set(expected):
                artifacts.save_debug(page, "draw_count_present_set_mismatch")
                return False

    # スタートが押下可能であること
    start_btn = page.get_by_text(S.DRAW_START_TEXT, exact=True)
    if start_btn.count() < 1:
        artifacts.save_debug(page, "start_button_missing")
        return False
    try:
        if not start_btn.first.is_enabled():
            artifacts.save_debug(page, "start_button_disabled")
            return False
    except Exception:
        pass

    return True


# ---------------- ② カードめくり画面のUIチェック（divでもOK） ----------------
def _assert_card_screen_ui(page: Page, artifacts: Artifacts, card_img) -> bool:
    """
    ②スタート後：
      - カード形式の結果めくり画面が表示
      - 表示要素：
         * 結果名（結果A/B/C）※カードimg alt から抽出
         * 結果画像（src）
         * 「タップで次へ」
         * 「スキップ」（div でも OK）
    """
    src = (card_img.get_attribute("src") or "").strip()
    if not src:
        artifacts.save_debug(page, "card_image_src_missing")
        return False

    alt = normalize_text(card_img.get_attribute("alt") or "")
    name = pick_result_name(alt)
    if name not in ALLOWED_RESULT_NAMES:
        artifacts.save_debug(page, "card_result_name_missing_or_invalid")
        return False

    # タップで次へ（text / div / button どれでも）
    tap = page.locator(S.CARD_TAP_NEXT_SELECTOR)
    if tap.count() < 1 and page.get_by_text(S.CARD_TAP_NEXT_TEXT).count() < 1:
        artifacts.save_debug(page, "card_tap_next_missing")
        return False

    # スキップ（text / div / button どれでも）
    skip = page.locator(S.CARD_SKIP_SELECTOR)
    if skip.count() < 1 and page.get_by_text(S.CARD_SKIP_TEXT).count() < 1:
        artifacts.save_debug(page, "card_skip_missing")
        return False

    return True


def _extract_top_thumbs(page: Page) -> List[str]:
    thumbs = page.locator(S.TOP_THUMB_SELECTOR)
    return [(thumbs.nth(i).get_attribute("src") or "").strip() for i in range(thumbs.count())]

def _pick_detail_name(it, draw_count: int) -> str:
    """
    結果詳細ブロック1件から「結果名」を安全に取得する

    - draw_count == 1:
        <div class="css-1cmdo0c">結果A</div>
    - draw_count >= 2:
        <div class="css-1r7lvp9">結果B</div>
        ※ 同classで「今すぐつかう」もあるため除外が必要
    """

    # --- 1回抽選用（最優先・安定） ---
    if draw_count == 1:
        loc = it.locator("div.css-1cmdo0c")
        if loc.count() > 0:
            txt = (loc.first.text_content() or "").strip()
            if txt.startswith("結果"):
                return txt

    # --- 2回以上用（「今すぐつかう」を除外） ---
    locs = it.locator("div.css-1r7lvp9")
    for i in range(locs.count()):
        txt = (locs.nth(i).text_content() or "").strip()
        if txt.startswith("結果"):
            return txt

    # --- フォールバック（DOM変更耐性） ---
    any_divs = it.locator("div")
    for i in range(any_divs.count()):
        txt = (any_divs.nth(i).text_content() or "").strip()
        if txt.startswith("結果"):
            return txt

    return ""

# gacha_flow.py 内（ALLOWED_RESULT_NAMES を使う前提）

RESULT_NAME_RE = re.compile(r"^結果[Ａ-ＺA-Z0-9]+$")

def _pick_detail_name(it: Locator, draw_count: int) -> str:
    """
    結果詳細ブロックから結果名（例: 結果A/結果B/結果C）を取得する。
    1回抽選と複数回抽選でDOMが違うため、複数候補 + 階層フォールバックで吸収する。

    - 1回抽選で見えた例: <div class="css-1cmdo0c">結果A</div>
    - 2回以上で見えた例: <div class="css-1r7lvp9">結果B</div>
    """

    # DOM差吸収のため、候補を「狭めたまま」複数用意（広い :has-text は最後の保険だけ）
    primary_selectors = [
        "div.css-1cmdo0c",  # 1回抽選の結果名
        "div.css-1r7lvp9",  # 2回以上で多い結果名
    ]

    def _clean(t: str) -> str:
        return (t or "").replace("\u3000", " ").strip()

    def _valid_name(t: str) -> bool:
        if not t:
            return False
        if t in ALLOWED_RESULT_NAMES:
            return True
        # 将来 結果D 等が出ても拾えるように（必要なら外してOK）
        if RESULT_NAME_RE.match(t) and t.startswith("結果") and len(t) <= 8:
            return True
        return False

    def _scan(base: Locator) -> str:
        # まずは狭いセレクタで探す
        for sel in primary_selectors:
            loc = base.locator(sel)
            c = loc.count()
            if c <= 0:
                continue
            for k in range(min(c, 10)):
                t = _clean(loc.nth(k).text_content() or "")
                # 「結果詳細」「結果」などのラベルを避ける
                if t in ("結果", "結果詳細") or "詳細" in t:
                    continue
                if _valid_name(t):
                    return t

        # 最終保険：base 内のテキスト群から「結果X」っぽいものを拾う（ただし広げすぎない）
        try:
            blob = _clean(base.text_content() or "")
            # 例: "結果\n結果A\n結果Aの説明..." から最初の "結果A" を拾う
            m = re.search(r"(結果[Ａ-ＺA-Z0-9]+)", blob)
            if m:
                cand = m.group(1)
                if _valid_name(cand):
                    return cand
        except Exception:
            pass

        return ""

    # 1) 詳細ブロック内
    name = _scan(it)
    if name:
        return name

    # 2) 1段上（ボタンが兄弟/親にある構造差を吸収）
    parent = it.locator("xpath=..")
    name = _scan(parent)
    if name:
        return name

    # 3) 2段上（念のため）
    parent2 = it.locator("xpath=../..")
    name = _scan(parent2)
    if name:
        return name

    return ""

def _extract_details_strict(page: Page, draw_count: int) -> list[dict]:
    """
    結果詳細の厳密チェック（selector 制限版）
    """

    block_sel = (
        S.DETAIL_BLOCK_SELECTOR_SINGLE
        if draw_count == 1
        else S.DETAIL_BLOCK_SELECTOR_MULTI
    )

    blocks = page.locator(block_sel)

    try:
        blocks.first.wait_for(state="attached", timeout=45000)
        blocks.first.wait_for(state="visible", timeout=45000)
    except PlaywrightTimeoutError:
        raise PlaywrightTimeoutError(
            f"結果詳細ブロックが表示されません selector='{block_sel}'"
        )

    count = blocks.count()
    if count != draw_count:
        raise AssertionError(
            f"結果詳細件数不一致: expected={draw_count}, actual={count}"
        )

    out = []

    for i in range(count):
        it = blocks.nth(i)

        # 結果画像（css-1xhi066 配下）
        img = it.locator(S.DETAIL_RESULT_IMG_SELECTOR)
        if img.count() != 1:
            raise AssertionError(
                f"[detail {i}] 結果画像が1枚ではありません (actual={img.count()})"
            )

        src = (img.first.get_attribute("src") or "").strip()
        alt = (img.first.get_attribute("alt") or "").strip()

        if not src:
            raise AssertionError(f"[detail {i}] 結果画像srcが空です")
        if not alt.startswith("結果"):
            raise AssertionError(f"[detail {i}] 結果画像altが想定外: '{alt}'")

        # 結果名
        name = _pick_detail_name(it, draw_count)
        if not name:
            raise AssertionError(f"[detail {i}] 結果名が取得できません")

        # 説明テキスト（必須）
        desc_text_loc = it.locator(S.DETAIL_DESC_TEXT_SELECTOR)
        if desc_text_loc.count() < 1:
            raise AssertionError(f"[detail {i}] 説明テキストがありません")

        desc_text = (desc_text_loc.first.text_content() or "").strip()
        if not desc_text:
            raise AssertionError(f"[detail {i}] 説明テキストが空です")

        # 説明内画像（1枚必須）
        desc_imgs = it.locator(S.DETAIL_DESC_IMAGE_SELECTOR)
        if desc_imgs.count() != 1:
            raise AssertionError(
                f"[detail {i}] 説明内画像は1枚必須 (actual={desc_imgs.count()})"
            )

        # 今すぐつかう（親 div 直下）
        use_btn = it.locator(S.DETAIL_USE_BUTTON_SELECTOR)
        if use_btn.count() < 1:
            raise AssertionError(f"[detail {i}] 今すぐつかうボタンが見つかりません")

        out.append(
            {
                "index": i,
                "name": name,
                "img_src": src,
                "img_alt": alt,
                "desc_text": desc_text,
            }
        )

    return out

def _extract_link_items_strict(page: Page) -> List[Dict[str, Any]]:
    items = page.locator(S.LINK_ITEM_SELECTOR)
    out: List[Dict[str, Any]] = []

    if items.count() == 0:
        raise PlaywrightTimeoutError("link items not found")

    for i in range(items.count()):
        it = items.nth(i)

        desc_loc = it.locator(S.LINK_DESC_TEXT_SELECTOR)
        desc_text = normalize_text(desc_loc.first.text_content() or "") if desc_loc.count() > 0 else ""
        if desc_text == "":
            raise PlaywrightTimeoutError(f"link desc text missing index={i}")

        if it.locator(S.LINK_DESC_IMAGE_SELECTOR).count() < 1:
            raise PlaywrightTimeoutError(f"link desc image missing index={i}")

        a = it.locator(S.LINK_BUTTON_SELECTOR).first
        href = (a.get_attribute("href") or "").strip()
        if href == "":
            raise PlaywrightTimeoutError(f"link href missing index={i}")

        bt = it.locator(S.LINK_BUTTON_TEXT_SELECTOR)
        btn_text = normalize_text(bt.first.text_content() or "") if bt.count() > 0 else normalize_text(a.text_content() or "")
        if btn_text == "":
            raise PlaywrightTimeoutError(f"link button text missing index={i}")

        out.append({"index": i, "button_text": btn_text, "href": href, "locator": a})

    return out


def _assert_dots_count(page: Page, artifacts: Artifacts, draw_count: int) -> bool:
    dots = page.locator(S.DOT_BUTTON_SELECTOR)
    try:
        dots.first.wait_for(timeout=8000)
    except Exception:
        pass
    if dots.count() != draw_count:
        artifacts.save_debug(page, "dot_count_mismatch")
        return False
    return True


def _assert_links_open_new_tab(page: Page, artifacts: Artifacts, link_items: List[Dict[str, Any]]) -> bool:
    for li in link_items:
        a = li["locator"]
        href = li["href"]

        _demo_wait(0.4)
        try:
            with page.expect_popup(timeout=15000) as pop:
                a.click()
            newp = pop.value
        except Exception:
            try:
                with page.context.expect_page(timeout=15000) as pg:
                    a.click()
                newp = pg.value
            except Exception:
                artifacts.save_debug(page, f"link_open_failed_{li['index']}")
                return False

        try:
            newp.wait_for_load_state("domcontentloaded", timeout=20000)
        except Exception:
            pass

        cur = newp.url or ""
        if href and (href not in cur) and (not cur.startswith(href)):
            artifacts.save_debug(page, f"link_url_mismatch_{li['index']}")
            try:
                newp.close()
            except Exception:
                pass
            return False

        _demo_wait(0.5)
        try:
            newp.close()
        except Exception:
            pass

    return True


def _assert_use_flow_all_results(page: Page, artifacts, detail_blocks, detail_names: list[str], slow_ms: int = 200) -> bool:
    """
    当選結果すべての「今すぐつかう」を順に押下して検証する

    - 各押下で確認モーダルが出る（注意文言、戻る、つかう）
    - モーダルに表示される結果名が「押下した結果名」と一致
    - 「つかう」押下でモーダルが閉じる
    - 押下した対象だけが「使用済み」になり押下不可
    - 押していない結果は「今すぐつかう」のまま（複数抽選時）

    detail_blocks: 1件=1結果を表すブロック locator（draw_count 件）
                  ※「今すぐつかう」が 1個上にある場合があるため、親も探索する
    detail_names : detail_blocks と同順の結果名（draw_count 件）
    """

    n = detail_blocks.count()
    if n <= 0:
        artifacts.save_debug(page, "use_no_detail_blocks")
        return False
    if len(detail_names) != n:
        artifacts.save_debug(page, "use_detail_names_len_mismatch")
        return False

    # 押下済みフラグ
    used_flags = [False] * n

    for i in range(n):
        # DOM更新対策：毎回取り直す
        it = detail_blocks.nth(i)
        target_name = detail_names[i]

        # --- 「今すぐつかう」ボタンを、ブロック自身→親(1段)→親(2段) の順で探す ---
        # （あなたのケース：css-1xhi066 の 1つ上に button がいる）
        # --- 「今すぐつかう」ボタン探索：子孫(button優先) → 親(1段) → 親(2段) ---
        # --- 「今すぐつかう」ボタン探索：子孫(button優先) → 親(1段) → 親(2段) ---
        cand = it.locator("button:has-text('今すぐつかう'), [role='button']:has-text('今すぐつかう')")
        if cand.count() < 1:
            cand = it.locator("xpath=..").locator("button:has-text('今すぐつかう'), [role='button']:has-text('今すぐつかう')")
        if cand.count() < 1:
            cand = it.locator("xpath=../..").locator("button:has-text('今すぐつかう'), [role='button']:has-text('今すぐつかう')")

        if cand.count() < 1:
            artifacts.save_debug(page, f"use_btn_missing_{i+1}")
            return False



        # クリックできるように
        try:
            cand.first.scroll_into_view_if_needed(timeout=5000)
        except Exception:
            pass
        page.wait_for_timeout(slow_ms)

        # 押下
        try:
            cand.first.click(timeout=15000)
        except Exception:
            # div拾ってる可能性もあるので force
            try:
                cand.first.click(timeout=15000, force=True)
            except Exception:
                artifacts.save_debug(page, f"use_btn_click_failed_{i+1}")
                return False

        # --- モーダル確認 ---
        modal = page.locator(S.RESULT_MODAL_SELECTOR)
        try:
            modal.first.wait_for(state="visible", timeout=15000)
        except PlaywrightTimeoutError:
            artifacts.save_debug(page, f"use_modal_not_visible_{i+1}")
            return False

        modal_text = (modal.first.text_content() or "").replace("\n", " ")

        # 注意文言
        if S.RESULT_MODAL_MESSAGE_TEXT not in modal_text:
            artifacts.save_debug(page, f"use_modal_notice_missing_{i+1}")
            return False

        # 結果名一致（押下した対象の結果名がモーダル内に含まれる）
        if target_name and (target_name not in modal_text):
            artifacts.save_debug(page, f"use_modal_name_mismatch_{i+1}")
            return False

        # 戻る/つかう ボタン
        if modal.locator(S.RESULT_MODAL_BACK_BUTTON_SELECTOR).count() < 1:
            artifacts.save_debug(page, f"use_modal_back_missing_{i+1}")
            return False
        if modal.locator(S.RESULT_MODAL_USE_BUTTON_SELECTOR).count() < 1:
            artifacts.save_debug(page, f"use_modal_use_missing_{i+1}")
            return False

        page.wait_for_timeout(slow_ms)

        # 「つかう」押下
        modal.locator(S.RESULT_MODAL_USE_BUTTON_SELECTOR).first.click()

        # モーダルが閉じる
        try:
            modal.first.wait_for(state="hidden", timeout=15000)
        except PlaywrightTimeoutError:
            # hidden にならない実装もあるため detached も見る
            try:
                modal.first.wait_for(state="detached", timeout=5000)
            except PlaywrightTimeoutError:
                artifacts.save_debug(page, f"use_modal_not_closed_{i+1}")
                return False

        # --- 押下した対象だけが使用済みになること ---
        # DOM更新対策で取り直す
        it2 = detail_blocks.nth(i)

        # 「使用済み」ボタンを（ブロック→親→親）で探す
        used_loc = it2.locator("button:has-text('使用済み'), [role='button']:has-text('使用済み')")
        if used_loc.count() < 1:
            used_loc = it2.locator("xpath=..").locator("button:has-text('使用済み'), [role='button']:has-text('使用済み')")
        if used_loc.count() < 1:
            used_loc = it2.locator("xpath=../..").locator("button:has-text('使用済み'), [role='button']:has-text('使用済み')")


        # 出るまで待つ（文言変化が遅い場合）
        try:
            used_loc.first.wait_for(state="visible", timeout=20000)
        except PlaywrightTimeoutError:
            artifacts.save_debug(page, f"not_marked_used_{i+1}")
            return False

        # 押下不可（disabled/クリック不可）を確認
        try:
            if used_loc.first.is_enabled():
                artifacts.save_debug(page, f"used_still_enabled_{i+1}")
                return False
        except Exception:
            # is_enabled が例外でも、とりあえず見えていればOKに寄せる
            pass

        used_flags[i] = True
        page.wait_for_timeout(slow_ms)

        # --- 他の未押下が「今すぐつかう」のまま ---
        # --- 他の未押下が「今すぐつかう」のまま ---
        for j in range(n):
            if used_flags[j]:
                continue

            other = detail_blocks.nth(j)

            # 「今すぐつかう」探す（ブロック→親→親）
            other_use = other.locator(S.DETAIL_USE_BUTTON_SELECTOR)
            if other_use.count() < 1:
                other_use = other.locator("xpath=..").locator(S.DETAIL_USE_BUTTON_SELECTOR)
            if other_use.count() < 1:
                other_use = other.locator("xpath=../..").locator(S.DETAIL_USE_BUTTON_SELECTOR)

            if other_use.count() < 1:
                # もし「使用済み」になっていたら、別原因（他まで使用済み化）
                other_used = other.locator(S.USED_BUTTON_SELECTOR)
                if other_used.count() < 1:
                    other_used = other.locator("xpath=..").locator(S.USED_BUTTON_SELECTOR)
                if other_used.count() < 1:
                    other_used = other.locator("xpath=../..").locator(S.USED_BUTTON_SELECTOR)

                if other_used.count() > 0:
                    artifacts.save_debug(page, f"unexpected_used_{i+1}_affects_{j+1}")
                    return False

                artifacts.save_debug(page, f"other_should_be_usable_{i+1}_but_{j+1}_missing")
                return False


    return True

# ---------------- ③④（reuse_policy） ----------------
def _toast_used_shown(
    page: Page,
    lead_params: dict | None = None,
    timeout_ms: int = 3500,
) -> bool:
    params = lead_params or {}

    toast_type = params.get("used_toast_type", "multi")

    if toast_type == "once":
        expected_text = S.TOAST_USED_MESSAGE_ONLY_ONCE
    else:
        expected_text = S.TOAST_USED_MESSAGE

    toast_title = page.locator(S.TOAST_TITLE_SELECTOR).filter(
        has_text=expected_text
    )

    try:
        toast_title.first.wait_for(timeout=timeout_ms)
        return True
    except Exception:
        return False


def _visible_with_text(page: Page, selector: str, text: str, timeout_ms: int) -> bool:
    try:
        page.locator(selector).filter(has_text=text).first.wait_for(
            state="visible",
            timeout=timeout_ms,
        )
        return True
    except Exception:
        return False


def _drawcount_screen_visible(page: Page, timeout_ms: int = 7000) -> bool:
    # 1) LINEログインモーダル
    if _visible_with_text(page, L.LINE_MODAL_SELECTOR, L.LINE_MODAL_TEXT, timeout_ms):
        return True

    # 2) SNSモーダル
    if _visible_with_text(page, N.SNS_MODAL_SELECTOR, N.SNS_MODAL_TEXT, timeout_ms):
        return True

    # 3) 通常フォーム（自前フォーム）モーダル
    if _visible_with_text(page, F.FORM_MODAL_SELECTOR, F.FORM_HEADING_TEXT1, timeout_ms):
        return True

    # 4) 埋め込みフォーム（HubSpot）: iframe 内に「送信」ボタンが見えたら進める
    try:
        iframe_loc = page.frame_locator("iframe.hs-form-iframe")
        iframe_loc.locator("input[type='submit'][value='送信']").first.wait_for(
            state="visible", timeout=timeout_ms
        )
        return True
    except Exception:
        pass

    # 5) 単発ガチャの抽選スタート画面（1〜10が無い方）
    # 「抽選スタート」ボタンが見えたら進める
    try:
        page.get_by_text("抽選スタート", exact=True).wait_for(timeout=timeout_ms)
        return True
    except Exception:
        pass

    try:
        page.get_by_text("QUESTION", exact=True).wait_for(timeout=timeout_ms)
        # 連続番号の "1" はガチャの回数ボタンと被るので、QUESTIONが見えた時だけ確認する
        page.get_by_text("1", exact=True).wait_for(timeout=timeout_ms)
        return True
    except Exception:
        pass

    # 6) 一括ガチャの抽選回数画面
    # ※ "text=1" は雑に拾うので、可能なら「回数ボタンの領域」セレクタに寄せるのが理想
    if _visible_with_text(page, "text=1", "1", timeout_ms):
        return True

    return False

def _click_play_again_to_top(page: Page, artifacts: Artifacts, top_start_text: str) -> bool:
    btn = page.locator(S.PLAY_AGAIN_BUTTON_SELECTOR).first
    if btn.count() < 1:
        artifacts.save_debug(page, "play_again_missing")
        return False
    _demo_wait(0.4)
    btn.click()
    try:
        page.get_by_text(top_start_text, exact=True).wait_for(timeout=20000)
    except PlaywrightTimeoutError:
        artifacts.save_debug(page, f"top_not_returned_{normalize_text(top_start_text)}")
        return False

    return True

def _attempt_start_gacha_and_observe(
    page: Page,
    lead_params: dict | None = None,
) -> str:

    params = lead_params or {}

    # 追加：開始ボタン文言（デフォルトはガチャ）
    start_text = (params.get("top_start_text") or S.START_GACHA_BTN_TEXT)
    print("DEBUG start_text:", start_text, "top_start_text:", params.get("top_start_text"))
    _demo_wait(0.4)
    page.get_by_text(start_text, exact=True).click()

    if _toast_used_shown(page, lead_params, timeout_ms=4000):
        return "used"
    if _drawcount_screen_visible(page, timeout_ms=15000):
        return "proceed"
    return "unknown"

def _ensure_userid_def_can_proceed(
    page: Page,
    artifacts: Artifacts,
    base_url: str,
    lead_params: dict | None = None,
) -> bool:
    _demo_wait(0.4)

    new_url = _maybe_randomize_userid(base_url, lead_params)

    page.goto(new_url, wait_until="domcontentloaded", timeout=45000)
    out = _attempt_start_gacha_and_observe(page, lead_params)
    if out != "proceed":
        artifacts.save_debug(page, "userid_random_still_blocked")
        return False
    return True



def _assert_play_again_policy(page: Page, artifacts: Artifacts, base_url: str, lead_params: Dict[str, Any] | None) -> bool:
    """
    lead_params:
      - reuse_policy:
          * "must_used"
          * "must_reusable"
          * "used_after_n"
          * "either"
      - reuse_allowed_times: used_after_n の N
    """
    params = lead_params or {}
    policy = params.get("reuse_policy", "either")
    allowed_times = int(params.get("reuse_allowed_times", 0) or 0)

    top_start_text = params.get("top_start_text", S.START_GACHA_BTN_TEXT)

    if not _click_play_again_to_top(page, artifacts, top_start_text=top_start_text):
        return False

    if policy == "must_used":
        out = _attempt_start_gacha_and_observe(page,lead_params)
        if out != "used":
            artifacts.save_debug(page, "must_used_but_not_used")
            return False
        return _ensure_userid_def_can_proceed(page, artifacts, base_url,lead_params)

    if policy == "must_reusable":
        out = _attempt_start_gacha_and_observe(page,lead_params)
        if out == "used":
            artifacts.save_debug(page, "must_reusable_but_used")
            return False
        if out != "proceed":
            artifacts.save_debug(page, "must_reusable_but_cannot_proceed")
            return False
        return True

    if policy == "used_after_n":
        if allowed_times <= 0:
            artifacts.save_debug(page, "used_after_n_missing_allowed_times")
            return False

        for k in range(allowed_times):
            top_start_text = params.get("top_start_text", S.START_GACHA_BTN_TEXT)
            out = _attempt_start_gacha_and_observe(page,lead_params)
            if out == "used":
                artifacts.save_debug(page, f"used_too_early_at_{k+1}")
                return False
            if out != "proceed":
                artifacts.save_debug(page, f"cannot_proceed_at_{k+1}")
                return False
            if not _click_play_again_to_top(page, artifacts, top_start_text=top_start_text):
                artifacts.save_debug(page, f"play_again_failed_at_{k+1}")
                return False

        out = _attempt_start_gacha_and_observe(page,lead_params)
        if out != "used":
            artifacts.save_debug(page, f"used_after_n_but_not_used_at_{allowed_times+1}")
            return False
        return _ensure_userid_def_can_proceed(page, artifacts, base_url,lead_params)

    # either
    out = _attempt_start_gacha_and_observe(page,lead_params)
    if out == "unknown":
        artifacts.save_debug(page, "neither_toast_nor_drawcount")
        return False
    if out == "used":
        return _ensure_userid_def_can_proceed(page, artifacts, base_url,lead_params)
    return True

def _assert_single_start_screen(page: Page, artifacts: Artifacts) -> bool:
    """
    単発ガチャ：
      - 「抽選スタート」ボタンが表示される
      - ここで 1〜10 は表示されない
    """
    try:
        page.get_by_text("抽選スタート", exact=True).wait_for(timeout=20000)
    except PlaywrightTimeoutError:
        artifacts.save_debug(page, "single_start_screen_not_opened")
        return False

    # 1〜10が見えていないこと（単発の条件）
    # ※ ページ内に別の数字が出る可能性があるなら、より狭い領域で絞り込みに変更可
    for n in range(1, 11):
        if page.get_by_text(str(n), exact=True).count() > 0:
            artifacts.save_debug(page, f"single_should_not_show_number_{n}")
            return False

    return True


# ---------------- メイン ----------------
def run_gacha(sc: Scenario, page: Page, artifacts: Artifacts) -> bool:
    if sc.draw_count is None:
        raise ValueError("gacha scenario requires draw_count")

    draw_count = sc.draw_count
    lead_params = sc.lead_params if isinstance(sc.lead_params, dict) else {}
    gacha_mode = (lead_params.get("gacha_mode") or "bulk").lower()

    try:
        lead_params = sc.lead_params if isinstance(sc.lead_params, dict) else {}
        url = _maybe_randomize_userid(sc.url, lead_params)
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.get_by_text(S.START_GACHA_BTN_TEXT, exact=True).click()

        # リード適用（noneならそのまま）
        try:
            page = apply_lead(sc, page, artifacts)
        except LeadSkipped:
            artifacts.save_debug(page, "lead_skipped")
            return True  # CAPTCHA等で続行不可なら落とさない方針
        
        # ★課金ガチャの場合だけ、購入フローをここで消化（単発/一括ロジックは崩さない）
        page = _maybe_handle_paid_gacha_after_lead(page, artifacts, sc)

        # =========================
        # 単発ガチャ分岐（ここだけ追加）
        # =========================
        if gacha_mode == "single":
            # ① 抽選スタート画面（1〜10が出ない）
            if not _assert_single_start_screen(page, artifacts):
                return False

            # ② 抽選スタート押下 → 結果画面へ（カード画面は経由しない）
            page.get_by_text("抽選スタート", exact=True).click()

            # 結果画面の詳細（単発なので draw_count=1 相当）
            # ※ カードが無いので card_results との一致チェックはしない
            try:
                details = _extract_details_strict(page, draw_count=1)
            except Exception:
                artifacts.save_debug(page, "detail_rule_failed_single")
                raise

            # 単発なのでサムネは出ない想定（出るなら仕様に合わせて緩める）
            if len(_extract_top_thumbs(page)) != 0:
                artifacts.save_debug(page, "topthumb_should_not_exist_single")
                return False

            # リンク
            try:
                link_items = _extract_link_items_strict(page)
            except PlaywrightTimeoutError:
                artifacts.save_debug(page, "link_rule_failed_single")
                return False

            # 単発：結果名は1つだけ
            unique_result_names = [details[0]["name"]]
            matched_count = {nm: 0 for nm in unique_result_names}
            for li in link_items:
                matched = None
                for nm in unique_result_names:
                    if nm in li["button_text"]:
                        matched = nm
                        break
                if matched is None:
                    artifacts.save_debug(page, f"link_not_matched_single_{li['index']}")
                    return False
                matched_count[matched] += 1

            for nm, cnt in matched_count.items():
                if cnt < 1:
                    artifacts.save_debug(page, f"link_count_invalid_single_{nm}_{cnt}")
                    return False

            # リンク押下→新規タブ
            if not _assert_links_open_new_tab(page, artifacts, link_items):
                return False

            # 「今すぐつかう」フロー（単発は1件）
            block_sel = S.DETAIL_BLOCK_SELECTOR_SINGLE
            detail_blocks = page.locator(block_sel)
            detail_names = [details[0]["name"]]

            if not _assert_use_flow_all_results(page, artifacts, detail_blocks, detail_names, slow_ms=400):
                artifacts.save_debug(page, "use_flow_failed_single")
                return False

            # もう一度あそぶ（reuse_policy）
            if not _assert_play_again_policy(page, artifacts, url, lead_params):
                return False

            return True

        # =========================
        # ここから下は “一括ガチャ” の既存ロジック（変更なし）
        # =========================

        # ① 抽選回数画面（表示チェック）
        if not _assert_draw_count_screen(page, artifacts, sc):
            return False

        # ② 抽選回数は固定ではなく sc.draw_count を使う
        page.get_by_text(str(draw_count), exact=True).click()
        page.get_by_text(S.DRAW_START_TEXT, exact=True).click()

        # カード待ち
        card = page.locator(S.CARD_IMAGE_SELECTOR).first
        try:
            card.wait_for(timeout=45000)
        except PlaywrightTimeoutError:
            artifacts.save_debug(page, "no_card")
            return False

        # ② カード画面 UI
        if not _assert_card_screen_ui(page, artifacts, card):
            return False

        # 追加：ドット数
        if not _assert_dots_count(page, artifacts, draw_count):
            return False

        # カードめくり結果収集
        card_results: List[Dict[str, str]] = []
        for i in range(draw_count):
            src = (card.get_attribute("src") or "").strip()
            alt = normalize_text(card.get_attribute("alt") or "")
            card_name = pick_result_name(alt)

            if card_name not in ALLOWED_RESULT_NAMES:
                artifacts.save_debug(page, f"card_name_invalid_{i+1}")
                return False

            card_results.append({"src": src, "name": card_name})

            _demo_wait(0.2)
            card.click()
            if i == draw_count - 1:
                break
            wait_until_src_changes(card, src, timeout_sec=20.0)

        # 上部サムネ
        if draw_count >= 2:
            try:
                page.locator(S.TOP_THUMB_SELECTOR).first.wait_for(timeout=25000)
            except PlaywrightTimeoutError:
                artifacts.save_debug(page, "no_topthumb")
                return False

            thumb_srcs = _extract_top_thumbs(page)
            if len(thumb_srcs) != draw_count:
                artifacts.save_debug(page, "topthumb_count_mismatch")
                return False

            card_srcs = [x["src"] for x in card_results]
            if thumb_srcs != card_srcs:
                artifacts.save_debug(page, "topthumb_order_mismatch")
                return False
        else:
            if len(_extract_top_thumbs(page)) != 0:
                artifacts.save_debug(page, "topthumb_should_not_exist")
                return False

        # 詳細
        try:
            details = _extract_details_strict(page, draw_count)
        except Exception:
            artifacts.save_debug(page, "detail_rule_failed")
            raise

        for i in range(draw_count):
            if details[i]["img_src"] != card_results[i]["src"]:
                artifacts.save_debug(page, f"detail_img_src_mismatch_{i+1}")
                return False
            if details[i]["name"] != card_results[i]["name"]:
                artifacts.save_debug(page, f"detail_name_mismatch_{i+1}")
                return False

        # リンク
        try:
            link_items = _extract_link_items_strict(page)
        except PlaywrightTimeoutError:
            artifacts.save_debug(page, "link_rule_failed")
            return False

        unique_result_names = list(dict.fromkeys([x["name"] for x in card_results]))
        matched_count = {nm: 0 for nm in unique_result_names}
        for li in link_items:
            matched = None
            for nm in unique_result_names:
                if nm in li["button_text"]:
                    matched = nm
                    break
            if matched is None:
                artifacts.save_debug(page, f"link_not_matched_{li['index']}")
                return False
            matched_count[matched] += 1

        for nm, cnt in matched_count.items():
            if cnt < 1:
                artifacts.save_debug(page, f"link_count_invalid_{nm}_{cnt}")
                return False

        if not _assert_links_open_new_tab(page, artifacts, link_items):
            return False

        block_sel = S.DETAIL_BLOCK_SELECTOR_SINGLE if draw_count == 1 else S.DETAIL_BLOCK_SELECTOR_MULTI
        detail_blocks = page.locator(block_sel)
        detail_names = [d["name"] for d in details]

        if not _assert_use_flow_all_results(page, artifacts, detail_blocks, detail_names, slow_ms=400):
            artifacts.save_debug(page, "use_flow_failed")
            return False

        if not _assert_play_again_policy(page, artifacts, url, lead_params):
            return False

        return True

    except Exception:
        artifacts.save_debug(page, "exception")
        raise
