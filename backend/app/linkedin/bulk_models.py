"""PostgreSQL / SQLite models for bulk LinkedIn URL extraction jobs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.database.connection import Base

ITEM_PENDING = "PENDING"
ITEM_QUEUED = "QUEUED"
ITEM_PROCESSING = "PROCESSING"
ITEM_RETRY_WAIT = "RETRY_WAIT"
ITEM_SUCCESS = "SUCCESS"
ITEM_FINAL_FAILED = "FINAL_FAILED"

TERMINAL_ITEM_STATUSES = (ITEM_SUCCESS, ITEM_FINAL_FAILED)
CLAIMABLE_ITEM_STATUSES = (ITEM_PENDING, ITEM_QUEUED)
JOB_PENDING = "pending"
JOB_RUNNING = "running"
JOB_DONE = "done"
JOB_FAILED = "failed"

PHASE_UPLOADING = "uploading"
PHASE_EXTRACTING = "extracting"
PHASE_COMPARING = "comparing"
PHASE_COMPLETED = "completed"


class BulkExtractJobRow(Base):
    __tablename__ = "linkedin_bulk_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    original_file_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    input_columns: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    total_urls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retrying_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    verified_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mismatch_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    review_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    phase: Mapped[str] = mapped_column(String(32), nullable=False, default=PHASE_UPLOADING)
    excel_finalized: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=JOB_PENDING, index=True)
    result_file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    items: Mapped[list["BulkJobItemRow"]] = relationship(
        "BulkJobItemRow",
        back_populates="job",
        cascade="all, delete-orphan",
    )


class BulkJobItemRow(Base):
    __tablename__ = "linkedin_bulk_job_items"
    __table_args__ = (
        Index("ix_bulk_items_job_status", "job_id", "status"),
        Index("ix_bulk_items_retry_after", "status", "retry_after"),
        Index("ix_bulk_items_job_row", "job_id", "source_row_number", unique=True),
        Index("ix_bulk_items_job_verify", "job_id", "verification_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("linkedin_bulk_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    profile_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    normalized_url: Mapped[str] = mapped_column(String(500), nullable=False, default="", index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=ITEM_QUEUED, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dedupe_of_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("linkedin_bulk_job_items.id"), nullable=True, index=True
    )
    source_row_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    company: Mapped[str | None] = mapped_column(String(500), nullable=True)
    designation: Mapped[str | None] = mapped_column(String(500), nullable=True)
    about: Mapped[str | None] = mapped_column(Text, nullable=True)
    headline: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    location: Mapped[str | None] = mapped_column(String(500), nullable=True)
    followers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    connections: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extraction_response: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="NOT_VERIFIED"
    )
    verification_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    name_match: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    designation_match: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    company_match: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    location_match: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    verification_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    job: Mapped["BulkExtractJobRow"] = relationship("BulkExtractJobRow", back_populates="items")
    attempts: Mapped[list["ExtractionAttemptRow"]] = relationship(
        "ExtractionAttemptRow",
        back_populates="job_item",
        cascade="all, delete-orphan",
    )


class ExtractionAttemptRow(Base):
    __tablename__ = "linkedin_extraction_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_item_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("linkedin_bulk_job_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    request_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    request_finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="FAILED")
    response: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    apify_run_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    job_item: Mapped["BulkJobItemRow"] = relationship("BulkJobItemRow", back_populates="attempts")
