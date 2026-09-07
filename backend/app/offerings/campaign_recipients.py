"""Import offering match candidates into campaign recipients for send flows."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.icp.models import IcpRecordRow
from app.linkedin.bulk_models import BulkJobItemRow
from app.offerings.models import OfferingMatchRow
from app.services.campaign_service import CampaignService
from app.services.excel_service import ExcelService

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_EMAIL_KEYS = (
    "email",
    "Email",
    "EMAIL",
    "work_email",
    "Work Email",
    "fresh_mail",
    "Fresh Mail",
    "Fresh mail",
    "E-mail",
)


def _extract_email_from_row(data: dict[str, Any] | None) -> str | None:
    if not data:
        return None
    for key in _EMAIL_KEYS:
        raw = data.get(key)
        if raw is None:
            continue
        email = str(raw).strip().lower()
        if email and _EMAIL_RE.match(email):
            return email
    for key, raw in data.items():
        if "email" not in str(key).lower():
            continue
        email = str(raw).strip().lower()
        if email and _EMAIL_RE.match(email):
            return email
    return None


def _email_for_icp(db: Session, icp: IcpRecordRow) -> str | None:
    if icp.source_record_id:
        item = db.query(BulkJobItemRow).filter(BulkJobItemRow.id == icp.source_record_id).first()
        if item:
            email = _extract_email_from_row(item.source_row_json)
            if email:
                return email
    return None


def _icp_to_recipient(
    db: Session,
    excel_service: ExcelService,
    icp: IcpRecordRow,
    seen_emails: set[str],
    skipped: list[dict[str, str]],
    source: str,
) -> int | None:
    email = _email_for_icp(db, icp)
    if not email:
        skipped.append({
            "name": icp.name or "Unnamed",
            "reason": "No email on file — add email in your prospect sheet first",
        })
        return None
    if email in seen_emails:
        return None
    seen_emails.add(email)

    recipient_data = {
        "name": (icp.name or email).strip(),
        "email": email,
        "company": icp.company_name,
        "designation": icp.designation,
        "industry": icp.industry,
        "source": source,
    }
    recipient, _created = excel_service.create_single_recipient(db, recipient_data)
    return recipient.id


def prepare_campaign_recipients(
    db: Session,
    *,
    offering_id: int,
    match_ids: list[int],
    icp_record_ids: list[int],
    campaign_id: int,
    group_name: str | None = None,
) -> dict[str, Any]:
    """Create or reuse recipients from offering matches and/or ICP records."""
    if not match_ids and not icp_record_ids:
        return {"recipient_ids": [], "tagged": 0, "skipped": []}

    icp_ids: set[int] = set(icp_record_ids or [])
    match_icp_ids: set[int] = set()

    matches: list[OfferingMatchRow] = []
    if match_ids:
        matches = (
            db.query(OfferingMatchRow)
            .filter(
                OfferingMatchRow.offering_id == offering_id,
                OfferingMatchRow.id.in_(match_ids),
            )
            .all()
        )
        match_icp_ids = {m.icp_record_id for m in matches}
        icp_ids.update(match_icp_ids)

    if not icp_ids:
        return {"recipient_ids": [], "tagged": 0, "skipped": []}

    icp_rows = db.query(IcpRecordRow).filter(IcpRecordRow.id.in_(icp_ids)).all()
    icp_by_id = {row.id: row for row in icp_rows}

    excel_service = ExcelService()
    campaign_service = CampaignService()
    recipient_ids: list[int] = []
    skipped: list[dict[str, str]] = []
    seen_emails: set[str] = set()

    for icp_id in icp_ids:
        icp = icp_by_id.get(icp_id)
        if not icp:
            skipped.append({"name": "Unknown", "reason": "ICP record not found"})
            continue
        source = "offering_match" if icp_id in match_icp_ids else "icp_database"
        rid = _icp_to_recipient(db, excel_service, icp, seen_emails, skipped, source)
        if rid is not None:
            recipient_ids.append(rid)

    tagged = 0
    if recipient_ids:
        tagged = campaign_service.tag_recipients(
            db,
            campaign_id,
            recipient_ids,
            template_id=None,
            group_id=None,
        )
        if group_name and group_name.strip():
            from app.services.recipient_group_service import RecipientGroupService

            group = RecipientGroupService().get_or_create(db, group_name.strip())
            RecipientGroupService().add_members(db, group.id, recipient_ids)

    db.commit()
    return {
        "recipient_ids": recipient_ids,
        "tagged": tagged,
        "skipped": skipped,
    }
