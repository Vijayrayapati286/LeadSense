"""Parse SES inbound MIME, classify, match campaign recipients, apply handlers.

Does not alter outbound SES sending. Inbound path:
  SES receipt rule → S3 (raw) → SNS notify → /api/webhooks/ses-inbound
  or local simulate with raw MIME bytes.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from email import message_from_bytes
from email.header import decode_header, make_header
from email.message import Message
from email.utils import parseaddr

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import CampaignRecipient, EmailLog, InboundEmail, Recipient
from app.services import event_service
from app.services.ooo_classifier import (
    CLASS_BOUNCE,
    CLASS_NORMAL_REPLY,
    CLASS_OTHER,
    CLASS_OUT_OF_OFFICE,
    classify_inbound_email,
)
from app.utils.helpers import utc_now

logger = logging.getLogger(__name__)
settings = get_settings()

_MSG_ID_RE = re.compile(r"<[^>]+>|[^\s<>]+")


@dataclass
class ParsedInbound:
    message: Message
    from_email: str
    to_email: str
    subject: str
    message_id: str
    in_reply_to: str
    references: str
    body_text: str
    body_html: str


@dataclass
class ProcessResult:
    classification: str
    inbound_message_id: str
    matched: bool
    campaign_id: int | None
    recipient_email: str | None
    detail: str
    duplicate: bool = False


def _decode_header_value(raw: str | None) -> str:
    if not raw:
        return ""
    try:
        return str(make_header(decode_header(raw)))
    except Exception:
        return raw


def _extract_address(raw: str | None) -> str:
    _name, addr = parseaddr(raw or "")
    return (addr or "").strip().lower()


def _normalize_msg_id(value: str | None) -> str:
    if not value:
        return ""
    value = value.strip()
    if value.startswith("<") and value.endswith(">"):
        return value.lower()
    return f"<{value}>".lower() if value else ""


def _msg_id_candidates(header_value: str | None) -> list[str]:
    if not header_value:
        return []
    found = []
    for match in _MSG_ID_RE.findall(header_value):
        norm = _normalize_msg_id(match)
        if norm and norm not in found:
            found.append(norm)
    return found


def _walk_body(msg: Message) -> tuple[str, str]:
    text_parts: list[str] = []
    html_parts: list[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "").lower()
            if "attachment" in disp:
                continue
            try:
                payload = part.get_payload(decode=True)
            except Exception:
                continue
            if payload is None:
                continue
            charset = part.get_content_charset() or "utf-8"
            try:
                decoded = payload.decode(charset, errors="replace")
            except Exception:
                decoded = payload.decode("utf-8", errors="replace")
            if ctype == "text/plain":
                text_parts.append(decoded)
            elif ctype == "text/html":
                html_parts.append(decoded)
    else:
        try:
            payload = msg.get_payload(decode=True)
        except Exception:
            payload = None
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            try:
                decoded = payload.decode(charset, errors="replace")
            except Exception:
                decoded = payload.decode("utf-8", errors="replace")
            if msg.get_content_type() == "text/html":
                html_parts.append(decoded)
            else:
                text_parts.append(decoded)
    return ("\n".join(text_parts), "\n".join(html_parts))


def parse_raw_email(raw: bytes) -> ParsedInbound:
    if not raw:
        raise ValueError("Empty email payload")
    try:
        msg = message_from_bytes(raw)
    except Exception as exc:
        raise ValueError(f"Malformed email: {exc}") from exc

    body_text, body_html = _walk_body(msg)
    return ParsedInbound(
        message=msg,
        from_email=_extract_address(msg.get("From")),
        to_email=_extract_address(msg.get("To")),
        subject=_decode_header_value(msg.get("Subject")),
        message_id=_normalize_msg_id(msg.get("Message-ID") or msg.get("Message-Id")),
        in_reply_to=_normalize_msg_id(msg.get("In-Reply-To")),
        references=msg.get("References") or "",
        body_text=body_text,
        body_html=body_html,
    )


def _idempotency_key(parsed: ParsedInbound, s3_key: str | None, raw: bytes) -> str:
    if parsed.message_id:
        return parsed.message_id
    if s3_key:
        return f"s3:{s3_key}"
    digest = hashlib.sha256(raw).hexdigest()[:40]
    return f"hash:{digest}"


def _match_campaign_recipient(
    db: Session, parsed: ParsedInbound
) -> tuple[CampaignRecipient | None, EmailLog | None, str]:
    """Find the campaign recipient that generated this inbound mail.

    Prefer Message-ID threading; fall back to latest sent row for from_email
    in a single campaign when unambiguous.
    """
    ref_ids = _msg_id_candidates(parsed.in_reply_to)
    ref_ids.extend(_msg_id_candidates(parsed.references))
    # Dedupe preserving order
    seen: set[str] = set()
    ordered_ids: list[str] = []
    for mid in ref_ids:
        if mid not in seen:
            seen.add(mid)
            ordered_ids.append(mid)

    if ordered_ids:
        # Match against stored MIME Message-ID (with or without brackets).
        variants: list[str] = []
        for mid in ordered_ids:
            variants.append(mid)
            bare = mid.strip("<>")
            variants.append(bare)
            variants.append(f"<{bare}>")
        log = (
            db.query(EmailLog)
            .filter(EmailLog.message_id.in_(variants), EmailLog.status == "sent")
            .order_by(EmailLog.sent_at.desc())
            .first()
        )
        if log:
            cr = (
                db.query(CampaignRecipient)
                .filter(
                    CampaignRecipient.campaign_id == log.campaign_id,
                    CampaignRecipient.recipient_id == log.recipient_id,
                )
                .first()
            )
            return cr, log, "message_id_match"

    if not parsed.from_email:
        return None, None, "no_from_email"

    recipients = db.query(Recipient).filter(Recipient.email == parsed.from_email).all()
    if not recipients:
        return None, None, "unknown_sender"

    recipient_ids = [r.id for r in recipients]
    # Active / recently contacted rows only — avoid marking unrelated old campaigns.
    candidates = (
        db.query(CampaignRecipient)
        .filter(
            CampaignRecipient.recipient_id.in_(recipient_ids),
            CampaignRecipient.status.in_(
                ["sent", "queued", "delivered", "opened", "clicked", "out_of_office"]
            ),
        )
        .order_by(CampaignRecipient.last_sent_at.desc())
        .all()
    )
    if not candidates:
        # Broader fallback: any row for this email with a last_sent_at
        candidates = (
            db.query(CampaignRecipient)
            .filter(
                CampaignRecipient.recipient_id.in_(recipient_ids),
                CampaignRecipient.last_sent_at.isnot(None),
            )
            .order_by(CampaignRecipient.last_sent_at.desc())
            .all()
        )

    if not candidates:
        return None, None, "no_campaign_recipient"

    # Same email in multiple campaigns: only auto-match when a single campaign
    # has the most recent send (strict). If multiple share the same last_sent_at
    # campaign scope, pick the single most recently sent row — one row only.
    best = candidates[0]
    # If two different campaigns appear equally recent, require message-id (already failed).
    other_campaigns = {c.campaign_id for c in candidates[:5]}
    if len(other_campaigns) > 1:
        # Still bind to the single most recent send (deterministic) but note ambiguity.
        return best, None, "latest_send_among_multiple_campaigns"

    return best, None, "latest_send_match"


def _download_s3_object(bucket: str, key: str) -> bytes:
    """Fetch raw MIME from the inbound bucket (or mock store)."""
    from app.storage.s3_service import S3Service
    from app.storage.exceptions import S3StorageError

    svc = S3Service()
    # Temporarily read from inbound bucket when configured.
    original = svc.settings.s3_bucket_name
    try:
        # Settings is a pydantic model — mutate via object.__setattr__ unsafe;
        # instead use boto3 / mock path directly when bucket differs.
        if svc.use_mock:
            # Mock path is key-based under outputs/s3_mock/; prefix with bucket folder.
            mock_key = f"{bucket}/{key}" if bucket else key
            return svc.download_bytes(key=mock_key)

        import boto3

        region = svc.settings.aws_region or "us-east-1"
        kwargs: dict = {"region_name": region}
        access = (svc.settings.aws_access_key_id or "").strip()
        secret = (svc.settings.aws_secret_access_key or "").strip()
        if access and secret:
            kwargs["aws_access_key_id"] = access
            kwargs["aws_secret_access_key"] = secret
        client = boto3.client("s3", **kwargs)
        resp = client.get_object(Bucket=bucket, Key=key)
        return resp["Body"].read()
    except S3StorageError:
        raise
    except Exception as exc:
        raise RuntimeError(f"Failed to download s3://{bucket}/{key}: {exc}") from exc
    finally:
        _ = original


def process_raw_inbound(
    db: Session,
    raw: bytes,
    *,
    s3_bucket: str | None = None,
    s3_key: str | None = None,
) -> ProcessResult:
    """Parse, classify, match, and apply side effects. Idempotent on inbound Message-ID."""
    if not raw:
        idem = f"s3:{s3_key}" if s3_key else f"hash:{hashlib.sha256(b'').hexdigest()[:40]}"
        existing = db.query(InboundEmail).filter(InboundEmail.inbound_message_id == idem).first()
        if existing:
            return ProcessResult(
                classification=existing.classification,
                inbound_message_id=idem,
                matched=False,
                campaign_id=existing.campaign_id,
                recipient_email=existing.from_email,
                detail=existing.detail or "duplicate",
                duplicate=True,
            )
        row = InboundEmail(
            inbound_message_id=idem,
            classification=CLASS_OTHER,
            detail="malformed:empty",
            s3_bucket=s3_bucket,
            s3_key=s3_key,
            processed_at=utc_now(),
        )
        db.add(row)
        db.commit()
        return ProcessResult(
            classification=CLASS_OTHER,
            inbound_message_id=idem,
            matched=False,
            campaign_id=None,
            recipient_email=None,
            detail="empty payload",
        )

    try:
        parsed = parse_raw_email(raw)
    except ValueError as exc:
        idem = f"s3:{s3_key}" if s3_key else f"hash:{hashlib.sha256(raw).hexdigest()[:40]}"
        existing = db.query(InboundEmail).filter(InboundEmail.inbound_message_id == idem).first()
        if existing:
            return ProcessResult(
                classification=existing.classification,
                inbound_message_id=idem,
                matched=False,
                campaign_id=existing.campaign_id,
                recipient_email=existing.from_email,
                detail=existing.detail or "duplicate",
                duplicate=True,
            )
        row = InboundEmail(
            inbound_message_id=idem,
            classification=CLASS_OTHER,
            detail=f"malformed:{exc}",
            s3_bucket=s3_bucket,
            s3_key=s3_key,
            processed_at=utc_now(),
        )
        db.add(row)
        db.commit()
        return ProcessResult(
            classification=CLASS_OTHER,
            inbound_message_id=idem,
            matched=False,
            campaign_id=None,
            recipient_email=None,
            detail=str(exc),
        )

    idem = _idempotency_key(parsed, s3_key, raw)
    existing = db.query(InboundEmail).filter(InboundEmail.inbound_message_id == idem).first()
    if existing:
        return ProcessResult(
            classification=existing.classification,
            inbound_message_id=idem,
            matched=existing.campaign_recipient_id is not None,
            campaign_id=existing.campaign_id,
            recipient_email=existing.from_email,
            detail=existing.detail or "duplicate",
            duplicate=True,
        )

    classification = classify_inbound_email(
        parsed.message,
        body_text=parsed.body_text,
        from_email=parsed.from_email,
    )

    cr, _log, match_reason = _match_campaign_recipient(db, parsed)
    campaign_id = cr.campaign_id if cr else None
    recipient_id = cr.recipient_id if cr else None
    cr_id = cr.id if cr else None
    recipient_email = parsed.from_email or None

    detail = f"{classification.reason}; match={match_reason}"

    row = InboundEmail(
        inbound_message_id=idem,
        classification=classification.classification,
        from_email=parsed.from_email or None,
        to_email=parsed.to_email or None,
        subject=(parsed.subject or "")[:500] or None,
        in_reply_to=parsed.in_reply_to or None,
        references_header=(parsed.references or "")[:4000] or None,
        s3_bucket=s3_bucket,
        s3_key=s3_key,
        campaign_id=campaign_id,
        recipient_id=recipient_id,
        campaign_recipient_id=cr_id,
        processed_at=utc_now(),
        detail=detail,
    )
    db.add(row)
    db.commit()

    if cr is None:
        return ProcessResult(
            classification=classification.classification,
            inbound_message_id=idem,
            matched=False,
            campaign_id=None,
            recipient_email=recipient_email,
            detail=detail,
        )

    email = parsed.from_email
    if classification.classification == CLASS_OUT_OF_OFFICE:
        event_service.handle_out_of_office(db, email, campaign_id=campaign_id)
    elif classification.classification == CLASS_NORMAL_REPLY:
        event_service.handle_reply(db, email, campaign_id=campaign_id)
    elif classification.classification == CLASS_BOUNCE:
        # Prefer SES bounce SNS for suppression; inbound DSN is secondary.
        event_service.handle_bounce(
            db, email, bounce_type="Permanent", campaign_id=campaign_id, detail="inbound_dsn"
        )
    # CLASS_OTHER: record only

    return ProcessResult(
        classification=classification.classification,
        inbound_message_id=idem,
        matched=True,
        campaign_id=campaign_id,
        recipient_email=recipient_email,
        detail=detail,
    )


def process_s3_notification(db: Session, bucket: str, key: str) -> ProcessResult:
    prefix = (settings.ses_inbound_s3_prefix or "").strip()
    if prefix and not key.startswith(prefix.lstrip("/")):
        # Still allow exact configured bucket objects; log soft skip only when prefix set.
        logger.info("Inbound key %s does not match prefix %s — processing anyway", key, prefix)
    raw = _download_s3_object(bucket, key)
    return process_raw_inbound(db, raw, s3_bucket=bucket, s3_key=key)


def extract_s3_location_from_ses_inbound_sns(message: dict) -> tuple[str, str] | None:
    """Parse SES receipt / S3 notify payload for (bucket, key)."""
    # SES receipt rule SNS action (JSON notification)
    receipt = message.get("receipt") or {}
    action = receipt.get("action") or {}
    if action.get("type") == "S3" or action.get("bucketName"):
        bucket = action.get("bucketName") or message.get("bucket")
        key = action.get("objectKey") or message.get("objectKey")
        if bucket and key:
            return bucket, key

    # S3 event notification wrapped in SNS
    records = message.get("Records") or []
    for rec in records:
        s3 = rec.get("s3") or {}
        bucket = (s3.get("bucket") or {}).get("name")
        key = (s3.get("object") or {}).get("key")
        if bucket and key:
            from urllib.parse import unquote_plus

            return bucket, unquote_plus(key)

    mail = message.get("mail") or {}
    # Some custom publishers put bucket/key at top level
    bucket = message.get("bucket") or message.get("s3Bucket")
    key = message.get("key") or message.get("s3Key") or message.get("objectKey")
    if bucket and key:
        return bucket, key

    _ = mail
    return None
