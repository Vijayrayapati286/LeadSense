"""Email and in-app bounce notices for the user who sent the message.

Lookup is by the SES message id stored on email_logs at send time. The
recipient of the notice is that log's sender_user_id, loaded from users.
Nothing here is hardcoded, and a failure never rolls back bounce processing.
"""

from __future__ import annotations

import html
import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Campaign, EmailLog, User, UserNotification
from app.services.ses_service import SESService
from app.utils.helpers import utc_now

logger = logging.getLogger(__name__)
_ses = SESService()


def notify_sender_of_bounce(
    db: Session,
    *,
    ses_message_id: str | None,
    recipient_email: str | None,
    bounce_type: str = "Permanent",
    detail: str | None = None,
) -> None:
    """Notify the sending user. Never raises."""
    try:
        _notify(
            db,
            ses_message_id=ses_message_id,
            recipient_email=recipient_email,
            bounce_type=bounce_type,
            detail=detail,
        )
    except Exception:
        logger.exception(
            "Bounce notification failed ses_message_id=%s recipient=%s",
            ses_message_id,
            recipient_email,
        )
        db.rollback()


def _notify(
    db: Session,
    *,
    ses_message_id: str | None,
    recipient_email: str | None,
    bounce_type: str,
    detail: str | None,
) -> None:
    message_id = (ses_message_id or "").strip()
    bounced = (recipient_email or "").strip()
    if not message_id or not bounced:
        logger.info("Bounce notification skipped: missing SES message id or recipient")
        return

    log = _match_log(db, message_id, bounced)
    if log is None or log.sender_user_id is None:
        logger.info(
            "Bounce notification skipped: no sender for ses_message_id=%s recipient=%s",
            message_id,
            bounced,
        )
        return

    user = db.query(User).filter(User.id == log.sender_user_id).first()
    if user is None or not (user.email or "").strip():
        logger.info("Bounce notification skipped: sender %s has no account email", log.sender_user_id)
        return

    campaign = db.query(Campaign).filter(Campaign.id == log.campaign_id).first()
    if (
        user.org_id
        and campaign is not None
        and campaign.org_id
        and user.org_id != campaign.org_id
    ):
        logger.warning(
            "Bounce notification skipped: sender %s org does not match campaign %s",
            user.id,
            log.campaign_id,
        )
        return

    campaign_name = (campaign.campaign_name if campaign else None) or "your campaign"
    kind_label = "Permanent" if (bounce_type or "").lower() == "permanent" else (bounce_type or "Bounce")
    title = "Email bounced"
    body = f"{bounced} bounced ({kind_label}) in {campaign_name}."
    dedupe_key = f"bounce:{message_id}"

    row = (
        db.query(UserNotification)
        .filter(UserNotification.user_id == user.id, UserNotification.dedupe_key == dedupe_key)
        .first()
    )
    if row is None:
        row = UserNotification(
            user_id=user.id,
            kind="bounce",
            title=title,
            body=body,
            dedupe_key=dedupe_key,
            campaign_id=log.campaign_id,
            recipient_email=bounced,
            bounce_type=kind_label,
        )
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            row = (
                db.query(UserNotification)
                .filter(UserNotification.user_id == user.id, UserNotification.dedupe_key == dedupe_key)
                .first()
            )
    if row is None or row.emailed_at is not None:
        return

    db.refresh(row)
    _send_notice(
        to_email=user.email.strip(),
        sender_name=user.name,
        campaign_name=campaign_name,
        recipient_email=bounced,
        bounce_type=kind_label,
        detail=detail,
    )
    row.emailed_at = utc_now()
    db.commit()
    logger.info("Bounce notification sent to user_id=%s for ses_message_id=%s", user.id, message_id)


def _match_log(db: Session, message_id: str, recipient_email: str) -> EmailLog | None:
    logs = (
        db.query(EmailLog)
        .filter(EmailLog.ses_message_id == message_id)
        .order_by(EmailLog.id.desc())
        .all()
    )
    if not logs:
        return None
    target = recipient_email.lower()
    for log in logs:
        address = ((log.recipient.email if log.recipient else "") or "").strip().lower()
        if address == target:
            return log
    if len(logs) == 1:
        return logs[0]
    return None


def _send_notice(
    *,
    to_email: str,
    sender_name: str | None,
    campaign_name: str,
    recipient_email: str,
    bounce_type: str,
    detail: str | None,
) -> None:
    safe_name = html.escape(sender_name or "there")
    safe_campaign = html.escape(campaign_name)
    safe_recipient = html.escape(recipient_email)
    safe_type = html.escape(bounce_type)
    detail_line = ""
    if detail:
        detail_line = f"<p>Detail: {html.escape(detail[:500])}</p>"
    body_html = (
        f"<p>Hi {safe_name},</p>"
        f"<p>An email you sent from LeadSense bounced.</p>"
        f"<p>Campaign: {safe_campaign}<br>"
        f"Recipient: {safe_recipient}<br>"
        f"Bounce type: {safe_type}</p>"
        f"{detail_line}"
        "<p>This notice was sent to the email address on your LeadSense account.</p>"
    )
    body_text = (
        f"Hi {sender_name or 'there'},\n\n"
        "An email you sent from LeadSense bounced.\n\n"
        f"Campaign: {campaign_name}\n"
        f"Recipient: {recipient_email}\n"
        f"Bounce type: {bounce_type}\n"
    )
    if detail:
        body_text += f"\nDetail: {detail[:500]}\n"
    result = _ses.send_email(
        to_email=to_email,
        subject=f"LeadSense bounce: {recipient_email}",
        body_html=body_html,
        body_text=body_text,
        from_name="LeadSense",
    )
    if result.get("status") != "sent":
        raise RuntimeError(result.get("error") or "bounce notification email was not sent")
