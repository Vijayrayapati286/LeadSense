import io
import re
import time

import pytest


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


def _make_xlsx(urls: list[str]) -> bytes:
    import pandas as pd

    buffer = io.BytesIO()
    df = pd.DataFrame({"LinkedIn URL": urls})
    df.to_excel(buffer, index=False, engine="openpyxl")
    return buffer.getvalue()


def test_bulk_extract_lifecycle_and_download(client, monkeypatch):
    from app.linkedin import routes as linkedin_routes
    from app.linkedin.apify_extractor import RichBatchOutcome

    urls = [
        "https://www.linkedin.com/in/alice/",
        "https://www.linkedin.com/in/bob/",
    ]

    def mock_run_rich_batch(profile_urls):
        return RichBatchOutcome(
            results_by_url={
                url: {
                    "status": "ok",
                    "data": {
                        "name": f"User {i}",
                        "headline": "Engineer",
                        "company": "Acme",
                        "job_title": "Dev",
                        "location": "NYC",
                        "summary": "About text",
                        "followers": 100,
                        "connections": 500,
                        "profile_url": url,
                    },
                    "error": None,
                }
                for i, url in enumerate(profile_urls)
            },
            actor_run_id="mock-run",
        )

    monkeypatch.setattr(
        linkedin_routes.bulk_extract_service._runner.apify,
        "run_rich_batch",
        mock_run_rich_batch,
    )

    content = _make_xlsx(urls)
    resp = client.post(
        "/api/linkedin/bulk-extract",
        files={"file": ("profiles.xlsx", content, "application/vnd.openxmlformats-officedocument.sheet")},
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["total"] == 2
    job_id = payload["job_id"]

    done = _wait_bulk_job(client, job_id)
    assert done["status"] == "done", done
    assert done["successful_profiles"] == 2
    assert done["failed_profiles"] == 0
    assert done["excel_file"].startswith("outputs/")

    filename = done["excel_file"].split("/")[-1]
    assert re.match(r"^bulk_[0-9a-f-]{36}\.xlsx$", filename)

    download = client.get(f"/api/linkedin/bulk-jobs/{job_id}/download")
    assert download.status_code == 200
    assert (
        download.headers.get("content-type", "")
        .startswith("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    )
    assert len(download.content) > 100

    assert done["download_ready"] is True


def test_bulk_extract_rejects_empty_file(client):
    resp = client.post(
        "/api/linkedin/bulk-extract",
        files={"file": ("empty.xlsx", b"", "application/vnd.openxmlformats-officedocument.sheet")},
    )
    assert resp.status_code == 400
