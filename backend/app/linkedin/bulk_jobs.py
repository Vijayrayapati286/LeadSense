"""Persistent bulk LinkedIn extraction jobs (PostgreSQL / SQLite)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from sqlalchemy import and_, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.connection import DATABASE_URL, SessionLocal
from app.config import get_settings
from app.linkedin.bulk_models import (
    CLAIMABLE_ITEM_STATUSES,
    ITEM_FINAL_FAILED,
    ITEM_PENDING,
    ITEM_PROCESSING,
    ITEM_QUEUED,
    ITEM_RETRY_WAIT,
    ITEM_SUCCESS,
    PHASE_COMPARING,
    PHASE_COMPLETED,
    PHASE_EXTRACTING,
    PHASE_UPLOADING,
    TERMINAL_ITEM_STATUSES,
    BulkExtractJobRow,
    BulkJobItemRow,
    ExtractionAttemptRow,
)
from app.linkedin.verification import (
    VERIFY_MISMATCH,
    VERIFY_REVIEW,
    VERIFY_VERIFIED,
    apply_verification,
)

BulkJobStatus = Literal["pending", "running", "done", "failed"]


@dataclass
class BulkExtractJob:
    """API-facing snapshot of a persisted bulk job."""

    job_id: str
    user_id: int | None
    status: BulkJobStatus = "pending"
    total: int = 0
    completed: int = 0
    failed: int = 0
    retrying: int = 0
    verified: int = 0
    mismatched: int = 0
    review: int = 0
    phase: str = "uploading"
    excel_finalized: bool = False
    total_batches: int = 0
    completed_batches: int = 0
    excel_file: str | None = None
    error: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    created_at: str = ""
    updated_at: str = ""


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def derive_phase(job: BulkExtractJobRow) -> str:
    if job.status in {"done", "failed"}:
        return PHASE_COMPLETED
    if job.status == "pending":
        return PHASE_UPLOADING
    processed = (job.processed_count or 0)
    total = job.total_urls or 0
    if processed >= total and total > 0:
        return PHASE_COMPARING
    if (job.success_count or 0) > 0:
        return PHASE_EXTRACTING
    return PHASE_EXTRACTING


def job_row_to_snapshot(job: BulkExtractJobRow) -> BulkExtractJob:
    processed = (job.success_count or 0) + (job.failed_count or 0)
    return BulkExtractJob(
        job_id=job.id,
        user_id=job.user_id,
        status=job.status if job.status in {"pending", "running", "done", "failed"} else "running",
        total=job.total_urls or 0,
        completed=job.success_count or 0,
        failed=job.failed_count or 0,
        retrying=job.retrying_count or 0,
        verified=job.verified_count or 0,
        mismatched=job.mismatch_count or 0,
        review=job.review_count or 0,
        phase=job.phase or derive_phase(job),
        excel_finalized=bool(job.excel_finalized),
        total_batches=0,
        completed_batches=0,
        excel_file=job.result_file_path,
        error=job.error,
        started_at=_iso(job.created_at) if job.status != "pending" else _iso(job.created_at),
        completed_at=_iso(job.completed_at),
        created_at=_iso(job.created_at) or "",
        updated_at=_iso(job.updated_at) or "",
    )


def refresh_job_counters(db: Session, job: BulkExtractJobRow) -> BulkExtractJobRow:
    success = (
        db.query(func.count(BulkJobItemRow.id))
        .filter(BulkJobItemRow.job_id == job.id, BulkJobItemRow.status == ITEM_SUCCESS)
        .scalar()
        or 0
    )
    failed = (
        db.query(func.count(BulkJobItemRow.id))
        .filter(BulkJobItemRow.job_id == job.id, BulkJobItemRow.status == ITEM_FINAL_FAILED)
        .scalar()
        or 0
    )
    retrying = (
        db.query(func.count(BulkJobItemRow.id))
        .filter(
            BulkJobItemRow.job_id == job.id,
            BulkJobItemRow.status.in_(
                (ITEM_PENDING, ITEM_QUEUED, ITEM_PROCESSING, ITEM_RETRY_WAIT)
            ),
        )
        .scalar()
        or 0
    )
    verified = (
        db.query(func.count(BulkJobItemRow.id))
        .filter(
            BulkJobItemRow.job_id == job.id,
            BulkJobItemRow.verification_status == VERIFY_VERIFIED,
        )
        .scalar()
        or 0
    )
    mismatched = (
        db.query(func.count(BulkJobItemRow.id))
        .filter(
            BulkJobItemRow.job_id == job.id,
            BulkJobItemRow.verification_status == VERIFY_MISMATCH,
        )
        .scalar()
        or 0
    )
    review = (
        db.query(func.count(BulkJobItemRow.id))
        .filter(
            BulkJobItemRow.job_id == job.id,
            BulkJobItemRow.verification_status == VERIFY_REVIEW,
        )
        .scalar()
        or 0
    )
    total = (
        db.query(func.count(BulkJobItemRow.id)).filter(BulkJobItemRow.job_id == job.id).scalar() or 0
    )
    job.success_count = int(success)
    job.failed_count = int(failed)
    job.retrying_count = int(retrying)
    job.verified_count = int(verified)
    job.mismatch_count = int(mismatched)
    job.review_count = int(review)
    job.processed_count = int(success) + int(failed)
    job.total_urls = int(total)
    job.phase = derive_phase(job)
    job.updated_at = datetime.now(timezone.utc)
    return job


def create_job_with_items(
    *,
    user_id: int | None,
    original_file_name: str | None,
    input_columns: list[str],
    url_rows: list[dict[str, Any]],
) -> BulkExtractJobRow:
    db = SessionLocal()
    try:
        job = BulkExtractJobRow(
            id=str(uuid.uuid4()),
            user_id=user_id,
            original_file_name=original_file_name,
            input_columns=input_columns,
            total_urls=len(url_rows),
            status="pending",
            phase=PHASE_UPLOADING,
            excel_finalized=False,
        )
        db.add(job)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            job = BulkExtractJobRow(
                id=str(uuid.uuid4()),
                user_id=None,
                original_file_name=original_file_name,
                input_columns=input_columns,
                total_urls=len(url_rows),
                status="pending",
                phase=PHASE_UPLOADING,
                excel_finalized=False,
            )
            db.add(job)
            db.flush()

        first_by_url: dict[str, BulkJobItemRow] = {}
        for entry in url_rows:
            normalized = (entry.get("normalized_url") or "").strip()
            raw = (entry.get("raw_url") or "").strip()
            if "is_valid" in entry:
                valid = bool(entry.get("is_valid"))
            else:
                valid = bool(normalized)
            canonical = first_by_url.get(normalized) if normalized else None
            item = BulkJobItemRow(
                job_id=job.id,
                source_row_number=int(entry.get("source_row_number") or entry.get("row_index") or 0),
                profile_url=raw or normalized,
                normalized_url=normalized,
                source_row_json=entry.get("source_row_json") or {},
                status=ITEM_QUEUED,
                attempt_count=0,
            )
            if not valid or not normalized:
                item.status = ITEM_FINAL_FAILED
                item.last_error = entry.get("error") or "Invalid LinkedIn profile URL"
                item.completed_at = datetime.now(timezone.utc)
            elif canonical is not None:
                item.status = ITEM_PENDING
            db.add(item)
            db.flush()
            if canonical is not None and valid and normalized:
                item.dedupe_of_id = canonical.id
            elif valid and normalized:
                first_by_url[normalized] = item

        refresh_job_counters(db, job)
        db.commit()
        db.refresh(job)
        return job
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_job(job_id: str) -> BulkExtractJob | None:
    db = SessionLocal()
    try:
        job = db.query(BulkExtractJobRow).filter(BulkExtractJobRow.id == job_id).first()
        if not job:
            return None
        refresh_job_counters(db, job)
        db.commit()
        return job_row_to_snapshot(job)
    finally:
        db.close()


def get_job_row(db: Session, job_id: str) -> BulkExtractJobRow | None:
    return db.query(BulkExtractJobRow).filter(BulkExtractJobRow.id == job_id).first()


def list_incomplete_job_ids() -> list[str]:
    db = SessionLocal()
    try:
        rows = (
            db.query(BulkExtractJobRow.id)
            .filter(BulkExtractJobRow.status.in_(("pending", "running")))
            .all()
        )
        return [r[0] for r in rows]
    finally:
        db.close()


def recover_stale_processing(
    db: Session, job_id: str, stale_seconds: int, *, force: bool = False
) -> int:
    q = db.query(BulkJobItemRow).filter(
        BulkJobItemRow.job_id == job_id,
        BulkJobItemRow.status == ITEM_PROCESSING,
    )
    if not force:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=max(stale_seconds, 1))
        q = q.filter(or_(BulkJobItemRow.updated_at.is_(None), BulkJobItemRow.updated_at <= cutoff))
    count = 0
    for item in q.all():
        item.status = ITEM_QUEUED
        item.retry_after = None
        count += 1
    return count


def copy_canonical_results_to_duplicates(db: Session, job_id: str) -> int:
    """Mirror SUCCESS / FINAL_FAILED onto duplicate rows without re-extracting."""
    items = (
        db.query(BulkJobItemRow)
        .filter(BulkJobItemRow.job_id == job_id, BulkJobItemRow.dedupe_of_id.isnot(None))
        .all()
    )
    if not items:
        return 0
    canons = {
        row.id: row
        for row in db.query(BulkJobItemRow).filter(
            BulkJobItemRow.id.in_({i.dedupe_of_id for i in items if i.dedupe_of_id})
        )
    }
    copied = 0
    now = datetime.now(timezone.utc)
    for item in items:
        if item.status in TERMINAL_ITEM_STATUSES:
            continue
        canon = canons.get(item.dedupe_of_id or 0)
        if not canon or canon.status not in TERMINAL_ITEM_STATUSES:
            continue
        item.status = canon.status
        item.name = canon.name
        item.company = canon.company
        item.designation = canon.designation
        item.about = canon.about
        item.headline = canon.headline
        item.location = canon.location
        item.followers = canon.followers
        item.connections = canon.connections
        item.extraction_response = canon.extraction_response
        item.last_error = canon.last_error
        item.attempt_count = int(canon.attempt_count or 0)
        item.completed_at = now
        apply_verification(
            item,
            match_threshold=int(getattr(get_settings(), "verify_match_threshold", 100)),
            review_threshold=int(getattr(get_settings(), "verify_review_threshold", 75)),
        )
        copied += 1
    return copied


def claim_batch(
    db: Session, job_id: str, batch_size: int, *, max_attempts: int | None = None
) -> list[BulkJobItemRow]:
    """Claim up to batch_size extractable URLs. Never claims SUCCESS, duplicates, or spent attempts."""
    now = datetime.now(timezone.utc)
    cap = max(int(max_attempts if max_attempts is not None else get_settings().apify_max_retries), 1)
    q = (
        db.query(BulkJobItemRow)
        .filter(
            BulkJobItemRow.job_id == job_id,
            BulkJobItemRow.dedupe_of_id.is_(None),
            BulkJobItemRow.attempt_count < cap,
            or_(
                BulkJobItemRow.status.in_(CLAIMABLE_ITEM_STATUSES),
                and_(
                    BulkJobItemRow.status == ITEM_RETRY_WAIT,
                    or_(BulkJobItemRow.retry_after.is_(None), BulkJobItemRow.retry_after <= now),
                ),
            ),
        )
        .order_by(BulkJobItemRow.source_row_number.asc())
        .limit(max(int(batch_size), 1))
    )
    if not DATABASE_URL.startswith("sqlite"):
        q = q.with_for_update(skip_locked=True)
    items = q.all()
    for item in items:
        item.status = ITEM_PROCESSING
        item.retry_after = None
        item.updated_at = now
    db.flush()
    return items


def next_retry_wait_seconds(db: Session, job_id: str) -> float | None:
    now = datetime.now(timezone.utc)
    row = (
        db.query(func.min(BulkJobItemRow.retry_after))
        .filter(BulkJobItemRow.job_id == job_id, BulkJobItemRow.status == ITEM_RETRY_WAIT)
        .scalar()
    )
    if row is None:
        return None
    if row.tzinfo is None:
        row = row.replace(tzinfo=timezone.utc)
    delta = (row - now).total_seconds()
    return max(delta, 0.0)


def add_attempt(
    db: Session,
    item: BulkJobItemRow,
    *,
    attempt_number: int,
    started_at: datetime,
    finished_at: datetime,
    status: str,
    response: dict[str, Any] | None,
    error: str | None,
    apify_run_id: str | None,
) -> ExtractionAttemptRow:
    row = ExtractionAttemptRow(
        job_item_id=item.id,
        attempt_number=attempt_number,
        request_started_at=started_at,
        request_finished_at=finished_at,
        status=status,
        response=response,
        error=error,
        apify_run_id=apify_run_id,
    )
    db.add(row)
    return row


def count_processing_items(db: Session, job_id: str) -> int:
    return (
        db.query(func.count(BulkJobItemRow.id))
        .filter(BulkJobItemRow.job_id == job_id, BulkJobItemRow.status == ITEM_PROCESSING)
        .scalar()
        or 0
    )


def list_recent_comparison_items(job_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
    db = SessionLocal()
    try:
        rows = (
            db.query(BulkJobItemRow)
            .filter(
                BulkJobItemRow.job_id == job_id,
                BulkJobItemRow.status == ITEM_SUCCESS,
            )
            .order_by(BulkJobItemRow.completed_at.desc(), BulkJobItemRow.id.desc())
            .limit(max(int(limit), 1))
            .all()
        )
        return [item_to_result_dict(row) for row in rows]
    finally:
        db.close()


def item_to_result_dict(item: BulkJobItemRow) -> dict[str, Any]:
    from app.linkedin.verification import original_fields

    originals = original_fields(item.source_row_json if isinstance(item.source_row_json, dict) else {})
    return {
        "item_id": item.id,
        "source_row_number": item.source_row_number,
        "url": item.normalized_url or item.profile_url,
        "extraction_status": item.status,
        "attempt_count": item.attempt_count or 0,
        "error": item.last_error,
        "uploaded": {
            "name": originals.get("name"),
            "designation": originals.get("designation"),
            "company": originals.get("company"),
            "location": originals.get("location"),
        },
        "extracted": {
            "name": item.name,
            "designation": item.designation,
            "company": item.company,
            "location": item.location,
            "about": item.about,
        },
        "name_match": item.name_match,
        "designation_match": item.designation_match,
        "company_match": item.company_match,
        "location_match": item.location_match,
        "verification_status": item.verification_status,
        "verification_score": item.verification_score or 0,
        "verification_reason": item.verification_reason,
    }


class BulkJobStore:
    """Compatibility wrapper used by routes for ownership checks."""

    def get(self, job_id: str) -> BulkExtractJob | None:
        return get_job(job_id)


bulk_job_store = BulkJobStore()
