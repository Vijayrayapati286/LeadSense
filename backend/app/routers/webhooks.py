"""Delivery-event webhook routes.

`/simulate-event` is dev-only (gated behind settings.debug) and is what the
suppression/tracking logic has been tested against so far.

`/ses-events` is the real, public, internet-facing listener AWS SNS calls in
production for bounce/complaint notifications.

`/ses-inbound` receives SNS notifications for SES inbound receiving (S3 drop
of raw MIME) and runs OOO / reply classification — separate from bounce SNS
so existing bounce wiring is unchanged.
"""

import base64
import json
import logging
import re

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database.connection import get_db
from app.middleware.auth import get_current_user
from app.models import User
from app.schemas.schemas import MessageResponse, SimulateEventRequest, SimulateInboundRequest
from app.services import event_service, inbound_email_service
from app.services.sns_verify import verify_sns_signature

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["Webhooks"])
settings = get_settings()

_SMTP_CODE_RE = re.compile(r"\d{3}[\s-]\d\.\d\.\d")


@router.post("/simulate-event", response_model=MessageResponse)
def simulate_event(
    data: SimulateEventRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Dev-only: manually trigger a bounce/complaint/reply/OOO event."""
    if not settings.debug:
        raise HTTPException(status_code=404, detail="Not found")

    if data.event_type == "bounce":
        event_service.handle_bounce(
            db, data.email, bounce_type=data.bounce_type, campaign_id=data.campaign_id,
            detail=data.detail, smtp_code=data.smtp_code,
        )
    elif data.event_type == "complaint":
        event_service.handle_complaint(
            db, data.email, campaign_id=data.campaign_id, detail=data.detail
        )
    elif data.event_type == "reply":
        event_service.handle_reply(db, data.email, campaign_id=data.campaign_id)
    elif data.event_type == "out_of_office":
        event_service.handle_out_of_office(db, data.email, campaign_id=data.campaign_id)

    return MessageResponse(message=f"Simulated {data.event_type} event for {data.email}")


@router.post("/simulate-inbound", response_model=MessageResponse)
def simulate_inbound(
    data: SimulateInboundRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Dev-only: inject a raw MIME email (base64) through the inbound processor."""
    if not settings.debug:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        raw = base64.b64decode(data.raw_email_base64, validate=False)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid base64: {exc}") from exc
    result = inbound_email_service.process_raw_inbound(db, raw)
    return MessageResponse(
        message=(
            f"Inbound {result.classification} duplicate={result.duplicate} "
            f"matched={result.matched} campaign_id={result.campaign_id}"
        )
    )


def _extract_campaign_id(ses_event: dict) -> int | None:
    """SES can echo custom message tags (set via a configuration set at send
    time) back on the notification. We don't set any today, so this is
    forward-compatible plumbing — it returns None until send-time tagging is
    added, which is fine since every handler already treats campaign_id as
    optional."""
    tags = ses_event.get("mail", {}).get("tags", {})
    values = tags.get("campaign_id")
    if values and str(values[0]).isdigit():
        return int(values[0])
    return None


def _process_bounce(db: Session, ses_event: dict) -> None:
    bounce = ses_event.get("bounce", {})
    bounce_type = bounce.get("bounceType", "Permanent")
    campaign_id = _extract_campaign_id(ses_event)

    for recipient in bounce.get("bouncedRecipients", []):
        email = recipient.get("emailAddress")
        if not email:
            continue
        diagnostic = recipient.get("diagnosticCode", "")
        smtp_match = _SMTP_CODE_RE.search(diagnostic)
        event_service.handle_bounce(
            db, email,
            bounce_type=bounce_type,
            campaign_id=campaign_id,
            detail=diagnostic or None,
            smtp_code=smtp_match.group(0) if smtp_match else None,
        )


def _process_complaint(db: Session, ses_event: dict) -> None:
    complaint = ses_event.get("complaint", {})
    campaign_id = _extract_campaign_id(ses_event)
    feedback_type = complaint.get("complaintFeedbackType")

    for recipient in complaint.get("complainedRecipients", []):
        email = recipient.get("emailAddress")
        if not email:
            continue
        event_service.handle_complaint(db, email, campaign_id=campaign_id, detail=feedback_type)


def _process_ses_notification(db: Session, ses_event: dict) -> None:
    notification_type = ses_event.get("notificationType") or ses_event.get("eventType")
    if notification_type == "Bounce":
        _process_bounce(db, ses_event)
    elif notification_type == "Complaint":
        _process_complaint(db, ses_event)
    else:
        # Delivery, Open, Click, etc. — nothing to suppress, safely ignored.
        logger.info("Ignoring SES notification type: %s", notification_type)


@router.post("/ses-events")
async def ses_events(request: Request, db: Session = Depends(get_db)):
    """Public endpoint AWS SNS POSTs to. Not authenticated with our normal
    Bearer tokens (AWS can't supply one) — authenticity is instead verified
    via the SNS message signature, which is mandatory, not optional."""
    raw_body = await request.body()
    try:
        # SNS sends Content-Type: text/plain even though the body is JSON,
        # so we parse it manually rather than relying on FastAPI's body model.
        message = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    if not verify_sns_signature(message):
        raise HTTPException(status_code=403, detail="Invalid SNS signature")

    message_type = message.get("Type")

    if message_type in ("SubscriptionConfirmation", "UnsubscribeConfirmation"):
        subscribe_url = message.get("SubscribeURL")
        if subscribe_url:
            try:
                httpx.get(subscribe_url, timeout=5.0)
                logger.info("Confirmed SNS %s", message_type)
            except Exception:
                logger.exception("Failed to confirm SNS %s", message_type)
        return {"status": "ok"}

    if message_type == "Notification":
        try:
            ses_event = json.loads(message.get("Message", "{}"))
        except json.JSONDecodeError:
            logger.warning("SNS Notification had a non-JSON Message body")
            return {"status": "ignored"}
        _process_ses_notification(db, ses_event)
        return {"status": "ok"}

    logger.info("Ignoring unrecognized SNS message type: %s", message_type)
    return {"status": "ignored"}


@router.post("/ses-inbound")
async def ses_inbound(request: Request, db: Session = Depends(get_db)):
    """SNS listener for SES inbound receiving (receipt rule → S3 → SNS).

    Signature-verified like /ses-events. Downloads raw MIME from S3 and runs
    the OOO/reply classifier. Does not replace bounce handling.
    """
    raw_body = await request.body()
    try:
        message = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    if not verify_sns_signature(message):
        raise HTTPException(status_code=403, detail="Invalid SNS signature")

    message_type = message.get("Type")

    if message_type in ("SubscriptionConfirmation", "UnsubscribeConfirmation"):
        subscribe_url = message.get("SubscribeURL")
        if subscribe_url:
            try:
                httpx.get(subscribe_url, timeout=5.0)
                logger.info("Confirmed SNS inbound %s", message_type)
            except Exception:
                logger.exception("Failed to confirm SNS inbound %s", message_type)
        return {"status": "ok"}

    if message_type != "Notification":
        return {"status": "ignored"}

    try:
        payload = json.loads(message.get("Message", "{}"))
    except json.JSONDecodeError:
        logger.warning("Inbound SNS Notification had a non-JSON Message body")
        return {"status": "ignored"}

    location = inbound_email_service.extract_s3_location_from_ses_inbound_sns(payload)
    if not location:
        # Some SES SNS actions embed content; try content as raw if present (rare).
        content = payload.get("content")
        if content:
            result = inbound_email_service.process_raw_inbound(db, content.encode("utf-8"))
            return {
                "status": "ok",
                "classification": result.classification,
                "duplicate": result.duplicate,
            }
        logger.info("Inbound SNS payload had no S3 location — ignored")
        return {"status": "ignored"}

    bucket, key = location
    configured = (settings.ses_inbound_s3_bucket or "").strip()
    if configured and bucket != configured:
        logger.warning("Rejecting inbound S3 bucket %s (expected %s)", bucket, configured)
        raise HTTPException(status_code=403, detail="Unexpected inbound bucket")

    try:
        result = inbound_email_service.process_s3_notification(db, bucket, key)
    except Exception:
        logger.exception("Failed processing inbound s3://%s/%s", bucket, key)
        raise HTTPException(status_code=500, detail="Inbound processing failed")

    return {
        "status": "ok",
        "classification": result.classification,
        "matched": result.matched,
        "duplicate": result.duplicate,
        "campaign_id": result.campaign_id,
    }
