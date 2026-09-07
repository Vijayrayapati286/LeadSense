"""Create offerings, offering_matches, and offering_match_jobs tables.

Revision ID: 016
Revises: 015
Create Date: 2026-08-26 12:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "offerings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("short_description", sa.String(length=500), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("product_type", sa.String(length=100), nullable=True),
        sa.Column("website_url", sa.String(length=500), nullable=True),
        sa.Column("target_industries", sa.JSON(), nullable=True),
        sa.Column("company_size_min", sa.Integer(), nullable=True),
        sa.Column("company_size_max", sa.Integer(), nullable=True),
        sa.Column("company_size_label", sa.String(length=100), nullable=True),
        sa.Column("revenue_min", sa.Integer(), nullable=True),
        sa.Column("revenue_max", sa.Integer(), nullable=True),
        sa.Column("target_geographies", sa.JSON(), nullable=True),
        sa.Column("business_models", sa.JSON(), nullable=True),
        sa.Column("target_departments", sa.JSON(), nullable=True),
        sa.Column("target_job_titles", sa.JSON(), nullable=True),
        sa.Column("target_seniority", sa.JSON(), nullable=True),
        sa.Column("decision_maker_types", sa.JSON(), nullable=True),
        sa.Column("buying_roles", sa.JSON(), nullable=True),
        sa.Column("buyer_personas", sa.JSON(), nullable=True),
        sa.Column("pain_points", sa.JSON(), nullable=True),
        sa.Column("business_problems", sa.JSON(), nullable=True),
        sa.Column("current_challenges", sa.JSON(), nullable=True),
        sa.Column("use_cases", sa.JSON(), nullable=True),
        sa.Column("desired_outcomes", sa.JSON(), nullable=True),
        sa.Column("benefits", sa.JSON(), nullable=True),
        sa.Column("must_have_rules", sa.JSON(), nullable=True),
        sa.Column("nice_to_have_rules", sa.JSON(), nullable=True),
        sa.Column("exclusion_rules", sa.JSON(), nullable=True),
        sa.Column("positive_keywords", sa.JSON(), nullable=True),
        sa.Column("negative_keywords", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("definition_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("definition_hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_offerings_user_id", "offerings", ["user_id"])
    op.create_index("ix_offerings_user_status", "offerings", ["user_id", "status"])
    op.create_index("ix_offerings_user_updated", "offerings", ["user_id", "updated_at"])

    op.create_table(
        "offering_match_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("offering_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("total_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("strong_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("potential_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("poor_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("definition_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["offering_id"], ["offerings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_offering_match_jobs_offering", "offering_match_jobs", ["offering_id"])
    op.create_index("ix_offering_match_jobs_status", "offering_match_jobs", ["status"])

    op.create_table(
        "offering_match_job_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("icp_record_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="QUEUED"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["offering_match_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["icp_record_id"], ["icp_records.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "icp_record_id", name="uq_match_job_icp"),
    )
    op.create_index("ix_match_job_items_job_status", "offering_match_job_items", ["job_id", "status"])

    op.create_table(
        "offering_matches",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("offering_id", sa.Integer(), nullable=False),
        sa.Column("icp_record_id", sa.Integer(), nullable=False),
        sa.Column("fit_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("industry_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("job_title_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("department_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("company_size_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pain_use_case_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("seniority_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("buying_signal_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("match_tier", sa.String(length=32), nullable=False, server_default="poor"),
        sa.Column("match_reasons", sa.JSON(), nullable=True),
        sa.Column("ai_analysis", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ai_matched"),
        sa.Column("offering_definition_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("reviewed_by", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["offering_id"], ["offerings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["icp_record_id"], ["icp_records.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("offering_id", "icp_record_id", name="uq_offering_icp_match"),
    )
    op.create_index("ix_offering_matches_offering_score", "offering_matches", ["offering_id", "fit_score"])
    op.create_index("ix_offering_matches_offering_status", "offering_matches", ["offering_id", "status"])
    op.create_index("ix_offering_matches_offering_tier", "offering_matches", ["offering_id", "match_tier"])
    op.create_index("ix_offering_matches_icp", "offering_matches", ["icp_record_id"])


def downgrade() -> None:
    op.drop_index("ix_offering_matches_icp", table_name="offering_matches")
    op.drop_index("ix_offering_matches_offering_tier", table_name="offering_matches")
    op.drop_index("ix_offering_matches_offering_status", table_name="offering_matches")
    op.drop_index("ix_offering_matches_offering_score", table_name="offering_matches")
    op.drop_table("offering_matches")
    op.drop_index("ix_match_job_items_job_status", table_name="offering_match_job_items")
    op.drop_table("offering_match_job_items")
    op.drop_index("ix_offering_match_jobs_status", table_name="offering_match_jobs")
    op.drop_index("ix_offering_match_jobs_offering", table_name="offering_match_jobs")
    op.drop_table("offering_match_jobs")
    op.drop_index("ix_offerings_user_updated", table_name="offerings")
    op.drop_index("ix_offerings_user_status", table_name="offerings")
    op.drop_index("ix_offerings_user_id", table_name="offerings")
    op.drop_table("offerings")
