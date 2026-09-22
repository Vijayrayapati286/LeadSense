"""Org-scoped leads for SmartOps list/get/create/update."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import Lead

DEFAULT_STATUS = "open"


def _new_lead_id() -> str:
    return f"lead_{secrets.token_hex(12)}"


def _lead_query(db: Session, organization_id: str):
    return db.query(Lead).filter(Lead.organization_id == organization_id)


def list_leads(
    db: Session,
    organization_id: str,
    *,
    status: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[Lead], int]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 200)
    q = _lead_query(db, organization_id)
    if status:
        q = q.filter(Lead.status == status.strip())
    total = q.count()
    items = (
        q.order_by(Lead.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total


def get_lead(db: Session, organization_id: str, lead_id: str) -> Lead | None:
    return _lead_query(db, organization_id).filter(Lead.id == lead_id).first()


def create_lead(db: Session, organization_id: str, data: dict) -> Lead:
    title = (data.get("title") or "").strip()
    if not title:
        raise ValueError("title is required")
    row = Lead(
        id=_new_lead_id(),
        organization_id=organization_id,
        title=title,
        status=(data.get("status") or DEFAULT_STATUS).strip() or DEFAULT_STATUS,
        name=(data.get("name") or None),
        email=(data.get("email") or None),
        company=(data.get("company") or None),
        source=(data.get("source") or None),
        due_date=data.get("due_date"),
        notes=data.get("notes"),
        external_id=(data.get("external_id") or None),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_lead(db: Session, lead: Lead, data: dict) -> Lead:
    for field in ("title", "status", "name", "email", "company", "source", "notes", "external_id"):
        if field in data and data[field] is not None:
            value = data[field]
            if field in {"title", "status"} and isinstance(value, str):
                value = value.strip()
                if field == "title" and not value:
                    raise ValueError("title is required")
            setattr(lead, field, value)
    if "due_date" in data:
        lead.due_date = data["due_date"]
    lead.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(lead)
    return lead
