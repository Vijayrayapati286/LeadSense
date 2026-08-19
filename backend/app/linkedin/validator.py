"""Validate LinkedIn /in/ URLs and extracted profile payloads."""

from __future__ import annotations

import re
from typing import Any
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


_CHALLENGE_MARKERS = (
    "authwall",
    "checkpoint",
    "join to view",
    "sign in",
    "security verification",
    "captcha",
)

_RETRYABLE_MARKERS = (
    "timeout",
    "timed out",
    "temporarily",
    "rate limit",
    "429",
    "502",
    "503",
    "504",
    "empty",
    "no data",
    "network",
    "connection",
    "apify",
    "server error",
)


def _nonempty(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    return bool(text) and text.lower() not in {"none", "null", "n/a", "-"}


def is_valid_extraction(result: dict[str, Any] | None) -> bool:
    """True only when the payload has usable profile fields, not merely HTTP/Apify OK."""
    if not result:
        return False
    status = str(result.get("status") or "").strip().lower()
    if status in {"failed", "final_failed", "error"}:
        return False
    if result.get("success") is False:
        return False
    data = result.get("data") if isinstance(result.get("data"), dict) else result
    if not isinstance(data, dict):
        return False

    blob = " ".join(str(v) for v in data.values() if v is not None).lower()
    if any(marker in blob for marker in _CHALLENGE_MARKERS) and not _nonempty(data.get("name")):
        return False

    name = data.get("name") or data.get("full_name")
    company = data.get("company")
    designation = data.get("job_title") or data.get("designation") or data.get("title")
    about = data.get("about") or data.get("summary")
    headline = data.get("headline")

    return any(_nonempty(v) for v in (name, company, designation, about, headline))


def is_retryable_error(message: str | None, *, non_retryable_csv: str = "") -> bool:
    """Default retryable; only clearly permanent errors skip remaining attempts."""
    text = (message or "").strip().lower()
    if not text:
        return True
    configured = [p.strip().lower() for p in (non_retryable_csv or "").split(",") if p.strip()]
    if any(p in text for p in configured):
        return False
    if "invalid url" in text or "must be a linkedin" in text or "malformed" in text:
        return False
    if any(m in text for m in _RETRYABLE_MARKERS):
        return True
    return True
