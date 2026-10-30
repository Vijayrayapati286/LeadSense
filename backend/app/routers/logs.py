"""Email log routes."""

import csv
import io
from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
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
from app.services.millionverifier_service import (
    DISPLAY_BAD,
    DISPLAY_GOOD,
    DISPLAY_RISKY,
    classify_cached_verification,
)

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
    item.recipient_company = recipient.company
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
                company=next((item.recipient_company for item in logs if item.recipient_company), None),
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
    category: str = Query(
        "",
        description="Show every risky, invalid, or verified address, one row per email",
    ),
    user_id: int | None = Query(None, description="Filter by the sender (User/Login)"),
    campaign_id: int | None = Query(None),
    group_id: int | None = Query(None, description="Filter by prospect list"),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    bucket = (category or "").strip().lower()
    if not bucket and verified_only:
        bucket = "verified"
    if bucket:
        if bucket not in _EXPORT_CATEGORIES:
            raise HTTPException(status_code=400, detail="category must be risky, invalid, or verified")
        return _list_by_category(
            db,
            category=bucket,
            page=page,
            page_size=page_size,
            search=search,
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


_EXPORT_CATEGORIES = {
    "risky": "risky",
    "invalid": "invalid",
    "verified": "verified",
}


def verification_export_bucket(
    quality: str | None,
    result: str | None,
    log_statuses: set[str] | None = None,
) -> str | None:
    """Place one address in risky, invalid, or verified.

    Risky wins over invalid, and both win over verified, so an address is
    never listed in more than one download.
    """
    statuses = log_statuses or set()
    label = classify_cached_verification(quality, result)
    if label == DISPLAY_RISKY or "risky" in statuses:
        return "risky"
    if label == DISPLAY_BAD or "invalid_email" in statuses:
        return "invalid"
    allowed = _allowed_verification_results()
    if label == DISPLAY_GOOD or (result or "").strip().lower() in allowed:
        return "verified"
    return None


def _collect_verification_export(db: Session) -> list[dict]:
    """One row per address that has a verification result or a blocked send."""
    by_email: dict[str, dict] = {}

    for row in db.query(EmailVerification).all():
        email = (row.email or "").strip()
        key = email.lower()
        if not key:
            continue
        by_email[key] = {
            "email": email,
            "name": "",
            "company": "",
            "result": row.result or "",
            "quality": row.quality or "",
            "statuses": set(),
            "latest_sent_at": None,
            "latest_campaign": "",
        }

    log_rows = (
        db.query(Recipient.name, Recipient.email, EmailLog.status, EmailLog.sent_at, Campaign.campaign_name)
        .join(Recipient, Recipient.id == EmailLog.recipient_id)
        .join(Campaign, Campaign.id == EmailLog.campaign_id)
        .order_by(EmailLog.sent_at.desc())
        .all()
    )
    for name, email, status, sent_at, campaign_name in log_rows:
        raw_email = (email or "").strip()
        key = raw_email.lower()
        if not key:
            continue
        entry = by_email.get(key)
        if entry is None:
            entry = {
                "email": raw_email,
                "name": "",
                "company": "",
                "result": "",
                "quality": "",
                "statuses": set(),
                "latest_sent_at": None,
                "latest_campaign": "",
            }
            by_email[key] = entry
        if name and not entry["name"]:
            entry["name"] = name.strip()
        if status:
            entry["statuses"].add(status)
        if sent_at and (entry["latest_sent_at"] is None or sent_at > entry["latest_sent_at"]):
            entry["latest_sent_at"] = sent_at
            entry["latest_campaign"] = campaign_name or ""

    if by_email:
        name_rows = (
            db.query(Recipient.email, Recipient.name, Recipient.company)
            .filter(func.lower(Recipient.email).in_(list(by_email)))
            .all()
        )
        for email, name, company in name_rows:
            entry = by_email.get((email or "").strip().lower())
            if not entry:
                continue
            if name and not entry["name"]:
                entry["name"] = name.strip()
            if company and not entry["company"]:
                entry["company"] = company.strip()

    exported: list[dict] = []
    for entry in by_email.values():
        bucket = verification_export_bucket(entry["quality"], entry["result"], entry["statuses"])
        if not bucket:
            continue
        exported.append(
            {
                "name": entry["name"],
                "email": entry["email"],
                "company": entry.get("company") or "",
                "status": _EXPORT_CATEGORIES[bucket],
                "result": entry["result"],
                "quality": entry["quality"],
                "latest_campaign": entry["latest_campaign"],
                "latest_sent_at": entry["latest_sent_at"],
                "_bucket": bucket,
                "_sort_name": (entry["name"] or entry["email"]).lower(),
            }
        )
    exported.sort(key=lambda row: (row["_sort_name"], row["email"].lower()))
    return exported


_BUCKET_LOG_STATUS = {
    "risky": "risky",
    "invalid": "invalid_email",
    "verified": "sent",
}


def _list_by_category(
    db: Session,
    *,
    category: str,
    page: int,
    page_size: int,
    search: str,
) -> EmailLogListResponse:
    """One row per address in the chosen verification bucket."""
    rows = [row for row in _collect_verification_export(db) if row["_bucket"] == category]
    term = (search or "").strip().lower()
    if term:
        rows = [
            row
            for row in rows
            if term in (row["name"] or "").lower()
            or term in (row["email"] or "").lower()
            or term in (row["latest_campaign"] or "").lower()
        ]

    total = len(rows)
    page_rows = rows[(page - 1) * page_size : page * page_size]
    keys = [(row["email"] or "").strip().lower() for row in page_rows if row["email"]]
    logs_by_email: dict[str, list[EmailLogResponse]] = {key: [] for key in keys}
    if keys:
        detail_rows = (
            _base_log_query(db)
            .filter(func.lower(Recipient.email).in_(keys))
            .order_by(EmailLog.sent_at.desc())
            .all()
        )
        for log, recipient, campaign, sender in detail_rows:
            key = (recipient.email or "").strip().lower()
            if key in logs_by_email:
                logs_by_email[key].append(_to_log_response(log, recipient, campaign, sender))

    groups: list[VerifiedEmailGroupResponse] = []
    for row in page_rows:
        key = (row["email"] or "").strip().lower()
        logs = logs_by_email.get(key) or []
        latest = logs[0] if logs else None
        groups.append(
            VerifiedEmailGroupResponse(
                group_key=key or row["email"],
                recipient_name=row["name"] or row["email"],
                recipient_email=row["email"],
                recipient_id=latest.recipient_id if latest else None,
                emails=[row["email"]] if row["email"] else [],
                email_count=1 if row["email"] else 0,
                send_count=len(logs),
                company=(row.get("company") or None) or (latest.recipient_company if latest else None),
                latest_sent_at=latest.sent_at if latest else row["latest_sent_at"],
                latest_status=latest.status if latest else _BUCKET_LOG_STATUS[category],
                latest_campaign_name=(latest.campaign_name if latest else None) or row["latest_campaign"] or None,
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


@router.get("/prospect", response_model=VerifiedEmailGroupResponse)
def get_prospect_sends(
    key: str = Query(..., min_length=1, description="Prospect email address"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Every send for one prospect, plus name, email, and company."""
    email_key = key.strip().lower()
    profile = (
        db.query(Recipient)
        .filter(func.lower(Recipient.email) == email_key)
        .order_by(Recipient.id.asc())
        .first()
    )
    detail_rows = (
        _base_log_query(db)
        .filter(func.lower(Recipient.email) == email_key)
        .order_by(EmailLog.sent_at.desc())
        .all()
    )
    logs = [
        _to_log_response(log, recipient, campaign, sender)
        for log, recipient, campaign, sender in detail_rows
    ]
    latest = logs[0] if logs else None
    if profile is None and latest is None:
        match = next(
            (
                row for row in _collect_verification_export(db)
                if (row["email"] or "").strip().lower() == email_key
            ),
            None,
        )
        if match is None:
            raise HTTPException(status_code=404, detail="Prospect not found")
        return VerifiedEmailGroupResponse(
            group_key=email_key,
            recipient_name=match["name"] or match["email"],
            recipient_email=match["email"],
            emails=[match["email"]] if match["email"] else [],
            email_count=1 if match["email"] else 0,
            send_count=0,
            company=match.get("company") or None,
            logs=[],
        )

    name = (
        (profile.name.strip() if profile and profile.name else None)
        or (latest.recipient_name if latest else None)
        or key.strip()
    )
    email = (profile.email if profile else None) or (latest.recipient_email if latest else None) or key.strip()
    company = (profile.company if profile else None) or (latest.recipient_company if latest else None)
    return VerifiedEmailGroupResponse(
        group_key=email_key,
        recipient_name=name,
        recipient_email=email,
        recipient_id=profile.id if profile else latest.recipient_id,
        emails=[email] if email else [],
        email_count=1 if email else 0,
        send_count=len(logs),
        company=company,
        latest_sent_at=latest.sent_at if latest else None,
        latest_status=latest.status if latest else None,
        latest_campaign_name=latest.campaign_name if latest else None,
        logs=logs,
    )


@router.get("/export")
def export_logs_by_verification(
    category: str = Query(..., description="risky, invalid, or verified"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Download every risky, invalid, or verified address as CSV."""
    bucket = (category or "").strip().lower()
    if bucket not in _EXPORT_CATEGORIES:
        raise HTTPException(status_code=400, detail="category must be risky, invalid, or verified")

    rows = [row for row in _collect_verification_export(db) if row["_bucket"] == bucket]
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["name", "email", "status", "result", "quality", "latest_campaign", "latest_sent_at"])
    for row in rows:
        writer.writerow(
            [
                row["name"],
                row["email"],
                row["status"],
                row["result"],
                row["quality"],
                row["latest_campaign"],
                row["latest_sent_at"].isoformat() if row["latest_sent_at"] else "",
            ]
        )
    buffer.seek(0)
    filename = f"{bucket}_emails.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
