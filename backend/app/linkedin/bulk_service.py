"""Orchestrate bulk LinkedIn profile extraction from uploaded Excel."""

from __future__ import annotations

from app.linkedin.bulk_batch_runner import BulkBatchRunner


class BulkExtractService:
    def __init__(self) -> None:
        self._runner = BulkBatchRunner()

    def process_job(
        self,
        job_id: str,
        *,
        file_content: bytes | None = None,
        filename: str | None = None,
    ) -> None:
        self._runner.process_job(job_id, file_content=file_content, filename=filename)


def resume_incomplete_bulk_jobs() -> None:
    """Continue PENDING/RUNNING jobs after process restart. Skipped under pytest."""
    import os
    import threading

    if os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("SKIP_BULK_RESUME"):
        return
    from app.linkedin.bulk_jobs import list_incomplete_job_ids

    ids = list_incomplete_job_ids()
    if not ids:
        return
    service = BulkExtractService()
    for job_id in ids:
        threading.Thread(
            target=service.process_job,
            args=(job_id,),
            name=f"bulk-resume-{job_id[:8]}",
            daemon=True,
        ).start()
