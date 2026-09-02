"""ICP Database service — upsert from verified bulk items + list/search."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.icp.models import (
    ICP_STATUS_VERIFIED,
    SOURCE_LINKEDIN_BULK,
    SOURCE_MANUAL,
    IcpRecordRow,
)
from app.linkedin.bulk_models import BulkJobItemRow, ITEM_SUCCESS
from app.linkedin.validator import is_linkedin_in_profile_url, normalize_profile_url
from app.linkedin.verification import (
    VERIFY_RESOLVED,
    VERIFY_VERIFIED,
    normalize_company,
    normalize_name,
    original_fields,
)
from app.services.excel_service import _normalize_header

logger = logging.getLogger(__name__)

ELIGIBLE_STATUSES = {VERIFY_VERIFIED, VERIFY_RESOLVED}

INDUSTRY_ALIASES = {"industry", "vertical", "sector", "subvertical", "sub_vertical"}
COMPANY_SIZE_ALIASES = {
    "companysize",
    "company_size",
    "employees",
    "headcount",
    "size",
    "revenue_range",
}
WEBSITE_ALIASES = {"website", "companywebsite", "company_website", "companyurl", "web"}
TAGS_ALIASES = {"tags", "tag", "labels"}
EMAIL_ALIASES = {"email", "emailaddress", "email_address", "workemail", "work_email", "contactemail", "contact_email", "e_mail"}


def _pick_from_row(source: dict[str, Any] | None, aliases: set[str]) -> str | None:
    if not isinstance(source, dict):
        return None
    for key, value in source.items():
        if _normalize_header(str(key)) in aliases:
            text = str(value).strip() if value is not None else ""
            if text and text.lower() not in {"none", "nan", "null", "n/a", "-"}:
                return text
    return None


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"none", "nan", "null", "n/a", "-"}:
        return None
    return text


def _normalize_linkedin(url: str | None) -> str | None:
    raw = _clean(url)
    if not raw:
        return None
    try:
        if is_linkedin_in_profile_url(raw):
            return normalize_profile_url(raw)
    except Exception:
        pass
    return raw.rstrip("/").lower()


def _dedupe_key(name: str | None, company: str | None) -> str | None:
    n = normalize_name(name)
    c = normalize_company(company)
    if not n:
        return None
    return f"{n}|{c}" if c else n


def _prefer(*values: Any) -> str | None:
    for value in values:
        cleaned = _clean(value)
        if cleaned:
            return cleaned
    return None


def build_sheet_payload_from_bulk_item(item: BulkJobItemRow) -> dict[str, Any] | None:
    """Map uploaded spreadsheet columns to ICP fields (no extracted LinkedIn data)."""
    source_row = item.source_row_json if isinstance(item.source_row_json, dict) else {}
    if not source_row:
        return None

    originals = original_fields(source_row)
    name = _clean(originals.get("name"))
    email = _clean(originals.get("email") or _pick_from_row(source_row, EMAIL_ALIASES))
    company = _clean(originals.get("company"))
    designation = _clean(originals.get("designation"))
    location = _clean(originals.get("location"))
    linkedin_url = _normalize_linkedin(item.normalized_url or item.profile_url)

    if not email and not linkedin_url and not name:
        return None

    industry = _pick_from_row(source_row, INDUSTRY_ALIASES)
    company_size = _pick_from_row(source_row, COMPANY_SIZE_ALIASES)
    company_website = _pick_from_row(source_row, WEBSITE_ALIASES)

    tags_raw = _pick_from_row(source_row, TAGS_ALIASES)
    tags: list[str] | None = None
    if tags_raw:
        tags = [t.strip() for t in tags_raw.replace(";", ",").split(",") if t.strip()]

    now = datetime.now(timezone.utc)
    return {
        "name": name,
        "email": email,
        "company_name": company,
        "designation": designation,
        "about": None,
        "linkedin_url": linkedin_url,
        "industry": industry,
        "company_size": _clean(company_size),
        "location": location,
        "company_website": _clean(company_website),
        "icp_status": ICP_STATUS_VERIFIED,
        "icp_score": None,
        "tags": tags,
        "verification_status": VERIFY_VERIFIED,
        "verified_at": now,
        "source": SOURCE_LINKEDIN_BULK,
        "source_record_id": item.id,
        "source_job_id": item.job_id,
        "dedupe_key": _dedupe_key(name, company),
    }


def build_payload_from_bulk_item(item: BulkJobItemRow) -> dict[str, Any]:
    """Map verified bulk item fields to ICP columns. Never invent values."""
    originals = original_fields(item.source_row_json if isinstance(item.source_row_json, dict) else {})
    source_row = item.source_row_json if isinstance(item.source_row_json, dict) else {}

    name = _prefer(getattr(item, "resolved_name", None), item.name, originals.get("name"))
    company = _prefer(getattr(item, "resolved_company", None), item.company, originals.get("company"))
    designation = _prefer(
        getattr(item, "resolved_designation", None), item.designation, originals.get("designation")
    )
    location = _prefer(
        getattr(item, "resolved_location", None), item.location, originals.get("location")
    )
    email = originals.get("email") or _pick_from_row(source_row, EMAIL_ALIASES)
    about = _prefer(item.about, item.headline)
    linkedin_url = _normalize_linkedin(item.normalized_url or item.profile_url)

    industry = _pick_from_row(source_row, INDUSTRY_ALIASES)
    company_size = _pick_from_row(source_row, COMPANY_SIZE_ALIASES)
    company_website = _pick_from_row(source_row, WEBSITE_ALIASES)

    tags_raw = _pick_from_row(source_row, TAGS_ALIASES)
    tags: list[str] | None = None
    if tags_raw:
        tags = [t.strip() for t in tags_raw.replace(";", ",").split(",") if t.strip()]

    verified_at = getattr(item, "resolved_at", None) or item.completed_at or datetime.now(timezone.utc)
    status = (item.verification_status or VERIFY_VERIFIED).upper()
    if status not in ELIGIBLE_STATUSES:
        status = VERIFY_VERIFIED

    return {
        "name": name,
        "email": _clean(email),
        "company_name": company,
        "designation": designation,
        "about": about,
        "linkedin_url": linkedin_url,
        "industry": industry,
        "company_size": company_size,
        "location": location,
        "company_website": company_website,
        "icp_status": ICP_STATUS_VERIFIED,
        "icp_score": getattr(item, "verification_score", None) or None,
        "tags": tags,
        "verification_status": status,
        "verified_at": verified_at,
        "source": SOURCE_LINKEDIN_BULK,
        "source_record_id": item.id,
        "source_job_id": item.job_id,
        "dedupe_key": _dedupe_key(name, company),
    }


def item_eligible_for_icp(item: BulkJobItemRow) -> bool:
    if (item.status or "").upper() != ITEM_SUCCESS:
        return False
    return (item.verification_status or "").upper() in ELIGIBLE_STATUSES


def _find_existing(
    db: Session,
    *,
    user_id: int | None,
    linkedin_url: str | None,
    dedupe_key: str | None,
    source_record_id: int | None = None,
) -> IcpRecordRow | None:
    if linkedin_url:
        q = db.query(IcpRecordRow).filter(IcpRecordRow.linkedin_url == linkedin_url)
        if user_id is not None:
            q = q.filter(IcpRecordRow.user_id == user_id)
        found = q.first()
        if found:
            return found

    if source_record_id is not None:
        q = db.query(IcpRecordRow).filter(
            IcpRecordRow.source_record_id == source_record_id,
            IcpRecordRow.source == SOURCE_LINKEDIN_BULK,
        )
        if user_id is not None:
            q = q.filter(IcpRecordRow.user_id == user_id)
        found = q.first()
        if found:
            return found

    if dedupe_key and not linkedin_url:
        q = db.query(IcpRecordRow).filter(
            IcpRecordRow.dedupe_key == dedupe_key,
            or_(IcpRecordRow.linkedin_url.is_(None), IcpRecordRow.linkedin_url == ""),
        )
        if user_id is not None:
            q = q.filter(IcpRecordRow.user_id == user_id)
        return q.first()

    return None


def _apply_payload(row: IcpRecordRow, payload: dict[str, Any], *, create: bool) -> None:
    for key, value in payload.items():
        if value is None and not create:
            # Do not wipe existing ICP fields with missing incoming values
            continue
        setattr(row, key, value)
    row.updated_at = datetime.now(timezone.utc)


def upsert_icp_sheet_fields_from_bulk_item(
    db: Session,
    item: BulkJobItemRow,
    *,
    user_id: int | None,
) -> IcpRecordRow | None:
    """Upsert sheet-sourced fields (email, name, company, etc.) without waiting for LinkedIn extraction."""
    payload = build_sheet_payload_from_bulk_item(item)
    if not payload:
        return None

    existing = _find_existing(
        db,
        user_id=user_id,
        linkedin_url=payload.get("linkedin_url"),
        dedupe_key=payload.get("dedupe_key"),
        source_record_id=item.id,
    )

    if existing:
        payload.pop("source_job_id", None)
        payload.pop("source_record_id", None)
        _apply_payload(existing, payload, create=False)
        existing.user_id = user_id if user_id is not None else existing.user_id
        db.flush()
        logger.info("ICP sheet fields updated id=%s from bulk item=%s", existing.id, item.id)
        return existing

    row = IcpRecordRow(user_id=user_id, **payload)
    db.add(row)
    db.flush()
    logger.info("ICP created from sheet id=%s bulk item=%s", row.id, item.id)
    return row


def sync_sheet_fields_for_job(db: Session, job_id: str, *, user_id: int | None) -> int:
    """Persist spreadsheet fields (especially email) for every row in a bulk upload job."""
    items = (
        db.query(BulkJobItemRow)
        .filter(
            BulkJobItemRow.job_id == job_id,
            BulkJobItemRow.dedupe_of_id.is_(None),
        )
        .all()
    )
    synced = 0
    for item in items:
        if upsert_icp_sheet_fields_from_bulk_item(db, item, user_id=user_id):
            synced += 1
    return synced


def upsert_icp_from_bulk_item(
    db: Session,
    item: BulkJobItemRow,
    *,
    user_id: int | None,
) -> IcpRecordRow:
    """Create or update an ICP record from a verified/resolved bulk item.

    Raises ValueError if the item is not eligible.
    """
    if not item_eligible_for_icp(item):
        raise ValueError(
            f"Item {item.id} is not eligible for ICP "
            f"(status={item.status}, verification={item.verification_status})"
        )

    payload = build_payload_from_bulk_item(item)
    existing = _find_existing(
        db,
        user_id=user_id,
        linkedin_url=payload.get("linkedin_url"),
        dedupe_key=payload.get("dedupe_key"),
        source_record_id=item.id,
    )

    if existing:
        _apply_payload(existing, payload, create=False)
        existing.user_id = user_id if user_id is not None else existing.user_id
        db.flush()
        logger.info("ICP updated id=%s from bulk item=%s", existing.id, item.id)
        return existing

    row = IcpRecordRow(user_id=user_id, **payload)
    db.add(row)
    db.flush()
    logger.info("ICP created id=%s from bulk item=%s", row.id, item.id)
    return row


def sync_icp_if_eligible(
    db: Session,
    item: BulkJobItemRow,
    *,
    user_id: int | None,
) -> IcpRecordRow | None:
    """Upsert when eligible; return None when not eligible. Propagates upsert errors."""
    if not item_eligible_for_icp(item):
        return None
    return upsert_icp_from_bulk_item(db, item, user_id=user_id)


def serialize_icp(row: IcpRecordRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "name": row.name,
        "email": row.email,
        "company_name": row.company_name,
        "designation": row.designation,
        "about": row.about,
        "linkedin_url": row.linkedin_url,
        "industry": row.industry,
        "company_size": row.company_size,
        "location": row.location,
        "company_website": row.company_website,
        "icp_status": row.icp_status,
        "icp_score": row.icp_score,
        "tags": row.tags or [],
        "verification_status": row.verification_status,
        "verified_at": row.verified_at.isoformat() if row.verified_at else None,
        "source": row.source,
        "source_record_id": row.source_record_id,
        "source_job_id": row.source_job_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def list_icp_records(
    db: Session,
    *,
    user_id: int | None,
    search: str | None = None,
    industry: str | None = None,
    company: str | None = None,
    company_size: str | None = None,
    designation: str | None = None,
    location: str | None = None,
    icp_status: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    verified_from: datetime | None = None,
    verified_to: datetime | None = None,
    sort_by: str = "verified_at",
    sort_order: str = "desc",
    page: int = 1,
    page_size: int = 25,
) -> dict[str, Any]:
    query = db.query(IcpRecordRow)
    if user_id is not None:
        query = query.filter(IcpRecordRow.user_id == user_id)

    if search and search.strip():
        like = f"%{search.strip()}%"
        query = query.filter(
            or_(
                IcpRecordRow.name.ilike(like),
                IcpRecordRow.company_name.ilike(like),
                IcpRecordRow.designation.ilike(like),
                IcpRecordRow.industry.ilike(like),
                IcpRecordRow.about.ilike(like),
                IcpRecordRow.location.ilike(like),
                IcpRecordRow.email.ilike(like),
                IcpRecordRow.linkedin_url.ilike(like),
            )
        )

    if company:
        query = query.filter(IcpRecordRow.company_name.ilike(f"%{company.strip()}%"))
    if industry:
        query = query.filter(IcpRecordRow.industry.ilike(f"%{industry.strip()}%"))
    if company_size:
        query = query.filter(IcpRecordRow.company_size.ilike(f"%{company_size.strip()}%"))
    if designation:
        query = query.filter(IcpRecordRow.designation.ilike(f"%{designation.strip()}%"))
    if location:
        query = query.filter(IcpRecordRow.location.ilike(f"%{location.strip()}%"))
    if icp_status:
        query = query.filter(IcpRecordRow.icp_status == icp_status.strip().lower())

    if created_from:
        query = query.filter(IcpRecordRow.created_at >= created_from)
    if created_to:
        query = query.filter(IcpRecordRow.created_at <= created_to)
    if verified_from:
        query = query.filter(IcpRecordRow.verified_at >= verified_from)
    if verified_to:
        query = query.filter(IcpRecordRow.verified_at <= verified_to)

    sortable = {
        "name": IcpRecordRow.name,
        "company_name": IcpRecordRow.company_name,
        "designation": IcpRecordRow.designation,
        "industry": IcpRecordRow.industry,
        "verified_at": IcpRecordRow.verified_at,
        "created_at": IcpRecordRow.created_at,
        "updated_at": IcpRecordRow.updated_at,
        "icp_score": IcpRecordRow.icp_score,
    }
    col = sortable.get(sort_by, IcpRecordRow.verified_at)
    query = query.order_by(col.asc() if sort_order.lower() == "asc" else col.desc())

    total = query.count()
    page = max(int(page), 1)
    page_size = min(max(int(page_size), 1), 100)
    rows = query.offset((page - 1) * page_size).limit(page_size).all()

    return {
        "items": [serialize_icp(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_icp_record(db: Session, record_id: int, *, user_id: int | None) -> IcpRecordRow | None:
    q = db.query(IcpRecordRow).filter(IcpRecordRow.id == record_id)
    if user_id is not None:
        q = q.filter(IcpRecordRow.user_id == user_id)
    return q.first()


def create_icp_record(
    db: Session,
    *,
    user_id: int | None,
    data: dict[str, Any],
) -> IcpRecordRow:
    name = _clean(data.get("name"))
    company = _clean(data.get("company_name") or data.get("company"))
    linkedin_url = _normalize_linkedin(data.get("linkedin_url"))
    payload = {
        "name": name,
        "email": _clean(data.get("email")),
        "company_name": company,
        "designation": _clean(data.get("designation")),
        "about": _clean(data.get("about")),
        "linkedin_url": linkedin_url,
        "industry": _clean(data.get("industry")),
        "company_size": _clean(data.get("company_size")),
        "location": _clean(data.get("location")),
        "company_website": _clean(data.get("company_website")),
        "icp_status": (_clean(data.get("icp_status")) or ICP_STATUS_VERIFIED).lower(),
        "icp_score": data.get("icp_score"),
        "tags": data.get("tags") if isinstance(data.get("tags"), list) else None,
        "verification_status": (_clean(data.get("verification_status")) or VERIFY_VERIFIED).upper(),
        "verified_at": data.get("verified_at") or datetime.now(timezone.utc),
        "source": SOURCE_MANUAL,
        "source_record_id": None,
        "source_job_id": None,
        "dedupe_key": _dedupe_key(name, company),
    }

    existing = _find_existing(
        db,
        user_id=user_id,
        linkedin_url=linkedin_url,
        dedupe_key=payload["dedupe_key"],
    )
    if existing:
        _apply_payload(existing, payload, create=False)
        db.flush()
        return existing

    row = IcpRecordRow(user_id=user_id, **payload)
    db.add(row)
    db.flush()
    return row


def update_icp_record(
    db: Session,
    row: IcpRecordRow,
    data: dict[str, Any],
) -> IcpRecordRow:
    fields = (
        "name",
        "email",
        "company_name",
        "designation",
        "about",
        "industry",
        "company_size",
        "location",
        "company_website",
        "icp_status",
        "icp_score",
    )
    for key in fields:
        if key in data:
            setattr(row, key, _clean(data[key]) if key != "icp_score" else data[key])
    if "linkedin_url" in data:
        row.linkedin_url = _normalize_linkedin(data.get("linkedin_url"))
    if "tags" in data and isinstance(data["tags"], list):
        row.tags = data["tags"]
    if "company" in data and "company_name" not in data:
        row.company_name = _clean(data["company"])
    row.dedupe_key = _dedupe_key(row.name, row.company_name)
    row.updated_at = datetime.now(timezone.utc)
    db.flush()
    return row


def delete_icp_record(db: Session, row: IcpRecordRow) -> None:
    db.delete(row)
    db.flush()


def count_icp_records(db: Session, *, user_id: int | None) -> int:
    q = db.query(func.count(IcpRecordRow.id))
    if user_id is not None:
        q = q.filter(IcpRecordRow.user_id == user_id)
    return int(q.scalar() or 0)


def find_icp_by_linkedin_urls(
    db: Session,
    *,
    user_id: int | None,
    urls: list[str],
) -> dict[str, IcpRecordRow]:
    """Batch lookup of ICP records by normalized LinkedIn profile URL."""
    normalized = [_normalize_linkedin(u) for u in urls if u]
    normalized = [u for u in normalized if u]
    if not normalized:
        return {}
    q = db.query(IcpRecordRow).filter(IcpRecordRow.linkedin_url.in_(normalized))
    if user_id is not None:
        q = q.filter(IcpRecordRow.user_id == user_id)
    return {row.linkedin_url: row for row in q.all() if row.linkedin_url}


def _apply_icp_record_to_bulk_item(item: BulkJobItemRow, icp: IcpRecordRow, *, now: datetime) -> None:
    """Mark a bulk job item as satisfied from an existing ICP record (no extraction)."""
    from app.linkedin.bulk_models import ITEM_SUCCESS
    from app.linkedin.verification import VERIFY_ALREADY_EXISTS

    item.status = ITEM_SUCCESS
    item.name = icp.name
    item.company = icp.company_name
    item.designation = icp.designation
    item.about = icp.about
    item.location = icp.location
    item.verification_status = VERIFY_ALREADY_EXISTS
    item.verification_reason = "Profile already exists in ICP Database"
    item.verification_score = icp.icp_score if icp.icp_score is not None else 100
    item.last_error = None
    item.completed_at = now


def skip_job_items_already_in_icp(db: Session, job_id: str, *, user_id: int | None) -> int:
    """Skip extraction for canonical URLs already present in the ICP Database."""
    from app.linkedin.bulk_jobs import copy_canonical_results_to_duplicates, get_job_row, refresh_job_counters
    from app.linkedin.bulk_models import CLAIMABLE_ITEM_STATUSES, BulkJobItemRow

    job = get_job_row(db, job_id)
    job_created_at = getattr(job, "created_at", None) if job else None

    items = (
        db.query(BulkJobItemRow)
        .filter(
            BulkJobItemRow.job_id == job_id,
            BulkJobItemRow.dedupe_of_id.is_(None),
            BulkJobItemRow.status.in_(CLAIMABLE_ITEM_STATUSES),
        )
        .all()
    )
    if not items:
        return 0

    icp_map = find_icp_by_linkedin_urls(
        db, user_id=user_id, urls=[item.normalized_url for item in items]
    )
    if not icp_map:
        return 0

    now = datetime.now(timezone.utc)
    skipped = 0
    for item in items:
        icp = icp_map.get(item.normalized_url)
        if not icp:
            continue
        upsert_icp_sheet_fields_from_bulk_item(db, item, user_id=user_id)
        # Only skip LinkedIn extraction when the profile was already in ICP before this upload.
        if job_created_at and icp.created_at and icp.created_at < job_created_at:
            _apply_icp_record_to_bulk_item(item, icp, now=now)
            skipped += 1
            logger.info(
                "ICP skip job=%s item=%s url=%s icp_id=%s",
                job_id,
                item.id,
                item.normalized_url,
                icp.id,
            )

    if skipped:
        copy_canonical_results_to_duplicates(db, job_id)
        job = get_job_row(db, job_id)
        if job:
            refresh_job_counters(db, job)
    return skipped


def list_accounts_summary(
    db: Session,
    *,
    user_id: int | None,
    search: str | None = None,
    industry: str | None = None,
    page: int = 1,
    page_size: int = 25,
) -> dict[str, Any]:
    """Group existing ICP contacts by company — no separate accounts table."""
    base = db.query(IcpRecordRow).filter(
        IcpRecordRow.company_name.isnot(None),
        IcpRecordRow.company_name != "",
    )
    if user_id is not None:
        base = base.filter(IcpRecordRow.user_id == user_id)

    if search and search.strip():
        like = f"%{search.strip()}%"
        base = base.filter(
            or_(
                IcpRecordRow.company_name.ilike(like),
                IcpRecordRow.industry.ilike(like),
                IcpRecordRow.company_website.ilike(like),
                IcpRecordRow.location.ilike(like),
            )
        )
    if industry and industry.strip():
        base = base.filter(IcpRecordRow.industry.ilike(f"%{industry.strip()}%"))

    grouped = (
        base.with_entities(
            IcpRecordRow.company_name,
            func.count(IcpRecordRow.id).label("contact_count"),
            func.max(IcpRecordRow.industry).label("industry"),
            func.max(IcpRecordRow.company_size).label("company_size"),
            func.max(IcpRecordRow.location).label("location"),
            func.max(IcpRecordRow.company_website).label("company_website"),
        )
        .group_by(IcpRecordRow.company_name)
        .order_by(IcpRecordRow.company_name.asc())
    )

    subq = grouped.subquery()
    total = db.query(func.count()).select_from(subq).scalar() or 0

    page = max(int(page), 1)
    page_size = min(max(int(page_size), 1), 100)
    rows = grouped.offset((page - 1) * page_size).limit(page_size).all()

    items = [
        {
            "company_name": row.company_name,
            "industry": row.industry,
            "company_size": row.company_size,
            "location": row.location,
            "company_website": row.company_website,
            "contact_count": int(row.contact_count or 0),
            "status": "active",
        }
        for row in rows
    ]

    return {
        "items": items,
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }
