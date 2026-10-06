"""Shared handlers for delivery events (bounce, complaint, reply, OOO).

Called by `/webhooks/simulate-event`, `/webhooks/ses-events` (bounce/complaint),
and `/webhooks/ses-inbound` (reply/OOO classification).
"""

import logging

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import CampaignRecipient, Recipient
from app.services.app_settings_service import AppSettingsService
from app.services.suppression_service import SuppressionService
from app.utils.helpers import utc_now

logger = logging.getLogger(__name__)
suppression_service = SuppressionService()
app_settings_service = AppSettingsService()


# Statuses that cancel any pending follow-up when applied.
_CANCEL_FOLLOWUP_STATUSES = frozenset({"replied", "bounced", "suppressed", "invalid_email", "risky"})


def _mark_campaign_recipients(
    db: Session, email: str, campaign_id: int | None, status: str, timestamp_field: str
) -> list[int]:
    query = (
        db.query(CampaignRecipient)
        .join(Recipient, CampaignRecipient.recipient_id == Recipient.id)
        .filter(Recipient.email == email)
    )
    if campaign_id is not None:
        query = query.filter(CampaignRecipient.campaign_id == campaign_id)

    now = utc_now()
    updated: list[int] = []
    for cr in query.all():
        cr.status = status
        setattr(cr, timestamp_field, now)
        # Cancel pending follow-ups so UI and next_send_at stay consistent.
        # Scheduler also re-checks status before send; clearing is belt-and-suspenders.
        if status in _CANCEL_FOLLOWUP_STATUSES:
            cr.next_send_at = None
        updated.append(cr.campaign_id)
    db.commit()
    return updated


def _maybe_publish_bounce_alerts(db: Session, campaign_ids: list[int]) -> None:
    """Alert from recipient_stats counts after a bounce is already recorded.

    SNS and stats failures are logged and swallowed so bounce handling still
    commits.
    """
    if not campaign_ids:
        return
    try:
        from app.models import Campaign
        from app.services.campaign_service import CampaignService
        from app.services.sns_service import bounce_rate_from_recipient_stats, send_bounce_alert

        service = CampaignService()
        seen: set[int] = set()
        for campaign_id in campaign_ids:
            if campaign_id in seen:
                continue
            seen.add(campaign_id)
            campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
            if campaign is None:
                logger.info("Bounce alert skipped: campaign %s not found", campaign_id)
                continue
            stats = service.recipient_stats(db, campaign.id)
            rate = bounce_rate_from_recipient_stats(stats)
            send_bounce_alert(rate, campaign.campaign_name, campaign_id=campaign.id)
    except Exception:
        logger.exception("Bounce-rate alert failed; bounce processing continues")


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
        updated = _mark_campaign_recipients(db, email, campaign_id, "bounced", "bounced_at")
        _maybe_publish_bounce_alerts(db, updated)
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

    updated = _mark_campaign_recipients(db, email, campaign_id, "bounced", "bounced_at")
    _maybe_publish_bounce_alerts(db, updated)


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
    but does NOT blacklist the address — it's a good lead, not a bad one."""
    _mark_campaign_recipients(db, email, campaign_id, "replied", "replied_at")


def handle_out_of_office(db: Session, email: str, campaign_id: int | None = None) -> None:
    """Mark recipient out_of_office. Does not suppress.

    Follow-ups stop only when OOO_STOPS_FOLLOWUPS=true; otherwise status is
    tracked and the scheduler continues unless the product enables that flag.
    """
    query = (
        db.query(CampaignRecipient)
        .join(Recipient, CampaignRecipient.recipient_id == Recipient.id)
        .filter(Recipient.email == email)
    )
    if campaign_id is not None:
        query = query.filter(CampaignRecipient.campaign_id == campaign_id)

    rows = query.all()
    if not rows:
        logger.info("OOO for unknown campaign recipient %s (campaign_id=%s)", email, campaign_id)
        return

    now = utc_now()
    stop_followups = get_settings().ooo_stops_followups
    for cr in rows:
        # Do not overwrite a human reply with OOO.
        if cr.status == "replied":
            continue
        cr.status = "out_of_office"
        cr.ooo_at = now
        if stop_followups:
            cr.next_send_at = None
    db.commit()
