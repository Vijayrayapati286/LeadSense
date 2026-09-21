"""Apify cost-guard: ICP skip, reuse, invalid URLs, and no Apify on download."""

from __future__ import annotations

import io
import time
import uuid
from datetime import datetime, timezone

import pandas as pd
import pytest

from app.database.connection import SessionLocal, init_db
from app.icp.models import IcpRecordRow
from app.linkedin.bulk_models import (
    ITEM_PROCESSING,
    ITEM_SUCCESS,
    BulkExtractJobRow,
    BulkJobItemRow,
)
from app.linkedin.cost_guard import apply_cost_guard_to_claimed_items
from app.linkedin.validator import classify_extraction_error, normalize_profile_url


def _uid_url(slug: str) -> str:
    return f"https://www.linkedin.com/in/{slug}-{uuid.uuid4().hex[:10]}/"


@pytest.fixture(autouse=True)
def _schema():
    init_db()


def _wait_bulk_job(client, job_id: str, *, timeout_s: float = 20.0):
    start = time.time()
    while time.time() - start < timeout_s:
        res = client.get(f"/api/linkedin/bulk-jobs/{job_id}")
        assert res.status_code == 200, res.text
        payload = res.json()
        if payload["status"] in {"done", "failed"}:
            return payload
        time.sleep(0.05)
    raise AssertionError(f"Timed out waiting for bulk job {job_id}")


def _seed_icp(linkedin_url: str, name: str = "Existing User") -> int:
    db = SessionLocal()
    try:
        normalized = normalize_profile_url(linkedin_url)
        existing = (
            db.query(IcpRecordRow)
            .filter(IcpRecordRow.user_id == 1, IcpRecordRow.linkedin_url == normalized)
            .first()
        )
        if existing:
            return existing.id
        now = datetime.now(timezone.utc)
        row = IcpRecordRow(
            user_id=1,
            name=name,
            company_name="Known Co",
            designation="Director",
            about="Already verified",
            linkedin_url=normalized,
            location="Boston",
            verification_status="VERIFIED",
            verified_at=now,
            created_at=now,
            source="manual",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row.id
    finally:
        db.close()


def _mock_apify(monkeypatch, extracted_urls: list[str]):
    from app.linkedin import routes as linkedin_routes
    from app.linkedin.apify_extractor import RichBatchOutcome

    def mock_run_rich_batch(profile_urls):
        extracted_urls.extend(profile_urls)
        return RichBatchOutcome(
            results_by_url={
                url: {
                    "status": "ok",
                    "data": {
                        "name": "New Person",
                        "headline": "Engineer",
                        "company": "Fresh Inc",
                        "job_title": "Engineer",
                        "location": "NYC",
                        "summary": "About",
                        "followers": 10,
                        "connections": 20,
                        "profile_url": url,
                    },
                    "error": None,
                }
                for url in profile_urls
            },
            actor_run_id="mock-run",
        )

    monkeypatch.setattr(
        linkedin_routes.bulk_extract_service._runner.apify,
        "run_rich_batch",
        mock_run_rich_batch,
    )


def _upload_urls(client, urls: list[str], filename: str = "sheet.xlsx"):
    buffer = io.BytesIO()
    pd.DataFrame({"LinkedIn URL": urls}).to_excel(buffer, index=False, engine="openpyxl")
    resp = client.post(
        "/api/linkedin/bulk-extract",
        files={
            "file": (
                filename,
                buffer.getvalue(),
                "application/vnd.openxmlformats-officedocument.sheet",
            )
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["job_id"]


def test_new_url_calls_apify(client, monkeypatch):
    url = _uid_url("new")
    extracted: list[str] = []
    _mock_apify(monkeypatch, extracted)
    job_id = _upload_urls(client, [url])
    done = _wait_bulk_job(client, job_id)
    assert done["status"] == "done"
    assert extracted == [normalize_profile_url(url)]


def test_existing_icp_skips_apify(client, monkeypatch):
    url = _uid_url("existing")
    _seed_icp(url)
    extracted: list[str] = []
    _mock_apify(monkeypatch, extracted)
    job_id = _upload_urls(client, [url])
    done = _wait_bulk_job(client, job_id)
    assert done["status"] == "done"
    assert extracted == []
    results = client.get(f"/api/linkedin/bulk-jobs/{job_id}/results").json()
    item = results["items"][0]
    assert item["verification_status"] == "ALREADY_EXISTS"
    assert item["attempt_count"] == 0


def test_duplicate_excel_urls_single_apify_call(client, monkeypatch):
    url = _uid_url("dup")
    extracted: list[str] = []
    _mock_apify(monkeypatch, extracted)
    urls = [url] * 100
    job_id = _upload_urls(client, urls, filename="dups.xlsx")
    done = _wait_bulk_job(client, job_id)
    assert done["status"] == "done"
    assert extracted == [normalize_profile_url(url)]
    assert done["successful_profiles"] == 100


def test_mixed_upload_apify_only_new_valid(client, monkeypatch):
    existing = _uid_url("mix-existing")
    new_a = _uid_url("mix-a")
    new_b = _uid_url("mix-b")
    new_c = _uid_url("mix-c")
    _seed_icp(existing)
    extracted: list[str] = []
    _mock_apify(monkeypatch, extracted)

    urls = (
        [existing] * 3
        + [new_a, new_b, new_c]
        + [new_a]
        + ["not-a-url", "https://example.com/x", ""]
    )
    job_id = _upload_urls(client, urls, filename="mixed.xlsx")
    done = _wait_bulk_job(client, job_id)
    assert done["status"] in {"done", "failed"}

    unique_new = {
        normalize_profile_url(new_a),
        normalize_profile_url(new_b),
        normalize_profile_url(new_c),
    }
    assert set(extracted) == unique_new
    assert len(extracted) == 3


def test_reuse_prior_extraction_skips_apify(client, monkeypatch):
    prior = _uid_url("prior")
    extracted: list[str] = []
    _mock_apify(monkeypatch, extracted)

    job1 = _upload_urls(client, [prior], filename="first.xlsx")
    done1 = _wait_bulk_job(client, job1)
    assert done1["status"] == "done"
    assert extracted == [normalize_profile_url(prior)]

    extracted.clear()
    job2 = _upload_urls(client, [prior], filename="second.xlsx")
    done2 = _wait_bulk_job(client, job2)
    assert done2["status"] == "done"
    assert extracted == []

    results = client.get(f"/api/linkedin/bulk-jobs/{job2}/results").json()
    item = results["items"][0]
    assert item["extraction_status"] == "SUCCESS"
    assert item["extracted"]["name"] == "New Person"
    assert item["attempt_count"] == 0


def test_cost_guard_unit_marks_icp_and_reuse():
    existing = _uid_url("unit-existing")
    prior = _uid_url("unit-prior")
    new_url = _uid_url("unit-new")
    db = SessionLocal()
    try:
        _seed_icp(existing)
        job_id = f"a{uuid.uuid4().hex[:31]}"
        prior_job_id = f"b{uuid.uuid4().hex[:31]}"
        job = BulkExtractJobRow(
            id=job_id,
            user_id=1,
            total_urls=2,
            status="running",
            phase="extracting",
        )
        db.add(job)
        db.flush()

        prior_job = BulkExtractJobRow(
            id=prior_job_id,
            user_id=1,
            total_urls=1,
            status="done",
            phase="completed",
            excel_finalized=True,
            success_count=1,
        )
        db.add(prior_job)
        db.flush()
        prior_item = BulkJobItemRow(
            job_id=prior_job.id,
            source_row_number=1,
            profile_url=prior,
            normalized_url=normalize_profile_url(prior),
            status=ITEM_SUCCESS,
            name="Prior Person",
            company="Prior Co",
            designation="VP",
            about="About prior",
            completed_at=datetime.now(timezone.utc),
            verification_status="VERIFIED",
            verification_score=100,
        )
        db.add(prior_item)
        db.flush()

        item_icp = BulkJobItemRow(
            job_id=job.id,
            source_row_number=1,
            profile_url=existing,
            normalized_url=normalize_profile_url(existing),
            status=ITEM_PROCESSING,
        )
        item_reuse = BulkJobItemRow(
            job_id=job.id,
            source_row_number=2,
            profile_url=prior,
            normalized_url=normalize_profile_url(prior),
            status=ITEM_PROCESSING,
        )
        item_new = BulkJobItemRow(
            job_id=job.id,
            source_row_number=3,
            profile_url=new_url,
            normalized_url=normalize_profile_url(new_url),
            status=ITEM_PROCESSING,
        )
        db.add_all([item_icp, item_reuse, item_new])
        db.commit()

        result = apply_cost_guard_to_claimed_items(
            db, job_id=job.id, items=[item_icp, item_reuse, item_new], user_id=1
        )
        assert result.stats.skipped_icp == 1
        assert result.stats.skipped_reuse == 1
        assert result.stats.eligible == 1
        assert result.eligible_items[0].normalized_url == normalize_profile_url(new_url)
        assert item_icp.status == ITEM_SUCCESS
        assert item_reuse.status == ITEM_SUCCESS
        assert item_reuse.name == "Prior Person"
        db.rollback()
    finally:
        db.close()


def test_download_does_not_call_apify(client, monkeypatch):
    url = _uid_url("dl")
    extracted: list[str] = []
    _mock_apify(monkeypatch, extracted)
    job_id = _upload_urls(client, [url])
    _wait_bulk_job(client, job_id)
    extracted.clear()

    resp = client.get(f"/api/linkedin/bulk-jobs/{job_id}/download")
    assert extracted == []
    assert resp.status_code in {200, 404, 502}


def test_recent_downloads_no_apify(client, monkeypatch):
    url = _uid_url("recent")
    extracted: list[str] = []
    _mock_apify(monkeypatch, extracted)
    job_id = _upload_urls(client, [url])
    _wait_bulk_job(client, job_id)
    extracted.clear()

    resp = client.get("/api/linkedin/recent-downloads")
    assert resp.status_code == 200, resp.text
    assert extracted == []
    payload = resp.json()
    assert "items" in payload
    assert any(i["job_id"] == job_id for i in payload["items"])


@pytest.mark.parametrize(
    "message,expect_retry,category_substr",
    [
        ("HTTP 429 rate limit", True, "transient"),
        ("temporary 503 server error", True, "transient"),
        ("profile not found", False, "permanent"),
        ("invalid url", False, "permanent"),
        ("private profile unavailable", False, "permanent"),
    ],
)
def test_retry_classification(message, expect_retry, category_substr):
    retryable, category = classify_extraction_error(message)
    assert retryable is expect_retry
    assert category_substr in category
