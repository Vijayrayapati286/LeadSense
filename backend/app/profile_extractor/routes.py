"""LeadSense Profile Extractor API — /api/v1/profile/*

Apify-only public /in/ extraction. Isolated from Sales Nav and Playwright modules.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.middleware.auth import get_current_user
from app.models import User
from app.profile_extractor.excel_service import ProfileExcelService
from app.profile_extractor.profile_service import ProfileService
from app.profile_extractor.rate_limit import profile_extract_limiter
from app.profile_extractor.schemas import (
    ProfileData,
    ProfileExtractQueuedResponse,
    ProfileExtractRequest,
    ProfileJobResponse,
)
from app.profile_extractor.validator import validate_profile_url

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/profile", tags=["LeadSense Profile Extractor"])

profile_service = ProfileService()
excel_service = ProfileExcelService()


@router.post("/extract", response_model=ProfileExtractQueuedResponse)
def extract_profile(
    body: ProfileExtractRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = getattr(current_user, "id", None)
    allowed, rate_msg = profile_extract_limiter.check(f"user:{user_id or 'anon'}")
    if not allowed:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=rate_msg)

    try:
        url = validate_profile_url(body.url)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    # Log path only — never extracted PII.
    logger.info("Profile extract queued user_id=%s", user_id)

    job, from_cache = profile_service.create_job(db, profile_url=url, user_id=user_id)
    if not from_cache:
        background_tasks.add_task(profile_service.process_job, job.id)

    return ProfileExtractQueuedResponse(
        job_id=job.id,
        status="completed" if from_cache else "queued",
    )


@router.get("/{job_id}", response_model=ProfileJobResponse)
def get_profile_job(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = profile_service.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    user_id = getattr(current_user, "id", None)
    if job.user_id is not None and user_id is not None and job.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    result = None
    download_url = None
    if job.status == "completed" and job.profile:
        result = ProfileData(
            full_name=job.profile.full_name,
            company=job.profile.company,
            designation=job.profile.designation,
            about=job.profile.about,
        )
        download_url = f"/api/v1/profile/{job.id}/download"

    return ProfileJobResponse(
        job_id=job.id,
        status=job.status,  # type: ignore[arg-type]
        profile_url=job.profile_url,
        result=result,
        download_url=download_url,
        error=job.error,
        cached=False,
    )


@router.get("/{job_id}/download")
def download_profile_excel(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = profile_service.get_job(db, job_id)
    if not job or job.status != "completed" or not job.excel_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    user_id = getattr(current_user, "id", None)
    if job.user_id is not None and user_id is not None and job.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    path = Path(job.excel_path)
    filename = path.name
    safe = excel_service.resolve_safe_path(filename)
    if safe is None:
        # Fallback: path stored from this service's outputs dir
        if not path.is_file():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
        safe = path

    logger.info("Profile Excel download job_id=%s user_id=%s", job_id, user_id)
    return FileResponse(
        safe,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=filename,
    )
