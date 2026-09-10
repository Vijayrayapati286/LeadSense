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
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import EmailLog, EmailVerification, Recipient, SuppressionEntry
from app.utils.helpers import utc_now

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# MillionVerifier result strings we treat as a final answer (not a transport error).
_DEFINITIVE_RESULTS = frozenset(
    {"ok", "catch_all", "unknown", "invalid", "disposable", "risky"}
)


def _as_utc(dt: datetime | None) -> datetime | None:
    """SQLite often returns naive datetimes; normalize before comparing."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@dataclass(frozen=True)
class VerificationGateResult:
    """Outcome of the pre-send verification gate."""

    allowed: bool
    definitive_reject: bool = False
    result: str | None = None
    detail: str | None = None
    from_cache: bool = False


class MillionVerifierService:
    def __init__(self) -> None:
        self.settings = get_settings()

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

    def _call_api(self, email: str) -> dict:
        api_key = (self.settings.millionverifier_api_key or "").strip()
        if not api_key:
            raise RuntimeError("MILLIONVERIFIER_API_KEY is not configured")

        timeout = max(float(self.settings.millionverifier_timeout_seconds or 10), 1.0)
        url = (self.settings.millionverifier_api_url or "").rstrip("/") + "/"
        params = {"api": api_key, "email": email, "timeout": int(timeout)}

        with httpx.Client(timeout=timeout + 2.0) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

        if not isinstance(data, dict):
            raise RuntimeError("MillionVerifier returned a non-object response")

        # API-level error payload (still HTTP 200 in some cases).
        err = (data.get("error") or "").strip()
        if err and not data.get("result"):
            raise RuntimeError(f"MillionVerifier error: {err}")
        return data

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
        except Exception as exc:
            logger.warning("MillionVerifier API failure for %s: %s", normalized, exc)
            return VerificationGateResult(
                allowed=False,
                definitive_reject=False,
                result="error",
                detail=f"MillionVerifier unavailable: {exc}",
            )

        result = str(data.get("result") or "unknown").strip().lower() or "unknown"
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
