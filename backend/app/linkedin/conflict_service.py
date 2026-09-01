"""Human-in-the-loop conflict resolution for bulk LinkedIn verification.

Never overwrites original uploaded values or extracted Apify values.
Stores resolved_* and audit rows separately.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.linkedin.bulk_models import (
    PHASE_COMPLETED,
    PHASE_REVIEW,
    BulkExtractJobRow,
    BulkJobItemRow,
    ConflictResolutionRow,
)
from app.linkedin.verification import (
    VERIFY_MISMATCH,
    VERIFY_RESOLVED,
    VERIFY_REVIEW,
    compare_field,
    original_fields,
)

RESOLVE_KEEP_UPLOADED = "KEEP_UPLOADED"
RESOLVE_KEEP_EXISTING = "KEEP_EXISTING"
RESOLVE_KEEP_EXTRACTED = "KEEP_EXTRACTED"
RESOLVE_MANUAL_EDIT = "MANUAL_EDIT"
RESOLVE_MARK_REVIEW = "MARK_REVIEW"

ALLOWED_RESOLUTIONS = {
    RESOLVE_KEEP_UPLOADED,
    RESOLVE_KEEP_EXISTING,
    RESOLVE_KEEP_EXTRACTED,
    RESOLVE_MANUAL_EDIT,
    RESOLVE_MARK_REVIEW,
}

RESOLUTION_LABELS = {
    RESOLVE_KEEP_UPLOADED: "kept uploaded value",
    RESOLVE_KEEP_EXISTING: "kept existing value",
    RESOLVE_KEEP_EXTRACTED: "kept extracted value",
    RESOLVE_MANUAL_EDIT: "manually edited value",
    RESOLVE_MARK_REVIEW: "marked for review",
}

COMPARE_FIELDS = ("name", "designation", "company", "location", "company_location")
RESOLVED_ATTR = {
    "name": "resolved_name",
    "designation": "resolved_designation",
    "company": "resolved_company",
    "location": "resolved_location",
    "company_location": "resolved_company_location",
}
EXTRACTED_ATTR = {
    "name": "name",
    "designation": "designation",
    "company": "company",
    "location": "location",
    # LinkedIn profile geo is person-level; company location is compared against it.
    "company_location": "location",
}


def canonicalize_resolution(resolution: str | None) -> str:
    value = (resolution or "").strip().upper()
    if value == RESOLVE_KEEP_EXISTING:
        return RESOLVE_KEEP_UPLOADED
    return value


def normalize_decisions(decisions: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for field, payload in (decisions or {}).items():
        if isinstance(payload, str):
            out[field] = {"resolution": canonicalize_resolution(payload), "edited_value": None}
        elif isinstance(payload, dict):
            out[field] = {
                "resolution": canonicalize_resolution(payload.get("resolution")),
                "edited_value": payload.get("edited_value"),
            }
        else:
            raise ValueError(f"Invalid decision for {field}")
    return out


def actor_display(user: Any | None, user_id: int | None = None) -> tuple[int | None, str | None, str | None, str]:
    uid = user_id
    name = None
    email = None
    if user is not None and not isinstance(user, (int, str)):
        uid = getattr(user, "id", None) if uid is None else uid
        name = (getattr(user, "name", None) or "").strip() or None
        email = (getattr(user, "email", None) or "").strip() or None
    label = name or email or (f"User {uid}" if uid is not None else "Unknown user")
    return uid, name, email, label


def build_change_summary(
    *,
    actor_label: str,
    field: str,
    uploaded: str | None,
    extracted: str | None,
    resolution: str,
    resolved_value: str | None,
) -> str:
    action = RESOLUTION_LABELS.get(resolution, resolution.replace("_", " ").lower())
    uploaded_text = uploaded or "—"
    extracted_text = extracted or "—"
    chosen = resolved_value or "—"
    if resolution == RESOLVE_MARK_REVIEW:
        return (
            f"{actor_label} marked {field} for review "
            f"(uploaded: {uploaded_text}; extracted: {extracted_text})"
        )
    if resolution == RESOLVE_MANUAL_EDIT:
        return (
            f"{actor_label} edited {field} to '{chosen}' "
            f"(uploaded: {uploaded_text}; extracted: {extracted_text})"
        )
    return (
        f"{actor_label} changed {field} from '{uploaded_text}' to '{chosen}' "
        f"({action}; extracted was '{extracted_text}')"
    )


def item_needs_review(item: BulkJobItemRow) -> bool:
    if getattr(item, "status", None) != "SUCCESS":
        return False
    status = (item.verification_status or "").upper()
    if status == VERIFY_RESOLVED:
        return False
    if conflicting_fields(item):
        return True
    if status in {VERIFY_MISMATCH, VERIFY_REVIEW, "NEEDS_REVIEW"}:
        # Status may be stale after country-only location rules; trust live conflicts.
        return False
    return False


def live_matches(item: BulkJobItemRow) -> dict[str, bool | None]:
    """Re-compare every field from the current values.

    Stored *_match flags are written once at extraction time and go stale when
    the comparison rules change, which is how identical values ended up being
    reported as differences. Nothing user-facing reads those columns anymore.
    """
    source = item.source_row_json if isinstance(item.source_row_json, dict) else {}
    originals = original_fields(source)
    return {
        field: compare_field(
            field,
            originals.get(field),
            getattr(item, EXTRACTED_ATTR[field], None),
            source_row=source,
        )
        for field in COMPARE_FIELDS
    }


def conflicting_fields(item: BulkJobItemRow) -> list[dict[str, Any]]:
    originals = original_fields(
        item.source_row_json if isinstance(item.source_row_json, dict) else {}
    )
    matches = live_matches(item)
    out: list[dict[str, Any]] = []
    for field in COMPARE_FIELDS:
        if matches[field] is not False:
            continue
        out.append(
            {
                "field": field,
                "uploaded": originals.get(field),
                "extracted": getattr(item, EXTRACTED_ATTR[field], None),
                "resolved": getattr(item, RESOLVED_ATTR[field], None),
            }
        )
    return out


def _field_has_resolution(db: Session, item_id: int, field: str) -> bool:
    return (
        db.query(ConflictResolutionRow.id)
        .filter(
            ConflictResolutionRow.job_item_id == item_id,
            ConflictResolutionRow.field == field,
            ConflictResolutionRow.resolution != RESOLVE_MARK_REVIEW,
        )
        .first()
        is not None
    )


def resolve_item_fields(
    db: Session,
    item: BulkJobItemRow,
    *,
    decisions: dict[str, Any],
    user_id: int | None,
    user: Any | None = None,
) -> BulkJobItemRow:
    """Apply per-field decisions. Does not mutate source_row_json or extracted columns."""
    originals = original_fields(
        item.source_row_json if isinstance(item.source_row_json, dict) else {}
    )
    now = datetime.now(timezone.utc)
    applied: list[str] = []
    actor_id, actor_name, actor_email, actor_label = actor_display(user, user_id)
    normalized = normalize_decisions(decisions)

    for field, payload in normalized.items():
        if field not in COMPARE_FIELDS:
            raise ValueError(f"Unknown field: {field}")
        resolution = payload["resolution"]
        if resolution not in ALLOWED_RESOLUTIONS and resolution != RESOLVE_KEEP_UPLOADED:
            raise ValueError(f"Invalid resolution: {resolution}")
        if resolution not in {
            RESOLVE_KEEP_UPLOADED,
            RESOLVE_KEEP_EXTRACTED,
            RESOLVE_MANUAL_EDIT,
            RESOLVE_MARK_REVIEW,
        }:
            raise ValueError(f"Invalid resolution: {resolution}")

        uploaded = originals.get(field)
        extracted = getattr(item, EXTRACTED_ATTR[field], None)
        edited_value = payload.get("edited_value")
        if isinstance(edited_value, str):
            edited_value = edited_value.strip() or None

        if resolution in {RESOLVE_KEEP_UPLOADED, RESOLVE_KEEP_EXISTING}:
            resolved_value = uploaded
            resolution = RESOLVE_KEEP_UPLOADED
        elif resolution == RESOLVE_KEEP_EXTRACTED:
            resolved_value = extracted
        elif resolution == RESOLVE_MANUAL_EDIT:
            if not edited_value:
                raise ValueError(f"edited_value is required for MANUAL_EDIT on {field}")
            resolved_value = edited_value
        else:
            resolved_value = None

        setattr(item, RESOLVED_ATTR[field], resolved_value)
        summary = build_change_summary(
            actor_label=actor_label,
            field=field,
            uploaded=uploaded,
            extracted=extracted,
            resolution=resolution,
            resolved_value=resolved_value,
        )
        row_kwargs: dict[str, Any] = dict(
            job_item_id=item.id,
            field=field,
            uploaded_value=uploaded,
            extracted_value=extracted,
            resolution=resolution,
            resolved_value=resolved_value,
            resolved_by=actor_id,
            resolved_by_name=actor_name,
            resolved_by_email=actor_email,
            change_summary=summary,
            resolved_at=now,
        )
        if hasattr(ConflictResolutionRow, "edited_value"):
            row_kwargs["edited_value"] = edited_value if resolution == RESOLVE_MANUAL_EDIT else None
        db.add(ConflictResolutionRow(**row_kwargs))
        applied.append(resolution)

    db.flush()

    remaining = [
        c["field"]
        for c in conflicting_fields(item)
        if not _field_has_resolution(db, item.id, c["field"])
    ]

    item.resolved_by = actor_id
    item.resolved_at = now
    if remaining:
        item.verification_status = VERIFY_REVIEW
        item.resolution_summary = "PARTIAL"
    elif any(r == RESOLVE_MARK_REVIEW for r in applied) or any(
        r.resolution == RESOLVE_MARK_REVIEW
        for r in db.query(ConflictResolutionRow)
        .filter(ConflictResolutionRow.job_item_id == item.id)
        .all()
    ):
        matches = live_matches(item)
        open_marked = [
            f
            for f in COMPARE_FIELDS
            if matches[f] is False and getattr(item, RESOLVED_ATTR[f], None) is None
        ]
        if open_marked:
            item.verification_status = VERIFY_REVIEW
            item.resolution_summary = RESOLVE_MARK_REVIEW
        else:
            item.verification_status = VERIFY_RESOLVED
            item.resolution_summary = ",".join(sorted(set(applied))) if applied else "RESOLVED"
    else:
        item.verification_status = VERIFY_RESOLVED
        item.resolution_summary = ",".join(sorted(set(applied))) if applied else "RESOLVED"
    return item


def refresh_job_after_resolutions(db: Session, job: BulkExtractJobRow) -> BulkExtractJobRow:
    from app.linkedin.bulk_jobs import refresh_job_counters

    refresh_job_counters(db, job)
    if job.status == "done":
        if (getattr(job, "needs_review_count", 0) or 0) > 0:
            job.phase = PHASE_REVIEW
        else:
            job.phase = PHASE_COMPLETED
    return job


def serialize_audit_row(row: ConflictResolutionRow, item: BulkJobItemRow | None = None) -> dict[str, Any]:
    item = item or getattr(row, "job_item", None)
    actor = row.resolved_by_name or row.resolved_by_email
    if not actor and row.resolved_by is not None:
        actor = f"User {row.resolved_by}"
    return {
        "id": row.id,
        "item_id": row.job_item_id,
        "source_row_number": getattr(item, "source_row_number", None) if item else None,
        "url": (getattr(item, "normalized_url", None) or getattr(item, "profile_url", None)) if item else None,
        "field": row.field,
        "uploaded_value": row.uploaded_value,
        "extracted_value": row.extracted_value,
        "edited_value": getattr(row, "edited_value", None),
        "resolution": row.resolution,
        "resolved_value": row.resolved_value,
        "resolved_by": row.resolved_by,
        "resolved_by_name": row.resolved_by_name,
        "resolved_by_email": row.resolved_by_email,
        "actor": actor or "Unknown user",
        "change_summary": row.change_summary
        or build_change_summary(
            actor_label=actor or "Unknown user",
            field=row.field,
            uploaded=row.uploaded_value,
            extracted=row.extracted_value,
            resolution=row.resolution or "",
            resolved_value=row.resolved_value,
        ),
        "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
    }


def list_job_audit(db: Session, job_id: str) -> list[dict[str, Any]]:
    rows = (
        db.query(ConflictResolutionRow, BulkJobItemRow)
        .join(BulkJobItemRow, BulkJobItemRow.id == ConflictResolutionRow.job_item_id)
        .filter(BulkJobItemRow.job_id == job_id)
        .order_by(ConflictResolutionRow.resolved_at.desc(), ConflictResolutionRow.id.desc())
        .all()
    )
    return [serialize_audit_row(resolution, item) for resolution, item in rows]


def audit_by_item_id(entries: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for entry in entries:
        grouped.setdefault(int(entry["item_id"]), []).append(entry)
    return grouped
