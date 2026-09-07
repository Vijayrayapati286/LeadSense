"""Add richer AI draft fields to offerings.

Revision ID: 025
Revises: 024
Create Date: 2026-09-07 12:00:00.000000
"""
import sys
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from column_utils import add_column_if_missing

revision: str = "025"
down_revision: Union[str, None] = "024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    add_column_if_missing("offerings", sa.Column("target_customer", sa.Text(), nullable=True))
    add_column_if_missing("offerings", sa.Column("target_company_size", sa.JSON(), nullable=True))
    add_column_if_missing("offerings", sa.Column("selling_points", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("offerings", "selling_points")
    op.drop_column("offerings", "target_company_size")
    op.drop_column("offerings", "target_customer")
