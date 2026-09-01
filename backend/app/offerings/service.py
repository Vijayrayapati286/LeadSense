"""Offering CRUD, serialization, and stats."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.offerings.models import (
    MATCH_STATUS_APPROVED,
    MATCH_STATUS_NEEDS_REVIEW,
    MATCH_STATUS_REJECTED,
    MATCH_TIER_GOOD,
    MATCH_TIER_POOR,
    MATCH_TIER_POTENTIAL,
    MATCH_TIER_STRONG,
    OfferingMatchRow,
    OfferingRow,
)
from app.offerings.embeddings import ensure_offering_embedding

DEFINITION_FIELDS = (
    "target_industries",
    "company_size_min",
    "company_size_max",
    "company_size_label",
    "revenue_min",
    "revenue_max",
    "target_geographies",
    "business_models",
    "target_departments",
    "target_job_titles",
    "target_seniority",
    "decision_maker_types",
    "buying_roles",
    "buyer_personas",
    "pain_points",
    "business_problems",
    "current_challenges",
    "use_cases",
    "desired_outcomes",
    "benefits",
    "must_have_rules",
    "nice_to_have_rules",
    "exclusion_rules",
    "positive_keywords",
    "negative_keywords",
)

LIST_FIELDS = (
    "target_industries",
    "target_geographies",
    "business_models",
    "target_departments",
    "target_job_titles",
    "target_seniority",
    "decision_maker_types",
    "buying_roles",
    "buyer_personas",
    "pain_points",
    "business_problems",
    "current_challenges",
    "use_cases",
    "desired_outcomes",
    "benefits",
    "must_have_rules",
    "nice_to_have_rules",
    "exclusion_rules",
    "positive_keywords",
    "negative_keywords",
)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _list_or_empty(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def compute_definition_hash(data: dict[str, Any]) -> str:
    payload = {k: data.get(k) for k in DEFINITION_FIELDS}
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def serialize_offering(row: OfferingRow, *, stats: dict[str, int] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": row.id,
        "user_id": row.user_id,
        "name": row.name,
        "short_description": row.short_description,
        "description": row.description,
        "product_type": row.product_type,
        "website_url": row.website_url,
        "target_industries": _list_or_empty(row.target_industries),
        "company_size_min": row.company_size_min,
        "company_size_max": row.company_size_max,
        "company_size_label": row.company_size_label,
        "revenue_min": row.revenue_min,
        "revenue_max": row.revenue_max,
        "target_geographies": _list_or_empty(row.target_geographies),
        "business_models": _list_or_empty(row.business_models),
        "target_departments": _list_or_empty(row.target_departments),
        "target_job_titles": _list_or_empty(row.target_job_titles),
        "target_seniority": _list_or_empty(row.target_seniority),
        "decision_maker_types": _list_or_empty(row.decision_maker_types),
        "buying_roles": _list_or_empty(row.buying_roles),
        "buyer_personas": _list_or_empty(row.buyer_personas),
        "pain_points": _list_or_empty(row.pain_points),
        "business_problems": _list_or_empty(row.business_problems),
        "current_challenges": _list_or_empty(row.current_challenges),
        "use_cases": _list_or_empty(row.use_cases),
        "desired_outcomes": _list_or_empty(row.desired_outcomes),
        "benefits": _list_or_empty(row.benefits),
        "must_have_rules": _list_or_empty(row.must_have_rules),
        "nice_to_have_rules": _list_or_empty(row.nice_to_have_rules),
        "exclusion_rules": _list_or_empty(row.exclusion_rules),
        "positive_keywords": _list_or_empty(row.positive_keywords),
        "negative_keywords": _list_or_empty(row.negative_keywords),
        "pricing_range": row.pricing_range,
        "hard_filter_rules": row.hard_filter_rules or {},
        "profile_text": row.profile_text,
        "status": row.status,
        "definition_version": row.definition_version or 1,
        "definition_hash": row.definition_hash,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }
    if stats:
        out.update(stats)
    return out


def get_offering(db: Session, offering_id: int, *, user_id: int | None) -> OfferingRow | None:
    q = db.query(OfferingRow).filter(OfferingRow.id == offering_id)
    if user_id is not None:
        q = q.filter(OfferingRow.user_id == user_id)
    return q.first()


def list_offerings(
    db: Session,
    *,
    user_id: int | None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 25,
) -> dict[str, Any]:
    q = db.query(OfferingRow)
    if user_id is not None:
        q = q.filter(OfferingRow.user_id == user_id)
    if search and search.strip():
        like = f"%{search.strip()}%"
        q = q.filter(
            or_(
                OfferingRow.name.ilike(like),
                OfferingRow.short_description.ilike(like),
                OfferingRow.description.ilike(like),
                OfferingRow.product_type.ilike(like),
            )
        )
    total = q.count()
    rows = (
        q.order_by(OfferingRow.updated_at.desc())
        .offset(max(0, (page - 1) * page_size))
        .limit(page_size)
        .all()
    )
    items = []
    for row in rows:
        stats = offering_match_counts(db, row.id)
        items.append(serialize_offering(row, stats=stats))
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def offering_match_counts(db: Session, offering_id: int) -> dict[str, int]:
    rows = (
        db.query(OfferingMatchRow.match_tier, OfferingMatchRow.status, func.count())
        .filter(OfferingMatchRow.offering_id == offering_id)
        .group_by(OfferingMatchRow.match_tier, OfferingMatchRow.status)
        .all()
    )
    total = 0
    strong = 0
    potential = 0
    approved = 0
    for tier, status, count in rows:
        c = int(count or 0)
        total += c
        if tier == MATCH_TIER_STRONG:
            strong += c
        elif tier in (MATCH_TIER_POTENTIAL, MATCH_TIER_GOOD):
            potential += c
        if status == MATCH_STATUS_APPROVED:
            approved += c
    return {
        "total_matches": total,
        "strong_matches": strong,
        "potential_matches": potential,
        "approved_matches": approved,
    }


def offering_stats(db: Session, offering_id: int) -> dict[str, int]:
    matches = db.query(OfferingMatchRow).filter(OfferingMatchRow.offering_id == offering_id).all()
    stats = {
        "total_candidates": len(matches),
        "strong_matches": 0,
        "potential_matches": 0,
        "poor_matches": 0,
        "approved": 0,
        "rejected": 0,
        "pending_review": 0,
        "needs_review": 0,
    }
    for m in matches:
        if m.match_tier == MATCH_TIER_STRONG:
            stats["strong_matches"] += 1
        elif m.match_tier in (MATCH_TIER_POTENTIAL, MATCH_TIER_GOOD):
            stats["potential_matches"] += 1
        else:
            stats["poor_matches"] += 1
        if m.status == MATCH_STATUS_APPROVED:
            stats["approved"] += 1
        elif m.status == MATCH_STATUS_REJECTED:
            stats["rejected"] += 1
        elif m.status == MATCH_STATUS_NEEDS_REVIEW:
            stats["needs_review"] += 1
            stats["pending_review"] += 1
        elif m.status in ("new", "ai_matched"):
            stats["pending_review"] += 1
    return stats


def _apply_fields(row: OfferingRow, data: dict[str, Any]) -> None:
    skip = {"id", "user_id", "created_at", "updated_at", "definition_version", "definition_hash"}
    for key, value in data.items():
        if key in skip or not hasattr(row, key):
            continue
        if key in LIST_FIELDS and value is None:
            continue
        setattr(row, key, value)


def create_offering(db: Session, *, user_id: int | None, data: dict[str, Any]) -> OfferingRow:
    payload = {k: v for k, v in data.items() if v is not None}
    if not payload.get("name"):
        raise ValueError("name is required")
    row = OfferingRow(user_id=user_id, definition_version=1)
    _apply_fields(row, payload)
    row.definition_hash = compute_definition_hash(serialize_offering(row))
    ensure_offering_embedding(row)
    db.add(row)
    db.flush()
    return row


def update_offering(db: Session, row: OfferingRow, data: dict[str, Any]) -> OfferingRow:
    before = compute_definition_hash(serialize_offering(row))
    payload = {k: v for k, v in data.items() if v is not None or k in LIST_FIELDS}
    _apply_fields(row, payload)
    after = compute_definition_hash(serialize_offering(row))
    row.definition_hash = after
    if after != before:
        row.definition_version = (row.definition_version or 1) + 1
        ensure_offering_embedding(row)
    db.flush()
    return row


def delete_offering(db: Session, row: OfferingRow) -> None:
    db.delete(row)
    db.flush()


def generated_to_offering_fields(generated: dict[str, Any]) -> dict[str, Any]:
    """Map AI generate payload into offering create/update fields."""
    cs = generated.get("company_size") or {}
    if hasattr(cs, "model_dump"):
        cs = cs.model_dump()
    return {
        "name": generated.get("suggested_name") or None,
        "short_description": generated.get("short_description"),
        "product_type": generated.get("product_type"),
        "target_industries": generated.get("industries") or [],
        "company_size_min": cs.get("min"),
        "company_size_max": cs.get("max"),
        "company_size_label": cs.get("label"),
        "target_geographies": generated.get("geographies") or [],
        "business_models": generated.get("business_models") or [],
        "target_departments": generated.get("departments") or [],
        "target_job_titles": generated.get("job_titles") or [],
        "target_seniority": generated.get("seniority") or [],
        "decision_maker_types": generated.get("decision_maker_types") or [],
        "buying_roles": generated.get("buying_roles") or [],
        "pain_points": generated.get("pain_points") or [],
        "business_problems": generated.get("business_problems") or [],
        "use_cases": generated.get("use_cases") or [],
        "desired_outcomes": generated.get("desired_outcomes") or [],
        "benefits": generated.get("benefits") or [],
        "positive_keywords": generated.get("positive_keywords") or [],
        "negative_keywords": generated.get("negative_keywords") or [],
        "must_have_rules": generated.get("must_have_rules") or [],
        "nice_to_have_rules": generated.get("nice_to_have_rules") or [],
        "exclusion_rules": generated.get("exclusion_rules") or [],
        "description": generated.get("description") or generated.get("detailed_description"),
        "pricing_range": generated.get("pricing_range"),
    }
