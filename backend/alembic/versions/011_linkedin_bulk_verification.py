"""Add verification fields and job phase counters for bulk LinkedIn jobs.

Revision ID: 011
Revises: 010
Create Date: 2026-08-19 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "linkedin_bulk_jobs",
        sa.Column("phase", sa.String(length=32), nullable=False, server_default="pending"),
    )
    op.add_column(
        "linkedin_bulk_jobs",
        sa.Column("verified_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "linkedin_bulk_jobs",
        sa.Column("mismatch_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "linkedin_bulk_jobs",
        sa.Column("review_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "linkedin_bulk_jobs",
        sa.Column("excel_finalized", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.add_column(
        "linkedin_bulk_job_items",
        sa.Column(
            "verification_status",
            sa.String(length=32),
            nullable=False,
            server_default="NOT_VERIFIED",
        ),
    )
    op.add_column(
        "linkedin_bulk_job_items",
        sa.Column("verification_score", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("linkedin_bulk_job_items", sa.Column("name_match", sa.Boolean(), nullable=True))
    op.add_column(
        "linkedin_bulk_job_items", sa.Column("designation_match", sa.Boolean(), nullable=True)
    )
    op.add_column("linkedin_bulk_job_items", sa.Column("company_match", sa.Boolean(), nullable=True))
    op.add_column("linkedin_bulk_job_items", sa.Column("location_match", sa.Boolean(), nullable=True))
    op.add_column("linkedin_bulk_job_items", sa.Column("verification_reason", sa.Text(), nullable=True))
    op.create_index(
        "ix_bulk_items_job_verify",
        "linkedin_bulk_job_items",
        ["job_id", "verification_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_bulk_items_job_verify", table_name="linkedin_bulk_job_items")
    op.drop_column("linkedin_bulk_job_items", "verification_reason")
    op.drop_column("linkedin_bulk_job_items", "location_match")
    op.drop_column("linkedin_bulk_job_items", "company_match")
    op.drop_column("linkedin_bulk_job_items", "designation_match")
    op.drop_column("linkedin_bulk_job_items", "name_match")
    op.drop_column("linkedin_bulk_job_items", "verification_score")
    op.drop_column("linkedin_bulk_job_items", "verification_status")
    op.drop_column("linkedin_bulk_jobs", "excel_finalized")
    op.drop_column("linkedin_bulk_jobs", "review_count")
    op.drop_column("linkedin_bulk_jobs", "mismatch_count")
    op.drop_column("linkedin_bulk_jobs", "verified_count")
    op.drop_column("linkedin_bulk_jobs", "phase")
