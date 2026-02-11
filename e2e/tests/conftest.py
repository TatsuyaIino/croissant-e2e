import os
import re
from datetime import datetime
from pathlib import Path

import pytest
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright


def _truthy(v: str | None) -> bool:
    return (v or "").lower() in ("1", "true", "yes", "y", "on")


def _safe_name(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_.-]+", "_", s or "")
    s = s.strip("_")
    return s[:120] if s else "trace"


@pytest.fixture(scope="session", autouse=True)
def _load_env():
    load_dotenv()


@pytest.fixture(scope="session")
def pw():
    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="session")
def artifacts_base_dir():
    base = Path(os.getenv("ARTIFACT_DIR", "artifacts"))
    base.mkdir(parents=True, exist_ok=True)
    return base


@pytest.fixture(scope="session")
def context(pw):
    """
    ✅ プライベートモード相当を避けるため persistent context を使う
    """
    is_ci = _truthy(os.getenv("CI"))
    headless = _truthy(os.getenv("PW_HEADLESS")) if os.getenv("PW_HEADLESS") is not None else is_ci

    profile_dir = Path(os.path.expanduser(os.getenv("PW_PROFILE_DIR", "~/playwright-profile")))
    profile_dir.mkdir(parents=True, exist_ok=True)

    channel = os.getenv("PW_CHANNEL")  # 例: "chrome"
    slow_mo = int(os.getenv("PW_SLOWMO_MS", "0"))
    timeout_ms = int(os.getenv("PW_TIMEOUT_MS", "30000"))
    nav_timeout_ms = int(os.getenv("PW_NAV_TIMEOUT_MS", "45000"))

    launch_kwargs = {
        "user_data_dir": str(profile_dir),
        "headless": headless,
        "slow_mo": slow_mo,
    }
    if channel:
        launch_kwargs["channel"] = channel

    ctx = pw.chromium.launch_persistent_context(**launch_kwargs)
    ctx.set_default_timeout(timeout_ms)
    ctx.set_default_navigation_timeout(nav_timeout_ms)

    yield ctx

    ctx.close()


@pytest.fixture()
def page(context):
    """
    テストごとに新しいタブを作る（プロファイルは共有＝非プライベート）
    """
    p = context.new_page()
    yield p
    p.close()


@pytest.fixture()
def tracing_stop(request, context, artifacts_base_dir):
    """
    テストごとに trace を保存する
    """
    scenario_id = None
    try:
        sc = request.node.callspec.params.get("sc")
        scenario_id = getattr(sc, "id", None)
    except Exception:
        pass

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = _safe_name(scenario_id or request.node.name)
    out_dir = artifacts_base_dir / (scenario_id or name)
    out_dir.mkdir(parents=True, exist_ok=True)
    trace_path = out_dir / f"trace_{name}_{ts}.zip"

    # start
    try:
        context.tracing.start(screenshots=True, snapshots=True, sources=True)
    except Exception:
        pass

    def _stop():
        try:
            context.tracing.stop(path=str(trace_path))
        except Exception:
            pass

    yield _stop

    _stop()
