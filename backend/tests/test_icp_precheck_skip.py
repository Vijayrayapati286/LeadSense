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
        row = IcpRecordRow(
            user_id=1,
            name=name,
            company_name="Known Co",
            designation="Director",
            about="Already verified",
            linkedin_url=normalize_profile_url(linkedin_url),
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
