"""Add email column to icp_records.

Revision ID: 020
Revises: 019
Create Date: 2026-09-02 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "020"
down_revision: Union[str, None] = "019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("icp_records", sa.Column("email", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("icp_records", "email")
