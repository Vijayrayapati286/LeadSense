import io
import re
import threading
import time
from unittest.mock import MagicMock

import pytest

from app.linkedin.apify_extractor import RichBatchOutcome
from app.linkedin.bulk_batch_runner import BulkBatchRunner, run_batch_with_retries, split_batches


def _ok_result(url: str) -> dict:
    return {
        "status": "ok",
        "data": {
            "name": "Test User",
            "headline": "Engineer",
            "company": "Acme",
            "job_title": "Dev",
            "location": "NYC",
            "summary": "About",
            "followers": 1,
            "connections": 2,
            "profile_url": url,
        },
        "error": None,
    }


def _failed_result(msg: str = "failed") -> dict:
    return {"status": "failed", "data": None, "error": msg}


class TestSplitBatches:
    def test_ten_urls_one_batch(self):
        urls = [f"https://www.linkedin.com/in/u{i}/" for i in range(10)]
        assert len(split_batches(urls, 10)) == 1
        assert len(split_batches(urls, 10)[0]) == 10

    def test_hundred_urls_ten_batches(self):
        urls = [f"https://www.linkedin.com/in/u{i}/" for i in range(100)]
        batches = split_batches(urls, 10)
        assert len(batches) == 10
        assert all(len(b) == 10 for b in batches)

    def test_hundred_five_urls_eleven_batches(self):
        urls = [f"https://www.linkedin.com/in/u{i}/" for i in range(105)]
        batches = split_batches(urls, 10)
        assert len(batches) == 11
        assert len(batches[-1]) == 5


def test_run_batch_with_retries_on_batch_error():
    apify = MagicMock()
    apify.run_rich_batch.side_effect = [
        RichBatchOutcome(
            results_by_url={"https://www.linkedin.com/in/a/": _failed_result("boom")},
            batch_error="boom",
        ),
        RichBatchOutcome(
            results_by_url={"https://www.linkedin.com/in/a/": _ok_result("https://www.linkedin.com/in/a/")},
        ),
    ]
    outcome = run_batch_with_retries(
        apify,
        ["https://www.linkedin.com/in/a/"],
        max_retries=2,
    )
    assert outcome.success_count == 1
    assert apify.run_rich_batch.call_count == 2


def test_concurrency_limit(client, monkeypatch):
    """At most max_workers batches run at the same time."""
    from app.config import get_settings
    from app.linkedin import routes as linkedin_routes
    from app.linkedin.bulk_batch_runner import BulkBatchRunner

    settings = get_settings()
    monkeypatch.setattr(settings, "apify_batch_size", 1)
    monkeypatch.setattr(settings, "max_concurrent_apify_runs", 2)
    monkeypatch.setattr(settings, "apify_max_retries", 0)
    monkeypatch.setattr(settings, "max_bulk_urls", 250)
    monkeypatch.setattr(settings, "bulk_retry_base_delay_seconds", 0)

    active = {"count": 0}
    peak = {"value": 0}
    lock = threading.Lock()

    def mock_run_rich_batch(urls):
        with lock:
            active["count"] += 1
            peak["value"] = max(peak["value"], active["count"])
        time.sleep(0.08)
        url = urls[0]
        with lock:
            active["count"] -= 1
        return RichBatchOutcome(
            results_by_url={url: _ok_result(url)},
            actor_run_id="run-mock",
        )

    runner = BulkBatchRunner(settings=settings)
    runner.apify.run_rich_batch = mock_run_rich_batch
    monkeypatch.setattr(linkedin_routes, "bulk_extract_service", type("S", (), {
        "process_job": runner.process_job,
    })())

    urls = [f"https://www.linkedin.com/in/u{i}/" for i in range(6)]
    import pandas as pd

    buffer = io.BytesIO()
    pd.DataFrame({"LinkedIn URL": urls}).to_excel(buffer, index=False, engine="openpyxl")
    content = buffer.getvalue()

    resp = client.post(
        "/api/linkedin/bulk-extract",
        files={"file": ("p.xlsx", content, "application/vnd.openxmlformats-officedocument.sheet")},
    )
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]

    deadline = time.time() + 15
    done = None
    while time.time() < deadline:
        status = client.get(f"/api/linkedin/bulk-jobs/{job_id}").json()
        if status["status"] == "done":
            done = status
            break
        time.sleep(0.05)

    assert done is not None
    assert done["successful_profiles"] == 6
    assert peak["value"] <= 2
    assert peak["value"] >= 2


def test_run_batch_with_retries_skips_successful_urls():
    apify = MagicMock()
    url_a = "https://www.linkedin.com/in/a/"
    url_b = "https://www.linkedin.com/in/b/"
    apify.run_rich_batch.side_effect = [
        RichBatchOutcome(
            results_by_url={
                url_a: _ok_result(url_a),
                url_b: _failed_result("empty"),
            }
        ),
        RichBatchOutcome(results_by_url={url_b: _ok_result(url_b)}),
    ]
    outcome = run_batch_with_retries(apify, [url_a, url_b], max_retries=2)
    assert outcome.success_count == 2
    assert apify.run_rich_batch.call_count == 2
    second_urls = apify.run_rich_batch.call_args_list[1].args[0]
    assert second_urls == [url_b]
    apify = MagicMock()
    apify.run_rich_batch.return_value = RichBatchOutcome(
        results_by_url={
            "https://www.linkedin.com/in/a/": _ok_result("https://www.linkedin.com/in/a/"),
            "https://www.linkedin.com/in/b/": _failed_result("missing"),
        },
        actor_run_id="run-1",
    )
    outcome = run_batch_with_retries(
        apify,
        [
            "https://www.linkedin.com/in/a/",
            "https://www.linkedin.com/in/b/",
        ],
        max_retries=0,
    )
    assert outcome.success_count == 1
    assert outcome.failure_count == 1


def test_duplicate_urls_deduped_before_batching():
    from app.linkedin.bulk_excel_service import BulkExcelService
    import pandas as pd

    svc = BulkExcelService()
    df = pd.DataFrame(
        {
            "LinkedIn URL": [
                "https://www.linkedin.com/in/alice/",
                "https://www.linkedin.com/in/alice/",
                "https://www.linkedin.com/in/bob/",
            ]
        }
    )
    rows = svc.extract_url_rows(df)
    assert len(rows) == 3
    assert sum(1 for r in rows if r["is_duplicate"]) == 1
    unique = {r["normalized_url"] for r in rows}
    assert unique == {
        "https://www.linkedin.com/in/alice/",
        "https://www.linkedin.com/in/bob/",
    }


def test_one_failed_batch_does_not_fail_whole_job(client, monkeypatch):
    from app.config import get_settings
    from app.linkedin import routes as linkedin_routes
    from app.linkedin.bulk_batch_runner import BulkBatchRunner

    settings = get_settings()
    monkeypatch.setattr(settings, "apify_batch_size", 1)
    monkeypatch.setattr(settings, "max_concurrent_apify_runs", 2)
    monkeypatch.setattr(settings, "apify_max_retries", 0)
    monkeypatch.setattr(settings, "max_bulk_urls", 250)
    monkeypatch.setattr(settings, "bulk_retry_base_delay_seconds", 0)

    call = {"n": 0}

    def mock_run_rich_batch(urls):
        call["n"] += 1
        url = urls[0]
        if "bad" in url:
            return RichBatchOutcome(
                results_by_url={url: _failed_result("batch failed")},
                batch_error="batch failed",
            )
        return RichBatchOutcome(results_by_url={url: _ok_result(url)}, actor_run_id="ok")

    runner = BulkBatchRunner(settings=settings)
    runner.apify.run_rich_batch = mock_run_rich_batch
    monkeypatch.setattr(linkedin_routes, "bulk_extract_service", type("S", (), {
        "process_job": runner.process_job,
    })())

    urls = [
        "https://www.linkedin.com/in/good/",
        "https://www.linkedin.com/in/bad/",
    ]
    import pandas as pd

    buffer = io.BytesIO()
    pd.DataFrame({"LinkedIn URL": urls}).to_excel(buffer, index=False, engine="openpyxl")
    content = buffer.getvalue()

    resp = client.post(
        "/api/linkedin/bulk-extract",
        files={"file": ("p.xlsx", content, "application/vnd.openxmlformats-officedocument.sheet")},
    )
    job_id = resp.json()["job_id"]

    deadline = time.time() + 15
    while time.time() < deadline:
        status = client.get(f"/api/linkedin/bulk-jobs/{job_id}").json()
        if status["status"] == "done":
            assert status["successful_profiles"] == 1
            assert status["failed_profiles"] == 1
            return
        time.sleep(0.05)
    pytest.fail("job did not complete")
