"""MillionVerifier pre-SES email verification.

Flow: LeadSense → verify (cache or API) → only allowed results → AWS SES.

Defaults:
- Allowed results: ``ok`` only (configurable via MILLIONVERIFIER_ALLOWED_RESULTS)
- Cache: MILLIONVERIFIER_CACHE_DAYS (default 30)
- API failure / timeout: block this send attempt but do not suppress (retry later)
- Definitive bad result: suppress + mark campaign recipient ``invalid_email``
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import EmailLog, EmailVerification, Recipient, SuppressionEntry
from app.utils.helpers import utc_now

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Official MillionVerifier API v3 `result` values (resultcodes 1–6).
_KNOWN_API_RESULTS = frozenset(
    {"ok", "catch_all", "unknown", "error", "disposable", "invalid"}
)

# Results we treat as a final answer for gating (not a transient transport failure).
# Exclude API `error` — that means MV could not decide; defer send, do not suppress.
_DEFINITIVE_RESULTS = frozenset(
    {"ok", "catch_all", "unknown", "invalid", "disposable", "risky"}
)

# Internal status mapping used in diagnostics / logs (derived from API `result`).
_INTERNAL_STATUS = {
    "ok": "valid",
    "invalid": "invalid",
    "disposable": "invalid",
    "catch_all": "risky",
    "unknown": "unknown",
    "error": "error",
}


class MillionVerifierConfigError(RuntimeError):
    """Raised when MillionVerifier is enabled but misconfigured."""


class MillionVerifierAuthError(RuntimeError):
    """API key rejected (HTTP 401/403) — do not retry."""


class MillionVerifierRateLimitError(RuntimeError):
    """HTTP 429 — transient; may retry with backoff."""


class MillionVerifierUnavailableError(RuntimeError):
    """Network / timeout / 5xx — transient; may retry."""


def _as_utc(dt: datetime | None) -> datetime | None:
    """SQLite often returns naive datetimes; normalize before comparing."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def mask_email(email: str | None) -> str:
    """Mask local-part for logs (privacy). Never log API keys."""
    text = (email or "").strip()
    if "@" not in text:
        return "***"
    local, _, domain = text.partition("@")
    if not local:
        return f"***@{domain}"
    return f"{local[0]}***@{domain}"


def validate_millionverifier_config(settings: Settings | None = None) -> None:
    """Fail fast at startup when real verification is enabled without a key.

    Does not raise when verification is disabled or mock mode is on.
    Never logs or returns the API key.
    """
    cfg = settings or get_settings()
    if not cfg.millionverifier_enabled:
        logger.info("MillionVerifier disabled (MILLIONVERIFIER_ENABLED=false)")
        return
    if cfg.use_mock_millionverifier:
        logger.warning(
            "MillionVerifier MOCK MODE enabled — all emails treated as ok; "
            "set USE_MOCK_MILLIONVERIFIER=false for real verification (UAT/prod)"
        )
        return
    if not (cfg.millionverifier_api_key or "").strip():
        raise MillionVerifierConfigError(
            "MillionVerifier is enabled but MILLIONVERIFIER_API_KEY is not configured."
        )
    logger.info(
        "MillionVerifier enabled mock=false url=%s timeout=%ss max_retries=%s",
        (cfg.millionverifier_api_url or "").rstrip("/") + "/",
        cfg.millionverifier_timeout_seconds,
        cfg.millionverifier_max_retries,
    )


def millionverifier_diagnostic(settings: Settings | None = None, *, check_connectivity: bool = False) -> dict:
    """Safe diagnostic payload — never includes the API key."""
    cfg = settings or get_settings()
    key_set = bool((cfg.millionverifier_api_key or "").strip())
    out: dict = {
        "enabled": bool(cfg.millionverifier_enabled),
        "mock": bool(cfg.use_mock_millionverifier),
        "api_key_configured": key_set,
        "api_url": (cfg.millionverifier_api_url or "").rstrip("/") + "/",
        "timeout_seconds": int(cfg.millionverifier_timeout_seconds or 30),
        "max_retries": int(cfg.millionverifier_max_retries or 3),
        "allowed_results": cfg.millionverifier_allowed_results or "ok",
        "connectivity": "skipped",
    }
    if not check_connectivity:
        return out
    if not cfg.millionverifier_enabled:
        out["connectivity"] = "skipped"
        return out
    if cfg.use_mock_millionverifier:
        out["connectivity"] = "skipped_mock"
        return out
    if not key_set:
        out["connectivity"] = "failed"
        out["connectivity_detail"] = "api_key_missing"
        return out
    try:
        svc = MillionVerifierService(settings=cfg)
        svc.check_credits()
        out["connectivity"] = "ok"
    except MillionVerifierAuthError as exc:
        out["connectivity"] = "failed"
        out["connectivity_detail"] = "authentication_failed"
        out["error"] = str(exc)
    except Exception as exc:
        out["connectivity"] = "failed"
        out["connectivity_detail"] = "unreachable"
        out["error"] = str(exc)
    return out


@dataclass(frozen=True)
class VerificationGateResult:
    """Outcome of the pre-send verification gate."""

    allowed: bool
    definitive_reject: bool = False
    result: str | None = None
    detail: str | None = None
    from_cache: bool = False


class MillionVerifierService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def _allowed_results(self) -> set[str]:
        raw = self.settings.millionverifier_allowed_results or "ok"
        return {part.strip().lower() for part in raw.split(",") if part.strip()}

    def _normalize_email(self, email: str) -> str:
        return (email or "").strip().lower()

    def _cache_expiry(self):
        days = max(int(self.settings.millionverifier_cache_days or 30), 1)
        return utc_now() + timedelta(days=days)

    def _get_cached(self, db: Session, email: str) -> EmailVerification | None:
        row = (
            db.query(EmailVerification)
            .filter(EmailVerification.email == email)
            .first()
        )
        if not row:
            return None
        expires = _as_utc(row.expires_at)
        if expires is None or expires <= utc_now():
            return None
        return row

    def _upsert_cache(
        self,
        db: Session,
        *,
        email: str,
        result: str,
        resultcode: int | None,
        quality: str | None,
        source: str,
        raw: dict | None,
    ) -> EmailVerification:
        now = utc_now()
        row = (
            db.query(EmailVerification)
            .filter(EmailVerification.email == email)
            .first()
        )
        payload = json.dumps(raw) if raw is not None else None
        if row is None:
            row = EmailVerification(
                email=email,
                result=result,
                resultcode=resultcode,
                quality=quality,
                source=source,
                raw_response=payload,
                verified_at=now,
                expires_at=self._cache_expiry(),
            )
            db.add(row)
        else:
            row.result = result
            row.resultcode = resultcode
            row.quality = quality
            row.source = source
            row.raw_response = payload
            row.verified_at = now
            row.expires_at = self._cache_expiry()
        db.flush()
        return row

    def _http_timeout(self) -> httpx.Timeout:
        read = max(float(self.settings.millionverifier_timeout_seconds or 30), 2.0)
        # MV docs: timeout query param 2–60s; give the HTTP client a small buffer.
        return httpx.Timeout(connect=5.0, read=read + 2.0, write=5.0, pool=5.0)

    def _max_retries(self) -> int:
        return max(int(self.settings.millionverifier_max_retries or 0), 0)

    def _verify_url(self) -> str:
        return (self.settings.millionverifier_api_url or "").rstrip("/") + "/"

    def _credits_url(self) -> str:
        base = (self.settings.millionverifier_api_url or "").rstrip("/")
        # .../api/v3 → .../api/v3/credits
        return f"{base}/credits"

    def check_credits(self) -> dict:
        """Call credits endpoint to confirm key + network (no email verified)."""
        api_key = (self.settings.millionverifier_api_key or "").strip()
        if not api_key:
            raise MillionVerifierConfigError(
                "MillionVerifier is enabled but MILLIONVERIFIER_API_KEY is not configured."
            )
        url = self._credits_url()
        with httpx.Client(timeout=self._http_timeout()) as client:
            response = client.get(url, params={"api": api_key})
        if response.status_code in (401, 403):
            raise MillionVerifierAuthError("verification service authentication failed")
        if response.status_code == 429:
            raise MillionVerifierRateLimitError("verification service rate limited")
        if response.status_code >= 500:
            raise MillionVerifierUnavailableError(
                f"verification service unavailable (HTTP {response.status_code})"
            )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise MillionVerifierUnavailableError("unexpected verification response")
        return data

    def _parse_api_payload(self, data: object) -> dict:
        if not isinstance(data, dict):
            raise MillionVerifierUnavailableError("unexpected verification response")

        err = (data.get("error") or "").strip() if isinstance(data.get("error"), str) else ""
        raw_result = data.get("result")
        if err and not raw_result:
            raise MillionVerifierUnavailableError(f"MillionVerifier error: {err}")

        result = str(raw_result or "").strip().lower()
        if not result or result not in _KNOWN_API_RESULTS:
            raise MillionVerifierUnavailableError(
                f"unexpected verification response (result={raw_result!r})"
            )
        return data

    def _call_api_once(self, client: httpx.Client, email: str, *, attempt: int) -> dict:
        api_key = (self.settings.millionverifier_api_key or "").strip()
        if not api_key:
            raise MillionVerifierConfigError(
                "MillionVerifier is enabled but MILLIONVERIFIER_API_KEY is not configured."
            )

        timeout_param = int(max(float(self.settings.millionverifier_timeout_seconds or 30), 2))
        timeout_param = min(timeout_param, 60)
        url = self._verify_url()
        # Never log params — they include the API key.
        logger.info(
            "MillionVerifier request started email=%s attempt=%s",
            mask_email(email),
            attempt,
        )
        response = client.get(
            url,
            params={"api": api_key, "email": email, "timeout": timeout_param},
        )
        status = response.status_code
        if status in (401, 403):
            logger.warning(
                "MillionVerifier request failed status=%s email=%s (auth)",
                status,
                mask_email(email),
            )
            raise MillionVerifierAuthError("verification service authentication failed")
        if status == 429:
            logger.warning(
                "MillionVerifier request failed status=429 email=%s retry=%s",
                mask_email(email),
                attempt,
            )
            raise MillionVerifierRateLimitError("verification service rate limited")
        if status >= 500:
            logger.warning(
                "MillionVerifier request failed status=%s email=%s retry=%s",
                status,
                mask_email(email),
                attempt,
            )
            raise MillionVerifierUnavailableError(
                f"verification service unavailable (HTTP {status})"
            )
        if status >= 400:
            logger.warning(
                "MillionVerifier request failed status=%s email=%s",
                status,
                mask_email(email),
            )
            raise MillionVerifierUnavailableError(
                f"verification request failed (HTTP {status})"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise MillionVerifierUnavailableError("unexpected verification response") from exc

        parsed = self._parse_api_payload(data)
        result = str(parsed.get("result") or "").strip().lower()
        logger.info(
            "MillionVerifier request completed status=%s result=%s internal=%s email=%s",
            status,
            result,
            _INTERNAL_STATUS.get(result, "unknown"),
            mask_email(email),
        )
        return parsed

    def _call_api(self, email: str) -> dict:
        max_retries = self._max_retries()
        last_exc: Exception | None = None

        with httpx.Client(timeout=self._http_timeout()) as client:
            for attempt in range(max_retries + 1):
                try:
                    return self._call_api_once(client, email, attempt=attempt)
                except MillionVerifierAuthError:
                    raise
                except MillionVerifierConfigError:
                    raise
                except (MillionVerifierRateLimitError, MillionVerifierUnavailableError) as exc:
                    last_exc = exc
                except httpx.TimeoutException as exc:
                    last_exc = MillionVerifierUnavailableError("verification request timed out")
                    logger.warning(
                        "MillionVerifier request timed out email=%s retry=%s",
                        mask_email(email),
                        attempt,
                    )
                    last_exc.__cause__ = exc
                except httpx.TransportError as exc:
                    last_exc = MillionVerifierUnavailableError(
                        f"verification service unavailable: {exc.__class__.__name__}"
                    )
                    logger.warning(
                        "MillionVerifier network error email=%s retry=%s error=%s",
                        mask_email(email),
                        attempt,
                        exc.__class__.__name__,
                    )
                    last_exc.__cause__ = exc

                if attempt >= max_retries:
                    break
                # Exponential backoff; respect rate limits without hammering.
                delay = min(2**attempt, 8)
                logger.info(
                    "MillionVerifier retrying email=%s after=%ss attempt=%s",
                    mask_email(email),
                    delay,
                    attempt + 1,
                )
                time.sleep(delay)

        assert last_exc is not None
        raise last_exc

    def verify_email(self, db: Session, email: str) -> VerificationGateResult:
        """Verify (or serve cache). Does not mutate recipient/campaign rows."""
        if not self.settings.millionverifier_enabled:
            return VerificationGateResult(allowed=True, result="skipped", detail="verification disabled")

        normalized = self._normalize_email(email)
        if not normalized or not _EMAIL_RE.match(normalized):
            return VerificationGateResult(
                allowed=False,
                definitive_reject=True,
                result="invalid",
                detail="Malformed email address",
            )

        cached = self._get_cached(db, normalized)
        if cached is not None:
            allowed = cached.result.lower() in self._allowed_results()
            return VerificationGateResult(
                allowed=allowed,
                definitive_reject=cached.result.lower() in _DEFINITIVE_RESULTS and not allowed,
                result=cached.result,
                detail=f"Cached MillionVerifier result: {cached.result}",
                from_cache=True,
            )

        if self.settings.use_mock_millionverifier:
            self._upsert_cache(
                db,
                email=normalized,
                result="ok",
                resultcode=1,
                quality="good",
                source="mock",
                raw={"result": "ok", "resultcode": 1, "quality": "good", "mock": True},
            )
            return VerificationGateResult(
                allowed=True,
                result="ok",
                detail="Mock MillionVerifier (USE_MOCK_MILLIONVERIFIER=true)",
            )

        try:
            data = self._call_api(normalized)
        except MillionVerifierAuthError as exc:
            logger.warning(
                "MillionVerifier auth failure email=%s detail=%s",
                mask_email(normalized),
                exc,
            )
            return VerificationGateResult(
                allowed=False,
                definitive_reject=False,
                result="error",
                detail="verification service authentication failed",
            )
        except MillionVerifierConfigError as exc:
            logger.error("MillionVerifier misconfigured: %s", exc)
            return VerificationGateResult(
                allowed=False,
                definitive_reject=False,
                result="error",
                detail=str(exc),
            )
        except MillionVerifierRateLimitError as exc:
            logger.warning(
                "MillionVerifier rate limited email=%s",
                mask_email(normalized),
            )
            return VerificationGateResult(
                allowed=False,
                definitive_reject=False,
                result="error",
                detail=str(exc),
            )
        except Exception as exc:
            logger.warning(
                "MillionVerifier API failure email=%s error=%s",
                mask_email(normalized),
                exc,
            )
            return VerificationGateResult(
                allowed=False,
                definitive_reject=False,
                result="error",
                detail=f"verification service unavailable: {exc}",
            )

        result = str(data.get("result") or "").strip().lower()
        # Do not cache transient API `error` — allow a later retry to re-query.
        if result == "error":
            return VerificationGateResult(
                allowed=False,
                definitive_reject=False,
                result="error",
                detail="verification service returned error (will retry)",
            )

        resultcode = data.get("resultcode")
        try:
            resultcode_int = int(resultcode) if resultcode is not None else None
        except (TypeError, ValueError):
            resultcode_int = None
        quality = data.get("quality")
        quality_str = str(quality) if quality is not None else None

        self._upsert_cache(
            db,
            email=normalized,
            result=result,
            resultcode=resultcode_int,
            quality=quality_str,
            source="millionverifier",
            raw=data,
        )

        allowed = result in self._allowed_results()
        definitive = result in _DEFINITIVE_RESULTS
        return VerificationGateResult(
            allowed=allowed,
            definitive_reject=definitive and not allowed,
            result=result,
            detail=f"MillionVerifier result: {result}"
            + (f" (quality={quality_str})" if quality_str else ""),
        )

    def apply_rejection(
        self,
        db: Session,
        *,
        recipient: Recipient,
        campaign_id: int,
        campaign_recipient,
        gate: VerificationGateResult,
        sender_user_id: int | None = None,
    ) -> None:
        """Suppress + mark invalid_email for a definitive verification failure."""
        detail = gate.detail or f"MillionVerifier rejected: {gate.result}"
        recipient.is_suppressed = True
        recipient.suppression_reason = "email_verification_failed"

        db.add(
            SuppressionEntry(
                email=recipient.email,
                company=recipient.company,
                reason="email_verification_failed",
                campaign_id=campaign_id,
                recipient_id=recipient.id,
                detail=detail,
            )
        )
        campaign_recipient.status = "invalid_email"
        campaign_recipient.next_send_at = None
        db.add(
            EmailLog(
                campaign_id=campaign_id,
                recipient_id=recipient.id,
                status="invalid_email",
                error_message=detail,
                sender_user_id=sender_user_id,
            )
        )


def resolve_verification_status(
    *,
    email: str | None,
    suppression_reason: str | None,
    cache_row: EmailVerification | None,
    allowed_results: set[str] | None = None,
) -> tuple[str, str | None]:
    """Return (status, raw_result) for UI: verified | failed | unchecked."""
    allowed = allowed_results or {"ok"}
    if (suppression_reason or "") == "email_verification_failed":
        raw = cache_row.result if cache_row else "invalid"
        return "failed", raw

    if cache_row is not None:
        expires = _as_utc(cache_row.expires_at)
        if expires is not None and expires > utc_now():
            raw = (cache_row.result or "").strip().lower() or "unknown"
            if raw in allowed:
                return "verified", raw
            return "failed", raw

    return "unchecked", None


def verification_lookup(db: Session, emails: list[str]) -> dict[str, EmailVerification]:
    normalized = sorted({(e or "").strip().lower() for e in emails if (e or "").strip()})
    if not normalized:
        return {}
    rows = (
        db.query(EmailVerification)
        .filter(EmailVerification.email.in_(normalized))
        .all()
    )
    return {row.email: row for row in rows}


def attach_verification_fields(
    db: Session,
    items: list[dict],
    *,
    email_key: str = "email",
    suppression_key: str = "suppression_reason",
) -> list[dict]:
    """Mutate/enrich dict payloads with email_verification_status + result."""
    svc = MillionVerifierService()
    allowed = svc._allowed_results()
    lookup = verification_lookup(db, [item.get(email_key) or "" for item in items])
    for item in items:
        email = (item.get(email_key) or "").strip().lower()
        status, raw = resolve_verification_status(
            email=email,
            suppression_reason=item.get(suppression_key),
            cache_row=lookup.get(email),
            allowed_results=allowed,
        )
        item["email_verification_status"] = status
        item["email_verification_result"] = raw
    return items


def recipients_to_responses(db: Session, recipients: list[Recipient]) -> list:
    """Build RecipientResponse list with verification fields populated."""
    from app.schemas.schemas import RecipientResponse

    lookup = verification_lookup(db, [r.email for r in recipients])
    allowed = MillionVerifierService()._allowed_results()
    out = []
    for recipient in recipients:
        payload = RecipientResponse.model_validate(recipient)
        status, raw = resolve_verification_status(
            email=recipient.email,
            suppression_reason=recipient.suppression_reason,
            cache_row=lookup.get((recipient.email or "").strip().lower()),
            allowed_results=allowed,
        )
        payload.email_verification_status = status
        payload.email_verification_result = raw
        out.append(payload)
    return out


millionverifier_service = MillionVerifierService()
