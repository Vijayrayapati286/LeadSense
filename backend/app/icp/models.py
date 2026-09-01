"""ORM model for the ICP Database."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.database.connection import Base

ICP_STATUS_VERIFIED = "verified"
ICP_STATUS_ACTIVE = "active"
SOURCE_LINKEDIN_BULK = "linkedin_bulk"
SOURCE_MANUAL = "manual"


class IcpRecordRow(Base):
    __tablename__ = "icp_records"
    __table_args__ = (
        UniqueConstraint("user_id", "linkedin_url", name="uq_icp_user_linkedin_url"),
        Index("ix_icp_user_verified_at", "user_id", "verified_at"),
        Index("ix_icp_user_industry", "user_id", "industry"),
        Index("ix_icp_user_dedupe", "user_id", "dedupe_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    designation: Mapped[str | None] = mapped_column(String(500), nullable=True)
    about: Mapped[str | None] = mapped_column(Text, nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)
    industry: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company_size: Mapped[str | None] = mapped_column(String(100), nullable=True)
    location: Mapped[str | None] = mapped_column(String(500), nullable=True)
    company_website: Mapped[str | None] = mapped_column(String(500), nullable=True)

    embedding: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(100), nullable=True)

    icp_status: Mapped[str] = mapped_column(String(50), nullable=False, default=ICP_STATUS_VERIFIED)
    icp_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tags: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)

    verification_status: Mapped[str] = mapped_column(String(32), nullable=False, default="VERIFIED")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    source: Mapped[str] = mapped_column(String(64), nullable=False, default=SOURCE_LINKEDIN_BULK)
    source_record_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    source_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
