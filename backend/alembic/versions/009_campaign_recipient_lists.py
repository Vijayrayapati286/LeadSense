"""Add campaign_recipient_lists (non-exclusive per-campaign list membership)

A recipient previously could only belong to one list per campaign, because
list membership was tracked via the single-valued CampaignRecipient.group_id
column. Adding them to a second list silently moved them out of the first,
which could make an existing list appear to lose members or disappear
entirely. This table tracks membership separately and additively — existing
group_id values are backfilled here so current lists are preserved.

Revision ID: 009
Revises: 008
Create Date: 2026-07-31 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "campaign_recipient_lists",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("campaign_id", sa.Integer(), sa.ForeignKey("campaigns.id"), nullable=False),
        sa.Column("recipient_id", sa.Integer(), sa.ForeignKey("recipients.id"), nullable=False),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("recipient_groups.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("campaign_id", "recipient_id", "group_id", name="uq_campaign_recipient_list"),
    )

    op.execute(
        """
        INSERT INTO campaign_recipient_lists (campaign_id, recipient_id, group_id)
        SELECT campaign_id, recipient_id, group_id
        FROM campaign_recipients
        WHERE group_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_table("campaign_recipient_lists")
