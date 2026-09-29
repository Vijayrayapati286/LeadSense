"""In-app notifications for the logged-in user."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.middleware.auth import get_current_user
from app.models import User, UserNotification
from app.schemas.schemas import NotificationItem, NotificationListResponse
from app.utils.helpers import utc_now

router = APIRouter(prefix="/notifications", tags=["Notifications"])


def _item(row: UserNotification) -> NotificationItem:
    return NotificationItem(
        id=row.id,
        kind=row.kind,
        title=row.title,
        body=row.body,
        recipient_email=row.recipient_email,
        campaign_id=row.campaign_id,
        bounce_type=row.bounce_type,
        read=row.read_at is not None,
        created_at=row.created_at,
    )


@router.get("", response_model=NotificationListResponse)
def list_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(UserNotification)
        .filter(UserNotification.user_id == current_user.id)
        .order_by(UserNotification.created_at.desc(), UserNotification.id.desc())
        .limit(50)
        .all()
    )
    unread = (
        db.query(UserNotification)
        .filter(UserNotification.user_id == current_user.id, UserNotification.read_at.is_(None))
        .count()
    )
    return NotificationListResponse(items=[_item(row) for row in rows], unread_count=unread)


@router.post("/{notification_id}/read", response_model=NotificationItem)
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = (
        db.query(UserNotification)
        .filter(UserNotification.id == notification_id, UserNotification.user_id == current_user.id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    if row.read_at is None:
        row.read_at = utc_now()
        db.commit()
        db.refresh(row)
    return _item(row)


@router.post("/read-all", response_model=NotificationListResponse)
def mark_all_notifications_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    now = utc_now()
    (
        db.query(UserNotification)
        .filter(UserNotification.user_id == current_user.id, UserNotification.read_at.is_(None))
        .update({UserNotification.read_at: now}, synchronize_session=False)
    )
    db.commit()
    return list_notifications(db=db, current_user=current_user)
