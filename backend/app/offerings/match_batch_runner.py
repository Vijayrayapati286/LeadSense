"""Background worker that processes offering match jobs in batches."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

from app.database.connection import SessionLocal
from app.icp.models import IcpRecordRow
from app.offerings.match_jobs import (
    claim_batch,
    list_incomplete_match_job_ids,
    recover_stale_processing,
    refresh_job_counters,
)
from app.offerings.matching_service import match_icp_to_offering
from app.offerings.models import (
    ITEM_FINAL_FAILED,
    ITEM_SKIPPED,
    ITEM_SUCCESS,
    JOB_DONE,
    JOB_FAILED,
    JOB_RUNNING,
    MATCH_TIER_GOOD,
    MATCH_TIER_POOR,
    MATCH_TIER_POTENTIAL,
    MATCH_TIER_STRONG,
    OfferingMatchJobRow,
    OfferingMatchRow,
    OfferingRow,
)

logger = logging.getLogger(__name__)

_running_lock = threading.Lock()
_running_jobs: set[str] = set()


def start_match_job_async(job_id: str, *, force: bool = False) -> None:
    with _running_lock:
        if job_id in _running_jobs:
            return
        _running_jobs.add(job_id)

    def _run():
        try:
            process_match_job(job_id, force=force)
        finally:
            with _running_lock:
                _running_jobs.discard(job_id)

    t = threading.Thread(target=_run, name=f"offering-match-{job_id[:8]}", daemon=True)
    t.start()


def process_match_job(job_id: str, *, force: bool = False, batch_size: int = 25) -> None:
    db = SessionLocal()
    try:
        job = db.query(OfferingMatchJobRow).filter(OfferingMatchJobRow.id == job_id).first()
        if not job:
            return
        offering = db.query(OfferingRow).filter(OfferingRow.id == job.offering_id).first()
        if not offering:
            job.status = JOB_FAILED
            job.error = "Offering not found"
            job.completed_at = datetime.now(timezone.utc)
            db.commit()
            return

        recover_stale_processing(db, job_id)
        job.status = JOB_RUNNING
        job.started_at = job.started_at or datetime.now(timezone.utc)
        job.error = None
        db.commit()

        while True:
            claimed = claim_batch(db, job_id, batch_size=batch_size)
            if not claimed:
                break
            db.commit()

            for item in claimed:
                try:
                    icp = db.query(IcpRecordRow).filter(IcpRecordRow.id == item.icp_record_id).first()
                    if not icp:
                        item.status = ITEM_SKIPPED
                        item.error = "ICP record missing"
                    else:
                        match_icp_to_offering(db, offering, icp, use_ai=True, force=force)
                        item.status = ITEM_SUCCESS
                        item.error = None
                except Exception as exc:
                    logger.exception("Match item failed job=%s icp=%s", job_id, item.icp_record_id)
                    item.status = ITEM_FINAL_FAILED
                    item.error = str(exc)[:500]
                db.commit()

            _refresh_tier_counts(db, job)
            refresh_job_counters(db, job)
            db.commit()

        job = db.query(OfferingMatchJobRow).filter(OfferingMatchJobRow.id == job_id).first()
        if job:
            _refresh_tier_counts(db, job)
            refresh_job_counters(db, job)
            job.status = JOB_DONE
            job.completed_at = datetime.now(timezone.utc)
            db.commit()
    except Exception as exc:
        logger.exception("Match job failed: %s", job_id)
        try:
            job = db.query(OfferingMatchJobRow).filter(OfferingMatchJobRow.id == job_id).first()
            if job:
                job.status = JOB_FAILED
                job.error = str(exc)[:1000]
                job.completed_at = datetime.now(timezone.utc)
                db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()


def _refresh_tier_counts(db, job: OfferingMatchJobRow) -> None:
    matches = (
        db.query(OfferingMatchRow)
        .filter(OfferingMatchRow.offering_id == job.offering_id)
        .all()
    )
    strong = potential = poor = 0
    for m in matches:
        if m.match_tier == MATCH_TIER_STRONG:
            strong += 1
        elif m.match_tier in (MATCH_TIER_POTENTIAL, MATCH_TIER_GOOD):
            potential += 1
        else:
            poor += 1
    job.strong_count = strong
    job.potential_count = potential
    job.poor_count = poor


def resume_incomplete_match_jobs() -> None:
    for job_id in list_incomplete_match_job_ids():
        logger.info("Resuming offering match job %s", job_id)
        start_match_job_async(job_id, force=False)
