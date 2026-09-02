"""Add email_template JSON column to offerings.

Revision ID: 022
Revises: 021
Create Date: 2026-09-02 13:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "022"
down_revision: Union[str, None] = "021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("offerings", sa.Column("email_template", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("offerings", "email_template")
