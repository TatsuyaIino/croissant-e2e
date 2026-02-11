from __future__ import annotations

from pathlib import Path
from typing import List, Any, Dict

import yaml

from .types import Scenario


def load_scenarios(path: str | Path = "scenarios/scenarios.yaml") -> List[Scenario]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Scenario file not found: {p.resolve()}")

    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("scenarios.yaml must be a list")

    out: List[Scenario] = []
    for row in raw:
        if not isinstance(row, dict):
            raise ValueError("Each scenario must be a dict")
        out.append(_to_scenario(row))
    return out


def _to_scenario(d: Dict[str, Any]) -> Scenario:
    required = ["id", "content_type", "name", "url", "lead_type"]
    for k in required:
        if k not in d:
            raise ValueError(f"Missing key '{k}' in scenario: {d}")

    lead_params = d.get("lead_params")
    if lead_params is not None and not isinstance(lead_params, dict):
        raise ValueError(f"lead_params must be dict: {d.get('id')}")

    return Scenario(
        id=str(d["id"]),
        content_type=str(d["content_type"]),
        name=str(d["name"]),
        url=str(d["url"]),
        lead_type=str(d["lead_type"]),
        draw_count=int(d["draw_count"]) if d.get("draw_count") is not None else None,
        lead_params=lead_params,
    )
