"""Add profile image URL column to icp_records.

Revision ID: 024
Revises: 023
Create Date: 2026-09-07 11:10:00.000000
"""
import sys
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from column_utils import add_column_if_missing

revision: str = "024"
down_revision: Union[str, None] = "023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    add_column_if_missing(
        "icp_records",
        sa.Column("image", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("icp_records", "image")
