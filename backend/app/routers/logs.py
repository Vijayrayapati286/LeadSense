"""Email log routes."""

from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.middleware.auth import get_current_user
from app.models import Campaign, CampaignRecipient, CampaignRecipientList, EmailLog, Recipient, User
from app.schemas.schemas import EmailLogListResponse, EmailLogResponse

router = APIRouter(prefix="/logs", tags=["Logs"])


@router.get("", response_model=EmailLogListResponse)
def list_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    search: str = Query("", alias="search"),
    status: str = Query("", alias="status"),
    user_id: int | None = Query(None, description="Filter by the sender (User/Login)"),
    campaign_id: int | None = Query(None),
    group_id: int | None = Query(None, description="Filter by prospect list"),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = (
        db.query(EmailLog, Recipient, Campaign, User)
        .join(Recipient, Recipient.id == EmailLog.recipient_id)
        .join(Campaign, Campaign.id == EmailLog.campaign_id)
        .outerjoin(User, User.id == EmailLog.sender_user_id)
    )

    if search:
        term = f"%{search}%"
        query = query.filter(
            or_(Recipient.name.ilike(term), Recipient.email.ilike(term), Campaign.campaign_name.ilike(term))
        )
    if status == "bounced":
        # A bounce is discovered asynchronously, well after the send already
        # logged as "sent" here — that later status only ever lands on
        # CampaignRecipient (see event_service.py's bounce/complaint
        # handlers), never back onto the EmailLog row itself. Join to it so
        # this filter actually finds anything instead of always coming back
        # empty against a status EmailLog.status never holds.
        query = query.join(
            CampaignRecipient,
            (CampaignRecipient.campaign_id == EmailLog.campaign_id)
            & (CampaignRecipient.recipient_id == EmailLog.recipient_id),
        ).filter(CampaignRecipient.status == "bounced")
    elif status:
        query = query.filter(EmailLog.status == status)
    if user_id:
        query = query.filter(EmailLog.sender_user_id == user_id)
    if campaign_id:
        query = query.filter(EmailLog.campaign_id == campaign_id)
    if group_id:
        # CampaignRecipientList (not the legacy single-valued
        # CampaignRecipient.group_id) is the source of truth for list
        # membership — a recipient can belong to several lists per
        # campaign, so this correctly surfaces their log rows under every
        # list they're tagged into, not just the last one.
        query = query.join(
            CampaignRecipientList,
            (CampaignRecipientList.campaign_id == EmailLog.campaign_id)
            & (CampaignRecipientList.recipient_id == EmailLog.recipient_id)
            & (CampaignRecipientList.group_id == group_id),
        )
    if date_from:
        query = query.filter(EmailLog.sent_at >= datetime.combine(date_from, time.min, tzinfo=timezone.utc))
    if date_to:
        query = query.filter(EmailLog.sent_at <= datetime.combine(date_to, time.max, tzinfo=timezone.utc))

    total = query.count()

    rows = (
        query.order_by(EmailLog.sent_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = []
    for log, recipient, campaign, sender in rows:
        item = EmailLogResponse.model_validate(log)
        item.recipient_name = recipient.name
        item.recipient_email = recipient.email
        item.campaign_name = campaign.campaign_name
        item.sender_name = sender.name if sender else None
        item.sender_email = sender.email if sender else None
        items.append(item)

    return EmailLogListResponse(items=items, total=total, page=page, page_size=page_size)
