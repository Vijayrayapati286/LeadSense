"""Add vouchers JSON column to offerings.

Revision ID: 021
Revises: 020
Create Date: 2026-09-02 12:45:00.000000
"""
import sys
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from column_utils import add_column_if_missing

revision: str = "021"
down_revision: Union[str, None] = "020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    add_column_if_missing(
        "offerings",
        sa.Column("vouchers", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("offerings", "vouchers")
