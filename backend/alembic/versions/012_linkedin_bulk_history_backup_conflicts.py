"""Add conflict resolution, resolved values, and backup metadata for bulk jobs.

Revision ID: 012
Revises: 011
Create Date: 2026-08-20 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "linkedin_bulk_jobs",
        sa.Column("needs_review_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "linkedin_bulk_jobs",
        sa.Column("resolved_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "linkedin_bulk_jobs",
        sa.Column("backup_status", sa.String(length=32), nullable=False, server_default="none"),
    )
    op.add_column(
        "linkedin_bulk_jobs",
        sa.Column("backup_file_path", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "linkedin_bulk_jobs",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.add_column(
        "linkedin_bulk_job_items",
        sa.Column("resolved_name", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "linkedin_bulk_job_items",
        sa.Column("resolved_designation", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "linkedin_bulk_job_items",
        sa.Column("resolved_company", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "linkedin_bulk_job_items",
        sa.Column("resolved_location", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "linkedin_bulk_job_items",
        sa.Column("resolution_summary", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "linkedin_bulk_job_items",
        sa.Column("resolved_by", sa.Integer(), nullable=True),
    )
    op.add_column(
        "linkedin_bulk_job_items",
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "linkedin_bulk_conflict_resolutions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "job_item_id",
            sa.Integer(),
            sa.ForeignKey("linkedin_bulk_job_items.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("field", sa.String(length=64), nullable=False),
        sa.Column("uploaded_value", sa.Text(), nullable=True),
        sa.Column("extracted_value", sa.Text(), nullable=True),
        sa.Column("resolution", sa.String(length=32), nullable=False),
        sa.Column("resolved_value", sa.Text(), nullable=True),
        sa.Column("resolved_by", sa.Integer(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_bulk_conflict_item_field",
        "linkedin_bulk_conflict_resolutions",
        ["job_item_id", "field"],
    )

    op.create_table(
        "linkedin_bulk_backups",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "job_id",
            sa.String(length=36),
            sa.ForeignKey("linkedin_bulk_jobs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("user_id", sa.Integer(), nullable=True, index=True),
        sa.Column("backup_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("file_path", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ready"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("linkedin_bulk_backups")
    op.drop_index("ix_bulk_conflict_item_field", table_name="linkedin_bulk_conflict_resolutions")
    op.drop_table("linkedin_bulk_conflict_resolutions")
    op.drop_column("linkedin_bulk_job_items", "resolved_at")
    op.drop_column("linkedin_bulk_job_items", "resolved_by")
    op.drop_column("linkedin_bulk_job_items", "resolution_summary")
    op.drop_column("linkedin_bulk_job_items", "resolved_location")
    op.drop_column("linkedin_bulk_job_items", "resolved_company")
    op.drop_column("linkedin_bulk_job_items", "resolved_designation")
    op.drop_column("linkedin_bulk_job_items", "resolved_name")
    op.drop_column("linkedin_bulk_jobs", "started_at")
    op.drop_column("linkedin_bulk_jobs", "backup_file_path")
    op.drop_column("linkedin_bulk_jobs", "backup_status")
    op.drop_column("linkedin_bulk_jobs", "resolved_count")
    op.drop_column("linkedin_bulk_jobs", "needs_review_count")
