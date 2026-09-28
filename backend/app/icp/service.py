"""ICP Database service — upsert from verified bulk items + list/search."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.icp.models import (
    ICP_STATUS_ACTIVE,
    ICP_STATUS_INCOMPLETE,
    ICP_STATUS_VERIFIED,
    SOURCE_LINKEDIN_BULK,
    SOURCE_MANUAL,
    IcpRecordRow,
)
from app.linkedin.bulk_models import BulkJobItemRow, ITEM_SUCCESS
from app.linkedin.validator import is_linkedin_in_profile_url, normalize_profile_url
from app.linkedin.verification import (
    VERIFY_ALREADY_EXISTS,
    VERIFY_NOT_VERIFIED,
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
    "employeecount",
    "employee_count",
    "headcount",
    "size",
    "revenue_range",
    "revenuerange",
}
WEBSITE_ALIASES = {"website", "companywebsite", "company_website", "companyurl", "web"}
TAGS_ALIASES = {"tags", "tag", "labels"}
EMAIL_ALIASES = {
    "email",
    "emailaddress",
    "email_address",
    "workemail",
    "work_email",
    "contactemail",
    "contact_email",
    "e_mail",
}
FIRST_NAME_ALIASES = {"firstname", "first", "givenname"}
LAST_NAME_ALIASES = {"lastname", "last", "surname", "familyname"}
DEPARTMENT_ALIASES = {"department", "dept", "division"}
PHONE_ALIASES = {"phone", "phoneno", "phonenumber", "mobile", "cellphone", "tel"}
CITY_ALIASES = {"city"}
STATE_ALIASES = {"state", "province", "contactstate"}
COUNTRY_ALIASES = {"country", "contactcountry"}
COUNTRY_CODE_ALIASES = {"countrycode", "countryiso", "iso"}
COMPANY_LINKEDIN_ALIASES = {
    "companylinkedin",
    "companylinkedinurl",
    "accountlinkedin",
    "accountlinkedinurl",
}
COMPANY_CITY_ALIASES = {"companycity", "accountcity"}
COMPANY_LOCATION_ALIASES = {
    "companylocation",
    "companyaddress",
    "accountlocation",
    "address",
}
ANNUAL_REVENUE_ALIASES = {"annualrevenue", "revenue", "companyrevenue"}
COMPANY_SUMMARY_ALIASES = {"companysummary", "accountsummary", "companyabout"}
CONTACT_SUMMARY_ALIASES = {"contactsummary", "summary", "bio"}

COUNTRY_CODES = {
    "united states": "US",
    "united states of america": "US",
    "usa": "US",
    "us": "US",
    "united kingdom": "GB",
    "uk": "GB",
    "england": "GB",
    "india": "IN",
    "canada": "CA",
    "australia": "AU",
    "germany": "DE",
    "france": "FR",
    "singapore": "SG",
    "united arab emirates": "AE",
    "uae": "AE",
    "netherlands": "NL",
    "ireland": "IE",
}

EXPORT_MAPPING_FIELDS = (
    "department",
    "phone",
    "city",
    "state",
    "country",
    "country_code",
    "contact_state",
    "contact_country",
    "company_linkedin_url",
    "company_location",
    "company_city",
    "annual_revenue",
    "company_summary",
    "account_linkedin_url",
    "account_city",
    "account_summary",
)


def resolve_org_id(
    db: Session,
    *,
    user_id: int | None = None,
    org_id: str | None = None,
) -> str | None:
    """Prefer explicit org_id; otherwise load the user's tenant."""
    if org_id:
        return str(org_id).strip() or None
    if user_id is None:
        return None
    from app.models import User

    row = db.query(User.org_id).filter(User.id == user_id).first()
    if not row:
        return None
    value = row[0]
    return str(value).strip() if value else None


def _apply_tenant_scope(query, *, org_id: str | None, user_id: int | None):
    """Scope ICP queries to the tenant when known; otherwise fall back to user."""
    if org_id:
        return query.filter(IcpRecordRow.org_id == org_id)
    if user_id is not None:
        return query.filter(IcpRecordRow.user_id == user_id)
    return query


def _org_member_user_ids(db: Session, org_id: str) -> list[int]:
    from app.models import User

    return [r[0] for r in db.query(User.id).filter(User.org_id == org_id).all()]


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


def _split_name(full_name: str | None) -> tuple[str | None, str | None]:
    parts = [p for p in str(full_name or "").strip().split() if p]
    if not parts:
        return None, None
    if len(parts) == 1:
        return parts[0], None
    return parts[0], " ".join(parts[1:])


def _parse_location(location: str | None) -> dict[str, str | None]:
    parts = [p.strip() for p in str(location or "").split(",") if p and p.strip()]
    if not parts:
        return {"city": None, "state": None, "country": None, "country_code": None}
    if len(parts) == 1:
        only = parts[0]
        code = COUNTRY_CODES.get(only.lower())
        if code:
            return {"city": None, "state": None, "country": only, "country_code": code}
        return {"city": only, "state": None, "country": None, "country_code": None}
    if len(parts) == 2:
        country = parts[1]
        return {
            "city": parts[0],
            "state": None,
            "country": country,
            "country_code": COUNTRY_CODES.get(country.lower()),
        }
    country = parts[-1]
    state = parts[-2]
    city = ", ".join(parts[:-2])
    return {
        "city": city,
        "state": state,
        "country": country,
        "country_code": COUNTRY_CODES.get(country.lower()),
    }


def _compose_name(first_name: str | None, last_name: str | None, fallback: str | None = None) -> str | None:
    joined = " ".join(p for p in (_clean(first_name), _clean(last_name)) if p)
    return joined or _clean(fallback)


def _enrich_export_mapping_fields(
    payload: dict[str, Any],
    source_row: dict[str, Any] | None = None,
    *,
    bulk_item: BulkJobItemRow | None = None,
) -> dict[str, Any]:
    """Fill CRM export columns from sheet / LinkedIn payload without inventing values."""
    source_row = source_row if isinstance(source_row, dict) else {}
    originals = original_fields(source_row) if source_row else {}

    # Sheet may send First/Last without a full name — compose name only (not stored separately).
    sheet_first = _prefer(
        payload.get("first_name"),
        _pick_from_row(source_row, FIRST_NAME_ALIASES),
    )
    sheet_last = _prefer(
        payload.get("last_name"),
        _pick_from_row(source_row, LAST_NAME_ALIASES),
    )
    name = _prefer(payload.get("name"), _compose_name(sheet_first, sheet_last))

    city = _prefer(payload.get("city"), _pick_from_row(source_row, CITY_ALIASES))
    state = _prefer(payload.get("state"), _pick_from_row(source_row, STATE_ALIASES))
    country = _prefer(payload.get("country"), _pick_from_row(source_row, COUNTRY_ALIASES))
    country_code = _prefer(
        payload.get("country_code"),
        _pick_from_row(source_row, COUNTRY_CODE_ALIASES),
    )

    location = _prefer(payload.get("location"))
    parsed = _parse_location(location)
    city = city or parsed["city"]
    state = state or parsed["state"]
    country = country or parsed["country"]
    country_code = country_code or parsed["country_code"]
    if country and not country_code:
        country_code = COUNTRY_CODES.get(country.lower())

    # If sheet had city/state/country but no composed location, rebuild it.
    if not location and any((city, state, country)):
        location = ", ".join(p for p in (city, state, country) if p)

    about = _prefer(payload.get("about"), _pick_from_row(source_row, CONTACT_SUMMARY_ALIASES))
    department = _prefer(payload.get("department"), _pick_from_row(source_row, DEPARTMENT_ALIASES))
    phone = _prefer(payload.get("phone"), _pick_from_row(source_row, PHONE_ALIASES))

    company_location = _prefer(
        payload.get("company_location"),
        getattr(bulk_item, "resolved_company_location", None) if bulk_item else None,
        originals.get("company_location"),
        _pick_from_row(source_row, COMPANY_LOCATION_ALIASES),
    )
    company_city = _prefer(
        payload.get("company_city"),
        _pick_from_row(source_row, COMPANY_CITY_ALIASES),
        _parse_location(company_location)["city"],
        company_location,
    )
    company_linkedin_url = _prefer(
        payload.get("company_linkedin_url"),
        _pick_from_row(source_row, COMPANY_LINKEDIN_ALIASES),
    )
    annual_revenue = _prefer(
        payload.get("annual_revenue"),
        _pick_from_row(source_row, ANNUAL_REVENUE_ALIASES),
    )
    company_summary = _prefer(
        payload.get("company_summary"),
        _pick_from_row(source_row, COMPANY_SUMMARY_ALIASES),
    )

    payload.update(
        {
            "name": name,
            "department": department,
            "phone": phone,
            "about": about,
            "location": location,
            "city": city,
            "state": state,
            "country": country,
            "country_code": country_code,
            "contact_state": state,
            "contact_country": country,
            "company_location": company_location,
            "company_city": company_city,
            "company_linkedin_url": company_linkedin_url,
            "annual_revenue": annual_revenue,
            "company_summary": company_summary,
            "account_city": company_city,
            "account_linkedin_url": company_linkedin_url,
            "account_summary": company_summary,
        }
    )
    # Do not persist transient sheet-only keys.
    payload.pop("first_name", None)
    payload.pop("last_name", None)
    return payload


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


def has_contact_identity(*, name: str | None) -> bool:
    """A contact is only 'verified' when we at least know who the person is."""
    return bool(_clean(name))


def resolve_icp_status(*, name: str | None, preferred: str | None = None) -> str:
    """Verified/active only with a real name; otherwise incomplete."""
    if not has_contact_identity(name=name):
        return ICP_STATUS_INCOMPLETE
    pref = (_clean(preferred) or "").lower()
    if pref in {ICP_STATUS_ACTIVE, ICP_STATUS_VERIFIED, ICP_STATUS_INCOMPLETE}:
        if pref == ICP_STATUS_INCOMPLETE:
            return ICP_STATUS_VERIFIED
        return pref
    return ICP_STATUS_VERIFIED


def effective_icp_status(row: IcpRecordRow) -> str:
    return resolve_icp_status(name=row.name, preferred=row.icp_status)


def repair_icp_status_if_needed(row: IcpRecordRow) -> bool:
    """Fix misleading verified labels on hollow records. Returns True if changed."""
    correct = effective_icp_status(row)
    if (row.icp_status or "").lower() == correct:
        return False
    row.icp_status = correct
    if correct == ICP_STATUS_INCOMPLETE:
        row.verified_at = None
    return True


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

    if not name:
        # Do not create hollow ICP rows from URL-only sheet uploads.
        return None

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
    payload = {
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
        "icp_score": None,
        "tags": tags,
        "source": SOURCE_LINKEDIN_BULK,
        "source_record_id": item.id,
        "source_job_id": item.job_id,
    }
    payload = _enrich_export_mapping_fields(payload, source_row, bulk_item=item)
    name = payload.get("name")
    icp_status = resolve_icp_status(name=name)
    complete = icp_status != ICP_STATUS_INCOMPLETE
    payload["icp_status"] = icp_status
    payload["verification_status"] = VERIFY_VERIFIED if complete else VERIFY_NOT_VERIFIED
    payload["verified_at"] = now if complete else None
    payload["dedupe_key"] = _dedupe_key(name, company)
    return payload


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
    image = _clean(getattr(item, "image", None))

    industry = _pick_from_row(source_row, INDUSTRY_ALIASES)
    company_size = _pick_from_row(source_row, COMPANY_SIZE_ALIASES)
    company_website = _pick_from_row(source_row, WEBSITE_ALIASES)

    tags_raw = _pick_from_row(source_row, TAGS_ALIASES)
    tags: list[str] | None = None
    if tags_raw:
        tags = [t.strip() for t in tags_raw.replace(";", ",").split(",") if t.strip()]

    verified_at = getattr(item, "resolved_at", None) or item.completed_at or datetime.now(timezone.utc)
    status = (item.verification_status or VERIFY_NOT_VERIFIED).upper()
    # Do not upgrade unverified / review rows to VERIFIED just because we sync extracted fields.
    if status not in ELIGIBLE_STATUSES and status != VERIFY_ALREADY_EXISTS:
        verified_at = None

    icp_status = resolve_icp_status(name=name)
    if icp_status == ICP_STATUS_INCOMPLETE:
        status = VERIFY_NOT_VERIFIED
        verified_at = None
    elif status in ELIGIBLE_STATUSES:
        pass
    else:
        # Extracted name is enough for a usable contact; keep bulk verify state separate.
        verified_at = None

    payload = {
        "name": name,
        "email": _clean(email),
        "company_name": company,
        "designation": designation,
        "about": about,
        "linkedin_url": linkedin_url,
        "image": image,
        "industry": industry,
        "company_size": company_size,
        "location": location,
        "company_website": company_website,
        "icp_status": icp_status,
        "icp_score": getattr(item, "verification_score", None) or None,
        "tags": tags,
        "verification_status": status,
        "verified_at": verified_at,
        "source": SOURCE_LINKEDIN_BULK,
        "source_record_id": item.id,
        "source_job_id": item.job_id,
    }
    payload = _enrich_export_mapping_fields(payload, source_row, bulk_item=item)
    payload["dedupe_key"] = _dedupe_key(payload.get("name"), company)
    return payload


def item_eligible_for_icp(item: BulkJobItemRow) -> bool:
    if (item.status or "").upper() != ITEM_SUCCESS:
        return False
    return (item.verification_status or "").upper() in ELIGIBLE_STATUSES


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    if isinstance(value, (list, dict)) and not value:
        return True
    return False


def _find_existing(
    db: Session,
    *,
    user_id: int | None,
    linkedin_url: str | None,
    dedupe_key: str | None,
    source_record_id: int | None = None,
    org_id: str | None = None,
) -> IcpRecordRow | None:
    org_id = resolve_org_id(db, user_id=user_id, org_id=org_id)

    if linkedin_url:
        q = db.query(IcpRecordRow).filter(IcpRecordRow.linkedin_url == linkedin_url)
        q = _apply_tenant_scope(q, org_id=org_id, user_id=user_id)
        found = q.first()
        if found:
            return found

    if source_record_id is not None:
        q = db.query(IcpRecordRow).filter(
            IcpRecordRow.source_record_id == source_record_id,
            IcpRecordRow.source == SOURCE_LINKEDIN_BULK,
        )
        q = _apply_tenant_scope(q, org_id=org_id, user_id=user_id)
        found = q.first()
        if found:
            return found

    if dedupe_key and not linkedin_url:
        q = db.query(IcpRecordRow).filter(
            IcpRecordRow.dedupe_key == dedupe_key,
            or_(IcpRecordRow.linkedin_url.is_(None), IcpRecordRow.linkedin_url == ""),
        )
        q = _apply_tenant_scope(q, org_id=org_id, user_id=user_id)
        return q.first()

    return None


def _apply_payload(row: IcpRecordRow, payload: dict[str, Any], *, create: bool) -> None:
    for key, value in payload.items():
        if value is None and not create:
            # Do not wipe existing ICP fields with missing incoming values
            continue
        setattr(row, key, value)
    row.updated_at = datetime.now(timezone.utc)


def _apply_payload_fill_empty(row: IcpRecordRow, payload: dict[str, Any]) -> None:
    """Write extracted LinkedIn fields only where the contact is currently blank."""
    for key, value in payload.items():
        if value is None:
            continue
        if _is_blank(getattr(row, key, None)):
            setattr(row, key, value)
    repair_icp_status_if_needed(row)
    row.updated_at = datetime.now(timezone.utc)


def upsert_icp_sheet_fields_from_bulk_item(
    db: Session,
    item: BulkJobItemRow,
    *,
    user_id: int | None,
    org_id: str | None = None,
) -> IcpRecordRow | None:
    """Upsert sheet-sourced fields (email, name, company, etc.) without waiting for LinkedIn extraction."""
    payload = build_sheet_payload_from_bulk_item(item)
    if not payload:
        return None

    org_id = resolve_org_id(db, user_id=user_id, org_id=org_id)
    existing = _find_existing(
        db,
        user_id=user_id,
        org_id=org_id,
        linkedin_url=payload.get("linkedin_url"),
        dedupe_key=payload.get("dedupe_key"),
        source_record_id=item.id,
    )

    if existing:
        payload.pop("source_job_id", None)
        payload.pop("source_record_id", None)
        _apply_payload(existing, payload, create=False)
        existing.user_id = user_id if user_id is not None else existing.user_id
        if org_id and not existing.org_id:
            existing.org_id = org_id
        db.flush()
        logger.info("ICP sheet fields updated id=%s from bulk item=%s", existing.id, item.id)
        return existing

    row = IcpRecordRow(user_id=user_id, org_id=org_id, **payload)
    db.add(row)
    db.flush()
    logger.info("ICP created from sheet id=%s bulk item=%s", row.id, item.id)
    return row


def sync_sheet_fields_for_job(
    db: Session, job_id: str, *, user_id: int | None, org_id: str | None = None
) -> int:
    """Persist spreadsheet fields (especially email) for every row in a bulk upload job."""
    org_id = resolve_org_id(db, user_id=user_id, org_id=org_id)
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
        if upsert_icp_sheet_fields_from_bulk_item(db, item, user_id=user_id, org_id=org_id):
            synced += 1
    return synced


def upsert_icp_from_bulk_item(
    db: Session,
    item: BulkJobItemRow,
    *,
    user_id: int | None,
    org_id: str | None = None,
    fill_empty_only: bool = False,
    require_verified: bool = True,
) -> IcpRecordRow:
    """Create or update an ICP record from a bulk item.

    When require_verified=True (default), only VERIFIED/RESOLVED items are accepted.
    When fill_empty_only=True, existing contacts keep sheet/user values; blank fields
    are filled from LinkedIn extraction (name, company, designation, location, about).
    """
    if require_verified and not item_eligible_for_icp(item):
        raise ValueError(
            f"Item {item.id} is not eligible for ICP "
            f"(status={item.status}, verification={item.verification_status})"
        )
    if not require_verified and (item.status or "").upper() != ITEM_SUCCESS:
        raise ValueError(
            f"Item {item.id} is not eligible for ICP extract sync (status={item.status})"
        )

    payload = build_payload_from_bulk_item(item)
    if not has_contact_identity(name=payload.get("name")):
        raise ValueError(f"Item {item.id} has no contact name — skipping hollow ICP create")

    org_id = resolve_org_id(db, user_id=user_id, org_id=org_id)
    existing = _find_existing(
        db,
        user_id=user_id,
        org_id=org_id,
        linkedin_url=payload.get("linkedin_url"),
        dedupe_key=payload.get("dedupe_key"),
        source_record_id=item.id,
    )

    if existing:
        if fill_empty_only:
            _apply_payload_fill_empty(existing, payload)
        else:
            _apply_payload(existing, payload, create=False)
        existing.user_id = user_id if user_id is not None else existing.user_id
        if org_id and not existing.org_id:
            existing.org_id = org_id
        db.flush()
        logger.info(
            "ICP updated id=%s from bulk item=%s fill_empty_only=%s",
            existing.id,
            item.id,
            fill_empty_only,
        )
        return existing

    row = IcpRecordRow(user_id=user_id, org_id=org_id, **payload)
    db.add(row)
    db.flush()
    logger.info("ICP created id=%s from bulk item=%s", row.id, item.id)
    return row


def sync_icp_if_eligible(
    db: Session,
    item: BulkJobItemRow,
    *,
    user_id: int | None,
    org_id: str | None = None,
) -> IcpRecordRow | None:
    """Upsert when verified/resolved; return None when not eligible."""
    if not item_eligible_for_icp(item):
        return None
    try:
        return upsert_icp_from_bulk_item(db, item, user_id=user_id, org_id=org_id)
    except ValueError as exc:
        if "no contact name" in str(exc).lower():
            logger.info("ICP sync skipped item_id=%s: %s", item.id, exc)
            return None
        raise


def sync_icp_after_extraction(
    db: Session,
    item: BulkJobItemRow,
    *,
    user_id: int | None,
    org_id: str | None = None,
) -> IcpRecordRow | None:
    """Push extracted LinkedIn fields into Contacts after a successful extraction.

    - VERIFIED / RESOLVED → full upsert (prefer resolved > extracted > sheet)
    - Otherwise → create contact or fill only blank fields (never overwrite sheet values)
    - ALREADY_EXISTS → skip (contact already present from pre-check)
    """
    if (item.status or "").upper() != ITEM_SUCCESS:
        return None
    vs = (item.verification_status or "").upper()
    if vs == VERIFY_ALREADY_EXISTS:
        return None
    fill_empty_only = vs not in ELIGIBLE_STATUSES
    try:
        return upsert_icp_from_bulk_item(
            db,
            item,
            user_id=user_id,
            org_id=org_id,
            fill_empty_only=fill_empty_only,
            require_verified=False,
        )
    except ValueError as exc:
        if "no contact name" in str(exc).lower() or "not eligible" in str(exc).lower():
            logger.info("ICP extract sync skipped item_id=%s: %s", item.id, exc)
            return None
        raise


def serialize_icp(row: IcpRecordRow) -> dict[str, Any]:
    status = effective_icp_status(row)
    return {
        "id": row.id,
        "user_id": row.user_id,
        "org_id": getattr(row, "org_id", None),
        "name": row.name,
        "email": row.email,
        "company_name": row.company_name,
        "designation": row.designation,
        "department": getattr(row, "department", None),
        "about": row.about,
        "linkedin_url": row.linkedin_url,
        "phone": getattr(row, "phone", None),
        "image": getattr(row, "image", None),
        "industry": row.industry,
        "company_size": row.company_size,
        "location": row.location,
        "city": getattr(row, "city", None),
        "state": getattr(row, "state", None),
        "country": getattr(row, "country", None),
        "country_code": getattr(row, "country_code", None),
        "contact_state": getattr(row, "contact_state", None),
        "contact_country": getattr(row, "contact_country", None),
        "company_website": row.company_website,
        "company_linkedin_url": getattr(row, "company_linkedin_url", None),
        "company_location": getattr(row, "company_location", None),
        "company_city": getattr(row, "company_city", None),
        "annual_revenue": getattr(row, "annual_revenue", None),
        "company_summary": getattr(row, "company_summary", None),
        "account_linkedin_url": getattr(row, "account_linkedin_url", None),
        "account_city": getattr(row, "account_city", None),
        "account_summary": getattr(row, "account_summary", None),
        "icp_status": status,
        "icp_score": row.icp_score,
        "tags": row.tags or [],
        "verification_status": row.verification_status,
        "verified_at": row.verified_at.isoformat() if row.verified_at and status != ICP_STATUS_INCOMPLETE else None,
        "source": row.source,
        "source_record_id": row.source_record_id,
        "source_job_id": row.source_job_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _without_company_filter():
    return or_(IcpRecordRow.company_name.is_(None), IcpRecordRow.company_name == "")


def _missing_name_filter():
    return or_(IcpRecordRow.name.is_(None), IcpRecordRow.name == "")


def _has_name_filter():
    return and_(IcpRecordRow.name.isnot(None), IcpRecordRow.name != "")


def purge_empty_icp_records(
    db: Session, *, user_id: int | None, org_id: str | None = None
) -> int:
    """Delete ICP contacts that have no person name (hollow upload shells)."""
    org_id = resolve_org_id(db, user_id=user_id, org_id=org_id)
    q = db.query(IcpRecordRow).filter(_missing_name_filter())
    q = _apply_tenant_scope(q, org_id=org_id, user_id=user_id)
    rows = q.all()
    deleted = len(rows)
    for row in rows:
        db.delete(row)
    if deleted:
        db.flush()
        logger.info(
            "Purged %s empty ICP contact(s) org_id=%s user_id=%s",
            deleted,
            org_id,
            user_id,
        )
    return deleted


def backfill_icp_export_mapping_fields(
    db: Session,
    *,
    user_id: int | None = None,
    org_id: str | None = None,
    limit: int | None = None,
) -> int:
    """Fill null CRM export columns from name/location and linked bulk source rows."""
    org_id = resolve_org_id(db, user_id=user_id, org_id=org_id)
    q = db.query(IcpRecordRow)
    q = _apply_tenant_scope(q, org_id=org_id, user_id=user_id)
    q = q.order_by(IcpRecordRow.id.asc())
    if limit is not None:
        q = q.limit(max(int(limit), 1))

    updated = 0
    bulk_cache: dict[int, BulkJobItemRow | None] = {}
    for row in q.all():
        bulk_item = None
        source_row = None
        if row.source_record_id is not None:
            if row.source_record_id not in bulk_cache:
                bulk_cache[row.source_record_id] = (
                    db.query(BulkJobItemRow)
                    .filter(BulkJobItemRow.id == row.source_record_id)
                    .first()
                )
            bulk_item = bulk_cache[row.source_record_id]
            if bulk_item and isinstance(bulk_item.source_row_json, dict):
                source_row = bulk_item.source_row_json

        before = {key: getattr(row, key, None) for key in EXPORT_MAPPING_FIELDS}
        enriched = _enrich_export_mapping_fields(
            {
                "name": row.name,
                "location": row.location,
                "city": row.city,
                "state": row.state,
                "country": row.country,
                "country_code": row.country_code,
                "about": row.about,
                "department": row.department,
                "phone": row.phone,
                "company_location": row.company_location,
                "company_city": row.company_city,
                "company_linkedin_url": row.company_linkedin_url,
                "annual_revenue": row.annual_revenue,
                "company_summary": row.company_summary,
            },
            source_row,
            bulk_item=bulk_item,
        )

        changed = False
        for key in EXPORT_MAPPING_FIELDS:
            new_val = enriched.get(key)
            if _is_blank(before.get(key)) and not _is_blank(new_val):
                setattr(row, key, new_val)
                changed = True
        if enriched.get("name") and _is_blank(row.name):
            row.name = enriched["name"]
            changed = True
        if enriched.get("location") and _is_blank(row.location):
            row.location = enriched["location"]
            changed = True
        if changed:
            row.updated_at = datetime.now(timezone.utc)
            updated += 1

    if updated:
        db.flush()
        logger.info(
            "ICP export-mapping backfill updated %s row(s) org_id=%s user_id=%s",
            updated,
            org_id,
            user_id,
        )
    return updated


def backfill_icp_from_extracted_items(
    db: Session,
    *,
    user_id: int | None,
    org_id: str | None = None,
    limit: int = 500,
) -> int:
    """Create/fill Contacts from SUCCESS bulk items that already have LinkedIn extraction data."""
    from app.linkedin.bulk_models import BulkExtractJobRow

    org_id = resolve_org_id(db, user_id=user_id, org_id=org_id)
    q = (
        db.query(BulkJobItemRow)
        .join(BulkExtractJobRow, BulkExtractJobRow.id == BulkJobItemRow.job_id)
        .filter(
            BulkJobItemRow.status == ITEM_SUCCESS,
            BulkJobItemRow.dedupe_of_id.is_(None),
            BulkJobItemRow.name.isnot(None),
            BulkJobItemRow.name != "",
        )
        .order_by(BulkJobItemRow.id.desc())
    )
    if org_id:
        member_ids = _org_member_user_ids(db, org_id)
        if member_ids:
            q = q.filter(BulkExtractJobRow.user_id.in_(member_ids))
        elif user_id is not None:
            q = q.filter(BulkExtractJobRow.user_id == user_id)
    elif user_id is not None:
        q = q.filter(BulkExtractJobRow.user_id == user_id)

    synced = 0
    for item in q.limit(max(int(limit), 1)).all():
        try:
            owner_id = user_id
            try:
                from app.linkedin.bulk_models import BulkExtractJobRow as _Job

                job_row = db.query(_Job.user_id).filter(_Job.id == item.job_id).first()
                if job_row and job_row[0] is not None:
                    owner_id = job_row[0]
            except Exception:
                pass
            if sync_icp_after_extraction(db, item, user_id=owner_id, org_id=org_id):
                synced += 1
        except Exception:
            logger.exception("ICP backfill failed for bulk item %s", item.id)
    if synced:
        logger.info(
            "ICP backfill synced %s contact(s) org_id=%s user_id=%s",
            synced,
            org_id,
            user_id,
        )
    return synced


def list_icp_records(
    db: Session,
    *,
    user_id: int | None,
    org_id: str | None = None,
    search: str | None = None,
    industry: str | None = None,
    company: str | None = None,
    company_size: str | None = None,
    designation: str | None = None,
    location: str | None = None,
    icp_status: str | None = None,
    without_company: bool = False,
    require_name: bool = True,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    verified_from: datetime | None = None,
    verified_to: datetime | None = None,
    sort_by: str = "verified_at",
    sort_order: str = "desc",
    page: int = 1,
    page_size: int = 25,
) -> dict[str, Any]:
    org_id = resolve_org_id(db, user_id=user_id, org_id=org_id)
    query = db.query(IcpRecordRow)
    query = _apply_tenant_scope(query, org_id=org_id, user_id=user_id)

    if require_name:
        query = query.filter(_has_name_filter())

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

    if without_company:
        query = query.filter(_without_company_filter())
    elif company:
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
    ascending = sort_order.lower() == "asc"
    try:
        ordered = col.asc().nullslast() if ascending else col.desc().nullslast()
    except Exception:
        ordered = col.asc() if ascending else col.desc()
    query = query.order_by(ordered)

    total = query.count()
    page = max(int(page), 1)
    page_size = min(max(int(page_size), 1), 100)
    rows = query.offset((page - 1) * page_size).limit(page_size).all()
    repaired = False
    for row in rows:
        if repair_icp_status_if_needed(row):
            repaired = True
    if repaired:
        db.flush()

    return {
        "items": [serialize_icp(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_icp_record(
    db: Session,
    record_id: int,
    *,
    user_id: int | None,
    org_id: str | None = None,
) -> IcpRecordRow | None:
    org_id = resolve_org_id(db, user_id=user_id, org_id=org_id)
    q = db.query(IcpRecordRow).filter(IcpRecordRow.id == record_id)
    q = _apply_tenant_scope(q, org_id=org_id, user_id=user_id)
    return q.first()


def create_icp_record(
    db: Session,
    *,
    user_id: int | None,
    data: dict[str, Any],
    org_id: str | None = None,
) -> IcpRecordRow:
    company = _clean(data.get("company_name") or data.get("company"))
    linkedin_url = _normalize_linkedin(data.get("linkedin_url"))
    org_id = resolve_org_id(db, user_id=user_id, org_id=org_id)
    payload = _enrich_export_mapping_fields(
        {
            "name": _clean(data.get("name")),
            "email": _clean(data.get("email")),
            "company_name": company,
            "designation": _clean(data.get("designation")),
            "department": _clean(data.get("department")),
            "about": _clean(data.get("about")),
            "linkedin_url": linkedin_url,
            "phone": _clean(data.get("phone")),
            "image": _clean(data.get("image")),
            "industry": _clean(data.get("industry")),
            "company_size": _clean(data.get("company_size")),
            "location": _clean(data.get("location")),
            "city": _clean(data.get("city")),
            "state": _clean(data.get("state")),
            "country": _clean(data.get("country")),
            "country_code": _clean(data.get("country_code")),
            "company_website": _clean(data.get("company_website")),
            "company_linkedin_url": _clean(data.get("company_linkedin_url")),
            "company_location": _clean(data.get("company_location")),
            "company_city": _clean(data.get("company_city")),
            "annual_revenue": _clean(data.get("annual_revenue")),
            "company_summary": _clean(data.get("company_summary")),
            "icp_score": data.get("icp_score"),
            "tags": data.get("tags") if isinstance(data.get("tags"), list) else None,
            "source": SOURCE_MANUAL,
            "source_record_id": None,
            "source_job_id": None,
        }
    )
    name = payload.get("name")
    icp_status = resolve_icp_status(name=name, preferred=data.get("icp_status"))
    payload["icp_status"] = icp_status
    payload["verification_status"] = (
        (_clean(data.get("verification_status")) or VERIFY_VERIFIED).upper()
        if icp_status != ICP_STATUS_INCOMPLETE
        else VERIFY_NOT_VERIFIED
    )
    payload["verified_at"] = (
        None
        if icp_status == ICP_STATUS_INCOMPLETE
        else (data.get("verified_at") or datetime.now(timezone.utc))
    )
    payload["dedupe_key"] = _dedupe_key(name, company)

    existing = _find_existing(
        db,
        user_id=user_id,
        org_id=org_id,
        linkedin_url=linkedin_url,
        dedupe_key=payload["dedupe_key"],
    )
    if existing:
        _apply_payload(existing, payload, create=False)
        if org_id and not existing.org_id:
            existing.org_id = org_id
        db.flush()
        return existing

    row = IcpRecordRow(user_id=user_id, org_id=org_id, **payload)
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
        "department",
        "about",
        "phone",
        "image",
        "industry",
        "company_size",
        "location",
        "city",
        "state",
        "country",
        "country_code",
        "company_website",
        "company_linkedin_url",
        "company_location",
        "company_city",
        "annual_revenue",
        "company_summary",
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

    enriched = _enrich_export_mapping_fields(
        {
            "name": row.name,
            "location": row.location,
            "city": row.city,
            "state": row.state,
            "country": row.country,
            "country_code": row.country_code,
            "about": row.about,
            "department": row.department,
            "phone": row.phone,
            "company_location": row.company_location,
            "company_city": row.company_city,
            "company_linkedin_url": row.company_linkedin_url,
            "annual_revenue": row.annual_revenue,
            "company_summary": row.company_summary,
        }
    )
    for key in EXPORT_MAPPING_FIELDS:
        setattr(row, key, enriched.get(key))
    if enriched.get("name"):
        row.name = enriched["name"]
    if enriched.get("location"):
        row.location = enriched["location"]

    row.dedupe_key = _dedupe_key(row.name, row.company_name)
    row.icp_status = resolve_icp_status(name=row.name, preferred=row.icp_status)
    if row.icp_status == ICP_STATUS_INCOMPLETE:
        row.verified_at = None
        if not row.verification_status or row.verification_status.upper() == VERIFY_VERIFIED:
            row.verification_status = VERIFY_NOT_VERIFIED
    elif not row.verified_at:
        row.verified_at = datetime.now(timezone.utc)
    row.updated_at = datetime.now(timezone.utc)
    db.flush()
    return row


def delete_icp_record(db: Session, row: IcpRecordRow) -> None:
    db.delete(row)
    db.flush()


def count_icp_records(
    db: Session,
    *,
    user_id: int | None,
    org_id: str | None = None,
    without_company: bool = False,
    require_name: bool = True,
) -> int:
    org_id = resolve_org_id(db, user_id=user_id, org_id=org_id)
    q = db.query(func.count(IcpRecordRow.id))
    q = _apply_tenant_scope(q, org_id=org_id, user_id=user_id)
    if require_name:
        q = q.filter(_has_name_filter())
    if without_company:
        q = q.filter(_without_company_filter())
    return int(q.scalar() or 0)


def icp_counts_summary(
    db: Session, *, user_id: int | None, org_id: str | None = None
) -> dict[str, int]:
    org_id = resolve_org_id(db, user_id=user_id, org_id=org_id)
    purged = purge_empty_icp_records(db, user_id=user_id, org_id=org_id)
    return {
        "total": count_icp_records(db, user_id=user_id, org_id=org_id, require_name=True),
        "without_account": count_icp_records(
            db, user_id=user_id, org_id=org_id, without_company=True, require_name=True
        ),
        "purged_empty": purged,
    }


def find_icp_by_linkedin_urls(
    db: Session,
    *,
    user_id: int | None,
    urls: list[str],
    org_id: str | None = None,
) -> dict[str, IcpRecordRow]:
    """Batch lookup of ICP records by normalized LinkedIn profile URL."""
    org_id = resolve_org_id(db, user_id=user_id, org_id=org_id)
    normalized = [_normalize_linkedin(u) for u in urls if u]
    normalized = [u for u in normalized if u]
    if not normalized:
        return {}
    q = db.query(IcpRecordRow).filter(IcpRecordRow.linkedin_url.in_(normalized))
    q = _apply_tenant_scope(q, org_id=org_id, user_id=user_id)
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


def skip_job_items_already_in_icp(
    db: Session, job_id: str, *, user_id: int | None, org_id: str | None = None
) -> int:
    """Skip extraction for canonical URLs already present in the ICP Database."""
    from app.linkedin.bulk_jobs import copy_canonical_results_to_duplicates, get_job_row, refresh_job_counters
    from app.linkedin.bulk_models import CLAIMABLE_ITEM_STATUSES, BulkJobItemRow

    org_id = resolve_org_id(db, user_id=user_id, org_id=org_id)
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
        db, user_id=user_id, org_id=org_id, urls=[item.normalized_url for item in items]
    )
    if not icp_map:
        return 0

    now = datetime.now(timezone.utc)
    skipped = 0
    for item in items:
        icp = icp_map.get(item.normalized_url)
        if not icp:
            continue
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
    org_id: str | None = None,
    search: str | None = None,
    industry: str | None = None,
    page: int = 1,
    page_size: int = 25,
) -> dict[str, Any]:
    """Group existing ICP contacts by company — no separate accounts table."""
    org_id = resolve_org_id(db, user_id=user_id, org_id=org_id)
    base = db.query(IcpRecordRow).filter(
        IcpRecordRow.company_name.isnot(None),
        IcpRecordRow.company_name != "",
    )
    base = _apply_tenant_scope(base, org_id=org_id, user_id=user_id)

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
            func.max(IcpRecordRow.company_location).label("company_location"),
            func.max(IcpRecordRow.company_city).label("company_city"),
            func.max(IcpRecordRow.account_city).label("account_city"),
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
            "company_location": row.company_location,
            "company_city": row.company_city or row.account_city,
            "account_city": row.account_city or row.company_city,
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


def add_job_verified_items_to_icp(
    db: Session,
    job_id: str,
    *,
    user_id: int | None,
    org_id: str | None = None,
) -> dict[str, Any]:
    """Upsert all VERIFIED / RESOLVED bulk items for a job into the tenant ICP pool."""
    org_id = resolve_org_id(db, user_id=user_id, org_id=org_id)
    items = (
        db.query(BulkJobItemRow)
        .filter(
            BulkJobItemRow.job_id == job_id,
            BulkJobItemRow.dedupe_of_id.is_(None),
            BulkJobItemRow.status == ITEM_SUCCESS,
            func.upper(BulkJobItemRow.verification_status).in_(
                [VERIFY_VERIFIED, VERIFY_RESOLVED]
            ),
        )
        .order_by(BulkJobItemRow.source_row_number.asc())
        .all()
    )

    added = 0
    updated = 0
    skipped = 0
    errors: list[dict[str, Any]] = []
    record_ids: list[int] = []

    for item in items:
        try:
            before = _find_existing(
                db,
                user_id=user_id,
                org_id=org_id,
                linkedin_url=_normalize_linkedin(
                    getattr(item, "normalized_url", None) or getattr(item, "profile_url", None)
                ),
                dedupe_key=_dedupe_key(getattr(item, "name", None), getattr(item, "company", None)),
                source_record_id=item.id,
            )
            row = upsert_icp_from_bulk_item(
                db,
                item,
                user_id=user_id,
                org_id=org_id,
                fill_empty_only=False,
                require_verified=True,
            )
            if row is None:
                skipped += 1
                continue
            record_ids.append(row.id)
            if before is not None and before.id == row.id:
                updated += 1
            else:
                added += 1
        except ValueError as exc:
            skipped += 1
            errors.append({"item_id": item.id, "error": str(exc)})
        except Exception as exc:
            logger.exception("Add-to-ICP failed job=%s item=%s", job_id, item.id)
            errors.append({"item_id": item.id, "error": str(exc)})

    db.flush()
    return {
        "job_id": job_id,
        "eligible": len(items),
        "added": added,
        "updated": updated,
        "skipped": skipped,
        "icp_record_ids": record_ids,
        "errors": errors[:25],
        "org_id": org_id,
    }
