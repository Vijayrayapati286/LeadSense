"""Validate and normalize LinkedIn /in/ profile URLs only."""

from __future__ import annotations

import re
from urllib.parse import urlparse, urlunparse

_HOSTS = {"www.linkedin.com", "linkedin.com"}
_IN_PATH = re.compile(r"^/in/([^/?#]+)/?$", re.I)


def is_linkedin_in_profile_url(url: str) -> bool:
    try:
        parsed = urlparse((url or "").strip())
    except Exception:
        return False
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or host not in _HOSTS:
        return False
    return bool(_IN_PATH.match(parsed.path or ""))


def normalize_profile_url(url: str) -> str:
    """Return a clean https://www.linkedin.com/in/{slug}/ URL (no query/fragment)."""
    raw = (url or "").strip()
    parsed = urlparse(raw)
    match = _IN_PATH.match(parsed.path or "")
    if not match:
        return raw
    slug = match.group(1)
    return urlunparse(("https", "www.linkedin.com", f"/in/{slug}/", "", "", ""))


def validate_profile_url(url: str) -> str:
    """Raise ValueError if invalid; otherwise return normalized URL."""
    cleaned = (url or "").strip()
    if not is_linkedin_in_profile_url(cleaned):
        raise ValueError(
            "URL must be a LinkedIn profile link like https://www.linkedin.com/in/username/"
        )
    return normalize_profile_url(cleaned)
