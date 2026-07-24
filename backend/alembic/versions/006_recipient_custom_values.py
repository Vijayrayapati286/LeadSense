"""Add recipient_custom_values table (per-prospect custom merge-field values)

Revision ID: 006
Revises: 005
Create Date: 2026-07-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "recipient_custom_values",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("recipient_id", sa.Integer(), sa.ForeignKey("recipients.id"), nullable=False),
        sa.Column("custom_field_id", sa.Integer(), sa.ForeignKey("custom_fields.id"), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.UniqueConstraint("recipient_id", "custom_field_id", name="uq_recipient_custom_field"),
    )


def downgrade() -> None:
    op.drop_table("recipient_custom_values")
