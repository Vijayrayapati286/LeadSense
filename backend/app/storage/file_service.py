"""Business logic: validate uploads, persist S3 metadata, reuse verified downloads."""

from __future__ import annotations

import hashlib
import logging
import mimetypes
import uuid
from collections.abc import Callable
from pathlib import PurePosixPath

from sqlalchemy.orm import Session

from app.config import get_settings
from app.storage.exceptions import (
    FileNotFoundStorageError,
    FileValidationError,
    S3StorageError,
    UnauthorizedFileAccess,
)
from app.storage.keys import (
    build_export_key,
    build_upload_key,
    build_verified_key,
    sanitize_filename,
)
from app.storage.models import (
    FILE_FINAL_EXPORT,
    FILE_OFFERING_VOUCHER,
    FILE_ORIGINAL_UPLOAD,
    FILE_VERIFIED_RESULT,
    STATUS_FAILED,
    STATUS_ORPHANED,
    STATUS_READY,
    STATUS_UPLOADED,
    StoredFileRow,
)
from app.storage.s3_service import get_s3_service

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".xlsx", ".xls", ".xlsm", ".csv", ".ods"}
VOUCHER_EXTENSIONS = {
    ".pdf",
    ".ppt",
    ".pptx",
    ".xlsx",
    ".xls",
    ".xlsm",
    ".csv",
    ".ods",
    ".doc",
    ".docx",
}
ALLOWED_MIME_PREFIXES = (
    "application/vnd.openxmlformats",
    "application/vnd.ms-excel",
    "application/vnd.oasis",
    "text/csv",
    "application/csv",
    "application/octet-stream",
)
VOUCHER_MIME_PREFIXES = ALLOWED_MIME_PREFIXES + (
    "application/pdf",
    "application/msword",
    "application/vnd.ms-powerpoint",
)


def validate_upload(
    *,
    filename: str,
    content: bytes,
    content_type: str | None = None,
) -> tuple[str, str]:
    settings = get_settings()
    max_bytes = int(getattr(settings, "max_upload_file_bytes", 25 * 1024 * 1024) or 25 * 1024 * 1024)
    if not content:
        raise FileValidationError("Uploaded file is empty")
    if len(content) > max_bytes:
        raise FileValidationError(f"File exceeds maximum size of {max_bytes} bytes")

    safe_name = sanitize_filename(filename, default="upload.xlsx")
    ext = PurePosixPath(safe_name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise FileValidationError(
            f"Invalid file type '{ext or 'unknown'}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    mime = (content_type or "").split(";")[0].strip().lower()
    if mime and not any(mime.startswith(p) for p in ALLOWED_MIME_PREFIXES):
        # Extension already validated; only reject clearly wrong types (e.g. image/*).
        if mime.startswith(("image/", "audio/", "video/", "text/html")):
            raise FileValidationError(f"Unsupported content type: {mime}")
    if not mime:
        mime = mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
    return safe_name, mime


def validate_offering_voucher_upload(
    *,
    filename: str,
    content: bytes,
    content_type: str | None = None,
) -> tuple[str, str]:
    settings = get_settings()
    max_bytes = int(getattr(settings, "max_upload_file_bytes", 25 * 1024 * 1024) or 25 * 1024 * 1024)
    if not content:
        raise FileValidationError("Uploaded file is empty")
    if len(content) > max_bytes:
        raise FileValidationError(f"File exceeds maximum size of {max_bytes} bytes")

    safe_name = sanitize_filename(filename, default="voucher.pdf")
    ext = PurePosixPath(safe_name).suffix.lower()
    if ext not in VOUCHER_EXTENSIONS:
        raise FileValidationError(
            f"Invalid file type '{ext or 'unknown'}'. Allowed: {', '.join(sorted(VOUCHER_EXTENSIONS))}"
        )

    mime = (content_type or "").split(";")[0].strip().lower()
    if mime and not any(mime.startswith(p) for p in VOUCHER_MIME_PREFIXES):
        if mime.startswith(("image/", "audio/", "video/", "text/html")):
            raise FileValidationError(f"Unsupported content type: {mime}")
    if not mime:
        mime = mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
    return safe_name, mime


def batch_content_version(job) -> str:
    """Fingerprint of verified/export-relevant job state for download reuse."""
    parts = [
        str(getattr(job, "id", "")),
        str(getattr(job, "resolved_count", 0) or 0),
        str(getattr(job, "verified_count", 0) or 0),
        str(getattr(job, "mismatch_count", 0) or 0),
        str(getattr(job, "needs_review_count", 0) or 0),
        str(getattr(job, "success_count", 0) or 0),
        str(getattr(job, "failed_count", 0) or 0),
        str(getattr(job, "processed_count", 0) or 0),
        str(getattr(job, "phase", "") or ""),
        str(getattr(job, "excel_finalized", False)),
    ]
    updated = getattr(job, "updated_at", None)
    if updated is not None:
        parts.append(updated.isoformat())
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def assert_batch_owner(*, job, user_id: int | None) -> None:
    if job is None:
        raise FileNotFoundStorageError("Batch not found")
    job_uid = getattr(job, "user_id", None)
    if job_uid is not None and user_id is not None and int(job_uid) != int(user_id):
        raise UnauthorizedFileAccess("Not allowed to access this batch")


def _row_to_public(row: StoredFileRow) -> dict:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "batch_id": row.batch_id,
        "type": row.file_type,
        "filename": row.original_filename,
        "s3_bucket": row.s3_bucket,
        "s3_key": row.s3_key,
        "mime_type": row.mime_type,
        "file_size": int(row.file_size or 0),
        "status": row.status,
        "content_version": row.content_version,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def store_bytes(
    db: Session,
    *,
    user_id: int | None,
    batch_id: str,
    file_type: str,
    filename: str,
    content: bytes,
    mime_type: str | None = None,
    content_version: str | None = None,
    s3_key: str | None = None,
    replace_existing: bool = False,
) -> StoredFileRow:
    """Upload bytes to S3 and persist metadata. Rolls orphan status on DB failure."""
    settings = get_settings()
    s3 = get_s3_service()
    safe_name = sanitize_filename(filename)
    mime = mime_type or mimetypes.guess_type(safe_name)[0] or "application/octet-stream"

    if file_type == FILE_ORIGINAL_UPLOAD:
        key = s3_key or build_upload_key(user_id=user_id or 0, batch_id=batch_id, filename=safe_name)
    elif file_type == FILE_VERIFIED_RESULT:
        key = s3_key or build_verified_key(
            user_id=user_id or 0,
            batch_id=batch_id,
            filename=safe_name if safe_name.endswith(".xlsx") else "verified.xlsx",
        )
    elif file_type == FILE_FINAL_EXPORT:
        key = s3_key or build_export_key(user_id=user_id or 0, batch_id=batch_id, filename=safe_name)
    else:
        key = s3_key or build_export_key(user_id=user_id or 0, batch_id=batch_id, filename=safe_name)

    existing: StoredFileRow | None = None
    if replace_existing:
        existing = (
            db.query(StoredFileRow)
            .filter(
                StoredFileRow.batch_id == batch_id,
                StoredFileRow.file_type == file_type,
                StoredFileRow.status.in_([STATUS_UPLOADED, STATUS_READY]),
            )
            .order_by(StoredFileRow.id.desc())
            .first()
        )
        if existing and existing.content_version == content_version and s3.file_exists(key=existing.s3_key):
            return existing
        if existing:
            key = existing.s3_key

    try:
        bucket = s3.upload_bytes(
            key=key,
            data=content,
            content_type=mime,
            metadata={"batch_id": str(batch_id), "file_type": file_type},
        )
    except S3StorageError:
        logger.exception("S3 upload failed batch_id=%s type=%s", batch_id, file_type)
        raise

    try:
        if existing:
            existing.original_filename = safe_name
            existing.s3_bucket = bucket
            existing.s3_key = key
            existing.mime_type = mime
            existing.file_size = len(content)
            existing.status = STATUS_READY if file_type != FILE_ORIGINAL_UPLOAD else STATUS_UPLOADED
            existing.content_version = content_version
            existing.error = None
            db.add(existing)
            db.flush()
            return existing

        row = StoredFileRow(
            user_id=user_id,
            batch_id=batch_id,
            file_type=file_type,
            original_filename=safe_name,
            s3_bucket=bucket,
            s3_key=key,
            mime_type=mime,
            file_size=len(content),
            status=STATUS_READY if file_type != FILE_ORIGINAL_UPLOAD else STATUS_UPLOADED,
            content_version=content_version,
        )
        db.add(row)
        db.flush()
        return row
    except Exception as exc:
        logger.error(
            "DB save failed after S3 upload — orphaned object bucket=%s key=%s err=%s",
            bucket,
            key,
            exc,
        )
        try:
            orphan = StoredFileRow(
                user_id=user_id,
                batch_id=batch_id,
                file_type=file_type,
                original_filename=safe_name,
                s3_bucket=bucket,
                s3_key=key,
                mime_type=mime,
                file_size=len(content),
                status=STATUS_ORPHANED,
                content_version=content_version,
                error=str(exc)[:500],
            )
            db.rollback()
            db.add(orphan)
            db.commit()
        except Exception:
            logger.exception("Could not record orphaned S3 object key=%s", key)
        raise S3StorageError("Failed to save file metadata after S3 upload") from exc


def store_original_upload(
    db: Session,
    *,
    user_id: int | None,
    batch_id: str,
    filename: str,
    content: bytes,
    content_type: str | None = None,
) -> StoredFileRow:
    safe_name, mime = validate_upload(filename=filename, content=content, content_type=content_type)
    return store_bytes(
        db,
        user_id=user_id,
        batch_id=batch_id,
        file_type=FILE_ORIGINAL_UPLOAD,
        filename=safe_name,
        content=content,
        mime_type=mime,
    )


def store_offering_voucher_upload(
    db: Session,
    *,
    user_id: int | None,
    batch_id: str,
    filename: str,
    content: bytes,
    content_type: str | None = None,
) -> StoredFileRow:
    safe_name, mime = validate_offering_voucher_upload(
        filename=filename, content=content, content_type=content_type
    )
    return store_bytes(
        db,
        user_id=user_id,
        batch_id=batch_id,
        file_type=FILE_OFFERING_VOUCHER,
        filename=safe_name,
        content=content,
        mime_type=mime,
    )


def store_verified_result(
    db: Session,
    *,
    user_id: int | None,
    batch_id: str,
    content: bytes,
    filename: str = "verified.xlsx",
    content_version: str | None = None,
) -> StoredFileRow:
    return store_bytes(
        db,
        user_id=user_id,
        batch_id=batch_id,
        file_type=FILE_VERIFIED_RESULT,
        filename=filename,
        content=content,
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        content_version=content_version,
        replace_existing=True,
    )


def get_file_for_user(db: Session, *, file_id: int, user_id: int | None) -> StoredFileRow:
    row = db.query(StoredFileRow).filter(StoredFileRow.id == file_id).first()
    if not row:
        raise FileNotFoundStorageError("File not found")
    if row.user_id is not None and user_id is not None and int(row.user_id) != int(user_id):
        raise UnauthorizedFileAccess("Not allowed to access this file")
    return row


def list_batch_files(db: Session, *, batch_id: str, user_id: int | None) -> list[dict]:
    q = db.query(StoredFileRow).filter(StoredFileRow.batch_id == batch_id)
    rows = q.order_by(StoredFileRow.id.asc()).all()
    if not rows:
        return []
    # Ownership: if any row has user_id, enforce match
    for row in rows:
        if row.user_id is not None and user_id is not None and int(row.user_id) != int(user_id):
            raise UnauthorizedFileAccess("Not allowed to access this batch")
    return [_row_to_public(r) for r in rows if r.status != STATUS_ORPHANED]


def find_reusable_verified(
    db: Session,
    *,
    batch_id: str,
    content_version: str,
) -> StoredFileRow | None:
    row = (
        db.query(StoredFileRow)
        .filter(
            StoredFileRow.batch_id == batch_id,
            StoredFileRow.file_type == FILE_VERIFIED_RESULT,
            StoredFileRow.status.in_([STATUS_READY, STATUS_UPLOADED]),
            StoredFileRow.content_version == content_version,
        )
        .order_by(StoredFileRow.id.desc())
        .first()
    )
    if not row:
        return None
    s3 = get_s3_service()
    if not s3.file_exists(key=row.s3_key):
        logger.warning("Verified file missing in S3 batch_id=%s key=%s", batch_id, row.s3_key)
        row.status = STATUS_FAILED
        row.error = "Missing S3 object"
        db.add(row)
        db.flush()
        return None
    return row


def build_download_payload(
    db: Session,
    *,
    row: StoredFileRow,
    expires_in: int | None = None,
    reused: bool = False,
    backend_url: str | None = None,
) -> dict:
    settings = get_settings()
    s3 = get_s3_service()
    expires = expires_in or int(getattr(settings, "s3_presign_expires_seconds", 3600) or 3600)
    base = (backend_url or settings.backend_url or "http://localhost:8000").rstrip("/")
    mock_url = f"{base}/api/files/{row.id}/content"
    url = s3.generate_presigned_download_url(
        key=row.s3_key,
        expires_in=expires,
        filename=row.original_filename,
        mock_content_url=mock_url,
    )
    return {
        "download_url": url,
        "filename": row.original_filename,
        "file_id": row.id,
        "expires_in": expires,
        "reused": reused,
    }


def ensure_verified_download(
    db: Session,
    *,
    job,
    user_id: int | None,
    generate_bytes: Callable[[], tuple[bytes, str]],
) -> dict:
    """
    Return a download URL for the verified result.
    Reuses an existing S3 object when content_version still matches.
    """
    assert_batch_owner(job=job, user_id=user_id)
    version = batch_content_version(job)
    existing = find_reusable_verified(db, batch_id=job.id, content_version=version)
    if existing:
        logger.info("Reusing verified S3 file batch_id=%s file_id=%s", job.id, existing.id)
        return build_download_payload(db, row=existing, reused=True)

    content, filename = generate_bytes()
    if not content:
        raise FileNotFoundStorageError("Verified result could not be generated")
    row = store_verified_result(
        db,
        user_id=user_id if user_id is not None else getattr(job, "user_id", None),
        batch_id=job.id,
        content=content,
        filename=filename or "verified.xlsx",
        content_version=version,
    )
    db.commit()
    db.refresh(row)
    return build_download_payload(db, row=row, reused=False)


def new_batch_id() -> str:
    return str(uuid.uuid4())
