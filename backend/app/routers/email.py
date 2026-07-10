"""Email sending routes."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.middleware.auth import get_current_user
from app.models import Campaign, CampaignRecipient, CampaignSequenceStage, EmailLog, Recipient, User
from app.schemas.schemas import SendEmailRequest, SendEmailResponse
from app.services.scheduler_service import compute_next_send_at
from app.services.ses_service import SESService
from app.utils.helpers import utc_now

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/email", tags=["Email"])
ses_service = SESService()


def _sync_campaign_recipient(db: Session, campaign_id: int, recipient_id: int, send_status: str) -> None:
    """Create/update the per-campaign tracking row after an initial (stage 0)
    send, and schedule the next follow-up stage if one exists."""
    cr = (
        db.query(CampaignRecipient)
        .filter(CampaignRecipient.campaign_id == campaign_id, CampaignRecipient.recipient_id == recipient_id)
        .first()
    )
    if not cr:
        cr = CampaignRecipient(campaign_id=campaign_id, recipient_id=recipient_id, current_stage=0)
        db.add(cr)

    cr.status = send_status
    cr.last_sent_at = utc_now()

    if send_status == "sent":
        next_stage = (
            db.query(CampaignSequenceStage)
            .filter(CampaignSequenceStage.campaign_id == campaign_id, CampaignSequenceStage.stage_order == 1)
            .first()
        )
        cr.next_send_at = compute_next_send_at(next_stage) if next_stage else None


@router.post("/send", response_model=SendEmailResponse)
def send_emails(
    data: SendEmailRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Send bulk emails to selected recipients for a campaign."""
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
            recipients = [
                {
                    "id": 0,
                    "name": "Test Recipient",
                    "email": ses_service.settings.test_email_override,
                    "company": "",
                    "designation": "",
                    "industry": "",
                }
            ]
        else:
            raise HTTPException(status_code=400, detail="No recipients selected")
    elif not recipients:
        raise HTTPException(
            status_code=400,
            detail=f"All {skipped_suppressed} selected recipient(s) are suppressed/blacklisted",
        )

    recipient_dicts = []
    for r in recipients:
        if isinstance(r, dict):
            recipient_dicts.append(
                {
                    "id": r.get("id"),
                    "name": r.get("name", ""),
                    "email": r.get("email", ""),
                    "company": r.get("company", "") or "",
                    "designation": r.get("designation", "") or "",
                    "industry": r.get("industry", "") or "",
                }
            )
        else:
            recipient_dicts.append(
                {
                    "id": r.id,
                    "name": r.name,
                    "email": r.email,
                    "company": r.company or "",
                    "designation": r.designation or "",
                    "industry": r.industry or "",
                }
            )

    result = ses_service.send_bulk_email(
        recipients=recipient_dicts,
        subject_template=data.subject,
        body_template=data.body,
        from_name=current_user.email,
        reply_to=current_user.email,
    )

    # Log all send results
    for detail in result["details"]:
        recipient = next(
            (r for r in recipient_dicts if r["email"] == detail["recipient_email"]),
            None,
        )
        if recipient:
            log = EmailLog(
                campaign_id=data.campaign_id,
                recipient_id=recipient["id"],
                status=detail["status"],
                error_message=detail.get("error"),
            )
            db.add(log)
            if recipient["id"]:
                _sync_campaign_recipient(db, data.campaign_id, recipient["id"], detail["status"])

    campaign.emails_sent += result["sent"]
    if result["sent"] > 0:
        campaign.status = "active"

    db.commit()

    return SendEmailResponse(**result, skipped_suppressed=skipped_suppressed)
