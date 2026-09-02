"""Add email_template JSON column to offerings.

Revision ID: 022
Revises: 021
Create Date: 2026-09-02 13:00:00.000000
"""
import sys
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from column_utils import add_column_if_missing

revision: str = "022"
down_revision: Union[str, None] = "021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    add_column_if_missing(
        "offerings",
        sa.Column("email_template", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("offerings", "email_template")
