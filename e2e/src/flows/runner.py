# e2e/src/flows/runner.py
from __future__ import annotations

from pathlib import Path
from playwright.sync_api import Page

from src.core.types import Scenario
from src.core.artifacts import Artifacts
from src.flows.gacha_flow import run_gacha

from src.flows.gacha_flow import run_gacha
from src.flows.diagnose_flow import run_diagnose

def run_scenario(sc: Scenario, page: Page, artifacts_base_dir: Path, tracing_stop) -> bool:
    """
    tracing_stop は conftest から渡される関数。
    scenario_id ごとに trace.zip を保存する。
    """
    artifacts = Artifacts(base_dir=artifacts_base_dir, scenario_id=sc.id)

    ok = False
    try:
        if sc.content_type == "gacha":
            return run_gacha(sc, page, artifacts)
        if sc.content_type == "diagnose":
            return run_diagnose(sc, page, artifacts)
        else:
            artifacts.save_debug(page, "unknown_content_type")
            raise ValueError(f"Unknown content_type: {sc.content_type}")

    finally:
        # trace保存（必ず）
        try:
            trace_path = str(artifacts.path("trace.zip"))
            tracing_stop(trace_path)
        except Exception:
            pass
