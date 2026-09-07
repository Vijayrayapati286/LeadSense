"""Push LinkedIn bulk Excel artifacts into S3 without duplicating binaries in Postgres."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.storage.exceptions import S3StorageError
from app.storage.file_service import batch_content_version, store_original_upload, store_verified_result

logger = logging.getLogger(__name__)


def persist_original_upload(
    db: Session,
    *,
    user_id: int | None,
    batch_id: str,
    filename: str,
    content: bytes,
    content_type: str | None = None,
) -> None:
    try:
        store_original_upload(
            db,
            user_id=user_id,
            batch_id=batch_id,
            filename=filename,
            content=content,
            content_type=content_type,
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to store original upload in S3 batch_id=%s", batch_id)
        raise


def persist_verified_excel(
    db: Session,
    *,
    job,
    content: bytes,
    filename: str,
) -> None:
    """Upload verified result; never overwrites/deletes ORIGINAL_UPLOAD."""
    if not content:
        return
    try:
        store_verified_result(
            db,
            user_id=getattr(job, "user_id", None),
            batch_id=job.id,
            content=content,
            filename=filename or "verified.xlsx",
            content_version=batch_content_version(job),
        )
        db.flush()
    except S3StorageError:
        logger.exception("Verified Excel S3 upload failed batch_id=%s", getattr(job, "id", None))
        # Keep local excel path usable; download endpoint can regenerate.
    except Exception:
        logger.exception("Verified Excel metadata save failed batch_id=%s", getattr(job, "id", None))
