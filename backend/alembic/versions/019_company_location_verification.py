"""Add company location match/resolved columns for bulk verification.

Revision ID: 019
Revises: 018
Create Date: 2026-08-26 18:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "019"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "linkedin_bulk_job_items",
        sa.Column("company_location_match", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "linkedin_bulk_job_items",
        sa.Column("resolved_company_location", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("linkedin_bulk_job_items", "resolved_company_location")
    op.drop_column("linkedin_bulk_job_items", "company_location_match")
