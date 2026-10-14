"""Signed one-click unsubscribe links for List-Unsubscribe headers."""

from __future__ import annotations

import hmac
from hashlib import sha256
from urllib.parse import quote, urlencode

from app.config import get_settings


def unsubscribe_token(email: str, secret: str | None = None) -> str:
    key = (secret or get_settings().secret_key or "").encode("utf-8")
    normalized = (email or "").strip().lower().encode("utf-8")
    return hmac.new(key, normalized, sha256).hexdigest()[:32]


def valid_unsubscribe_token(email: str, token: str, secret: str | None = None) -> bool:
    expected = unsubscribe_token(email, secret)
    return bool(token) and hmac.compare_digest(expected, (token or "").strip())


def public_api_base(settings=None) -> str:
    cfg = settings or get_settings()
    return (
        (cfg.public_api_url or "").strip()
        or (cfg.frontend_url or "").strip()
        or (cfg.backend_url or "").strip()
        or "http://localhost:8000"
    ).rstrip("/")


def unsubscribe_url(email: str, *, backend_url: str | None = None) -> str:
    base = (backend_url or public_api_base()).rstrip("/")
    query = urlencode({"email": (email or "").strip().lower(), "token": unsubscribe_token(email)})
    return f"{base}/api/public/unsubscribe?{query}"


def unsubscribe_footer_html(email: str) -> str:
    url = unsubscribe_url(email)
    return (
        '<p style="margin-top:28px;padding-top:12px;border-top:1px solid #e5e7eb;'
        'font-size:12px;color:#64748b;line-height:1.5;">'
        "If you no longer wish to receive emails from LeadSense, "
        f'<a href="{url}" style="color:#64748b;text-decoration:underline;">unsubscribe here</a>.'
        "</p>"
    )


def unsubscribe_footer_text(email: str) -> str:
    return f"\n\nIf you no longer wish to receive emails from LeadSense, unsubscribe here:\n{unsubscribe_url(email)}\n"


def list_unsubscribe_value(to_email: str, from_address: str) -> str:
    """RFC 2369 header value: mailto + HTTPS one-click."""
    mailto = f"<mailto:{from_address}?subject={quote('unsubscribe')}>"
    https = f"<{unsubscribe_url(to_email)}>"
    return f"{mailto}, {https}"
