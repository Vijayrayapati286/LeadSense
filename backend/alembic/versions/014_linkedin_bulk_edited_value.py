"""Store manual-edit value separately from resolved value.

Revision ID: 014
Revises: 013
Create Date: 2026-08-25 02:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "linkedin_bulk_conflict_resolutions",
        sa.Column("edited_value", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("linkedin_bulk_conflict_resolutions", "edited_value")
