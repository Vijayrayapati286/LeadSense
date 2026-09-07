"""LinkedIn bulk extraction jobs, items, and attempt history.

Revision ID: 010
Revises: 009
Create Date: 2026-08-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "linkedin_bulk_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True, index=True),
        sa.Column("original_file_name", sa.String(length=500), nullable=True),
        sa.Column("input_columns", sa.JSON(), nullable=True),
        sa.Column("total_urls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retrying_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending", index=True),
        sa.Column("result_file_path", sa.String(length=500), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "linkedin_bulk_job_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "job_id",
            sa.String(length=36),
            sa.ForeignKey("linkedin_bulk_jobs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("profile_url", sa.String(length=1000), nullable=False),
        sa.Column("normalized_url", sa.String(length=500), nullable=False, server_default="", index=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="QUEUED", index=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "dedupe_of_id",
            sa.Integer(),
            sa.ForeignKey("linkedin_bulk_job_items.id"),
            nullable=True,
            index=True,
        ),
        sa.Column("source_row_json", sa.JSON(), nullable=True),
        sa.Column("name", sa.String(length=500), nullable=True),
        sa.Column("company", sa.String(length=500), nullable=True),
        sa.Column("designation", sa.String(length=500), nullable=True),
        sa.Column("about", sa.Text(), nullable=True),
        sa.Column("headline", sa.String(length=1000), nullable=True),
        sa.Column("location", sa.String(length=500), nullable=True),
        sa.Column("followers", sa.Integer(), nullable=True),
        sa.Column("connections", sa.Integer(), nullable=True),
        sa.Column("extraction_response", sa.JSON(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("retry_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_bulk_items_job_status", "linkedin_bulk_job_items", ["job_id", "status"])
    op.create_index("ix_bulk_items_retry_after", "linkedin_bulk_job_items", ["status", "retry_after"])
    op.create_index(
        "ix_bulk_items_job_row",
        "linkedin_bulk_job_items",
        ["job_id", "source_row_number"],
        unique=True,
    )
    op.create_table(
        "linkedin_extraction_attempts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "job_item_id",
            sa.Integer(),
            sa.ForeignKey("linkedin_bulk_job_items.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("request_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("request_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="FAILED"),
        sa.Column("response", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("apify_run_id", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("linkedin_extraction_attempts")
    op.drop_table("linkedin_bulk_job_items")
    op.drop_table("linkedin_bulk_jobs")
