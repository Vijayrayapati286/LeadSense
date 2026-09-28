"""SmartOps → LeadSense offering upsert (PAT, org-scoped, multi-doc)."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.offerings.models import OFFERING_STATUS_ACTIVE, OfferingDocumentRow, OfferingRow

ALLOWED_FILE_FORMATS = {"pdf", "docx", "pptx", "txt"}


def new_offering_id() -> str:
    return f"ls_off_{secrets.token_hex(12)}"


def _parse_created_at(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _normalize_format(value: str | None, *, required: bool = False) -> str | None:
    if value is None or str(value).strip() == "":
        if required:
            raise ValueError(f"file_format must be one of: {', '.join(sorted(ALLOWED_FILE_FORMATS))}")
        return None
    fmt = str(value).strip().lower().lstrip(".")
    if fmt not in ALLOWED_FILE_FORMATS:
        raise ValueError(f"file_format must be one of: {', '.join(sorted(ALLOWED_FILE_FORMATS))}")
    return fmt


def _doc_count(db: Session, offering_id: str | None) -> int:
    if not offering_id:
        return 0
    return db.query(OfferingDocumentRow).filter(OfferingDocumentRow.offering_id == offering_id).count()


def serialize_sync_offering(row: OfferingRow, *, doc_count: int | None = None) -> dict[str, Any]:
    created = row.created_at
    if created is not None and created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    count = doc_count if doc_count is not None else (row.doc_count or 0)
    return {
        "offering_id": row.offering_id,
        "organization_id": row.organization_id,
        "name": row.name,
        "status": row.status or OFFERING_STATUS_ACTIVE,
        "doc_count": count,
        "created_at": created.isoformat() if created else None,
    }


def get_by_smartops_id(db: Session, organization_id: str, smartops_offering_id: str) -> OfferingRow | None:
    return (
        db.query(OfferingRow)
        .filter(
            OfferingRow.organization_id == organization_id,
            OfferingRow.smartops_offering_id == smartops_offering_id,
        )
        .first()
    )


def get_by_public_id(db: Session, organization_id: str, offering_id: str) -> OfferingRow | None:
    return (
        db.query(OfferingRow)
        .filter(
            OfferingRow.organization_id == organization_id,
            OfferingRow.offering_id == offering_id,
        )
        .first()
    )


def list_sync_offerings(db: Session, organization_id: str) -> list[dict[str, Any]]:
    rows = (
        db.query(OfferingRow)
        .filter(OfferingRow.organization_id == organization_id)
        .order_by(OfferingRow.created_at.desc())
        .all()
    )
    return [serialize_sync_offering(row, doc_count=_doc_count(db, row.offering_id)) for row in rows]


def _incoming_docs(data: dict[str, Any], *, public_offering_id: str) -> list[dict[str, Any]]:
    raw = data.get("docs")
    if isinstance(raw, list) and raw:
        return [item if isinstance(item, dict) else {} for item in raw]
    # v1 fallback: single top-level file
    file_name = (data.get("file_name") or "").strip()
    if not file_name:
        return []
    return [
        {
            "doc_id": f"legacy_{public_offering_id}",
            "file_name": file_name,
            "file_format": data.get("file_format"),
            "s3_key": (data.get("s3_key") or data.get("file_url") or "").strip() or None,
            "created_at": data.get("created_at"),
        }
    ]


def _upsert_documents(db: Session, offering_id: str, docs: list[dict[str, Any]]) -> int:
    for item in docs:
        doc_id = str(item.get("doc_id") or "").strip()
        file_name = str(item.get("file_name") or "").strip()
        if not doc_id:
            raise ValueError("each document requires doc_id")
        if not file_name:
            raise ValueError("each document requires file_name")
        file_format = _normalize_format(item.get("file_format"), required=True)
        s3_key = str(item.get("s3_key") or item.get("file_url") or "").strip() or None
        created_at = _parse_created_at(item.get("created_at"))
        row = db.query(OfferingDocumentRow).filter(OfferingDocumentRow.doc_id == doc_id).first()
        if row:
            row.offering_id = offering_id
            row.file_name = file_name
            row.file_format = file_format or row.file_format
            row.s3_key = s3_key if s3_key is not None else row.s3_key
            continue
        db.add(
            OfferingDocumentRow(
                doc_id=doc_id,
                offering_id=offering_id,
                file_name=file_name,
                file_format=file_format or "pdf",
                s3_key=s3_key,
                created_at=created_at,
            )
        )
    db.flush()
    return _doc_count(db, offering_id)


def upsert_from_smartops(
    db: Session,
    *,
    organization_id: str,
    data: dict[str, Any],
    owner_user_id: int | None = None,
    existing: OfferingRow | None = None,
) -> tuple[OfferingRow, bool]:
    """Create or update an offering from SmartOps. Returns (row, created)."""
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("name is required")
    smartops_id = (data.get("smartops_offering_id") or "").strip()
    if not smartops_id:
        raise ValueError("smartops_offering_id is required")

    if existing is None:
        existing = get_by_smartops_id(db, organization_id, smartops_id)

    created = existing is None
    row = existing or OfferingRow(
        offering_id=new_offering_id(),
        organization_id=organization_id,
        smartops_offering_id=smartops_id,
        user_id=owner_user_id,
        definition_version=1,
        status=OFFERING_STATUS_ACTIVE,
        product_type="Document",
        doc_count=0,
    )
    row.name = name
    description = (data.get("description") or "").strip() or None
    row.description = description
    row.short_description = description[:500] if description else None
    row.status = (data.get("status") or row.status or OFFERING_STATUS_ACTIVE).strip() or OFFERING_STATUS_ACTIVE
    if not row.offering_id:
        row.offering_id = new_offering_id()
    if not row.organization_id:
        row.organization_id = organization_id
    if owner_user_id and not row.user_id:
        row.user_id = owner_user_id
    created_at = _parse_created_at(data.get("created_at"))
    if created and created_at is not None:
        row.created_at = created_at

    if created:
        db.add(row)
    db.flush()

    docs = _incoming_docs(data, public_offering_id=row.offering_id or "")
    stored = _upsert_documents(db, row.offering_id, docs) if docs else _doc_count(db, row.offering_id)
    declared = data.get("doc_count")
    try:
        declared_n = int(declared) if declared is not None else stored
    except (TypeError, ValueError):
        declared_n = stored
    row.doc_count = max(declared_n, stored)
    if docs:
        first = docs[0]
        row.file_name = str(first.get("file_name") or "").strip() or row.file_name
        row.file_format = _normalize_format(first.get("file_format")) or row.file_format
        row.file_url = str(first.get("s3_key") or first.get("file_url") or "").strip() or row.file_url
    db.flush()
    return row, created
