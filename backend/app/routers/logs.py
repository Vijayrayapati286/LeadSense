"""Email log routes."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.middleware.auth import get_current_user
from app.models import Campaign, EmailLog, Recipient, User
from app.schemas.schemas import EmailLogListResponse, EmailLogResponse

router = APIRouter(prefix="/logs", tags=["Logs"])


@router.get("", response_model=EmailLogListResponse)
def list_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    search: str = Query("", alias="search"),
    status: str = Query("", alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(EmailLog)

    if status:
        query = query.filter(EmailLog.status == status)

    total = query.count()

    logs = (
        query.order_by(EmailLog.sent_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = []
    for log in logs:
        recipient = db.query(Recipient).filter(Recipient.id == log.recipient_id).first()
        campaign = db.query(Campaign).filter(Campaign.id == log.campaign_id).first()
        sender = db.query(User).filter(User.id == log.sender_user_id).first() if log.sender_user_id else None

        item = EmailLogResponse.model_validate(log)
        item.recipient_name = recipient.name if recipient else None
        item.recipient_email = recipient.email if recipient else None
        item.campaign_name = campaign.campaign_name if campaign else None
        item.sender_name = sender.name if sender else None
        item.sender_email = sender.email if sender else None

        if search:
            term = search.lower()
            searchable = f"{item.recipient_name} {item.recipient_email} {item.campaign_name}".lower()
            if term not in searchable:
                continue

        items.append(item)

    return EmailLogListResponse(
        items=items,
        total=total if not search else len(items),
        page=page,
        page_size=page_size,
    )
