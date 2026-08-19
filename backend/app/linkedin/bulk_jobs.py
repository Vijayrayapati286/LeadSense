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
from app.linkedin.bulk_models import (
    CLAIMABLE_ITEM_STATUSES,
    ITEM_FINAL_FAILED,
    ITEM_PENDING,
    ITEM_PROCESSING,
    ITEM_QUEUED,
    ITEM_RETRY_WAIT,
    ITEM_SUCCESS,
    TERMINAL_ITEM_STATUSES,
    BulkExtractJobRow,
    BulkJobItemRow,
    ExtractionAttemptRow,
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
    total = (
        db.query(func.count(BulkJobItemRow.id)).filter(BulkJobItemRow.job_id == job.id).scalar() or 0
    )
    job.success_count = int(success)
    job.failed_count = int(failed)
    job.retrying_count = int(retrying)
    job.processed_count = int(success) + int(failed)
    job.total_urls = int(total)
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
        item.attempt_count = 0
        item.completed_at = now
        copied += 1
    return copied


def claim_batch(db: Session, job_id: str, batch_size: int) -> list[BulkJobItemRow]:
    """Claim up to batch_size extractable URLs. Never claims SUCCESS or duplicates."""
    now = datetime.now(timezone.utc)
    q = (
        db.query(BulkJobItemRow)
        .filter(
            BulkJobItemRow.job_id == job_id,
            BulkJobItemRow.dedupe_of_id.is_(None),
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


class BulkJobStore:
    """Compatibility wrapper used by routes for ownership checks."""

    def get(self, job_id: str) -> BulkExtractJob | None:
        return get_job(job_id)


bulk_job_store = BulkJobStore()
