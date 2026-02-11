# e2e/src/leads/lead_router.py
from __future__ import annotations
from playwright.sync_api import Page
from src.core.artifacts import Artifacts
from src.core.types import Scenario

from src.leads.line_lead import apply_line_lead
from src.leads.sns_lead import apply_sns_lead
from src.leads.form_lead import apply_form_lead
from src.leads.embed_form_lead import apply_embed_form_lead

def apply_lead(sc: Scenario, page: Page, artifacts: Artifacts, phase: str = "before_start") -> Page:
    """
    phase:
      - before_start
      - before_result
    """
    lead_type = (sc.lead_type or "none").lower()
    lead_params = sc.lead_params if isinstance(sc.lead_params, dict) else {}

    # ✅ 診断用：タイミングが合わない場合は何もしない
    lead_timing = (lead_params.get("lead_timing") or "before_start").lower()
    if lead_timing and lead_timing != phase:
        return page

    if lead_type == "none":
        return page
    if lead_type == "line":
        return apply_line_lead(page, artifacts)
    if lead_type == "sns":
        return apply_sns_lead(page, artifacts)
    if lead_type == "form":
        return apply_form_lead(page, artifacts)
    if lead_type == "embed_form":
        return apply_embed_form_lead(page, artifacts)

    return page
