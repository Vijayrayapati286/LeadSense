"""Create icp_records table for verified ICP Database.

Revision ID: 015
Revises: 014
Create Date: 2026-08-25 14:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "icp_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=500), nullable=True),
        sa.Column("company_name", sa.String(length=500), nullable=True),
        sa.Column("designation", sa.String(length=500), nullable=True),
        sa.Column("about", sa.Text(), nullable=True),
        sa.Column("linkedin_url", sa.String(length=500), nullable=True),
        sa.Column("industry", sa.String(length=255), nullable=True),
        sa.Column("company_size", sa.String(length=100), nullable=True),
        sa.Column("location", sa.String(length=500), nullable=True),
        sa.Column("company_website", sa.String(length=500), nullable=True),
        sa.Column("icp_status", sa.String(length=50), nullable=False, server_default="verified"),
        sa.Column("icp_score", sa.Integer(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("verification_status", sa.String(length=32), nullable=False, server_default="VERIFIED"),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False, server_default="linkedin_bulk"),
        sa.Column("source_record_id", sa.Integer(), nullable=True),
        sa.Column("source_job_id", sa.String(length=36), nullable=True),
        sa.Column("dedupe_key", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "linkedin_url", name="uq_icp_user_linkedin_url"),
    )
    op.create_index("ix_icp_records_user_id", "icp_records", ["user_id"])
    op.create_index("ix_icp_records_linkedin_url", "icp_records", ["linkedin_url"])
    op.create_index("ix_icp_records_source_record_id", "icp_records", ["source_record_id"])
    op.create_index("ix_icp_records_source_job_id", "icp_records", ["source_job_id"])
    op.create_index("ix_icp_user_verified_at", "icp_records", ["user_id", "verified_at"])
    op.create_index("ix_icp_user_industry", "icp_records", ["user_id", "industry"])
    op.create_index("ix_icp_user_dedupe", "icp_records", ["user_id", "dedupe_key"])


def downgrade() -> None:
    op.drop_index("ix_icp_user_dedupe", table_name="icp_records")
    op.drop_index("ix_icp_user_industry", table_name="icp_records")
    op.drop_index("ix_icp_user_verified_at", table_name="icp_records")
    op.drop_index("ix_icp_records_source_job_id", table_name="icp_records")
    op.drop_index("ix_icp_records_source_record_id", table_name="icp_records")
    op.drop_index("ix_icp_records_linkedin_url", table_name="icp_records")
    op.drop_index("ix_icp_records_user_id", table_name="icp_records")
    op.drop_table("icp_records")
