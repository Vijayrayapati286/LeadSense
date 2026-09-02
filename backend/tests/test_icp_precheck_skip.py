"""ICP Database pre-check skips extraction for URLs already in ICP."""

from __future__ import annotations

import io
import time
from datetime import datetime, timezone

import pandas as pd
import pytest

from app.database.connection import SessionLocal, init_db
from app.icp.models import IcpRecordRow
from app.linkedin.validator import normalize_profile_url


EXISTING_URL = "https://www.linkedin.com/in/existing-user/"
NEW_URL = "https://www.linkedin.com/in/brand-new/"
EMAIL_SYNC_URL = "https://www.linkedin.com/in/josh-hailey-b3392064/"


@pytest.fixture(autouse=True)
def _schema():
    init_db()


def _wait_bulk_job(client, job_id: str, *, timeout_s: float = 15.0):
    start = time.time()
    while time.time() - start < timeout_s:
        res = client.get(f"/api/linkedin/bulk-jobs/{job_id}")
        assert res.status_code == 200, res.text
        payload = res.json()
        if payload["status"] in {"done", "failed"}:
            return payload
        time.sleep(0.05)
    raise AssertionError(f"Timed out waiting for bulk job {job_id}")


def _seed_icp_with_linkedin(*, linkedin_url: str, name: str = "Existing User") -> int:
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
        row = IcpRecordRow(
            user_id=1,
            name=name,
            company_name="Known Co",
            designation="Director",
            about="Already verified",
            linkedin_url=normalized,
            location="Boston",
            verification_status="VERIFIED",
            verified_at=datetime.now(timezone.utc),
            source="manual",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row.id
    finally:
        db.close()


def test_sheet_email_synced_on_upload(client, monkeypatch):
    """Email column from spreadsheet is saved to ICP/Contacts immediately on upload."""
    from app.linkedin import routes as linkedin_routes
    from app.linkedin.apify_extractor import RichBatchOutcome

    def mock_run_rich_batch(profile_urls):
        return RichBatchOutcome(
            results_by_url={
                url: {
                    "status": "ok",
                    "data": {
                        "name": "Josh Hailey",
                        "headline": "VP",
                        "company": "BankFirst Financial Services",
                        "job_title": "VP, Director of Technology",
                        "location": "Macon, Mississippi",
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

    buffer = io.BytesIO()
    pd.DataFrame(
        {
            "FIRST NAME": ["Josh"],
            "LAST NAME": ["Hailey"],
            "EMAIL": ["jhailey@bankfirstfs.com"],
            "TITLE": ["VP, Director of Technology"],
            "COMPANY NAME": ["BankFirst Financial Services"],
            "PERSON LINKEDIN URL": [EMAIL_SYNC_URL],
            "INDUSTRY": ["banking"],
        }
    ).to_excel(buffer, index=False, engine="openpyxl")

    resp = client.post(
        "/api/linkedin/bulk-extract",
        files={"file": ("contacts.xlsx", buffer.getvalue(), "application/vnd.openxmlformats-officedocument.sheet")},
    )
    assert resp.status_code == 200, resp.text

    db = SessionLocal()
    try:
        row = (
            db.query(IcpRecordRow)
            .filter(IcpRecordRow.linkedin_url == normalize_profile_url(EMAIL_SYNC_URL))
            .first()
        )
        assert row is not None, "ICP record should be created from sheet on upload"
        assert row.email == "jhailey@bankfirstfs.com"
        assert row.name == "Josh Hailey"
        assert row.company_name == "BankFirst Financial Services"
        assert row.industry == "banking"
    finally:
        db.close()


def test_sheet_email_updates_existing_icp_on_reupload(client, monkeypatch):
    """Re-uploading a sheet with email updates an existing ICP record that had no email."""
    from app.linkedin import routes as linkedin_routes
    from app.linkedin.apify_extractor import RichBatchOutcome

    _seed_icp_with_linkedin(linkedin_url=EXISTING_URL)

    def mock_run_rich_batch(profile_urls):
        return RichBatchOutcome(results_by_url={}, actor_run_id="mock-run")

    monkeypatch.setattr(
        linkedin_routes.bulk_extract_service._runner.apify,
        "run_rich_batch",
        mock_run_rich_batch,
    )

    buffer = io.BytesIO()
    pd.DataFrame(
        {
            "FIRST NAME": ["Existing"],
            "LAST NAME": ["User"],
            "EMAIL": ["existing.user@example.com"],
            "PERSON LINKEDIN URL": [EXISTING_URL],
        }
    ).to_excel(buffer, index=False, engine="openpyxl")

    resp = client.post(
        "/api/linkedin/bulk-extract",
        files={"file": ("update.xlsx", buffer.getvalue(), "application/vnd.openxmlformats-officedocument.sheet")},
    )
    assert resp.status_code == 200, resp.text

    db = SessionLocal()
    try:
        row = (
            db.query(IcpRecordRow)
            .filter(IcpRecordRow.linkedin_url == normalize_profile_url(EXISTING_URL))
            .first()
        )
        assert row is not None
        assert row.email == "existing.user@example.com"
    finally:
        db.close()


def test_icp_precheck_skips_extraction_and_in_file_duplicates(client, monkeypatch):
    from app.linkedin import routes as linkedin_routes
    from app.linkedin.apify_extractor import RichBatchOutcome

    _seed_icp_with_linkedin(linkedin_url=EXISTING_URL)

    extracted_urls: list[str] = []

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

    buffer = io.BytesIO()
    pd.DataFrame(
        {
            "LinkedIn URL": [
                EXISTING_URL,
                EXISTING_URL,  # in-file duplicate
                NEW_URL,
            ],
        }
    ).to_excel(buffer, index=False, engine="openpyxl")

    resp = client.post(
        "/api/linkedin/bulk-extract",
        files={"file": ("mixed.xlsx", buffer.getvalue(), "application/vnd.openxmlformats-officedocument.sheet")},
    )
    assert resp.status_code == 200, resp.text
    job_id = resp.json()["job_id"]

    done = _wait_bulk_job(client, job_id)
    assert done["status"] == "done", done
    assert done["successful_profiles"] == 3
    assert done["failed_profiles"] == 0

    # Apify should only run for the one URL not already in ICP.
    assert extracted_urls == [normalize_profile_url(NEW_URL)]

    results = client.get(f"/api/linkedin/bulk-jobs/{job_id}/results")
    assert results.status_code == 200
    by_url = {item["url"]: item for item in results.json()["items"]}

    existing = by_url[normalize_profile_url(EXISTING_URL)]
    assert existing["verification_status"] == "ALREADY_EXISTS"
    assert existing["extraction_status"] == "SUCCESS"
    assert existing["attempt_count"] == 0
    assert existing["needs_review"] is False
    assert existing["extracted"]["name"] == "Existing User"
    assert existing["extracted"]["company"] == "Known Co"

    new_item = by_url[normalize_profile_url(NEW_URL)]
    assert new_item["extraction_status"] == "SUCCESS"
    assert new_item["attempt_count"] >= 1
    assert new_item["extracted"]["name"] == "New Person"

    # In-file duplicate row should mirror the ICP skip without extra extraction.
    items = client.get(f"/api/linkedin/bulk-jobs/{job_id}/items").json()["items"]
    existing_rows = [i for i in items if i["url"] == normalize_profile_url(EXISTING_URL)]
    assert len(existing_rows) == 2
    assert all(r["verification_status"] == "ALREADY_EXISTS" for r in existing_rows)
    assert all(r["attempt_count"] == 0 for r in existing_rows)
