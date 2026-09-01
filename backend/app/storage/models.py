"""PostgreSQL metadata for files stored in S3 (binaries never live in the DB)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.connection import Base

FILE_ORIGINAL_UPLOAD = "ORIGINAL_UPLOAD"
FILE_VERIFIED_RESULT = "VERIFIED_RESULT"
FILE_FINAL_EXPORT = "FINAL_EXPORT"

STATUS_UPLOADING = "uploading"
STATUS_UPLOADED = "uploaded"
STATUS_READY = "ready"
STATUS_FAILED = "failed"
STATUS_ORPHANED = "orphaned"


class StoredFileRow(Base):
    __tablename__ = "stored_files"
    __table_args__ = (
        Index("ix_stored_files_batch_type", "batch_id", "file_type"),
        Index("ix_stored_files_user_batch", "user_id", "batch_id"),
        Index("ix_stored_files_s3_key", "s3_key", unique=False),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    batch_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    file_type: Mapped[str] = mapped_column(String(32), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    s3_bucket: Mapped[str] = mapped_column(String(255), nullable=False)
    s3_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(200), nullable=True)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=STATUS_UPLOADED)
    # When set, download reuses this object if version still matches current batch state.
    content_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
