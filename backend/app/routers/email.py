"""Email sending routes.

Sends are queued rather than performed synchronously: a mandatory interval
between outgoing emails (configurable in Settings) means a real campaign send
can take minutes, far too long to hold an HTTP request open. This endpoint
just stamps each recipient's `CampaignRecipient` row with `status="queued"`
and a staggered `next_send_at`; the `process_queued_initial_sends` scheduler
job (see scheduler_service.py) does the actual sending as each row comes due.
"""

import logging
from collections import defaultdict
from datetime import timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.middleware.auth import get_current_user
from app.models import Campaign, CampaignRecipient, CustomField, EmailLog, Recipient, RecipientCustomValue, Template, User
from app.schemas.schemas import IncompleteRecipientInfo, SendEmailRequest, SendEmailResponse
from app.services.app_settings_service import AppSettingsService
from app.services.campaign_service import CampaignService
from app.services.ses_service import SESService
from app.utils.helpers import KNOWN_MERGE_FIELDS, extract_placeholders, utc_now

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/email", tags=["Email"])
ses_service = SESService()
app_settings_service = AppSettingsService()
campaign_service = CampaignService()


def _filter_incomplete_recipients(
    db: Session, campaign_id: int, recipients: list[Recipient]
) -> tuple[list[Recipient], list[IncompleteRecipientInfo]]:
    """Drop any recipient missing a value for a custom field their effective
    template (their CampaignRecipient.template_id tag, else the campaign's
    primary template) uses — so a literal unresolved {{Field}} never reaches
    an inbox. Standard fields always resolve (even to ""), so only custom
    fields can cause this."""
    if not recipients:
        return [], []

    recipient_ids = [r.id for r in recipients]
    existing_crs = {
        cr.recipient_id: cr
        for cr in db.query(CampaignRecipient)
        .filter(CampaignRecipient.campaign_id == campaign_id, CampaignRecipient.recipient_id.in_(recipient_ids))
        .all()
    }
    primary_template = campaign_service.get_template(db, campaign_id)
    template_cache: dict[int, Template | None] = {}

    def resolve_template(template_id: int | None) -> Template | None:
        if template_id is None:
            return primary_template
        if template_id not in template_cache:
            template_cache[template_id] = db.query(Template).filter(Template.id == template_id).first()
        return template_cache[template_id]

    recipient_custom_names: dict[int, set[str]] = defaultdict(set)
    custom_value_rows = (
        db.query(RecipientCustomValue.recipient_id, CustomField.name)
        .join(CustomField, CustomField.id == RecipientCustomValue.custom_field_id)
        .filter(RecipientCustomValue.recipient_id.in_(recipient_ids))
        .all()
    )
    for recipient_id, name in custom_value_rows:
        recipient_custom_names[recipient_id].add(name)

    sendable: list[Recipient] = []
    incomplete: list[IncompleteRecipientInfo] = []
    for recipient in recipients:
        cr = existing_crs.get(recipient.id)
        template = resolve_template(cr.template_id if cr else None)
        if template:
            used_fields = extract_placeholders(
                " ".join(filter(None, [template.subject, template.body, template.closing, template.cta]))
            )
            custom_fields_used = [f for f in used_fields if f not in KNOWN_MERGE_FIELDS]
            missing = [f for f in custom_fields_used if f not in recipient_custom_names.get(recipient.id, set())]
            if missing:
                incomplete.append(IncompleteRecipientInfo(email=recipient.email, missing_fields=missing))
                continue
        sendable.append(recipient)

    return sendable, incomplete


@router.post("/send", response_model=SendEmailResponse)
def send_emails(
    data: SendEmailRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Queue bulk emails to selected recipients for a campaign, staggered by
    the configured send interval."""
    campaign = db.query(Campaign).filter(Campaign.id == data.campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if data.recipient_ids:
        recipients_all = db.query(Recipient).filter(Recipient.id.in_(data.recipient_ids)).all()
    else:
        recipients_all = db.query(Recipient).filter(Recipient.is_selected == True).all()

    skipped_suppressed = len([r for r in recipients_all if r.is_suppressed])
    recipients = [r for r in recipients_all if not r.is_suppressed]

    if not recipients_all:
        if ses_service.settings.use_mock_ses:
            # Dev convenience: no real recipients selected, mock SES is on —
            # fire a single immediate test email rather than queuing (there's
            # no real Recipient row to attach a CampaignRecipient to).
            result = ses_service.send_bulk_email(
                recipients=[{
                    "id": 0,
                    "name": "Test Recipient",
                    "email": ses_service.settings.test_email_override,
                    "company": "",
                    "designation": "",
                    "industry": "",
                }],
                subject_template=data.subject,
                body_template=data.body,
                from_name=current_user.name,
                reply_to=current_user.email,
            )
            db.add(EmailLog(
                campaign_id=data.campaign_id,
                recipient_id=recipients_all[0].id if recipients_all else None,
                status=result["details"][0]["status"],
                error_message=result["details"][0].get("error"),
                sender_user_id=current_user.id,
            ))
            campaign.emails_sent += result["sent"]
            if result["sent"] > 0:
                campaign.status = "active"
            db.commit()
            return SendEmailResponse(queued=0, skipped_suppressed=0, immediate_sent=result["sent"])
        raise HTTPException(status_code=400, detail="No recipients selected")
    elif not recipients:
        raise HTTPException(
            status_code=400,
            detail=f"All {skipped_suppressed} selected recipient(s) are suppressed/blacklisted",
        )

    recipients, incomplete = _filter_incomplete_recipients(db, data.campaign_id, recipients)
    skipped_incomplete_data = len(incomplete)

    if not recipients:
        return SendEmailResponse(
            queued=0,
            skipped_suppressed=skipped_suppressed,
            skipped_incomplete_data=skipped_incomplete_data,
            incomplete=incomplete,
        )

    interval_seconds = app_settings_service.get(db).send_interval_seconds
    now = utc_now()
    # SQLite drops tzinfo on round-trip, so a stored scheduled_at comes back
    # naive — treat it as UTC (the only timezone we ever write) to compare.
    scheduled_at = campaign.scheduled_at
    if scheduled_at is not None and scheduled_at.tzinfo is None:
        scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
    # A future scheduled_at delays the whole batch; a past/unset one starts
    # staggering immediately, so editing a campaign after its scheduled time
    # has already passed still sends right away instead of silently stalling.
    base_time = scheduled_at if scheduled_at and scheduled_at > now else now

    queued = 0
    for index, recipient in enumerate(recipients):
        cr = (
            db.query(CampaignRecipient)
            .filter(CampaignRecipient.campaign_id == data.campaign_id, CampaignRecipient.recipient_id == recipient.id)
            .first()
        )
        if not cr:
            cr = CampaignRecipient(campaign_id=data.campaign_id, recipient_id=recipient.id, current_stage=0)
            db.add(cr)

        cr.status = "queued"
        cr.next_send_at = base_time + timedelta(seconds=index * interval_seconds)
        cr.sender_user_id = current_user.id
        queued += 1

    campaign.status = "active"
    db.commit()

    logger.info("Queued %d email(s) for campaign %d, %ds apart", queued, data.campaign_id, interval_seconds)

    return SendEmailResponse(
        queued=queued,
        skipped_suppressed=skipped_suppressed,
        skipped_incomplete_data=skipped_incomplete_data,
        incomplete=incomplete,
    )
