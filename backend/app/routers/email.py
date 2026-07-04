"""Email sending routes."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.middleware.auth import get_current_user
from app.models import Campaign, EmailLog, Recipient, User
from app.schemas.schemas import SendEmailRequest, SendEmailResponse
from app.services.ses_service import SESService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/email", tags=["Email"])
ses_service = SESService()


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
        recipients = db.query(Recipient).filter(Recipient.id.in_(data.recipient_ids)).all()
    else:
        recipients = db.query(Recipient).filter(Recipient.is_selected == True).all()

    if not recipients:
        raise HTTPException(status_code=400, detail="No recipients selected")

    recipient_dicts = [
        {
            "id": r.id,
            "name": r.name,
            "email": r.email,
            "company": r.company or "",
            "designation": r.designation or "",
            "industry": r.industry or "",
        }
        for r in recipients
    ]

    result = ses_service.send_bulk_email(
        recipients=recipient_dicts,
        subject_template=data.subject,
        body_template=data.body,
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

    campaign.emails_sent += result["sent"]
    if result["sent"] > 0:
        campaign.status = "active"

    db.commit()

    return SendEmailResponse(**result)
