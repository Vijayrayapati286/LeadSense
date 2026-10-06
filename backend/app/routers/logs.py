"""Email log routes."""

from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Query as OrmQuery, Session

from app.config import get_settings
from app.database.connection import get_db
from app.middleware.auth import get_current_user
from app.models import (
    Campaign,
    CampaignRecipient,
    CampaignRecipientList,
    EmailLog,
    EmailVerification,
    Recipient,
    User,
)
from app.schemas.schemas import EmailLogListResponse, EmailLogResponse, VerifiedEmailGroupResponse

router = APIRouter(prefix="/logs", tags=["Logs"])


def _allowed_verification_results() -> set[str]:
    raw = get_settings().millionverifier_allowed_results or "ok"
    return {part.strip().lower() for part in raw.split(",") if part.strip()} or {"ok"}


def _verified_email_count(db: Session) -> int:
    """Count cached addresses that passed verification (allowed MillionVerifier results)."""
    allowed = _allowed_verification_results()
    return (
        db.query(EmailVerification)
        .filter(EmailVerification.result.in_(list(allowed)))
        .count()
    )


def _apply_log_filters(
    query: OrmQuery,
    *,
    search: str,
    status: str,
    verified_only: bool,
    user_id: int | None,
    campaign_id: int | None,
    group_id: int | None,
    date_from: date | None,
    date_to: date | None,
) -> OrmQuery:
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
    if verified_only:
        allowed = _allowed_verification_results()
        query = query.filter(
            func.lower(Recipient.email).in_(
                select(EmailVerification.email).where(
                    EmailVerification.result.in_(list(allowed)),
                )
            )
        )
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
    return query


def _to_log_response(log: EmailLog, recipient: Recipient, campaign: Campaign, sender: User | None) -> EmailLogResponse:
    item = EmailLogResponse.model_validate(log)
    item.recipient_name = recipient.name
    item.recipient_email = recipient.email
    item.campaign_name = campaign.campaign_name
    item.sender_name = sender.name if sender else None
    item.sender_email = sender.email if sender else None
    return item


def _base_log_query(db: Session) -> OrmQuery:
    return (
        db.query(EmailLog, Recipient, Campaign, User)
        .join(Recipient, Recipient.id == EmailLog.recipient_id)
        .join(Campaign, Campaign.id == EmailLog.campaign_id)
        .outerjoin(User, User.id == EmailLog.sender_user_id)
    )


def _list_grouped_verified(
    db: Session,
    *,
    page: int,
    page_size: int,
    search: str,
    status: str,
    user_id: int | None,
    campaign_id: int | None,
    group_id: int | None,
    date_from: date | None,
    date_to: date | None,
) -> EmailLogListResponse:
    """One row per unique verified prospect name; nested logs hold every matching send.

    Name is preferred so the same person with several verified addresses appears once.
    Rows with a blank name fall back to the email address as the group key.
    """
    # Coalesce blank names to the email so every row still groups cleanly.
    name_key = func.lower(
        func.coalesce(
            func.nullif(func.trim(Recipient.name), ""),
            Recipient.email,
        )
    )
    base = _apply_log_filters(
        _base_log_query(db),
        search=search,
        status=status,
        verified_only=True,
        user_id=user_id,
        campaign_id=campaign_id,
        group_id=group_id,
        date_from=date_from,
        date_to=date_to,
    )

    total = base.with_entities(name_key).distinct().count()

    page_keys = [
        row[0]
        for row in (
            base.with_entities(name_key, func.max(EmailLog.sent_at).label("latest"))
            .group_by(name_key)
            .order_by(func.max(EmailLog.sent_at).desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
    ]

    if not page_keys:
        return EmailLogListResponse(
            items=[],
            groups=[],
            total=total,
            page=page,
            page_size=page_size,
            verified_total=_verified_email_count(db),
            grouped=True,
        )

    detail_rows = (
        base.filter(name_key.in_(page_keys))
        .order_by(EmailLog.sent_at.desc())
        .all()
    )

    grouped: dict[str, list[EmailLogResponse]] = {key: [] for key in page_keys}
    display_names: dict[str, str | None] = {}
    recipient_ids: dict[str, int | None] = {}

    for log, recipient, campaign, sender in detail_rows:
        raw_name = (recipient.name or "").strip()
        key = (raw_name or recipient.email or "").strip().lower()
        if key not in grouped:
            continue
        item = _to_log_response(log, recipient, campaign, sender)
        grouped[key].append(item)
        if key not in display_names:
            display_names[key] = raw_name or recipient.email
            recipient_ids[key] = recipient.id

    groups: list[VerifiedEmailGroupResponse] = []
    for key in page_keys:
        logs = grouped.get(key) or []
        latest = logs[0] if logs else None
        emails: list[str] = []
        seen_emails: set[str] = set()
        for item in logs:
            email = (item.recipient_email or "").strip()
            email_l = email.lower()
            if email and email_l not in seen_emails:
                seen_emails.add(email_l)
                emails.append(email)
        groups.append(
            VerifiedEmailGroupResponse(
                group_key=key,
                recipient_name=display_names.get(key) or (latest.recipient_name if latest else None),
                recipient_email=emails[0] if emails else (latest.recipient_email if latest else None),
                recipient_id=recipient_ids.get(key) or (latest.recipient_id if latest else None),
                emails=emails,
                email_count=len(emails),
                send_count=len(logs),
                latest_sent_at=latest.sent_at if latest else None,
                latest_status=latest.status if latest else None,
                latest_campaign_name=latest.campaign_name if latest else None,
                logs=logs,
            )
        )

    return EmailLogListResponse(
        items=[],
        groups=groups,
        total=total,
        page=page,
        page_size=page_size,
        verified_total=_verified_email_count(db),
        grouped=True,
    )


@router.get("", response_model=EmailLogListResponse)
def list_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    search: str = Query("", alias="search"),
    status: str = Query("", alias="status"),
    verified_only: bool = Query(
        False,
        description="Only logs whose recipient email passed address verification; "
        "response is grouped one row per unique prospect name",
    ),
    user_id: int | None = Query(None, description="Filter by the sender (User/Login)"),
    campaign_id: int | None = Query(None),
    group_id: int | None = Query(None, description="Filter by prospect list"),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if verified_only:
        return _list_grouped_verified(
            db,
            page=page,
            page_size=page_size,
            search=search,
            status=status,
            user_id=user_id,
            campaign_id=campaign_id,
            group_id=group_id,
            date_from=date_from,
            date_to=date_to,
        )

    query = _apply_log_filters(
        _base_log_query(db),
        search=search,
        status=status,
        verified_only=False,
        user_id=user_id,
        campaign_id=campaign_id,
        group_id=group_id,
        date_from=date_from,
        date_to=date_to,
    )

    total = query.count()
    rows = (
        query.order_by(EmailLog.sent_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items = [_to_log_response(log, recipient, campaign, sender) for log, recipient, campaign, sender in rows]

    return EmailLogListResponse(
        items=items,
        groups=[],
        total=total,
        page=page,
        page_size=page_size,
        verified_total=_verified_email_count(db),
        grouped=False,
    )
