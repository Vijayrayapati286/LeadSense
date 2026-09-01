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

from app.database.connection import SessionLocal
from app.linkedin.backup_service import (
    BackupError,
    create_job_backup,
    resolve_backup_path,
    restore_backup,
)
from app.linkedin.bulk_excel_service import BulkExcelError, BulkExcelService, refresh_job_result_excel
from app.linkedin.bulk_jobs import (
    BulkExtractJob,
    bulk_job_store,
    create_job_with_items,
    get_job_row,
    list_job_items,
    list_jobs,
    list_recent_comparison_items,
)
from app.linkedin.bulk_models import BulkBackupRow, BulkExtractJobRow, BulkJobItemRow
from app.linkedin.bulk_service import BulkExtractService
from app.linkedin.conflict_service import (
    conflicting_fields,
    item_needs_review,
    list_job_audit,
    refresh_job_after_resolutions,
    resolve_item_fields,
)
from app.linkedin.excel_service import LinkedInExcelService
from app.linkedin.hybrid import HybridLinkedInProfileExtractor
from app.linkedin.apify_extractor import LinkedInApifyProfileExtractor
from app.linkedin.jobs import job_store
from app.linkedin.rate_limit import bulk_extract_limiter, profile_extract_limiter
from app.linkedin.schemas import (
    BackupCreateResponse,
    BackupListItem,
    BackupListResponse,
    BackupRestoreResponse,
    BulkJobCreateResponse,
    BulkJobItemsPageResponse,
    BulkJobListResponse,
    BulkJobResultsResponse,
    BulkJobStatusResponse,
    ConflictBulkResolveRequest,
    ConflictResolveRequest,
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
            needs_review=getattr(job, "needs_review", 0) or 0,
            resolved=getattr(job, "resolved", 0) or 0,
            backup_status=getattr(job, "backup_status", None) or "none",
            original_file_name=getattr(job, "original_file_name", None),
            progress_percent=percent,
            total_profiles=job.total,
            processed_profiles=processed,
            successful_profiles=job.completed,
            failed_profiles=job.failed,
            total_batches=job.total_batches,
            completed_batches=job.completed_batches,
            created_at=job.created_at or None,
            updated_at=job.updated_at or None,
            started_at=job.started_at,
            completed_at=job.completed_at,
            excel_file=job.excel_file,
            download_ready=download_ready,
            error=job.error,
        )


def _require_bulk_job(job_id: str, user_id: int | None) -> BulkExtractJob:
    job = bulk_job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if job.user_id is not None and user_id is not None and job.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


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

    # Persist original upload in S3 (metadata in Postgres — never store binaries in DB).
    try:
        from app.linkedin.s3_persist import persist_original_upload

        db = SessionLocal()
        try:
            persist_original_upload(
                db,
                user_id=user_id,
                batch_id=job.id,
                filename=filename,
                content=content,
                content_type=file.content_type,
            )
        finally:
            db.close()
    except Exception as exc:
        from app.storage.exceptions import FileValidationError, S3StorageError

        if isinstance(exc, FileValidationError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        if isinstance(exc, S3StorageError):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to store upload in S3: {exc}",
            ) from exc
        logger.exception("Unexpected S3 original-upload failure job_id=%s", job.id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to store upload in S3",
        ) from exc

    background_tasks.add_task(_background_bulk_extract, job.id)

    logger.info(
        "Bulk LinkedIn extract queued job_id=%s user_id=%s urls=%s",
        job.id,
        user_id,
        len(url_rows),
    )
    return BulkJobCreateResponse(job_id=job.id, total=len(url_rows))




@router.get("/bulk-jobs", response_model=BulkJobListResponse)
def list_bulk_jobs(
    q: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    phase: str | None = Query(None),
    needs_review: bool | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    user_id = getattr(current_user, "id", None)
    payload = list_jobs(
        user_id=user_id,
        q=q,
        status=status_filter,
        phase=phase,
        needs_review=needs_review,
        page=page,
        page_size=page_size,
    )
    return BulkJobListResponse(
        total=payload["total"],
        page=payload["page"],
        page_size=payload["page_size"],
        items=[_bulk_job_status_response(j) for j in payload["items"]],
    )


@router.get("/bulk-jobs/{job_id}/items", response_model=BulkJobItemsPageResponse)
def get_bulk_job_items(
    job_id: str,
    verification_status: str | None = Query(None),
    extraction_status: str | None = Query(None),
    needs_review: bool | None = Query(None),
    q: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    current_user: User = Depends(get_current_user),
):
    user_id = getattr(current_user, "id", None)
    _require_bulk_job(job_id, user_id)
    payload = list_job_items(
        job_id,
        verification_status=verification_status,
        extraction_status=extraction_status,
        needs_review=needs_review,
        q=q,
        page=page,
        page_size=page_size,
    )
    return BulkJobItemsPageResponse(
        job_id=job_id,
        total=payload["total"],
        page=payload["page"],
        page_size=payload["page_size"],
        items=payload["items"],
    )


@router.get("/bulk-jobs/{job_id}/conflicts")
def get_bulk_job_conflicts(
    job_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=500),
    current_user: User = Depends(get_current_user),
):
    user_id = getattr(current_user, "id", None)
    _require_bulk_job(job_id, user_id)
    payload = list_job_items(
        job_id,
        needs_review=True,
        page=page,
        page_size=page_size,
    )
    enriched = []
    db = SessionLocal()
    try:
        for item in payload["items"]:
            row = db.query(BulkJobItemRow).filter(BulkJobItemRow.id == item["item_id"]).first()
            fields = item.get("conflicts") or (conflicting_fields(row) if row else [])
            # A stored MISMATCH/REVIEW that no longer has any live difference was
            # decided by an older rule set; settle it so it leaves the queue.
            if row and not fields:
                from app.linkedin.verification import VERIFY_VERIFIED

                if (row.verification_status or "").upper() in {
                    "MISMATCH",
                    "REVIEW",
                    "NEEDS_REVIEW",
                }:
                    row.verification_status = VERIFY_VERIFIED
                    row.verification_reason = (
                        (row.verification_reason or "") + "; auto-cleared: values match"
                    ).strip("; ")
            enriched.append(
                {
                    **item,
                    "conflicts": fields,
                    "verification_status": getattr(row, "verification_status", None)
                    or item.get("verification_status"),
                }
            )
        db.commit()
        from app.linkedin.conflict_service import refresh_job_after_resolutions

        job = get_job_row(db, job_id)
        if job:
            refresh_job_after_resolutions(db, job)
            db.commit()
    finally:
        db.close()
    # Drop items whose location conflicts were auto-cleared.
    enriched = [row for row in enriched if row.get("conflicts")]
    return {
        "job_id": job_id,
        "total": len(enriched),
        "page": payload["page"],
        "page_size": payload["page_size"],
        "items": enriched,
    }


@router.get("/bulk-jobs/{job_id}/audit")
def get_bulk_job_audit(
    job_id: str,
    current_user: User = Depends(get_current_user),
):
    user_id = getattr(current_user, "id", None)
    _require_bulk_job(job_id, user_id)
    db = SessionLocal()
    try:
        entries = list_job_audit(db, job_id)
    finally:
        db.close()
    return {"job_id": job_id, "total": len(entries), "items": entries}


@router.post("/bulk-jobs/{job_id}/conflicts/{item_id}/resolve")
def resolve_bulk_conflict(
    job_id: str,
    item_id: int,
    body: ConflictResolveRequest,
    current_user: User = Depends(get_current_user),
):
    user_id = getattr(current_user, "id", None)
    _require_bulk_job(job_id, user_id)
    decisions = {
        d.field: {"resolution": d.resolution, "edited_value": getattr(d, "edited_value", None)}
        for d in body.decisions
    }
    if not decisions:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No decisions provided")

    db = SessionLocal()
    try:
        job = get_job_row(db, job_id)
        item = (
            db.query(BulkJobItemRow)
            .filter(BulkJobItemRow.id == item_id, BulkJobItemRow.job_id == job_id)
            .first()
        )
        if not job or not item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
        if not item_needs_review(item) and (item.verification_status or "").upper() != "RESOLVED":
            # allow re-resolve only for mismatch/review items; still allow if fields conflict
            if not conflicting_fields(item):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Item does not need conflict resolution",
                )
        try:
            resolve_item_fields(db, item, decisions=decisions, user_id=user_id, user=current_user)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        refresh_job_after_resolutions(db, job)

        icp_record_id = None
        icp_synced = False
        try:
            from app.icp.service import sync_icp_if_eligible

            icp_row = sync_icp_if_eligible(db, item, user_id=job.user_id or user_id)
            if icp_row is not None:
                icp_record_id = icp_row.id
                icp_synced = True
        except Exception as exc:
            logger.exception("ICP sync failed after resolve job_id=%s item_id=%s", job_id, item_id)
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Resolve succeeded locally but ICP Database sync failed: {exc}",
            ) from exc

        try:
            refresh_job_result_excel(db, job, excel_service=bulk_excel_service)
        except Exception:
            logger.exception("Excel refresh after conflict resolve failed job_id=%s", job_id)
        db.commit()
        return {
            "job_id": job_id,
            "item_id": item_id,
            "verification_status": item.verification_status,
            "needs_review": job.needs_review_count or 0,
            "resolved": job.resolved_count or 0,
            "phase": job.phase,
            "icp_synced": icp_synced,
            "icp_record_id": icp_record_id,
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.post("/bulk-jobs/{job_id}/conflicts/bulk-resolve")
def bulk_resolve_conflicts(
    job_id: str,
    body: ConflictBulkResolveRequest,
    current_user: User = Depends(get_current_user),
):
    if not body.confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bulk resolve requires confirm=true",
        )
    user_id = getattr(current_user, "id", None)
    _require_bulk_job(job_id, user_id)
    decisions = {
        d.field: {"resolution": d.resolution, "edited_value": getattr(d, "edited_value", None)}
        for d in body.decisions
    }
    if not decisions or not body.item_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nothing to resolve")

    db = SessionLocal()
    try:
        job = get_job_row(db, job_id)
        if not job:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        updated = 0
        for item_id in body.item_ids:
            item = (
                db.query(BulkJobItemRow)
                .filter(BulkJobItemRow.id == item_id, BulkJobItemRow.job_id == job_id)
                .first()
            )
            if not item or not item_needs_review(item):
                continue
            # only apply decisions for fields that actually conflict
            field_set = {c["field"] for c in conflicting_fields(item)}
            scoped = {k: v for k, v in decisions.items() if k in field_set}
            if not scoped:
                continue
            resolve_item_fields(db, item, decisions=scoped, user_id=user_id, user=current_user)
            try:
                from app.icp.service import sync_icp_if_eligible

                sync_icp_if_eligible(db, item, user_id=job.user_id or user_id)
            except Exception as exc:
                logger.exception("ICP sync failed during bulk-resolve item_id=%s", item_id)
                db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"ICP Database sync failed for item {item_id}: {exc}",
                ) from exc
            updated += 1
        refresh_job_after_resolutions(db, job)
        refresh_job_result_excel(db, job, excel_service=bulk_excel_service)
        db.commit()
        return {
            "job_id": job_id,
            "updated": updated,
            "needs_review": job.needs_review_count or 0,
            "resolved": job.resolved_count or 0,
            "phase": job.phase,
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.post("/bulk-jobs/{job_id}/backup", response_model=BackupCreateResponse)
def create_bulk_job_backup(
    job_id: str,
    current_user: User = Depends(get_current_user),
):
    user_id = getattr(current_user, "id", None)
    _require_bulk_job(job_id, user_id)
    try:
        row = create_job_backup(job_id, user_id=user_id)
    except BackupError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return BackupCreateResponse(
        backup_id=row.id,
        job_id=job_id,
        status=row.status,
        file_path=row.file_path,
    )


@router.get("/bulk-jobs/{job_id}/backup/download")
def download_bulk_job_backup(
    job_id: str,
    current_user: User = Depends(get_current_user),
):
    user_id = getattr(current_user, "id", None)
    job = _require_bulk_job(job_id, user_id)
    path = resolve_backup_path(getattr(job, "backup_file_path", None) or "")
    if path is None:
        db = SessionLocal()
        try:
            row = (
                db.query(BulkBackupRow)
                .filter(BulkBackupRow.job_id == job_id)
                .order_by(BulkBackupRow.id.desc())
                .first()
            )
            if row:
                path = resolve_backup_path(row.file_path)
        finally:
            db.close()
    if path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup not found")
    return FileResponse(
        path,
        media_type="application/zip",
        filename=path.name,
    )


@router.get("/bulk-backups", response_model=BackupListResponse)
def list_bulk_backups(
    current_user: User = Depends(get_current_user),
):
    user_id = getattr(current_user, "id", None)
    db = SessionLocal()
    try:
        q = db.query(BulkBackupRow)
        if user_id is not None:
            q = q.filter(BulkBackupRow.user_id == user_id)
        rows = q.order_by(BulkBackupRow.created_at.desc()).limit(200).all()
        items = []
        for row in rows:
            job = db.query(BulkExtractJobRow).filter(BulkExtractJobRow.id == row.job_id).first()
            items.append(
                BackupListItem(
                    id=row.id,
                    job_id=row.job_id,
                    backup_version=row.backup_version,
                    status=row.status,
                    file_path=row.file_path,
                    created_at=row.created_at.isoformat() if row.created_at else None,
                    original_file_name=job.original_file_name if job else None,
                )
            )
        return BackupListResponse(total=len(items), items=items)
    finally:
        db.close()


@router.get("/bulk-backups/{backup_id}/download")
def download_backup_by_id(
    backup_id: int,
    current_user: User = Depends(get_current_user),
):
    user_id = getattr(current_user, "id", None)
    db = SessionLocal()
    try:
        row = db.query(BulkBackupRow).filter(BulkBackupRow.id == backup_id).first()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup not found")
        if row.user_id is not None and user_id is not None and row.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup not found")
        path = resolve_backup_path(row.file_path)
        if path is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup file missing")
        return FileResponse(path, media_type="application/zip", filename=path.name)
    finally:
        db.close()


@router.post("/bulk-backups/restore", response_model=BackupRestoreResponse)
async def restore_bulk_backup(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    user_id = getattr(current_user, "id", None)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty backup file")
    try:
        job = restore_backup(content, user_id=user_id)
    except BackupError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return BackupRestoreResponse(
        job_id=job.id,
        status=job.status,
        total=job.total_urls or 0,
    )


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
    """Return a temporary (presigned) download URL for the verified Excel result."""
    from app.storage.exceptions import (
        FileNotFoundStorageError,
        S3StorageError,
        UnauthorizedFileAccess,
    )
    from app.storage.file_service import ensure_verified_download
    from app.storage.schemas import DownloadUrlResponse
    from app.linkedin.bulk_models import BulkExtractJobRow, BulkJobItemRow

    job = bulk_job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    user_id = getattr(current_user, "id", None)
    if job.user_id is not None and user_id is not None and job.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    if not job.excel_finalized or (job.completed + job.failed) <= 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Result Excel is not ready yet",
        )

    db = SessionLocal()
    try:
        job_row = db.query(BulkExtractJobRow).filter(BulkExtractJobRow.id == job_id).first()
        if job_row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

        def _generate() -> tuple[bytes, str]:
            items = (
                db.query(BulkJobItemRow)
                .filter(BulkJobItemRow.job_id == job_id)
                .order_by(BulkJobItemRow.source_row_number.asc())
                .all()
            )
            content, filename, relative = BulkExcelService().build_result_workbook_from_items(
                job_id=job_id,
                items=items,
                input_columns=list(job_row.input_columns or []),
            )
            job_row.result_file_path = relative
            job_row.excel_finalized = True
            return content, filename or f"bulk_{job_id}.xlsx"

        try:
            payload = ensure_verified_download(
                db,
                job=job_row,
                user_id=user_id,
                generate_bytes=_generate,
            )
        except UnauthorizedFileAccess:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found") from None
        except FileNotFoundStorageError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except S3StorageError as exc:
            logger.exception("S3 download URL failed job_id=%s", job_id)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=str(exc),
            ) from exc

        logger.info(
            "Bulk job Excel download URL user_id=%s job_id=%s reused=%s",
            user_id,
            job_id,
            payload.get("reused"),
        )
        return DownloadUrlResponse(**payload)
    finally:
        db.close()


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
