"""LinkedIn Profile Extractor API routes.

Isolated from Sales Navigator. Cookies never leave the server.
Uses Playwright first, then Apify fallback (engine=auto).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse

from app.linkedin.bulk_excel_service import BulkExcelError, BulkExcelService
from app.linkedin.bulk_jobs import (
    BulkExtractJob,
    bulk_job_store,
    create_job_with_items,
    list_recent_comparison_items,
)
from app.linkedin.bulk_service import BulkExtractService
from app.linkedin.excel_service import LinkedInExcelService
from app.linkedin.hybrid import HybridLinkedInProfileExtractor
from app.linkedin.apify_extractor import LinkedInApifyProfileExtractor
from app.linkedin.jobs import job_store
from app.linkedin.rate_limit import bulk_extract_limiter, profile_extract_limiter
from app.linkedin.schemas import (
    BulkJobCreateResponse,
    BulkJobResultsResponse,
    BulkJobStatusResponse,
    JobCreateResponse,
    JobStatusResponse,
    LinkedInExtractData,
    LinkedInExtractRequest,
    LinkedInExtractResponse,
    ProfileExtractRequest,
    ProfileExtractResponse,
)
from app.linkedin.validator import validate_profile_url
from app.middleware.auth import get_current_user
from app.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/linkedin", tags=["LinkedIn Profile Extractor"])

extractor = HybridLinkedInProfileExtractor()
apify_extractor = LinkedInApifyProfileExtractor()
excel_service = LinkedInExcelService()
bulk_excel_service = BulkExcelService()
bulk_extract_service = BulkExtractService()

EngineParam = Literal["auto", "playwright", "apify"]


def _bulk_job_status_response(job: BulkExtractJob) -> BulkJobStatusResponse:
        processed = job.completed + job.failed
        percent = int(round((processed / job.total) * 100)) if job.total else 0
        download_ready = bool(
            job.status in {"done", "failed"}
            and job.excel_finalized
            and job.excel_file
            and processed > 0
        )
        return BulkJobStatusResponse(
            job_id=job.job_id,
            status=job.status,
            phase=job.phase,
            total=job.total,
            completed=job.completed,
            failed=job.failed,
            retrying=job.retrying,
            processed=processed,
            success=job.completed,
            verified=job.verified,
            mismatched=job.mismatched,
            review=job.review,
            progress_percent=percent,
            total_profiles=job.total,
            processed_profiles=processed,
            successful_profiles=job.completed,
            failed_profiles=job.failed,
            total_batches=job.total_batches,
            completed_batches=job.completed_batches,
            started_at=job.started_at,
            completed_at=job.completed_at,
            excel_file=job.excel_file,
            download_ready=download_ready,
            error=job.error,
        )


@router.post("/extract", response_model=LinkedInExtractResponse)
def linkedin_extract(
    body: LinkedInExtractRequest,
    current_user: User = Depends(get_current_user),
):
    """Apify LinkedIn profile scrape → clean frontend JSON."""
    user_id = getattr(current_user, "id", None)
    rate_key = f"user:{user_id or 'anon'}"
    allowed, rate_msg = profile_extract_limiter.check(rate_key)
    if not allowed:
        return LinkedInExtractResponse(success=False, message=rate_msg, data=None)

    try:
        url = validate_profile_url(body.url)
    except ValueError as exc:
        return LinkedInExtractResponse(success=False, message=str(exc), data=None)

    logger.info(
        "LinkedIn /extract requested user_id=%s path=%s",
        user_id,
        url,
    )

    try:
        result = apify_extractor.extract_rich(url)
        if not result.get("success"):
            return LinkedInExtractResponse(
                success=False,
                message=result.get("message") or "No profile data returned",
                data=None,
            )
        return LinkedInExtractResponse(
            success=True,
            data=LinkedInExtractData(**(result.get("data") or {})),
            message=None,
        )
    except Exception as exc:
        logger.exception("linkedin/extract failed")
        return LinkedInExtractResponse(success=False, message=str(exc), data=None)


def _run_extraction(url: str, engine: EngineParam = "auto") -> ProfileExtractResponse:
    result = extractor.extract(url, engine=engine)
    if not result.ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.message)

    _, _filename, relative = excel_service.build_workbook(result.as_dict())
    source = result.source if result.source in {"playwright", "apify"} else None
    return ProfileExtractResponse(
        full_name=result.full_name,
        company=result.company,
        job_title=result.job_title,
        about=result.about,
        excel_file=relative,
        source=source,
    )


def _background_extract(job_id: str, url: str, engine: EngineParam = "auto") -> None:
    job_store.update(job_id, status="running")
    try:
        result = extractor.extract(url, engine=engine)
        if not result.ok:
            job_store.update(job_id, status="failed", error=result.message)
            return
        _, _filename, relative = excel_service.build_workbook(result.as_dict())
        payload = {
            "full_name": result.full_name,
            "company": result.company,
            "job_title": result.job_title,
            "about": result.about,
            "excel_file": relative,
            "source": result.source if result.source in {"playwright", "apify"} else None,
        }
        job_store.update(job_id, status="done", result=payload)
    except Exception as exc:
        logger.exception("Background LinkedIn extract failed job_id=%s", job_id)
        job_store.update(job_id, status="failed", error=str(exc))


@router.post(
    "/extract-profile",
    response_model=ProfileExtractResponse | JobCreateResponse,
)
def extract_profile(
    body: ProfileExtractRequest,
    background_tasks: BackgroundTasks,
    async_mode: bool = Query(False, alias="async"),
    engine: EngineParam = Query(
        "auto",
        description="auto = Playwright then Apify fallback; or force one engine",
    ),
    current_user: User = Depends(get_current_user),
):
    """Extract Full Name, Company, Designation, About from a LinkedIn /in/ URL."""
    user_id = getattr(current_user, "id", None)
    rate_key = f"user:{user_id or 'anon'}"
    allowed, rate_msg = profile_extract_limiter.check(rate_key)
    if not allowed:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=rate_msg)

    try:
        url = validate_profile_url(body.url)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    logger.info(
        "LinkedIn profile extract requested user_id=%s async=%s engine=%s path=%s",
        user_id,
        async_mode,
        engine,
        url,
    )

    if async_mode:
        job = job_store.create(user_id=user_id, url=url)
        background_tasks.add_task(_background_extract, job.job_id, url, engine)
        return JobCreateResponse(job_id=job.job_id, status="pending")

    return _run_extraction(url, engine=engine)


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
):
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    user_id = getattr(current_user, "id", None)
    if job.user_id is not None and user_id is not None and job.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    result = None
    if job.result:
        result = ProfileExtractResponse(**job.result)

    return JobStatusResponse(
        job_id=job.job_id,
        status=job.status,
        result=result,
        error=job.error,
    )


@router.get("/download/{filename}")
def download_excel(
    filename: str,
    current_user: User = Depends(get_current_user),
):
    """Download a previously generated profile Excel (auth required)."""
    path: Path | None = excel_service.resolve_safe_path(filename)
    if path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    logger.info(
        "LinkedIn Excel download user_id=%s file=%s",
        getattr(current_user, "id", None),
        filename,
    )
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=filename,
    )


def _background_bulk_extract(job_id: str, file_content: bytes | None = None, filename: str | None = None) -> None:
    bulk_extract_service.process_job(job_id, file_content=file_content, filename=filename)


@router.post("/bulk-extract", response_model=BulkJobCreateResponse)
async def bulk_extract(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Upload Excel/CSV with LinkedIn URLs; extract profiles in background → filled Excel."""
    user_id = getattr(current_user, "id", None)
    rate_key = f"bulk:user:{user_id or 'anon'}"
    allowed, rate_msg = bulk_extract_limiter.check(rate_key)
    if not allowed:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=rate_msg)

    filename = file.filename or ""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty")

    try:
        df = bulk_excel_service.read_upload(content, filename)
        url_rows = bulk_excel_service.extract_url_rows(df)
        input_columns = bulk_excel_service.input_columns(df)
    except BulkExcelError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    job = create_job_with_items(
        user_id=user_id,
        original_file_name=filename,
        input_columns=input_columns,
        url_rows=url_rows,
    )
    background_tasks.add_task(_background_bulk_extract, job.id)

    logger.info(
        "Bulk LinkedIn extract queued job_id=%s user_id=%s urls=%s",
        job.id,
        user_id,
        len(url_rows),
    )
    return BulkJobCreateResponse(job_id=job.id, total=len(url_rows))


@router.get("/bulk-jobs/{job_id}", response_model=BulkJobStatusResponse)
def get_bulk_job_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
):
    job = bulk_job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    user_id = getattr(current_user, "id", None)
    if job.user_id is not None and user_id is not None and job.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    return _bulk_job_status_response(job)



@router.get("/bulk-jobs/{job_id}/results", response_model=BulkJobResultsResponse)
def get_bulk_job_results(
    job_id: str,
    limit: int = Query(25, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    job = bulk_job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    user_id = getattr(current_user, "id", None)
    if job.user_id is not None and user_id is not None and job.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    items = list_recent_comparison_items(job_id, limit=limit)
    return BulkJobResultsResponse(job_id=job_id, items=items)


@router.get("/bulk-jobs/{job_id}/download")
def download_bulk_job_excel(
    job_id: str,
    current_user: User = Depends(get_current_user),
):
    """Download partial or final Excel for a bulk job."""
    job = bulk_job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    user_id = getattr(current_user, "id", None)
    if job.user_id is not None and user_id is not None and job.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    if not job.excel_finalized or not job.excel_file or (job.completed + job.failed) <= 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Result Excel is not ready yet",
        )

    filename = job.excel_file.split("/")[-1]
    path: Path | None = bulk_excel_service.resolve_safe_path(filename)
    if path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    logger.info(
        "Bulk job Excel download user_id=%s job_id=%s file=%s status=%s",
        user_id,
        job_id,
        filename,
        job.status,
    )
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=filename,
    )


@router.get("/bulk-download/{filename}")
def download_bulk_excel(
    filename: str,
    current_user: User = Depends(get_current_user),
):
    """Download a bulk-enriched profile Excel workbook."""
    path: Path | None = bulk_excel_service.resolve_safe_path(filename)
    if path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    logger.info(
        "Bulk LinkedIn Excel download user_id=%s file=%s",
        getattr(current_user, "id", None),
        filename,
    )
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=filename,
    )
