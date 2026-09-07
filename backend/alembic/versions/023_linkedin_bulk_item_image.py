"""Add image URL column to LinkedIn bulk job items.

Revision ID: 023
Revises: 022
Create Date: 2026-09-04 12:30:00.000000
"""
import sys
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from column_utils import add_column_if_missing

revision: str = "023"
down_revision: Union[str, None] = "022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    add_column_if_missing(
        "linkedin_bulk_job_items",
        sa.Column("image", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("linkedin_bulk_job_items", "image")
