"""Add custom_fields table (approved merge-field names beyond the standard set)

Revision ID: 005
Revises: 004
Create Date: 2026-07-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "custom_fields",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("name", name="uq_custom_fields_name"),
    )
    op.create_index("ix_custom_fields_name", "custom_fields", ["name"])


def downgrade() -> None:
    op.drop_index("ix_custom_fields_name", table_name="custom_fields")
    op.drop_table("custom_fields")
