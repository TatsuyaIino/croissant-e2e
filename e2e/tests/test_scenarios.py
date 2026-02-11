import pytest
from src.core.scenario_loader import load_scenarios
from src.flows.runner import run_scenario

SCENARIOS = load_scenarios()

@pytest.mark.parametrize("sc", SCENARIOS, ids=lambda s: s.id)
def test_scenario(sc, page, artifacts_base_dir, tracing_stop):
    ok = run_scenario(sc, page, artifacts_base_dir, tracing_stop)
    assert ok, f"Scenario failed: {sc.id} {sc.name}"
