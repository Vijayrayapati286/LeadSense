"""Add vouchers JSON column to offerings.

Revision ID: 021
Revises: 020
Create Date: 2026-09-02 12:45:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "021"
down_revision: Union[str, None] = "020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("offerings", sa.Column("vouchers", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("offerings", "vouchers")
