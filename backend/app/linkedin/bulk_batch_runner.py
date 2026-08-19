"""Concurrent batch runner for bulk LinkedIn URL extraction.

Database is the queue. Successful URLs are never retried; only failed URLs
are re-queued up to APIFY_MAX_RETRIES attempts.
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

from app.config import Settings, get_settings
from app.database.connection import SessionLocal
from app.linkedin.apify_extractor import LinkedInApifyProfileExtractor, RichBatchOutcome
from app.linkedin.bulk_excel_service import BulkExcelService
from app.linkedin.bulk_jobs import (
    add_attempt,
    claim_batch,
    copy_canonical_results_to_duplicates,
    count_processing_items,
    get_job_row,
    next_retry_wait_seconds,
    recover_stale_processing,
    refresh_job_counters,
)
from app.linkedin.bulk_models import (
    ITEM_FINAL_FAILED,
    ITEM_PENDING,
    ITEM_PROCESSING,
    ITEM_QUEUED,
    ITEM_RETRY_WAIT,
    ITEM_SUCCESS,
    PHASE_EXTRACTING,
    BulkJobItemRow,
)
from app.linkedin.validator import is_retryable_error, is_valid_extraction
from app.linkedin.verification import apply_verification

logger = logging.getLogger(__name__)

_claim_lock = threading.Lock()
_apify_semaphore: threading.BoundedSemaphore | None = None
_apify_sema_n: int | None = None
_apify_sema_lock = threading.Lock()


def split_batches(urls: Sequence[str], batch_size: int) -> list[list[str]]:
    size = max(int(batch_size), 1)
    items = list(urls)
    return [items[i : i + size] for i in range(0, len(items), size)]


def retry_delay_seconds(attempt_count: int, settings: Settings) -> float:
    base = max(float(settings.bulk_retry_base_delay_seconds), 0.0)
    multiplier = max(float(settings.bulk_retry_backoff_multiplier), 1.0)
    exponent = max(int(attempt_count) - 1, 0)
    return base * (multiplier**exponent)


def _apify_limit(settings: Settings) -> threading.BoundedSemaphore:
    global _apify_semaphore, _apify_sema_n
    n = max(int(settings.max_concurrent_apify_runs), 1)
    with _apify_sema_lock:
        if _apify_semaphore is None or _apify_sema_n != n:
            _apify_semaphore = threading.BoundedSemaphore(n)
            _apify_sema_n = n
        return _apify_semaphore


def run_batch_with_retries(
    apify: LinkedInApifyProfileExtractor,
    urls: list[str],
    *,
    max_retries: int = 0,
    settings: Settings | None = None,
) -> RichBatchOutcome:
    """Run one Apify batch. Optionally retry ONLY URLs that still lack valid data.

    Successful URLs from an earlier attempt are never sent again.
    """
    cfg = settings or get_settings()
    remaining = list(urls)
    combined: dict[str, dict[str, Any]] = {}
    last_run_id: str | None = None
    last_batch_error: str | None = None
    attempts = max(int(max_retries), 0) + 1

    for attempt in range(1, attempts + 1):
        if not remaining:
            break
        outcome = apify.run_rich_batch(remaining)
        last_run_id = outcome.actor_run_id
        last_batch_error = outcome.batch_error
        next_remaining: list[str] = []
        for url in remaining:
            result = outcome.results_by_url.get(url) or {
                "status": "failed",
                "data": None,
                "error": outcome.batch_error or "No data returned for this URL in batch",
            }
            if is_valid_extraction(result):
                combined[url] = {**result, "status": "ok"}
            else:
                combined[url] = {
                    "status": "failed",
                    "data": result.get("data"),
                    "error": result.get("error") or last_batch_error or "Extraction failed",
                }
                next_remaining.append(url)
        remaining = next_remaining
        if remaining and attempt < attempts:
            delay = retry_delay_seconds(attempt, cfg)
            if delay > 0:
                time.sleep(delay)

    for url in urls:
        combined.setdefault(
            url,
            {"status": "failed", "data": None, "error": last_batch_error or "Extraction failed"},
        )
    return RichBatchOutcome(results_by_url=combined, actor_run_id=last_run_id, batch_error=last_batch_error)


class BulkBatchRunner:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.apify = LinkedInApifyProfileExtractor()
        self.excel = BulkExcelService()

    def process_job(
        self,
        job_id: str,
        *,
        file_content: bytes | None = None,
        filename: str | None = None,
    ) -> None:
        del file_content, filename
        worker_id = threading.current_thread().name
        logger.info("[JOB-%s] [WORKER-%s] Extraction job started", job_id, worker_id)
        db = SessionLocal()
        try:
            job = get_job_row(db, job_id)
            if not job:
                logger.error("[JOB-%s] Job not found", job_id)
                return
            job.status = "running"
            job.phase = PHASE_EXTRACTING
            job.excel_finalized = False
            job.updated_at = datetime.now(timezone.utc)
            recover_stale_processing(
                db, job_id, self.settings.bulk_stale_processing_seconds, force=True
            )
            copy_canonical_results_to_duplicates(db, job_id)
            refresh_job_counters(db, job)
            cfg_error = self._missing_apify_config()
            if cfg_error:
                logger.error("[JOB-%s] %s", job_id, cfg_error)
                now = datetime.now(timezone.utc)
                pending = (
                    db.query(BulkJobItemRow)
                    .filter(
                        BulkJobItemRow.job_id == job_id,
                        BulkJobItemRow.status.in_(
                            (ITEM_PENDING, ITEM_QUEUED, ITEM_PROCESSING, ITEM_RETRY_WAIT)
                        ),
                    )
                    .all()
                )
                for item in pending:
                    item.status = ITEM_FINAL_FAILED
                    item.last_error = cfg_error
                    item.completed_at = now
                refresh_job_counters(db, job)
                job.status = "failed"
                job.phase = "completed"
                job.error = cfg_error
                job.completed_at = now
                self._write_excel(db, job)
                job.excel_finalized = True
                db.commit()
                db.close()
                return
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("[JOB-%s] Failed to start job", job_id)
            db.close()
            return
        db.close()

        max_workers = max(
            int(
                getattr(self.settings, "max_concurrent_batches", None)
                or self.settings.max_concurrent_apify_runs
            ),
            1,
        )
        try:
            with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix=f"bulk-{job_id[:8]}") as pool:
                futures: set[Any] = set()

                def fill() -> None:
                    while len(futures) < max_workers:
                        item_ids = self._claim(job_id)
                        if not item_ids:
                            break
                        batch_id = f"{job_id[:8]}-{item_ids[0]}"
                        futures.add(pool.submit(self._run_claimed_batch, job_id, item_ids, batch_id))

                fill()
                idle_rounds = 0
                while True:
                    if futures:
                        done, futures = wait(futures, return_when=FIRST_COMPLETED, timeout=30)
                        for fut in done:
                            try:
                                fut.result()
                            except Exception:
                                logger.exception("[JOB-%s] Worker batch crashed", job_id)
                        fill()
                        idle_rounds = 0
                        continue

                    db = SessionLocal()
                    try:
                        recover_stale_processing(
                            db, job_id, self.settings.bulk_stale_processing_seconds, force=False
                        )
                        copy_canonical_results_to_duplicates(db, job_id)
                        job = get_job_row(db, job_id)
                        if job:
                            refresh_job_counters(db, job)
                            db.commit()
                            if job.processed_count >= job.total_urls and job.total_urls > 0:
                                self._finalize_job(db, job)
                                db.commit()
                                logger.info("[JOB-%s] Extraction job completed", job_id)
                                return
                        wait_s = next_retry_wait_seconds(db, job_id)
                    finally:
                        db.close()

                    fill()
                    if futures:
                        continue
                    if wait_s is not None:
                        time.sleep(min(wait_s, 15.0) if wait_s > 0 else 0.05)
                        idle_rounds = 0
                        fill()
                        continue
                    idle_rounds += 1
                    if idle_rounds >= 3:
                        db = SessionLocal()
                        try:
                            copy_canonical_results_to_duplicates(db, job_id)
                            job = get_job_row(db, job_id)
                            if job:
                                refresh_job_counters(db, job)
                                if job.processed_count >= job.total_urls:
                                    self._finalize_job(db, job)
                                else:
                                    job.status = "failed"
                                    job.error = "Job stalled with unfinished URLs"
                                    job.completed_at = datetime.now(timezone.utc)
                                    job.phase = "completed"
                                    self._write_excel(db, job)
                                    job.excel_finalized = True
                                db.commit()
                        finally:
                            db.close()
                        return
                    time.sleep(0.2)
        except Exception as exc:
            logger.exception("[JOB-%s] Job runner failed", job_id)
            db = SessionLocal()
            try:
                job = get_job_row(db, job_id)
                if job:
                    job.status = "failed"
                    job.error = str(exc)
                    job.completed_at = datetime.now(timezone.utc)
                    job.phase = "completed"
                    self._write_excel(db, job)
                    job.excel_finalized = True
                    db.commit()
            finally:
                db.close()

    def _missing_apify_config(self) -> str | None:
        if not (self.settings.apify_token or "").strip():
            return "APIFY_TOKEN is not configured. Set it in backend/.env and restart the backend."
        actor = (
            (self.settings.apify_profile_actor_id or "").strip()
            or (self.settings.apify_actor_id or "").strip()
        )
        if not actor:
            return (
                "APIFY_PROFILE_ACTOR_ID (or APIFY_ACTOR_ID) is not configured. "
                "Set it in backend/.env and restart the backend."
            )
        return None

    def _claim(self, job_id: str) -> list[int]:
        with _claim_lock:
            db = SessionLocal()
            try:
                batch_size = max(int(self.settings.apify_batch_size), 1)
                window = max(int(getattr(self.settings, "processing_window", 100)), 1)
                processing = count_processing_items(db, job_id)
                room = window - processing
                if room <= 0:
                    return []
                items = claim_batch(
                    db,
                    job_id,
                    min(batch_size, room),
                    max_attempts=max(int(self.settings.apify_max_retries), 1),
                )
                ids = [int(item.id) for item in items]
                db.commit()
                return ids
            except Exception:
                db.rollback()
                logger.exception("[JOB-%s] Failed to claim batch", job_id)
                return []
            finally:
                db.close()

    def _run_claimed_batch(self, job_id: str, item_ids: list[int], batch_id: str) -> None:
        worker_id = threading.current_thread().name
        db = SessionLocal()
        try:
            items = (
                db.query(BulkJobItemRow)
                .filter(BulkJobItemRow.id.in_(item_ids), BulkJobItemRow.job_id == job_id)
                .all()
            )
            items = [i for i in items if i.status == "PROCESSING"]
            if not items:
                return

            max_attempts = max(int(self.settings.apify_max_retries), 1)
            started = datetime.now(timezone.utc)
            for item in items:
                item.attempt_count = int(item.attempt_count or 0) + 1
                logger.info(
                    "[JOB-%s] [URL-%s] [ATTEMPT-%s] [WORKER-%s] [BATCH-%s] Extraction started url=%s",
                    job_id,
                    item.id,
                    item.attempt_count,
                    worker_id,
                    batch_id,
                    item.normalized_url,
                )

            urls = [item.normalized_url for item in items]
            sema = _apify_limit(self.settings)
            acquired = sema.acquire()
            try:
                outcome = self.apify.run_rich_batch(urls)
            finally:
                if acquired:
                    sema.release()

            finished = datetime.now(timezone.utc)
            duration_ms = int((finished - started).total_seconds() * 1000)
            apify_run_id = outcome.actor_run_id

            for item in items:
                result = outcome.results_by_url.get(item.normalized_url) or {
                    "status": "failed",
                    "data": None,
                    "error": outcome.batch_error or "No data returned for this URL in batch",
                }
                valid = is_valid_extraction(result)
                if valid:
                    data = result.get("data") or {}
                    self._mark_success(db, item, data, result, apify_run_id, started, finished)
                    logger.info(
                        "[JOB-%s] [URL-%s] [ATTEMPT-%s] [WORKER-%s] [BATCH-%s] [APIFY-%s] Extraction success duration_ms=%s",
                        job_id,
                        item.id,
                        item.attempt_count,
                        worker_id,
                        batch_id,
                        apify_run_id or "-",
                        duration_ms,
                    )
                    continue

                error = (
                    result.get("error")
                    or outcome.batch_error
                    or "No usable profile data returned"
                )
                self._mark_failure(
                    db,
                    item,
                    error=error,
                    response=result,
                    apify_run_id=apify_run_id,
                    started=started,
                    finished=finished,
                    max_attempts=max_attempts,
                )
                logger.info(
                    "[JOB-%s] [URL-%s] [ATTEMPT-%s] [WORKER-%s] [BATCH-%s] [APIFY-%s] Extraction failed duration_ms=%s error=%s",
                    job_id,
                    item.id,
                    item.attempt_count,
                    worker_id,
                    batch_id,
                    apify_run_id or "-",
                    duration_ms,
                    error,
                )

            copy_canonical_results_to_duplicates(db, job_id)
            job = get_job_row(db, job_id)
            if job:
                refresh_job_counters(db, job)
                self._write_excel(db, job)
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("[JOB-%s] [BATCH-%s] Batch processing failed", job_id, batch_id)
            db = SessionLocal()
            try:
                items = db.query(BulkJobItemRow).filter(BulkJobItemRow.id.in_(item_ids)).all()
                now = datetime.now(timezone.utc)
                max_attempts = max(int(self.settings.apify_max_retries), 1)
                for item in items:
                    if item.status == ITEM_SUCCESS:
                        continue
                    self._mark_failure(
                        db,
                        item,
                        error="Worker error while processing batch",
                        response=None,
                        apify_run_id=None,
                        started=now,
                        finished=now,
                        max_attempts=max_attempts,
                    )
                db.commit()
            except Exception:
                db.rollback()
            finally:
                db.close()
        finally:
            db.close()

    def _mark_success(
        self,
        db,
        item: BulkJobItemRow,
        data: dict[str, Any],
        result: dict[str, Any],
        apify_run_id: str | None,
        started: datetime,
        finished: datetime,
    ) -> None:
        item.status = ITEM_SUCCESS
        item.name = _str(data.get("name") or data.get("full_name"))
        item.company = _str(data.get("company"))
        item.designation = _str(data.get("job_title") or data.get("designation"))
        item.about = _str(data.get("summary") or data.get("about"))
        item.headline = _str(data.get("headline"))
        item.location = _str(data.get("location"))
        item.followers = data.get("followers") if isinstance(data.get("followers"), int) else None
        item.connections = data.get("connections") if isinstance(data.get("connections"), int) else None
        item.extraction_response = result
        item.last_error = None
        item.retry_after = None
        item.completed_at = finished
        add_attempt(
            db,
            item,
            attempt_number=item.attempt_count,
            started_at=started,
            finished_at=finished,
            status="SUCCESS",
            response=result,
            error=None,
            apify_run_id=apify_run_id,
        )
        verification = apply_verification(
            item,
            match_threshold=int(getattr(self.settings, "verify_match_threshold", 100)),
            review_threshold=int(getattr(self.settings, "verify_review_threshold", 75)),
        )
        logger.info(
            "[JOB-%s] [URL-%s] [ATTEMPT-%s] Extraction SUCCESS Verification %s Score %s%%",
            item.job_id,
            item.id,
            item.attempt_count,
            verification.status,
            verification.score,
        )

    def _mark_failure(
        self,
        db,
        item: BulkJobItemRow,
        *,
        error: str,
        response: dict[str, Any] | None,
        apify_run_id: str | None,
        started: datetime,
        finished: datetime,
        max_attempts: int,
    ) -> None:
        retryable = is_retryable_error(error, non_retryable_csv=self.settings.bulk_non_retryable_errors)
        item.last_error = error
        item.extraction_response = response
        add_attempt(
            db,
            item,
            attempt_number=item.attempt_count,
            started_at=started,
            finished_at=finished,
            status="FAILED",
            response=response,
            error=error,
            apify_run_id=apify_run_id,
        )
        if (not retryable) or item.attempt_count >= max_attempts:
            item.status = ITEM_FINAL_FAILED
            item.retry_after = None
            item.completed_at = finished
            apply_verification(
                item,
                match_threshold=int(getattr(self.settings, "verify_match_threshold", 100)),
                review_threshold=int(getattr(self.settings, "verify_review_threshold", 75)),
            )
            return
        delay = retry_delay_seconds(item.attempt_count, self.settings)
        item.status = ITEM_RETRY_WAIT
        item.retry_after = finished + timedelta(seconds=delay)

    def _write_excel(self, db, job) -> None:
        items = (
            db.query(BulkJobItemRow)
            .filter(BulkJobItemRow.job_id == job.id)
            .order_by(BulkJobItemRow.source_row_number.asc())
            .all()
        )
        _, _filename, relative = self.excel.build_result_workbook_from_items(
            job_id=job.id,
            items=items,
            input_columns=list(job.input_columns or []),
        )
        job.result_file_path = relative

    def _finalize_job(self, db, job) -> None:
        copy_canonical_results_to_duplicates(db, job.id)
        refresh_job_counters(db, job)
        self._write_excel(db, job)
        job.status = "done"
        job.phase = "completed"
        job.excel_finalized = True
        job.completed_at = datetime.now(timezone.utc)
        job.error = None


def _str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
