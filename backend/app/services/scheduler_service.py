"""Follow-up sequence scheduler.

Polls CampaignRecipient rows periodically for ones whose next follow-up is
due, and sends the next CampaignSequenceStage via the existing SES service —
no new infrastructure (queue/worker), it just runs inside the FastAPI process.
"""

import html
import logging
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import Session

from app.database.connection import SessionLocal
from app.models import CampaignRecipient, CampaignSequenceStage, EmailLog, Recipient, Template, User
from app.services.ses_service import SESService
from app.utils.helpers import build_recipient_context, render_email_body, render_template, utc_now

logger = logging.getLogger(__name__)
ses_service = SESService()

# Statuses that should never receive another automated follow-up.
TERMINAL_STATUSES = {"replied", "suppressed", "bounced", "invalid_email"}

POLL_INTERVAL_SECONDS = 300
QUEUED_SEND_POLL_INTERVAL_SECONDS = 5
BUSINESS_HOURS_START = 9
BUSINESS_HOURS_END = 18


def next_business_hour_utc(tz_name: str, now_utc: datetime) -> datetime | None:
    """None if `now_utc` already falls within the recipient's local 9am-6pm
    business hours; otherwise the next local 9am, converted back to UTC."""
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        return None
    local_now = now_utc.astimezone(tz)
    if BUSINESS_HOURS_START <= local_now.hour < BUSINESS_HOURS_END:
        return None
    next_day = local_now.date()
    if local_now.hour >= BUSINESS_HOURS_END:
        next_day += timedelta(days=1)
    next_9am_local = datetime.combine(next_day, time(hour=BUSINESS_HOURS_START), tzinfo=tz)
    return next_9am_local.astimezone(timezone.utc)

_scheduler: AsyncIOScheduler | None = None


def _resolve_sender(cr: CampaignRecipient) -> User | None:
    """Whoever triggered this recipient's current send (Send/Schedule) is the
    From/Reply-To identity — falls back to the campaign's creator only for
    rows queued before sender_user_id existed."""
    return cr.sender_user or cr.campaign.owner_user


def compute_next_send_at(stage: CampaignSequenceStage):
    unit = stage.delay_unit
    value = stage.delay_value
    if unit == "minutes":
        delta = timedelta(minutes=value)
    elif unit == "hours":
        delta = timedelta(hours=value)
    else:
        delta = timedelta(days=value)
    return utc_now() + delta


def process_due_followups() -> None:
    db: Session = SessionLocal()
    try:
        due = (
            db.query(CampaignRecipient)
            .join(Recipient, CampaignRecipient.recipient_id == Recipient.id)
            .filter(
                CampaignRecipient.next_send_at.isnot(None),
                CampaignRecipient.next_send_at <= utc_now(),
                CampaignRecipient.status.notin_(TERMINAL_STATUSES),
                Recipient.is_suppressed == False,  # noqa: E712
            )
            .all()
        )

        for cr in due:
            next_stage_order = cr.current_stage + 1
            stage = (
                db.query(CampaignSequenceStage)
                .filter(
                    CampaignSequenceStage.campaign_id == cr.campaign_id,
                    CampaignSequenceStage.stage_order == next_stage_order,
                )
                .first()
            )
            if not stage:
                cr.next_send_at = None
                continue

            recipient = cr.recipient
            context = build_recipient_context(recipient)
            subject = render_template(stage.subject, context)
            body = render_template(stage.body, context)
            if stage.closing:
                body = f"{body}\n\n{render_template(stage.closing, context)}"

            owner = _resolve_sender(cr)
            result = ses_service.send_email(
                to_email=recipient.email,
                subject=subject,
                body_html=body.replace("\n", "<br>"),
                body_text=body,
                from_name=owner.name if owner else None,
                reply_to=owner.email if owner else None,
            )

            db.add(
                EmailLog(
                    campaign_id=cr.campaign_id,
                    recipient_id=recipient.id,
                    status=result["status"],
                    error_message=result.get("error"),
                    sender_user_id=owner.id if owner else None,
                )
            )

            cr.status = result["status"]
            cr.last_sent_at = utc_now()
            if result["status"] == "sent":
                cr.current_stage = next_stage_order
                following_stage = (
                    db.query(CampaignSequenceStage)
                    .filter(
                        CampaignSequenceStage.campaign_id == cr.campaign_id,
                        CampaignSequenceStage.stage_order == next_stage_order + 1,
                    )
                    .first()
                )
                cr.next_send_at = compute_next_send_at(following_stage) if following_stage else None
            else:
                cr.next_send_at = None

        db.commit()
        if due:
            logger.info("Processed %d due follow-up(s)", len(due))
    except Exception:
        logger.exception("Error processing due follow-ups")
        db.rollback()
    finally:
        db.close()


def process_queued_initial_sends() -> None:
    """Send the campaign's stage-0 Template to recipients whose queued send
    time (staggered at queue time by the configured send interval) has come
    due. Mirrors process_due_followups' approach for later stages."""
    db: Session = SessionLocal()
    try:
        due = (
            db.query(CampaignRecipient)
            .join(Recipient, CampaignRecipient.recipient_id == Recipient.id)
            .filter(
                CampaignRecipient.status == "queued",
                CampaignRecipient.next_send_at.isnot(None),
                CampaignRecipient.next_send_at <= utc_now(),
                Recipient.is_suppressed == False,  # noqa: E712
            )
            .all()
        )

        for cr in due:
            recipient = cr.recipient

            if cr.campaign.use_recipient_timezone and recipient.timezone:
                reschedule = next_business_hour_utc(recipient.timezone, utc_now())
                if reschedule is not None:
                    cr.next_send_at = reschedule
                    continue  # stays "queued" — outside business hours, try again then

            template = None
            if cr.template_id:
                template = db.query(Template).filter(Template.id == cr.template_id).first()
            if not template:
                # Untagged, or the tagged template was deleted — fall back to
                # the campaign's primary (first-created) template.
                template = (
                    db.query(Template)
                    .filter(Template.campaign_id == cr.campaign_id)
                    .order_by(Template.created_at.asc())
                    .first()
                )
            if not template:
                cr.status = "failed"
                cr.next_send_at = None
                continue
            context = build_recipient_context(recipient)
            subject = render_template(template.subject, context)
            body_html, body_text = render_email_body(template.body, template.type, context)
            if template.closing:
                # Legacy templates only — the Manual editor no longer exposes
                # a separate Closing field, so new Manual templates never set
                # this. Escaped so a literal "<" a user once typed here can't
                # be mistaken for markup once appended after real HTML.
                closing = render_template(template.closing, context)
                body_html = f"{body_html}<br><br>{html.escape(closing)}"
                body_text = f"{body_text}\n\n{closing}"

            owner = _resolve_sender(cr)
            result = ses_service.send_email(
                to_email=recipient.email,
                subject=subject,
                body_html=body_html,
                body_text=body_text,
                from_name=owner.name if owner else None,
                reply_to=owner.email if owner else None,
            )

            db.add(
                EmailLog(
                    campaign_id=cr.campaign_id,
                    recipient_id=recipient.id,
                    status=result["status"],
                    error_message=result.get("error"),
                    sender_user_id=owner.id if owner else None,
                )
            )

            cr.status = result["status"]
            cr.last_sent_at = utc_now()
            if result["status"] == "sent":
                cr.campaign.emails_sent += 1
                next_stage = (
                    db.query(CampaignSequenceStage)
                    .filter(CampaignSequenceStage.campaign_id == cr.campaign_id, CampaignSequenceStage.stage_order == 1)
                    .first()
                )
                cr.next_send_at = compute_next_send_at(next_stage) if next_stage else None
            else:
                cr.next_send_at = None

        db.commit()
        if due:
            logger.info("Sent %d queued initial email(s)", len(due))
    except Exception:
        logger.exception("Error processing queued initial sends")
        db.rollback()
    finally:
        db.close()


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(process_due_followups, "interval", seconds=POLL_INTERVAL_SECONDS, id="process_due_followups")
    _scheduler.add_job(
        process_queued_initial_sends, "interval",
        seconds=QUEUED_SEND_POLL_INTERVAL_SECONDS, id="process_queued_initial_sends",
    )
    _scheduler.start()
    logger.info("Follow-up scheduler started (polling every %ds)", POLL_INTERVAL_SECONDS)
    logger.info("Queued-send scheduler started (polling every %ds)", QUEUED_SEND_POLL_INTERVAL_SECONDS)


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
