# e2e/src/flows/diagnose_flow.py
from __future__ import annotations
from typing import Dict, Any, List
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from src.core.types import Scenario
from src.core.artifacts import Artifacts
from src.core.url import with_random_userid
from src.leads.lead_router import apply_lead

from src.selectors import diagnose_selectors as D

# ✅ 結果画面の検証はガチャの既存資産を流用
from src.flows.gacha_flow import (
    _extract_details_strict,
    _extract_link_items_strict,
    _assert_links_open_new_tab,
    _assert_use_flow_all_results,
    _assert_play_again_policy,
)
from src.selectors import gacha_selectors as GS


def _get_params(sc: Scenario) -> Dict[str, Any]:
    return sc.lead_params if isinstance(sc.lead_params, dict) else {}


def _wait_top(page: Page, artifacts: Artifacts) -> bool:
    try:
        page.get_by_text(D.START_BTN_TEXT, exact=True).wait_for(timeout=20000)
        return True
    except Exception:
        artifacts.save_debug(page, "diagnose_top_not_opened")
        return False


def _assert_question_common(page: Page, artifacts: Artifacts, q_no: int) -> bool:
    try:
        page.get_by_text(D.QUESTION_LABEL_TEXT, exact=True).wait_for(timeout=20000)
        page.get_by_text(str(q_no), exact=True).wait_for(timeout=20000)
        # 画像
        if page.locator(D.QUESTION_IMAGE_SELECTOR).count() < 1:
            artifacts.save_debug(page, f"diagnose_q{q_no}_image_missing")
            return False
        return True
    except Exception:
        artifacts.save_debug(page, f"diagnose_q{q_no}_header_missing")
        return False


def _select_answer_single(page: Page, artifacts: Artifacts, answer_text: str) -> bool:
    """
    単一回答：ラベル内のテキストで選択（checkboxでもOK）
    """
    try:
        # 回答テキスト（A/B/Cなど）を含む label をクリック
        loc = page.locator("label").filter(has_text=answer_text)
        if loc.count() < 1:
            artifacts.save_debug(page, f"diagnose_single_answer_not_found_{answer_text}")
            return False
        loc.first.click(timeout=20000)
        return True
    except Exception:
        artifacts.save_debug(page, f"diagnose_single_answer_click_failed_{answer_text}")
        return False


def _select_answer_multi(page: Page, artifacts: Artifacts, answers: List[str]) -> bool:
    for a in answers:
        if not _select_answer_single(page, artifacts, a):
            return False
    return True


def _assert_multi_ui(page: Page, artifacts: Artifacts) -> bool:
    try:
        page.get_by_text(D.MULTI_LABEL_TEXT, exact=True).wait_for(timeout=20000)
        page.get_by_text(D.NEXT_BTN_TEXT, exact=True).wait_for(timeout=20000)
        return True
    except Exception:
        artifacts.save_debug(page, "diagnose_multi_ui_missing")
        return False


def _assert_branch(page: Page, artifacts: Artifacts, branch_expected: Dict[str, Any], step: str) -> bool:
    """
    branch_expected:
      q2_text, q3_text, q3_multi
    """
    if not branch_expected:
        return True

    try:
        if step == "q2" and branch_expected.get("q2_text"):
            if page.get_by_text(branch_expected["q2_text"], exact=False).count() < 1:
                artifacts.save_debug(page, "diagnose_branch_q2_mismatch")
                return False

        if step == "q3" and branch_expected.get("q3_text"):
            if page.get_by_text(branch_expected["q3_text"], exact=False).count() < 1:
                artifacts.save_debug(page, "diagnose_branch_q3_mismatch")
                return False

        if step == "q3" and branch_expected.get("q3_multi") is True:
            if page.get_by_text(D.MULTI_LABEL_TEXT, exact=True).count() < 1:
                artifacts.save_debug(page, "diagnose_branch_q3_should_be_multi")
                return False

        return True
    except Exception:
        artifacts.save_debug(page, "diagnose_branch_check_error")
        return False


def _calc_total_points(params: Dict[str, Any]) -> int | None:
    """
    answer_points が入っている時だけ合計点を計算する。
    入ってないなら None を返す（結果名の固定検証だけにする）
    """
    ap = params.get("answer_points")
    ans = params.get("answers")
    if not isinstance(ap, dict) or not isinstance(ans, dict):
        return None

    total = 0

    # q1
    q1 = ans.get("q1")
    if isinstance(q1, str):
        total += int(ap.get("q1", {}).get(q1, 0) or 0)

    # q2
    q2 = ans.get("q2")
    if isinstance(q2, str):
        total += int(ap.get("q2", {}).get(q2, 0) or 0)

    # q3
    q3 = ans.get("q3")
    if isinstance(q3, list):
        for x in q3:
            total += int(ap.get("q3", {}).get(x, 0) or 0)
    elif isinstance(q3, str):
        total += int(ap.get("q3", {}).get(q3, 0) or 0)

    return total


def _axis_expected_result(params: Dict[str, Any], total_points: int) -> str | None:
    th = params.get("axis_thresholds")
    if not isinstance(th, dict):
        return None

    # 例: A:[0,5], B:[5,11], C:[12,999]
    for name, rng in th.items():
        if not isinstance(rng, list) or len(rng) != 2:
            continue
        lo, hi = int(rng[0]), int(rng[1])
        if lo <= total_points <= hi:
            return f"結果{name}"
    return None

def _calc_additive_points(params: Dict[str, Any]) -> Dict[str, int] | None:
    """
    answer_points が {A:...,B:...,C:...} の辞書を返す形のとき、
    A/B/C の合計点を作る。
    """
    ap = params.get("answer_points")
    ans = params.get("answers")
    if not isinstance(ap, dict) or not isinstance(ans, dict):
        return None

    total = {"A": 0, "B": 0, "C": 0}

    def add_from(qkey: str, picked: str) -> None:
        nonlocal total
        m = ap.get(qkey, {})  # q1/q2/q3
        rule = m.get(picked)
        if not isinstance(rule, dict):
            return
        total["A"] += int(rule.get("A", 0) or 0)
        total["B"] += int(rule.get("B", 0) or 0)
        total["C"] += int(rule.get("C", 0) or 0)

    # q1
    q1 = ans.get("q1")
    if isinstance(q1, str):
        add_from("q1", q1)

    # q2
    q2 = ans.get("q2")
    if isinstance(q2, str):
        add_from("q2", q2)

    # q3（複数）
    q3 = ans.get("q3")
    if isinstance(q3, list):
        for x in q3:
            if isinstance(x, str):
                add_from("q3", x)
    elif isinstance(q3, str):
        add_from("q3", q3)

    return total

def _pick_additive_result(params: Dict[str, Any], total: Dict[str, int]) -> str:
    """
    total={"A":..,"B":..,"C":..} から最大を選び、"結果A" などに変換する。
    同点があれば tie_breaker の順で決める（無ければ A→B→C）。
    """
    tie = params.get("tie_breaker")
    order = tie if isinstance(tie, list) and tie else ["A", "B", "C"]

    maxv = max(total.values())
    candidates = [k for k, v in total.items() if v == maxv]

    for k in order:
        if k in candidates:
            return f"結果{k}"

    # ここには基本来ないが保険
    return f"結果{candidates[0]}"


def run_diagnose(sc: Scenario, page: Page, artifacts: Artifacts) -> bool:
    params = _get_params(sc)

    # ✅ ① userid をランダム付与してアクセス
    url = with_random_userid(sc.url)
    page.goto(url, wait_until="domcontentloaded", timeout=45000)

    # トップ
    if not _wait_top(page, artifacts):
        return False

    # ✅ ② 診断を始める
    page.get_by_text(D.START_BTN_TEXT, exact=True).click()

    # ✅ lead timing: before_start の場合ここでリードが出る
    page = apply_lead(sc, page, artifacts, phase="before_start")

    # Q1表示
    if not _assert_question_common(page, artifacts, q_no=1):
        return False
    if page.get_by_text("Q1", exact=False).count() < 1:
        artifacts.save_debug(page, "diagnose_q1_text_missing")
        return False

    answers = params.get("answers", {})
    branch_expected = params.get("branch_expected", {})

    # ✅ ③ Q1
    q1 = answers.get("q1")
    if not isinstance(q1, str):
        artifacts.save_debug(page, "diagnose_answers_q1_missing")
        return False
    if not _select_answer_single(page, artifacts, q1):
        return False

    # Q2
    if not _assert_question_common(page, artifacts, q_no=2):
        return False
    if not _assert_branch(page, artifacts, branch_expected, step="q2"):
        return False

    q2 = answers.get("q2")
    if not isinstance(q2, str):
        artifacts.save_debug(page, "diagnose_answers_q2_missing")
        return False
    if not _select_answer_single(page, artifacts, q2):
        return False

    # Q3
    if not _assert_question_common(page, artifacts, q_no=3):
        return False
    if not _assert_branch(page, artifacts, branch_expected, step="q3"):
        return False

    q3 = answers.get("q3")
    if isinstance(q3, list):
        # 複数回答
        if not _assert_multi_ui(page, artifacts):
            return False
        if not _select_answer_multi(page, artifacts, q3):
            return False
        page.get_by_text(D.NEXT_BTN_TEXT, exact=True).click()
    elif isinstance(q3, str):
        # 単一回答
        if not _select_answer_single(page, artifacts, q3):
            return False
    else:
        artifacts.save_debug(page, "diagnose_answers_q3_missing")
        return False

    # 結果確認前画面
    try:
        page.get_by_text(D.RESULT_CONFIRM_TEXT, exact=False).wait_for(timeout=25000)
        page.get_by_text(D.RESULT_BTN_TEXT, exact=True).wait_for(timeout=25000)
        page.get_by_text(D.BACK_TO_ANS_TEXT, exact=True).wait_for(timeout=25000)
    except Exception:
        artifacts.save_debug(page, "diagnose_result_confirm_screen_missing")
        return False

    # ✅ lead timing: before_result の場合ここでリードが出る（結果ボタン押下時）
    # 先にボタン押下 → 直後に apply_lead で吸収、の順にする
    page.get_by_text(D.RESULT_BTN_TEXT, exact=True).click()
    page = apply_lead(sc, page, artifacts, phase="before_result")

    # ✅ 結果画面（ガチャ単発と同じ扱い）
    try:
        details = _extract_details_strict(page, draw_count=1)
    except Exception:
        artifacts.save_debug(page, "diagnose_detail_rule_failed")
        raise

    # ✅ ポイント検証（可能な場合）
    dtype = (params.get("diagnose_type") or "").lower()

    if dtype == "axis_point":
        total = _calc_total_points(params)  # 一軸の合計点
        if total is not None:
            exp = _axis_expected_result(params, total)
            if exp and details[0]["name"] != exp:
                artifacts.save_debug(
                    page,
                    f"diagnose_axis_result_mismatch_actual_{details[0]['name']}_expected_{exp}",
                )
                return False

    elif dtype == "additive":
        total = _calc_additive_points(params)  # 結果ごとの加算点（例: {"A":x,"B":y,"C":z} など）
        if total is not None:
            expected = _pick_additive_result(params, total)
            if expected and details[0]["name"] != expected:
                artifacts.save_debug(
                    page,
                    f"diagnose_additive_result_mismatch_actual_{details[0]['name']}_expected_{expected}",
                )
                return False

    if total is not None:
        dtype = (params.get("diagnose_type") or "").lower()
        if dtype == "axis_point":
            exp = _axis_expected_result(params, total)
            if exp and details[0]["name"] != exp:
                artifacts.save_debug(page, f"diagnose_axis_result_mismatch_{details[0]['name']}_expected_{exp}")
                return False

    # ✅ リンク（複数リンクを許容するなら「結果名が含まれてるものが1件以上」でOKにする、など調整可能）
    try:
        link_items = _extract_link_items_strict(page)
    except PlaywrightTimeoutError:
        artifacts.save_debug(page, "diagnose_link_rule_failed")
        return False

    if not _assert_links_open_new_tab(page, artifacts, link_items):
        return False

    # 今すぐつかう（結果は1件想定）
    detail_blocks = page.locator(GS.DETAIL_BLOCK_SELECTOR_SINGLE)
    detail_names = [details[0]["name"]]
    if not _assert_use_flow_all_results(page, artifacts, detail_blocks, detail_names, slow_ms=400):
        artifacts.save_debug(page, "diagnose_use_flow_failed")
        return False

    # ✅ もう一度あそぶ → トップへ
    if not _assert_play_again_policy(page, artifacts, sc.url, params):
        return False

    # ✅ must_used（once）の場合：同一useridだと「ご利用済み」になるが、診断は毎回useridランダムで来てるのでここは任意
    return True
