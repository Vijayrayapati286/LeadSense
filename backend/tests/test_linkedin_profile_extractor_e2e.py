import re
import time

import pytest


def _mock_profile_result(playwright: bool = True):
    from app.linkedin.extractor import ProfileResult

    return ProfileResult(
        ok=True,
        message="ok",
        full_name="John Doe",
        company="Acme Inc",
        job_title="Senior Engineer",
        about="About section text.",
        source="playwright" if playwright else "apify",
    )


def _wait_until(client, url: str, *, timeout_s: float = 2.0):
    start = time.time()
    while time.time() - start < timeout_s:
        res = client.get(url)
        if res.status_code != 200:
            raise AssertionError(f"GET {url} failed: {res.status_code} {res.text}")
        payload = res.json()
        if payload["status"] in {"done", "failed"}:
            return payload
        time.sleep(0.05)
    raise AssertionError(f"Timed out waiting for {url} to reach done/failed")


def test_linkedin_extract_profile_sync_success(client, monkeypatch):
    from app.linkedin import routes as linkedin_routes

    monkeypatch.setattr(linkedin_routes.extractor, "extract", lambda url, engine="auto": _mock_profile_result(True))

    resp = client.post(
        "/api/linkedin/extract-profile",
        json={"url": "https://www.linkedin.com/in/example"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["full_name"] == "John Doe"
    assert data["company"] == "Acme Inc"
    assert data["job_title"] == "Senior Engineer"
    assert data["about"] == "About section text."

    assert data["source"] == "playwright"
    assert data["excel_file"].startswith("outputs/")
    assert re.match(r"^outputs/profile_\d{8}_\d{6}\.xlsx$", data["excel_file"])


def test_linkedin_extract_profile_async_lifecycle_and_download(client, monkeypatch):
    from app.linkedin import routes as linkedin_routes

    monkeypatch.setattr(linkedin_routes.extractor, "extract", lambda url, engine="auto": _mock_profile_result(True))

    resp = client.post(
        "/api/linkedin/extract-profile?async=true",
        json={"url": "https://www.linkedin.com/in/example-async"},
    )
    assert resp.status_code == 200, resp.text
    job_payload = resp.json()
    assert "job_id" in job_payload
    job_id = job_payload["job_id"]
    assert job_payload["status"] == "pending"

    status_url = f"/api/linkedin/jobs/{job_id}"
    job_done_payload = _wait_until(client, status_url, timeout_s=2.0)
    assert job_done_payload["status"] == "done", job_done_payload
    assert job_done_payload["result"] is not None

    excel_file = job_done_payload["result"]["excel_file"]
    filename = excel_file.split("/")[-1]
    assert re.match(r"^profile_\d{8}_\d{6}\.xlsx$", filename)

    download_resp = client.get(f"/api/linkedin/download/{filename}")
    assert download_resp.status_code == 200, download_resp.text
    assert download_resp.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert len(download_resp.content) > 0


def test_linkedin_extract_profile_async_failure_marks_job_failed(client, monkeypatch):
    from app.linkedin import routes as linkedin_routes
    from app.linkedin.extractor import ProfileResult

    monkeypatch.setattr(
        linkedin_routes.extractor,
        "extract",
        lambda url, engine="auto": ProfileResult(ok=False, message="mock extraction failure"),
    )

    resp = client.post(
        "/api/linkedin/extract-profile?async=true",
        json={"url": "https://www.linkedin.com/in/example-fail"},
    )
    assert resp.status_code == 200, resp.text
    job_payload = resp.json()
    job_id = job_payload["job_id"]

    status_url = f"/api/linkedin/jobs/{job_id}"
    job_done_payload = _wait_until(client, status_url, timeout_s=2.0)
    assert job_done_payload["status"] == "failed"
    assert "error" in job_done_payload
    assert "mock extraction failure" in (job_done_payload["error"] or "")


def test_linkedin_extract_profile_rate_limited(client, monkeypatch):
    from app.linkedin import routes as linkedin_routes
    from app.linkedin.rate_limit import profile_extract_limiter

    # Make limit small for the test. Restore after via monkeypatch cleanup.
    monkeypatch.setattr(profile_extract_limiter, "max_calls", 2)
    monkeypatch.setattr(profile_extract_limiter, "window_seconds", 3600)
    profile_extract_limiter._hits.clear()

    monkeypatch.setattr(linkedin_routes.extractor, "extract", lambda url, engine="auto": _mock_profile_result(True))

    for i in range(2):
        resp = client.post("/api/linkedin/extract-profile", json={"url": f"https://www.linkedin.com/in/ex-{i}"})
        assert resp.status_code == 200, resp.text

    resp = client.post("/api/linkedin/extract-profile", json={"url": "https://www.linkedin.com/in/ex-overlimit"})
    assert resp.status_code == 429
    assert "Rate limit exceeded" in resp.json()["detail"]

