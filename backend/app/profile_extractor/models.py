"""PostgreSQL / SQLite models for LeadSense Profile Extractor (isolated)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.connection import Base


class ProfileExtractJob(Base):
    __tablename__ = "profile_extract_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    profile_url: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued", index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    excel_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    profile: Mapped["ProfileExtractResult | None"] = relationship(
        "ProfileExtractResult",
        back_populates="job",
        uselist=False,
        cascade="all, delete-orphan",
    )


class ProfileExtractResult(Base):
    __tablename__ = "profile_extract_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("profile_extract_jobs.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    designation: Mapped[str | None] = mapped_column(String(500), nullable=True)
    about: Mapped[str | None] = mapped_column(Text, nullable=True)

    job: Mapped["ProfileExtractJob"] = relationship("ProfileExtractJob", back_populates="profile")


class ProfileExtractCache(Base):
    __tablename__ = "profile_extract_cache"
    __table_args__ = (UniqueConstraint("url_hash", name="uq_profile_extract_cache_url_hash"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    profile_url: Mapped[str] = mapped_column(String(500), nullable=False)
    result_json: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
