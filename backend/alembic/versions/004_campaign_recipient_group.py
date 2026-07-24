"""Add CampaignRecipient.group_id (per-campaign list tagging)

Revision ID: 004
Revises: 003
Create Date: 2026-07-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("campaign_recipients", sa.Column("group_id", sa.Integer(), nullable=True))
    with op.batch_alter_table("campaign_recipients") as batch_op:
        batch_op.create_foreign_key(
            "fk_campaign_recipients_group_id", "recipient_groups", ["group_id"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("campaign_recipients") as batch_op:
        batch_op.drop_constraint("fk_campaign_recipients_group_id", type_="foreignkey")
        batch_op.drop_column("group_id")
