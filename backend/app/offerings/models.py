"""ORM models for Offerings and ICP matching."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.database.connection import Base

OFFERING_STATUS_ACTIVE = "active"
OFFERING_STATUS_ARCHIVED = "archived"
OFFERING_STATUS_DRAFT = "draft"

MATCH_STATUS_NEW = "new"
MATCH_STATUS_AI_MATCHED = "ai_matched"
MATCH_STATUS_NEEDS_REVIEW = "needs_review"
MATCH_STATUS_APPROVED = "approved"
MATCH_STATUS_REJECTED = "rejected"

MATCH_TIER_STRONG = "strong"
MATCH_TIER_GOOD = "good"
MATCH_TIER_POTENTIAL = "potential"
MATCH_TIER_POOR = "poor"

JOB_PENDING = "pending"
JOB_RUNNING = "running"
JOB_DONE = "done"
JOB_FAILED = "failed"

ITEM_QUEUED = "QUEUED"
ITEM_PROCESSING = "PROCESSING"
ITEM_SUCCESS = "SUCCESS"
ITEM_FINAL_FAILED = "FINAL_FAILED"
ITEM_SKIPPED = "SKIPPED"

STRONG_THRESHOLD = 80
GOOD_THRESHOLD = 65
POTENTIAL_THRESHOLD = 50  # Possible Match lower bound; below = do not recommend by default

# Feedback actions
FEEDBACK_VIEWED = "viewed"
FEEDBACK_ACCEPTED = "accepted"
FEEDBACK_REJECTED = "rejected"
FEEDBACK_RECOMMENDED = "recommended"
FEEDBACK_CONVERTED = "converted"

DEFAULT_HARD_FILTER_RULES = {
    "require_industry_overlap": True,
    "require_geography_overlap": False,
    "require_company_size_overlap": False,
    "require_role_overlap": False,
    "min_role_token_overlap": 0.4,
}

# Historical performance is neutral until feedback exists
HISTORICAL_NEUTRAL_SCORE = 70

# Spec weights (components are 0–100, then weighted)
SCORE_WEIGHTS_V2 = {
    "icp_fit": 0.25,
    "problem_fit": 0.20,
    "role_fit": 0.15,
    "industry_fit": 0.15,
    "company_fit": 0.10,
    "buying_signal": 0.10,
    "historical": 0.05,
}


class OfferingRow(Base):
    __tablename__ = "offerings"
    __table_args__ = (
        Index("ix_offerings_user_status", "user_id", "status"),
        Index("ix_offerings_user_updated", "user_id", "updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    short_description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    website_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    target_industries: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    company_size_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    company_size_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    company_size_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    revenue_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    revenue_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_geographies: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    business_models: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    target_departments: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)

    target_job_titles: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    target_seniority: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    decision_maker_types: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    buying_roles: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    buyer_personas: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)

    pain_points: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    business_problems: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    current_challenges: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)

    use_cases: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    desired_outcomes: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    benefits: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)

    must_have_rules: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    nice_to_have_rules: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    exclusion_rules: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)

    positive_keywords: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    negative_keywords: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)

    pricing_range: Mapped[str | None] = mapped_column(String(100), nullable=True)
    hard_filter_rules: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    embedding: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    profile_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    vouchers: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    email_template: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default=OFFERING_STATUS_ACTIVE)
    definition_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    definition_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OfferingMatchRow(Base):
    __tablename__ = "offering_matches"
    __table_args__ = (
        UniqueConstraint("offering_id", "icp_record_id", name="uq_offering_icp_match"),
        Index("ix_offering_matches_offering_score", "offering_id", "fit_score"),
        Index("ix_offering_matches_offering_status", "offering_id", "status"),
        Index("ix_offering_matches_offering_tier", "offering_id", "match_tier"),
        Index("ix_offering_matches_icp", "icp_record_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    offering_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("offerings.id", ondelete="CASCADE"), nullable=False
    )
    icp_record_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("icp_records.id", ondelete="CASCADE"), nullable=False
    )

    fit_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    industry_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    job_title_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    department_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    company_size_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pain_use_case_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    seniority_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    buying_signal_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Spec component scores (0–100 each)
    icp_fit_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    problem_fit_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    role_fit_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    company_fit_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    historical_score: Mapped[int] = mapped_column(Integer, nullable=False, default=70)
    semantic_similarity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    missing_information: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)

    match_tier: Mapped[str] = mapped_column(String(32), nullable=False, default=MATCH_TIER_POOR)
    match_reasons: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    ai_analysis: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default=MATCH_STATUS_AI_MATCHED)
    offering_definition_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    reviewed_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OfferingMatchJobRow(Base):
    __tablename__ = "offering_match_jobs"
    __table_args__ = (
        Index("ix_offering_match_jobs_offering", "offering_id"),
        Index("ix_offering_match_jobs_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    offering_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("offerings.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default=JOB_PENDING)
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    strong_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    potential_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    poor_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    definition_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OfferingMatchJobItemRow(Base):
    __tablename__ = "offering_match_job_items"
    __table_args__ = (
        UniqueConstraint("job_id", "icp_record_id", name="uq_match_job_icp"),
        Index("ix_match_job_items_job_status", "job_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("offering_match_jobs.id", ondelete="CASCADE"), nullable=False
    )
    icp_record_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("icp_records.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=ITEM_QUEUED)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OfferingRecommendationFeedbackRow(Base):
    __tablename__ = "offering_recommendation_feedback"
    __table_args__ = (
        Index("ix_offering_feedback_offering", "offering_id"),
        Index("ix_offering_feedback_icp", "icp_record_id"),
        Index("ix_offering_feedback_action", "action"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recommendation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("offering_matches.id", ondelete="CASCADE"), nullable=False
    )
    offering_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("offerings.id", ondelete="CASCADE"), nullable=False
    )
    icp_record_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("icp_records.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    score_at_action: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
