"""Read-only remaining credits for MillionVerifier and Apify.

Failures are returned as a status payload. They never raise, and secrets
are never included in the result or in logs.
"""

from __future__ import annotations

import logging

import httpx

from app.config import get_settings
from app.services.millionverifier_service import (
    MillionVerifierAuthError,
    MillionVerifierConfigError,
    MillionVerifierService,
)

logger = logging.getLogger(__name__)

_APIFY_USER_URL = "https://api.apify.com/v2/users/me"
_APIFY_USAGE_URL = "https://api.apify.com/v2/users/me/usage/monthly"
_HTTP_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)


def _mv_payload(status: str, *, credits_remaining: int | None = None, detail: str | None = None) -> dict:
    return {
        "provider": "millionverifier",
        "status": status,
        "credits_remaining": credits_remaining,
        "unit": "credits",
        "detail": detail,
    }


def _apify_payload(
    status: str,
    *,
    credits_remaining: float | None = None,
    credits_limit: float | None = None,
    credits_used: float | None = None,
    detail: str | None = None,
) -> dict:
    return {
        "provider": "apify",
        "status": status,
        "credits_remaining": credits_remaining,
        "credits_limit": credits_limit,
        "credits_used": credits_used,
        "unit": "usd",
        "detail": detail,
    }


def _millionverifier_credits() -> dict:
    settings = get_settings()
    if not settings.millionverifier_enabled:
        return _mv_payload("disabled", detail="MillionVerifier is disabled.")
    if settings.use_mock_millionverifier:
        return _mv_payload("mock", detail="Mock mode does not use MillionVerifier credits.")
    if not (settings.millionverifier_api_key or "").strip():
        return _mv_payload("not_configured", detail="MILLIONVERIFIER_API_KEY is not set.")
    try:
        data = MillionVerifierService(settings=settings).check_credits()
    except MillionVerifierConfigError:
        return _mv_payload("not_configured", detail="MILLIONVERIFIER_API_KEY is not set.")
    except MillionVerifierAuthError:
        logger.error("MillionVerifier credit check failed: authentication")
        return _mv_payload("unavailable", detail="MillionVerifier rejected the API key.")
    except Exception as exc:
        logger.error("MillionVerifier credit check failed: %s", exc)
        return _mv_payload("unavailable", detail="Could not reach MillionVerifier.")

    raw = data.get("credits") if isinstance(data, dict) else None
    try:
        credits = int(raw)
    except (TypeError, ValueError):
        logger.error("MillionVerifier credit check returned no credits field")
        return _mv_payload("unavailable", detail="MillionVerifier did not return a credit balance.")
    return _mv_payload("ok", credits_remaining=credits)


def _as_float(value: object) -> float | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _apify_get(url: str, token: str) -> dict:
    with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
        response = client.get(url, headers={"Authorization": f"Bearer {token}"})
    if response.status_code in (401, 403):
        raise PermissionError("authentication")
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("unexpected response")
    inner = data.get("data")
    return inner if isinstance(inner, dict) else data


def _apify_credits() -> dict:
    token = (get_settings().apify_token or "").strip()
    if not token:
        return _apify_payload("not_configured", detail="APIFY_TOKEN is not set.")
    try:
        user = _apify_get(_APIFY_USER_URL, token)
        usage = _apify_get(_APIFY_USAGE_URL, token)
    except PermissionError:
        logger.error("Apify credit check failed: authentication")
        return _apify_payload("unavailable", detail="Apify rejected the API token.")
    except Exception as exc:
        logger.error("Apify credit check failed: %s", exc)
        return _apify_payload("unavailable", detail="Could not reach Apify.")

    plan = user.get("plan") if isinstance(user.get("plan"), dict) else {}
    limit = _as_float(plan.get("monthlyUsageCreditsUsd"))
    if limit is None:
        limit = _as_float(plan.get("maxMonthlyUsageUsd"))
    used = _as_float(usage.get("totalUsageCreditsUsdAfterVolumeDiscount"))
    if used is None:
        used = _as_float(usage.get("totalUsageCreditsUsdBeforeVolumeDiscount"))
    if limit is None and used is None:
        return _apify_payload("unavailable", detail="Apify did not return a credit balance.")

    remaining = None
    if limit is not None and used is not None:
        remaining = round(max(limit - used, 0.0), 2)
    elif limit is not None:
        remaining = round(limit, 2)
    return _apify_payload(
        "ok",
        credits_remaining=remaining,
        credits_limit=None if limit is None else round(limit, 2),
        credits_used=None if used is None else round(used, 2),
    )


def get_provider_credits() -> dict:
    return {
        "millionverifier": _millionverifier_credits(),
        "apify": _apify_credits(),
    }
