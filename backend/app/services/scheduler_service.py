"""Engagement Studio scheduler.

Polls CampaignRecipient rows periodically for ones whose next follow-up is
due, and sends the next EngagementStudioStage via the existing SES service —
no new infrastructure (queue/worker), it just runs inside the FastAPI process.
"""

import html
import logging
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import Session

from app.database.connection import SessionLocal
from app.models import (
    CampaignRecipient,
    CampaignRecipientList,
    EmailLog,
    EngagementStudioList,
    EngagementStudioStage,
    Recipient,
    Template,
    User,
)
from app.config import get_settings
from app.services.graph_reply_service import poll_replies
from app.services.ses_service import SESService
from app.utils.helpers import build_recipient_context, render_email_body, render_template, utc_now

logger = logging.getLogger(__name__)
settings = get_settings()
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


def compute_next_send_at(stage: EngagementStudioStage):
    unit = stage.delay_unit
    value = stage.delay_value
    if unit == "minutes":
        delta = timedelta(minutes=value)
    elif unit == "hours":
        delta = timedelta(hours=value)
    else:
        delta = timedelta(days=value)
    return utc_now() + delta


def _resolve_stage_content(stage: EngagementStudioStage) -> tuple[str, str, str | None]:
    """(subject, body, closing) for a stage — pulled live from its library
    Mailer when mailer_id is set (so edits to the Mailer are picked up on the
    next send), otherwise the stage's own inline content."""
    if stage.mailer_id and stage.mailer:
        return stage.mailer.subject, stage.mailer.body, stage.mailer.closing
    return stage.subject, stage.body, stage.closing


def process_due_followups() -> None:
    db: Session = SessionLocal()
    try:
        due_ids = [
            row.id
            for row in db.query(CampaignRecipient.id)
            .join(Recipient, CampaignRecipient.recipient_id == Recipient.id)
            .filter(
                CampaignRecipient.next_send_at.isnot(None),
                CampaignRecipient.next_send_at <= utc_now(),
                CampaignRecipient.status.notin_(TERMINAL_STATUSES),
                Recipient.is_suppressed == False,  # noqa: E712
            )
            .all()
        ]

        sent_count = 0
        for cr_id in due_ids:
            # Re-fetch with a row lock, skipping rows another process already
            # claimed (SKIP LOCKED) — if this backend ever runs as more than
            # one replica, each has its own in-process poller hitting the
            # same table; without this, two replicas can both see the same
            # "due" row and both send it. Re-checking the terminal-status
            # filter here too, in case a reply/bounce landed between the scan
            # above and this lock.
            cr = (
                db.query(CampaignRecipient)
                .filter(
                    CampaignRecipient.id == cr_id,
                    CampaignRecipient.status.notin_(TERMINAL_STATUSES),
                )
                .with_for_update(skip_locked=True)
                .first()
            )
            if cr is None:
                continue

            next_stage_order = cr.current_stage + 1
            stage = (
                db.query(EngagementStudioStage)
                .filter(
                    EngagementStudioStage.campaign_id == cr.campaign_id,
                    EngagementStudioStage.stage_order == next_stage_order,
                )
                .first()
            )
            if not stage:
                cr.next_send_at = None
                db.commit()
                continue

            recipient = cr.recipient

            # Auto-classify engagement: a reply anywhere already tagged this
            # recipient "Hot" (event_service.handle_reply). If that hasn't
            # happened, reaching this point means a stage came due with no
            # reply — tag "Cold", overriding any earlier manual tag (Warm/
            # Negative). Hot itself is never downgraded back to Cold here.
            if recipient.response_tag != "Hot":
                recipient.response_tag = "Cold"

            # Condition: a "Hot" tag (an actual reply) stops automation here,
            # on top of the reply/bounce/suppression check already applied
            # above via TERMINAL_STATUSES — "Cold" (non-responsive) keeps
            # moving through the sequence.
            if stage.skip_if_tagged and recipient.response_tag == "Hot":
                cr.next_send_at = None
                db.commit()
                continue

            stage_subject, stage_body, stage_closing = _resolve_stage_content(stage)
            context = build_recipient_context(recipient)
            subject = render_template(stage_subject, context)
            body = render_template(stage_body, context)
            if stage_closing:
                body = f"{body}\n\n{render_template(stage_closing, context)}"

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
                    message_id=result.get("rfc_message_id"),
                )
            )

            cr.status = result["status"]
            cr.last_sent_at = utc_now()
            if result["status"] == "sent":
                cr.current_stage = next_stage_order
                following_stage = (
                    db.query(EngagementStudioStage)
                    .filter(
                        EngagementStudioStage.campaign_id == cr.campaign_id,
                        EngagementStudioStage.stage_order == next_stage_order + 1,
                    )
                    .first()
                )
                cr.next_send_at = compute_next_send_at(following_stage) if following_stage else None
            else:
                cr.next_send_at = None

            db.commit()
            if result["status"] == "sent":
                sent_count += 1

        if sent_count:
            logger.info("Processed %d due follow-up(s)", sent_count)
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
        due_ids = [
            row.id
            for row in db.query(CampaignRecipient.id)
            .join(Recipient, CampaignRecipient.recipient_id == Recipient.id)
            .filter(
                CampaignRecipient.status == "queued",
                CampaignRecipient.next_send_at.isnot(None),
                CampaignRecipient.next_send_at <= utc_now(),
                Recipient.is_suppressed == False,  # noqa: E712
            )
            .all()
        ]

        sent_count = 0
        for cr_id in due_ids:
            # Row lock, skipping rows another process already claimed — see
            # the matching comment in process_due_followups for why.
            cr = (
                db.query(CampaignRecipient)
                .filter(CampaignRecipient.id == cr_id, CampaignRecipient.status == "queued")
                .with_for_update(skip_locked=True)
                .first()
            )
            if cr is None:
                continue

            recipient = cr.recipient

            if cr.campaign.use_recipient_timezone and recipient.timezone:
                reschedule = next_business_hour_utc(recipient.timezone, utc_now())
                if reschedule is not None:
                    cr.next_send_at = reschedule
                    db.commit()
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
                db.commit()
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
                    message_id=result.get("rfc_message_id"),
                )
            )

            cr.status = result["status"]
            cr.last_sent_at = utc_now()
            if result["status"] == "sent":
                cr.campaign.emails_sent += 1
                next_stage = (
                    db.query(EngagementStudioStage)
                    .filter(EngagementStudioStage.campaign_id == cr.campaign_id, EngagementStudioStage.stage_order == 1)
                    .first()
                )
                # Enroll in the automated chain only if this recipient is in
                # one of the campaign's selected Engagement Studio lists — or
                # if no lists are configured at all, in which case every
                # recipient enrolls (matches pre-Engagement-Studio behavior).
                studio_group_ids = [
                    row.group_id
                    for row in db.query(EngagementStudioList.group_id)
                    .filter(EngagementStudioList.campaign_id == cr.campaign_id)
                    .all()
                ]
                in_scope = not studio_group_ids or (
                    db.query(CampaignRecipientList)
                    .filter(
                        CampaignRecipientList.campaign_id == cr.campaign_id,
                        CampaignRecipientList.recipient_id == cr.recipient_id,
                        CampaignRecipientList.group_id.in_(studio_group_ids),
                    )
                    .first()
                    is not None
                )
                cr.next_send_at = compute_next_send_at(next_stage) if (next_stage and in_scope) else None
            else:
                cr.next_send_at = None

            db.commit()
            if result["status"] == "sent":
                sent_count += 1

        if sent_count:
            logger.info("Sent %d queued initial email(s)", sent_count)
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
    # Registered unconditionally — poll_replies itself no-ops until
    # settings.enable_reply_polling is true AND Graph app-only auth actually
    # succeeds, so there's no behavior change just from this job existing.
    _scheduler.add_job(
        poll_replies, "interval",
        seconds=settings.graph_reply_poll_interval_seconds, id="poll_replies",
    )
    _scheduler.start()
    logger.info("Follow-up scheduler started (polling every %ds)", POLL_INTERVAL_SECONDS)
    logger.info("Queued-send scheduler started (polling every %ds)", QUEUED_SEND_POLL_INTERVAL_SECONDS)
    logger.info(
        "Reply-polling scheduler started (polling every %ds, active=%s)",
        settings.graph_reply_poll_interval_seconds, settings.enable_reply_polling,
    )


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
