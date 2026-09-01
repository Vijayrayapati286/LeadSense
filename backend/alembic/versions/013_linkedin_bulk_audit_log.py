"""Store who changed which field on bulk conflict resolutions.

Revision ID: 013
Revises: 012
Create Date: 2026-08-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "linkedin_bulk_conflict_resolutions",
        sa.Column("resolved_by_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "linkedin_bulk_conflict_resolutions",
        sa.Column("resolved_by_email", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "linkedin_bulk_conflict_resolutions",
        sa.Column("change_summary", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("linkedin_bulk_conflict_resolutions", "change_summary")
    op.drop_column("linkedin_bulk_conflict_resolutions", "resolved_by_email")
    op.drop_column("linkedin_bulk_conflict_resolutions", "resolved_by_name")
