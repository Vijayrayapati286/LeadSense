"""Generic file upload / metadata / download APIs (S3-backed)."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.middleware.auth import get_current_user
from app.models import User
from app.storage.exceptions import (
    FileNotFoundStorageError,
    FileValidationError,
    S3StorageError,
    UnauthorizedFileAccess,
)
from app.storage.file_service import (
    build_download_payload,
    get_file_for_user,
    list_batch_files,
    store_offering_voucher_upload,
    store_original_upload,
)
from app.storage.models import (
    FILE_FINAL_EXPORT,
    FILE_VERIFIED_RESULT,
    STATUS_READY,
    STATUS_UPLOADED,
    StoredFileRow,
)
from app.storage.s3_service import get_s3_service
from app.storage.schemas import (
    BatchFilesResponse,
    DownloadUrlResponse,
    FileUploadResponse,
    StoredFileOut,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/files", tags=["files"])


def _http_from_storage(exc: Exception) -> HTTPException:
    if isinstance(exc, FileValidationError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, UnauthorizedFileAccess):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    if isinstance(exc, FileNotFoundStorageError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, S3StorageError):
        return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Storage error")


def _stored_out(f: dict | StoredFileRow) -> StoredFileOut:
    if isinstance(f, StoredFileRow):
        return StoredFileOut(
            id=f.id,
            user_id=f.user_id,
            batch_id=f.batch_id,
            type=f.file_type,
            filename=f.original_filename,
            mime_type=f.mime_type,
            file_size=int(f.file_size or 0),
            status=f.status,
            content_version=f.content_version,
            created_at=f.created_at,
            updated_at=f.updated_at,
        )
    return StoredFileOut(
        id=f["id"],
        user_id=f.get("user_id"),
        batch_id=f["batch_id"],
        type=f["type"],
        filename=f["filename"],
        mime_type=f.get("mime_type"),
        file_size=f.get("file_size") or 0,
        status=f["status"],
        content_version=f.get("content_version"),
        created_at=f.get("created_at"),
        updated_at=f.get("updated_at"),
    )


@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    batch_id: str | None = None,
    purpose: str | None = Query(None, description="Set to offering_voucher for PDF/PPT/Excel collateral"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload an original file to S3 and store metadata only in PostgreSQL."""
    user_id = getattr(current_user, "id", None)
    filename = file.filename or "upload.xlsx"
    content = await file.read()
    bid = (batch_id or "").strip() or str(uuid.uuid4())
    upload_fn = store_offering_voucher_upload if purpose == "offering_voucher" else store_original_upload
    try:
        row = upload_fn(
            db,
            user_id=user_id,
            batch_id=bid,
            filename=filename,
            content=content,
            content_type=file.content_type,
        )
        db.commit()
        db.refresh(row)
    except (FileValidationError, S3StorageError) as exc:
        db.rollback()
        raise _http_from_storage(exc) from exc
    except Exception as exc:
        db.rollback()
        logger.exception("Upload failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Upload failed",
        ) from exc

    return FileUploadResponse(
        file_id=row.id,
        batch_id=row.batch_id,
        filename=row.original_filename,
        file_type=row.file_type,
        status=row.status,
        s3_key=row.s3_key,
        file_size=int(row.file_size or 0),
    )


@router.get("/{file_id}", response_model=StoredFileOut)
def get_file_metadata(
    file_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        row = get_file_for_user(db, file_id=file_id, user_id=getattr(current_user, "id", None))
    except (FileNotFoundStorageError, UnauthorizedFileAccess) as exc:
        raise _http_from_storage(exc) from exc
    return _stored_out(row)


@router.get("/{file_id}/content")
def download_file_content(
    file_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Authenticated stream for mock-S3 (and fallback) downloads."""
    try:
        row = get_file_for_user(db, file_id=file_id, user_id=getattr(current_user, "id", None))
        data = get_s3_service().download_bytes(key=row.s3_key)
    except (FileNotFoundStorageError, UnauthorizedFileAccess, S3StorageError) as exc:
        raise _http_from_storage(exc) from exc
    return Response(
        content=data,
        media_type=row.mime_type
        or "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{row.original_filename}"',
        },
    )


@router.get("/{file_id}/download-url", response_model=DownloadUrlResponse)
def get_file_download_url(
    file_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        row = get_file_for_user(db, file_id=file_id, user_id=getattr(current_user, "id", None))
        if not get_s3_service().file_exists(key=row.s3_key):
            raise FileNotFoundStorageError("File not found in S3")
        payload = build_download_payload(db, row=row, reused=True)
    except (FileNotFoundStorageError, UnauthorizedFileAccess, S3StorageError) as exc:
        raise _http_from_storage(exc) from exc
    return DownloadUrlResponse(**payload)


batches_router = APIRouter(prefix="/batches", tags=["batches"])


@batches_router.get("/{batch_id}/files", response_model=BatchFilesResponse)
def get_batch_files(
    batch_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        files = list_batch_files(db, batch_id=batch_id, user_id=getattr(current_user, "id", None))
    except UnauthorizedFileAccess as exc:
        raise _http_from_storage(exc) from exc
    return BatchFilesResponse(batch_id=batch_id, files=[_stored_out(f) for f in files])


@batches_router.get("/{batch_id}/download", response_model=DownloadUrlResponse)
def download_batch_verified(
    batch_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Presigned download for a batch verified/final file (LinkedIn bulk or generic)."""
    from app.linkedin.bulk_excel_service import BulkExcelService
    from app.linkedin.bulk_models import BulkExtractJobRow, BulkJobItemRow
    from app.storage.file_service import ensure_verified_download

    user_id = getattr(current_user, "id", None)
    job_row = db.query(BulkExtractJobRow).filter(BulkExtractJobRow.id == batch_id).first()

    if job_row is not None:
        if job_row.user_id is not None and user_id is not None and job_row.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found")
        done = (job_row.success_count or 0) + (job_row.failed_count or 0)
        if not job_row.excel_finalized or done <= 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Result Excel is not ready yet",
            )

        def _generate() -> tuple[bytes, str]:
            items = (
                db.query(BulkJobItemRow)
                .filter(BulkJobItemRow.job_id == batch_id)
                .order_by(BulkJobItemRow.source_row_number.asc())
                .all()
            )
            content, filename, relative = BulkExcelService().build_result_workbook_from_items(
                job_id=batch_id,
                items=items,
                input_columns=list(job_row.input_columns or []),
            )
            job_row.result_file_path = relative
            job_row.excel_finalized = True
            return content, filename or f"bulk_{batch_id}.xlsx"

        try:
            payload = ensure_verified_download(
                db,
                job=job_row,
                user_id=user_id,
                generate_bytes=_generate,
            )
            return DownloadUrlResponse(**payload)
        except (FileNotFoundStorageError, UnauthorizedFileAccess, S3StorageError) as exc:
            raise _http_from_storage(exc) from exc

    row = (
        db.query(StoredFileRow)
        .filter(
            StoredFileRow.batch_id == batch_id,
            StoredFileRow.file_type.in_([FILE_VERIFIED_RESULT, FILE_FINAL_EXPORT]),
            StoredFileRow.status.in_([STATUS_READY, STATUS_UPLOADED]),
        )
        .order_by(StoredFileRow.id.desc())
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Verified file not ready")
    if row.user_id is not None and user_id is not None and int(row.user_id) != int(user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found")
    try:
        if not get_s3_service().file_exists(key=row.s3_key):
            raise FileNotFoundStorageError("File not found in S3")
        return DownloadUrlResponse(**build_download_payload(db, row=row, reused=True))
    except (FileNotFoundStorageError, S3StorageError) as exc:
        raise _http_from_storage(exc) from exc
