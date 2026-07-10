"""Follow-up sequence scheduler.

Polls CampaignRecipient rows periodically for ones whose next follow-up is
due, and sends the next CampaignSequenceStage via the existing SES service —
no new infrastructure (queue/worker), it just runs inside the FastAPI process.
"""

import logging
from datetime import timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import Session

from app.database.connection import SessionLocal
from app.models import CampaignRecipient, CampaignSequenceStage, EmailLog, Recipient
from app.services.ses_service import SESService
from app.utils.helpers import render_template, utc_now

logger = logging.getLogger(__name__)
ses_service = SESService()

# Statuses that should never receive another automated follow-up.
TERMINAL_STATUSES = {"replied", "suppressed", "bounced", "invalid_email"}

POLL_INTERVAL_SECONDS = 300

_scheduler: AsyncIOScheduler | None = None


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
            context = {
                "Name": recipient.name,
                "Email": recipient.email,
                "Company": recipient.company or "",
                "Designation": recipient.designation or "",
                "Industry": recipient.industry or "",
            }
            subject = render_template(stage.subject, context)
            body = render_template(stage.body, context)
            if stage.closing:
                body = f"{body}\n\n{render_template(stage.closing, context)}"

            result = ses_service.send_email(
                to_email=recipient.email,
                subject=subject,
                body_html=body.replace("\n", "<br>"),
                body_text=body,
            )

            db.add(
                EmailLog(
                    campaign_id=cr.campaign_id,
                    recipient_id=recipient.id,
                    status=result["status"],
                    error_message=result.get("error"),
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


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(process_due_followups, "interval", seconds=POLL_INTERVAL_SECONDS, id="process_due_followups")
    _scheduler.start()
    logger.info("Follow-up scheduler started (polling every %ds)", POLL_INTERVAL_SECONDS)


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
