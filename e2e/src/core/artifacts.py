from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from playwright.sync_api import Page


@dataclass
class Artifacts:
    base_dir: Path
    scenario_id: str

    @property
    def out_dir(self) -> Path:
        d = self.base_dir / self.scenario_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def path(self, filename: str) -> Path:
        return self.out_dir / filename

    def save_debug(self, page: Page, prefix: str) -> None:
        # スクショ
        try:
            page.screenshot(path=str(self.path(f"{prefix}.png")), full_page=True)
        except Exception:
            pass
        # HTML
        try:
            html = page.content()
            self.path(f"{prefix}.html").write_text(html, encoding="utf-8")
        except Exception:
            pass

    def save_last(self, page: Page) -> None:
        self.save_debug(page, "last")


def get_artifact_base_dir() -> Path:
    base = Path(os.getenv("ARTIFACT_DIR", "artifacts"))
    base.mkdir(parents=True, exist_ok=True)
    return base
