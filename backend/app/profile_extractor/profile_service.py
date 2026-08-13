"""Orchestrate profile extract jobs: cache → Apify → Excel → DB."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.database.connection import SessionLocal
from app.profile_extractor.apify_service import ProfileApifyError, ProfileApifyService
from app.profile_extractor.cache_service import ProfileCacheService
from app.profile_extractor.excel_service import ProfileExcelService
from app.profile_extractor.models import ProfileExtractJob, ProfileExtractResult

logger = logging.getLogger(__name__)


class ProfileService:
    def __init__(self) -> None:
        self.apify = ProfileApifyService()
        self.cache = ProfileCacheService()
        self.excel = ProfileExcelService()

    def create_job(
        self,
        db: Session,
        *,
        profile_url: str,
        user_id: int | None,
    ) -> tuple[ProfileExtractJob, bool]:
        """
        Create a job. If cache hit, complete immediately.
        Returns (job, from_cache).
        """
        cached = self.cache.get(db, profile_url)
        job_id = str(uuid.uuid4())

        if cached:
            _, filename, path = self.excel.build_workbook(cached)
            job = ProfileExtractJob(
                id=job_id,
                user_id=user_id,
                profile_url=profile_url,
                status="completed",
                excel_path=str(path),
                completed_at=datetime.now(timezone.utc),
            )
            db.add(job)
            db.flush()
            db.add(
                ProfileExtractResult(
                    job_id=job_id,
                    full_name=cached.get("full_name"),
                    company=cached.get("company"),
                    designation=cached.get("designation"),
                    about=cached.get("about"),
                )
            )
            db.commit()
            db.refresh(job)
            logger.info("Profile job %s completed from cache", job_id)
            return job, True

        job = ProfileExtractJob(
            id=job_id,
            user_id=user_id,
            profile_url=profile_url,
            status="queued",
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job, False

    def process_job(self, job_id: str) -> None:
        """Background worker entry — opens its own DB session."""
        db = SessionLocal()
        try:
            job = db.query(ProfileExtractJob).filter(ProfileExtractJob.id == job_id).first()
            if not job:
                return
            if job.status == "completed":
                return

            job.status = "processing"
            db.commit()

            try:
                fields = self.apify.extract(job.profile_url)
                _, _filename, path = self.excel.build_workbook(fields)
                self.cache.set(db, job.profile_url, fields)

                existing = (
                    db.query(ProfileExtractResult)
                    .filter(ProfileExtractResult.job_id == job_id)
                    .first()
                )
                if existing:
                    existing.full_name = fields.get("full_name")
                    existing.company = fields.get("company")
                    existing.designation = fields.get("designation")
                    existing.about = fields.get("about")
                else:
                    db.add(
                        ProfileExtractResult(
                            job_id=job_id,
                            full_name=fields.get("full_name"),
                            company=fields.get("company"),
                            designation=fields.get("designation"),
                            about=fields.get("about"),
                        )
                    )

                job.status = "completed"
                job.excel_path = str(path)
                job.completed_at = datetime.now(timezone.utc)
                job.error = None
                db.commit()
                logger.info("Profile job %s completed via Apify", job_id)
            except ProfileApifyError as exc:
                job.status = "failed"
                job.error = exc.message
                job.completed_at = datetime.now(timezone.utc)
                db.commit()
                logger.warning("Profile job %s failed: %s", job_id, exc.message)
            except Exception as exc:
                job.status = "failed"
                job.error = "Extraction failed due to an internal error"
                job.completed_at = datetime.now(timezone.utc)
                db.commit()
                logger.exception("Profile job %s unexpected error: %s", job_id, exc)
        finally:
            db.close()

    def get_job(self, db: Session, job_id: str) -> ProfileExtractJob | None:
        return db.query(ProfileExtractJob).filter(ProfileExtractJob.id == job_id).first()

    def excel_filename(self, job: ProfileExtractJob) -> str | None:
        if not job.excel_path:
            return None
        return Path(job.excel_path).name
