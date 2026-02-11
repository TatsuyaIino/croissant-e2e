# e2e/src/core/url.py
from __future__ import annotations

from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
import uuid

def with_random_userid(url: str, key: str = "userid") -> str:
    p = urlparse(url)
    q = parse_qs(p.query)
    q[key] = [uuid.uuid4().hex]  # 被りにくい
    new_query = urlencode(q, doseq=True)
    return urlunparse((p.scheme, p.netloc, p.path, p.params, new_query, p.fragment))
