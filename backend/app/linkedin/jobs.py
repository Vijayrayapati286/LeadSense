"""In-memory background job store for LinkedIn profile extraction."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

JobStatus = Literal["pending", "running", "done", "failed"]


@dataclass
class ExtractJob:
    job_id: str
    user_id: int | None
    url: str
    status: JobStatus = "pending"
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class JobStore:
    """Thread-safe in-memory jobs. Swap for Redis later without changing routes."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, ExtractJob] = {}

    def create(self, *, user_id: int | None, url: str) -> ExtractJob:
        job = ExtractJob(job_id=str(uuid.uuid4()), user_id=user_id, url=url)
        with self._lock:
            self._jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> ExtractJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update(
        self,
        job_id: str,
        *,
        status: JobStatus | None = None,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> ExtractJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            if status is not None:
                job.status = status
            if result is not None:
                job.result = result
            if error is not None:
                job.error = error
            job.updated_at = datetime.now(timezone.utc).isoformat()
            return job


job_store = JobStore()
