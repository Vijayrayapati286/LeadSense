"""Validate public LinkedIn /in/ profile URLs only."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import urlparse, urlunparse

_HOSTS = {"www.linkedin.com", "linkedin.com"}
_IN_PATH = re.compile(r"^/in/([^/?#]+)/?$", re.I)


def is_public_profile_url(url: str) -> bool:
    try:
        parsed = urlparse((url or "").strip())
    except Exception:
        return False
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or host not in _HOSTS:
        return False
    return bool(_IN_PATH.match(parsed.path or ""))


def normalize_profile_url(url: str) -> str:
    raw = (url or "").strip()
    parsed = urlparse(raw)
    match = _IN_PATH.match(parsed.path or "")
    if not match:
        return raw
    slug = match.group(1)
    return urlunparse(("https", "www.linkedin.com", f"/in/{slug}/", "", "", ""))


def validate_profile_url(url: str) -> str:
    cleaned = (url or "").strip()
    if not is_public_profile_url(cleaned):
        raise ValueError(
            "URL must be a public LinkedIn profile like https://www.linkedin.com/in/username/"
        )
    return normalize_profile_url(cleaned)


def url_hash(url: str) -> str:
    return hashlib.sha256(normalize_profile_url(url).encode("utf-8")).hexdigest()
