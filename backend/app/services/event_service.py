"""Shared handlers for delivery events (bounce, complaint, reply).

These are called today only by the dev-only `/webhooks/simulate-event` endpoint
(see backend/app/routers/webhooks.py). When real AWS SES/SNS wiring is added
later, the SNS notification parser should call these same functions so the
suppression/tracking behavior is identical in both paths.
"""

import logging

from sqlalchemy.orm import Session

from app.models import CampaignRecipient, Recipient
from app.services.app_settings_service import AppSettingsService
from app.services.suppression_service import SuppressionService
from app.utils.helpers import utc_now

logger = logging.getLogger(__name__)
suppression_service = SuppressionService()
app_settings_service = AppSettingsService()


def _mark_campaign_recipients(
    db: Session, email: str, campaign_id: int | None, status: str, timestamp_field: str
) -> None:
    query = (
        db.query(CampaignRecipient)
        .join(Recipient, CampaignRecipient.recipient_id == Recipient.id)
        .filter(Recipient.email == email)
    )
    if campaign_id is not None:
        query = query.filter(CampaignRecipient.campaign_id == campaign_id)

    for cr in query.all():
        cr.status = status
        setattr(cr, timestamp_field, utc_now())
    db.commit()


def handle_bounce(
    db: Session,
    email: str,
    bounce_type: str = "Permanent",
    campaign_id: int | None = None,
    detail: str | None = None,
    smtp_code: str | None = None,
) -> None:
    """Hard (Permanent) bounces — invalid/non-existent mailbox, domain doesn't
    exist — are suppressed immediately, since retrying can only hurt sender
    reputation. Soft (Transient) bounces — full mailbox, temporary server
    error — are retried: each occurrence increments a per-recipient counter,
    and only once that count exceeds `settings.soft_bounce_threshold` does
    the address get suppressed too (as `soft_bounce_threshold_exceeded`)."""
    recipients = db.query(Recipient).filter(Recipient.email == email).all()

    if bounce_type != "Permanent":
        if not recipients:
            logger.info("Transient bounce for unknown recipient %s — nothing to track", email)
            return

        for recipient in recipients:
            recipient.soft_bounce_count += 1
        db.commit()

        threshold = app_settings_service.get(db).soft_bounce_threshold
        if recipients[0].soft_bounce_count <= threshold:
            logger.info(
                "Transient bounce %d/%d for %s — retrying",
                recipients[0].soft_bounce_count, threshold, email,
            )
            return

        logger.info(
            "Soft bounce threshold exceeded for %s (%d > %d) — suppressing",
            email, recipients[0].soft_bounce_count, threshold,
        )
        for recipient in recipients:
            suppression_service.add(
                db, recipient, reason="soft_bounce_threshold_exceeded",
                detail=detail, campaign_id=campaign_id,
                bounce_type=bounce_type, smtp_code=smtp_code,
            )
        _mark_campaign_recipients(db, email, campaign_id, "bounced", "bounced_at")
        return

    if recipients:
        for recipient in recipients:
            suppression_service.add(
                db, recipient, reason="hard_bounce", detail=detail, campaign_id=campaign_id,
                bounce_type=bounce_type, smtp_code=smtp_code,
            )
    else:
        suppression_service.add_by_email(
            db, email, reason="hard_bounce", detail=detail, campaign_id=campaign_id,
            bounce_type=bounce_type, smtp_code=smtp_code,
        )

    _mark_campaign_recipients(db, email, campaign_id, "bounced", "bounced_at")


def handle_complaint(
    db: Session, email: str, campaign_id: int | None = None, detail: str | None = None
) -> None:
    recipients = db.query(Recipient).filter(Recipient.email == email).all()
    if recipients:
        for recipient in recipients:
            suppression_service.add(
                db, recipient, reason="complaint", detail=detail, campaign_id=campaign_id
            )
    else:
        suppression_service.add_by_email(
            db, email, reason="complaint", detail=detail, campaign_id=campaign_id
        )

    _mark_campaign_recipients(db, email, campaign_id, "suppressed", "bounced_at")


def handle_reply(db: Session, email: str, campaign_id: int | None = None) -> None:
    """A reply stops automated follow-ups for this recipient in this campaign,
    but does NOT blacklist the address — it's a good lead, not a bad one.

    Also auto-tags the recipient "Hot" — always overriding any earlier tag
    (manual or automatic), since an actual reply is the strongest engagement
    signal available. This is what lets Engagement Studio stages
    automatically exclude responders (see scheduler_service.py's
    skip_if_tagged handling) without a rep having to tag them by hand."""
    _mark_campaign_recipients(db, email, campaign_id, "replied", "replied_at")
    for recipient in db.query(Recipient).filter(Recipient.email == email).all():
        recipient.response_tag = "Hot"
    db.commit()
