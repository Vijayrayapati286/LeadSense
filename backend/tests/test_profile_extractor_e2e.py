"""BuildE2E: profile extractor cache + Apify mock (no real Apify calls)."""

from __future__ import annotations

import time


def _wait_job(client, job_id: str, *, timeout_s: float = 3.0) -> dict:
    start = time.time()
    while time.time() - start < timeout_s:
        res = client.get(f"/api/v1/profile/{job_id}")
        assert res.status_code == 200, res.text
        payload = res.json()
        if payload["status"] in {"completed", "failed"}:
            return payload
        time.sleep(0.05)
    raise AssertionError(f"Timed out waiting for profile job {job_id}")


def test_profile_extract_apify_flow_and_cache_hit(client, monkeypatch):
    from app.profile_extractor import routes as pe_routes

    calls = {"n": 0}

    def _fake_extract(url: str) -> dict:
        calls["n"] += 1
        return {
            "full_name": "Jane Cache",
            "company": "Cache Co",
            "designation": "Engineer",
            "about": "Cached about text",
        }

    monkeypatch.setattr(pe_routes.profile_service.apify, "extract", _fake_extract)

    url = "https://www.linkedin.com/in/jane-cache"

    # First request: miss → queued → Apify mock → completed.
    r1 = client.post("/api/v1/profile/extract", json={"url": url})
    assert r1.status_code == 200, r1.text
    body1 = r1.json()
    assert body1["status"] == "queued"
    job1 = _wait_job(client, body1["job_id"])
    assert job1["status"] == "completed"
    assert job1["result"]["full_name"] == "Jane Cache"
    assert calls["n"] == 1

    # Second request: cache hit → completed immediately, no second Apify call.
    r2 = client.post("/api/v1/profile/extract", json={"url": url})
    assert r2.status_code == 200, r2.text
    body2 = r2.json()
    assert body2["status"] == "completed"
    assert calls["n"] == 1

    job2 = client.get(f"/api/v1/profile/{body2['job_id']}")
    assert job2.status_code == 200
    payload2 = job2.json()
    assert payload2["status"] == "completed"
    assert payload2["result"]["company"] == "Cache Co"

    # Excel download from completed job.
    assert payload2["download_url"]
    dl = client.get(payload2["download_url"])
    assert dl.status_code == 200
    assert len(dl.content) > 0


def test_profile_extract_apify_failure_returns_failed_job(client, monkeypatch):
    from app.profile_extractor import routes as pe_routes
    from app.profile_extractor.apify_service import ProfileApifyError

    def _boom(url: str):
        raise ProfileApifyError("mock provider failure")

    monkeypatch.setattr(pe_routes.profile_service.apify, "extract", _boom)

    r = client.post(
        "/api/v1/profile/extract",
        json={"url": "https://www.linkedin.com/in/fail-case"},
    )
    assert r.status_code == 200, r.text
    job = _wait_job(client, r.json()["job_id"])
    assert job["status"] == "failed"
    assert "mock provider failure" in (job["error"] or "")
