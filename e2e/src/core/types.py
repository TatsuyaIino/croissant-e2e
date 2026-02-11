from dataclasses import dataclass
from typing import Literal, Optional, Dict, Any

ContentType = Literal["gacha", "diagnose", "survey"]
LeadType = Literal["none", "line", "sns", "form", "embed_form"]


@dataclass(frozen=True)
class Scenario:
    id: str
    content_type: ContentType
    name: str
    url: str
    lead_type: LeadType
    draw_count: Optional[int] = None
    lead_params: Optional[Dict[str, Any]] = None
