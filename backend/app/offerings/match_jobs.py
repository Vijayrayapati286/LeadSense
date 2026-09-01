"""Background matching job creation, claim, and progress."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.database.connection import SessionLocal
from app.offerings.models import (
    ITEM_FINAL_FAILED,
    ITEM_PROCESSING,
    ITEM_QUEUED,
    ITEM_SKIPPED,
    ITEM_SUCCESS,
    JOB_DONE,
    JOB_FAILED,
    JOB_PENDING,
    JOB_RUNNING,
    OfferingMatchJobItemRow,
    OfferingMatchJobRow,
    OfferingRow,
)
from app.offerings.matching_service import list_icp_ids_for_user

logger = logging.getLogger(__name__)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def serialize_job(job: OfferingMatchJobRow) -> dict[str, Any]:
    total = job.total_count or 0
    processed = job.processed_count or 0
    percent = int((processed / total) * 100) if total else (100 if job.status == JOB_DONE else 0)
    return {
        "job_id": job.id,
        "status": job.status,
        "total_count": total,
        "processed_count": processed,
        "strong_count": job.strong_count or 0,
        "potential_count": job.potential_count or 0,
        "poor_count": job.poor_count or 0,
        "error_count": job.error_count or 0,
        "percent": min(100, percent),
        "error": job.error,
        "started_at": _iso(job.started_at),
        "completed_at": _iso(job.completed_at),
    }


def create_match_job(
    db: Session,
    *,
    offering: OfferingRow,
    user_id: int | None,
    force: bool = False,
    verified_only: bool = True,
) -> OfferingMatchJobRow:
    # Cancel/ignore other running jobs for this offering by marking failed if still pending
    active = (
        db.query(OfferingMatchJobRow)
        .filter(
            OfferingMatchJobRow.offering_id == offering.id,
            OfferingMatchJobRow.status.in_([JOB_PENDING, JOB_RUNNING]),
        )
        .all()
    )
    for j in active:
        j.status = JOB_FAILED
        j.error = "Superseded by new matching job"
        j.completed_at = datetime.now(timezone.utc)

    icp_ids = list_icp_ids_for_user(db, user_id, verified_only=verified_only)
    job = OfferingMatchJobRow(
        id=str(uuid.uuid4()),
        offering_id=offering.id,
        user_id=user_id,
        status=JOB_PENDING,
        total_count=len(icp_ids),
        definition_version=offering.definition_version or 1,
    )
    db.add(job)
    db.flush()

    for icp_id in icp_ids:
        db.add(
            OfferingMatchJobItemRow(
                job_id=job.id,
                icp_record_id=icp_id,
                status=ITEM_QUEUED,
            )
        )
    db.flush()
    job._force = force  # type: ignore[attr-defined]
    return job


def refresh_job_counters(db: Session, job: OfferingMatchJobRow) -> None:
    items = db.query(OfferingMatchJobItemRow).filter(OfferingMatchJobItemRow.job_id == job.id).all()
    processed = 0
    errors = 0
    for it in items:
        if it.status in (ITEM_SUCCESS, ITEM_FINAL_FAILED, ITEM_SKIPPED):
            processed += 1
        if it.status == ITEM_FINAL_FAILED:
            errors += 1
    job.processed_count = processed
    job.error_count = errors
    # strong/potential/poor refreshed by runner from matches
    db.flush()


def claim_batch(db: Session, job_id: str, *, batch_size: int = 25) -> list[OfferingMatchJobItemRow]:
    items = (
        db.query(OfferingMatchJobItemRow)
        .filter(
            OfferingMatchJobItemRow.job_id == job_id,
            OfferingMatchJobItemRow.status == ITEM_QUEUED,
        )
        .limit(batch_size)
        .all()
    )
    now = datetime.now(timezone.utc)
    claimed = []
    for it in items:
        it.status = ITEM_PROCESSING
        it.attempts = (it.attempts or 0) + 1
        it.updated_at = now
        claimed.append(it)
    db.flush()
    return claimed


def get_latest_job(db: Session, offering_id: int) -> OfferingMatchJobRow | None:
    return (
        db.query(OfferingMatchJobRow)
        .filter(OfferingMatchJobRow.offering_id == offering_id)
        .order_by(OfferingMatchJobRow.created_at.desc())
        .first()
    )


def list_incomplete_match_job_ids() -> list[str]:
    db = SessionLocal()
    try:
        rows = (
            db.query(OfferingMatchJobRow.id)
            .filter(OfferingMatchJobRow.status.in_([JOB_PENDING, JOB_RUNNING]))
            .all()
        )
        return [r[0] for r in rows]
    finally:
        db.close()


def recover_stale_processing(db: Session, job_id: str) -> int:
    """Re-queue PROCESSING items so a resumed job can continue."""
    items = (
        db.query(OfferingMatchJobItemRow)
        .filter(
            OfferingMatchJobItemRow.job_id == job_id,
            OfferingMatchJobItemRow.status == ITEM_PROCESSING,
        )
        .all()
    )
    for it in items:
        it.status = ITEM_QUEUED
    db.flush()
    return len(items)
