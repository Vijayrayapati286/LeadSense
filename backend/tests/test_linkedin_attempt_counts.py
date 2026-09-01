"""Per-URL attempt_count and retry-queue behavior."""

from __future__ import annotations

import io
import threading
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from app.database.connection import SessionLocal
from app.linkedin.apify_extractor import RichBatchOutcome
from app.linkedin.bulk_jobs import claim_batch, recover_stale_processing
from app.linkedin.bulk_models import (
    ITEM_FINAL_FAILED,
    ITEM_PROCESSING,
    ITEM_QUEUED,
    ITEM_SUCCESS,
    BulkJobItemRow,
    ExtractionAttemptRow,
)


def _ok(url: str) -> dict:
    return {
        "status": "ok",
        "data": {
            "name": "User",
            "headline": "Eng",
            "company": "Acme",
            "job_title": "Dev",
            "location": "NYC",
            "summary": "About",
            "profile_url": url,
        },
        "error": None,
    }


def _fail() -> dict:
    return {"status": "failed", "data": None, "error": "empty"}


def _wait_done(client, job_id: str, timeout_s: float = 20.0):
    start = time.time()
    while time.time() - start < timeout_s:
        payload = client.get(f"/api/linkedin/bulk-jobs/{job_id}").json()
        if payload["status"] in {"done", "failed"}:
            return payload
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} did not finish")


def _post_urls(client, monkeypatch, urls: list[str], mock_fn, *, max_retries: int = 5):
    from app.config import get_settings
    from app.linkedin import routes as linkedin_routes
    from app.linkedin.bulk_batch_runner import BulkBatchRunner

    settings = get_settings()
    monkeypatch.setattr(settings, "apify_batch_size", 10)
    monkeypatch.setattr(settings, "max_concurrent_batches", 2)
    monkeypatch.setattr(settings, "max_concurrent_apify_runs", 2)
    monkeypatch.setattr(settings, "apify_max_retries", max_retries)
    monkeypatch.setattr(settings, "bulk_retry_base_delay_seconds", 0)
    monkeypatch.setattr(settings, "processing_window", 100)
    monkeypatch.setattr(settings, "max_bulk_urls", 5000)

    runner = BulkBatchRunner(settings=settings)
    runner.apify.run_rich_batch = mock_fn
    monkeypatch.setattr(
        linkedin_routes,
        "bulk_extract_service",
        type("S", (), {"process_job": runner.process_job})(),
    )

    buffer = io.BytesIO()
    pd.DataFrame({"LinkedIn URL": urls}).to_excel(buffer, index=False, engine="openpyxl")
    resp = client.post(
        "/api/linkedin/bulk-extract",
        files={"file": ("p.xlsx", buffer.getvalue(), "application/vnd.openxmlformats-officedocument.sheet")},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["job_id"]


def _items(job_id: str) -> list[BulkJobItemRow]:
    db = SessionLocal()
    try:
        return (
            db.query(BulkJobItemRow)
            .filter(BulkJobItemRow.job_id == job_id)
            .order_by(BulkJobItemRow.source_row_number.asc())
            .all()
        )
    finally:
        db.close()


def _attempts_for(item_id: int) -> list[ExtractionAttemptRow]:
    db = SessionLocal()
    try:
        return (
            db.query(ExtractionAttemptRow)
            .filter(ExtractionAttemptRow.job_item_id == item_id)
            .order_by(ExtractionAttemptRow.attempt_number.asc())
            .all()
        )
    finally:
        db.close()


@pytest.mark.parametrize(
    "fail_times,expected_status,expected_attempts",
    [
        (0, ITEM_SUCCESS, 1),
        (1, ITEM_SUCCESS, 2),
        (2, ITEM_SUCCESS, 3),
        (4, ITEM_SUCCESS, 5),
        (5, ITEM_FINAL_FAILED, 5),
    ],
)
def test_per_url_attempt_count(client, monkeypatch, fail_times, expected_status, expected_attempts):
    url = "https://www.linkedin.com/in/solo/"
    seen = {"n": 0}

    def mock_run_rich_batch(urls):
        seen["n"] += 1
        if seen["n"] <= fail_times:
            return RichBatchOutcome(results_by_url={url: _fail()})
        return RichBatchOutcome(results_by_url={url: _ok(url)})

    job_id = _post_urls(client, monkeypatch, [url], mock_run_rich_batch)
    done = _wait_done(client, job_id)
    assert done["status"] == "done"
    item = _items(job_id)[0]
    assert item.status == expected_status
    assert item.attempt_count == expected_attempts
    assert seen["n"] == expected_attempts
    history = _attempts_for(item.id)
    assert len(history) == expected_attempts
    if expected_status == ITEM_SUCCESS:
        assert history[-1].status == "SUCCESS"
        assert all(h.status == "FAILED" for h in history[:-1])
    else:
        assert all(h.status == "FAILED" for h in history)


def test_only_failed_urls_in_batch_are_retried(client, monkeypatch):
    urls = [f"https://www.linkedin.com/in/u{i}/" for i in range(10)]
    fail_set = {urls[2], urls[7]}
    calls: list[list[str]] = []

    def mock_run_rich_batch(batch):
        calls.append(list(batch))
        return RichBatchOutcome(
            results_by_url={
                u: _fail() if u in fail_set else _ok(u) for u in batch
            }
        )

    job_id = _post_urls(client, monkeypatch, urls, mock_run_rich_batch)
    done = _wait_done(client, job_id)
    assert done["successful_profiles"] == 8
    assert done["failed_profiles"] == 2
    items = {row.normalized_url: row for row in _items(job_id)}
    for u in urls:
        if u in fail_set:
            assert items[u].status == ITEM_FINAL_FAILED
            assert items[u].attempt_count == 5
        else:
            assert items[u].status == ITEM_SUCCESS
            assert items[u].attempt_count == 1
    first = set(calls[0])
    assert first == set(urls)
    later = [u for batch in calls[1:] for u in batch]
    assert set(later) <= fail_set
    assert urls[0] not in later


def test_successful_url_never_reprocessed(client, monkeypatch):
    good = "https://www.linkedin.com/in/good/"
    bad = "https://www.linkedin.com/in/bad/"
    calls: list[list[str]] = []

    def mock_run_rich_batch(batch):
        calls.append(list(batch))
        return RichBatchOutcome(
            results_by_url={u: _ok(u) if u == good else _fail() for u in batch}
        )

    job_id = _post_urls(client, monkeypatch, [good, bad], mock_run_rich_batch)
    _wait_done(client, job_id)
    appeared = [i for i, batch in enumerate(calls) if good in batch]
    assert appeared == [0]
    items = {row.normalized_url: row for row in _items(job_id)}
    assert items[good].attempt_count == 1
    assert items[bad].attempt_count == 5


def test_claim_skips_urls_that_already_used_max_attempts(client):
    from app.linkedin.bulk_jobs import create_job_with_items

    job = create_job_with_items(
        user_id=1,
        original_file_name="t.xlsx",
        input_columns=["LinkedIn URL"],
        url_rows=[
            {
                "source_row_number": 1,
                "raw_url": "https://www.linkedin.com/in/spent/",
                "normalized_url": "https://www.linkedin.com/in/spent/",
                "is_valid": True,
                "source_row_json": {},
            }
        ],
    )
    db = SessionLocal()
    try:
        item = db.query(BulkJobItemRow).filter(BulkJobItemRow.job_id == job.id).one()
        item.status = "RETRY_WAIT"
        item.attempt_count = 5
        item.retry_after = None
        db.commit()
        claimed = claim_batch(db, job.id, 10, max_attempts=5)
        assert claimed == []
    finally:
        db.close()


def test_two_claims_cannot_select_the_same_url():
    from app.linkedin.bulk_jobs import create_job_with_items

    job = create_job_with_items(
        user_id=1,
        original_file_name="t.xlsx",
        input_columns=["LinkedIn URL"],
        url_rows=[
            {
                "source_row_number": 1,
                "raw_url": "https://www.linkedin.com/in/one/",
                "normalized_url": "https://www.linkedin.com/in/one/",
                "is_valid": True,
                "source_row_json": {},
            }
        ],
    )
    from app.linkedin.bulk_batch_runner import _claim_lock

    seen: list[list[int]] = []
    errors: list[BaseException] = []

    def worker():
        with _claim_lock:
            db = SessionLocal()
            try:
                claimed = claim_batch(db, job.id, 10, max_attempts=5)
                db.commit()
                seen.append([i.id for i in claimed])
            except BaseException as exc:
                errors.append(exc)
                db.rollback()
            finally:
                db.close()

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    assert not errors
    ids = [i for batch in seen for i in batch]
    assert len(ids) == 1
    assert ids.count(ids[0]) == 1


def test_hundred_urls_keep_independent_attempt_counts(client, monkeypatch):
    urls = [f"https://www.linkedin.com/in/row{i}/" for i in range(100)]
    always_fail = set(urls[:5])

    def mock_run_rich_batch(batch):
        return RichBatchOutcome(
            results_by_url={u: _fail() if u in always_fail else _ok(u) for u in batch}
        )

    job_id = _post_urls(client, monkeypatch, urls, mock_run_rich_batch)
    done = _wait_done(client, job_id, timeout_s=40)
    assert done["successful_profiles"] + done["failed_profiles"] == 100
    items = _items(job_id)
    assert len(items) == 100
    for row in items:
        if row.normalized_url in always_fail:
            assert row.status == ITEM_FINAL_FAILED
            assert row.attempt_count == 5
        else:
            assert row.status == ITEM_SUCCESS
            assert row.attempt_count == 1

    download = client.get(f"/api/linkedin/bulk-jobs/{job_id}/download")
    assert download.status_code == 200
    df = pd.read_excel(io.BytesIO(download.content))
    assert list(df["Extraction Attempts"]) == [row.attempt_count for row in items]


def test_crash_recovery_does_not_reset_attempt_count():
    from app.linkedin.bulk_jobs import create_job_with_items

    job = create_job_with_items(
        user_id=1,
        original_file_name="t.xlsx",
        input_columns=["LinkedIn URL"],
        url_rows=[
            {
                "source_row_number": 1,
                "raw_url": "https://www.linkedin.com/in/resume/",
                "normalized_url": "https://www.linkedin.com/in/resume/",
                "is_valid": True,
                "source_row_json": {},
            }
        ],
    )
    db = SessionLocal()
    try:
        item = db.query(BulkJobItemRow).filter(BulkJobItemRow.job_id == job.id).one()
        item.status = ITEM_PROCESSING
        item.attempt_count = 3
        item.updated_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db.commit()
        recover_stale_processing(db, job.id, stale_seconds=60, force=True)
        db.commit()
        db.refresh(item)
        assert item.status == ITEM_QUEUED
        assert item.attempt_count == 3
    finally:
        db.close()
